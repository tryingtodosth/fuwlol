"""Remove R2 objects that were uploaded and never attached to a post.

A presigned PUT succeeds on its own; the post that was supposed to reference it may never
be submitted — the browser was closed, the form failed validation, the person changed
their mind. Those objects are unreferenced and unguessable, but they are still bytes
somebody uploaded to our bucket, and nothing else will ever delete them.

    0 5 * * *  docker compose exec -T api python manage.py sweep_uploads
"""
from django.core.management.base import BaseCommand

from archive.uploads import sweep_orphan_uploads


class Command(BaseCommand):
    help = 'Delete unclaimed R2 upload objects older than --hours (default 24).'

    def add_arguments(self, parser):
        parser.add_argument('--hours', type=int, default=24)

    def handle(self, *args, **options):
        n = sweep_orphan_uploads(older_than_hours=options['hours'])
        self.stdout.write(f'Usunięto {n} nieprzypisanych plików z R2.')
