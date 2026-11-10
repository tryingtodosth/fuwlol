"""What the newsletter's three endpoints and its one mail promise. `test.md` lists this suite."""
import re
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from . import mail as nl_mail
from .models import CONFIRM_DAYS, CONSENT_VERSION, EMAIL_MAX, PENDING_DAYS, TOKEN_MAX, Subscriber

URL = '/api/newsletter/'
CONFIRM = '/api/newsletter/confirm/'
UNSUB = '/api/newsletter/unsubscribe/'
ORIGIN = 'https://medapp.net'


def _frag(body, name):
    m = re.search(r'https://medapp\.net(/[a-z]{2})?/newsletter#' + name + r'=(\S+)', body)
    return m and m.group(2)


class NewsletterCase(TestCase):
    def setUp(self):
        cache.clear()

    def sub(self, origin=ORIGIN, **kw):
        body = {'email': 'Vet@Example.org ', 'consent_version': CONSENT_VERSION, 'locale': 'pl'}
        body.update(kw)
        extra = {'HTTP_ORIGIN': origin} if origin else {}
        return self.client.post(URL, body, content_type='application/json', **extra)

    def post(self, url, token, origin=ORIGIN):
        return self.client.post(url, {'token': token}, content_type='application/json', HTTP_ORIGIN=origin)

    def confirm_token(self, i=-1):
        return _frag(mail.outbox[i].body, 'confirm')

    def unsub_token(self, i=-1):
        return _frag(mail.outbox[i].body, 'unsubscribe') or \
            re.search(r'#unsubscribe=([^>]+)', mail.outbox[i].extra_headers['List-Unsubscribe']).group(1)

    def cool_down(self):
        Subscriber.objects.update(mailed_at=timezone.now() - timedelta(hours=1))


