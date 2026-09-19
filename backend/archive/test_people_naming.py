"""Naming a person into existence — and what the directory does about it.

The bug this feature fixes was not a crash: the editor showed checkboxes for the people who
already existed, the help text said „Brak osoby? Wpisz ją w tagach", and nothing ever
promoted such a tag to a `Person`. So /ludzie stood at the seed data from launch day while
the tag list grew. These tests are about the three things that had to be true before an
ordinary account could be allowed to add a row to a public index of named human beings:

  1. naming somebody who is already there REUSES them (`name_key`), or the directory fills
     up with twins that split one lecturer's posts between two pages;
  2. a proposed person is invisible until a post naming them is published, and invisible in
     a way that does not distinguish „nie ma takiej osoby" from „ta osoba prosiła, żeby jej
     nie było";
  3. the moderator who publishes the post can SEE that they are also publishing the person.
"""
import json
import tempfile

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APITestCase

from .models import Category, Person, Post
from .people import MAX_NEW_PEOPLE_PER_POST, resolve_people
from .test_moderation import make_trusted

# The file cache is shared with a running dev server and with every other test process on
# this machine, so the per-IP post_create throttle leaks between runs. Everything here
# creates posts; an isolated cache is the difference between a suite and a coin flip.
LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), CACHES=LOCMEM)
class Base(APITestCase):
    def setUp(self):
        self.cat = Category.objects.create(slug='memy', name='Memy')
        self.staff = User.objects.create_user('mod', 'm@x.pl', 'haslo12345', is_staff=True)
        self.user = User.objects.create_user('ola', 'o@x.pl', 'haslo12345')
        self.other = User.objects.create_user('bartek', 'b@x.pl', 'haslo12345')
        self.trusted = make_trusted('zaufany')
        self.known = Person.objects.create(slug='kwant-niepewny', name='Kwant Niepewny', degree='dr')

    def as_(self, u):
        self.client.force_authenticate(u)

    def post_payload(self, **kw):
        body = {'title': 'Wpis', 'category': 'memy', 'format': 'text', 'body': 'treść',
                'rights_confirmed': True}
        body.update(kw)
        return body


