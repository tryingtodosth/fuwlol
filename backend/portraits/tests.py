r"""What the portrait gallery must never do, mostly.

The happy path here is three lines long and the interesting half is everywhere else: a
person who never agreed, a person who agreed and then changed their mind, a file that is
not a photograph, a vote cast twice, two moderators pressing the same button. Those are
the cases this file pins down, because they are the ones with a statute behind them
(art. 81 pr. aut. — the right to one's own likeness) rather than a preference.

The cache is swapped for an in-memory one: throttle counters live in a FILE cache shared
with the running dev server (backend/cachedata), so a test suite that used the real one
would both flake against its own history and spend the developer's upload budget.
"""
import io
import tempfile
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APITestCase

from archive.models import Person
from archive.test_moderation import make_trusted

from .models import Portrait, PortraitAction, PortraitVote
from . import rules

TEST_SETTINGS = dict(
    MEDIA_ROOT=tempfile.mkdtemp(),
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)


def png_bytes(color=(10, 120, 200), size=(16, 16)):
    out = io.BytesIO()
    Image.new('RGB', size, color).save(out, format='PNG')
    return out.getvalue()


def a_png(name='zdjecie.png', color=(10, 120, 200)):
    return SimpleUploadedFile(name, png_bytes(color), content_type='image/png')


