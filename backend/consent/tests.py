r"""„Jesteś tą osobą?” — the tests that matter.

The ones worth naming: the request endpoint is not an oracle (404 for an unlisted person,
202 for everything else, including the cap and the honeypot); the claimant's note never
leaves the database in an e-mail; a tightening wish is applied precautionarily ONLY from
an institutional mailbox; `no_images` hides the photographs and nothing else, including a
post that is the person's only through a nickname; a rejection restores exactly the posts
this claim hid, to the statuses they had, and does not touch a post a moderator hid for
reasons of their own; and a loosening gives back what the stricter wish took.
"""
import re
from datetime import timedelta

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from archive.models import Attachment, Category, ModerationAction, Person, Post, Report, Tag
from archive.moderation import hide_post
from archive.test_moderation import make_trusted

from . import rules
from .models import ConsentHide, PersonClaim

FUW = 'kwant.niepewny@fuw.edu.pl'
GMAIL = 'ktostam@gmail.com'
NOTE = 'To ja, ten na zdjęciu z 2009 roku, i wolałbym bez tego.'

# Throttle counters live in the shared FILE cache (backend/cachedata/) and would otherwise
# leak between tests — and in from whatever the dev server has been doing all afternoon.
LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


def token_from(body, page):
    m = re.search(page + r'\?token=([A-Za-z0-9_\-]+)', body)
    return m.group(1) if m else None


@override_settings(CACHES=LOCMEM)
class ConsentTestCase(APITestCase):
    def setUp(self):
        cache.clear()
        mail.outbox = []
        self.cat = Category.objects.create(slug='memy', name='Memy')
        self.person = Person.objects.create(slug='kwant-niepewny', degree='dr',
                                            name='Kwant Niepewny', surname='Niepewny')
        self.nick = Tag.objects.create(slug='kwant', name='Kwant')
        self.person.aliases.add(self.nick)
        self.other_person = Person.objects.create(slug='helena', name='Helena Hamiltonian')
        self.staff = User.objects.create_user('dziekan', 'dziekan@x.pl', 'haslo12345', is_staff=True)
        self.trusted = make_trusted('doktorant')
        self.plain = User.objects.create_user('student', 'student@x.pl', 'haslo12345')
        # the person's posts: a quote (no picture), a photo, a photo that is theirs only
        # through the nickname, and one post that has nothing to do with them
        self.quote = self.make_post('Cytat', people=[self.person])
        self.photo = self.make_post('Zdjęcie z korytarza', people=[self.person], image=True)
        self.nick_photo = self.make_post('Mem z Kwantem', tags=[self.nick], image=True)
        self.stranger = self.make_post('Nie o nim', people=[self.other_person], image=True)

    def make_post(self, title, *, status='published', people=(), tags=(), image=False):
        p = Post.objects.create(title=title, category=self.cat, body='treść', status=status)
        if people:
            p.people.set(people)
        if tags:
            p.tags.set(tags)
        if image:
            Attachment.objects.create(post=p, original_name='foto.png', kind='image')
        return p

    def ask(self, wish=None, email=FUW, slug=None, **extra):
        body = {'email': email, 'wish': wish or 'no_images', 'agree': True, 'note': NOTE}
        body.update(extra)
        return self.client.post(f'/api/people/{slug or self.person.slug}/claims/', body)

    def confirm_last(self):
        token = PersonClaim.objects.order_by('-id').first().token
        return self.client.post('/api/claims/confirm/', {'token': token})

    def status_of(self, post):
        post.refresh_from_db()
        return post.status