class SubscribeTests(NewsletterCase):
    def test_a_sign_up_is_pending_lower_cased_and_mailed_a_link(self):
        r = self.sub()
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.json(), {'ok': True})
        s = Subscriber.objects.get()
        self.assertEqual(s.email, 'vet@example.org')
        self.assertEqual((s.locale, s.source, s.consent_version, s.status), ('pl', 'medapp', CONSENT_VERSION, 'pending'))
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertEqual(m.to, ['vet@example.org'])
        self.assertEqual(m.from_email, 'medapp.net <info@medapp.net>')
        self.assertEqual(m.reply_to, ['info@medapp.net'])
        self.assertRegex(m.message()['Message-ID'], r'^<[^@<>\s]+@medapp\.net>$')
        self.assertIn('Potwierdź', m.subject)
        self.assertIn('https://medapp.net/pl/newsletter#confirm=', m.body)
        self.assertIn(f'{CONFIRM_DAYS} dni', m.body)
        self.assertLessEqual(len(self.confirm_token()), TOKEN_MAX)

    def test_the_link_follows_the_language_and_english_has_no_prefix(self):
        self.sub(locale='en')
        self.assertIn('https://medapp.net/newsletter#confirm=', mail.outbox[0].body)
        self.assertIn('Confirm', mail.outbox[0].subject)
        self.sub(email='b@example.org', locale='uk')
        self.assertIn('https://medapp.net/uk/newsletter#confirm=', mail.outbox[1].body)
        self.sub(email='c@example.org', locale='lol')
        self.assertIn('https://medapp.net/newsletter#', mail.outbox[2].body)  # lol: English mail

    def test_nothing_identifying_the_sender_is_kept(self):
        self.sub()
        fields = {f.name for f in Subscriber._meta.get_fields()}
        self.assertEqual(fields, {'id', 'email', 'locale', 'source', 'consent_version', 'status',
                                  'subscribed_at', 'confirmed_at', 'unsubscribed_at', 'mailed_at'})

    def test_only_a_known_origin_may_sign_up_and_it_gets_cors(self):
        r = self.sub()
        self.assertEqual(r['Access-Control-Allow-Origin'], ORIGIN)
        self.assertNotIn('Access-Control-Allow-Credentials', r)
        self.assertIn('Origin', r['Vary'])
        for origin in ('https://evil.example', None):
            r = self.sub(origin=origin, email='a@b.org')
            self.assertEqual(r.status_code, 403)
            self.assertNotIn('Access-Control-Allow-Origin', r)
        self.assertFalse(Subscriber.objects.filter(email='a@b.org').exists())
        self.assertEqual(len(mail.outbox), 1)

    def test_the_preflight_is_answered_and_not_throttled(self):
        for url in (URL, CONFIRM, UNSUB):
            for _ in range(30):
                r = self.client.options(url, HTTP_ORIGIN=ORIGIN, HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST')
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r['Access-Control-Allow-Origin'], ORIGIN)
            self.assertIn('POST', r['Access-Control-Allow-Methods'])
            self.assertIn('Content-Type', r['Access-Control-Allow-Headers'])

    def test_one_mail_per_address_within_the_cooldown_with_the_same_answer(self):
        self.assertEqual(self.sub().status_code, 202)
        self.assertEqual(self.sub().status_code, 202)
        self.assertEqual(len(mail.outbox), 1)
        self.cool_down()
        self.assertEqual(self.sub(locale='en').status_code, 202)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(Subscriber.objects.get().locale, 'en')

    def test_a_newer_sign_up_voids_the_older_link(self):
        self.sub()
        old = self.confirm_token()
        self.cool_down()
        Subscriber.objects.update(subscribed_at=timezone.now() - timedelta(minutes=5))
        self.sub()
        self.assertEqual(self.post(CONFIRM, old).status_code, 404)
        self.assertEqual(self.post(CONFIRM, self.confirm_token()).status_code, 200)

    def test_an_address_already_on_the_list_gets_a_different_mail_and_the_same_answer(self):
        self.sub()
        self.post(CONFIRM, self.confirm_token())
        self.cool_down()
        r = self.sub(locale='en', consent_version=CONSENT_VERSION)
        self.assertEqual((r.status_code, r.json()), (202, {'ok': True}))
        s = Subscriber.objects.get()
        self.assertEqual((s.status, s.locale), ('active', 'pl'))  # nothing changed by a stranger
        self.assertIn('już na liście', mail.outbox[-1].body)
        self.assertNotIn('#confirm=', mail.outbox[-1].body)
        self.assertIn('#unsubscribe=', mail.outbox[-1].body)

    def test_a_wrong_consent_version_or_a_bad_address_is_refused(self):
        self.assertEqual(self.sub(consent_version='old').status_code, 400)
        self.assertEqual(self.sub(email='not-an-address').status_code, 400)
        self.assertEqual(self.sub(email='a' * (EMAIL_MAX - 10) + '@example.org').status_code, 400)
        self.assertFalse(Subscriber.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_the_honeypot_answers_the_same_and_keeps_and_mails_nothing(self):
        r = self.sub(website='http://spam.example')
        self.assertEqual((r.status_code, r.json()), (202, {'ok': True}))
        self.assertFalse(Subscriber.objects.exists())
        self.assertEqual(mail.outbox, [])

    def test_an_odd_locale_is_dropped_not_refused(self):
        self.assertEqual(self.sub(locale='<script>').status_code, 202)
        self.assertEqual(Subscriber.objects.get().locale, '')

    def test_an_unconfirmed_row_is_forgotten_after_the_pending_days(self):
        self.sub()
        Subscriber.objects.update(subscribed_at=timezone.now() - timedelta(days=PENDING_DAYS + 1))
        self.sub(email='other@example.org')
        self.assertEqual(list(Subscriber.objects.values_list('email', flat=True)), ['other@example.org'])

    def test_a_mail_that_fails_answers_503_and_does_not_start_the_cooldown(self):
        with mock.patch.object(nl_mail.EmailMessage, 'send', side_effect=OSError('smtp down')), \
                self.assertLogs('newsletter.views', 'ERROR'):
            r = self.sub()
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()['mail'], ['unavailable'])
        self.assertIsNone(Subscriber.objects.get().mailed_at)
        self.assertEqual(self.sub().status_code, 202)
        self.assertEqual(len(mail.outbox), 1)

    def test_there_is_no_get(self):
        self.sub()
        for url in (URL, CONFIRM, UNSUB):
            self.assertEqual(self.client.get(url, HTTP_ORIGIN=ORIGIN).status_code, 405)

    def test_a_session_cookie_is_not_a_csrf_403(self):
        from django.contrib.auth import get_user_model
        from django.test import Client
        user = get_user_model().objects.create_user('someone', 'someone@example.org', 'pw-123456789')
        c = Client(enforce_csrf_checks=True)
        c.force_login(user)
        r = c.post(URL, {'email': 'x@example.org', 'consent_version': CONSENT_VERSION},
                   content_type='application/json', HTTP_ORIGIN=ORIGIN)
        self.assertEqual(r.status_code, 202)

    def test_signing_up_is_throttled(self):
        codes = [self.sub(email=f'p{i}@example.org').status_code for i in range(21)]
        self.assertEqual(codes[:20], [202] * 20)
        self.assertEqual(codes[20], 429)


