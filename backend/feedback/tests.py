"""What the one endpoint promises. `test.md` lists this suite.

The theme of most of these: a note must be hard to lose. Only the text can be refused; the
hidden fields never refuse anything, and the response says plainly that the note arrived.
"""
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase
from rest_framework.authtoken.models import Token

from .models import MAX_LEN, Feedback

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
        """The endpoint is same-origin with the archive (`fuw.lol/fwumu`), so a visitor signed
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
