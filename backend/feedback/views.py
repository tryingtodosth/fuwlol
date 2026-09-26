"""`POST /api/feedback/` — the one endpoint. There is no GET.

Write-only on purpose. Nobody but the people running the session needs to read the notes, they
read them in the Django admin, and an endpoint that lists them would be a way to read what
other people at the same session wrote — a small oracle of exactly the kind the root
`CLAUDE.md` rule 5 is about. Not implementing it is also the shortest path to today's deploy;
`feedback/CLAUDE.md` records it as left open rather than forgotten.
"""
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

    **Token authentication only — deliberately not the project default.** FwUMU is served from
    fuw.lol itself (`/fwumu`), so a visitor who happens to be signed in to the archive in the
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

    def post(self, request):
        s = FeedbackWriteSerializer(data=request.data, context={'request': request})
        s.is_valid(raise_exception=True)
        user = request.user if request.user.is_authenticated else None
        note = Feedback.objects.create(
            app=s.validated_data.get('app') or 'skoki',
            kind=s.validated_data['kind'],
            text=s.validated_data['text'],
            location=s.validated_data.get('location', ''),
            locale=s.validated_data.get('locale', ''),
            ip_hash=hash_ip(request.META.get('REMOTE_ADDR', '')),
            author=user,
        )
        # The id goes back so the widget can say "note #12 arrived" — there is nothing to fetch
        # with it, and nothing else about the row is secret.
        return Response({'ok': True, 'id': note.id}, status=status.HTTP_201_CREATED)
