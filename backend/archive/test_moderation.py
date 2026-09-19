"""The trusted tier: hide / restore / nuke, and who may read what afterwards."""
import tempfile

from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import TrustedDomain
from .models import Category, Comment, ModerationAction, Post, Report


def make_trusted(username):
    u = User.objects.create_user(username, f'{username}@fuw.edu.pl', 'haslo12345')
    dom, _ = TrustedDomain.objects.get_or_create(domain='fuw.edu.pl', defaults={'institution': 'FUW', 'kind': 'fuw'})
    # edit the profile THROUGH the user object: force_authenticate reuses this instance for
    # every request, and its cached reverse one-to-one would otherwise stay unverified
    p = u.profile
    p.affiliation_email, p.affiliation_domain, p.verified_at = f'{username}@fuw.edu.pl', dom, timezone.now()
    p.save()
    return u


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ModerationTierTests(APITestCase):
    def setUp(self):
        self.cat = Category.objects.create(slug='memy', name='Memy')
        self.staff = User.objects.create_user('mod', 'm@x.pl', 'haslo12345', is_staff=True)
        self.trusted = make_trusted('zaufany')
        self.plain = User.objects.create_user('ola', 'o@x.pl', 'haslo12345')
        self.post = Post.objects.create(title='Wpis', category=self.cat, body='treść', status='published',
                                        submitted_by=self.plain)

    def as_(self, u):
        self.client.force_authenticate(u)

    def test_me_reports_trust(self):
        self.as_(self.trusted)
        self.assertTrue(self.client.get('/api/auth/me/').data['is_trusted'])
        self.as_(self.plain)
        self.assertFalse(self.client.get('/api/auth/me/').data['is_trusted'])

    def test_trusted_hides_in_one_call_and_public_loses_it(self):
        Report.objects.create(post=self.post, reason='wrong')
        self.as_(self.trusted)
        r = self.client.post(f'/api/posts/{self.post.slug}/hide/', {'reason': 'nie tak'})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['status'], 'hidden')
        self.assertEqual(r.data['moderation']['actor'], 'zaufany')
        self.assertTrue(Report.objects.get().resolved)
        self.assertEqual(ModerationAction.objects.filter(post=self.post, action='hide').count(), 1)
        # trusted still reads it, with a notice; the public does not
        d = self.client.get(f'/api/posts/{self.post.slug}/').data
        self.assertEqual(d['status'], 'hidden')
        self.assertTrue(d['moderation_notice'])
        self.assertTrue(d['can_moderate'])
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/').status_code, 404)
        self.assertEqual(self.client.get('/api/posts/').data['count'], 0)
        self.assertEqual(self.client.get('/api/posts/random/').status_code, 404)
        self.assertEqual(self.client.get('/api/posts/?q=Wpis').data['count'], 0)
        # board shows it in full to trusted; restore brings it back
        self.as_(self.trusted)
        b = self.client.get('/api/moderation/board/').data
        self.assertEqual(b['count'], 1)
        self.assertEqual(b['posts'][0]['title'], 'Wpis')
        self.assertEqual(b['posts'][0]['moderation']['reason'], 'nie tak')
        r = self.client.post(f'/api/posts/{self.post.slug}/restore/')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['status'], 'published')
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/posts/').data['count'], 1)

    def test_plain_user_cannot_moderate_or_see_board(self):
        self.as_(self.plain)
        self.assertEqual(self.client.post(f'/api/posts/{self.post.slug}/hide/').status_code, 403)
        self.assertEqual(self.client.get('/api/moderation/board/').status_code, 403)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get('/api/moderation/board/').status_code, (401, 403))

    def test_nuke_is_staff_only_to_read_and_restore(self):
        self.as_(self.trusted)
        self.assertEqual(self.client.post(f'/api/posts/{self.post.slug}/nuke/', {'reason': ''}).status_code, 400)
        r = self.client.post(f'/api/posts/{self.post.slug}/nuke/', {'reason': 'nielegalne'})
        self.assertEqual(r.status_code, 200, r.data)
        stub = self.client.get('/api/moderation/board/').data['posts'][0]
        self.assertEqual(stub['status'], 'nuked')
        for key in ('title', 'body', 'slug', 'attachments', 'summary'):
            self.assertNotIn(key, stub)
        self.assertEqual(stub['moderation']['actor'], 'zaufany')
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/').status_code, 404)
        self.assertEqual(self.client.post(f'/api/posts/{self.post.slug}/restore/').status_code, 403)
        self.as_(self.plain)  # the author cannot read their own nuked post either
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/').status_code, 404)
        self.as_(self.staff)
        full = self.client.get('/api/moderation/board/').data['posts'][0]
        self.assertEqual(full['title'], 'Wpis')
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/').status_code, 200)
        r = self.client.post(f'/api/posts/{self.post.slug}/restore/')
        self.assertEqual(r.data['status'], 'published')
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/').status_code, 200)

    def test_restore_returns_a_pending_post_to_pending(self):
        pending = Post.objects.create(title='P', category=self.cat, body='x', status='pending', submitted_by=self.plain)
        # a trusted user cannot even see a stranger's pending post, so cannot hide it (404) —
        # staff can, and a restore must send it back to the queue, never publish it
        self.as_(self.trusted)
        self.assertEqual(self.client.post(f'/api/posts/{pending.slug}/hide/', {'reason': 'x'}).status_code, 404)
        self.as_(self.staff)
        self.assertEqual(self.client.post(f'/api/posts/{pending.slug}/hide/', {'reason': 'x'}).status_code, 200)
        r = self.client.post(f'/api/posts/{pending.slug}/restore/')
        self.assertEqual(r.data['status'], 'pending')

    def test_trusted_own_post_publishes_immediately(self):
        self.as_(self.trusted)
        r = self.client.post('/api/posts/', {'rights_confirmed': 'true', 'title': 'T', 'category': 'memy', 'body': 'x'})
        self.assertEqual(r.data['status'], 'published')
        self.as_(self.plain)
        r = self.client.post('/api/posts/', {'rights_confirmed': 'true', 'title': 'T2', 'category': 'memy', 'body': 'x'})
        self.assertEqual(r.data['status'], 'pending')

    def test_comment_hide_placeholder_and_nuke(self):
        c = Comment.objects.create(post=self.post, author=self.plain, body='obraźliwe')
        self.as_(self.trusted)
        r = self.client.post(f'/api/comments/{c.pk}/hide/', {'reason': 'ton'})
        self.assertEqual(r.status_code, 200, r.data)
        self.client.force_authenticate(None)
        pub = self.client.get(f'/api/posts/{self.post.slug}/comments/').data
        self.assertEqual(pub[0]['moderation'], 'hidden')
        self.assertEqual(pub[0]['body'], '')
        self.as_(self.trusted)
        mine = self.client.get(f'/api/posts/{self.post.slug}/comments/').data
        self.assertEqual(mine[0]['body'], 'obraźliwe')
        self.assertEqual(self.client.post(f'/api/comments/{c.pk}/nuke/', {'reason': 'nielegalne'}).status_code, 200)
        mine = self.client.get(f'/api/posts/{self.post.slug}/comments/').data
        self.assertEqual(mine[0]['body'], '')
        self.assertEqual(self.client.post(f'/api/comments/{c.pk}/restore/').status_code, 403)
        self.as_(self.staff)
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/comments/').data[0]['body'], 'obraźliwe')
        self.assertEqual(self.client.post(f'/api/comments/{c.pk}/restore/').status_code, 200)
        self.as_(self.plain)
        self.assertEqual(self.client.post(f'/api/comments/{c.pk}/hide/').status_code, 403)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PinningTests(APITestCase):
    """Pin / unpin from the post page itself. It was staff-only and reachable only from
    the moderation board, which meant pinning a post required going to find it in a queue."""

    def setUp(self):
        self.cat = Category.objects.create(slug='memy', name='Memy')
        self.staff = User.objects.create_user('mod', 'm@x.pl', 'haslo12345', is_staff=True)
        self.trusted = make_trusted('zaufany')
        self.plain = User.objects.create_user('ola', 'o@x.pl', 'haslo12345')
        self.post = Post.objects.create(title='Wpis', category=self.cat, body='t',
                                        status='published')

    def url(self, post=None):
        return f'/api/posts/{(post or self.post).slug}/feature/'

    def test_an_anonymous_visitor_cannot_pin(self):
        self.assertIn(self.client.post(self.url()).status_code, (401, 403))

    def test_a_plain_user_cannot_pin(self):
        self.client.force_authenticate(self.plain)
        self.assertEqual(self.client.post(self.url()).status_code, 403)
        self.post.refresh_from_db()
        self.assertFalse(self.post.featured)

    def test_a_trusted_moderator_can_pin_and_unpin(self):
        """The widening: this used to require `is_staff`."""
        self.client.force_authenticate(self.trusted)
        r = self.client.post(self.url(), {}, format='json')
        self.assertEqual(r.status_code, 200)
        self.post.refresh_from_db()
        self.assertTrue(self.post.featured)

        r = self.client.post(self.url(), {}, format='json')   # toggles back
        self.assertEqual(r.status_code, 200)
        self.post.refresh_from_db()
        self.assertFalse(self.post.featured)

    def test_it_is_audited_like_every_other_moderation_act(self):
        """Who put this on the front page is a question that gets asked."""
        self.client.force_authenticate(self.trusted)
        self.client.post(self.url(), {}, format='json')
        a = ModerationAction.objects.filter(post=self.post).first()
        self.assertEqual(a.action, 'feature')
        self.assertEqual(a.actor, self.trusted)

    def test_an_explicit_state_beats_a_toggle(self):
        """Two moderators clicking at once must not flip it twice — the board sends the
        state it wants rather than 'the opposite of what I last saw'."""
        self.client.force_authenticate(self.trusted)
        self.client.post(self.url(), {'featured': True}, format='json')
        r = self.client.post(self.url(), {'featured': True}, format='json')
        self.assertEqual(r.status_code, 400)          # already in that state
        self.post.refresh_from_db()
        self.assertTrue(self.post.featured)

    def test_only_a_published_post_can_be_pinned(self):
        """Pinning something pending would queue it to appear on the homepage the moment
        it went live, which is not a decision anybody made.

        Tested as STAFF, not as a trusted moderator: a pending post is not in a trusted
        user's queryset at all, so they get 404 — the queue's own scoping answering first,
        which is right. Staff can see it, so staff is who the rule has to refuse."""
        draft = Post.objects.create(title='Szkic', category=self.cat, body='t', status='pending')
        self.client.force_authenticate(self.staff)
        r = self.client.post(self.url(draft), {'featured': True}, format='json')
        self.assertEqual(r.status_code, 400)
        draft.refresh_from_db()
        self.assertFalse(draft.featured)

    def test_a_trusted_moderator_cannot_even_see_a_pending_post(self):
        draft = Post.objects.create(title='Szkic', category=self.cat, body='t', status='pending')
        self.client.force_authenticate(self.trusted)
        self.assertEqual(self.client.post(self.url(draft), {'featured': True}, format='json').status_code, 404)

    def test_a_pinned_post_that_gets_hidden_can_still_be_unpinned(self):
        self.post.featured = True
        self.post.save(update_fields=['featured'])
        self.post.status = 'hidden'
        self.post.save(update_fields=['status'])
        self.client.force_authenticate(self.trusted)
        r = self.client.post(self.url(), {'featured': False}, format='json')
        self.assertEqual(r.status_code, 200)
        self.post.refresh_from_db()
        self.assertFalse(self.post.featured)
