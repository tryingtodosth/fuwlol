from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from . import rules
from .models import Ballot, Member, MemberAction, Participation, Poll, PublishKey, StatusEntry, Vote, hash_secret


def make_member(email, name=None, role=Member.CZLONEK, affiliation=Member.STUDENT, approved=None, **kw):
    m = Member.objects.create(email=email, name=name or email.split('@')[0], status=Member.MEMBER, role=role,
                              affiliation=affiliation, email_confirmed_at=timezone.now(),
                              approved_at=approved or timezone.now() - timedelta(days=30), **kw)
    return m


def client_for(member):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION='Kolo ' + rules.new_session(member))
    return c


def link_token(body):
    return body.split('token=')[1].split()[0]


class Base(TestCase):
    def setUp(self):
        cache.clear()


class MajorityTests(TestCase):
    """The arithmetic the module exists for. An abstention counts in the denominator for every
    majority except the simple one."""

    def o(self, counts, majority, kind=Poll.UCHWALA, options=rules.YES_NO):
        return rules.outcome(kind, options, counts, majority)[0]

    def test_simple_ignores_abstentions(self):
        self.assertTrue(self.o([3, 2, 10], 'zwykla'))
        self.assertFalse(self.o([2, 2, 0], 'zwykla'))

    def test_absolute_counts_abstentions(self):
        self.assertFalse(self.o([5, 0, 5], 'bezwzgledna'))
        self.assertTrue(self.o([6, 0, 5], 'bezwzgledna'))

    def test_qualified(self):
        self.assertTrue(self.o([6, 3, 0], '2/3'))
        self.assertFalse(self.o([6, 2, 2], '2/3'))
        self.assertTrue(self.o([3, 2, 0], '3/5'))
        self.assertTrue(self.o([3, 1, 1], '3/5'))  # 3 of 5, abstention counted
        self.assertFalse(self.o([2, 1, 1], '3/5'))
        self.assertFalse(self.o([0, 0, 0], '2/3'))

    def test_election_single_candidate(self):
        opts = rules.default_options(Poll.WYBORY, ['Ala'])
        self.assertEqual(opts, ['Ala', 'przeciw', 'wstrzymuję się'])
        self.assertEqual(rules.outcome(Poll.WYBORY, opts, [3, 1, 2], 'bezwzgledna')[:2], (False, None))
        self.assertEqual(rules.outcome(Poll.WYBORY, opts, [4, 1, 2], 'bezwzgledna')[:2], (True, 'Ala'))

    def test_election_runoff_names_top_two(self):
        opts = rules.default_options(Poll.WYBORY, ['Ala', 'Bob', 'Cyp'])
        passed, winner, note = rules.outcome(Poll.WYBORY, opts, [4, 3, 2, 1], 'bezwzgledna')
        self.assertFalse(passed)
        self.assertIn('Ala, Bob', note)


