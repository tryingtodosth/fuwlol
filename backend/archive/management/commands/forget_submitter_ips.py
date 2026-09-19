"""Blank the uploader addresses that have outlived their purpose.

`Post.submitter_ip` exists for one reason — being the identifying half of an art. 18 DSA
report to Dyżurnet.pl — and a raw address kept after that stops being plausible is a
liability under RODO rather than an asset: it is personal data with no remaining purpose,
which is exactly what art. 5(1)(e) says not to keep.

So this is the forgetting half, and it is a cron job rather than a good intention:

    0 4 * * *  docker compose exec -T api python manage.py forget_submitter_ips

A post that has been escalated keeps its address for as long as the escalation is open,
because that is the case the field exists for; once an escalation is purged the address
lives on only inside the EvidenceAuditLog row, which is deliberately not touched here.
"""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from archive.models import Post


class Command(BaseCommand):
    help = 'Blank Post.submitter_ip / submitter_user_agent older than the retention window.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=None)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        days = options['days'] or getattr(settings, 'SUBMITTER_IP_RETENTION_DAYS', 90)
        cutoff = timezone.now() - timedelta(days=days)
        from escalation.models import ACTIVE_STATUSES, Escalation
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(Post)
        open_ids = set(Escalation.objects.filter(content_type=ct, status__in=ACTIVE_STATUSES)
                       .values_list('object_id', flat=True))
        qs = (Post.all_objects.filter(created_at__lt=cutoff)
              .exclude(submitter_ip=None, submitter_user_agent='')
              .exclude(pk__in=open_ids))
        n = qs.count()
        if options['dry_run']:
            self.stdout.write(f'{n} wpisów do wyczyszczenia (starsze niż {days} dni).')
            return
        qs.update(submitter_ip=None, submitter_user_agent='')
        self.stdout.write(f'Wyczyszczono adresy IP / user-agent w {n} wpisach (starsze niż {days} dni).')
