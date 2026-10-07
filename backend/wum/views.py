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
  table and nothing else;
- a practitioner (`rules.is_practitioner`, a WUM account with a `Practice`): its own practice,
  diary, patients and notes. Any WUM account may open a practice; the row is the mark.

No oracle (root `CLAUDE.md` rule 5): a login with an archive account's correct password is the
same 401 as a wrong password; a draft template, a withdrawn publication and a stranger's
withdraw attempt are all 404, byte for byte the 404 of an id that never existed.
"""
from datetime import date, datetime, timedelta

from django.contrib.auth import authenticate
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
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
from .models import VISIT_HORIZON_DAYS, Practice, PracticeNote, Publication, Template, Visit
from .serializers import (NoteWriteSerializer, PracticeWriteSerializer, PractitionerVisitSerializer,
                          PublicationMineSerializer, PublicationPublicSerializer, PublishSerializer,
                          ProfileSerializer, RegisterSerializer, TemplateDetailSerializer,
                          TemplateListSerializer, TemplateWriteSerializer, VisitDecisionSerializer,
                          VisitRequestSerializer, account_row, note_row, practice_row, visit_row)


class IsWumAccount(BasePermission):
    message = 'To nie jest konto WUM.'

    def has_permission(self, request, view):
        return rules.is_wum_account(request.user)


class IsPractitioner(BasePermission):
    message = 'To konto nie ma gabinetu.'

    def has_permission(self, request, view):
        return rules.is_practitioner(request.user)


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


# --- the practice round -----------------------------------------------------------------------

NOT_FOUND = {'detail': 'Nie znaleziono.'}
VISIT_ACTIONS = ('confirm', 'decline', 'cancel', 'complete', 'no_show')
ACTION_TO_STATUS = {'confirm': 'confirmed', 'decline': 'declined', 'cancel': 'cancelled',
                    'complete': 'completed', 'no_show': 'no_show'}


def _day(value, default):
    d = parse_date(value) if value else None
    return d or default


def _instant(value):
    """An aware instant from a query parameter, or None."""
    if not value:
        return None
    d = parse_datetime(value)
    if d is None:
        day = parse_date(value)
        if day is None:
            return None
        d = datetime.combine(day, datetime.min.time())
    return d if timezone.is_aware(d) else timezone.make_aware(d, rules.PRACTICE_TZ)


class PracticeListView(WumView):
    """Who is taking patients. Public; `listed` rows only, and never the owner's username."""
    permission_classes = [AllowAny]

    def get(self, request):
        qs = Practice.objects.filter(listed=True)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([practice_row(p) for p in page])


class PracticeDetailView(WumView):
    permission_classes = [AllowAny]

    def get(self, request, public_id):
        row = Practice.objects.filter(public_id=public_id).first()
        if row is None or not (row.listed or row.owner_id == getattr(request.user, 'id', None)):
            return Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        return Response(practice_row(row, own=row.owner_id == getattr(request.user, 'id', None)))


class PracticeSlotsView(WumView):
    """Open slots, `?from=YYYY-MM-DD&days=14`. What a patient books from; the server is the
    authority on what is free, so two phones cannot both be told a slot is open and both get it
    (`rules.request_visit` re-checks under a lock)."""
    permission_classes = [AllowAny]

    def get(self, request, public_id):
        row = Practice.objects.filter(public_id=public_id, listed=True).first()
        if row is None:
            return Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        today = timezone.localtime(timezone.now(), rules.PRACTICE_TZ).date()
        from_day = _day(request.query_params.get('from'), today)
        try:
            days = int(request.query_params.get('days', 14))
        except ValueError:
            days = 14
        slots = rules.open_slots(row, from_day, days)
        return Response({'practice': practice_row(row), 'from': from_day, 'days': max(1, min(days, VISIT_HORIZON_DAYS)),
                         'slots': [{'start': s, 'end': e} for (s, e) in slots]})


