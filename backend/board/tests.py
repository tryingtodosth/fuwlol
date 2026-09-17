"""The shoutbox, tested at its refusals.

Most of what this app is, is what it will not accept: a picture, a sixth link, a 2049th
character, somebody else's username, a bot filling the honeypot. Those get a test each,
in both directions where the boundary matters (2048 passes, 2049 does not).
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils import timezone
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.test import APITestCase

from accounts.models import TrustedDomain
from .models import MAX_LEN, Message, Report

URL = '/api/board/'


def make_trusted(username):
    u = User.objects.create_user(username, f'{username}@fuw.edu.pl', 'haslo12345')
    dom, _ = TrustedDomain.objects.get_or_create(domain='fuw.edu.pl', defaults={'institution': 'FUW', 'kind': 'fuw'})
    p = u.profile
    p.affiliation_email, p.affiliation_domain, p.verified_at = f'{username}@fuw.edu.pl', dom, timezone.now()
    p.save()
    return u


class Base(APITestCase):
    def setUp(self):
        # throttle counters live in the shared file cache and would leak between tests
        cache.clear()
        self.staff = User.objects.create_user('mod', 'm@x.pl', 'haslo12345', is_staff=True)
        self.user = User.objects.create_user('ola', 'o@x.pl', 'haslo12345')

    def post(self, **data):
        data.setdefault('body', 'cześć')
        return self.client.post(URL, data)


class WriteTests(Base):
    def test_guest_writes_with_a_nick(self):
        r = self.post(nick='Zdzisław', body='no i po egzaminie')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['nick'], 'Zdzisław')
        self.assertTrue(r.data['is_guest'])
        self.assertIsNone(r.data['author_id'])

    def test_guest_without_a_nick_is_anonim(self):
        r = self.post(body='ktoś tu jest?')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['nick'], 'Anonim')

    def test_a_logged_in_author_is_always_their_username(self):
        self.client.force_authenticate(self.user)
        r = self.post(nick='NieOla', body='to ja')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['nick'], 'ola')
        self.assertFalse(r.data['is_guest'])
        self.assertEqual(r.data['author_id'], self.user.pk)

    def test_a_guest_may_not_borrow_a_registered_name(self):
        r = self.post(nick='OLA', body='udaję kogoś')
        self.assertEqual(r.status_code, 400)
        self.assertIn('zarejestrowanego', str(r.data['nick']))
        self.assertEqual(Message.objects.count(), 0)

    def test_nick_characters_are_limited(self):
        self.assertEqual(self.post(nick='<b>hej</b>', body='x').status_code, 400)

    def test_the_length_limit_is_2048_exactly(self):
        self.assertEqual(MAX_LEN, 2 ** 11)
        self.assertEqual(self.post(body='a' * (MAX_LEN + 1)).status_code, 400)
        self.assertEqual(self.post(body='a' * MAX_LEN).status_code, 201)

    def test_a_too_long_message_says_how_long_in_polish(self):
        r = self.post(body='a' * (MAX_LEN + 1))
        self.assertIn('Najwyżej 2048 znaków.', str(r.data['body']))

    def test_an_empty_message_is_refused(self):
        self.assertEqual(self.post(body='   ').status_code, 400)

    def test_pictures_are_refused_but_links_are_not(self):
        for body in ['![kot](kot.jpg)', 'a <img src="x.jpg"> b',
                     '\\includegraphics{wykres.png}', 'data:image/png;base64,AAA']:
            with self.subTest(body=body):
                r = self.post(body=body)
                self.assertEqual(r.status_code, 400, body)
                self.assertIn('Obrazki', str(r.data['body']))
        self.assertEqual(self.post(body='patrz [tutaj](https://fuw.edu.pl)').status_code, 201)
        self.assertEqual(self.post(body='patrz https://fuw.edu.pl/a?b=1 sam').status_code, 201)

    def test_five_links_pass_and_six_do_not(self):
        five = ' '.join(f'https://fuw.edu.pl/{i}' for i in range(5))
        self.assertEqual(self.post(body=five).status_code, 201)
        r = self.post(body=five + ' https://fuw.edu.pl/6')
        self.assertEqual(r.status_code, 400)
        self.assertIn('Za dużo linków.', str(r.data['body']))

    def test_the_honeypot_stops_a_bot(self):
        r = self.post(body='kup tanie zegarki', website='http://spam.example')
        self.assertEqual(r.status_code, 400)
        self.assertIn('Spam?', str(r.data['website']))
        self.assertEqual(Message.objects.count(), 0)

    def test_latex_is_kept_as_written(self):
        r = self.post(body='$\\int_0^1 x^2\\,dx = 1/3$', format='latex')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['format'], 'latex')
        self.assertIn('\\int', r.data['body'])

    def test_the_address_is_hashed_not_stored(self):
        # REMOTE_ADDR goes to the client as an extra, never into the posted data
        self.client.post(URL, {'body': 'skąd ja jestem'}, REMOTE_ADDR='198.51.100.7')
        self.client.post(URL, {'body': 'i jeszcze raz'}, REMOTE_ADDR='198.51.100.7')
        self.client.post(URL, {'body': 'a to ktoś inny'}, REMOTE_ADDR='203.0.113.9')
        first, second, other = Message.objects.order_by('id')
        self.assertEqual(len(first.ip_hash), 64)
        self.assertNotIn('198.51.100', first.ip_hash)
        self.assertEqual(first.ip_hash, second.ip_hash)   # same visitor, traceable
        self.assertNotEqual(first.ip_hash, other.ip_hash)  # different one, distinguishable


class ListTests(Base):
    def seed(self, n=130):
        return [Message.objects.create(nick='ktoś', body=f'wiadomość {i}') for i in range(n)]

    def test_newest_first_default_page_of_50_with_a_full_count(self):
        self.seed(130)
        r = self.client.get(URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['count'], 130)
        self.assertEqual(len(r.data['results']), 50)
        self.assertEqual(r.data['results'][0]['body'], 'wiadomość 129')
        ids = [m['id'] for m in r.data['results']]
        self.assertEqual(ids, sorted(ids, reverse=True))
        self.assertEqual(r.data['latest_id'], max(ids))

    def test_limit_is_honoured_up_to_100(self):
        self.seed(130)
        self.assertEqual(len(self.client.get(URL + '?limit=10').data['results']), 10)
        self.assertEqual(len(self.client.get(URL + '?limit=100').data['results']), 100)
        # asking for more than the maximum quietly gets the maximum, not an error
        self.assertEqual(len(self.client.get(URL + '?limit=500').data['results']), 100)

    def test_before_walks_backwards(self):
        msgs = self.seed(130)
        first_page = self.client.get(URL + '?limit=100').data['results']
        oldest_shown = first_page[-1]['id']
        older = self.client.get(f'{URL}?before={oldest_shown}').data['results']
        self.assertEqual(len(older), 30)
        self.assertTrue(all(m['id'] < oldest_shown for m in older))
        self.assertEqual(older[-1]['id'], msgs[0].pk)

    def test_since_returns_only_what_is_new(self):
        self.seed(3)
        latest = self.client.get(URL).data['latest_id']
        fresh = Message.objects.create(nick='ktoś', body='nowa')
        r = self.client.get(f'{URL}?since={latest}')
        self.assertEqual([m['id'] for m in r.data['results']], [fresh.pk])
        self.assertEqual(self.client.get(f'{URL}?since={fresh.pk}').data['results'], [])

    def test_a_nonsense_cursor_does_not_break_the_page(self):
        self.seed(3)
        self.assertEqual(self.client.get(URL + '?before=abc&limit=zzz').status_code, 200)


class HidingTests(Base):
    def setUp(self):
        super().setUp()
        self.msg = Message.objects.create(nick='ktoś', body='coś niemiłego')
        self.other = Message.objects.create(nick='ktoś', body='coś miłego')

    def test_hidden_messages_are_invisible_to_the_public(self):
        self.msg.is_hidden = True
        self.msg.save()
        r = self.client.get(URL)
        self.assertEqual(r.data['count'], 1)
        self.assertEqual([m['id'] for m in r.data['results']], [self.other.pk])
        # even asking for them: include_hidden is a moderator's switch, not a query param
        self.assertEqual(len(self.client.get(URL + '?include_hidden=1').data['results']), 1)

    def test_staff_can_ask_to_see_them(self):
        self.msg.is_hidden = True
        self.msg.save()
        self.client.force_authenticate(self.staff)
        r = self.client.get(URL + '?include_hidden=1')
        self.assertEqual(r.data['count'], 2)
        hidden = [m for m in r.data['results'] if m['id'] == self.msg.pk][0]
        self.assertTrue(hidden['is_hidden'])
        self.assertTrue(hidden['can_hide'])

    def test_a_plain_user_cannot_hide(self):
        self.client.force_authenticate(self.user)
        r = self.client.post(f'{URL}{self.msg.pk}/hide/')
        self.assertEqual(r.status_code, 403)
        self.msg.refresh_from_db()
        self.assertFalse(self.msg.is_hidden)

    def test_can_hide_is_false_for_everybody_else(self):
        self.assertFalse(self.client.get(URL).data['results'][0]['can_hide'])
        self.client.force_authenticate(self.user)
        self.assertFalse(self.client.get(URL).data['results'][0]['can_hide'])

    def test_staff_hides_and_restores(self):
        self.client.force_authenticate(self.staff)
        r = self.client.post(f'{URL}{self.msg.pk}/hide/')
        self.assertEqual(r.status_code, 200, r.data)
        self.msg.refresh_from_db()
        self.assertTrue(self.msg.is_hidden)
        self.assertEqual(self.msg.hidden_by, self.staff)

        r = self.client.post(f'{URL}{self.msg.pk}/restore/')
        self.assertEqual(r.status_code, 200, r.data)
        self.msg.refresh_from_db()
        self.assertFalse(self.msg.is_hidden)
        self.assertIsNone(self.msg.hidden_by)

    def test_hiding_something_that_is_not_there(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.post(f'{URL}999999/hide/').status_code, 404)


class FeedTests(Base):
    def test_rss_is_xml_and_carries_the_messages(self):
        Message.objects.create(nick='Zdzisław', body='pierwsza wiadomość na czacie')
        Message.objects.create(nick='Ukryty', body='tego nie ma', is_hidden=True)
        r = self.client.get(URL + 'rss/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('xml', r['Content-Type'])
        body = r.content.decode()
        self.assertIn('fuw.lol — czat', body)
        self.assertIn('Zdzis', body)
        self.assertIn('pierwsza wiadomość na czacie', body)
        self.assertIn('/czat#m', body)
        self.assertNotIn('tego nie ma', body)


class ThrottleTests(Base):
    def test_a_guest_runs_out_of_turns(self):
        # THROTTLE_RATES is a class attribute read at request time, so override_settings
        # never reaches it — the dict itself has to be patched.
        rates = dict(SimpleRateThrottle.THROTTLE_RATES, board_anon='2/hour')
        with patch.object(SimpleRateThrottle, 'THROTTLE_RATES', rates):
            self.assertEqual(self.post(body='raz').status_code, 201)
            self.assertEqual(self.post(body='dwa').status_code, 201)
            self.assertEqual(self.post(body='trzy').status_code, 429)
        self.assertEqual(Message.objects.count(), 2)

    def test_a_logged_in_writer_has_their_own_budget(self):
        rates = dict(SimpleRateThrottle.THROTTLE_RATES, board_anon='1/hour', board_user='5/hour')
        with patch.object(SimpleRateThrottle, 'THROTTLE_RATES', rates):
            self.assertEqual(self.post(body='gość raz').status_code, 201)
            self.assertEqual(self.post(body='gość dwa').status_code, 429)
            self.client.force_authenticate(self.user)
            for i in range(3):
                self.assertEqual(self.post(body=f'zalogowany {i}').status_code, 201)


class ReportTests(Base):
    """Reports: who may send one, when three trusted ones hide a message on their own, and
    what a moderator's verdict afterwards does to reputation."""

    def setUp(self):
        super().setUp()
        self.author = User.objects.create_user('autor', 'a@x.pl', 'haslo12345')
        self.msg = Message.objects.create(author=self.author, nick='autor', body='coś')
        self.trusted = [make_trusted(f'zaufany{i}') for i in range(3)]

    def report(self, msg, **data):
        data.setdefault('reason', 'offensive')
        return self.client.post(f'{URL}{msg.pk}/report/', data)

    def test_a_guest_may_report(self):
        r = self.report(self.msg)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Report.objects.count(), 1)
        self.assertIsNone(Report.objects.get().reporter)

    def test_an_unknown_reason_is_refused(self):
        r = self.report(self.msg, reason='sabotaż')
        self.assertEqual(r.status_code, 400)

    def test_the_author_cannot_report_their_own_message(self):
        self.client.force_authenticate(self.author)
        r = self.report(self.msg)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Report.objects.count(), 0)

    def test_a_signed_in_user_cannot_report_the_same_message_twice(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.report(self.msg).status_code, 201)
        r = self.report(self.msg)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Report.objects.count(), 1)

    def test_guest_reports_never_auto_hide_however_many(self):
        for _ in range(5):
            self.client.force_authenticate(None)
            r = self.report(self.msg)
            self.assertEqual(r.status_code, 201)
        self.msg.refresh_from_db()
        self.assertFalse(self.msg.is_hidden)

    def test_untrusted_signed_in_reports_do_not_count_toward_the_quorum(self):
        for i in range(3):
            u = User.objects.create_user(f'plain{i}', f'p{i}@x.pl', 'haslo12345')
            self.client.force_authenticate(u)
            self.assertEqual(self.report(self.msg).status_code, 201)
        self.msg.refresh_from_db()
        self.assertFalse(self.msg.is_hidden)

    def test_three_distinct_trusted_reports_auto_hide(self):
        for i, u in enumerate(self.trusted[:2]):
            self.client.force_authenticate(u)
            self.report(self.msg)
            self.msg.refresh_from_db()
            self.assertFalse(self.msg.is_hidden, f'should not hide after {i + 1} trusted reports')
        self.client.force_authenticate(self.trusted[2])
        r = self.report(self.msg)
        self.assertEqual(r.status_code, 201, r.data)
        self.msg.refresh_from_db()
        self.assertTrue(self.msg.is_hidden)
        self.assertIsNone(self.msg.hidden_by)  # the reports did this, not a moderator

    def test_a_moderators_confirm_rewards_the_trusted_reporters_but_not_the_moderator(self):
        self.client.force_authenticate(self.trusted[0])
        self.report(self.msg)  # this reporter is ALSO the confirming moderator below
        for u in self.trusted[1:]:
            self.client.force_authenticate(u)
            self.report(self.msg)
        self.msg.refresh_from_db()
        self.assertTrue(self.msg.is_hidden)

        self.client.force_authenticate(self.trusted[0])
        r = self.client.post(f'{URL}{self.msg.pk}/hide/')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(Report.objects.filter(message=self.msg).first().resolved)
        self.assertTrue(all(rep.upheld for rep in Report.objects.filter(message=self.msg)))
        self.trusted[0].profile.refresh_from_db()
        self.trusted[1].profile.refresh_from_db()
        self.trusted[2].profile.refresh_from_db()
        self.assertEqual(self.trusted[0].profile.reputation, 0)   # excluded: also the actor
        self.assertEqual(self.trusted[1].profile.reputation, 1)
        self.assertEqual(self.trusted[2].profile.reputation, 1)

    def test_a_restore_penalises_the_trusted_reporters(self):
        for u in self.trusted:
            self.client.force_authenticate(u)
            self.report(self.msg)
        self.msg.refresh_from_db()
        self.assertTrue(self.msg.is_hidden)

        self.client.force_authenticate(self.staff)
        r = self.client.post(f'{URL}{self.msg.pk}/restore/')
        self.assertEqual(r.status_code, 200, r.data)
        for u in self.trusted:
            u.profile.refresh_from_db()
            self.assertEqual(u.profile.reputation, -1)
        self.assertFalse(any(rep.upheld for rep in Report.objects.filter(message=self.msg)))

    def test_flagged_query_param_lists_only_reported_messages_for_moderators(self):
        other = Message.objects.create(nick='x', body='inna wiadomość')
        self.report(self.msg)
        self.client.force_authenticate(self.staff)
        r = self.client.get(URL + '?flagged=1')
        ids = [m['id'] for m in r.data['results']]
        self.assertIn(self.msg.pk, ids)
        self.assertNotIn(other.pk, ids)

    def test_flagged_is_ignored_for_non_moderators(self):
        self.report(self.msg)
        r = self.client.get(URL + '?flagged=1')  # anonymous
        ids = [m['id'] for m in r.data['results']]
        self.assertIn(self.msg.pk, ids)  # not filtered — the switch is a moderator's only
        self.assertIsNone(r.data['results'][0]['open_reports'])  # and the count is hidden too
