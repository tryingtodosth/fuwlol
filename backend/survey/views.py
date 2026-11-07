"""`POST /api/survey/` and `POST /api/survey/withdraw/` — the two endpoints. No GET anywhere.

Write-only for the reason feedback/ is, and for a stronger one: the rows are health data and
data about an offence (`models.py`), read by the people running the study in the Django admin
and exported by `manage.py export_survey`. An endpoint that listed them would be a way for
anybody to read everybody's sheet. Withdrawal is the one thing a person can do to their own
sheet from outside, and only with the key they asked for when they sent it.
"""
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import rules
from .models import SurveyResponse
from .serializers import SurveyWithdrawSerializer, SurveyWriteSerializer


class SurveyView(APIView):
    """Anonymous, throttled per IP, one row per call — and nothing about the caller stored.

    **Token authentication only — deliberately not the project default**, exactly as in
    `feedback/views.py`: LSD is served from fuw.lol itself (`/lsd`), so a visitor signed in to
    the archive in the same browser sends the archive's session cookie with this POST whether
    they meant to or not. With `SessionAuthentication` in the list DRF would enforce CSRF on a
    request that carries no CSRF token and answer **403 to somebody who has just spent fifteen
    minutes on a questionnaire**. Dropping session auth makes the cookie irrelevant instead of
    fatal; the client also sends `credentials: 'omit'`, so in practice no cookie arrives at all.

    Unlike feedback/, this view never reads `request.user`, `REMOTE_ADDR` or the user agent: a
    valid token in the header is accepted and ignored. The throttle is the one place the address
    is used — a counter in the throttle cache, keyed by address for an hour, holding no row id.
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [AllowAny]
    throttle_scope = 'survey'
    throttle_classes = [ScopedRateThrottle]

    def post(self, request):
        s = SurveyWriteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        # The key exists in plain text exactly here, in this response, and then only in the
        # person's hands (or their QR). The row keeps its hash.
        key = rules.new_key() if d.get('wants_key') else None
        row = SurveyResponse.objects.create(
            survey=d['survey'],
            version=d['version'],
            consent_version=d['consent_version'],
            locale=d.get('locale', ''),
            duration_s=d.get('duration_s'),
            answers=d['answers'],
            contact_hash=rules.hash_contact(d.get('contact_email', '')),
            key_hash=rules.hash_key(key) if key else '',
        )
        # The id goes back so the client can say "sheet #12 arrived". There is nothing to fetch
        # with it, and the number itself says only how many sheets came before this one.
        return Response({'ok': True, 'id': row.id, 'key': key}, status=status.HTTP_201_CREATED)


class SurveyWithdrawView(APIView):
    """`POST {"key": …}` blanks the sheet that key belongs to (`rules.withdraw`).

    The same authentication arrangement as above, for the same reason. The key is a 256-bit
    secret only its holder has, so there is no oracle to protect: an unknown key is 404, a known
    one — withdrawn already or not — is 200, and a second call changes nothing. Throttled on
    its own scope, more tightly than sending: nobody withdraws sixty sheets an hour.
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [AllowAny]
    throttle_scope = 'survey_withdraw'
    throttle_classes = [ScopedRateThrottle]

    def post(self, request):
        s = SurveyWithdrawSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        row = rules.find_by_key(s.validated_data['key'])
        if row is None:
            raise NotFound('Nie ma ankiety z takim kluczem.')
        rules.withdraw(row)
        return Response({'ok': True, 'status': row.status})
