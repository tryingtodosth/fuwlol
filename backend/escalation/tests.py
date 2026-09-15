"""Escalation to NASK: adversarial by design. The premise of this app is that a small,
technically sophisticated crowd (see the brief that started it) will try exactly the moves
below — IDOR by guessable id, "staff surely counts as admin", racing the decide endpoint,
re-reading content through a side door once it is supposed to be gone. Every test here is
one of those moves, made, and checked against the wall it should hit."""
import tempfile

from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import TrustedDomain
from archive.models import Category, Post
from board.models import Message
from .models import Escalation
from .services import create_escalation, decide_escalation


def make_trusted(username):
    u = User.objects.create_user(username, f'{username}@fuw.edu.pl', 'haslo12345')
    dom, _ = TrustedDomain.objects.get_or_create(domain='fuw.edu.pl', defaults={'institution': 'FUW', 'kind': 'fuw'})
    p = u.profile
    p.affiliation_email, p.affiliation_domain, p.verified_at = f'{username}@fuw.edu.pl', dom, timezone.now()
    p.save()
    return u


class Base(APITestCase):
    def setUp(self):
        # A fresh directory per TEST, not per class: the class-level decorator form
        # evaluates tempfile.mkdtemp() once at import time, and every test's Escalation
        # reuses pk=1 (each test's transaction rolls back, so SQLite's rowid restarts) —
        # which would collide on the same on-disk evidence directory across tests.
        override = override_settings(MEDIA_ROOT=tempfile.mkdtemp(), EVIDENCE_ROOT=tempfile.mkdtemp())
        override.enable()
        self.addCleanup(override.disable)
        self.superuser = User.objects.create_superuser('szef', 's@x.pl', 'haslo12345')
        self.staff = User.objects.create_user('mod', 'm@x.pl', 'haslo12345', is_staff=True)
        self.trusted = make_trusted('zaufany')
        self.plain = User.objects.create_user('ola', 'o@x.pl', 'haslo12345')
        self.cat = Category.objects.create(slug='memy', name='Memy')
        self.post = Post.objects.create(title='Zły wpis', category=self.cat, body='treść',
                                        status='published', submitted_by=self.plain)
        self.msg = Message.objects.create(nick='ktoś', body='coś bardzo złego')

    def as_(self, u):
        self.client.force_authenticate(u)


class RequestPermissionTests(Base):
    """Who may even ASK for an escalation: trusted or staff, same tier as hide/restore/nuke."""

    def test_a_plain_user_cannot_escalate_a_post(self):
        self.as_(self.plain)
        r = self.client.post(f'/api/posts/{self.post.slug}/escalate/', {'reason': 'to jest bardzo złe'})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Escalation.objects.count(), 0)

    def test_a_plain_user_cannot_escalate_a_board_message(self):
        self.as_(self.plain)
        r = self.client.post(f'/api/board/{self.msg.pk}/escalate/', {'reason': 'to jest bardzo złe'})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Escalation.objects.count(), 0)

    def test_a_trusted_user_may_escalate_a_post(self):
        self.as_(self.trusted)
        r = self.client.post(f'/api/posts/{self.post.slug}/escalate/', {'reason': 'to jest bardzo złe'})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Escalation.objects.count(), 1)
        esc = Escalation.objects.get()
        self.assertEqual(esc.status, 'pending')
        self.assertEqual(esc.requested_by, self.trusted)
        self.assertTrue(esc.evidence_ref)  # the frozen package was hashed

    def test_a_reason_is_mandatory(self):
        self.as_(self.trusted)
        r = self.client.post(f'/api/posts/{self.post.slug}/escalate/', {'reason': '   '})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Escalation.objects.count(), 0)

    def test_escalating_twice_is_refused_not_duplicated(self):
        # The second attempt 404s, not 400 — the post is already excluded from the trusted
        # user's own queryset the instant it is escalated, even though THEY were the one
        # who escalated it. That is the same "no oracle" property as everywhere else: this
        # endpoint never distinguishes "already escalated" from "does not exist".
        self.as_(self.trusted)
        self.client.post(f'/api/posts/{self.post.slug}/escalate/', {'reason': 'raz'})
        r = self.client.post(f'/api/posts/{self.post.slug}/escalate/', {'reason': 'dwa'})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(Escalation.objects.count(), 1)