@override_settings(**TEST_SETTINGS)
class PortraitGalleryTests(APITestCase):
    def setUp(self):
        # The throttle counters live in the cache, and the in-memory one outlives a single
        # test the way the file one outlives a restart — while `self.plain` gets the same
        # primary key in every test, which is what the throttle keys on. Without this, the
        # fourth test in the class starts halfway through an hourly upload budget.
        cache.clear()
        self.person = Person.objects.create(slug='kwant-niepewny', name='Kwant Niepewny',
                                            degree='dr', sex='m', image_consent='granted')
        self.silent = Person.objects.create(slug='cichy-wykladowca', name='Cichy Wykładowca',
                                            image_consent='unknown')
        self.staff = User.objects.create_user('mod', 'm@x.pl', 'haslo12345', is_staff=True)
        self.trusted = make_trusted('zaufany')
        self.plain = User.objects.create_user('ola', 'o@x.pl', 'haslo12345')
        self.other = User.objects.create_user('tomek', 't@x.pl', 'haslo12345')

    # --- helpers -----------------------------------------------------------------------
    def url(self, person=None):
        return f'/api/people/{(person or self.person).slug}/portraits/'

    def as_(self, user):
        self.client.force_authenticate(user)

    def upload(self, person=None, user=None, name='zdjecie.png', rights='true', **extra):
        if user is not None:
            self.as_(user)
        data = {'file': a_png(name), 'rights_confirmed': rights}
        data.update(extra)
        return self.client.post(self.url(person), data, format='multipart')

    def publish(self, person=None, user=None, **kw):
        """A published portrait, whoever uploads it — the trusted tier skips the queue."""
        r = self.upload(person=person, user=user or self.trusted, **kw)
        self.assertEqual(r.status_code, 201, r.data)
        return Portrait.objects.get(pk=r.data['id'])

    # --- consent -----------------------------------------------------------------------
    def test_a_person_who_never_agreed_has_no_gallery_and_the_page_is_told_why(self):
        """The refusal carries its reason and the reason carries the statute — 'nie można'
        with no explanation is how a reader concludes the site is broken."""
        self.as_(self.plain)
        body = self.client.get(self.url(self.silent)).data
        self.assertEqual(body['consent'], 'unknown')
        self.assertFalse(body['can_upload'])
        self.assertIn('art. 81', body['upload_block_reason'])
        self.assertIn('/ludzie/zgoda', body['upload_block_reason'])
        self.assertEqual(body['items'], [])
        self.assertIsNone(body['current'])

        r = self.upload(person=self.silent, user=self.plain)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data['detail'], rules.NO_CONSENT)
        self.assertEqual(Portrait.objects.count(), 0)

    def test_an_anonymous_visitor_is_asked_to_log_in_rather_than_refused_blankly(self):
        self.as_(None)
        body = self.client.get(self.url()).data
        self.assertEqual(body['upload_block_reason'], rules.LOGIN_TO_UPLOAD)
        r = self.upload(user=None)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data['detail'], rules.LOGIN_TO_UPLOAD)

    def test_a_person_who_is_not_listed_does_not_exist_here(self):
        self.person.is_listed = False
        self.person.save()
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    # --- the queue vs the trusted tier --------------------------------------------------
    def test_a_plain_upload_waits_and_a_trusted_one_goes_straight_up(self):
        r = self.upload(user=self.plain)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['status'], 'pending')

        r = self.upload(user=self.trusted)
        self.assertEqual(r.data['status'], 'published')
        # …and even the queue-less publication leaves an audit line
        self.assertEqual(PortraitAction.objects.filter(portrait_id=r.data['id'],
                                                       action='publish').count(), 1)

    def test_a_pending_portrait_is_visible_to_its_uploader_and_the_queue_and_nobody_else(self):
        pending = Portrait.objects.get(pk=self.upload(user=self.plain).data['id'])
        # the default page is `status=published`, so it is empty for everybody — asking for
        # the pending ones is what tells the three callers apart
        for who in (None, self.other, self.plain, self.trusted):
            self.as_(who)
            self.assertEqual(self.client.get(self.url()).data['items'], [])
        self.as_(None)
        self.assertEqual(self.client.get(self.url() + '?status=pending').data['items'], [])
        self.as_(self.other)
        self.assertEqual(self.client.get(self.url() + '?status=pending').data['items'], [])
        self.as_(self.plain)
        mine = self.client.get(self.url() + '?status=pending').data['items']
        self.assertEqual([i['id'] for i in mine], [pending.pk])
        self.assertEqual(mine[0]['status'], 'pending')
        # `mine=1` alone widens the status, so "which of mine got through" has an answer
        self.assertEqual([i['id'] for i in self.client.get(self.url() + '?mine=1').data['items']], [pending.pk])
        self.as_(self.trusted)
        self.assertEqual([i['id'] for i in self.client.get(self.url() + '?status=pending').data['items']],
                         [pending.pk])
        # a pending photograph is nobody's profile picture, not even its uploader's
        self.assertIsNone(self.client.get(self.url()).data['current'])

    def test_the_uploader_learns_that_their_photograph_was_rejected(self):
        """A rejected row is kept, not deleted — and the person who sent it in can see
        that a decision was made rather than watching it vanish."""
        p = Portrait.objects.get(pk=self.upload(user=self.plain).data['id'])
        self.as_(self.trusted)
        self.client.post(f'/api/portraits/{p.pk}/moderate/', {'decision': 'reject', 'note': 'nie ta osoba'})
        self.as_(self.plain)
        items = self.client.get(self.url() + '?mine=1').data['items']
        self.assertEqual(items[0]['status'], 'rejected')
        self.as_(self.other)
        self.assertEqual(self.client.get(self.url() + '?status=rejected').data['items'], [])

    # --- the vote -----------------------------------------------------------------------
    def test_one_vote_per_person_moves_and_toggles(self):
        a = self.publish(name='a.png')
        b = self.publish(name='b.png')
        self.as_(self.plain)

        r = self.client.post(f'/api/portraits/{a.pk}/vote/')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data['votes'], r.data['my_vote'], r.data['current_id']), (1, True, a.pk))

        # the same photograph again takes the vote back
        r = self.client.post(f'/api/portraits/{a.pk}/vote/')
        self.assertEqual((r.data['votes'], r.data['my_vote']), (0, False))

        # a different photograph of the SAME person moves the one vote rather than adding
        self.client.post(f'/api/portraits/{a.pk}/vote/')
        r = self.client.post(f'/api/portraits/{b.pk}/vote/')
        self.assertEqual((r.data['votes'], r.data['my_vote'], r.data['current_id']), (1, True, b.pk))
        self.assertEqual(PortraitVote.objects.filter(user=self.plain).count(), 1)
        self.assertEqual(rules.current_portrait(self.person).pk, b.pk)

    def test_the_winner_is_the_most_voted_and_a_tie_goes_to_the_oldest(self):
        first = self.publish(name='a.png')
        second = self.publish(name='b.png')
        # nobody has voted: the oldest is the profile photograph
        self.assertEqual(rules.current_portrait(self.person).pk, first.pk)
        # one vote each: still a tie, still the oldest
        PortraitVote.objects.create(portrait=first, user=self.plain)
        PortraitVote.objects.create(portrait=second, user=self.other)
        self.assertEqual(rules.current_portrait(self.person).pk, first.pk)
        # two against one: the vote wins over age
        PortraitVote.objects.create(portrait=second, user=self.staff)
        self.assertEqual(rules.current_portrait(self.person).pk, second.pk)
        self.as_(None)
        self.assertEqual(self.client.get(self.url()).data['current']['id'], second.pk)

    def test_a_vote_needs_an_account_a_published_photograph_and_a_living_gallery(self):
        published = self.publish()
        pending = Portrait.objects.get(pk=self.upload(user=self.plain).data['id'])
        self.as_(None)
        self.assertIn(self.client.post(f'/api/portraits/{published.pk}/vote/').status_code, (401, 403))
        # a photograph the caller may not see is a 404, not a 403: for them it is not there
        self.as_(self.other)
        self.assertEqual(self.client.post(f'/api/portraits/{pending.pk}/vote/').status_code, 404)
        # the trusted tier CAN see the queue, so for them the honest answer is the reason
        self.as_(self.trusted)
        r = self.client.post(f'/api/portraits/{pending.pk}/vote/')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data['detail'], rules.ONLY_PUBLISHED_VOTES)

    # --- withdrawal ----------------------------------------------------------------------
    def test_withdrawing_consent_empties_the_gallery_at_once_and_deletes_nothing(self):
        """The whole point of `visible_q`: no job runs, no rows are touched, and the next
        request — from anybody, including staff — sees an empty gallery and no profile
        photograph."""
        portrait = self.publish()
        PortraitVote.objects.create(portrait=portrait, user=self.plain)
        self.person.image_consent = 'refused'
        self.person.save(update_fields=['image_consent'])

        for who in (None, self.plain, self.trusted, self.staff):
            self.as_(who)
            body = self.client.get(self.url()).data
            self.assertEqual(body['items'], [], f'widoczne dla {who}')
            self.assertIsNone(body['current'])
        self.assertTrue(Portrait.objects.filter(pk=portrait.pk).exists())
        self.assertTrue(Portrait.objects.get(pk=portrait.pk).file)

        self.as_(self.plain)
        r = self.client.post(f'/api/portraits/{portrait.pk}/vote/')
        self.assertEqual(r.status_code, 404)  # not visible any more, so it does not exist
        self.as_(self.trusted)
        self.assertEqual(self.client.get('/api/portraits/queue/').data['items'], [])

    def test_an_opt_out_takes_the_gallery_with_the_entry(self):
        portrait = self.publish()
        self.person.image_consent, self.person.is_listed = 'opted_out', False
        self.person.save()
        self.assertIsNone(rules.current_portrait(self.person))
        self.assertEqual(self.client.get(self.url()).status_code, 404)
        self.assertTrue(Portrait.objects.filter(pk=portrait.pk).exists())

    # --- moderation -----------------------------------------------------------------------
    def test_every_transition_is_audited_and_the_same_decision_twice_is_409(self):
        portrait = Portrait.objects.get(pk=self.upload(user=self.plain).data['id'])
        self.as_(self.trusted)
        mod = f'/api/portraits/{portrait.pk}/moderate/'

        r = self.client.post(mod, {'decision': 'publish', 'note': 'ładne'})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['status'], 'published')
        # the world moved: 409, not 400 — the request was fine, the state was not
        self.assertEqual(self.client.post(mod, {'decision': 'publish'}).status_code, 409)

        self.assertEqual(self.client.post(mod, {'decision': 'hide', 'note': 'prosiła osoba'}).data['status'], 'hidden')
        self.as_(None)
        self.assertEqual(self.client.get(self.url()).data['items'], [])
        self.as_(self.trusted)
        self.assertEqual(self.client.post(mod, {'decision': 'restore'}).data['status'], 'published')
        self.assertEqual(self.client.post(mod, {'decision': 'wysadzić'}).status_code, 400)

        actions = list(PortraitAction.objects.filter(portrait=portrait).order_by('id')
                       .values_list('action', 'previous_status'))
        self.assertEqual(actions, [('publish', 'pending'), ('hide', 'published'), ('restore', 'hidden')])
        self.assertEqual(PortraitAction.objects.filter(portrait=portrait).first().actor, self.trusted)

    def test_a_photograph_cannot_be_published_once_the_consent_behind_it_is_gone(self):
        """An id in a URL never meets a queryset filter, so the rule has to be asked again
        at the moment of the decision — a portrait can wait a week in a queue and the
        person can change their mind on the Tuesday."""
        portrait = Portrait.objects.get(pk=self.upload(user=self.plain).data['id'])
        self.person.image_consent = 'refused'
        self.person.save(update_fields=['image_consent'])
        self.as_(self.trusted)
        mod = f'/api/portraits/{portrait.pk}/moderate/'
        r = self.client.post(mod, {'decision': 'publish'})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data['detail'], rules.PUBLISH_NEEDS_CONSENT)
        # taking it DOWN is never blocked by anything
        self.assertEqual(self.client.post(mod, {'decision': 'reject'}).status_code, 200)

    def test_moderating_and_the_queue_are_the_trusted_tier_only(self):
        portrait = self.publish()
        for user, expected in ((None, (401, 403)), (self.plain, (403,))):
            self.as_(user)
            self.assertIn(self.client.get('/api/portraits/queue/').status_code, expected)
            self.assertIn(self.client.post(f'/api/portraits/{portrait.pk}/moderate/',
                                           {'decision': 'hide'}).status_code, expected)
        self.assertEqual(Portrait.objects.get(pk=portrait.pk).status, 'published')

    def test_the_queue_carries_the_person_each_photograph_is_of(self):
        other_person = Person.objects.create(slug='helena', name='Helena Hamiltonian',
                                             degree='prof. dr hab.', image_consent='granted')
        self.upload(user=self.plain)
        self.upload(person=other_person, user=self.plain, name='b.png')
        self.publish()  # published, so NOT in the queue
        self.as_(self.trusted)
        body = self.client.get('/api/portraits/queue/').data
        rows = body['items']
        self.assertEqual((len(rows), body['count'], body['next']), (2, 2, None))
        self.assertEqual({r['person']['slug'] for r in rows}, {'kwant-niepewny', 'helena'})
        self.assertEqual(rows[1]['person']['full_name'], 'prof. dr hab. Helena Hamiltonian')
        self.assertTrue(all(r['status'] == 'pending' for r in rows))

    # --- the bytes ---------------------------------------------------------------------------
    def test_only_an_image_gets_in_whatever_it_is_called(self):
        self.as_(self.plain)
        pdf = SimpleUploadedFile('skan.pdf', b'%PDF-1.4 to nie jest portret', content_type='application/pdf')
        r = self.client.post(self.url(), {'file': pdf, 'rights_confirmed': 'true'}, format='multipart')
        self.assertEqual(r.status_code, 400)
        self.assertIn(rules.NOT_AN_IMAGE, str(r.data))
        # …and a name is not evidence: a .png that Pillow cannot decode is refused too
        liar = SimpleUploadedFile('mem.png', b'MZ\x90\x00 to jest plik wykonywalny', content_type='image/png')
        r = self.client.post(self.url(), {'file': liar, 'rights_confirmed': 'true'}, format='multipart')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Portrait.objects.count(), 0)

    def test_the_rights_declaration_is_not_optional(self):
        self.as_(self.plain)
        r = self.client.post(self.url(), {'file': a_png()}, format='multipart')
        self.assertEqual(r.status_code, 400)
        self.assertIn(rules.RIGHTS_REQUIRED, str(r.data))
        r = self.client.post(self.url(), {'file': a_png(), 'rights_confirmed': 'false'}, format='multipart')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Portrait.objects.count(), 0)

    def test_a_photograph_is_stored_without_the_metadata_it_arrived_with(self):
        """A portrait is the worst possible carrier of EXIF: it is a picture of a person,
        taken somewhere, at a time, on a device — all four of which the file will happily
        say out loud. The stored bytes are a re-save, and `sha256` is of THOSE bytes."""
        exif = Image.Exif()
        exif[0x010F] = 'FUW-APARAT-TESTOWY'   # Make
        exif[0x0110] = 'Pasteura 5'           # Model
        out = io.BytesIO()
        Image.new('RGB', (12, 12), (200, 30, 30)).save(out, format='JPEG', exif=exif.tobytes())
        original = out.getvalue()
        self.assertIn(b'FUW-APARAT-TESTOWY', original)

        self.as_(self.plain)
        r = self.client.post(self.url(), {'file': SimpleUploadedFile('portret.jpg', original,
                                                                     content_type='image/jpeg'),
                                          'rights_confirmed': 'true'}, format='multipart')
        self.assertEqual(r.status_code, 201, r.data)
        portrait = Portrait.objects.get(pk=r.data['id'])
        stored = portrait.file.read()
        self.assertNotIn(b'FUW-APARAT-TESTOWY', stored)
        self.assertNotIn(b'Pasteura 5', stored)
        self.assertEqual(dict(Image.open(io.BytesIO(stored)).getexif()), {})
        import hashlib
        self.assertEqual(portrait.sha256, hashlib.sha256(stored).hexdigest())
        # the uploader's own filename is kept as text and never as the stored name
        self.assertEqual(portrait.original_name, 'portret.jpg')
        self.assertNotIn('portret', portrait.file.name)

    def test_the_caps_are_stated_rather_than_silently_enforced(self):
        for i in range(rules.MAX_PENDING_PER_UPLOADER):
            self.assertEqual(self.upload(user=self.plain, name=f'{i}.png').status_code, 201)
        r = self.upload(user=self.plain, name='jeszcze.png')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data['detail'], rules.PENDING_CAP)
        # somebody else is not out of room because this uploader is
        self.assertEqual(self.upload(user=self.other, name='inny.png').status_code, 201)
        # and the page says so before the form is even drawn
        self.as_(self.plain)
        self.assertEqual(self.client.get(self.url()).data['upload_block_reason'], rules.PENDING_CAP)

    def test_the_caption_and_the_provenance_survive_the_round_trip(self):
        r = self.upload(user=self.trusted, caption='Przy tablicy',
                        source_note='Zdjęcie własne, 2019, za zgodą')
        self.assertEqual(r.data['caption'], 'Przy tablicy')
        self.assertEqual(r.data['source_note'], 'Zdjęcie własne, 2019, za zgodą')
        self.assertEqual(r.data['uploaded_by'], 'zaufany')
        self.assertTrue(r.data['url'].startswith('http'))
        self.assertTrue(r.data['can_moderate'])
        self.as_(self.plain)
        item = self.client.get(self.url()).data['items'][0]
        self.assertFalse(item['can_moderate'])
        self.assertFalse(item['my_vote'])
        self.assertEqual(item['votes'], 0)


