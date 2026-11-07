"""Withdraw a person's sheet at their request — the controller's half of `rules.withdraw`.

    manage.py survey_withdraw --key <the key they pasted> [--dry-run]
    manage.py survey_withdraw --id 12

For a key that arrived by mail instead of through `POST /api/survey/withdraw/`, and for the row
id a person may have noted from the "sheet #12 arrived" message (which identifies nobody on its
own — only together with the mail that quotes it). The `--email` form went with the e-mail opt-in
in SURVEY-R3 (2026-11-07, `rules.py`). Not a cron job; a person asks, somebody runs it.
"""
from django.core.management.base import BaseCommand

from survey import rules
from survey.models import SurveyResponse


class Command(BaseCommand):
    help = 'Blank the answers of the sheet a person asks to withdraw, by key or id.'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--key')
        group.add_argument('--id', type=int)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        if options['key']:
            row = rules.find_by_key(options['key'])
            qs = SurveyResponse.objects.filter(pk=row.pk) if row else SurveyResponse.objects.none()
        else:
            qs = SurveyResponse.objects.filter(pk=options['id'])
        rows = list(qs.filter(status='received').order_by('id'))
        if not rows:
            self.stdout.write('Nie znaleziono przyjętej ankiety do wycofania.')
            return
        ids = ', '.join(f'#{row.id}' for row in rows)
        if options['dry_run']:
            self.stdout.write(f'Do wycofania: {len(rows)} (ankiety {ids}).')
            return
        for row in rows:
            rules.withdraw(row)
        self.stdout.write(f'Wycofano {len(rows)} (ankiety {ids}): odpowiedzi wyczyszczone, '
                          f'wiersze zostają jako „wycofane”.')
