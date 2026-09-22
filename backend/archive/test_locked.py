"""„Kontrowersyjne" — `Post.trusted_only`: the post stays listed, the content does not.

The teaser is the whole point and the whole danger: a locked post keeps its title on every
public list, so every OTHER way of reaching its content has to be closed one by one. Most of
what is pinned here is those ways — search over the body-derived columns, the filing filters,
the comment thread, a suggestion's frozen `base`, a link preview — rather than the blanking
itself, which is the easy half.
"""
import tempfile

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APITestCase

from .models import Category, EditSuggestion, ModerationAction, Person, Post, Report
from .test_moderation import make_trusted


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class LockedPostTests(APITestCase):
    def setUp(self):
        self.cat = Category.objects.create(slug='memy', name='Memy')
        self.staff = User.objects.create_user('mod', 'm@x.pl', 'haslo12345', is_staff=True)
        self.trusted = make_trusted('zaufany')
        self.plain = User.objects.create_user('ola', 'o@x.pl', 'haslo12345')
        self.author = User.objects.create_user('autor', 'a@x.pl', 'haslo12345')
        self.person = Person.objects.create(name='dr Kwant Niepewny', slug='kwant-niepewny')
        self.post = Post.objects.create(
            title='Legendarne kolokwium', category=self.cat, status='published',
            body='kontrabas na wykładzie z $\\dfrac{1}{2}$', summary='streszczenie treści',
            trusted_only=True, submitted_by=self.author)
        self.post.people.add(self.person)
        self.open = Post.objects.create(title='Zwykły wpis', category=self.cat, status='published',
                                        body='kontrabas też tutaj', summary='jawne')

    def as_(self, u):
        self.client.force_authenticate(u)

    def card(self, user=None, **params):
        self.as_(user)
        r = self.client.get('/api/posts/', params)
        return {p['slug']: p for p in r.data['results']}

    # --- the teaser -------------------------------------------------------------------

    def test_the_card_keeps_the_title_and_loses_what_the_post_is_about(self):
        card = self.card()[self.post.slug]
        self.assertEqual(card['title'], 'Legendarne kolokwium')
        self.assertTrue(card['trusted_only'])
        self.assertTrue(card['locked'])
        self.assertEqual(card['summary'], '')
        self.assertIsNone(card['cover'])
        self.assertEqual(card['people'], [])
        self.assertEqual(card['tags'], [])
        self.assertEqual(card['comment_count'], 0)
        self.assertEqual(set(card['reaction_counts'].values()), {0})
        # the filing that IS on the card stays: it is what makes the teaser honest
        self.assertEqual(card['category'], 'memy')

    def test_the_detail_page_carries_the_notice_and_no_body(self):
        r = self.client.get(f'/api/posts/{self.post.slug}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['body'], '')
        self.assertEqual(r.data['attachments'], [])
        self.assertIn('kontrowersyjny', r.data['lock_notice'])

    def test_a_trusted_reader_gets_the_whole_post_and_no_notice(self):
        self.as_(self.trusted)
        r = self.client.get(f'/api/posts/{self.post.slug}/')
        self.assertIn('kontrabas', r.data['body'])
        self.assertFalse(r.data['locked'])
        self.assertIsNone(r.data['lock_notice'])
        self.assertTrue(r.data['trusted_only'])  # still badged, so they know it is restricted

    def test_a_plain_account_is_no_better_off_than_a_stranger(self):
        self.as_(self.plain)
        self.assertTrue(self.client.get(f'/api/posts/{self.post.slug}/').data['locked'])

    def test_the_author_reads_their_own_restricted_post(self):
        self.as_(self.author)
        r = self.client.get(f'/api/posts/{self.post.slug}/')
        self.assertFalse(r.data['locked'])
        self.assertIn('kontrabas', r.data['body'])

    def test_a_teaser_is_not_counted_as_a_view(self):
        before = self.post.views
        self.client.get(f'/api/posts/{self.post.slug}/')
        self.post.refresh_from_db()
        self.assertEqual(self.post.views, before)
        self.as_(self.trusted)
        self.client.get(f'/api/posts/{self.post.slug}/')
        self.post.refresh_from_db()
        self.assertEqual(self.post.views, before + 1)

    # --- the ways to the content that are not the content -----------------------------

    def test_the_body_is_not_searchable_although_the_title_is(self):
        """A yes/no about text you may not read is an oracle, and yes/no answers bisect."""
        self.assertNotIn(self.post.slug, self.card(q='kontrabas'))
        self.assertIn(self.open.slug, self.card(q='kontrabas'))
        self.assertIn(self.post.slug, self.card(q='kolokwium'))
        self.assertIn(self.post.slug, self.card(self.trusted, q='kontrabas'))
        self.assertIn(self.post.slug, self.card(self.author, q='kontrabas'))

    def test_a_formula_in_a_restricted_body_is_not_searchable_either(self):
        self.assertNotIn(self.post.slug, self.card(q='\\frac{1}{2}'))
        self.assertIn(self.post.slug, self.card(self.trusted, q='\\frac{1}{2}'))

    def test_filtering_by_the_person_named_inside_does_not_return_it(self):
        self.assertNotIn(self.post.slug, self.card(person='kwant-niepewny'))
        self.assertIn(self.post.slug, self.card(self.trusted, person='kwant-niepewny'))

    def test_a_person_named_only_in_a_locked_post_stays_out_of_the_directory(self):
        """Visibility is derived from a published post (`people.visible_people_q`), and
        `_public_posts` does not count a locked one — so naming somebody into existence
        inside a restricted post does not give a stranger a page about them."""
        proposed = Person.objects.create(name='mgr Nowa Osoba', slug='nowa-osoba',
                                         created_by=self.author)
        self.post.people.add(proposed)
        r = self.client.get('/api/people/')
        rows = r.data['results'] if isinstance(r.data, dict) else r.data
        self.assertNotIn('nowa-osoba', [p['slug'] for p in rows])
        # and the count on a person who IS listed does not move either
        r = self.client.get('/api/people/kwant-niepewny/')
        self.assertEqual(r.data['post_count'], 0)

    def test_the_comment_thread_is_refused_with_a_reason(self):
        r = self.client.get(f'/api/posts/{self.post.slug}/comments/')
        self.assertEqual(r.status_code, 403)
        self.as_(self.plain)
        r = self.client.post(f'/api/posts/{self.post.slug}/comments/', {'body': 'ha'}, format='json')
        self.assertEqual(r.status_code, 403)
        self.as_(self.trusted)
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/comments/').status_code, 200)

    def test_reacting_to_what_you_cannot_read_is_refused(self):
        self.as_(self.plain)
        r = self.client.post(f'/api/posts/{self.post.slug}/react/', {'kind': 'lol'}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_a_stranger_cannot_read_the_body_out_of_a_suggestion(self):
        """`create_suggestion` freezes the current value of every field it touches into
        `base`, and the suggester may read their own suggestion back."""
        self.as_(self.plain)
        r = self.client.post(f'/api/posts/{self.post.slug}/suggestions/',
                             {'changes': {'body': 'moja wersja'}, 'rationale': 'bo tak'}, format='json')
        self.assertEqual(r.status_code, 403)
        self.assertNotIn('kontrabas', str(r.data))
        self.assertFalse(EditSuggestion.objects.filter(post=self.post).exists())

    def test_an_older_suggestion_stops_being_readable_when_the_post_is_locked(self):
        self.post.trusted_only = False
        self.post.save(update_fields=['trusted_only'])
        self.as_(self.plain)
        self.client.post(f'/api/posts/{self.post.slug}/suggestions/',
                         {'changes': {'body': 'moja wersja'}, 'rationale': 'bo tak'}, format='json')
        self.post.trusted_only = True
        self.post.save(update_fields=['trusted_only'])
        r = self.client.get(f'/api/posts/{self.post.slug}/suggestions/')
        self.assertEqual(r.data, [])

    def test_random_never_hands_a_stranger_a_post_they_cannot_read(self):
        self.open.delete()
        r = self.client.get('/api/posts/random/')
        self.assertEqual(r.status_code, 404)
        self.as_(self.trusted)
        self.assertEqual(self.client.get('/api/posts/random/').status_code, 200)

    def test_a_locked_post_still_takes_a_report(self):
        """The title is readable, and recognising it is exactly why somebody reports."""
        r = self.client.post('/api/reports/', {'post': self.post.slug, 'reason': 'privacy',
                                               'note': 'to o mnie'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertTrue(Report.objects.filter(post=self.post).exists())

    # --- who may set it ---------------------------------------------------------------

    def test_a_plain_author_may_lock_their_own_post_while_they_may_edit_it(self):
        self.as_(self.plain)
        r = self.client.post('/api/posts/', {'title': 'Mój', 'category': 'memy', 'body': 'treść',
                                             'rights_confirmed': 'true', 'trusted_only': 'true'},
                             format='multipart')
        self.assertEqual(r.status_code, 201)
        self.assertTrue(Post.objects.get(slug=r.data['slug']).trusted_only)

    def test_an_author_may_undo_their_own_tick_but_not_a_moderators(self):
        self.as_(self.author)
        post = Post.objects.create(title='Szkic', category=self.cat, status='pending',
                                   body='treść', trusted_only=True, submitted_by=self.author)
        r = self.client.patch(f'/api/posts/{post.slug}/', {'trusted_only': False}, format='json')
        self.assertEqual(r.status_code, 200)
        post.refresh_from_db()
        self.assertFalse(post.trusted_only)
        # now a moderator locks it, and the same click stops working
        ModerationAction.objects.create(action='lock', actor=self.trusted, post=post)
        post.trusted_only = True
        post.save(update_fields=['trusted_only'])
        r = self.client.patch(f'/api/posts/{post.slug}/', {'trusted_only': False}, format='json')
        self.assertEqual(r.status_code, 400)
        post.refresh_from_db()
        self.assertTrue(post.trusted_only)

    def test_a_trusted_moderator_locks_and_unlocks_and_every_turn_is_audited(self):
        self.as_(self.trusted)
        r = self.client.post(f'/api/posts/{self.open.slug}/lock/', {}, format='json')
        self.assertEqual(r.status_code, 200)
        self.open.refresh_from_db()
        self.assertTrue(self.open.trusted_only)
        self.assertTrue(ModerationAction.objects.filter(post=self.open, action='lock',
                                                        actor=self.trusted).exists())
        self.client.post(f'/api/posts/{self.open.slug}/lock/', {'trusted_only': False}, format='json')
        self.open.refresh_from_db()
        self.assertFalse(self.open.trusted_only)
        self.assertTrue(ModerationAction.objects.filter(post=self.open, action='unlock').exists())

    def test_a_no_op_is_refused_rather_than_written_twice(self):
        self.as_(self.trusted)
        r = self.client.post(f'/api/posts/{self.post.slug}/lock/', {'trusted_only': True}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_a_plain_user_may_not_lock_somebody_elses_post(self):
        self.as_(self.plain)
        r = self.client.post(f'/api/posts/{self.open.slug}/lock/', {}, format='json')
        self.assertEqual(r.status_code, 403)
        self.open.refresh_from_db()
        self.assertFalse(self.open.trusted_only)

    def test_staff_can_lock_from_the_queue_before_publishing(self):
        pending = Post.objects.create(title='W kolejce', category=self.cat, status='pending',
                                      body='treść', submitted_by=self.plain)
        self.as_(self.staff)
        r = self.client.post(f'/api/posts/{pending.slug}/moderate/', {'decision': 'lock'}, format='json')
        self.assertEqual(r.status_code, 200)
        pending.refresh_from_db()
        self.assertTrue(pending.trusted_only)
