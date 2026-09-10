"""The confirmation flow and `is_trusted`. Throttle counters normally live in the shared
FILE cache (config/settings.py), which outlives a test run — so these tests swap in a
memory cache and clear it, or the 5/hour `verify` scope would start 429-ing on the second
run within an hour."""
from datetime import timedelta

from django.contrib.auth.models import AnonymousUser, User
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import EmailVerification, Profile, TrustedDomain
from .trust import is_trusted, mask_email, match_domain

FUW = 'jan@fuw.edu.pl'


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class Base(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('ola', 'o@x.pl', 'haslo12345')
        self.other = User.objects.create_user('bartek', 'b@x.pl', 'haslo12345')
        self.staff = User.objects.create_user('mod', 'm@x.pl', 'haslo12345', is_staff=True)

    def login(self, u):
        self.client.force_authenticate(u)

    def request(self, email, user=None):
        self.login(user or self.user)
        return self.client.post('/api/auth/verify/request/', {'email': email})

    def confirm(self, token):
        self.client.force_authenticate(None)  # the link may be opened logged out
        return self.client.post('/api/auth/verify/confirm/', {'token': token})

    def me(self, user):
        # A fresh instance, as a real request would have: force_authenticate() reuses the
        # same Python object, whose `.profile` reverse cache would otherwise go stale.
        self.login(User.objects.get(pk=user.pk))
        return self.client.get('/api/auth/me/').data


class MatchDomainTests(Base):
    def test_seed_is_present_and_matches(self):
        self.assertEqual(match_domain(FUW).institution, 'Wydział Fizyki UW')
        self.assertEqual(match_domain('Ktos@OKWF.fuw.edu.pl').domain, 'fuw.edu.pl')  # subdomain, case
        self.assertEqual(match_domain('x@student.uw.edu.pl').institution, 'Studenci UW')
        self.assertEqual(match_domain('x@uw.edu.pl').domain, 'uw.edu.pl')
        self.assertEqual(match_domain('x@ifpan.edu.pl').kind, 'pan')

    def test_spoofs_and_neighbours_do_not_match(self):
        for bad in ['x@evil.com', 'x@fuw.edu.pl.evil.com', 'x@gmail.com@fuw.edu.pl', 'x@gmail.com',
                    'x@foo.uw.edu.pl',       # uw.edu.pl does not match subdomains
                    'x@mimuw.edu.pl',        # seeded inactive
                    '"x y"@fuw.edu.pl', 'x y@fuw.edu.pl', 'x@fuw.edu.pl ', 'jaś@fuw.edu.pl',
                    'fuw.edu.pl', '', None, '@fuw.edu.pl']:
            self.assertIsNone(match_domain(bad), bad)

    def test_deactivating_a_domain_switches_it_off(self):
        TrustedDomain.objects.filter(domain='fuw.edu.pl').update(is_active=False)
        self.assertIsNone(match_domain(FUW))

    def test_mask(self):
        self.assertEqual(mask_email('jan.kowalski@fuw.edu.pl'), 'j***@fuw.edu.pl')
        self.assertEqual(mask_email(''), '')


class IsTrustedTests(Base):
    def test_staff_is_trusted_without_verification(self):
        self.assertTrue(is_trusted(self.staff))
        me = self.me(self.staff)
        self.assertTrue(me['is_trusted'])
        self.assertIsNone(me['affiliation'])

    def test_anonymous_and_none(self):
        self.assertFalse(is_trusted(AnonymousUser()))
        self.assertFalse(is_trusted(None))

    def test_plain_user_is_not_trusted(self):
        self.assertFalse(is_trusted(self.user))

    def test_user_without_profile_row_does_not_crash(self):
        Profile.objects.filter(user=self.user).delete()
        u = User.objects.get(pk=self.user.pk)
        self.assertFalse(is_trusted(u))
        self.assertTrue(Profile.objects.filter(user=u).exists())  # recreated on the way
        me = self.me(u)
        self.assertFalse(me['is_trusted'])

    def test_verified_user_loses_trust_when_domain_is_deactivated(self):
        self.confirm(self.request(FUW).data and EmailVerification.objects.get().token)
        self.assertTrue(is_trusted(User.objects.get(pk=self.user.pk)))
        TrustedDomain.objects.filter(domain='fuw.edu.pl').update(is_active=False)
        self.assertFalse(is_trusted(User.objects.get(pk=self.user.pk)))


class VerificationFlowTests(Base):
    def test_request_sends_link_then_confirm_grants_trust(self):
        r = self.request(FUW)
        self.assertEqual(r.status_code, 202, r.data)
        self.assertEqual(r.data, {'sent_to': 'j***@fuw.edu.pl'})
        self.assertEqual(len(mail.outbox), 1)
        v = EmailVerification.objects.get()
        m = mail.outbox[0]
        self.assertEqual(m.to, [FUW])
        self.assertEqual(m.subject, 'fuw.lol — potwierdź adres')
        self.assertIn(f'http://localhost:5173/potwierdz?token={v.token}', m.body)
        self.assertIn('tablicy moderacji', m.body)  # says what it grants
        me = self.me(self.user)
        self.assertFalse(me['is_trusted'])
        self.assertIsNone(me['affiliation'])
        self.assertEqual(me['pending_verification'], 'j***@fuw.edu.pl')

        r = self.confirm(v.token)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data, {'ok': True, 'is_trusted': True, 'institution': 'Wydział Fizyki UW'})
        me = self.me(self.user)
        self.assertTrue(me['is_trusted'])
        self.assertEqual(me['affiliation']['institution'], 'Wydział Fizyki UW')
        self.assertEqual(me['affiliation']['domain'], 'fuw.edu.pl')
        self.assertEqual(me['affiliation']['email_masked'], 'j***@fuw.edu.pl')
        self.assertIsNotNone(me['affiliation']['verified_at'])
        self.assertIsNone(me['pending_verification'])
        self.assertTrue(is_trusted(User.objects.get(pk=self.user.pk)))

    def test_gmail_is_refused_naming_the_institutions(self):
        r = self.request('jan@gmail.com')
        self.assertEqual(r.status_code, 400)
        msg = r.data['email'][0]
        self.assertIn('Wydział Fizyki UW (fuw.edu.pl)', msg)
        self.assertIn('Instytut Fizyki PAN (ifpan.edu.pl)', msg)
        self.assertNotIn('mimuw', msg)  # inactive domains are not advertised
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(EmailVerification.objects.count(), 0)

    def test_spoofed_addresses_are_refused(self):
        for bad in ['x@gmail.com@fuw.edu.pl', 'x@fuw.edu.pl.evil.com', 'x@mimuw.edu.pl']:
            self.assertEqual(self.request(bad).status_code, 400, bad)
        self.assertEqual(len(mail.outbox), 0)

    def test_token_is_single_use(self):
        self.request(FUW)
        token = EmailVerification.objects.get().token
        self.assertEqual(self.confirm(token).status_code, 200)
        r = self.confirm(token)
        self.assertEqual(r.status_code, 400)
        self.assertIn('wygasł lub został już użyty', r.data['detail'])
        self.assertEqual(self.confirm('nie-ma-takiego').status_code, 400)
        self.assertEqual(self.confirm('').status_code, 400)

    def test_expired_token_is_refused(self):
        self.request(FUW)
        v = EmailVerification.objects.get()
        EmailVerification.objects.filter(pk=v.pk).update(created_at=timezone.now() - timedelta(hours=25))
        r = self.confirm(v.token)
        self.assertEqual(r.status_code, 400)
        self.assertIn('wygasł', r.data['detail'])
        self.assertFalse(is_trusted(User.objects.get(pk=self.user.pk)))
        self.assertIsNone(self.me(self.user)['pending_verification'])

    def test_new_request_invalidates_the_older_one(self):
        self.request(FUW)
        old = EmailVerification.objects.get().token
        self.request('jan@okwf.fuw.edu.pl')
        self.assertEqual(EmailVerification.objects.count(), 1)
        self.assertEqual(self.confirm(old).status_code, 400)
        self.assertEqual(self.confirm(EmailVerification.objects.get().token).status_code, 200)

    def test_second_account_cannot_verify_the_same_email(self):
        self.request(FUW)
        self.confirm(EmailVerification.objects.get().token)
        r = self.request(FUW, user=self.other)
        self.assertEqual(r.status_code, 400)
        self.assertIn('innym koncie', r.data['email'][0])
        # …nor with a token it obtained before the first account confirmed
        self.request('Jan@FUW.edu.pl', user=self.other)  # (rejected above only once confirmed; re-request for the race)
        self.assertEqual(EmailVerification.objects.filter(user=self.other).count(), 0)

    def test_race_between_two_accounts_is_caught_at_confirm(self):
        self.request(FUW)
        self.request(FUW, user=self.other)
        first, second = (EmailVerification.objects.get(user=u).token for u in (self.user, self.other))
        self.assertEqual(self.confirm(first).status_code, 200)
        r = self.confirm(second)
        self.assertEqual(r.status_code, 400)
        self.assertIn('innym koncie', r.data['detail'])
        self.assertFalse(is_trusted(User.objects.get(pk=self.other.pk)))

    def test_domain_switched_off_between_mail_and_click(self):
        self.request(FUW)
        TrustedDomain.objects.filter(domain='fuw.edu.pl').update(is_active=False)
        r = self.confirm(EmailVerification.objects.get().token)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(is_trusted(User.objects.get(pk=self.user.pk)))

    def test_anonymous_cannot_request(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post('/api/auth/verify/request/', {'email': FUW}).status_code, 401)

    def test_request_is_throttled(self):
        for _ in range(5):
            self.assertEqual(self.request('x@gmail.com').status_code, 400)
        self.assertEqual(self.request(FUW).status_code, 429)
        self.assertEqual(len(mail.outbox), 0)

    def test_trusted_domains_are_public(self):
        self.client.force_authenticate(None)
        r = self.client.get('/api/auth/trusted-domains/')
        self.assertEqual(r.status_code, 200)
        domains = {d['domain'] for d in r.data}
        self.assertIn('fuw.edu.pl', domains)
        self.assertIn('ippt.pan.pl', domains)
        self.assertNotIn('mimuw.edu.pl', domains)
        self.assertEqual(set(r.data[0]), {'domain', 'institution', 'kind'})


