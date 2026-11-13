"""`manage.py vetdir_sweep` — the same sweep every write runs (`rules.sweep`): blank the personal
fields of requests past REQUEST_KEEP_DAYS (or unconfirmed past REQUEST_UNCONFIRMED_DAYS) and delete
listings never confirmed within LISTING_PENDING_DAYS. For a quiet week with no writes; a cron line is
optional, nothing depends on one."""
from django.core.management.base import BaseCommand

from vetdir import rules


class Command(BaseCommand):
    help = 'Blank expired visit requests and drop listings never confirmed (vetdir).'

    def handle(self, *args, **options):
        blanked, deleted = rules.sweep()
        self.stdout.write(f'Wyczyszczone prośby: {blanked}; usunięte niepotwierdzone wpisy: {deleted}.')