class PracticeMeView(WumView):
    """The practitioner's own practice. GET answers 404 until it exists; PUT opens or replaces it.
    Any WUM account may PUT once — that is how a practice is opened."""
    throttle_classes = [UnsafeScopedThrottle]
    throttle_scope = 'wum_practice'

    def get_permissions(self):
        return [IsWumAccount()]

    def get(self, request):
        row = Practice.objects.filter(owner=request.user).first()
        if row is None:
            return Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        return Response(practice_row(row, own=True))

    def put(self, request):
        s = PracticeWriteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        existed = Practice.objects.filter(owner=request.user).exists()
        row = s.save(owner=request.user)
        return Response(practice_row(row, own=True),
                        status=status.HTTP_200_OK if existed else status.HTTP_201_CREATED)


class PracticeVisitsView(WumView):
    """The diary. GET `?from=&to=` (instants or days; default the coming 14 days from today's
    start) lists every status, blocks included. POST writes the practitioner's own entry."""
    permission_classes = [IsPractitioner]
    throttle_classes = [UnsafeScopedThrottle]
    throttle_scope = 'wum_visit'

    def get(self, request):
        practice = request.user.wum_practice
        start_of_today = timezone.make_aware(
            datetime.combine(timezone.localtime(timezone.now(), rules.PRACTICE_TZ).date(), datetime.min.time()),
            rules.PRACTICE_TZ)
        lo = _instant(request.query_params.get('from')) or start_of_today
        hi = _instant(request.query_params.get('to')) or lo + timedelta(days=14)
        if hi - lo > timedelta(days=VISIT_HORIZON_DAYS + 31):
            hi = lo + timedelta(days=VISIT_HORIZON_DAYS + 31)
        rows = (Visit.objects.filter(practice=practice, start__lt=hi, end__gt=lo)
                .select_related('patient__wum_profile', 'practice'))
        return Response({'from': lo, 'to': hi, 'visits': [visit_row(v, 'practitioner') for v in rows]})

    def post(self, request):
        s = PractitionerVisitSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        row, problems = rules.practitioner_visit(request.user.wum_practice, d.get('patient'), d['start'],
                                                 d['end'], d.get('note', ''))
        if problems:
            return Response({'start': problems}, status=status.HTTP_400_BAD_REQUEST)
        return Response(visit_row(row, 'practitioner'), status=status.HTTP_201_CREATED)


class PracticePatientsView(WumView):
    permission_classes = [IsPractitioner]

    def get(self, request):
        rows = rules.practice_patients(request.user.wum_practice)
        return Response([{
            'username': r['patient__username'],
            'first_name': r['patient__wum_profile__first_name'] or '',
            'surname': r['patient__wum_profile__surname'] or '',
            'contact_email': r['patient__wum_profile__contact_email'] or '',
            'contact_phone': r['patient__wum_profile__contact_phone'] or '',
            'visits': r['visits'],
            'last_start': r['last_start'],
        } for r in rows])


def _patient_of(practice, username):
    """A patient this practice may write about: somebody who has (had) a visit here. Anybody
    else is the 404 of a username that does not exist — a practitioner cannot use this to learn
    whether a stranger has an account."""
    return (Visit.objects.filter(practice=practice, patient__username__iexact=username)
            .select_related('patient').values_list('patient', flat=True).first())


