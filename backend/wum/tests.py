"""What `/api/wum/…` promises. `test.md` lists this suite.

Three themes: the public read of a publication never carries the account; every refusal is
keyed by the field the app can name; and the two populations (archive, WUM) share the user
table and nothing else.
"""
import json
import re

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase
from rest_framework.authtoken.models import Token

from accounts.views import RegisterSerializer as ArchiveRegisterSerializer

from . import rules
from .models import (MAX_PUBLICATION_BYTES, MAX_TEMPLATE_BYTES, PAYLOAD_VERSION,
                     TEMPLATE_DOCUMENT_VERSION, TEMPLATE_KEYS, TEMPLATE_REFUSED_KEYS, Publication,
                     Template, WumProfile)
from .serializers import USERNAME_RE

REGISTER = '/api/wum/auth/register/'
LOGIN = '/api/wum/auth/login/'
LOGOUT = '/api/wum/auth/logout/'
ME = '/api/wum/auth/me/'
TEMPLATES = '/api/wum/templates/'
PUBLICATIONS = '/api/wum/publications/'
PASSWORD = 'korytarz-pasteura-5'


def good_payload(**over):
    payload = {
        'version': PAYLOAD_VERSION, 'ageBand': '30–39', 'categories': ['symptom_map', 'medications'],
        'notesIncluded': False,
        'symptoms': [{'partId': 'knee_l', 'region': 'leg', 'side': 'left', 'layer': 'skin',
                      'kind': 'pain', 'severity': 3, 'pattern': 'constant', 'trend': 'same',
                      'onsetMonth': '2026-07'}],
        'medications': [{'name': 'Naproxen', 'strength': '500 mg', 'dose': '1 tablet',
                         'form': 'tablet', 'critical': False, 'startedMonth': '2026-06'}],
    }
    payload.update(over)
    return payload


def good_document(**over):
    doc = {'schemaVersion': TEMPLATE_DOCUMENT_VERSION, 'exportedAt': '2026-08-01T08:00:00.000Z',
           'patient': {'name': 'Zofia W.', 'age': 34, 'country': 'PL'},
           'symptoms': [], 'medications': [], 'appointments': [], 'vitals': [], 'checkIns': [],
           'doseEvents': [], 'careTeam': [], 'documents': [],
           'emergency': {'allergies': [], 'conditions': [], 'contacts': []}}
    doc.update(over)
    return doc


class WumTestCase(TestCase):
    def setUp(self):
        # The throttle counters live in a FILE cache shared with the dev server (root CLAUDE.md).
        cache.clear()

    def register(self, username='zofia', **over):
        body = {'username': username, 'password': PASSWORD, 'agree': True,
                'consent_text_version': rules.WUM_ACCOUNT_TEXT_VERSION}
        body.update(over)
        return self.client.post(REGISTER, body, content_type='application/json')

    def account(self, username='zofia'):
        r = self.register(username)
        assert r.status_code == 201, r.content
        return r.json()['token']

    def staff_token(self):
        staff = User.objects.create_user('staff', password=PASSWORD, is_staff=True)
        return Token.objects.create(user=staff).key

    def archive_token(self, username='archiwista'):
        u = User.objects.create_user(username, 'a@example.com', PASSWORD)
        return Token.objects.create(user=u).key

    def auth(self, token):
        return {'HTTP_AUTHORIZATION': f'Token {token}'}

    def post(self, url, body, token=None):
        return self.client.post(url, body, content_type='application/json', **(self.auth(token) if token else {}))