class VisibilityFreezeTests(Base):
    """The content vanishes for EVERYONE below head-admin the instant it is escalated —
    staff included. That "staff included" clause is the one people assume is false."""

    def escalate_post(self, actor=None):
        return create_escalation(self.post, actor or self.trusted, 'bardzo złe')

    def escalate_message(self, actor=None):
        return create_escalation(self.msg, actor or self.trusted, 'bardzo złe')

    def test_staff_loses_the_post_too(self):
        self.escalate_post()
        self.as_(self.staff)
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/').status_code, 404)
        self.assertNotIn(self.post.pk, [p['id'] for p in self.client.get('/api/posts/queue/').data['results']])

    def test_trusted_loses_the_post_too(self):
        self.escalate_post()
        self.as_(self.trusted)
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/').status_code, 404)

    def test_the_public_never_had_it_and_still_does_not(self):
        self.escalate_post()
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/').status_code, 404)
        self.assertNotIn(self.post.pk, [p['id'] for p in self.client.get('/api/posts/').data['results']])

    def test_only_head_admin_can_still_read_it(self):
        self.escalate_post()
        self.as_(self.superuser)
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/').status_code, 200)

    def test_the_moderation_board_drops_it_for_staff_once_hidden_and_escalated(self):
        from archive import moderation as rules
        rules.hide_post(self.post, self.staff, 'powód')
        self.escalate_post(self.staff)
        self.as_(self.staff)
        b = self.client.get('/api/moderation/board/').data
        self.assertEqual(b['count'], 0)

    def test_a_board_message_disappears_from_the_stream_for_staff_too(self):
        self.escalate_message()
        self.as_(self.staff)
        r = self.client.get('/api/board/?include_hidden=1')
        self.assertNotIn(self.msg.pk, [m['id'] for m in r.data['results']])

    def test_a_board_message_disappears_from_rss(self):
        self.escalate_message()
        r = self.client.get('/api/board/rss/')
        self.assertNotIn('bardzo złe', r.content.decode())

    def test_normal_moderation_is_frozen_while_pending_even_for_staff(self):
        self.escalate_message()
        self.as_(self.staff)
        r = self.client.post(f'/api/board/{self.msg.pk}/hide/')
        self.assertEqual(r.status_code, 403)

    def test_normal_moderation_is_frozen_on_a_post_even_for_staff(self):
        # 404, not 403: the post is unreachable through the ordinary endpoints at all once
        # escalated (post_queryset excludes it), so staff cannot even confirm it exists —
        # `require_not_escalated` inside hide_post/moderate is defense-in-depth for any
        # caller that reaches the target a different way, but the ViewSet never does.
        self.escalate_post()
        self.as_(self.staff)
        r = self.client.post(f'/api/posts/{self.post.slug}/hide/', {'reason': 'x'})
        self.assertEqual(r.status_code, 404)
        r2 = self.client.post(f'/api/posts/{self.post.slug}/moderate/', {'decision': 'reject'})
        self.assertEqual(r2.status_code, 404)


class IDORAndTierTests(Base):
    """Sequential, guessable escalation ids: `IsHeadAdmin.has_permission` short-circuits
    BEFORE the view ever looks the id up, so every non-head-admin gets the exact same 403
    whether the id exists or not — there is no oracle here, just a constant refusal."""

    def setUp(self):
        super().setUp()
        self.esc = create_escalation(self.post, self.trusted, 'bardzo złe')

    def test_a_plain_user_cannot_reach_it(self):
        self.as_(self.plain)
        self.assertEqual(self.client.get(f'/api/moderation/escalations/{self.esc.pk}/').status_code, 403)
        self.assertEqual(self.client.post(f'/api/moderation/escalations/{self.esc.pk}/decide/',
                                          {'decision': 'approve'}).status_code, 403)

    def test_the_trusted_requester_themselves_cannot_decide_their_own_escalation(self):
        self.as_(self.trusted)
        self.assertEqual(self.client.get(f'/api/moderation/escalations/{self.esc.pk}/').status_code, 403)
        self.assertEqual(self.client.post(f'/api/moderation/escalations/{self.esc.pk}/decide/',
                                          {'decision': 'approve'}).status_code, 403)

    def test_staff_is_not_head_admin(self):
        """The test the brief specifically called out: 'staff' people will assume is_staff
        is enough. It is not — only is_superuser is."""
        self.as_(self.staff)
        self.assertEqual(self.client.get('/api/moderation/escalations/').status_code, 403)
        self.assertEqual(self.client.get(f'/api/moderation/escalations/{self.esc.pk}/').status_code, 403)
        self.assertEqual(self.client.post(f'/api/moderation/escalations/{self.esc.pk}/decide/',
                                          {'decision': 'approve'}).status_code, 403)
        self.assertEqual(Escalation.objects.get(pk=self.esc.pk).status, 'pending')

    def test_head_admin_can_list_and_read(self):
        self.as_(self.superuser)
        self.assertEqual(len(self.client.get('/api/moderation/escalations/').data), 1)
        d = self.client.get(f'/api/moderation/escalations/{self.esc.pk}/').data
        self.assertEqual(d['status'], 'pending')
        self.assertIsNotNone(d['evidence'])
        self.assertEqual(d['evidence']['title'], 'Zły wpis')

    def test_anonymous_gets_401_or_403_never_the_content(self):
        r = self.client.get(f'/api/moderation/escalations/{self.esc.pk}/')
        self.assertIn(r.status_code, (401, 403, 404))