class PracticePatientView(WumView):
    """One patient of the practice: their card, their visits here and every note about them."""
    permission_classes = [IsPractitioner]
    throttle_classes = [UnsafeScopedThrottle]
    throttle_scope = 'wum_practice'

    def get(self, request, username):
        practice = request.user.wum_practice
        patient_id = _patient_of(practice, username)
        if patient_id is None:
            return Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        from django.contrib.auth.models import User
        patient = User.objects.select_related('wum_profile').get(pk=patient_id)
        visits = Visit.objects.filter(practice=practice, patient=patient).select_related('practice').order_by('-start')
        notes = PracticeNote.objects.filter(practice=practice, patient=patient).select_related('practice', 'visit')
        from .serializers import patient_card
        return Response({'patient': patient_card(patient),
                         'visits': [visit_row(v, 'practitioner') for v in visits],
                         'notes': [note_row(n, 'practitioner') for n in notes]})

    def post(self, request, username):
        """A new note. Append-only; `amends` names the note it corrects."""
        practice = request.user.wum_practice
        patient_id = _patient_of(practice, username)
        if patient_id is None:
            return Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        s = NoteWriteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        visit = amends = None
        if d.get('visit'):
            visit = Visit.objects.filter(public_id=d['visit'], practice=practice, patient_id=patient_id).first()
            if visit is None:
                return Response({'visit': ['Nie ma takiej wizyty u tego pacjenta.']}, status=status.HTTP_400_BAD_REQUEST)
        if d.get('amends'):
            amends = PracticeNote.objects.filter(public_id=d['amends'], practice=practice, patient_id=patient_id).first()
            if amends is None:
                return Response({'amends': ['Nie ma takiej notatki u tego pacjenta.']}, status=status.HTTP_400_BAD_REQUEST)
        shared = bool(d.get('shared_with_patient'))
        row = PracticeNote.objects.create(practice=practice, patient_id=patient_id, visit=visit, amends=amends,
                                          body=d['body'].strip(), shared_with_patient=shared,
                                          shared_at=timezone.now() if shared else None)
        return Response(note_row(row, 'practitioner'), status=status.HTTP_201_CREATED)


class NoteShareView(WumView):
    permission_classes = [IsPractitioner]
    throttle_classes = [UnsafeScopedThrottle]
    throttle_scope = 'wum_practice'

    def post(self, request, public_id):
        row = PracticeNote.objects.filter(public_id=public_id, practice=request.user.wum_practice).first()
        if row is None:
            return Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        return Response(note_row(rules.share_note(row), 'practitioner'))


class VisitsView(WumView):
    """POST: a patient asks for a slot."""
    permission_classes = [IsWumAccount]
    throttle_classes = [UnsafeScopedThrottle]
    throttle_scope = 'wum_visit'

    def post(self, request):
        s = VisitRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        practice = Practice.objects.filter(public_id=d['practice'], listed=True).first()
        if practice is None:
            return Response({'practice': ['Nieznany gabinet.']}, status=status.HTTP_400_BAD_REQUEST)
        row, problems = rules.request_visit(practice, request.user, d['start'], d.get('reason', ''))
        if problems:
            return Response({'start': problems}, status=status.HTTP_400_BAD_REQUEST)
        return Response(visit_row(row, 'patient'), status=status.HTTP_201_CREATED)


class VisitsMineView(WumView):
    permission_classes = [IsWumAccount]

    def get(self, request):
        rows = Visit.objects.filter(patient=request.user).select_related('practice').order_by('-start')
        return Response([visit_row(v, 'patient') for v in rows])


class VisitActionView(WumView):
    """`confirm | decline | cancel | complete | no_show`. Who the caller is decides which moves
    exist (`rules.transition`); a visit that is neither theirs as patient nor in their practice
    is the 404 of an unknown id."""
    permission_classes = [IsWumAccount]
    throttle_classes = [UnsafeScopedThrottle]
    throttle_scope = 'wum_visit'

    def post(self, request, public_id, action):
        if action not in VISIT_ACTIONS:
            return Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        row = Visit.objects.filter(public_id=public_id).select_related('practice', 'patient__wum_profile').first()
        if row is None:
            return Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        if row.practice.owner_id == request.user.id:
            actor = 'practitioner'
        elif row.patient_id == request.user.id:
            actor = 'patient'
        else:
            return Response(NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        s = VisitDecisionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        done = rules.transition(row, ACTION_TO_STATUS[action], actor, note=s.validated_data.get('note'))
        if done is None:
            return Response({'status': ['Tej zmiany nie można już wykonać.']}, status=status.HTTP_400_BAD_REQUEST)
        return Response(visit_row(done, actor))


class NotesMineView(WumView):
    """What a patient may read: the notes shared with them."""
    permission_classes = [IsWumAccount]

    def get(self, request):
        return Response([note_row(n, 'patient') for n in rules.notes_for_patient(request.user)])