class RequestTests(ConsentTestCase):
    def test_request_sends_a_link_and_says_nothing_else(self):
        r = self.ask('no_images')
        self.assertEqual(r.status_code, 202, r.data)
        self.assertEqual(r.data, {'sent_to': 'k***@fuw.edu.pl'})
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, [FUW])
        self.assertIn('/ludzie/kwant-niepewny/potwierdz?token=', msg.body)
        self.assertIn('24 godziny', msg.body)
        claim = PersonClaim.objects.get()
        self.assertEqual((claim.status, claim.wish, claim.note), ('sent', 'no_images', NOTE))
        self.assertEqual(claim.consent_text_version, rules.CONSENT_TEXT_VERSION)
        self.assertIsNotNone(claim.requester_ip)

    def test_the_note_never_leaves_the_database_in_a_mail(self):
        """A form that mails a stranger's text to an address the same stranger chose is a
        spam relay with our domain on the envelope."""
        self.ask('no_mention')
        self.assertNotIn(NOTE, mail.outbox[0].body)
        self.assertNotIn('Nie chcę być w archiwum', mail.outbox[0].body)  # not even the wish

    def test_unknown_and_unlisted_people_answer_the_same_404(self):
        self.assertEqual(self.ask(slug='nie-ma-takiego').status_code, 404)
        Person.objects.filter(pk=self.person.pk).update(is_listed=False)
        self.assertEqual(self.ask().status_code, 404)
        self.assertEqual(len(mail.outbox), 0)

    def test_honeypot_answers_202_and_does_nothing(self):
        r = self.ask('no_images', website='https://kup-linki.example')
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.data['sent_to'], 'k***@fuw.edu.pl')
        self.assertEqual(PersonClaim.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_agreement_and_wish_are_checked(self):
        self.assertEqual(self.ask('no_images', agree=False).status_code, 400)
        self.assertEqual(self.ask('cokolwiek').status_code, 400)
        self.assertEqual(PersonClaim.objects.count(), 0)

    def test_throttle_is_three_an_hour(self):
        for i in range(3):
            self.assertEqual(self.ask('no_images', email=f'a{i}@fuw.edu.pl').status_code, 202)
        self.assertEqual(self.ask('no_images', email='a4@fuw.edu.pl').status_code, 429)

    def test_daily_cap_per_person_is_silent(self):
        """Four attempts, three mails, and the fourth caller cannot tell. (Driven through
        the rules module: the per-IP throttle would answer first over HTTP.)"""
        for i in range(3):
            rules.request_claim(self.person, f'a{i}@fuw.edu.pl', 'no_images', '')
        out = rules.request_claim(self.person, 'a4@fuw.edu.pl', 'no_images', '')
        self.assertEqual(out, {'sent_to': 'a***@fuw.edu.pl', 'sent': False})
        self.assertEqual(len(mail.outbox), 3)
        self.assertEqual(PersonClaim.objects.count(), 3)

    def test_a_second_request_from_the_same_address_replaces_the_first(self):
        self.ask('no_images')
        first = PersonClaim.objects.get().token
        self.ask('no_mention')
        claim = PersonClaim.objects.get()  # still exactly one
        self.assertEqual(claim.wish, 'no_mention')
        self.assertNotEqual(claim.token, first)
        self.assertEqual(self.client.post('/api/claims/confirm/', {'token': first}).status_code, 400)


class ConfirmTests(ConsentTestCase):
    def test_confirm_verifies_once_and_only_once(self):
        self.ask('images_ok', email=GMAIL)
        token = PersonClaim.objects.get().token
        r = self.client.post('/api/claims/confirm/', {'token': token})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['wish'], 'images_ok')
        self.assertFalse(r.data['applied'])
        self.assertIn('administracja', r.data['message'])
        claim = PersonClaim.objects.get()
        self.assertEqual(claim.status, 'verified')
        self.assertIsNotNone(claim.verified_at)
        # single use, and the same sentence for used / expired / invented
        again = self.client.post('/api/claims/confirm/', {'token': token})
        self.assertEqual(again.status_code, 400)
        self.assertEqual(again.data['detail'], rules.BAD_TOKEN)
        self.assertEqual(self.client.post('/api/claims/confirm/', {'token': 'zmyslony'}).data['detail'],
                         rules.BAD_TOKEN)

    def test_a_link_older_than_a_day_is_dead(self):
        self.ask('no_images')
        claim = PersonClaim.objects.get()
        PersonClaim.objects.filter(pk=claim.pk).update(created_at=timezone.now() - timedelta(hours=25))
        r = self.client.post('/api/claims/confirm/', {'token': claim.token})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(PersonClaim.objects.get().status, 'sent')

    def test_precaution_applies_only_from_an_institutional_mailbox(self):
        self.ask('no_images', email=GMAIL)
        self.confirm_last()
        self.assertIsNone(PersonClaim.objects.get().applied_at)
        self.assertEqual(self.status_of(self.photo), 'published')
        self.person.refresh_from_db()
        self.assertEqual(self.person.image_consent, 'unknown')

    def test_precaution_never_applies_to_the_wish_that_publishes_a_consent(self):
        """The asymmetry, stated as a test: an institutional address is enough to hide a
        photograph for a day and nowhere near enough to put a public ✓ on somebody's name."""
        self.ask('images_ok', email=FUW)
        r = self.confirm_last()
        self.assertFalse(r.data['applied'])
        self.person.refresh_from_db()
        self.assertEqual(self.person.image_consent, 'unknown')

    def test_no_images_hides_the_photographs_only_and_finds_them_through_a_nickname(self):
        Report.objects.create(post=self.photo, reason='privacy')
        self.ask('no_images', email=FUW)
        r = self.confirm_last()
        self.assertTrue(r.data['applied'])
        self.assertIn('2', r.data['message'])  # two posts, said out loud
        self.assertEqual(self.status_of(self.photo), 'hidden')
        self.assertEqual(self.status_of(self.nick_photo), 'hidden')  # theirs only via „Kwant”
        self.assertEqual(self.status_of(self.quote), 'published')    # a mention without a picture stays
        self.assertEqual(self.status_of(self.stranger), 'published')
        self.person.refresh_from_db()
        self.assertEqual(self.person.image_consent, 'refused')
        self.assertTrue(self.person.is_listed)
        # the audit line names the mechanism and not the claimant
        action = ModerationAction.objects.filter(post=self.photo, action='hide').get()
        self.assertIsNone(action.actor)
        self.assertIn('na wniosek osoby', action.reason)
        self.assertNotIn('@', action.reason)
        self.assertEqual(action.previous_status, 'published')
        self.assertTrue(Report.objects.get().resolved)  # a hide IS the answer to "take this down"
        self.assertEqual(set(ConsentHide.objects.values_list('post_id', flat=True)),
                         {self.photo.pk, self.nick_photo.pk})

    def test_no_mention_hides_everything_and_takes_the_entry_off_the_list(self):
        pending = self.make_post('Czeka w kolejce', status='pending', people=[self.person])
        self.ask('no_mention', email=FUW)
        self.confirm_last()
        for p in (self.quote, self.photo, self.nick_photo, pending):
            self.assertEqual(self.status_of(p), 'hidden', p.title)
        self.assertEqual(self.status_of(self.stranger), 'published')
        self.person.refresh_from_db()
        self.assertEqual(self.person.image_consent, 'opted_out')
        self.assertFalse(self.person.is_listed)
        # and the profile goes with it
        self.assertEqual(self.client.get(f'/api/people/{self.person.slug}/').status_code, 404)
        # a post that was in the queue remembers it was in the queue
        self.assertEqual(ConsentHide.objects.get(post=pending).previous_status, 'pending')

    def test_a_post_already_hidden_by_a_moderator_gets_no_consent_hide_row(self):
        hide_post(self.photo, self.trusted, 'bo tak')
        self.ask('no_mention', email=FUW)
        self.confirm_last()
        self.assertFalse(ConsentHide.objects.filter(post=self.photo).exists())
        self.assertEqual(ConsentHide.objects.count(), 2)  # quote + nick_photo


