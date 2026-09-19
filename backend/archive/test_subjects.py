"""Subjects — the third filing axis, and the only one anybody may extend by typing.

A subject is a university course, so almost none of the care a `Person` needs applies: no
consent, no opt-out, no directory that must hide a proposal. What DOES need testing is the
part that is easy to get subtly wrong — which rows the list shows, and that a typed name
folds onto the seeded row rather than minting a second one with the „ł" eaten (Django's own
`slugify` drops it, which would have filed „Fizyka ciała stałego" as `fizyka-ciaa-staego`).
"""
import tempfile

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APITestCase

from .models import Category, Post, Subject
from .subjects import MAX_SUBJECTS_PER_POST, resolve_subjects, subject_slug

LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), CACHES=LOCMEM)
class Base(APITestCase):
    def setUp(self):
        self.cat = Category.objects.create(slug='memy', name='Memy')
        self.staff = User.objects.create_user('mod', 'm@x.pl', 'haslo12345', is_staff=True)
        self.user = User.objects.create_user('ola', 'o@x.pl', 'haslo12345')

    def as_(self, u):
        self.client.force_authenticate(u)

    def payload(self, **kw):
        body = {'title': 'Wpis', 'category': 'memy', 'format': 'text', 'body': 'treść',
                'rights_confirmed': True}
        body.update(kw)
        return body


class SeedTests(Base):
    def test_the_faculty_programme_is_in_the_database_after_migrating(self):
        self.assertGreaterEqual(Subject.objects.count(), 25)
        mk = Subject.objects.get(slug='mechanika-klasyczna')
        self.assertEqual((mk.name, mk.short), ('Mechanika klasyczna', 'MK'))
        self.assertIsNone(mk.created_by_id)  # NULL is what makes it „from the programme"

    def test_polish_letters_survive_the_slug(self):
        """Django's slugify would have made this `fizyka-ciaa-staego`."""
        self.assertEqual(subject_slug('Fizyka ciała stałego'), 'fizyka-ciala-stalego')
        self.assertTrue(Subject.objects.filter(slug='fizyka-ciala-stalego').exists())
        # and a slug folds to itself, so the picker may send either
        self.assertEqual(subject_slug('fizyka-ciala-stalego'), 'fizyka-ciala-stalego')


class ResolveTests(Base):
    def test_a_typed_name_lands_on_the_seeded_row(self):
        for typed in ('Mechanika klasyczna', 'MECHANIKA KLASYCZNA', 'mechanika-klasyczna'):
            got = resolve_subjects([typed], self.user)
            self.assertEqual([s.slug for s in got], ['mechanika-klasyczna'], typed)
        self.assertIsNone(Subject.objects.get(slug='mechanika-klasyczna').created_by_id)

    def test_an_unknown_name_creates_a_subject_credited_to_its_author(self):
        got = resolve_subjects(['Wstęp do kosmologii'], self.user)[0]
        self.assertEqual((got.name, got.slug, got.created_by), ('Wstęp do kosmologii', 'wstep-do-kosmologii', self.user))
        self.assertEqual(got.order, 900)  # after everything the programme seeded

    def test_repeats_collapse_and_the_order_given_is_kept(self):
        got = resolve_subjects(['Elektrodynamika klasyczna', 'Mechanika klasyczna',
                                'elektrodynamika-klasyczna'], self.user)
        self.assertEqual([s.slug for s in got], ['elektrodynamika-klasyczna', 'mechanika-klasyczna'])

    def test_a_name_must_be_a_name_and_there_is_a_ceiling(self):
        for bad in ('x', 'zapisy@fuw.edu.pl', 'https://usosweb.uw.edu.pl/x', '---'):
            with self.assertRaises(Exception, msg=bad):
                resolve_subjects([bad], self.user)
        too_many = [f'Zupełnie Nowy Przedmiot {i}' for i in range(MAX_SUBJECTS_PER_POST + 1)]
        with self.assertRaises(Exception):
            resolve_subjects(too_many, self.user)

    def test_an_anonymous_caller_may_not_mint_a_subject_but_may_name_one(self):
        from django.contrib.auth.models import AnonymousUser
        with self.assertRaises(Exception):
            resolve_subjects(['Wstęp do kosmologii'], AnonymousUser())
        self.assertEqual(resolve_subjects(['Mechanika klasyczna'], AnonymousUser())[0].slug, 'mechanika-klasyczna')