class ResolvePeopleTests(Base):
    def test_a_typed_name_that_already_exists_is_reused_not_twinned(self):
        # case, diacritics and the title in front all fold away — `name_key`
        for typed in ('Kwant Niepewny', 'KWANT NIEPEWNY', 'dr Kwant Niepewny'):
            people = resolve_people([{'name': typed}], self.user)
            self.assertEqual([p.pk for p in people], [self.known.pk], typed)
        self.assertEqual(Person.objects.count(), 1)

    def test_a_new_name_creates_one_person_credited_to_its_author(self):
        people = resolve_people([{'name': 'prof. dr hab. Anna Nowak', 'role': 'wykładowczyni'}], self.user)
        person = people[0]
        self.assertEqual(person.name, 'Anna Nowak')
        self.assertEqual(person.degree, 'prof. dr hab.')  # peeled off the name, as the directory prints it
        self.assertEqual(person.surname, 'Nowak')
        self.assertEqual(person.role, 'wykładowczyni')
        self.assertEqual(person.created_by, self.user)
        self.assertTrue(person.is_listed)
        self.assertEqual(person.name_key, 'anna nowak')

    def test_the_degree_field_wins_over_a_title_typed_into_the_name(self):
        person = resolve_people([{'name': 'dr Jan Kowalski', 'degree': 'mgr inż.'}], self.user)[0]
        self.assertEqual((person.degree, person.name), ('mgr inż.', 'Jan Kowalski'))

    def test_slugs_and_objects_mix_in_one_list_and_repeats_collapse(self):
        people = resolve_people(['kwant-niepewny', {'name': 'Anna Nowak'}, {'name': 'anna nowak'},
                                 'kwant-niepewny'], self.user)
        self.assertEqual(len(people), 2)
        self.assertEqual(people[0].slug, 'kwant-niepewny')

    def test_at_most_five_new_people_per_post(self):
        ok = [{'name': f'Osoba Numer{i}'} for i in range(MAX_NEW_PEOPLE_PER_POST)]
        self.assertEqual(len(resolve_people(ok, self.user)), MAX_NEW_PEOPLE_PER_POST)
        Person.objects.filter(created_by=self.user).delete()
        with self.assertRaises(Exception) as caught:
            resolve_people(ok + [{'name': 'Jeszcze Jedna'}], self.user)
        self.assertIn('Najwyżej', str(caught.exception))

    def test_a_name_must_be_a_name(self):
        for bad in ('', 'x', 'kto@fuw.edu.pl', 'https://fuw.edu.pl/kto', 'dr hab.', 'a' * 121):
            with self.assertRaises(Exception, msg=bad):
                resolve_people([{'name': bad}], self.user)
        self.assertFalse(Person.objects.filter(created_by=self.user).exists())

    def test_an_unknown_slug_and_an_unlisted_one_are_refused_the_same_way(self):
        hidden = Person.objects.create(slug='cichy', name='Cichy Bohater', is_listed=False)
        messages = []
        for slug in ('nie-ma-takiego', hidden.slug):
            with self.assertRaises(Exception) as caught:
                resolve_people([slug], self.user)
            messages.append(str(caught.exception))
        self.assertEqual(messages[0], messages[1])

    def test_naming_somebody_who_opted_out_does_not_bring_them_back(self):
        """Neither a twin nor a reuse: a row somebody asked to be removed from stays out,
        and the refusal is the same sentence an unknown name gets."""
        Person.objects.create(slug='wycofana', name='Wycofana Osoba', is_listed=False,
                              image_consent='opted_out')
        with self.assertRaises(Exception):
            resolve_people([{'name': 'wycofana osoba'}], self.user)
        self.assertEqual(Person.objects.filter(name_key='wycofana osoba').count(), 1)

    def test_an_anonymous_caller_may_not_mint_a_person(self):
        from django.contrib.auth.models import AnonymousUser
        with self.assertRaises(Exception):
            resolve_people([{'name': 'Anna Nowak'}], AnonymousUser())
        # …but may still name somebody who exists, so a read-only path is not broken by this
        self.assertEqual(resolve_people(['kwant-niepewny'], AnonymousUser())[0].pk, self.known.pk)


