"""Nightly cron (deploy/OVH.md). The join form promises that an address nobody confirmed is
gone within 30 days (frontend/src/routes/ai/+page.svelte, the consent text): such a row is
somebody's e-mail typed by anybody, with no agreement behind it. Expired links and sessions
go too — they are hashes, but nothing needs them."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from kolo_ai.models import LoginLink, Member, Session

KEEP_UNCONFIRMED = timedelta(days=30)


class Command(BaseCommand):
    help = 'Usuń niepotwierdzone zgłoszenia do Koła AI starsze niż 30 dni.'

    def handle(self, **_):
        now = timezone.now()
        stale = Member.objects.filter(status=Member.PENDING_EMAIL, email_confirmed_at__isnull=True,
                                      created_at__lt=now - KEEP_UNCONFIRMED, actions__isnull=True)
        n = stale.count()
        stale.delete()  # links and sessions cascade
        LoginLink.objects.filter(Q(expires_at__lt=now - timedelta(days=1)) | Q(used_at__isnull=False)).delete()
        Session.objects.filter(Q(expires_at__lt=now) | Q(revoked_at__isnull=False)).delete()
        self.stdout.write(f'Usunięto niepotwierdzonych zgłoszeń: {n}')
