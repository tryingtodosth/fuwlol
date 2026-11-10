"""`POST /api/feedback/` — the one endpoint. There is no GET.

Write-only on purpose. Nobody but the people running the session needs to read the notes, they
read them in the Django admin, and an endpoint that lists them would be a way to read what
other people at the same session wrote — a small oracle of exactly the kind the root
`CLAUDE.md` rule 5 is about. Not implementing it is also the shortest path to today's deploy;
`feedback/CLAUDE.md` records it as left open rather than forgotten.
"""
from django.conf import settings
from django.utils.cache import patch_vary_headers
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from board.models import hash_ip

from .models import Feedback
from .serializers import FeedbackWriteSerializer


class FeedbackView(APIView):
    """Anonymous, throttled per IP, one row per call.

    **Token authentication only — deliberately not the project default.** WUM is served from
    fuw.lol itself (`/fum`), so a visitor who happens to be signed in to the archive in the
    same browser sends the archive's session cookie with this POST whether they meant to or
    not. With `SessionAuthentication` in the list, DRF would then enforce CSRF on a request that
    carries no CSRF token and answer **403 to somebody trying to file a bug report** — the one
    failure this endpoint must not have. Dropping session auth here makes the cookie irrelevant
    instead of fatal; the widget also sends `credentials: 'omit'`, so in practice no cookie is
    sent at all. `author` is therefore filled in only by a caller that passes a real
    `Authorization: Token …` (the archive's own frontend, if it ever files one).
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [AllowAny]
    throttle_scope = 'feedback'
    throttle_classes = [ScopedRateThrottle]

    # **Across origins, for this one endpoint only.** MedApp on its own domain (medapp.net, a
    # static copy on another host) files its notes here. The project-wide CORS list stays empty
    # in production — nothing else on this API is opened to another origin — and this view
    # answers the listed origins itself: `Access-Control-Allow-Origin` with that origin, POST and
    # the two headers the widget sends, never `Allow-Credentials` (the widget sends no cookie,
    # and a note needs none). The origin also decides `app`: a note from medapp.net is filed as
    # `medapp` whatever its body says. An origin not in the list gets no CORS headers, so a
    # browser there cannot read the answer — and the POST it may still send is just a note.
    def _cross_origin_app(self, request):
        return settings.FUWLOL_FEEDBACK_ORIGINS.get(request.META.get('HTTP_ORIGIN', ''))

    def get_throttles(self):
        # A preflight is not a note; it must not spend the session's allowance.
        return [] if self.request.method == 'OPTIONS' else super().get_throttles()

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        origin = request.META.get('HTTP_ORIGIN', '')
        if origin in settings.FUWLOL_FEEDBACK_ORIGINS:
            response['Access-Control-Allow-Origin'] = origin
            if request.method == 'OPTIONS':
                response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
                response['Access-Control-Allow-Headers'] = 'Content-Type, Accept'
                response['Access-Control-Max-Age'] = '86400'
        patch_vary_headers(response, ('Origin',))
        return response

    def post(self, request):
        s = FeedbackWriteSerializer(data=request.data, context={'request': request})
        s.is_valid(raise_exception=True)
        user = request.user if request.user.is_authenticated else None
        note = Feedback.objects.create(
            app=self._cross_origin_app(request) or s.validated_data.get('app') or 'skoki',
            kind=s.validated_data['kind'],
            text=s.validated_data['text'],
            location=s.validated_data.get('location', ''),
            locale=s.validated_data.get('locale', ''),
            contact=s.validated_data.get('contact') or '',
            ip_hash=hash_ip(request.META.get('REMOTE_ADDR', '')),
            author=user,
        )
        # The id goes back so the widget can say "note #12 arrived" — there is nothing to fetch
        # with it, and nothing else about the row is secret.
        return Response({'ok': True, 'id': note.id}, status=status.HTTP_201_CREATED)
