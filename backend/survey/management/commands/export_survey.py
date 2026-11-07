"""Export one survey's sheets to stdout for the analysis — JSON Lines or CSV.

    docker compose -f docker-compose.prod.yml --env-file .env exec -T api \\
        python manage.py export_survey psychodeliki-retro-2026 --format csv --since 2026-11-01 > ankieta.csv

Not a cron job: the study team runs it by hand when the collection is over (or in between, to
look). The output carries exactly what the row holds — `id`, `version`, `consent_version`,
`locale`, `duration_s`, `received_on` and the answers — and nothing about anybody, because the
row holds nothing of the kind (`models.py`; the key hash is not exported). Withdrawn sheets
are left out unless `--include-withdrawn` asks for their empty rows. The CSV flattens the answers
into one column per question id: the union of every key across the exported rows, sorted, after
the six fixed columns; a list answer is joined with `|`, a boolean is `true` / `false`, a null is
an empty cell. A text cell that begins with `=`, `+`, `-`, `@`, a tab or a carriage return is
written with a leading apostrophe (SURVEY-R3, 2026-11-07): a spreadsheet that evaluates formulas
would otherwise run a respondent's typed answer as one. Numbers are never prefixed, so a negative
integer stays a number; the JSON Lines form has no such problem.
"""
import csv
import datetime
import json

from django.core.management.base import BaseCommand, CommandError

from survey import rules
from survey.models import SurveyResponse

FIXED_COLUMNS = ['id', 'version', 'consent_version', 'locale', 'duration_s', 'received_on']
# What a spreadsheet reads as the start of a formula (OWASP "CSV injection").
FORMULA_START = ('=', '+', '-', '@', '\t', '\r')


def cell(value):
    if value is None:
        return ''
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    if isinstance(value, list):
        text = '|'.join(value)
    elif isinstance(value, str):
        text = value
    else:
        return str(value)  # an integer is never a formula
    return "'" + text if text.startswith(FORMULA_START) else text


class Command(BaseCommand):
    help = "Write one survey's responses to stdout as JSON Lines (default) or CSV."

    def add_arguments(self, parser):
        parser.add_argument('slug', help='a key of survey.rules.SURVEYS')
        parser.add_argument('--format', choices=['jsonl', 'csv'], default='jsonl')
        parser.add_argument('--since', default=None, metavar='YYYY-MM-DD',
                            help='only sheets received on or after this date')
        parser.add_argument('--include-withdrawn', action='store_true',
                            help='also the withdrawn sheets (their answers are empty)')

    def handle(self, *args, **options):
        slug = options['slug']
        if slug not in rules.SURVEYS:
            known = ', '.join(sorted(rules.SURVEYS))
            raise CommandError(f'Nieznana ankieta: {slug!r}. Znane: {known}.')
        qs = SurveyResponse.objects.filter(survey=slug).order_by('id')
        if not options['include_withdrawn']:
            qs = qs.filter(status='received')
        if options['since']:
            try:
                since = datetime.date.fromisoformat(options['since'])
            except ValueError:
                raise CommandError('--since musi mieć postać YYYY-MM-DD.')
            qs = qs.filter(received_on__gte=since)
        if options['format'] == 'csv':
            self.write_csv(qs)
        else:
            self.write_jsonl(qs)

    @staticmethod
    def fixed(row):
        return {'id': row.id, 'version': row.version, 'consent_version': row.consent_version,
                'locale': row.locale, 'duration_s': row.duration_s,
                'received_on': row.received_on.isoformat()}

    def write_jsonl(self, qs):
        for row in qs.iterator():
            self.stdout.write(json.dumps({**self.fixed(row), 'answers': row.answers},
                                         ensure_ascii=False))

    def write_csv(self, qs):
        rows = list(qs)
        keys = sorted({key for row in rows for key in row.answers})
        writer = csv.writer(self.stdout, lineterminator='\n')
        writer.writerow(FIXED_COLUMNS + keys)
        for row in rows:
            fixed = self.fixed(row)
            writer.writerow([cell(fixed[c]) for c in FIXED_COLUMNS]
                            + [cell(row.answers.get(key)) for key in keys])
