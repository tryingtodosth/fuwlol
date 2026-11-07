"""What the two endpoints promise. `test.md` lists this suite.

Three themes. A finished questionnaire must be hard to lose — only the submission itself
(`survey`, `version`, `consent_version`, `answers`, the honeypot, the one opt-in the person
ticked) can be refused, and the bookkeeping fields never refuse anything. A stored sheet must carry
NOTHING about the person who sent it unless they chose to take a key — no address, no account,
no second — and even then only a hash (`models.py` says why). And the way back works: the key
withdraws the sheet. (The e-mail opt-in and its `contact_hash` went in SURVEY-R3, 2026-11-07.)
"""
import csv
import datetime
import hashlib
import json
from io import StringIO

from django.conf import settings
from django.contrib.admin.sites import site as admin_site
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import models
from django.test import Client, RequestFactory, TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token

from . import rules
from .models import SurveyResponse
from .views import SurveyView, SurveyWithdrawView

URL = '/api/survey/'
WITHDRAW = '/api/survey/withdraw/'
SLUG = 'psychodeliki-retro-2026'


def good_body(**over):
    body = {
        'survey': SLUG,
        'version': rules.SURVEYS[SLUG]['version'],
        'consent_version': rules.CONSENT_VERSION,
        'locale': 'pl',
        'duration_s': 612,
        'answers': {
            'age_band': '25–29',
            'substances': ['lsd', 'psilocybin'],
            'times_total': 4,
            'with_sitter': True,
            'notes': 'Raz w górach, raz w domu.\nDrugi raz lepiej.',
            'regret': None,
        },
        'website': '',
    }
    body.update(over)
    return body


