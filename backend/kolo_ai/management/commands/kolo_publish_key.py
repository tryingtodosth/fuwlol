"""    manage.py kolo_publish_key create claude     → prints the key ONCE
    manage.py kolo_publish_key revoke claude
    manage.py kolo_publish_key list

A key posts and withdraws status entries on ai.fuw.lol and does nothing else."""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from kolo_ai.models import PublishKey, hash_secret, new_secret


class Command(BaseCommand):
    help = 'Klucze do publikowania statusu Koła AI.'

    def add_arguments(self, p):
        p.add_argument('action', choices=['create', 'revoke', 'list'])
        p.add_argument('name', nargs='?')

    def handle(self, action, name, **_):
        if action == 'list':
            for k in PublishKey.objects.all():
                self.stdout.write(f'{k.name}\t{k.created_at:%Y-%m-%d}\t{"odwołany" if k.revoked_at else "aktywny"}')
            return
        if not name:
            raise CommandError('Podaj nazwę klucza.')
        if action == 'create':
            raw = new_secret()
            PublishKey.objects.create(name=name, key_hash=hash_secret(raw))
            self.stdout.write(raw)
        else:
            n = PublishKey.objects.filter(name=name, revoked_at__isnull=True).update(revoked_at=timezone.now())
            self.stdout.write(f'Odwołano: {n}')