class RealIpMiddlewareTests(APITestCase):
    """Behind Traefik/Cloudflare the per-IP throttles must see the visitor, not the proxy."""

    def _ip(self, **headers):
        from django.test import override_settings
        seen = {}
        from accounts import views as v
        original = v.LoginView.post

        def spy(self_, request):
            seen['ip'] = request.META.get('REMOTE_ADDR')
            return original(self_, request)
        v.LoginView.post = spy
        try:
            with override_settings(FUWLOL_TRUST_PROXY=True):
                self.client.post('/api/auth/login/', {'username': 'x', 'password': 'y'}, **headers)
        finally:
            v.LoginView.post = original
        return seen.get('ip')

    def test_cloudflare_header_wins_then_forwarded_for(self):
        self.assertEqual(self._ip(HTTP_CF_CONNECTING_IP='203.0.113.9', HTTP_X_FORWARDED_FOR='10.0.0.1'), '203.0.113.9')
        self.assertEqual(self._ip(HTTP_X_FORWARDED_FOR='198.51.100.7, 10.0.0.1'), '198.51.100.7')

    def test_headers_ignored_without_trust_flag(self):
        from django.test import override_settings
        with override_settings(FUWLOL_TRUST_PROXY=False):
            r = self.client.post('/api/auth/login/', {'username': 'x', 'password': 'y'}, HTTP_CF_CONNECTING_IP='203.0.113.9')
        self.assertEqual(r.status_code, 401)  # the request went through normally; the header did nothing