class SurveyWriteTests(TestCase):
    def setUp(self):
        # The throttle counters live in a FILE cache shared with the dev server and the browser
        # scripts (root CLAUDE.md); a suite that does not clear it starts at whatever the last
        # run left behind and fails at 429 for no reason visible in the code.
        cache.clear()

    def post(self, body=None, **over):
        body = good_body(**over) if body is None else body
        return self.client.post(URL, body, content_type='application/json')

    def test_a_valid_sheet_is_stored_with_its_fields(self):
        r = self.post()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json(), {'ok': True, 'id': r.json()['id'], 'key': None})
        row = SurveyResponse.objects.get(pk=r.json()['id'])
        self.assertEqual(row.survey, SLUG)
        self.assertEqual(row.version, rules.SURVEYS[SLUG]['version'])
        self.assertEqual(row.consent_version, rules.CONSENT_VERSION)
        self.assertEqual(row.status, 'received')
        self.assertIsNone(row.withdrawn_on)
        self.assertEqual(row.locale, 'pl')
        self.assertEqual(row.duration_s, 612)
        self.assertEqual(row.answers, good_body()['answers'])
        self.assertEqual(row.received_on, timezone.localdate())
        self.assertEqual(row.key_hash, '')

    def test_an_unknown_survey_is_refused_by_name(self):
        for bad in ('inna-ankieta', '', None):
            r = self.post(survey=bad)
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn('survey', r.json(), bad)
            self.assertNotIn('version', r.json(), bad)
        self.assertEqual(SurveyResponse.objects.count(), 0)

    def test_a_stale_version_is_refused_by_name(self):
        for bad in (0, 1, 3, 'abc', None):
            r = self.post(version=bad)
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn('version', r.json(), bad)
        self.assertEqual(SurveyResponse.objects.count(), 0)

    def test_a_stale_consent_text_is_refused_by_name(self):
        for bad in ('2026-01-01', '', None):
            r = self.post(consent_version=bad)
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn('consent_version', r.json(), bad)
        body = good_body()
        del body['consent_version']
        self.assertIn('consent_version', self.post(body=body).json())
        # Both stale at once: both named, so the client says "reload" once.
        r = self.post(version=99, consent_version='2026-01-01')
        self.assertEqual(set(r.json()), {'version', 'consent_version'})
        self.assertEqual(SurveyResponse.objects.count(), 0)

    def test_the_honeypot_refuses_and_stores_nothing(self):
        r = self.post(website='http://spam.example')
        self.assertEqual(r.status_code, 400)
        self.assertIn('website', r.json())
        self.assertEqual(SurveyResponse.objects.count(), 0)

    # --- answers: the shape is checked, the meaning is not ----------------------------

    def assert_answers_refused(self, answers, label=None):
        label = repr(answers)[:80] if label is None else label
        r = self.post(answers=answers)
        self.assertEqual(r.status_code, 400, label)
        self.assertEqual(list(r.json()), ['answers'], label)
        self.assertEqual(SurveyResponse.objects.count(), 0, label)

    def test_answers_that_are_not_an_object_are_refused(self):
        for bad in ('tak', 5, True, None, ['a', 'b']):
            self.assert_answers_refused(bad)
        body = good_body()
        del body['answers']
        r = self.post(body=body)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(list(r.json()), ['answers'])

    def test_empty_answers_are_refused(self):
        self.assert_answers_refused({})

    def test_too_many_keys_are_refused_and_the_limit_is_not(self):
        self.assertEqual(self.post(answers={f'q{i}': i for i in range(rules.MAX_KEYS)}).status_code, 201)
        SurveyResponse.objects.all().delete()
        self.assert_answers_refused({f'q{i}': i for i in range(rules.MAX_KEYS + 1)}, 'MAX_KEYS + 1')

    def test_a_bad_key_is_refused(self):
        for key in ('Q1', '1q', 'q-1', 'q 1', 'q' * 41, '', 'q1\n', 'ąę', '__proto__'):
            self.assert_answers_refused({key: 1}, repr(key))
        self.assertEqual(self.post(answers={'q' * 40: 1, 'a1_b2': 'x'}).status_code, 201)

    def test_a_string_over_the_limit_is_refused_and_one_at_it_is_not(self):
        self.assertEqual(self.post(answers={'notes': 'a' * rules.MAX_STRING}).status_code, 201)
        SurveyResponse.objects.all().delete()
        self.assert_answers_refused({'notes': 'a' * (rules.MAX_STRING + 1)}, 'MAX_STRING + 1')
        # The limit is measured after stripping, and the stripped text is what is stored.
        r = self.post(answers={'notes': '  ' + 'a' * rules.MAX_STRING + '\n'})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(SurveyResponse.objects.get().answers['notes'], 'a' * rules.MAX_STRING)

    def test_a_list_too_long_or_with_odd_items_is_refused(self):
        self.assertEqual(self.post(answers={'s': ['x'] * rules.MAX_LIST, 't': []}).status_code, 201)
        SurveyResponse.objects.all().delete()
        self.assert_answers_refused({'s': ['x'] * (rules.MAX_LIST + 1)}, 'MAX_LIST + 1')
        self.assert_answers_refused({'s': ['x' * (rules.MAX_LIST_ITEM + 1)]}, 'MAX_LIST_ITEM + 1')
        self.assert_answers_refused({'s': [1, 2]}, 'integers in a list')
        self.assert_answers_refused({'s': [None]}, 'null in a list')
        self.assert_answers_refused({'s': [['nested']]}, 'a nested list')

    def test_control_characters_are_refused_but_newline_and_tab_are_not(self):
        self.assertEqual(self.post(answers={'notes': 'linia 1\nlinia 2\tkolumna'}).status_code, 201)
        SurveyResponse.objects.all().delete()
        for bad in ('a\x00b', 'a\x1bb', 'a\rb', 'a\x7fb', '\x08'):
            self.assert_answers_refused({'notes': bad}, repr(bad))
            self.assert_answers_refused({'s': ['ok', bad]}, repr([bad]))

    def test_a_nested_object_or_a_float_is_refused(self):
        self.assert_answers_refused({'q': {'inner': 1}}, 'an object as a value')
        self.assert_answers_refused({'q': 3.5}, 'a float')

    def test_an_integer_out_of_range_is_refused_and_booleans_stay_booleans(self):
        self.assert_answers_refused({'q': rules.MAX_INT + 1}, 'MAX_INT + 1')
        self.assert_answers_refused({'q': -rules.MAX_INT - 1}, '-MAX_INT - 1')
        answers = {'a': rules.MAX_INT, 'b': -rules.MAX_INT, 'c': True, 'd': False, 'e': None, 'f': 0}
        self.assertEqual(self.post(answers=answers).status_code, 201)
        stored = SurveyResponse.objects.get().answers
        self.assertEqual(stored, answers)
        self.assertIs(stored['c'], True)
        self.assertIs(stored['f'], 0)

    def test_answers_over_the_byte_cap_are_refused(self):
        # 120 × 300 × 'ż' is 36 000 CHARACTERS — under the cap counted that way — and 72 000
        # BYTES of UTF-8, which is what is counted. Every per-field rule passes (120 ≤ MAX_KEYS).
        self.assert_answers_refused({f'q{i}': 'ż' * rules.MAX_STRING for i in range(120)}, 'bytes')

    def test_unknown_question_ids_are_the_clients_business(self):
        # Nothing semantic: this server does not know which questions exist.
        self.assertEqual(self.post(answers={'zzz_not_a_question': 'kept'}).status_code, 201)

    # --- the bookkeeping fields never lose a sheet -------------------------------------

    def test_an_odd_locale_is_dropped_not_refused(self):
        for bad in ('klingon', 'PL', 'p\nl', 'x' * 300, None, 7, ['pl'], {'a': 1}):
            SurveyResponse.objects.all().delete()
            r = self.post(locale=bad)
            self.assertEqual(r.status_code, 201, bad)
            self.assertEqual(SurveyResponse.objects.get().locale, '', bad)
        # Stripped first, like feedback/: padding around a real tag is not a reason to drop it.
        for sent, kept in (('en', 'en'), ('uk', 'uk'), ('pt-BR', 'pt-BR'), (' pl\n', 'pl')):
            SurveyResponse.objects.all().delete()
            self.assertEqual(self.post(locale=sent).status_code, 201, sent)
            self.assertEqual(SurveyResponse.objects.get().locale, kept, sent)

    def test_an_odd_duration_is_dropped_not_refused(self):
        for bad in (None, -1, rules.MAX_DURATION_S + 1, 'abc', '612', 12.5, True, [1]):
            SurveyResponse.objects.all().delete()
            r = self.post(duration_s=bad)
            self.assertEqual(r.status_code, 201, bad)
            self.assertIsNone(SurveyResponse.objects.get().duration_s, bad)
        for ok in (0, rules.MAX_DURATION_S):
            SurveyResponse.objects.all().delete()
            self.assertEqual(self.post(duration_s=ok).status_code, 201)
            self.assertEqual(SurveyResponse.objects.get().duration_s, ok)

    def test_a_sheet_without_the_optional_fields_still_arrives(self):
        body = good_body()
        del body['locale'], body['duration_s'], body['website']
        r = self.post(body=body)
        self.assertEqual(r.status_code, 201)
        row = SurveyResponse.objects.get()
        self.assertEqual(row.locale, '')
        self.assertIsNone(row.duration_s)
        self.assertEqual(row.key_hash, '')

    # --- the one opt-in way back ----------------------------------------------------------

    def test_a_contact_email_from_an_older_client_is_ignored_and_stored_nowhere(self):
        # SURVEY-R3: there is no e-mail opt-in any more. An older build that still sends the key
        # loses nothing (201) and the address lands nowhere — the row has no field for it.
        r = self.post(contact_email='Osoba@Example.COM')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(set(r.json()), {'ok', 'id', 'key'})
        row = SurveyResponse.objects.get()
        self.assertFalse(hasattr(row, 'contact_hash'))
        self.assertNotIn('example', json.dumps(row.answers).lower())
        self.assertFalse(hasattr(rules, 'hash_contact'))
        self.assertFalse(hasattr(rules, 'MAX_EMAIL'))

    def test_a_key_is_handed_back_once_and_kept_as_a_hash(self):
        r = self.post(wants_key=True)
        self.assertEqual(r.status_code, 201)
        key = r.json()['key']
        self.assertIsInstance(key, str)
        self.assertGreaterEqual(len(key), 40)
        row = SurveyResponse.objects.get()
        self.assertEqual(row.key_hash, hashlib.sha256(key.encode()).hexdigest())
        self.assertNotIn(key, row.key_hash)
        # Two sheets, two keys.
        self.assertNotEqual(self.post(wants_key=True).json()['key'], key)
        # Not asked for: none made.
        for no in (False, None, 'false', 0):
            SurveyResponse.objects.all().delete()
            r = self.post(wants_key=no)
            self.assertEqual(r.status_code, 201, no)
            self.assertIsNone(r.json()['key'], no)
            self.assertEqual(SurveyResponse.objects.get().key_hash, '', no)

    def test_a_garbled_wants_key_is_refused_by_name(self):
        r = self.post(wants_key='może')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(list(r.json()), ['wants_key'])

    def test_the_key_withdraws_the_sheet_and_only_that_sheet(self):
        key = self.post(wants_key=True).json()['key']
        other = SurveyResponse.objects.get(pk=self.post().json()['id'])
        r = self.client.post(WITHDRAW, {'key': key}, content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'ok': True, 'status': 'withdrawn'})
        row = SurveyResponse.objects.get(key_hash=rules.hash_key(key))
        self.assertEqual(row.status, 'withdrawn')
        self.assertEqual(row.answers, {})
        self.assertEqual(row.withdrawn_on, timezone.localdate())
        # The row stays, with its date and its survey, so the count of sheets received is right.
        self.assertEqual(row.received_on, timezone.localdate())
        self.assertEqual(row.survey, SLUG)
        other.refresh_from_db()
        self.assertEqual(other.status, 'received')
        self.assertEqual(other.answers, good_body()['answers'])
        # A second call finds the same sheet and changes nothing.
        r = self.client.post(WITHDRAW, {'key': f' {key}\n'}, content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(SurveyResponse.objects.filter(status='withdrawn').count(), 1)

    def test_an_unknown_key_is_404_and_a_missing_one_is_400_by_name(self):
        self.post(wants_key=True)
        for bad in ('nie-ten-klucz', 'x' * 500, hashlib.sha256(b'x').hexdigest()):
            r = self.client.post(WITHDRAW, {'key': bad}, content_type='application/json')
            self.assertEqual(r.status_code, 404, bad)
        for missing in ({}, {'key': ''}, {'key': None}, {'key': ['a']}):
            r = self.client.post(WITHDRAW, missing, content_type='application/json')
            self.assertEqual(r.status_code, 400, missing)
            self.assertEqual(list(r.json()), ['key'], missing)
        self.assertEqual(SurveyResponse.objects.filter(status='received').count(), 1)
        self.assertEqual(self.client.get(WITHDRAW).status_code, 405)

    def test_withdraw_has_its_own_scope_and_answers_429_eventually(self):
        self.assertEqual(SurveyWithdrawView.throttle_scope, 'survey_withdraw')
        self.assertEqual(settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['survey_withdraw'], '20/hour')
        for _ in range(20):
            self.client.post(WITHDRAW, {'key': 'zgaduję'}, content_type='application/json')
        r = self.client.post(WITHDRAW, {'key': 'zgaduję'}, content_type='application/json')
        self.assertEqual(r.status_code, 429)

    # --- nothing about the person --------------------------------------------------------

    def test_the_row_has_no_address_no_account_and_no_timestamp(self):
        names = {f.name for f in SurveyResponse._meta.get_fields()}
        for forbidden in ('ip_hash', 'ip', 'author', 'user', 'created_at', 'user_agent',
                          'contact_email', 'contact_hash', 'email', 'key'):
            self.assertNotIn(forbidden, names)
        self.assertEqual(names, {'id', 'survey', 'version', 'consent_version', 'status',
                                 'withdrawn_on', 'locale', 'duration_s', 'answers',
                                 'key_hash', 'received_on'})
        for name in ('received_on', 'withdrawn_on'):
            field = SurveyResponse._meta.get_field(name)
            self.assertIsInstance(field, models.DateField)
            self.assertNotIsInstance(field, models.DateTimeField)

    def test_the_received_date_is_a_date_and_nothing_finer(self):
        r = self.post()
        row = SurveyResponse.objects.get(pk=r.json()['id'])
        self.assertIsInstance(row.received_on, datetime.date)
        # datetime.datetime IS a datetime.date, so the first assertion alone would not catch it.
        self.assertNotIsInstance(row.received_on, datetime.datetime)

    def test_a_session_cookie_is_neither_a_csrf_403_nor_an_attribution(self):
        """The endpoint is same-origin with the archive (`fuw.lol/lsd`), so a visitor signed in
        to fuw.lol sends its session cookie with this POST whether they meant to or not. With
        SessionAuthentication in the list DRF would enforce CSRF and refuse the sheet with 403;
        `views.SurveyView` drops session auth for exactly that reason (feedback/tests.py has the
        twin). `enforce_csrf_checks` makes this client behave like a real browser — the default
        test client does not, so without it this test passes against the very code it is meant
        to catch."""
        user = User.objects.create_user('dziekan', password='x')
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        r = client.post(URL, good_body(), content_type='application/json')
        self.assertEqual(r.status_code, 201)
        # A real token changes nothing either: the row has no field it could land in.
        token = Token.objects.create(user=user)
        r = self.client.post(URL, good_body(), content_type='application/json',
                             HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(SurveyResponse.objects.count(), 2)

    # --- the shape of the endpoint -------------------------------------------------------

    def test_there_is_no_way_to_read_the_sheets_back(self):
        self.post()
        self.assertEqual(self.client.get(URL).status_code, 405)
        self.assertEqual(self.client.get(f'{URL}1/').status_code, 404)

    def test_the_throttle_scope_is_survey_and_configured(self):
        self.assertEqual(SurveyView.throttle_scope, 'survey')
        self.assertEqual(settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['survey'], '60/hour')

    def test_the_throttle_answers_429_eventually(self):
        # 60/hour (settings.py). Proving the scope is wired at all is the point; the exact rate
        # is a settings question, not a code one.
        for _ in range(60):
            self.assertEqual(self.post().status_code, 201)
        self.assertEqual(self.post().status_code, 429)


class AdminTests(TestCase):
    """Read-only for everybody, deletion for the head admin only, the JSON escaped, no hash shown."""

    def setUp(self):
        self.ma = admin_site._registry[SurveyResponse]
        self.staff = User.objects.create_user('mod', password='x', is_staff=True)
        self.head = User.objects.create_user('dziekan', password='x', is_staff=True, is_superuser=True)
        self.row = SurveyResponse.objects.create(
            survey=SLUG, version=1, consent_version=rules.CONSENT_VERSION, locale='pl', duration_s=5,
            answers={'notes': '<script>alert(1)</script>', 'age_band': '25–29'},
            key_hash=rules.hash_key('klucz'))

    def test_permissions(self):
        request = RequestFactory().get('/')
        request.user = self.staff
        self.assertFalse(self.ma.has_add_permission(request))
        self.assertFalse(self.ma.has_change_permission(request))
        self.assertFalse(self.ma.has_delete_permission(request))
        request.user = self.head
        self.assertFalse(self.ma.has_add_permission(request))
        self.assertFalse(self.ma.has_change_permission(request))
        self.assertTrue(self.ma.has_delete_permission(request))
        self.assertEqual(set(self.ma.readonly_fields), set(self.ma.fields))
        for hidden in ('key_hash', 'answers'):
            self.assertNotIn(hidden, self.ma.fields)
            self.assertNotIn(hidden, self.ma.list_display)
        self.assertNotIn('has_contact', self.ma.list_display)

    def test_the_answers_are_escaped_and_the_pages_open_without_a_hash(self):
        html = self.ma.pretty_answers(self.row)
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>', html)
        self.client.force_login(self.head)
        r = self.client.get('/admin/survey/surveyresponse/')
        self.assertEqual(r.status_code, 200)
        r = self.client.get(f'/admin/survey/surveyresponse/{self.row.id}/change/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'age_band')
        self.assertNotContains(r, self.row.key_hash)


class WithdrawCommandTests(TestCase):
    """`manage.py survey_withdraw`: the controller's half, by key or id (no `--email` since SURVEY-R3)."""

    def setUp(self):
        self.a = SurveyResponse.objects.create(survey=SLUG, version=1, consent_version=rules.CONSENT_VERSION,
                                               answers={'a': 1})
        self.b = SurveyResponse.objects.create(survey=SLUG, version=1, consent_version=rules.CONSENT_VERSION,
                                               answers={'a': 2}, key_hash=rules.hash_key('klucz-b'))
        self.c = SurveyResponse.objects.create(survey=SLUG, version=1, consent_version=rules.CONSENT_VERSION,
                                               answers={'a': 3})

    def run_command(self, *args):
        out = StringIO()
        call_command('survey_withdraw', *args, stdout=out)
        return out.getvalue()

    def statuses(self):
        return [SurveyResponse.objects.get(pk=row.pk).status for row in (self.a, self.b, self.c)]

    def test_by_key_and_by_id(self):
        self.assertIn('Do wycofania: 1', self.run_command('--key', 'klucz-b', '--dry-run'))
        self.assertEqual(self.statuses(), ['received'] * 3)
        self.assertIn('Wycofano 1', self.run_command('--key', 'klucz-b'))
        self.assertIn('Wycofano 1', self.run_command('--id', str(self.c.pk)))
        self.assertEqual(self.statuses(), ['received', 'withdrawn', 'withdrawn'])
        self.assertIn('Nie znaleziono', self.run_command('--key', 'nie-ten'))
        self.assertIn('Nie znaleziono', self.run_command('--id', '999999'))

    def test_there_is_no_email_form_any_more(self):
        with self.assertRaises((CommandError, SystemExit)):
            call_command('survey_withdraw', '--email', 'osoba@example.com', stdout=StringIO(), stderr=StringIO())
        self.assertEqual(self.statuses(), ['received'] * 3)


class ExportTests(TestCase):
    """`manage.py export_survey`: the six fixed columns, then every key seen, sorted."""

    def setUp(self):
        self.a = SurveyResponse.objects.create(survey=SLUG, version=1, consent_version=rules.CONSENT_VERSION,
                                               locale='pl', duration_s=10, answers={'b': ['x', 'y'], 'a': 1},
                                               key_hash=rules.hash_key('klucz-a'))
        self.b = SurveyResponse.objects.create(survey=SLUG, version=1, consent_version=rules.CONSENT_VERSION,
                                               locale='', duration_s=None,
                                               answers={'c': True, 'a': 'tekst, z przecinkiem', 'd': None})
        self.gone = SurveyResponse.objects.create(survey=SLUG, version=1, consent_version=rules.CONSENT_VERSION,
                                                  answers={'a': 'wycofane'})
        rules.withdraw(self.gone)

    def run_export(self, *args):
        out = StringIO()
        call_command('export_survey', SLUG, *args, stdout=out)
        return out.getvalue()

    def test_csv_flattens_keys_joins_lists_and_skips_withdrawn_sheets(self):
        text = self.run_export('--format', 'csv')
        rows = list(csv.reader(StringIO(text)))
        self.assertEqual(rows[0], ['id', 'version', 'consent_version', 'locale', 'duration_s',
                                   'received_on', 'a', 'b', 'c', 'd'])
        today = timezone.localdate().isoformat()
        self.assertEqual(rows[1], [str(self.a.id), '1', rules.CONSENT_VERSION, 'pl', '10', today, '1', 'x|y', '', ''])
        self.assertEqual(rows[2], [str(self.b.id), '1', rules.CONSENT_VERSION, '', '', today,
                                   'tekst, z przecinkiem', '', 'true', ''])
        self.assertEqual(len(rows), 3)
        self.assertNotIn(self.a.key_hash, text)
        with_gone = list(csv.reader(StringIO(self.run_export('--format', 'csv', '--include-withdrawn'))))
        self.assertEqual(len(with_gone), 4)
        self.assertEqual(with_gone[3][6:], ['', '', '', ''])

    def test_csv_text_that_looks_like_a_formula_is_prefixed_and_numbers_are_not(self):
        # SURVEY-R3: a respondent's typed answer must not run as a formula in a spreadsheet.
        SurveyResponse.objects.all().delete()
        SurveyResponse.objects.create(survey=SLUG, version=2, consent_version=rules.CONSENT_VERSION,
                                      answers={'e': '=1+1', 'p': '+x', 'm': '-y', 'a': '@z',
                                               't': '\tx', 'n': -5, 'l': ['=a', 'b'], 'ok': 'zwykły tekst'})
        rows = list(csv.reader(StringIO(self.run_export('--format', 'csv'))))
        self.assertEqual(rows[0][6:], ['a', 'e', 'l', 'm', 'n', 'ok', 'p', 't'])
        self.assertEqual(rows[1][6:], ["'@z", "'=1+1", "'=a|b", "'-y", '-5', 'zwykły tekst', "'+x", "'\tx"])
        self.assertNotIn('\n=1+1', self.run_export())  # the JSON Lines form is untouched

    def test_jsonl_and_since(self):
        lines = [json.loads(line) for line in self.run_export().splitlines()]
        self.assertEqual([line['id'] for line in lines], [self.a.id, self.b.id])
        self.assertEqual(set(lines[0]), {'id', 'version', 'consent_version', 'locale', 'duration_s',
                                         'received_on', 'answers'})
        self.assertEqual(lines[0]['answers'], {'b': ['x', 'y'], 'a': 1})
        self.assertEqual(self.run_export('--since', timezone.localdate().isoformat()).count('\n'), 2)
        tomorrow = (timezone.localdate() + datetime.timedelta(days=1)).isoformat()
        self.assertEqual(self.run_export('--since', tomorrow), '')

    def test_an_unknown_slug_or_a_bad_date_is_a_command_error(self):
        with self.assertRaises(CommandError):
            call_command('export_survey', 'nie-ma-takiej', stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command('export_survey', SLUG, '--since', '2026-13-45', stdout=StringIO())


class MirroredConstantsTests(TestCase):
    """The wire contract exists twice — here and in MedApp's `src/lib/survey/api.ts`, a SEPARATE
    REPOSITORY that cannot be imported. This pins the server's copy so that a change here is a
    visible, deliberate diff; the app's file carries the same values with a comment naming this one."""

    def test_pinned(self):
        self.assertEqual(rules.SURVEYS, {'psychodeliki-retro-2026': {
            'version': 2,
            'title': 'Psychodeliki – ankieta retrospektywna w ramach przygotowań do studenckiego badania obserwacyjnego'}})
        self.assertEqual(rules.CONSENT_VERSION, '2026-11-07')
        self.assertEqual(rules.CONSENT_STATEMENTS, (
            'Chcę podzielić się moim doświadczeniem w celach przygotowań do studenckiego badania obserwacyjnego.',
            'Projekt nie jest powiązany z żadną uczelnią.',
            'Administrator danych: Piotr Putyło, admin@fuw.lol.',
        ))
        self.assertEqual((rules.CONTROLLER, rules.CONTROLLER_EMAIL), ('Piotr Putyło', 'admin@fuw.lol'))
        self.assertEqual(
            (rules.MAX_KEYS, rules.MAX_STRING, rules.MAX_LIST, rules.MAX_LIST_ITEM, rules.MAX_INT,
             rules.MAX_ANSWERS_BYTES, rules.MAX_DURATION_S, rules.MAX_KEY),
            (200, 300, 50, 200, 1_000_000, 65536, 86400, 128))
        self.assertFalse(hasattr(rules, 'MAX_EMAIL'))
        self.assertEqual(rules.KEY_RE.pattern, r'^[a-z][a-z0-9_]{0,39}$')
