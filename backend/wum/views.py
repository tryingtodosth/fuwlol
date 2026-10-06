"""`/api/wum/…` — the side app's accounts, example templates and anonymised publications.

**Token authentication only, on every view here** — the same reason as `feedback/views.py`: WUM
is served from fuw.lol itself (`/fum`), so a visitor signed in to the archive in the same browser
would send the archive's session cookie, and with `SessionAuthentication` in the list DRF would
demand a CSRF token the app never sends and answer 403. The app sends `credentials: 'omit'` and an
`Authorization: Token …` header of its own (stored under its own key, not the archive's).

Who may do what:

- anybody: register, log in, read published templates, read live publications;
- a WUM account (`rules.is_wum_account`): its own profile, publish, withdraw, list its own rows;
- staff (`is_staff`): write templates. Nothing else on this server is reachable with a WUM token
  and nothing here is reachable with the archive's powers — the two populations share the user
  table and nothing else.

No oracle (root `CLAUDE.md` rule 5): a login with an archive account's correct password is the
same 401 as a wrong password; a draft template, a withdrawn publication and a stranger's
withdraw attempt are all 404, byte for byte the 404 of an id that never existed.
"""
from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import SAFE_METHODS, AllowAny, BasePermission, IsAdminUser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.views import LoginUsernameThrottle

from . import rules
from .models import Publication, Template
from .serializers import (PublicationMineSerializer, PublicationPublicSerializer, PublishSerializer,
                          ProfileSerializer, RegisterSerializer, TemplateDetailSerializer,
                          TemplateListSerializer, TemplateWriteSerializer, account_row)


class IsWumAccount(BasePermission):
    message = 'To nie jest konto WUM.'

    def has_permission(self, request, view):
        return rules.is_wum_account(request.user)


class UnsafeScopedThrottle(ScopedRateThrottle):
    """Counts only writes. A view that is read on every app start and written once a month must
    not spend its write budget on the reads."""
    def allow_request(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return super().allow_request(request, view)


class WumView(APIView):
    authentication_classes = [TokenAuthentication]


def _session(user):
    token, _ = Token.objects.get_or_create(user=user)
    return {'token': token.key, 'account': account_row(user)}


# --- accounts ---------------------------------------------------------------------------------

class RegisterView(WumView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'wum_register'

    def post(self, request):
        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(_session(s.save()), status=status.HTTP_201_CREATED)


class LoginView(WumView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle, LoginUsernameThrottle]
    throttle_scope = 'wum_login'

    def post(self, request):
        ident = (request.data.get('username') or '').strip() if hasattr(request.data, 'get') else ''
        password = request.data.get('password') or '' if hasattr(request.data, 'get') else ''
        user = authenticate(request, username=ident, password=password)
        # An archive account with the right password is refused with the SAME sentence as a wrong
        # password: this endpoint must not confirm that a username exists on the archive.
        if user is None or not rules.is_wum_account(user):
            return Response({'detail': 'Zła nazwa lub hasło.'}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(_session(user))


class LogoutView(WumView):
    permission_classes = [IsWumAccount]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(WumView):
    permission_classes = [IsWumAccount]
    throttle_classes = [UnsafeScopedThrottle]
    throttle_scope = 'wum_profile'

    def get(self, request):
        return Response(account_row(request.user))

    def patch(self, request):
        s = ProfileSerializer(request.user.wum_profile, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(account_row(request.user))


# --- templates --------------------------------------------------------------------------------

class TemplateListView(WumView):
    throttle_classes = [UnsafeScopedThrottle]
    throttle_scope = 'wum_template_write'

    def get_permissions(self):
        return [IsAdminUser()] if self.request.method not in SAFE_METHODS else [AllowAny()]

    def get(self, request):
        qs = Template.objects.filter(status='published')
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(TemplateListSerializer(page, many=True).data)

    def post(self, request):
        s = TemplateWriteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        row = s.save(created_by=request.user)
        return Response(TemplateDetailSerializer(row).data, status=status.HTTP_201_CREATED)


class TemplateDetailView(WumView):
    throttle_classes = [UnsafeScopedThrottle]
    throttle_scope = 'wum_template_write'

    def get_permissions(self):
        return [IsAdminUser()] if self.request.method not in SAFE_METHODS else [AllowAny()]

    def get(self, request, slug):
        row = Template.objects.filter(slug=slug, status='published').first()
        if row is None:
            return Response({'detail': 'Nie znaleziono.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(TemplateDetailSerializer(row).data)

    def put(self, request, slug):
        row = Template.objects.filter(slug=slug).first()
        if row is None:
            return Response({'detail': 'Nie znaleziono.'}, status=status.HTTP_404_NOT_FOUND)
        s = TemplateWriteSerializer(row, data=request.data)
        s.is_valid(raise_exception=True)
        return Response(TemplateDetailSerializer(s.save()).data)

    def delete(self, request, slug):
        """Retires, never deletes: a template somebody started from last week is still the
        thing they started from."""
        row = Template.objects.filter(slug=slug).first()
        if row is None:
            return Response({'detail': 'Nie znaleziono.'}, status=status.HTTP_404_NOT_FOUND)
        row.status = 'retired'
        row.save(update_fields=['status', 'updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- publications -----------------------------------------------------------------------------

class PublicationListView(WumView):
    throttle_classes = [UnsafeScopedThrottle]
    throttle_scope = 'wum_publish'

    def get_permissions(self):
        return [IsWumAccount()] if self.request.method not in SAFE_METHODS else [AllowAny()]

    def get(self, request):
        qs = Publication.objects.filter(status='published')
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(PublicationPublicSerializer(page, many=True).data)

    def post(self, request):
        s = PublishSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        row, superseded = rules.publish(request.user, d['payload'], d['payload_version'],
                                        d['consent_text_version'])
        return Response({'id': str(row.public_id), 'published_month': row.published_month,
                         'superseded': str(superseded) if superseded else None},
                        status=status.HTTP_201_CREATED)


class PublicationMineView(WumView):
    permission_classes = [IsWumAccount]

    def get(self, request):
        rows = Publication.objects.filter(account=request.user)
        return Response(PublicationMineSerializer(rows, many=True).data)


class PublicationDetailView(WumView):
    permission_classes = [AllowAny]

    def get(self, request, public_id):
        row = Publication.objects.filter(public_id=public_id, status='published').first()
        if row is None:
            return Response({'detail': 'Nie znaleziono.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(PublicationPublicSerializer(row).data)


class PublicationWithdrawView(WumView):
    permission_classes = [IsWumAccount]

    def post(self, request, public_id):
        row = Publication.objects.filter(public_id=public_id).first()
        done = rules.withdraw(row, request.user) if row else None
        if done is None:
            return Response({'detail': 'Nie znaleziono.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(PublicationMineSerializer(done).data)
