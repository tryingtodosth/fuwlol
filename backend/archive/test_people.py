"""/ludzie — filing a name the way the faculty directory does, nicknames as alternative tags,
and the alias endpoints. The rules under test live in archive/people.py."""
from django.contrib.auth.models import User
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from .models import Category, Person, Post, Tag
from .people import derive_surname, letter_for, sort_key_for, split_degree
from .test_moderation import make_trusted


class FilingTests(SimpleTestCase):
    def test_split_degree(self):
        cases = {
            'dr Kwant Niepewny': ('dr', 'Kwant Niepewny'),
            'prof. dr hab. Helena Hamiltonian': ('prof. dr hab.', 'Helena Hamiltonian'),
            'mgr inż. Anna Abramczuk': ('mgr inż.', 'Anna Abramczuk'),
            'Pani z portierni': ('', 'Pani z portierni'),
            'Doc': ('', 'Doc'),  # peeling would leave nothing
            '': ('', ''),
        }
        for name, want in cases.items():
            with self.subTest(name=name):
                self.assertEqual(split_degree(name), want)

    def test_surname_letter_and_sort_key(self):
        self.assertEqual(derive_surname('dr Jan Nowak'), 'Nowak')
        self.assertEqual(derive_surname('Pani z portierni'), 'portierni')
        # the letter keeps its diacritic — Ż is its own letter in the faculty's strip —
        # while the sort key folds it, so Łoś files next to Lis whatever the collation
        self.assertEqual(letter_for('Żygierewicz'), 'Ż')
        self.assertEqual(letter_for('Łoś'), 'Ł')
        self.assertEqual(sort_key_for('Łoś', 'Jan Łoś'), 'los jan')
        self.assertEqual(sort_key_for('Nowak', 'dr Jan Nowak'), 'nowak jan')
        self.assertEqual(letter_for('', 'Kwant'), 'K')


class PersonModelTests(APITestCase):
    def test_save_files_the_name(self):
        p = Person.objects.create(slug='jan-nowak', name='Jan Nowak', degree='dr')
        self.assertEqual((p.surname, p.sort_key, p.letter, p.full_name), ('Nowak', 'nowak jan', 'N', 'dr Jan Nowak'))

    def test_surname_override_sticks(self):
        p = Person.objects.create(slug='pani', name='Pani z portierni', surname='Pani')
        p.name = 'Pani z portierni głównej'
        p.save()
        self.assertEqual((p.surname, p.letter), ('Pani', 'P'))


class PeopleApiTests(APITestCase):
    def setUp(self):
        self.cat = Category.objects.create(slug='memy', name='Memy')
        self.trusted = make_trusted('zaufany')
        self.plain = User.objects.create_user('ola', 'o@x.pl', 'haslo12345')
        self.helena = Person.objects.create(slug='helena', name='Helena Hamiltonian', degree='prof.', sex='f')
        self.kwant = Person.objects.create(slug='kwant', name='Kwant Niepewny', degree='dr', sex='m')
        self.nick = Tag.objects.create(slug='hamiltonianka', name='Hamiltonianka')
        self.helena.aliases.add(self.nick)

        def post(title, year, status='published', people=(), tags=()):
            p = Post.objects.create(title=title, category=self.cat, body='x', status=status, year=year,
                                    submitted_by=self.plain)
            p.people.set(people)
            p.tags.set(tags)
            return p
        self.named = post('named', 2009, people=[self.helena])
        self.tagged = post('tagged only', 2019, tags=[self.nick])
        self.both = post('both', 2015, people=[self.helena], tags=[self.nick])
        self.pending = post('pending', 2020, status='pending', tags=[self.nick])
        self.hidden = post('hidden', 2021, status='hidden', people=[self.helena])

    def test_directory_is_filed_by_surname_and_counts_through_aliases(self):
        rows = self.client.get('/api/people/').json()
        self.assertEqual([r['slug'] for r in rows], ['helena', 'kwant'])  # Hamiltonian < Niepewny
        h = rows[0]
        self.assertEqual(h['full_name'], 'prof. Helena Hamiltonian')
        self.assertEqual(h['letter'], 'H')
        self.assertEqual([a['slug'] for a in h['aliases']], ['hamiltonianka'])
        # named + tagged-only + both = 3; 'both' once; pending and hidden never
        self.assertEqual((h['post_count'], h['year_min'], h['year_max']), (3, 2009, 2019))
        self.assertEqual((rows[1]['post_count'], rows[1]['year_min']), (0, None))

    def test_browse_filter_includes_nickname_tagged_posts_once(self):
        titles = [p['title'] for p in self.client.get('/api/posts/?person=helena').json()['results']]
        self.assertEqual(sorted(titles), ['both', 'named', 'tagged only'])

    def test_search_matches_nickname(self):
        self.assertEqual([r['slug'] for r in self.client.get('/api/people/?q=hamiltonianka').json()], ['helena'])
        self.assertEqual([r['slug'] for r in self.client.get('/api/people/?q=niepew').json()], ['kwant'])

    def test_unlisted_person_is_404(self):
        self.kwant.is_listed = False
        self.kwant.save()
        self.assertEqual(self.client.get('/api/people/kwant/').status_code, 404)
        self.assertEqual([r['slug'] for r in self.client.get('/api/people/').json()], ['helena'])

    def test_embedded_person_on_a_post_carries_aliases_but_no_count(self):
        p = self.client.get('/api/posts/named/').json()['people'][0]
        self.assertEqual(p['aliases'][0]['slug'], 'hamiltonianka')
        self.assertNotIn('post_count', p)

    # --- aliases -------------------------------------------------------------------------

    def test_alias_endpoints_need_the_trusted_tier(self):
        self.assertEqual(self.client.post('/api/people/kwant/aliases/', {'name': 'Kwancik'}).status_code, 401)
        self.client.force_authenticate(self.plain)
        self.assertEqual(self.client.post('/api/people/kwant/aliases/', {'name': 'Kwancik'}).status_code, 403)

    def test_add_and_remove_alias(self):
        self.client.force_authenticate(self.trusted)
        r = self.client.post('/api/people/kwant/aliases/', {'name': 'Kwancik'})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual([a['slug'] for a in r.json()['aliases']], ['kwancik'])
        self.assertTrue(Tag.objects.filter(slug='kwancik').exists())
        # the same nickname twice → 400; somebody else's nickname → 409
        self.assertEqual(self.client.post('/api/people/kwant/aliases/', {'name': 'kwancik'}).status_code, 400)
        r = self.client.post('/api/people/kwant/aliases/', {'name': 'Hamiltonianka'})
        self.assertEqual(r.status_code, 409)
        self.assertIn('Helena', r.json()['detail'])
        # malformed
        self.assertEqual(self.client.post('/api/people/kwant/aliases/', {'name': 'x'}).status_code, 400)
        self.assertEqual(self.client.post('/api/people/kwant/aliases/', {'name': 'kto@gdzie.pl'}).status_code, 400)
        # remove: an alias with no posts takes its tag with it; one with posts keeps the tag
        r = self.client.delete('/api/people/kwant/aliases/kwancik/')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Tag.objects.filter(slug='kwancik').exists())
        self.assertEqual(self.client.delete('/api/people/kwant/aliases/kwancik/').status_code, 404)
        r = self.client.delete('/api/people/helena/aliases/hamiltonianka/')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Tag.objects.filter(slug='hamiltonianka').exists())
        self.assertEqual(self.client.get('/api/people/helena/').json()['post_count'], 2)