@override_settings(**TEST_SETTINGS)
class GalleryPagingTests(APITestCase):
    """Sorting, filtering and paging — and the two things they must never touch.

    A filter is the caller's question and `visible_q` is our answer to it, so the tests
    that matter here are the ones where those two disagree: an anonymous visitor asking
    for `status=pending`, a plain user asking for somebody else's queue. Both come back
    empty rather than refused, because for that caller those rows are not there.

    The other invariant is `current`. The profile photograph is the winner of the whole
    gallery; a reader on page two of "najstarsze" has not changed who that is, and a page
    that recomputed it from its own slice would put a different face on the header
    depending on how the reader was sorting.
    """

    def setUp(self):
        cache.clear()
        self.person = Person.objects.create(slug='kwant-niepewny', name='Kwant Niepewny',
                                            degree='dr', image_consent='granted')
        self.trusted = make_trusted('zaufany')
        self.plain = User.objects.create_user('ola', 'o@x.pl', 'haslo12345')
        self.other = User.objects.create_user('tomek', 't@x.pl', 'haslo12345')
        # Five published, made oldest-first with a known order, plus votes on the third so
        # that "most votes" and "oldest" are different answers.
        self.pub = [self._make('published', i) for i in range(5)]
        PortraitVote.objects.create(portrait=self.pub[2], user=self.plain)
        PortraitVote.objects.create(portrait=self.pub[2], user=self.other)
        PortraitVote.objects.create(portrait=self.pub[4], user=self.trusted)
        self.pending_mine = self._make('pending', 5, user=self.plain)
        self.pending_theirs = self._make('pending', 6, user=self.other)
        self.hidden = self._make('hidden', 7)
        self.rejected_mine = self._make('rejected', 8, user=self.plain)

    def _make(self, status, i, user=None):
        return Portrait.objects.create(
            person=self.person, uploaded_by=user or self.trusted,
            uploaded_by_username=(user or self.trusted).username, file=a_png(f'{i}.png'),
            original_name=f'{i}.png', caption=f'zdjęcie {i}', rights_confirmed=True,
            status=status, created_at=timezone.now() - timedelta(days=20 - i))

    def url(self, query=''):
        return f'/api/people/{self.person.slug}/portraits/{query}'

    def as_(self, user):
        self.client.force_authenticate(user)

    def ids(self, query='', user=None):
        self.as_(user)
        return [i['id'] for i in self.client.get(self.url(query)).data['items']]

    # --- sorting ---------------------------------------------------------------------
    def test_the_three_orders_are_three_different_answers(self):
        by_votes = [self.pub[2].pk, self.pub[4].pk, self.pub[0].pk, self.pub[1].pk, self.pub[3].pk]
        self.assertEqual(self.ids(), by_votes)                     # default
        self.assertEqual(self.ids('?sort=votes'), by_votes)
        self.assertEqual(self.ids('?sort=old'), [p.pk for p in self.pub])
        self.assertEqual(self.ids('?sort=new'), [p.pk for p in reversed(self.pub)])

    def test_a_misspelt_sort_is_a_400_rather_than_a_quiet_default(self):
        self.as_(None)
        r = self.client.get(self.url('?sort=newest'))
        self.assertEqual(r.status_code, 400)
        self.assertIn('votes', str(r.data))
        self.assertEqual(self.client.get(self.url('?status=zniknione')).status_code, 400)

    # --- filtering -------------------------------------------------------------------
    def test_a_filter_narrows_and_never_widens(self):
        """`status=pending` is a legitimate question from anybody; the answer differs."""
        self.assertEqual(self.ids('?status=pending', None), [])
        self.assertEqual(self.ids('?status=pending', self.plain), [self.pending_mine.pk])
        self.assertEqual(sorted(self.ids('?status=pending', self.trusted)),
                         sorted([self.pending_mine.pk, self.pending_theirs.pk]))
        self.assertEqual(self.ids('?status=hidden', None), [])
        self.assertEqual(self.ids('?status=hidden', self.trusted), [self.hidden.pk])
        # rejected is the uploader's own business and nobody else's, moderators included
        self.assertEqual(self.ids('?status=rejected', self.plain), [self.rejected_mine.pk])
        self.assertEqual(self.ids('?status=rejected', self.trusted), [])

    def test_status_all_is_still_only_what_the_caller_may_see(self):
        self.assertEqual(sorted(self.ids('?status=all&limit=60', None)),
                         sorted(p.pk for p in self.pub))
        self.assertEqual(sorted(self.ids('?status=all&limit=60', self.plain)),
                         sorted([p.pk for p in self.pub] + [self.pending_mine.pk, self.rejected_mine.pk]))
        self.assertEqual(sorted(self.ids('?status=all&limit=60', self.trusted)),
                         sorted([p.pk for p in self.pub]
                                + [self.pending_mine.pk, self.pending_theirs.pk, self.hidden.pk]))

    def test_mine_is_my_uploads_at_every_stage_and_nothing_for_a_stranger(self):
        self.assertEqual(sorted(self.ids('?mine=1&limit=60', self.plain)),
                         sorted([self.pending_mine.pk, self.rejected_mine.pk]))
        # an explicit status still wins over the widening `mine` does on its own
        self.assertEqual(self.ids('?mine=1&status=published', self.plain), [])
        self.assertEqual(self.ids('?mine=1', None), [])  # nobody is anonymous's own

    # --- paging ------------------------------------------------------------------------
    def test_count_and_next_walk_the_whole_gallery_exactly_once(self):
        self.as_(None)
        seen, url, pages = [], self.url('?sort=old&limit=2'), 0
        while url is not None:
            body = self.client.get(url).data
            self.assertEqual(body['count'], 5)
            self.assertEqual(body['limit'], 2)
            seen += [i['id'] for i in body['items']]
            url, pages = body['next'], pages + 1
        self.assertEqual(seen, [p.pk for p in self.pub])
        self.assertEqual(pages, 3)

    def test_next_carries_the_question_it_was_asked(self):
        self.as_(self.trusted)
        body = self.client.get(self.url('?status=pending&sort=old&limit=1')).data
        self.assertEqual((body['count'], body['status'], body['sort']), (2, 'pending', 'old'))
        self.assertIn('status=pending', body['next'])
        self.assertIn('offset=1', body['next'])
        second = self.client.get(body['next']).data
        self.assertEqual([i['id'] for i in second['items']], [self.pending_theirs.pk])
        self.assertIsNone(second['next'])

    def test_the_paging_parameters_refuse_nonsense_and_clamp_greed(self):
        self.as_(None)
        self.assertEqual(self.client.get(self.url('?offset=-1')).status_code, 400)
        self.assertEqual(self.client.get(self.url('?limit=0')).status_code, 400)
        self.assertEqual(self.client.get(self.url('?limit=-5')).status_code, 400)
        self.assertEqual(self.client.get(self.url('?offset=dużo')).status_code, 400)
        # asking for more than we serve is not malformed — it is answered with what we serve
        self.assertEqual(self.client.get(self.url('?limit=1000')).data['limit'], rules.MAX_LIMIT)
        # past the end is an empty page, not an error: a reader can hold a stale link
        past = self.client.get(self.url('?offset=99')).data
        self.assertEqual((past['items'], past['count'], past['next']), ([], 5, None))

    def test_the_default_page_is_twelve(self):
        self.as_(None)
        self.assertEqual(self.client.get(self.url()).data['limit'], rules.DEFAULT_LIMIT)

    # --- what paging must not touch -------------------------------------------------
    def test_current_is_the_winner_of_the_gallery_not_of_the_page(self):
        winner = self.pub[2].pk
        for query in ('', '?sort=old', '?sort=new&offset=4&limit=1', '?status=pending',
                      '?mine=1', '?status=all&limit=1'):
            for who in (None, self.plain, self.trusted):
                self.as_(who)
                body = self.client.get(self.url(query)).data
                self.assertEqual(body['current']['id'], winner, f'{query} / {who}')

    # --- the queue --------------------------------------------------------------------
    def test_the_queue_sorts_filters_by_person_and_pages(self):
        other_person = Person.objects.create(slug='helena', name='Helena Hamiltonian',
                                             image_consent='granted')
        far = Portrait.objects.create(person=other_person, uploaded_by=self.plain,
                                      uploaded_by_username='ola', file=a_png('h.png'),
                                      original_name='h.png', rights_confirmed=True, status='pending',
                                      created_at=timezone.now())
        self.as_(self.trusted)
        oldest_first = [self.pending_mine.pk, self.pending_theirs.pk, far.pk]
        body = self.client.get('/api/portraits/queue/').data
        self.assertEqual([i['id'] for i in body['items']], oldest_first)
        self.assertEqual((body['count'], body['sort'], body['next']), (3, 'old', None))
        self.assertEqual([i['id'] for i in self.client.get('/api/portraits/queue/?sort=new').data['items']],
                         list(reversed(oldest_first)))
        one = self.client.get('/api/portraits/queue/?person=helena').data
        self.assertEqual(([i['id'] for i in one['items']], one['count'], one['person']),
                         ([far.pk], 1, 'helena'))
        page = self.client.get('/api/portraits/queue/?limit=2').data
        self.assertEqual((len(page['items']), page['count']), (2, 3))
        self.assertIn('offset=2', page['next'])
        self.assertEqual(self.client.get('/api/portraits/queue/?sort=oldest').status_code, 400)
