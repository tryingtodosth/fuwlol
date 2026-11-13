"""The directory's endpoints (`/api/vetdir/…`). MedApp's vet app and its owner pages call them with
`fetch` from another origin (medapp.net is a static copy), so every view answers CORS itself for
settings.FUWLOL_VETDIR_ORIGINS, as `newsletter/views.py` does; the project-wide CORS list is
untouched and `CORS_URLS_REGEX` leaves these paths to the views.

No authentication class at all: the clinic is known by its key (header `X-Vetdir-Key`, compared in
constant time against a hash, `rules.key_matches`), the owner by a signed token from a mail; a
fuw.lol session cookie means nothing here and can never become a CSRF 403. A write needs a known
Origin (403 otherwise), because the mailed links point at the copy it came from.

    POST /listings/                           the card + e-mail + consent → 201 {id, key} once; mails the link
    POST /listings/confirm/            {token} the clinic's mailed link → listed
    GET  /listings/<id>/                      public card only while public; with the key: the clinic's view
    PUT  /listings/<id>/                      key: replace the card (re-mails the link while pending)
    POST /listings/<id>/unlist/               key: off the directory, for good
    POST /listings/<id>/requests/             an owner's wish → 202, always the same; mails the owner a link
    GET  /listings/<id>/requests/             key: `requested` and later, never `pending_email`
    POST /listings/<id>/requests/<rid>/       key: {status: confirmed, start} | {status: declined}; mails the owner
    POST /requests/confirm/            {token} the owner's mailed link → requested
    POST /requests/cancel/             {token} the owner's cancel link → cancelled
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import mail, rules
from .models import Listing, VisitRequest

log = logging.getLogger(__name__)

KEY_HEADER = 'HTTP_X_VETDIR_KEY'
ACCEPTED = {'ok': True}


class _Scope(ScopedRateThrottle):
    """A ScopedRateThrottle with its scope fixed at construction (`archive.views.FixedScopeThrottle`'s
    reason: one view, a scope per method)."""

    def __init__(self, scope):
        self.scope = scope
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)

    def allow_request(self, request, view):
        if self.rate is None:
            return True
        self.key = self.get_cache_key(request, view)
        if self.key is None:
            return True
        self.history = self.cache.get(self.key, [])
        self.now = self.timer()
        while self.history and self.history[-1] <= self.now - self.duration:
            self.history.pop()
        if len(self.history) >= self.num_requests:
            return self.throttle_failure()
        return self.throttle_success()


class _View(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    #: method → throttle scope; a method not named is not throttled here.
    scopes = {}

    def get_throttles(self):
        # A preflight is not a call and must not spend the allowance.
        scope = self.scopes.get(self.request.method)
        return [_Scope(scope)] if scope else []

    def source(self, request):
        return settings.FUWLOL_VETDIR_ORIGINS.get(request.META.get('HTTP_ORIGIN', ''))

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        origin = request.META.get('HTTP_ORIGIN', '')
        if origin in settings.FUWLOL_VETDIR_ORIGINS:
            response['Access-Control-Allow-Origin'] = origin
            if request.method == 'OPTIONS':
                response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, OPTIONS'
                response['Access-Control-Allow-Headers'] = 'Content-Type, Accept, X-Vetdir-Key'
                response['Access-Control-Max-Age'] = '86400'
        patch_vary_headers(response, ('Origin',))
        return response

    def listing_or_none(self, public_id):
        if not isinstance(public_id, str) or not rules.ID_RE.fullmatch(public_id):
            return None
        return Listing.objects.filter(public_id=public_id).first()

    def keyed(self, request, public_id):
        """The listing whose key the caller holds, refreshed; None for unknown and wrong alike."""
        row = self.listing_or_none(public_id)
        if row is None or not rules.key_matches(row, request.META.get(KEY_HEADER, '')):
            return None
        Listing.objects.filter(pk=row.pk).update(seen_at=timezone.now())
        row.refresh_from_db()
        return row


def _forbidden():
    return Response({'ok': False, 'origin': ['unknown']}, status=status.HTTP_403_FORBIDDEN)


def _not_found(field='listing'):
    return Response({'ok': False, field: ['unknown']}, status=status.HTTP_404_NOT_FOUND)


def _body(request):
    return request.data if isinstance(request.data, dict) else {}


def _token(request):
    t = _body(request).get('token')
    return t if isinstance(t, str) and 0 < len(t) <= rules.TOKEN_MAX else None


def public_row(row):
    # `example` (Amendment 1): the page says "an example, not a real clinic" in words.
    return {'id': row.public_id, 'card': row.card, 'example': row.example}


def clinic_row(row, now=None):
    now = now or timezone.now()
    return {
        'id': row.public_id,
        'status': row.status,
        'public': rules.is_public(row, now),
        'example': row.example,
        'card': row.card,
        'confirmed_on': row.confirmed_at.date().isoformat() if row.confirmed_at else None,
        # The day the page stops being public unless the app calls again with the key.
        'idle_until': (row.seen_at + timedelta(days=rules.LISTING_IDLE_DAYS)).date().isoformat(),
    }


def request_row(req):
    return {
        'id': req.public_id,
        'status': req.status,
        'owner_name': req.owner_name,
        'phone': req.phone,
        'email': req.email,
        'species': req.species,
        'animal_name': req.animal_name,
        'day': req.day.isoformat(),
        'part_of_day': req.part_of_day,
        'reason': req.reason,
        'locale': req.locale,
        'sent_on': timezone.localtime(req.created_at, rules.CLINIC_TZ).date().isoformat(),
        'start': req.start.isoformat() if req.start else None,
        'example': req.example,
    }


class ListingsView(_View):
    scopes = {'POST': 'vetdir_listing'}

    def post(self, request):
        source = self.source(request)
        if not source:
            return _forbidden()
        data = _body(request)
        if data.get('website'):
            # The honeypot: an answer shaped like a real one, nothing stored, nothing mailed.
            return Response({'ok': True, 'id': rules.new_public_id(), 'key': rules.new_key(),
                             'status': 'pending', 'mail': 'sent'}, status=status.HTTP_201_CREATED)
        problems = {}
        if data.get('consent_version') != rules.CONSENT_VERSION:
            problems['consent_version'] = ['Nieaktualna wersja zgody: odśwież stronę.']
        p = rules.email_problem(data.get('email'))
        if p:
            problems['email'] = [p]
        card, card_problems = rules.clean_card(data.get('card'))
        if card_problems:
            problems.update(card_problems)
        if problems:
            return Response(problems, status=status.HTTP_400_BAD_REQUEST)
        rules.sweep()
        now = timezone.now()
        key = rules.new_key()
        row = Listing.objects.create(
            public_id=rules.new_public_id(), key_hash=rules.hash_key(key),
            email=data['email'].strip().lower(), locale=rules.clean_locale(data.get('locale')),
            source=source, consent_version=rules.CONSENT_VERSION, card=card,
            created_at=now, seen_at=now, mailed_at=now)
        sent = 'sent'
        try:
            mail.send_listing_confirmation(row)
        except Exception:  # noqa: BLE001 — SMTP fails many ways; the clinic needs its key either way
            log.exception('vetdir: the confirmation mail for listing %s was not sent', row.pk)
            Listing.objects.filter(pk=row.pk).update(mailed_at=None)
            sent = 'unavailable'
        # The key exists in plain text exactly here, then only in the clinic's hands.
        return Response({'ok': True, 'id': row.public_id, 'key': key, 'status': row.status, 'mail': sent},
                        status=status.HTTP_201_CREATED)


class ListingConfirmView(_View):
    scopes = {'POST': 'vetdir_token'}

    def post(self, request):
        token = _token(request)
        if token is None:
            return Response({'ok': False, 'token': ['malformed']}, status=status.HTTP_400_BAD_REQUEST)
        rules.sweep()
        row, why = Listing.from_confirm_token(token)
        if row is None:
            code = status.HTTP_410_GONE if why == 'expired' else status.HTTP_404_NOT_FOUND
            return Response({'ok': False, 'token': [why]}, status=code)
        if row.status == 'unlisted':
            # Unlisted after the mail went: the older link must not undo that.
            return Response({'ok': False, 'token': ['unknown']}, status=status.HTTP_404_NOT_FOUND)
        now = timezone.now()
        Listing.objects.filter(pk=row.pk, status='pending').update(
            status='listed', confirmed_at=now, seen_at=now)
        # A second press is a success, not an error.
        return Response({'ok': True, 'id': row.public_id})


class ListingView(_View):
    scopes = {'GET': 'vetdir_read', 'PUT': 'vetdir_listing'}

    def get(self, request, public_id):
        if request.META.get(KEY_HEADER):
            row = self.keyed(request, public_id)
            return Response(clinic_row(row)) if row else _not_found()
        row = self.listing_or_none(public_id)
        # Pending, unlisted, idle and unknown answer the same 404 (root rule 5).
        if row is None or not rules.is_public(row):
            return _not_found()
        return Response(public_row(row))

    def put(self, request, public_id):
        if not self.source(request):
            return _forbidden()
        row = self.keyed(request, public_id)
        if row is None:
            return _not_found()
        if row.status == 'unlisted':
            return Response({'ok': False, 'status': ['unlisted']}, status=status.HTTP_409_CONFLICT)
        card, problems = rules.clean_card(_body(request).get('card'))
        if problems:
            return Response(problems, status=status.HTTP_400_BAD_REQUEST)
        rules.sweep()
        row.card = card
        row.save(update_fields=['card'])
        sent = None
        now = timezone.now()
        if row.status == 'pending' and (row.mailed_at is None or
                                        row.mailed_at < now - timedelta(minutes=rules.MAIL_COOLDOWN_MINUTES)):
            # Still unconfirmed: the clinic pressing "send again" gets the link again.
            try:
                mail.send_listing_confirmation(row)
                Listing.objects.filter(pk=row.pk).update(mailed_at=now)
                sent = 'sent'
            except Exception:  # noqa: BLE001
                log.exception('vetdir: the confirmation mail for listing %s was not sent', row.pk)
                sent = 'unavailable'
        elif row.status == 'pending':
            sent = 'cooldown'
        out = clinic_row(row)
        out['mail'] = sent
        return Response(out)


class UnlistView(_View):
    scopes = {'POST': 'vetdir_listing'}

    def post(self, request, public_id):
        if not self.source(request):
            return _forbidden()
        row = self.keyed(request, public_id)
        if row is None:
            return _not_found()
        rules.sweep()
        Listing.objects.filter(pk=row.pk).exclude(status='unlisted').update(
            status='unlisted', unlisted_at=timezone.now())
        row.refresh_from_db()
        return Response(clinic_row(row))


class RequestsView(_View):
    scopes = {'POST': 'vetdir_request', 'GET': 'vetdir_clinic'}

    def post(self, request, public_id):
        if not self.source(request):
            return _forbidden()
        row = self.listing_or_none(public_id)
        if row is None or not rules.accepts_requests(row):
            # The public page says whether a clinic takes requests; this is no oracle.
            return _not_found()
        data = _body(request)
        if data.get('website'):
            return Response(ACCEPTED, status=status.HTTP_202_ACCEPTED)
        fields, problems = rules.clean_request(data, row)
        if problems:
            return Response(problems, status=status.HTTP_400_BAD_REQUEST)
        if row.example:
            # Amendment 1: an example clinic takes the request and goes nowhere with it — nothing
            # kept, nobody mailed; the page says so beside the form.
            return Response(ACCEPTED, status=status.HTTP_202_ACCEPTED)
        rules.sweep()
        now = timezone.now()
        with transaction.atomic():
            recent = VisitRequest.objects.select_for_update().filter(
                listing=row, email=fields['email'], blanked_at__isnull=True,
                created_at__gt=now - timedelta(minutes=rules.MAIL_COOLDOWN_MINUTES)).exists()
            if recent:
                # Somebody pressing twice, or filling a stranger's inbox: one mail is enough.
                return Response(ACCEPTED, status=status.HTTP_202_ACCEPTED)
            req = VisitRequest.objects.create(public_id=rules.new_public_id(), listing=row,
                                              created_at=now, **fields)
        try:
            mail.send_request_confirmation(req)
        except Exception:  # noqa: BLE001
            log.exception('vetdir: the confirmation mail for request %s was not sent', req.pk)
            # Nobody can ever press a link that was never sent: keep the row, empty.
            VisitRequest.objects.filter(pk=req.pk).update(
                blanked_at=now, **{f: '' for f in rules.PERSONAL_REQUEST_FIELDS})
            return Response({'ok': False, 'mail': ['unavailable']},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        # The same answer whether a row was created or not (newsletter's rule).
        return Response(ACCEPTED, status=status.HTTP_202_ACCEPTED)

    def get(self, request, public_id):
        row = self.keyed(request, public_id)
        if row is None:
            return _not_found()
        rules.sweep()
        # Never a request the owner did not confirm — not even one they cancelled before confirming.
        reqs = (VisitRequest.objects.filter(listing=row, status__in=rules.CLINIC_VISIBLE_STATUSES,
                                            email_confirmed_at__isnull=False, blanked_at__isnull=True)
                .order_by('created_at')[:500])
        return Response({'requests': [request_row(r) for r in reqs]})


class RequestDecisionView(_View):
    scopes = {'POST': 'vetdir_clinic'}

    def post(self, request, public_id, request_id):
        if not self.source(request):
            return _forbidden()
        row = self.keyed(request, public_id)
        if row is None:
            return _not_found()
        req = (VisitRequest.objects.filter(listing=row, public_id=request_id, blanked_at__isnull=True)
               .first() if isinstance(request_id, str) and rules.ID_RE.fullmatch(request_id) else None)
        if req is None or req.email_confirmed_at is None:
            return _not_found('request')
        data = _body(request)
        to = data.get('status')
        start = None
        if to == 'confirmed':
            start = rules.parse_start(data.get('start'))
            if start is None:
                return Response({'ok': False, 'start': ['Początek wizyty: data i godzina ze strefą czasową, '
                                                        f'najwyżej {rules.CONFIRM_START_MAX_DAYS} dni naprzód.']},
                                status=status.HTTP_400_BAD_REQUEST)
        rules.sweep()
        with transaction.atomic():
            req = VisitRequest.objects.select_for_update().get(pk=req.pk)
            if req.status == to and to in ('confirmed', 'declined'):
                # A retried send after a lost answer: the same outcome, no second mail.
                return Response({'ok': True, 'request': request_row(req), 'mail': None})
            if rules.move(req, to, 'clinic', start=start) is None:
                return Response({'ok': False, 'status': [req.status]}, status=status.HTTP_400_BAD_REQUEST)
        if req.example or row.example:
            # Amendment 1: a seeded request has a fictional address; nobody is mailed.
            return Response({'ok': True, 'request': request_row(req), 'mail': None})
        sent = 'sent'
        try:
            (mail.send_confirmed if to == 'confirmed' else mail.send_declined)(req)
        except Exception:  # noqa: BLE001 — the decision stands; the app says the owner was not mailed
            log.exception('vetdir: the %s mail for request %s was not sent', to, req.pk)
            sent = 'unavailable'
        return Response({'ok': True, 'request': request_row(req), 'mail': sent})


class RequestConfirmView(_View):
    scopes = {'POST': 'vetdir_token'}

    def post(self, request):
        token = _token(request)
        if token is None:
            return Response({'ok': False, 'token': ['malformed']}, status=status.HTTP_400_BAD_REQUEST)
        rules.sweep()
        req, why = VisitRequest.from_confirm_token(token)
        if req is None:
            code = status.HTTP_410_GONE if why == 'expired' else status.HTTP_404_NOT_FOUND
            return Response({'ok': False, 'token': [why]}, status=code)
        if req.blanked_at is not None or req.status in rules.TERMINAL_STATUSES:
            return Response({'ok': False, 'token': ['unknown']}, status=status.HTTP_404_NOT_FOUND)
        if req.status == 'pending_email':
            if not rules.accepts_requests(req.listing):
                return Response({'ok': False, 'listing': ['unavailable']}, status=status.HTTP_404_NOT_FOUND)
            rules.move(req, 'requested', 'owner')
        # A second press is a success.
        return Response({'ok': True, 'status': req.status})


class RequestCancelView(_View):
    scopes = {'POST': 'vetdir_token'}

    def post(self, request):
        token = _token(request)
        if token is None:
            return Response({'ok': False, 'token': ['malformed']}, status=status.HTTP_400_BAD_REQUEST)
        rules.sweep()
        req = VisitRequest.from_cancel_token(token)
        if req is None:
            return Response({'ok': False, 'token': ['unknown']}, status=status.HTTP_404_NOT_FOUND)
        if req.status == 'cancelled':
            return Response({'ok': True, 'status': 'cancelled'})
        if rules.move(req, 'cancelled', 'owner') is None:
            # Declined by the clinic: nothing leaves a terminal state.
            return Response({'ok': False, 'status': [req.status]}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'ok': True, 'status': 'cancelled'})