class DecisionTests(ConsentTestCase):
    def verified_claim(self, wish='images_ok', email=FUW):
        self.ask(wish, email=email)
        self.confirm_last()
        mail.outbox = []
        return PersonClaim.objects.order_by('-id').first()

    def decide(self, claim, decision, note=''):
        self.client.force_authenticate(self.staff)
        r = self.client.post(f'/api/claims/{claim.pk}/decide/', {'decision': decision, 'note': note})
        self.client.force_authenticate(None)
        return r

    def test_queue_is_staff_only_and_carries_the_signals(self):
        claim = self.verified_claim('images_ok', email=FUW)
        self.assertIn(self.client.get('/api/claims/queue/').status_code, (401, 403))
        for user in (self.plain, self.trusted):  # trusted is NOT staff here, on purpose
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get('/api/claims/queue/').status_code, 403)
        self.client.force_authenticate(self.staff)
        rows = self.client.get('/api/claims/queue/').data
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['id'], claim.pk)
        self.assertEqual(row['person'], {'slug': 'kwant-niepewny', 'full_name': 'dr Kwant Niepewny'})
        self.assertEqual(row['email'], FUW)  # in full: this screen's whole job is judging it
        self.assertEqual(row['wish_label'], 'Zdjęcia ze mną mogą tu być')
        self.assertEqual(row['note'], NOTE)
        self.assertEqual(row['signals'], {'domain_trusted': True, 'institution': 'Wydział Fizyki UW',
                                          'name_tokens_in_local_part': True, 'account': None,
                                          'earlier_claims': 0})

    def test_signals_are_honest_about_a_stranger(self):
        User.objects.create_user('ktos', GMAIL, 'haslo12345')
        claim = self.verified_claim('no_images', email=GMAIL)
        s = rules.signals(claim)
        self.assertEqual(s['domain_trusted'], False)
        self.assertIsNone(s['institution'])
        self.assertFalse(s['name_tokens_in_local_part'])
        self.assertEqual(s['account'], 'ktos')

    def test_approve_applies_the_wish_and_mails_a_settings_link(self):
        claim = self.verified_claim('images_ok', email=FUW)
        r = self.decide(claim, 'approve', 'Adres zgadza się ze spisem Wydziału.')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['status'], 'approved')
        self.person.refresh_from_db()
        self.assertEqual(self.person.image_consent, 'granted')
        claim.refresh_from_db()
        self.assertIsNotNone(claim.applied_at)
        self.assertEqual(claim.decided_by, self.staff)
        self.assertEqual(claim.previous_consent, 'unknown')
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn('/ludzie/kwant-niepewny/ustawienia?token=', body)
        self.assertIn('Adres zgadza się ze spisem Wydziału.', body)  # a decision carries its reason
        self.assertNotIn(NOTE, body)

    def test_a_decision_cannot_be_taken_twice(self):
        claim = self.verified_claim('images_ok')
        self.assertEqual(self.decide(claim, 'approve').status_code, 200)
        self.assertEqual(self.decide(claim, 'reject').status_code, 409)

    def test_an_unconfirmed_claim_cannot_be_approved(self):
        self.ask('images_ok')
        claim = PersonClaim.objects.get()
        r = self.decide(claim, 'approve')
        self.assertEqual(r.status_code, 409)
        self.person.refresh_from_db()
        self.assertEqual(self.person.image_consent, 'unknown')

    def test_reject_restores_exactly_what_the_claim_hid_and_nothing_else(self):
        queued = self.make_post('W kolejce', status='pending', people=[self.person])
        hide_post(self.stranger, self.trusted, 'moderator, z innego powodu')
        claim = self.verified_claim('no_mention', email=FUW)  # institutional: applied at once
        self.assertEqual(self.status_of(self.quote), 'hidden')
        r = self.decide(claim, 'reject', 'Adres nie pasuje do tej osoby.')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.status_of(self.quote), 'published')
        self.assertEqual(self.status_of(self.photo), 'published')
        self.assertEqual(self.status_of(queued), 'pending')      # back to the queue, not published
        self.assertEqual(self.status_of(self.stranger), 'hidden')  # the moderator's hide survives
        self.person.refresh_from_db()
        self.assertEqual(self.person.image_consent, 'unknown')
        self.assertTrue(self.person.is_listed)
        claim.refresh_from_db()
        self.assertEqual(claim.status, 'rejected')
        self.assertIsNone(claim.applied_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Adres nie pasuje do tej osoby.', mail.outbox[0].body)

    def test_a_looser_wish_gives_back_what_the_stricter_one_took(self):
        first = self.verified_claim('no_images', email=FUW)  # institutional: applied at once
        self.decide(first, 'approve')
        self.assertEqual(self.status_of(self.photo), 'hidden')
        # the same person writes again — they have changed their mind about photographs
        self.ask('images_ok', email=FUW)
        self.confirm_last()
        second = PersonClaim.objects.order_by('-id').first()
        self.assertEqual(self.decide(second, 'approve').status_code, 200)
        first.refresh_from_db()
        self.assertEqual(first.status, 'superseded')
        self.assertIsNone(first.applied_at)   # its precaution is no longer in force
        self.assertEqual(self.status_of(self.photo), 'published')
        self.assertEqual(self.status_of(self.nick_photo), 'published')
        self.person.refresh_from_db()
        self.assertEqual(self.person.image_consent, 'granted')
        # …and the superseded row is still there, saying what was agreed to and when
        self.assertEqual(PersonClaim.objects.count(), 2)

    def test_an_opted_out_person_is_no_longer_claimable_through_the_form(self):
        """Not a gap: `no_mention` takes the whole entry away, and the form lives on the
        entry. The way back is the settings link in their own mailbox (ManageTests)."""
        claim = self.verified_claim('no_mention', email=FUW)
        self.decide(claim, 'approve')
        self.assertEqual(self.ask('images_ok', email=FUW).status_code, 404)


    def test_tightening_then_withdrawing_gives_everything_back(self):
        """no_images → no_mention → „to jednak nie ja”. The trap this covers: the photo
        posts were hidden by the FIRST claim, which the second one supersedes — if that
        claim is not reverted on the way past, nothing can ever give them back."""
        first = self.verified_claim('no_images', email=FUW)
        self.decide(first, 'approve')
        self.assertEqual(self.status_of(self.photo), 'hidden')
        self.ask('no_mention', email=FUW)
        self.confirm_last()
        second = PersonClaim.objects.order_by('-id').first()
        self.decide(second, 'approve')
        first.refresh_from_db()
        self.assertIsNone(first.applied_at)  # exactly one claim is in force at a time
        for p in (self.quote, self.photo, self.nick_photo):
            self.assertEqual(self.status_of(p), 'hidden', p.title)
        # the person changes their mind about the whole thing
        rules.withdraw_claim(rules._rotate_manage_token(second))
        for p in (self.quote, self.photo, self.nick_photo):
            self.assertEqual(self.status_of(p), 'published', p.title)
        self.person.refresh_from_db()
        self.assertEqual(self.person.image_consent, 'unknown')
        self.assertTrue(self.person.is_listed)


class ManageTests(ConsentTestCase):
    def approved(self, wish='no_images', email=FUW):
        self.ask(wish, email=email)
        self.confirm_last()
        claim = PersonClaim.objects.order_by('-id').first()
        self.client.force_authenticate(self.staff)
        self.client.post(f'/api/claims/{claim.pk}/decide/', {'decision': 'approve'})
        self.client.force_authenticate(None)
        token = token_from(mail.outbox[-1].body, '/ludzie/kwant-niepewny/ustawienia')
        mail.outbox = []
        return claim, token

    def test_manage_state_reads_the_current_wish(self):
        _, token = self.approved('no_images')
        r = self.client.get(f'/api/claims/manage/?token={token}')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['current_wish'], 'no_images')
        self.assertEqual(r.data['email_masked'], 'k***@fuw.edu.pl')
        self.assertEqual(r.data['person']['full_name'], 'dr Kwant Niepewny')
        self.assertEqual(r.data['consent_text_version'], rules.CONSENT_TEXT_VERSION)
        self.assertEqual(self.client.get('/api/claims/manage/?token=nic').status_code, 400)

    def test_the_same_mailbox_changes_its_mind_without_a_second_review(self):
        old, token = self.approved('no_images')
        self.assertEqual(self.status_of(self.photo), 'hidden')
        r = self.client.post('/api/claims/manage/', {'token': token, 'wish': 'images_ok'})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['wish'], 'images_ok')
        self.person.refresh_from_db()
        self.assertEqual(self.person.image_consent, 'granted')
        self.assertEqual(self.status_of(self.photo), 'published')
        old.refresh_from_db()
        self.assertEqual(old.status, 'superseded')  # kept, never edited: it is the evidence
        fresh = PersonClaim.objects.order_by('-id').first()
        self.assertEqual((fresh.status, fresh.wish), ('approved', 'images_ok'))
        self.assertIsNone(fresh.decided_by)
        # the link in the mailbox still works, and now opens the new row
        self.assertEqual(self.client.get(f'/api/claims/manage/?token={token}').data['current_wish'], 'images_ok')

    def test_the_magic_link_is_the_way_back_from_an_opt_out(self):
        """no_mention → no_images through the settings link: the mentions come back, the
        photographs stay down, and the entry returns to the directory."""
        old, token = self.approved('no_mention')
        self.assertFalse(Person.objects.get(pk=self.person.pk).is_listed)
        r = self.client.post('/api/claims/manage/', {'token': token, 'wish': 'no_images'})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.status_of(self.quote), 'published')
        self.assertEqual(self.status_of(self.photo), 'hidden')
        self.assertEqual(self.status_of(self.nick_photo), 'hidden')
        self.person.refresh_from_db()
        self.assertEqual(self.person.image_consent, 'refused')
        self.assertTrue(self.person.is_listed)
        self.assertEqual(self.client.get(f'/api/people/{self.person.slug}/').status_code, 200)

    def test_withdrawal_puts_everything_back(self):
        claim, token = self.approved('no_mention')
        self.assertFalse(Person.objects.get(pk=self.person.pk).is_listed)
        r = self.client.post('/api/claims/manage/withdraw/', {'token': token})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.status_of(self.quote), 'published')
        self.person.refresh_from_db()
        self.assertEqual(self.person.image_consent, 'unknown')
        self.assertTrue(self.person.is_listed)
        claim.refresh_from_db()
        self.assertEqual(claim.status, 'withdrawn')
        self.assertEqual(self.client.get(f'/api/claims/manage/?token={token}').status_code, 400)

    def test_manage_link_is_not_an_oracle(self):
        self.approved('no_images')
        url = f'/api/people/{self.person.slug}/claims/manage-link/'
        r = self.client.post(url, {'email': FUW})
        self.assertEqual(r.status_code, 202)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/ludzie/kwant-niepewny/ustawienia?token=', mail.outbox[0].body)
        r = self.client.post(url, {'email': 'nikt@fuw.edu.pl'})
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.data['sent_to'], 'n***@fuw.edu.pl')
        self.assertEqual(len(mail.outbox), 1)  # nothing sent, nothing said

    def test_somebody_who_opted_out_can_still_ask_for_the_way_back(self):
        """`is_listed=False` hides the profile from everybody — it must not hide the door
        out of it from the person who closed it (RODO art. 7 ust. 3)."""
        self.approved('no_mention')
        self.assertEqual(self.client.get(f'/api/people/{self.person.slug}/').status_code, 404)
        self.assertEqual(self.ask('images_ok', email=FUW).status_code, 404)  # the form is gone with the entry
        r = self.client.post(f'/api/people/{self.person.slug}/claims/manage-link/', {'email': FUW})
        self.assertEqual(r.status_code, 202)
        self.assertEqual(len(mail.outbox), 1)


class RetentionTests(ConsentTestCase):
    def test_forget_claim_ips_keeps_the_evidence(self):
        from django.core.management import call_command
        from io import StringIO
        self.ask('no_images', email=FUW)
        self.confirm_last()
        claim = PersonClaim.objects.get()
        self.client.force_authenticate(self.staff)
        self.client.post(f'/api/claims/{claim.pk}/decide/', {'decision': 'approve'})
        self.client.force_authenticate(None)
        old = rules.request_claim(self.person, 'ktos@fuw.edu.pl', 'no_images', '')
        stale = PersonClaim.objects.exclude(pk=claim.pk).get()
        PersonClaim.objects.update(created_at=timezone.now() - timedelta(days=400),
                                   requester_ip='198.51.100.7', requester_user_agent='curl')
        call_command('forget_claim_ips', stdout=StringIO())
        stale.refresh_from_db()
        claim.refresh_from_db()
        self.assertIsNone(stale.requester_ip)
        self.assertEqual(stale.requester_user_agent, '')
        self.assertEqual(claim.requester_ip, '198.51.100.7')  # approved: this IS the evidence
        self.assertTrue(old['sent'])