class DirectoryVisibilityTests(Base):
    def _submit_with_new_person(self, name='Anna Nowak'):
        self.as_(self.user)
        r = self.client.post('/api/posts/', self.post_payload(people=[{'name': name}]), format='json')
        self.assertEqual(r.status_code, 201, r.data)
        return r.data['slug'], Person.objects.get(name=name)

    def test_a_proposed_person_is_seen_by_their_proposer_and_nobody_else_until_publication(self):
        slug, person = self._submit_with_new_person()
        self.assertEqual(person.created_by, self.user)

        # the proposer sees their own proposal, in the list and on its page
        self.assertIn(person.slug, [p['slug'] for p in self.client.get('/api/people/').data])
        self.assertEqual(self.client.get(f'/api/people/{person.slug}/').status_code, 200)

        # a stranger — logged in or not — gets nothing, and a 404 rather than a 403: for them
        # this person does not exist, which is the honest answer as well as the safe one
        for who in (self.other, None):
            self.client.force_authenticate(who)
            self.assertNotIn(person.slug, [p['slug'] for p in self.client.get('/api/people/').data])
            self.assertEqual(self.client.get(f'/api/people/{person.slug}/').status_code, 404)

        # a moderator publishes the post; now she is simply in the directory, for everybody
        self.as_(self.staff)
        self.assertEqual(self.client.post(f'/api/posts/{slug}/moderate/', {'decision': 'publish'}).status_code, 200)
        self.client.force_authenticate(None)
        row = next(p for p in self.client.get('/api/people/').data if p['slug'] == person.slug)
        self.assertEqual(row['post_count'], 1)
        self.assertEqual(self.client.get(f'/api/people/{person.slug}/').status_code, 200)

    def test_a_rejected_submission_never_puts_the_person_in_the_directory(self):
        slug, person = self._submit_with_new_person()
        self.as_(self.staff)
        self.client.post(f'/api/posts/{slug}/moderate/', {'decision': 'reject', 'note': 'nie'})
        self.client.force_authenticate(None)
        self.assertNotIn(person.slug, [p['slug'] for p in self.client.get('/api/people/').data])

    def test_a_trusted_submitters_person_is_visible_at_once_because_the_post_is(self):
        self.as_(self.trusted)
        r = self.client.post('/api/posts/', self.post_payload(people=[{'name': 'Barbara Bozon'}]), format='json')
        self.assertEqual(r.data['status'], 'published')
        self.client.force_authenticate(None)
        self.assertIn('barbara-bozon', [p['slug'] for p in self.client.get('/api/people/').data])

    def test_a_seeded_person_with_no_posts_is_listed_anyway(self):
        Person.objects.create(slug='portiernia', name='Pani z portierni')  # created_by is NULL
        self.client.force_authenticate(None)
        self.assertIn('portiernia', [p['slug'] for p in self.client.get('/api/people/').data])

    def test_the_editors_typeahead_is_scoped_the_same_way(self):
        _, person = self._submit_with_new_person('Anna Nowak')
        self.as_(self.other)
        self.assertEqual([p['slug'] for p in self.client.get('/api/people/?q=nowak').data], [])
        self.as_(self.user)
        self.assertEqual([p['slug'] for p in self.client.get('/api/people/?q=nowak').data], [person.slug])


