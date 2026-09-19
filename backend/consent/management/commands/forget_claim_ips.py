"""Blank the claim addresses that have outlived their purpose.

`PersonClaim.requester_ip` exists for the same reason as `Post.submitter_ip` and is
forgotten by the same clock (`SUBMITTER_IP_RETENTION_DAYS`): it is the "from where" half
of "who agreed to what, when", and a raw address kept past the point where it could still
answer a question is personal data with no remaining purpose — which is exactly what RODO
art. 5 ust. 1 lit. e says not to keep. So this is the forgetting half, and it is a cron
job rather than a good intention:

    0 4 * * *  docker compose exec -T api python manage.py forget_claim_ips

**Approved claims keep theirs.** They are not a log entry, they are the evidence that this
archive is allowed to publish somebody's face — and evidence of consent that cannot say
where the consent came from is worth noticeably less on the day somebody disputes it. That
asymmetry is the one difference from `forget_submitter_ips`, and it is deliberate: a
consent record is kept as long as it is relied upon (RODO art. 7 ust. 1: we must be able
to DEMONSTRATE consent), while an unconfirmed or rejected claim is just traffic.
"""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from consent.models import PersonClaim


class Command(BaseCommand):
    help = 'Blank PersonClaim.requester_ip / requester_user_agent outside the retention window.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=None)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        days = options['days'] or getattr(settings, 'SUBMITTER_IP_RETENTION_DAYS', 90)
        cutoff = timezone.now() - timedelta(days=days)
        qs = (PersonClaim.objects.filter(created_at__lt=cutoff)
              .exclude(status='approved')
              .exclude(requester_ip=None, requester_user_agent=''))
        n = qs.count()
        if options['dry_run']:
            self.stdout.write(f'{n} wniosków do wyczyszczenia (starsze niż {days} dni, poza zatwierdzonymi).')
            return
        qs.update(requester_ip=None, requester_user_agent='')
        self.stdout.write(f'Wyczyszczono adresy IP / user-agent w {n} wnioskach '
                          f'(starsze niż {days} dni; zatwierdzone zostają jako dowód zgody).')
