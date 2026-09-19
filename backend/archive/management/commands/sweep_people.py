"""Delete people who were proposed and then never published.

Naming a person into existence (archive/people.resolve_people) means an ordinary account
can create a row in a public index of named human beings. `visible_people` already
keeps such a row invisible to everybody but its proposer until a post that names them is
published — so nothing leaks — but invisible is not gone, and a rejected submission or an
abandoned draft would otherwise leave the name sitting in the database forever.

Thirty days is the window because that is roughly how long a rejected post stays worth
editing and resubmitting; sweeping sooner would delete a person out from under an author
who is still arguing about their post. A person with a post of ANY status behind them —
pending, rejected, hidden, even in criminal quarantine — is never swept: the post is the
reason to keep the name, whatever state it is in.

Run it from cron next to `forget_submitter_ips` and `sweep_uploads`:

    manage.py sweep_people --dry-run     # say what would go
    manage.py sweep_people               # and then do it
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from archive.people import sweepable_people

DEFAULT_DAYS = 30


class Command(BaseCommand):
    help = 'Usuwa zaproponowane osoby bez żadnego wpisu, starsze niż N dni.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=DEFAULT_DAYS,
                            help=f'ile dni osoba bez wpisu ma przeżyć (domyślnie {DEFAULT_DAYS})')
        parser.add_argument('--dry-run', action='store_true', help='tylko wypisz, nic nie usuwaj')

    def handle(self, *args, **opts):
        before = timezone.now() - timedelta(days=opts['days'])
        gone = 0
        for person in list(sweepable_people(before)):
            who = person.created_by.username if person.created_by_id else '?'
            self.stdout.write(f'{"(próbnie) " if opts["dry_run"] else ""}usuwam {person.slug} '
                              f'— zaproponowana przez {who} {person.created_at:%Y-%m-%d}, bez wpisów')
            if not opts['dry_run']:
                person.delete()
            gone += 1
        if not gone:
            self.stdout.write('Nie ma czego sprzątać.')
        else:
            self.stdout.write(self.style.SUCCESS(
                f'{"Do usunięcia" if opts["dry_run"] else "Usunięto"}: {gone} osob(y).'))
