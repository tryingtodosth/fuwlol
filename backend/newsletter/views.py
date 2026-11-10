"""`POST /api/newsletter/` asks for an address to be signed up and mails it a link;
`POST /api/newsletter/confirm/` is that link's press on medapp.net; `POST /api/newsletter/unsubscribe/`
takes the address off. The tokens are signed (models.py).

No GET anywhere: the list is read in the Django admin only. Both views answer CORS themselves for
the origins in settings.FUWLOL_NEWSLETTER_ORIGINS (MedApp's static copy on medapp.net calls them
with `fetch` from its own page), exactly as feedback/views.py does for notes; the project-wide
CORS list is untouched. Token authentication only, for feedback's reason: a fuw.lol session
cookie must never turn a sign-up into a CSRF 403.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .mail import send_already, send_confirmation
from .models import MAIL_COOLDOWN_MINUTES, PENDING_DAYS, Subscriber
from .serializers import SubscribeSerializer, TokenSerializer

log = logging.getLogger(__name__)


class _CrossOrigin(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [AllowAny]
    throttle_scope = 'newsletter'
    throttle_classes = [ScopedRateThrottle]

    def get_throttles(self):
        # A preflight is not a sign-up and must not spend the allowance.
        return [] if self.request.method == 'OPTIONS' else super().get_throttles()

    def _source(self, request):
        return settings.FUWLOL_NEWSLETTER_ORIGINS.get(request.META.get('HTTP_ORIGIN', ''))

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        origin = request.META.get('HTTP_ORIGIN', '')
        if origin in settings.FUWLOL_NEWSLETTER_ORIGINS:
            response['Access-Control-Allow-Origin'] = origin
            if request.method == 'OPTIONS':
                response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
                response['Access-Control-Allow-Headers'] = 'Content-Type, Accept'
                response['Access-Control-Max-Age'] = '86400'
        patch_vary_headers(response, ('Origin',))
        return response


ACCEPTED = {'ok': True}


class SubscribeView(_CrossOrigin):
    def post(self, request):
        source = self._source(request)
        if not source:
            # The links in the mail point at the copy the sign-up came from; with no known copy
            # there is nowhere to send the person, and no reason to mail anybody.
            return Response({'ok': False, 'origin': ['unknown']}, status=status.HTTP_403_FORBIDDEN)
        s = SubscribeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        if s.validated_data.get('website'):
            # The honeypot: the same answer as a real sign-up, nothing stored, nothing mailed.
            return Response(ACCEPTED, status=status.HTTP_202_ACCEPTED)
        now = timezone.now()
        Subscriber.objects.filter(status='pending',
                                  subscribed_at__lt=now - timedelta(days=PENDING_DAYS)).delete()
        with transaction.atomic():
            row = Subscriber.objects.select_for_update().filter(email=s.validated_data['email']).first()
            if row and row.mailed_at and row.mailed_at > now - timedelta(minutes=MAIL_COOLDOWN_MINUTES):
                # Somebody pressing twice, or somebody filling a stranger's inbox: one mail is enough.
                return Response(ACCEPTED, status=status.HTTP_202_ACCEPTED)
            already = bool(row and row.status == 'active')
            if not already:
                row = row or Subscriber(email=s.validated_data['email'])
                row.locale = s.validated_data.get('locale', '')
                row.source = source
                row.consent_version = s.validated_data['consent_version']
                row.status = 'pending'
                row.subscribed_at = now
                row.confirmed_at = None
                row.unsubscribed_at = None
            row.mailed_at = now
            row.save()
        try:
            (send_already if already else send_confirmation)(row)
        except Exception:  # noqa: BLE001 — SMTP has many ways to fail; the person needs one answer
            log.exception('newsletter: the mail to subscriber %s was not sent', row.pk)
            Subscriber.objects.filter(pk=row.pk).update(mailed_at=None)
            return Response({'ok': False, 'mail': ['unavailable']},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        # The same answer for a new address and a known one (models.py): nothing to learn here.
        return Response(ACCEPTED, status=status.HTTP_202_ACCEPTED)


class ConfirmView(_CrossOrigin):
    def post(self, request):
        s = TokenSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        row, why = Subscriber.from_confirm_token(s.validated_data['token'])
        if row is None:
            code = status.HTTP_410_GONE if why == 'expired' else status.HTTP_404_NOT_FOUND
            return Response({'ok': False, 'token': [why]}, status=code)
        if row.status == 'unsubscribed':
            # Unsubscribed after the mail went: the older link must not undo that.
            return Response({'ok': False, 'token': ['unknown']}, status=status.HTTP_404_NOT_FOUND)
        if row.status == 'pending':
            Subscriber.objects.filter(pk=row.pk, status='pending').update(
                status='active', confirmed_at=timezone.now())
        # A second press on the same link is a success, not an error.
        return Response({'ok': True})


class UnsubscribeView(_CrossOrigin):
    def post(self, request):
        s = TokenSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        row = Subscriber.from_unsubscribe_token(s.validated_data['token'])
        if row is None:
            return Response({'ok': False, 'token': ['unknown']}, status=status.HTTP_404_NOT_FOUND)
        Subscriber.objects.filter(pk=row.pk).exclude(status='unsubscribed').update(
            status='unsubscribed', unsubscribed_at=timezone.now())
        # Already off the list is the outcome the person wants: 200 either way.
        return Response({'ok': True})