class MembershipTests(Base):
    def join(self, email, affiliation='student', name='Jan Kowalski'):
        return APIClient().post('/api/kolo/join/', {'email': email, 'name': name, 'affiliation': affiliation,
                                                    'agreed_text_version': rules.CONSENT_VERSION}, format='json')

    def test_join_says_pending_and_is_no_oracle(self):
        r1 = self.join('jan@student.uw.edu.pl')
        r2 = self.join('jan@student.uw.edu.pl')
        self.assertEqual(r1.status_code, 202)
        self.assertEqual(r1.json(), r2.json())
        self.assertIn('Oczekujesz na zatwierdzenie', r1.json()['detail'])
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(Member.objects.get().status, Member.PENDING_EMAIL)

    def test_join_requires_consent(self):
        r = APIClient().post('/api/kolo/join/', {'email': 'a@student.uw.edu.pl', 'name': 'Ala Kot', 'affiliation': 'student'},
                             format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Member.objects.exists())

    def test_dead_student_domain_is_refused_with_the_right_one(self):
        r = self.join('Z.Iwan@stud.uw.edu.pl')
        self.assertEqual(r.status_code, 400)
        self.assertIn('z.iwan@student.uw.edu.pl', r.json()['email'][0])
        r = APIClient().post('/api/kolo/login/', {'email': 'z.iwan@stud.uw.edu.pl'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Member.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_link_confirms_then_waits_for_approval_by_default(self):
        self.join('jan@student.uw.edu.pl')
        r = APIClient().post('/api/kolo/link/', {'token': link_token(mail.outbox[0].body)}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['member']['status'], Member.PENDING_APPROVAL)
        again = APIClient().post('/api/kolo/link/', {'token': link_token(mail.outbox[0].body)}, format='json')
        self.assertEqual(again.status_code, 400)  # single use

    @override_settings(FUWLOL_KOLO_AUTO_ADMIT=True)
    def test_auto_admit_student_address_only(self):
        self.join('jan@student.uw.edu.pl')
        self.join('ewa@fuw.edu.pl', name='Ewa Nowak')
        a = APIClient().post('/api/kolo/link/', {'token': link_token(mail.outbox[0].body)}, format='json').json()
        b = APIClient().post('/api/kolo/link/', {'token': link_token(mail.outbox[1].body)}, format='json').json()
        self.assertEqual((a['member']['status'], a['member']['role']), (Member.MEMBER, Member.CZLONEK))
        self.assertEqual(b['member']['status'], Member.PENDING_APPROVAL)

    def test_inny_and_non_uw_are_sympatyk_at_most(self):
        m = Member.objects.create(email='x@fuw.edu.pl', name='Pracownik', affiliation=Member.INNY,
                                  status=Member.PENDING_APPROVAL, email_confirmed_at=timezone.now())
        self.assertIsNotNone(rules.admission_problem(m, Member.CZLONEK))
        self.assertIsNone(rules.admission_problem(m, Member.SYMPATYK))
        g = Member.objects.create(email='x@gmail.com', name='Gość', status=Member.PENDING_APPROVAL,
                                  email_confirmed_at=timezone.now())
        self.assertIsNotNone(rules.admission_problem(g, Member.CZLONEK))

    def test_doktorant_cap(self):
        make_member('s1@student.uw.edu.pl')
        make_member('d1@student.uw.edu.pl', affiliation=Member.DOKTORANT)
        d2 = Member.objects.create(email='d2@student.uw.edu.pl', name='D2', affiliation=Member.DOKTORANT,
                                   status=Member.PENDING_APPROVAL, email_confirmed_at=timezone.now())
        self.assertIn('połowę', rules.admission_problem(d2, Member.CZLONEK))  # 2 of 3 would be doktoranci
        make_member('s2@student.uw.edu.pl')
        self.assertIsNone(rules.admission_problem(d2, Member.CZLONEK))  # 2 of 4

    def test_manager_decides_and_refusal_needs_reason(self):
        boss = make_member('boss@student.uw.edu.pl', can_manage=True)
        m = Member.objects.create(email='k@student.uw.edu.pl', name='Kandydat', status=Member.PENDING_APPROVAL,
                                  email_confirmed_at=timezone.now())
        c = client_for(boss)
        r = c.post(f'/api/kolo/members/{m.pk}/decide/', {'decision': 'reject'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = c.post(f'/api/kolo/members/{m.pk}/decide/', {'decision': 'admit', 'role': 'czlonek'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], Member.MEMBER)
        self.assertEqual(MemberAction.objects.filter(member=m, action='admit', actor=boss).count(), 1)

    def test_non_manager_cannot_list_members(self):
        c = client_for(make_member('a@student.uw.edu.pl'))
        self.assertEqual(c.get('/api/kolo/members/').status_code, 403)

    def test_invite_is_approval(self):
        boss = make_member('boss@student.uw.edu.pl', can_manage=True)
        r = client_for(boss).post('/api/kolo/invite/', {'email': 'Nowa@Student.UW.edu.pl', 'name': 'Nowa Osoba',
                                                        'affiliation': 'student', 'role': 'czlonek'}, format='json')
        self.assertEqual(r.status_code, 201)
        r = APIClient().post('/api/kolo/link/', {'token': link_token(mail.outbox[-1].body)}, format='json')
        self.assertEqual(r.json()['member']['status'], Member.MEMBER)
        self.assertEqual(Member.objects.get(email='nowa@student.uw.edu.pl').role, Member.CZLONEK)

    def test_archive_token_opens_nothing_here(self):
        u = User.objects.create_user('arch', password='x' * 12)
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION='Token ' + Token.objects.create(user=u).key)
        self.assertEqual(c.get('/api/kolo/me/').status_code, 401)

    def test_kolo_session_opens_nothing_in_archive(self):
        c = client_for(make_member('a@student.uw.edu.pl'))
        self.assertIn(c.get('/api/auth/me/').status_code, (401, 403))


class PollTests(Base):
    def setUp(self):
        super().setUp()
        self.boss = make_member('boss@student.uw.edu.pl', name='Boss', can_manage=True)
        self.a = make_member('a@student.uw.edu.pl', name='Ala')
        self.b = make_member('b@student.uw.edu.pl', name='Bob')
        self.c = make_member('c@student.uw.edu.pl', name='Cyp')

    def poll(self, mode=Poll.JAWNE, opened=True, **kw):
        now = timezone.now()
        opens = now - timedelta(hours=1) if opened else now + timedelta(days=8)
        defaults = dict(title='w sprawie testu', body='Uchwala się test.', mode=mode, options=list(rules.YES_NO),
                        status=Poll.ANNOUNCED, opens_at=opens, closes_at=opens + timedelta(hours=48),
                        announced_at=now - timedelta(days=8), created_by=self.boss)
        defaults.update(kw)
        return Poll.objects.create(**defaults)

    def close(self, p):
        p.opens_at = timezone.now() - timedelta(days=3)
        p.closes_at = timezone.now() - timedelta(minutes=1)
        p.save()

    def test_announce_rules(self):
        now = timezone.now()
        p = Poll.objects.create(title='t', body='b', options=list(rules.YES_NO), opens_at=now + timedelta(days=1),
                                closes_at=now + timedelta(days=2), created_by=self.boss)
        self.assertIn('48', rules.announce_problem(p))
        p.closes_at = p.opens_at + timedelta(hours=48)
        self.assertIn('7 dni', rules.announce_problem(p))
        p.trial = True
        self.assertIsNone(rules.announce_problem(p))
        p.trial, p.organ = False, Poll.ZARZAD
        self.assertIn('2 dni', rules.announce_problem(p))  # one day is too little even for the Zarząd
        p.opens_at, p.closes_at = now + timedelta(days=3), now + timedelta(days=5)
        self.assertIsNone(rules.announce_problem(p))  # Zarząd: two days' notice

    def test_announce_mails_voting_members(self):
        now = timezone.now()
        p = Poll.objects.create(title='t', body='b', options=list(rules.YES_NO), opens_at=now + timedelta(days=8),
                                closes_at=now + timedelta(days=10), created_by=self.boss)
        make_member('s@gmail.com', role=Member.SYMPATYK)
        r = client_for(self.boss).post(f'/api/kolo/polls/{p.pk}/announce/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(sorted(m.to[0] for m in mail.outbox),
                         sorted(['boss@student.uw.edu.pl', 'a@student.uw.edu.pl', 'b@student.uw.edu.pl', 'c@student.uw.edu.pl']))

    def test_open_vote_once_and_results_hidden_until_close(self):
        p = self.poll()
        ca = client_for(self.a)
        self.assertEqual(ca.post(f'/api/kolo/polls/{p.pk}/vote/', {'option': 0}, format='json').status_code, 201)
        r = ca.post(f'/api/kolo/polls/{p.pk}/vote/', {'option': 1}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIsNone(ca.get(f'/api/kolo/polls/{p.pk}/').json()['result'])
        client_for(self.b).post(f'/api/kolo/polls/{p.pk}/vote/', {'option': 0}, format='json')
        self.close(p)
        d = ca.get(f'/api/kolo/polls/{p.pk}/').json()
        self.assertEqual(d['result']['counts'], [2, 0, 0])
        self.assertTrue(d['result']['quorum'])  # 2 of 4
        self.assertTrue(d['result']['passed'])
        self.assertEqual([v['name'] for v in d['named_votes']], ['Ala', 'Bob'])

    def test_quorum(self):
        p = self.poll()
        client_for(self.a).post(f'/api/kolo/polls/{p.pk}/vote/', {'option': 0}, format='json')
        self.close(p)
        r = rules.tally(p)
        self.assertFalse(r['quorum'])
        self.assertFalse(r['passed'])

    def test_admitted_after_opening_cannot_vote(self):
        p = self.poll()
        late = make_member('late@student.uw.edu.pl', approved=timezone.now())
        r = client_for(late).post(f'/api/kolo/polls/{p.pk}/vote/', {'option': 0}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('§ 10a ust. 2', r.json()['detail'])

    def test_secret_vote_keeps_no_link(self):
        p = self.poll(mode=Poll.TAJNE)
        for m, o in ((self.a, 0), (self.b, 1), (self.c, 0)):
            self.assertEqual(client_for(m).post(f'/api/kolo/polls/{p.pk}/vote/', {'option': o}, format='json').status_code, 201)
        self.assertEqual(Participation.objects.filter(poll=p).count(), 3)
        self.assertFalse(Vote.objects.filter(poll=p).exists())
        field_names = {f.name for f in Ballot._meta.get_fields()}
        self.assertEqual(field_names, {'id', 'poll', 'option'})
        self.assertEqual({f.name for f in Participation._meta.get_fields()}, {'id', 'poll', 'member'})
        before = set(Ballot.objects.filter(poll=p).values_list('id', flat=True))
        self.close(p)
        d = client_for(self.a).get(f'/api/kolo/polls/{p.pk}/').json()
        self.assertEqual(d['result']['counts'], [2, 1, 0])
        self.assertIsNone(d['named_votes'])
        after = set(Ballot.objects.filter(poll=p).values_list('id', flat=True))
        self.assertFalse(before & after)  # re-written with fresh keys after the close
        self.assertEqual(rules.tally(p)['counts'], [2, 1, 0])  # and only once

    def test_sympatyk_and_stranger_see_nothing(self):
        p = self.poll()
        s = make_member('s@gmail.com', role=Member.SYMPATYK)
        self.assertEqual(client_for(s).get(f'/api/kolo/polls/{p.pk}/').status_code, 404)
        self.assertEqual(APIClient().get(f'/api/kolo/polls/{p.pk}/').status_code, 404)
        self.assertEqual(client_for(s).get('/api/kolo/polls/').json(), [])

    def test_zarzad_poll_only_for_zarzad(self):
        self.a.zarzad = True
        self.a.save()
        p = self.poll(organ=Poll.ZARZAD)
        self.assertEqual(client_for(self.b).get(f'/api/kolo/polls/{p.pk}/').status_code, 404)
        self.assertEqual(client_for(self.a).post(f'/api/kolo/polls/{p.pk}/vote/', {'option': 0}, format='json').status_code, 201)
        self.close(p)
        self.assertEqual(rules.tally(p)['eligible'], 1)

    def test_one_fifth_moves_to_meeting(self):
        p = self.poll(opened=False)
        r = client_for(self.a).post(f'/api/kolo/polls/{p.pk}/object/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], Poll.MOVED)  # 1 of 4 members ≥ 1/5

    def test_deliberation(self):
        p = self.poll(opened=False)
        c = client_for(self.a)
        self.assertEqual(c.post(f'/api/kolo/polls/{p.pk}/comments/', {'body': 'Jestem za.'}, format='json').status_code, 201)
        self.assertEqual([x['body'] for x in c.get(f'/api/kolo/polls/{p.pk}/comments/').json()], ['Jestem za.'])
        self.close(p)
        self.assertEqual(c.post(f'/api/kolo/polls/{p.pk}/comments/', {'body': 'Za późno.'}, format='json').status_code, 400)

    def test_manager_creates_election_with_forced_absolute_majority(self):
        now = timezone.now()
        r = client_for(self.boss).post('/api/kolo/polls/', {
            'organ': 'walne', 'kind': 'wybory', 'mode': 'tajne', 'majority': 'zwykla', 'title': 'wybór Prezesa',
            'body': 'Wybór Prezesa Koła AI.', 'candidates': ['Ala', 'Bob'],
            'opens_at': (now + timedelta(days=8)).isoformat(), 'closes_at': (now + timedelta(days=10)).isoformat()}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['majority'], 'bezwzgledna')
        self.assertEqual(r.json()['options'], ['Ala', 'Bob', 'wstrzymuję się'])

    def test_protocol_lists_voters(self):
        p = self.poll(mode=Poll.TAJNE)
        client_for(self.a).post(f'/api/kolo/polls/{p.pk}/vote/', {'option': 0}, format='json')
        client_for(self.b).post(f'/api/kolo/polls/{p.pk}/vote/', {'option': 0}, format='json')
        self.close(p)
        md = client_for(self.boss).get(f'/api/kolo/polls/{p.pk}/protocol/').json()['markdown']
        self.assertIn('1. Ala', md)
        self.assertIn('2. Bob', md)
        self.assertNotIn('Cyp', md)


class StatusTests(Base):
    def test_publish_with_key_and_read_publicly(self):
        PublishKey.objects.create(name='claude', key_hash=hash_secret('sekret'))
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION='KoloKey sekret')
        r = c.post('/api/kolo/status/', {'title': 'Zebranie założycielskie', 'body': 'Odbyło się.'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(StatusEntry.objects.get().source, 'klucz: claude')
        self.assertEqual(APIClient().get('/api/kolo/status/').json()[0]['title'], 'Zebranie założycielskie')
        c.post(f'/api/kolo/status/{r.json()["id"]}/withdraw/')
        self.assertEqual(APIClient().get('/api/kolo/status/').json(), [])

    def test_member_without_manage_cannot_publish(self):
        c = client_for(make_member('a@student.uw.edu.pl'))
        self.assertEqual(c.post('/api/kolo/status/', {'title': 'x'}, format='json').status_code, 403)

    def test_bad_key_is_401(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION='KoloKey zly')
        self.assertEqual(c.post('/api/kolo/status/', {'title': 'x'}, format='json').status_code, 401)


class RetentionTests(Base):
    def test_unconfirmed_go_after_30_days(self):
        from django.core.management import call_command
        old = Member.objects.create(email='old@x.pl', name='Old')
        Member.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=31))
        fresh = Member.objects.create(email='new@x.pl', name='New')
        kept = make_member('m@student.uw.edu.pl')
        Member.objects.filter(pk=kept.pk).update(created_at=timezone.now() - timedelta(days=90))
        call_command('kolo_forget_unconfirmed', stdout=open('/dev/null', 'w'))
        self.assertEqual(set(Member.objects.values_list('email', flat=True)), {'new@x.pl', 'm@student.uw.edu.pl'})


class FounderTests(Base):
    def put(self, c, **kw):
        data = {'phone': '+48 600 100 200', 'kierunek': 'Fizyka', 'etap': '2. rok I st.', 'nr_albumu': '445566',
                'agreed_text_version': rules.FOUNDER_CONSENT_VERSION}
        data.update(kw)
        return c.put('/api/kolo/me/founder/', data, format='json')

    def test_pending_student_files_data_and_manager_lists_it(self):
        m = Member.objects.create(email='zal@student.uw.edu.pl', name='Anna Zet', status=Member.PENDING_APPROVAL,
                                  email_confirmed_at=timezone.now())
        r = self.put(client_for(m))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['nr_albumu'], '445566')
        boss = make_member('boss@student.uw.edu.pl', name='Boss Adam', can_manage=True)
        rows = client_for(boss).get('/api/kolo/founders/').json()
        self.assertEqual([x['name'] for x in rows], ['Anna Zet'])
        self.assertEqual(rows[0]['email'], 'zal@student.uw.edu.pl')

    def test_validation_and_consent(self):
        m = make_member('a@student.uw.edu.pl')
        c = client_for(m)
        self.assertEqual(self.put(c, nr_albumu='12ab').status_code, 400)
        self.assertEqual(self.put(c, phone='12').status_code, 400)
        self.assertEqual(self.put(c, agreed_text_version='').status_code, 400)

    def test_inny_or_non_uw_cannot_be_founder(self):
        g = Member.objects.create(email='x@gmail.com', name='Gość', status=Member.PENDING_APPROVAL,
                                  email_confirmed_at=timezone.now())
        self.assertEqual(self.put(client_for(g)).status_code, 400)
        s = make_member('s@fuw.edu.pl', affiliation=Member.INNY, role=Member.SYMPATYK)
        self.assertEqual(self.put(client_for(s)).status_code, 400)

    def test_only_managers_list_and_person_can_withdraw(self):
        m = make_member('a@student.uw.edu.pl')
        c = client_for(m)
        self.put(c)
        self.assertEqual(c.get('/api/kolo/founders/').status_code, 403)
        self.assertEqual(APIClient().get('/api/kolo/founders/').status_code, 403)
        c.delete('/api/kolo/me/founder/')
        self.assertEqual(c.get('/api/kolo/me/founder/').json()['nr_albumu'], '')


class SettingTests(Base):
    def test_default_then_manager_edits(self):
        info = APIClient().get('/api/kolo/info/').json()
        self.assertIn('11:00–11:40', info['texts']['founders_notice'])
        boss = make_member('boss@student.uw.edu.pl', can_manage=True)
        r = client_for(boss).put('/api/kolo/settings/founders_notice/', {'value': 'Podpisy 11:05–11:45.'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(APIClient().get('/api/kolo/info/').json()['texts']['founders_notice'], 'Podpisy 11:05–11:45.')

    def test_non_manager_and_unknown_key(self):
        m = make_member('a@student.uw.edu.pl')
        self.assertEqual(client_for(m).put('/api/kolo/settings/founders_notice/', {'value': 'x'}, format='json').status_code, 403)
        boss = make_member('boss@student.uw.edu.pl', can_manage=True)
        self.assertEqual(client_for(boss).put('/api/kolo/settings/nope/', {'value': 'x'}, format='json').status_code, 404)


NO_LINK_LINE = 'Nie chcesz więcej maili? Odpowiedz na tego maila słowem WYPISZ.'


class MailingTests(Base):
    """Unsubscribing (the link in every mailing, the one-click header, the switch on the page) and
    `kolo_mail`, which honours it."""

    def _send(self, *args):
        import io
        from django.core.management import call_command
        out = io.StringIO()
        call_command('kolo_mail', *args, '--pause', '0', stdout=out)
        return out.getvalue()

    def _file(self, text):
        import tempfile
        f = tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8')
        f.write(text)
        f.close()
        return f.name

    def test_link_unsubscribes_and_can_undo(self):
        m = make_member('a@student.uw.edu.pl')
        token = rules.unsubscribe_token(m)
        self.assertEqual(APIClient().get('/api/kolo/unsubscribe/', {'t': token}).status_code, 405)
        m.refresh_from_db()
        self.assertIsNone(m.mail_opt_out_at)
        r = APIClient().post('/api/kolo/unsubscribe/', {'token': token}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()['mail'])
        self.assertNotIn(m, rules.mailing_recipients())
        self.assertEqual(MemberAction.objects.filter(member=m, action='mail_off').count(), 1)
        APIClient().post('/api/kolo/unsubscribe/', {'token': token}, format='json')  # twice: one action
        self.assertEqual(MemberAction.objects.filter(member=m, action='mail_off').count(), 1)
        APIClient().post('/api/kolo/unsubscribe/', {'token': token, 'subscribe': True}, format='json')
        self.assertIn(m, rules.mailing_recipients())

    def test_one_click_form_post(self):
        m = make_member('a@student.uw.edu.pl')
        url = '/api/kolo/unsubscribe/?t=' + rules.unsubscribe_token(m)
        r = APIClient().post(url, 'List-Unsubscribe=One-Click', content_type='application/x-www-form-urlencoded')
        self.assertEqual(r.status_code, 200)
        m.refresh_from_db()
        self.assertIsNotNone(m.mail_opt_out_at)

    def test_forged_token_is_400(self):
        m = make_member('a@student.uw.edu.pl')
        self.assertEqual(APIClient().post('/api/kolo/unsubscribe/', {'token': f'{m.pk}:zly'}, format='json').status_code, 400)
        self.assertEqual(APIClient().post('/api/kolo/unsubscribe/', {'token': str(m.pk)}, format='json').status_code, 400)

    def test_switch_for_logged_in(self):
        m = make_member('a@student.uw.edu.pl')
        c = client_for(m)
        self.assertTrue(c.get('/api/kolo/me/').json()['mail'])
        self.assertFalse(c.put('/api/kolo/me/mail/', {'mail': False}, format='json').json()['mail'])
        self.assertTrue(c.put('/api/kolo/me/mail/', {'mail': True}, format='json').json()['mail'])
        self.assertEqual(APIClient().put('/api/kolo/me/mail/', {'mail': False}, format='json').status_code, 401)

    def test_kolo_mail_sends_only_to_the_list_each_with_own_link(self):
        a = make_member('a@student.uw.edu.pl')
        b = Member.objects.create(email='b@student.uw.edu.pl', name='B', status=Member.PENDING_APPROVAL)
        Member.objects.create(email='c@student.uw.edu.pl', name='C')  # pending_email: never confirmed
        Member.objects.create(email='l@student.uw.edu.pl', name='L', status=Member.LEFT)
        Member.objects.create(email='r@student.uw.edu.pl', name='R', status=Member.REJECTED)
        gone = make_member('d@student.uw.edu.pl')
        rules.set_mailings(gone, False, None, 'test')
        path = self._file('Temat ogłoszenia\n\nTreść.\nNie chcesz? [LINK_REZYGNACJI]\n')

        out = self._send(path)  # dry run
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn('RECIPIENTS 2', out)

        self._send(path, '--send', '--extra', 'opiekun@fuw.edu.pl', '--extra', 'd@student.uw.edu.pl')
        self.assertEqual(sorted(x.to[0] for x in mail.outbox), ['a@student.uw.edu.pl', 'b@student.uw.edu.pl', 'opiekun@fuw.edu.pl'])
        by = {x.to[0]: x for x in mail.outbox}
        self.assertEqual(by['a@student.uw.edu.pl'].subject, 'Temat ogłoszenia')
        self.assertIn(rules.unsubscribe_url(a), by['a@student.uw.edu.pl'].body)
        self.assertNotIn(rules.unsubscribe_url(a), by['b@student.uw.edu.pl'].body)
        self.assertIn(rules.unsubscribe_url(b), by['b@student.uw.edu.pl'].body)
        self.assertIn(NO_LINK_LINE, by['opiekun@fuw.edu.pl'].body)
        self.assertNotIn('[LINK_REZYGNACJI]', by['opiekun@fuw.edu.pl'].body)
        self.assertNotIn('Nie chcesz? ', by['opiekun@fuw.edu.pl'].body)
        self.assertEqual(by['a@student.uw.edu.pl'].extra_headers['List-Unsubscribe-Post'], 'List-Unsubscribe=One-Click')
        self.assertNotIn('List-Unsubscribe-Post', by['opiekun@fuw.edu.pl'].extra_headers)

    def test_kolo_mail_test_copy(self):
        make_member('a@student.uw.edu.pl')
        self._send(self._file('Temat\nTreść\n'), '--test', 'admin@fuw.lol')
        self.assertEqual([x.to for x in mail.outbox], [['admin@fuw.lol']])
        self.assertEqual(mail.outbox[0].subject, '[TEST] Temat')
