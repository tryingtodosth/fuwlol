"""    manage.py kolo_protocol <poll id>   → the Markdown protocol of a closed vote (§ 10a ust. 8)."""
from django.core.management.base import BaseCommand, CommandError

from kolo_ai import rules
from kolo_ai.models import Poll
from kolo_ai.protocol import protocol_markdown


class Command(BaseCommand):
    help = 'Protokół zakończonego głosowania zdalnego Koła AI.'

    def add_arguments(self, p):
        p.add_argument('poll_id', type=int)

    def handle(self, poll_id, **_):
        p = Poll.objects.filter(pk=poll_id).first()
        if p is None or rules.phase(p) != 'closed':
            raise CommandError('Nie ma takiego zakończonego głosowania.')
        self.stdout.write(protocol_markdown(p))