class RegisterTests(WumTestCase):
    def test_a_sign_up_creates_user_profile_and_token(self):
        r = self.register(first_name='Zofia', surname='W.', contact_email='z@example.com')
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertTrue(body['token'])
        self.assertEqual(body['account']['username'], 'zofia')
        self.assertEqual(body['account']['first_name'], 'Zofia')
        self.assertIsNone(body['account']['live_publication'])
        user = User.objects.get(username='zofia')
        self.assertEqual(user.email, '')  # the contact address is on the profile, not a login
        self.assertEqual(user.wum_profile.contact_email, 'z@example.com')
        self.assertEqual(user.wum_profile.agreed_text_version, rules.WUM_ACCOUNT_TEXT_VERSION)
        self.assertFalse(user.is_staff)

    def test_a_username_held_by_an_archive_account_is_taken(self):
        User.objects.create_user('Zofia', password=PASSWORD)
        r = self.register('zofia')
        self.assertEqual(r.status_code, 400)
        self.assertIn('username', r.json())

    def test_a_bad_username_is_refused_by_name(self):
        for bad in ('zo', 'zofia w', 'x' * 31, 'zofia@'):
            r = self.register(bad)
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn('username', r.json())

    def test_a_weak_password_is_refused_by_name(self):
        r = self.register(password='1234')
        self.assertEqual(r.status_code, 400)
        self.assertIn('password', r.json())

    def test_without_the_agreement_there_is_no_account(self):
        for agree in (False, None, 'no'):
            r = self.register(agree=agree)
            self.assertEqual(r.status_code, 400, agree)
            self.assertIn('agree', r.json())
        self.assertEqual(WumProfile.objects.count(), 0)

    def test_a_stale_consent_text_is_409_keyed_by_field(self):
        r = self.register(consent_text_version='1999-01-01')
        self.assertEqual(r.status_code, 409)
        self.assertIn('consent_text_version', r.json())
        self.assertEqual(User.objects.count(), 0)

    def test_a_bad_contact_email_is_refused_by_name(self):
        r = self.register(contact_email='not-an-address')
        self.assertEqual(r.status_code, 400)
        self.assertIn('contact_email', r.json())

    def test_the_honeypot_refuses(self):
        r = self.register(website='http://spam.example')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(User.objects.count(), 0)

    def test_an_archive_session_cookie_is_not_a_csrf_403(self):
        """The app is same-origin with the archive: a visitor signed in there sends the archive's
        session cookie whether they mean to or not. Token-only auth makes it irrelevant."""
        User.objects.create_user('ktos', password=PASSWORD)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(User.objects.get(username='ktos'))
        r = strict.post(REGISTER, json.dumps({'username': 'nowy', 'password': PASSWORD, 'agree': True,
                                              'consent_text_version': rules.WUM_ACCOUNT_TEXT_VERSION}),
                        content_type='application/json')
        self.assertEqual(r.status_code, 201)

    def test_the_eleventh_sign_up_from_one_address_is_429(self):
        for i in range(10):
            self.assertEqual(self.register(f'user{i}').status_code, 201)
        self.assertEqual(self.register('user10').status_code, 429)