class ConfirmTests(NewsletterCase):
    def test_the_link_confirms_once_and_a_second_press_is_still_ok(self):
        self.sub()
        t = self.confirm_token()
        r = self.post(CONFIRM, t)
        self.assertEqual((r.status_code, r.json()), (200, {'ok': True}))
        self.assertEqual(r['Access-Control-Allow-Origin'], ORIGIN)
        s = Subscriber.objects.get()
        self.assertEqual(s.status, 'active')
        self.assertIsNotNone(s.confirmed_at)
        self.assertEqual(self.post(CONFIRM, t).status_code, 200)

    def test_an_old_link_is_gone_and_a_forged_one_unknown(self):
        self.sub()
        t = self.confirm_token()
        later = timezone.now() + timedelta(days=CONFIRM_DAYS, minutes=1)
        with mock.patch('django.core.signing.time.time', return_value=later.timestamp()):
            r = self.post(CONFIRM, t)
        self.assertEqual((r.status_code, r.json()['token']), (410, ['expired']))
        self.assertEqual(self.post(CONFIRM, t[:-2] + 'xx').status_code, 404)
        self.assertEqual(self.post(CONFIRM, self.unsub_token()).status_code, 404)  # wrong salt
        self.assertEqual(Subscriber.objects.get().status, 'pending')

    def test_a_link_does_not_undo_an_unsubscription(self):
        self.sub()
        t = self.confirm_token()
        self.post(UNSUB, self.unsub_token())
        self.assertEqual(self.post(CONFIRM, t).status_code, 404)
        self.assertEqual(Subscriber.objects.get().status, 'unsubscribed')


class UnsubscribeTests(NewsletterCase):
    def test_the_unsubscribe_link_ends_it_and_a_second_press_is_ok(self):
        self.sub()
        self.post(CONFIRM, self.confirm_token())
        t = self.unsub_token()
        r = self.post(UNSUB, t)
        self.assertEqual((r.status_code, r.json()), (200, {'ok': True}))
        s = Subscriber.objects.get()
        self.assertEqual(s.status, 'unsubscribed')
        self.assertIsNotNone(s.unsubscribed_at)
        self.assertEqual(self.post(UNSUB, t).status_code, 200)
        self.assertEqual(self.post(UNSUB, 'nonsense').status_code, 404)
        self.assertEqual(self.post(UNSUB, 'x' * (TOKEN_MAX + 1)).status_code, 400)

    def test_signing_up_again_after_unsubscribing_asks_for_confirmation_again(self):
        self.sub()
        self.post(CONFIRM, self.confirm_token())
        self.post(UNSUB, self.unsub_token())
        self.cool_down()
        self.sub()
        self.assertEqual(Subscriber.objects.get().status, 'pending')
        self.assertIn('#confirm=', mail.outbox[-1].body)

    def test_every_mail_carries_a_list_unsubscribe_header(self):
        self.sub()
        self.assertIn('/newsletter#unsubscribe=', mail.outbox[0].extra_headers['List-Unsubscribe'])
        self.assertEqual(mail.outbox[0].extra_headers['Auto-Submitted'], 'auto-generated')


@override_settings(FUWLOL_NEWSLETTER_SITES={'medapp': 'http://127.0.0.1:5197'})
class SiteTests(NewsletterCase):
    def test_the_links_point_at_the_configured_copy(self):
        self.sub(locale='en')
        self.assertIn('http://127.0.0.1:5197/newsletter#confirm=', mail.outbox[0].body)


class AdminExportTests(NewsletterCase):
    def test_the_export_lists_confirmed_rows_with_their_unsubscribe_link(self):
        from django.contrib.auth import get_user_model
        self.sub()
        self.post(CONFIRM, self.confirm_token())
        self.sub(email='pending@example.org')
        admin = get_user_model().objects.create_superuser('root', 'root@example.org', 'pw-123456789')
        self.client.force_login(admin)
        r = self.client.post('/admin/newsletter/subscriber/', {
            'action': 'export_active', '_selected_action': list(Subscriber.objects.values_list('pk', flat=True))})
        body = r.content.decode()
        self.assertIn('vet@example.org', body)
        self.assertNotIn('pending@example.org', body)
        self.assertIn('https://medapp.net/pl/newsletter#unsubscribe=', body)