class ApiListTests(Base):
    def test_the_list_shows_the_programme_always_and_a_named_subject_once_it_has_a_post(self):
        named = resolve_subjects(['Wstęp do kosmologii'], self.user)[0]
        slugs = [s['slug'] for s in self.client.get('/api/subjects/').data]
        self.assertIn('mechanika-klasyczna', slugs)          # seeded, no posts — listed anyway
        self.assertNotIn(named.slug, slugs)                   # named, no published post — not yet

        published = Post.objects.create(title='Wpis', category=self.cat, body='x', status='published')
        published.subjects.add(named)
        row = next(s for s in self.client.get('/api/subjects/').data if s['slug'] == named.slug)
        self.assertEqual(row['post_count'], 1)

    def test_a_pending_post_does_not_count_and_does_not_list(self):
        self.as_(self.user)
        self.client.post('/api/posts/', self.payload(subjects=['Wstęp do kosmologii']), format='json')
        self.client.force_authenticate(None)
        self.assertNotIn('wstep-do-kosmologii', [s['slug'] for s in self.client.get('/api/subjects/').data])

    def test_retrieve_does_not_narrow_so_a_shared_link_always_opens(self):
        named = resolve_subjects(['Wstęp do kosmologii'], self.user)[0]
        self.client.force_authenticate(None)
        r = self.client.get(f'/api/subjects/{named.slug}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['post_count'], 0)
        self.assertEqual(self.client.get('/api/subjects/nie-ma-takiego/').status_code, 404)

    def test_search_matches_the_name_and_the_short_form(self):
        by_name = [s['slug'] for s in self.client.get('/api/subjects/?q=kwantow').data]
        self.assertIn('mechanika-kwantowa-i', by_name)
        self.assertNotIn('mechanika-klasyczna', by_name)
        self.assertEqual([s['slug'] for s in self.client.get('/api/subjects/?q=AM1').data],
                         ['analiza-matematyczna-i'])

    def test_the_list_is_in_programme_order_not_alphabetical(self):
        slugs = [s['slug'] for s in self.client.get('/api/subjects/').data]
        self.assertLess(slugs.index('analiza-matematyczna-i'), slugs.index('mechanika-kwantowa-ii'))


class PostIntegrationTests(Base):
    def test_a_post_carries_its_subjects_and_can_be_filtered_by_one(self):
        self.as_(self.staff)  # staff publish straight away
        r = self.client.post('/api/posts/', self.payload(
            subjects=['Mechanika klasyczna', 'Nowy Przedmiot Autorski']), format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual([s['slug'] for s in r.data['subjects']],
                         ['mechanika-klasyczna', 'nowy-przedmiot-autorski'])
        self.assertEqual(r.data['subjects'][0]['short'], 'MK')
        self.assertNotIn('post_count', r.data['subjects'][0])  # embedded: three keys, no count

        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/posts/?subject=mechanika-klasyczna').data['count'], 1)
        self.assertEqual(self.client.get('/api/posts/?subject=fizyka-statystyczna').data['count'], 0)

    def test_the_free_text_search_finds_a_post_by_its_subject(self):
        self.as_(self.staff)
        self.client.post('/api/posts/', self.payload(title='Bez wzmianki', body='nic tu nie ma',
                                                     subjects=['Elektrodynamika klasyczna']), format='json')
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/posts/?q=elektrodynamika').data['count'], 1)

    def test_editing_a_post_replaces_its_subjects_and_omitting_them_keeps_them(self):
        self.as_(self.staff)
        slug = self.client.post('/api/posts/', self.payload(subjects=['Mechanika klasyczna']),
                                format='json').data['slug']
        r = self.client.patch(f'/api/posts/{slug}/', {'subjects': ['Optyka']}, format='json')
        self.assertEqual([s['name'] for s in r.data['subjects']], ['Optyka'])
        r = self.client.patch(f'/api/posts/{slug}/', {'title': 'Inny'}, format='json')
        self.assertEqual([s['name'] for s in r.data['subjects']], ['Optyka'])
        r = self.client.patch(f'/api/posts/{slug}/', {'subjects': []}, format='json')
        self.assertEqual(r.data['subjects'], [])

    def test_the_multipart_json_string_shape_the_editor_sends(self):
        import json
        self.as_(self.staff)
        r = self.client.post('/api/posts/', {
            'title': 'Z formularza', 'category': 'memy', 'format': 'text', 'body': 'treść',
            'rights_confirmed': 'true', 'subjects': json.dumps(['Mechanika klasyczna']),
        }, format='multipart')
        self.assertEqual([s['slug'] for s in r.data['subjects']], ['mechanika-klasyczna'])


class TagSearchTests(Base):
    def test_tags_can_be_searched_for_the_typeahead_and_still_need_a_published_post(self):
        published = Post.objects.create(title='A', category=self.cat, body='x', status='published')
        pending = Post.objects.create(title='B', category=self.cat, body='x', status='pending')
        from .models import Tag
        live = Tag.objects.create(slug='kolokwium', name='kolokwium')
        quiet = Tag.objects.create(slug='kreda', name='kreda')
        published.tags.add(live)
        pending.tags.add(quiet)
        self.assertEqual([t['slug'] for t in self.client.get('/api/tags/?q=kolo').data], ['kolokwium'])
        self.assertEqual([t['slug'] for t in self.client.get('/api/tags/?q=kred').data], [])
        self.assertEqual([t['slug'] for t in self.client.get('/api/tags/').data], ['kolokwium'])