class LoginTests(WumTestCase):
    def test_login_logout_me(self):
        self.account()
        r = self.post(LOGIN, {'username': 'zofia', 'password': PASSWORD})
        self.assertEqual(r.status_code, 200)
        token = r.json()['token']
        self.assertEqual(self.client.get(ME, **self.auth(token)).json()['username'], 'zofia')
        self.assertEqual(self.post(LOGOUT, {}, token).status_code, 204)
        self.assertEqual(self.client.get(ME, **self.auth(token)).status_code, 401)

    def test_a_wrong_password_is_401(self):
        self.account()
        r = self.post(LOGIN, {'username': 'zofia', 'password': 'nie-to'})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()['detail'], 'Zła nazwa lub hasło.')

    def test_an_archive_account_cannot_log_in_here_and_learns_nothing(self):
        User.objects.create_user('archiwista', password=PASSWORD)
        r = self.post(LOGIN, {'username': 'archiwista', 'password': PASSWORD})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()['detail'], 'Zła nazwa lub hasło.')

    def test_an_archive_token_is_not_a_wum_account(self):
        token = self.archive_token()
        self.assertEqual(self.client.get(ME, **self.auth(token)).status_code, 403)
        self.assertEqual(self.post(PUBLICATIONS, {'payload': good_payload()}, token).status_code, 403)

    def test_patch_me_changes_the_four_fields_and_nothing_else(self):
        token = self.account()
        r = self.client.patch(ME, json.dumps({'surname': 'Wiśniewska', 'contact_phone': '+48 600 000 000',
                                              'username': 'hacker', 'agreed_text_version': 'x'}),
                              content_type='application/json', **self.auth(token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['surname'], 'Wiśniewska')
        self.assertEqual(r.json()['username'], 'zofia')
        self.assertEqual(r.json()['agreed_text_version'], rules.WUM_ACCOUNT_TEXT_VERSION)


class TemplateTests(WumTestCase):
    def make(self, slug='zofia', status='published', **over):
        return Template.objects.create(slug=slug, title=slug.title(), locale='pl',
                                       document=good_document(**over), status=status)

    def test_anybody_lists_published_templates_only(self):
        self.make('a'); self.make('b', status='draft'); self.make('c', status='retired')
        r = self.client.get(TEMPLATES)
        self.assertEqual(r.status_code, 200)
        self.assertEqual([t['slug'] for t in r.json()['results']], ['a'])
        self.assertNotIn('document', r.json()['results'][0])

    def test_detail_hides_drafts_and_retired_like_unknown_slugs(self):
        self.make('d', status='draft'); self.make('r', status='retired'); self.make('p')
        self.assertEqual(self.client.get(TEMPLATES + 'd/').status_code, 404)
        self.assertEqual(self.client.get(TEMPLATES + 'r/').status_code, 404)
        self.assertEqual(self.client.get(TEMPLATES + 'nope/').status_code, 404)
        r = self.client.get(TEMPLATES + 'p/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['document']['patient']['name'], 'Zofia W.')

    def test_only_staff_write(self):
        body = {'slug': 'nowy', 'title': 'Nowy', 'locale': 'pl', 'document': good_document(), 'status': 'published'}
        self.assertEqual(self.post(TEMPLATES, body).status_code, 401)
        self.assertEqual(self.post(TEMPLATES, body, self.account()).status_code, 403)
        r = self.post(TEMPLATES, body, self.staff_token())
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Template.objects.get(slug='nowy').created_by.username, 'staff')

    def test_put_updates_and_delete_retires(self):
        self.make('p')
        token = self.staff_token()
        r = self.client.put(TEMPLATES + 'p/', json.dumps({'slug': 'p', 'title': 'Inny', 'locale': 'en',
                                                          'document': good_document(), 'status': 'published'}),
                            content_type='application/json', **self.auth(token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Template.objects.get(slug='p').title, 'Inny')
        self.assertEqual(self.client.delete(TEMPLATES + 'p/', **self.auth(token)).status_code, 204)
        self.assertEqual(Template.objects.get(slug='p').status, 'retired')

    def test_a_document_carrying_consent_state_is_refused_by_name(self):
        token = self.staff_token()
        for bad in (good_document(grants=[]), good_document(accessLog=[]), {'patient': {}},
                    good_document(schemaVersion='medapp.export/1'), good_document(extra=1),
                    good_document(patient={'name': '', 'age': 3}), good_document(patient={'name': 'X', 'age': 200}),
                    good_document(symptoms=[1])):
            r = self.post(TEMPLATES, {'slug': 's', 'title': 'S', 'locale': 'pl', 'document': bad}, token)
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn('document', r.json())
        self.assertEqual(Template.objects.count(), 0)

    def test_an_oversized_document_is_refused(self):
        r = self.post(TEMPLATES, {'slug': 's', 'title': 'S', 'locale': 'pl',
                                  'document': good_document(documents=[{'body': 'x' * MAX_TEMPLATE_BYTES}])},
                      self.staff_token())
        self.assertEqual(r.status_code, 400)
        self.assertIn('document', r.json())

    def test_a_bad_locale_and_a_duplicate_slug_are_refused_by_name(self):
        token = self.staff_token()
        r = self.post(TEMPLATES, {'slug': 's', 'title': 'S', 'locale': 'polish', 'document': good_document()}, token)
        self.assertEqual(r.status_code, 400)
        self.assertIn('locale', r.json())
        self.make('s')
        r = self.post(TEMPLATES, {'slug': 's', 'title': 'S', 'locale': 'pl', 'document': good_document()}, token)
        self.assertEqual(r.status_code, 400)
        self.assertIn('slug', r.json())


class PublicationTests(WumTestCase):
    def publish(self, token, **over):
        body = {'payload': good_payload(), 'payload_version': PAYLOAD_VERSION, 'agree': True,
                'consent_text_version': rules.WUM_PUBLISH_TEXT_VERSION}
        body.update(over)
        return self.post(PUBLICATIONS, body, token)

    def test_a_publication_is_listed_without_the_account(self):
        token = self.account('zofia')
        r = self.publish(token)
        self.assertEqual(r.status_code, 201)
        self.assertIsNone(r.json()['superseded'])
        self.assertRegex(r.json()['published_month'], r'^\d{4}-\d{2}$')
        listing = self.client.get(PUBLICATIONS)
        self.assertEqual(listing.status_code, 200)
        text = listing.content.decode()
        row = listing.json()['results'][0]
        self.assertEqual(set(row), {'id', 'payload', 'payload_version', 'published_month'})
        self.assertEqual(row['payload']['ageBand'], '30–39')
        self.assertNotIn('account', text)
        self.assertNotIn('zofia', text)
        self.assertNotIn('created_at', text)
        detail = self.client.get(PUBLICATIONS + row['id'] + '/')
        self.assertEqual(detail.status_code, 200)
        self.assertNotIn('zofia', detail.content.decode())

    def test_the_account_row_names_the_live_publication(self):
        token = self.account()
        pid = self.publish(token).json()['id']
        me = self.client.get(ME, **self.auth(token)).json()
        self.assertEqual(me['live_publication'], pid)
        self.assertEqual(me['publications_total'], 1)

    def test_publishing_again_supersedes_and_the_list_shows_one(self):
        token = self.account()
        first = self.publish(token).json()['id']
        r = self.publish(token, payload=good_payload(ageBand='40–49'))
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()['superseded'], first)
        old = Publication.objects.get(public_id=first)
        self.assertEqual(old.status, 'superseded')
        self.assertEqual(str(old.superseded_by.public_id), r.json()['id'])
        ids = [row['id'] for row in self.client.get(PUBLICATIONS).json()['results']]
        self.assertEqual(ids, [r.json()['id']])
        self.assertEqual(self.client.get(PUBLICATIONS + first + '/').status_code, 404)

    def test_withdraw_is_immediate_and_keeps_the_row(self):
        token = self.account()
        pid = self.publish(token).json()['id']
        r = self.post(PUBLICATIONS + pid + '/withdraw/', {}, token)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'withdrawn')
        row = Publication.objects.get(public_id=pid)
        self.assertEqual(row.status, 'withdrawn')
        self.assertIsNotNone(row.withdrawn_at)
        self.assertEqual(row.payload['ageBand'], '30–39')  # kept, not blanked (left open)
        self.assertEqual(self.client.get(PUBLICATIONS).json()['count'], 0)
        self.assertEqual(self.client.get(PUBLICATIONS + pid + '/').status_code, 404)
        # Withdrawing twice is a 404 like any row that is not live.
        self.assertEqual(self.post(PUBLICATIONS + pid + '/withdraw/', {}, token).status_code, 404)

    def test_a_stranger_cannot_withdraw_and_learns_nothing(self):
        owner = self.account('zofia')
        pid = self.publish(owner).json()['id']
        other = self.account('inna')
        r = self.post(PUBLICATIONS + pid + '/withdraw/', {}, other)
        self.assertEqual(r.status_code, 404)
        nope = self.post(PUBLICATIONS + '00000000-0000-4000-8000-000000000000/withdraw/', {}, other)
        self.assertEqual(r.content, nope.content)
        self.assertEqual(Publication.objects.get(public_id=pid).status, 'published')
        self.assertEqual(self.post(PUBLICATIONS + pid + '/withdraw/', {}).status_code, 401)

    def test_mine_lists_every_status(self):
        token = self.account()
        first = self.publish(token).json()['id']
        second = self.publish(token).json()['id']
        self.post(PUBLICATIONS + second + '/withdraw/', {}, token)
        rows = self.client.get(PUBLICATIONS + 'mine/', **self.auth(token)).json()
        self.assertEqual({r['id']: r['status'] for r in rows}, {first: 'superseded', second: 'withdrawn'})
        self.assertEqual(self.client.get(PUBLICATIONS + 'mine/').status_code, 401)

    def test_a_forbidden_key_anywhere_is_refused_by_name_and_a_medicine_name_is_not(self):
        token = self.account()
        for bad in (good_payload(displayName='Zofia'),
                    good_payload(symptoms=[{'partId': 'knee_l', 'subjectId': 'persona_02'}]),
                    good_payload(medications=[{'name': 'X', 'prescriber': {'phone': '600'}}]),
                    good_payload(ageBand='34'), good_payload(ageBand='1990-01-01'),
                    good_payload(version='wum.publication/0'), 'not a dict'):
            r = self.publish(token, payload=bad)
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn('payload', r.json())
        self.assertEqual(Publication.objects.count(), 0)
        self.assertEqual(self.publish(token).status_code, 201)

    def test_stale_versions_are_409_keyed_by_field(self):
        token = self.account()
        r = self.publish(token, payload_version='wum.publication/0')
        self.assertEqual(r.status_code, 409)
        self.assertIn('payload_version', r.json())
        r = self.publish(token, consent_text_version='1999-01-01')
        self.assertEqual(r.status_code, 409)
        self.assertIn('consent_text_version', r.json())
        self.assertEqual(Publication.objects.count(), 0)

    def test_an_oversized_payload_and_a_missing_agreement_are_refused(self):
        token = self.account()
        r = self.publish(token, payload=good_payload(history=['x' * MAX_PUBLICATION_BYTES]))
        self.assertEqual(r.status_code, 400)
        self.assertIn('payload', r.json())
        r = self.publish(token, agree=False)
        self.assertEqual(r.status_code, 400)
        self.assertIn('agree', r.json())
        self.assertEqual(self.publish(None).status_code, 401)

    def test_the_twenty_first_publish_from_one_address_is_429(self):
        token = self.account()
        for _ in range(20):
            self.assertEqual(self.publish(token).status_code, 201)
        self.assertEqual(self.publish(token).status_code, 429)
        # Reads are not counted against the write budget.
        self.assertEqual(self.client.get(PUBLICATIONS).status_code, 200)

    def test_an_account_with_publications_cannot_be_deleted(self):
        token = self.account()
        self.publish(token)
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            User.objects.get(username='zofia').delete()


