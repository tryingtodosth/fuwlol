"""What the one endpoint promises. `test.md` lists this suite.

The theme of most of these: a note must be hard to lose. Only the text can be refused; the
hidden fields never refuse anything, and the response says plainly that the note arrived.
"""
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from rest_framework.authtoken.models import Token

from .models import CONTACT_MAX, MAX_LEN, Feedback

URL = '/api/feedback/'


class FeedbackWriteTests(TestCase):
    def setUp(self):
        # The throttle counters live in a FILE cache shared with the dev server and the browser
        # scripts (root CLAUDE.md), so a suite that does not clear it starts at whatever the
        # last run left behind and fails at 429 for no reason visible in the code.
        cache.clear()

    def post(self, **kwargs):
        body = {'kind': 'bug', 'text': 'Lista dawek gubi wiersz 22:00.',
                'location': '/care/medicines', 'locale': 'pl'}
        body.update(kwargs)
        return self.client.post(URL, body, content_type='application/json')

    def test_a_note_is_stored_with_the_screen_it_came_from(self):
        r = self.post()
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json()['ok'])
        note = Feedback.objects.get(pk=r.json()['id'])
        self.assertEqual(note.kind, 'bug')
        self.assertEqual(note.location, '/care/medicines')
        self.assertEqual(note.locale, 'pl')
        self.assertEqual(note.app, 'skoki')
        self.assertEqual(note.status, 'new')
        self.assertIsNone(note.author)

    def test_all_four_kinds_are_accepted(self):
        for kind in ('bug', 'suggestion', 'idea', 'comment'):
            self.assertEqual(self.post(kind=kind).status_code, 201, kind)
        self.assertEqual(Feedback.objects.count(), 4)

    def test_an_unknown_kind_is_refused_by_name(self):
        r = self.post(kind='praise')
        self.assertEqual(r.status_code, 400)
        self.assertIn('kind', r.json())

    def test_an_empty_note_is_refused(self):
        for text in ('', '   ', None):
            r = self.post(text=text)
            self.assertEqual(r.status_code, 400)
            self.assertIn('text', r.json())
        self.assertEqual(Feedback.objects.count(), 0)

    def test_a_note_over_the_limit_is_refused_and_one_at_the_limit_is_not(self):
        self.assertEqual(self.post(text='a' * MAX_LEN).status_code, 201)
        r = self.post(text='a' * (MAX_LEN + 1))
        self.assertEqual(r.status_code, 400)
        self.assertIn('text', r.json())

    def test_the_honeypot_refuses(self):
        r = self.post(website='http://spam.example')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Feedback.objects.count(), 0)

    # --- the hidden fields never lose a note -----------------------------------------

    def test_a_note_with_no_location_still_arrives(self):
        r = self.post(location=None)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Feedback.objects.get().location, '')

    def test_a_location_that_is_not_a_path_is_dropped_not_refused(self):
        for bad in ('https://evil.example/x', '//evil.example/x', 'care/medicines',
                    '/care/\nmedicines', '/' + 'x' * 400):
            Feedback.objects.all().delete()
            r = self.post(location=bad)
            self.assertEqual(r.status_code, 201, bad)
            self.assertEqual(Feedback.objects.get().location, '', bad)

    def test_a_location_with_a_query_is_kept(self):
        self.assertEqual(self.post(location='/history?symptom=3').status_code, 201)
        self.assertEqual(Feedback.objects.get().location, '/history?symptom=3')

    def test_an_odd_locale_is_dropped_not_refused(self):
        r = self.post(locale='klingon')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Feedback.objects.get().locale, '')

    def test_uk_and_en_are_kept(self):
        for locale in ('uk', 'en', 'pt-BR'):
            Feedback.objects.all().delete()
            self.assertEqual(self.post(locale=locale).status_code, 201)
            self.assertEqual(Feedback.objects.get().locale, locale)

    # --- who is asking ---------------------------------------------------------------

    def test_the_address_is_hashed_never_stored(self):
        self.post(REMOTE_ADDR='203.0.113.9')
        note = Feedback.objects.get()
        self.assertTrue(note.ip_hash)
        self.assertNotIn('203.0.113', note.ip_hash)
        self.assertEqual(len(note.ip_hash), 64)

    def test_a_caller_with_a_token_is_recorded(self):
        user = User.objects.create_user('doktorant', password='x')
        token = Token.objects.create(user=user)
        self.client.post(URL, {'kind': 'idea', 'text': 'Da się.'},
                         content_type='application/json',
                         HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(Feedback.objects.get().author, user)

    def test_a_session_cookie_does_not_turn_a_note_into_a_csrf_403(self):
        """The endpoint is same-origin with the archive (`fuw.lol/fum`), so a visitor signed
        in to fuw.lol sends its session cookie with this POST whether they meant to or not. With
        SessionAuthentication in the list DRF would enforce CSRF and refuse the note with 403;
        `views.FeedbackView` drops session auth for exactly that reason. `enforce_csrf_checks`
        makes this client behave like a real browser — the default test client does not, so
        without it this test passes against the very code it is meant to catch."""
        user = User.objects.create_user('dziekan', password='x')
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        r = client.post(URL, {'kind': 'bug', 'text': 'Z ciasteczkiem archiwum.'},
                        content_type='application/json')
        self.assertEqual(r.status_code, 201)
        # Nobody's note is attributed to them by a cookie they forgot they had, either.
        self.assertIsNone(Feedback.objects.get().author)

    # --- the shape of the endpoint ---------------------------------------------------

    def test_there_is_no_way_to_read_the_notes_back(self):
        self.post()
        self.assertEqual(self.client.get(URL).status_code, 405)

    def test_the_throttle_answers_429_eventually(self):
        # 120/hour (settings.py). Proving the scope is wired at all is the point; the exact
        # rate is a settings question, not a code one.
        for _ in range(120):
            self.post()
        self.assertEqual(self.post().status_code, 429)


class SignatureTests(TestCase):
    """The optional "sign it" line: kept as typed on one line, refused only for its length."""

    def setUp(self):
        cache.clear()

    def post(self, **kwargs):
        body = {'kind': 'comment', 'text': 'Dobre.', 'location': '/today', 'locale': 'pl'}
        body.update(kwargs)
        return self.client.post(URL, body, content_type='application/json')

    def test_a_note_without_a_signature_is_anonymous_as_before(self):
        r = self.post()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Feedback.objects.get().contact, '')

    def test_a_signature_is_kept(self):
        self.assertEqual(self.post(contact='  Ola, ola@example.org ').status_code, 201)
        self.assertEqual(Feedback.objects.get().contact, 'Ola, ola@example.org')

    def test_line_breaks_are_folded_not_refused(self):
        self.assertEqual(self.post(contact='Ola\r\nola@example.org\t').status_code, 201)
        self.assertEqual(Feedback.objects.get().contact, 'Ola ola@example.org')

    def test_null_and_blank_are_anonymous(self):
        for value in (None, '', '   '):
            self.assertEqual(self.post(contact=value).status_code, 201, value)
        self.assertEqual(set(Feedback.objects.values_list('contact', flat=True)), {''})

    def test_a_signature_over_the_limit_is_refused_by_name_and_one_at_it_is_not(self):
        self.assertEqual(self.post(contact='a' * CONTACT_MAX).status_code, 201)
        r = self.post(contact='a' * (CONTACT_MAX + 1))
        self.assertEqual(r.status_code, 400)
        self.assertIn('contact', r.json())
        self.assertEqual(Feedback.objects.count(), 1)