class ModeratorCardTests(Base):
    def test_a_proposed_person_is_marked_new_on_the_queue_and_stops_being_new_once_published(self):
        self.as_(self.user)
        slug = self.client.post('/api/posts/', self.post_payload(
            people=['kwant-niepewny', {'name': 'Anna Nowak', 'role': 'wykładowczyni'}]), format='json').data['slug']
        self.as_(self.staff)
        row = next(p for p in self.client.get('/api/posts/queue/').data['results'] if p['slug'] == slug)
        marks = {p['slug']: p['is_new'] for p in row['people']}
        self.assertEqual(marks, {'kwant-niepewny': False, 'anna-nowak': True})

        self.client.post(f'/api/posts/{slug}/moderate/', {'decision': 'publish'})
        # a second post naming her now: she is no longer new to the archive
        self.as_(self.user)
        second = self.client.post('/api/posts/', self.post_payload(
            title='Drugi', people=[{'name': 'Anna Nowak'}]), format='json').data['slug']
        self.as_(self.staff)
        row = next(p for p in self.client.get('/api/posts/queue/').data['results'] if p['slug'] == second)
        self.assertEqual([p['is_new'] for p in row['people']], [False])

    def test_staff_can_drop_or_merge_a_new_person_by_patching_the_post(self):
        self.as_(self.user)
        slug = self.client.post('/api/posts/', self.post_payload(
            people=[{'name': 'Kfant Niepewny'}]), format='json').data['slug']  # a misspelling
        typo = Person.objects.get(name='Kfant Niepewny')

        self.as_(self.staff)
        r = self.client.patch(f'/api/posts/{slug}/', {'people': ['kwant-niepewny']}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual([p['slug'] for p in r.data['people']], ['kwant-niepewny'])
        # the orphan survives the merge — `manage.py sweep_people` is what removes it, so an
        # undo is a click in the admin rather than a restore from backup
        self.assertTrue(Person.objects.filter(pk=typo.pk).exists())

        r = self.client.patch(f'/api/posts/{slug}/', {'people': []}, format='json')
        self.assertEqual(r.data['people'], [])

    def test_a_stranger_cannot_patch_the_people_on_somebody_elses_post(self):
        self.as_(self.user)
        slug = self.client.post('/api/posts/', self.post_payload(people=[{'name': 'Anna Nowak'}]),
                                format='json').data['slug']
        self.as_(self.other)
        self.assertEqual(self.client.patch(f'/api/posts/{slug}/', {'people': []}, format='json').status_code, 404)


class WireShapeTests(Base):
    def test_the_editors_multipart_json_string_is_read_the_same_as_a_json_list(self):
        """What the browser actually sends: one multipart field holding a JSON string."""
        self.as_(self.user)
        r = self.client.post('/api/posts/', {
            'title': 'Z formularza', 'category': 'memy', 'format': 'text', 'body': 'treść',
            'rights_confirmed': 'true',
            'people': json.dumps(['kwant-niepewny', {'name': 'Anna Nowak', 'degree': 'dr'}]),
            'tags': json.dumps(['kolokwium', 'Pasteura 5']),
        }, format='multipart')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(sorted(p['slug'] for p in r.data['people']), ['anna-nowak', 'kwant-niepewny'])
        self.assertEqual(sorted(t['slug'] for t in r.data['tags']), ['kolokwium', 'pasteura-5'])
        self.assertEqual(Person.objects.get(slug='anna-nowak').degree, 'dr')

    def test_the_old_comma_separated_shape_still_works(self):
        """The API is a public surface: a script written against it before the pickers
        existed sent `people=kwant-niepewny,ktos-inny`, and still may."""
        self.as_(self.user)
        r = self.client.post('/api/posts/', self.post_payload(people='kwant-niepewny', tags='sesja, kreda'),
                             format='multipart')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual([p['slug'] for p in r.data['people']], ['kwant-niepewny'])
        self.assertEqual(sorted(t['slug'] for t in r.data['tags']), ['kreda', 'sesja'])

    def test_a_patch_that_does_not_mention_people_leaves_them_alone(self):
        self.as_(self.user)
        slug = self.client.post('/api/posts/', self.post_payload(people=['kwant-niepewny']),
                                format='json').data['slug']
        r = self.client.patch(f'/api/posts/{slug}/', {'title': 'Inny tytuł'}, format='json')
        self.assertEqual([p['slug'] for p in r.data['people']], ['kwant-niepewny'])


class SweepTests(Base):
    def test_sweep_removes_only_proposed_people_with_no_posts_at_all(self):
        from datetime import timedelta
        from io import StringIO
        from django.core.management import call_command
        from django.utils import timezone

        self.as_(self.user)
        slug = self.client.post('/api/posts/', self.post_payload(people=[{'name': 'Anna Nowak'}]),
                                format='json').data['slug']
        orphan = resolve_people([{'name': 'Nikt Znikąd'}], self.user)[0]
        on_a_pending_post = Person.objects.get(name='Anna Nowak')
        old = timezone.now() - timedelta(days=40)
        Person.objects.filter(created_by=self.user).update(created_at=old)

        call_command('sweep_people', stdout=StringIO())
        # the orphan is gone; the person on a post still in the QUEUE is not — the post is
        # the reason to keep the name, whatever state the post is in
        self.assertFalse(Person.objects.filter(pk=orphan.pk).exists())
        self.assertTrue(Person.objects.filter(pk=on_a_pending_post.pk).exists())
        self.assertTrue(Post.objects.filter(slug=slug).exists())
        # and a seeded person with no posts is never swept, however old
        self.assertTrue(Person.objects.filter(pk=self.known.pk).exists())

    def test_a_fresh_proposal_survives_the_sweep(self):
        from io import StringIO
        from django.core.management import call_command
        person = resolve_people([{'name': 'Nikt Znikąd'}], self.user)[0]
        call_command('sweep_people', stdout=StringIO())
        self.assertTrue(Person.objects.filter(pk=person.pk).exists())