class DecisionTests(Base):
    def setUp(self):
        super().setUp()
        self.esc = create_escalation(self.post, self.trusted, 'bardzo złe')

    def test_approve_marks_status_and_freezes_it(self):
        self.as_(self.superuser)
        r = self.client.post(f'/api/moderation/escalations/{self.esc.pk}/decide/',
                             {'decision': 'approve', 'note': 'zgłoszone'})
        self.assertEqual(r.status_code, 200, r.data)
        self.esc.refresh_from_db()
        self.assertEqual(self.esc.status, 'approved')
        self.assertEqual(self.esc.decided_by, self.superuser)
        self.assertIsNotNone(self.esc.decided_at)
        # still frozen: 'approved' is as active as 'pending' for visibility purposes
        self.as_(self.staff)
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/').status_code, 404)

    def test_decline_unfreezes_normal_moderation(self):
        self.as_(self.superuser)
        r = self.client.post(f'/api/moderation/escalations/{self.esc.pk}/decide/', {'decision': 'decline'})
        self.assertEqual(r.status_code, 200, r.data)
        self.as_(self.staff)
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/').status_code, 200)
        # normal moderation works again
        r2 = self.client.post(f'/api/posts/{self.post.slug}/hide/', {'reason': 'x'})
        self.assertEqual(r2.status_code, 200, r2.data)

    def test_a_decided_escalation_cannot_be_decided_again(self):
        self.as_(self.superuser)
        decide_escalation(self.esc, self.superuser, 'approve')
        r = self.client.post(f'/api/moderation/escalations/{self.esc.pk}/decide/', {'decision': 'decline'})
        self.assertEqual(r.status_code, 400)
        self.esc.refresh_from_db()
        self.assertEqual(self.esc.status, 'approved')  # the first decision stands

    def test_an_invalid_decision_is_refused(self):
        self.as_(self.superuser)
        r = self.client.post(f'/api/moderation/escalations/{self.esc.pk}/decide/', {'decision': 'delete-everything'})
        self.assertEqual(r.status_code, 400)
        self.esc.refresh_from_db()
        self.assertEqual(self.esc.status, 'pending')


class EvidenceTests(Base):
    def test_the_evidence_survives_the_post_being_edited_afterwards(self):
        esc = create_escalation(self.post, self.trusted, 'bardzo złe')
        self.post.title, self.post.body = 'Zmieniony tytuł', 'zmieniona treść'
        self.post.save()
        self.as_(self.superuser)
        d = self.client.get(f'/api/moderation/escalations/{esc.pk}/').data
        self.assertEqual(d['evidence']['title'], 'Zły wpis')  # frozen at escalation time
        self.assertEqual(d['evidence']['body'], 'treść')

    def test_a_comment_escalation_freezes_its_own_body(self):
        from archive.models import Comment
        c = Comment.objects.create(post=self.post, author=self.plain, body='obrzydliwy komentarz')
        self.as_(self.trusted)
        r = self.client.post(f'/api/comments/{c.pk}/escalate/', {'reason': 'to jest bardzo złe'})
        self.assertEqual(r.status_code, 201, r.data)
        self.as_(self.staff)
        d = self.client.get(f'/api/posts/{self.post.slug}/comments/').data
        target = next(x for x in d if x['id'] == c.pk)
        self.assertEqual(target['body'], '')  # gone even for staff
        self.as_(self.superuser)
        esc = Escalation.objects.get()
        detail = self.client.get(f'/api/moderation/escalations/{esc.pk}/').data
        self.assertEqual(detail['evidence']['body'], 'obrzydliwy komentarz')