@override_settings(FUWLOL_FEEDBACK_ORIGINS={'https://medapp.net': 'medapp'})
class CrossOriginTests(TestCase):
    """medapp.net files notes here from another origin; nothing else is opened."""

    def setUp(self):
        cache.clear()

    def post(self, origin, **kwargs):
        body = {'kind': 'bug', 'text': 'Przycisk nie działa.', 'location': '/today', 'locale': 'en'}
        body.update(kwargs)
        return self.client.post(URL, body, content_type='application/json', HTTP_ORIGIN=origin)

    def test_the_preflight_from_a_listed_origin_is_answered(self):
        r = self.client.options(URL, HTTP_ORIGIN='https://medapp.net',
                                HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
                                HTTP_ACCESS_CONTROL_REQUEST_HEADERS='content-type')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Access-Control-Allow-Origin'], 'https://medapp.net')
        self.assertIn('POST', r['Access-Control-Allow-Methods'])
        self.assertIn('Content-Type', r['Access-Control-Allow-Headers'])
        self.assertNotIn('Access-Control-Allow-Credentials', r)

    def test_a_note_from_a_listed_origin_is_filed_under_its_app(self):
        r = self.post('https://medapp.net', app='skoki', contact='x@example.org')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r['Access-Control-Allow-Origin'], 'https://medapp.net')
        self.assertIn('Origin', r['Vary'])
        note = Feedback.objects.get()
        self.assertEqual(note.app, 'medapp')
        self.assertEqual(note.contact, 'x@example.org')

    def test_an_unlisted_origin_gets_no_cors_headers(self):
        r = self.post('https://evil.example')
        self.assertNotIn('Access-Control-Allow-Origin', r)
        r = self.client.options(URL, HTTP_ORIGIN='https://evil.example',
                                HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST')
        self.assertNotIn('Access-Control-Allow-Origin', r)

    def test_same_origin_notes_keep_their_app(self):
        self.assertEqual(self.post('https://fuw.lol').status_code, 201)
        self.assertEqual(Feedback.objects.get().app, 'skoki')

    def test_a_preflight_does_not_spend_the_allowance(self):
        for _ in range(130):
            self.client.options(URL, HTTP_ORIGIN='https://medapp.net',
                                HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST')
        self.assertEqual(self.post('https://medapp.net').status_code, 201)

    def test_the_other_endpoints_are_not_opened(self):
        r = self.client.options('/api/wum/', HTTP_ORIGIN='https://medapp.net',
                                HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST')
        self.assertNotIn('Access-Control-Allow-Origin', r)


class MirroredConstantsTests(TestCase):
    """`KIND_CHOICES` and `MAX_LEN` exist twice — here and in MedApp's widget, which is a
    SEPARATE REPOSITORY and therefore cannot be imported. This test pins the server's copy so
    that a change here is a visible, deliberate diff; the app's `src/lib/feedback/api.ts`
    carries the same list with a comment naming this file."""

    def test_the_four_kinds_and_the_limit_are_what_the_widget_draws(self):
        from .models import KIND_CHOICES
        self.assertEqual([k for k, _ in KIND_CHOICES],
                         ['bug', 'suggestion', 'idea', 'comment'])
        self.assertEqual(MAX_LEN, 4096)
        self.assertEqual(CONTACT_MAX, 200)
