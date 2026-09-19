r"""The seven consent endpoints. None of them decides anything — `consent/rules.py` does.

    POST /api/people/<slug>/claims/              „Jesteś tą osobą?” — send me the link
    POST /api/people/<slug>/claims/manage-link/  send me the settings link again
    POST /api/claims/confirm/                    the click in the mailbox
    GET  /api/claims/manage/?token=              what my current wish is
    POST /api/claims/manage/                     change it (applies at once)
    POST /api/claims/manage/withdraw/            "that is not me after all"
    GET  /api/claims/queue/                      the staff queue   (is_staff)
    POST /api/claims/<id>/decide/                approve / reject  (is_staff)

**Two of these must not be oracles, and that shapes their whole signature.** The request
and the manage-link endpoints answer 202 with a masked address whatever happened behind
them — sent, capped, no such claim, honeypot — because every distinguishable answer is a
question somebody could ask about a colleague's mailbox by filling in our form. The one
exception is 503, and only when the mail itself failed: nothing was sent, so nothing is
leaked by saying so, and the alternative is a person waiting for a message that will
never come (house rule: flag it, don't fake it).

The profile lookup goes the other way: a person who is not listed answers **404**, the
same 404 a name nobody ever added answers. That is the honest answer as well as the safe
one — for a stranger, an opted-out person genuinely is not here.

Throttles use `FixedScopeThrottle` from `archive/views.py` rather than a copy: DRF's own
`ScopedRateThrottle` reads the scope off the *view*, so an instance handed a scope by hand
silently allows everything — a bug this project has already shipped once.
"""
from django.shortcuts import get_object_or_404
from rest_framework import status as http
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.trust import mask_email
from archive.views import FixedScopeThrottle

from . import rules
from .models import PersonClaim
from .serializers import (ClaimRequestSerializer, DecideSerializer, EmailOnlySerializer,
                          ManageChangeSerializer, TokenSerializer, claim_row)

ACCEPTED = http.HTTP_202_ACCEPTED


class PersonClaimView(APIView):
    """POST — „Jesteś tą osobą?”. 202 {sent_to} always (see the module docstring)."""
    permission_classes = [AllowAny]

    def get_throttles(self):
        # Three an hour per address. This endpoint sends mail to somebody ELSE's mailbox,
        # which makes the rate a limit on what one visitor can do TO a third party, not on
        # what they can do to us.
        return [FixedScopeThrottle('claim_request')]

    def post(self, request, slug):
        person = rules.person_for_claim(slug)
        s = ClaimRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        if (data.get('website') or '').strip():
            # A bot. It gets the same 202 as everybody, having learned nothing, and having
            # spent one of its three attempts for the hour.
            return Response({'sent_to': mask_email(data['email'])}, status=ACCEPTED)
        out = rules.request_claim(person, data['email'], data['wish'], data.get('note', ''),
                                  request=request, user=request.user)
        return Response({'sent_to': out['sent_to']}, status=ACCEPTED)


class ManageLinkView(APIView):
    """POST {email} → 202 {sent_to}. Deliberately does NOT 404 for an unlisted person: the
    one thing somebody who asked to disappear must never lose is the way back."""
    permission_classes = [AllowAny]

    def get_throttles(self):
        return [FixedScopeThrottle('claim_manage')]

    def post(self, request, slug):
        s = EmailOnlySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        person = rules.person_for_manage(slug)
        out = rules.send_manage_link(person, s.validated_data['email'])
        return Response({'sent_to': out['sent_to']}, status=ACCEPTED)


class ClaimConfirmView(APIView):
    """POST {token} → 200 {ok, wish, applied, message}. AllowAny: the link is opened in
    whatever browser the mail was read in, and the token is the secret, not the session."""
    permission_classes = [AllowAny]

    def post(self, request):
        s = TokenSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(rules.confirm(s.validated_data['token']))


class ClaimManageView(APIView):
    """GET ?token= → the current wish. POST {token, wish} → change it, at once."""
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(rules.manage_state(request.query_params.get('token')))

    def post(self, request):
        s = ManageChangeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(rules.change_wish(s.validated_data['token'], s.validated_data['wish']))


class ClaimWithdrawView(APIView):
    """POST {token} → 200. „To jednak nie ja”."""
    permission_classes = [AllowAny]

    def post(self, request):
        s = TokenSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(rules.withdraw_claim(s.validated_data['token']))


class ClaimQueueView(APIView):
    """GET → the claims waiting for a human, newest first. `?status=` to see the rest.

    Staff, and deliberately not the trusted tier. A confirmed fuw.edu.pl address says
    somebody is around the Faculty; it does not qualify them to decide whether a stranger
    really is dr Kwant Niepewny, and that decision publishes a consent under somebody's
    name. Different power, different tier."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        wanted = request.query_params.get('status') or 'verified'
        qs = PersonClaim.objects.select_related('person', 'decided_by')
        if wanted != 'all':
            qs = qs.filter(status=wanted)
        return Response([claim_row(c) for c in qs[:200]])


class ClaimDecideView(APIView):
    """POST {decision, note?} → 200 the row. 409 when it has already been decided."""
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        s = DecideSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        claim = get_object_or_404(PersonClaim.objects.select_related('person'), pk=pk)
        claim = rules.decide(claim, request.user, s.validated_data['decision'],
                             s.validated_data.get('note', ''))
        return Response(claim_row(claim))