class MirroredConstantsTests(TestCase):
    """Pins this side of every constant that also lives in the medapp repository, so a change
    here is a visible diff and the other side's gate (`scripts/privacy-check.mjs`) pins that one."""

    def test_payload_version(self):
        self.assertEqual(PAYLOAD_VERSION, 'wum.publication/1')

    def test_text_versions_are_dates(self):
        for v in (rules.WUM_ACCOUNT_TEXT_VERSION, rules.WUM_PUBLISH_TEXT_VERSION):
            self.assertRegex(v, r'^\d{4}-\d{2}-\d{2}$')

    def test_forbidden_keys_name_identity_and_never_a_medicine_name(self):
        self.assertNotIn('name', rules.FORBIDDEN_PAYLOAD_KEYS)
        for k in ('displayName', 'legalName', 'subjectId', 'country', 'position', 'onsetDate', 'careTeam'):
            self.assertIn(k, rules.FORBIDDEN_PAYLOAD_KEYS)

    def test_size_caps(self):
        self.assertEqual(MAX_PUBLICATION_BYTES, 128 * 1024)
        self.assertEqual(MAX_TEMPLATE_BYTES, 256 * 1024)

    def test_template_keys_exclude_consent_state(self):
        self.assertEqual(TEMPLATE_DOCUMENT_VERSION, 'medapp.export/2')
        self.assertFalse(set(TEMPLATE_KEYS) & set(TEMPLATE_REFUSED_KEYS))
        for k in ('patient', 'symptoms', 'medications', 'emergency'):
            self.assertIn(k, TEMPLATE_KEYS)

    def test_username_rule_is_the_archives(self):
        validators = ArchiveRegisterSerializer().fields['username'].validators
        archive = next(v for v in validators if hasattr(v, 'regex')).regex.pattern
        self.assertEqual(USERNAME_RE, archive)
        self.assertEqual(USERNAME_RE, r'^[a-zA-Z0-9_.-]{3,30}$')
