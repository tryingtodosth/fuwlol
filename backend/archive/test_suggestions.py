"""Edit suggestions and the history they leave behind.

The archive's value is other people knowing better — the year is wrong by two, the quote
is misattributed, the LaTeX does not compile. Those people are usually neither the author
nor a moderator, and before this the only channel open to them was "report", which means
"take this down".

What is tested here is mostly the edges, because the happy path is a dictionary: who may
decide, what happens when two people edit the same post, and whether a suggestion is a way
around the rules that guard an ordinary edit. That last one is the reason this file exists
at all — a second way to write to `body` with its own idea of what is valid would quietly
retire the LaTeX guard.
"""
import tempfile

from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import TrustedDomain
from escalation.services import create_escalation
from .latexguard import MAX_POST_CHARS
from .models import Category, EditSuggestion, Post, PostRevision


def make_trusted(username):
    u = User.objects.create_user(username, f'{username}@fuw.edu.pl', 'haslo12345')
    dom, _ = TrustedDomain.objects.get_or_create(domain='fuw.edu.pl',
                                                 defaults={'institution': 'FUW', 'kind': 'fuw'})
    p = u.profile
    p.affiliation_email, p.affiliation_domain, p.verified_at = f'{username}@fuw.edu.pl', dom, timezone.now()
    p.save()
    return u


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class Base(APITestCase):
    def setUp(self):
        # The project's throttles live in a FILE cache that outlives the process, so
        # counters leak between tests and between runs — the second `manage.py test` in an
        # hour would fail with 429 and look like a regression. Clearing is the honest fix;
        # the throttle itself is the thing under test elsewhere.
        from django.core.cache import cache
        cache.clear()
        # A fresh evidence directory per TEST, not per class: each test's transaction rolls
        # back, so SQLite hands out escalation pk=1 again and the on-disk package directory
        # from the previous test is still sitting there. Same reasoning as escalation/tests.py.
        override = override_settings(EVIDENCE_ROOT=tempfile.mkdtemp())
        override.enable()
        self.addCleanup(override.disable)
        self.cat = Category.objects.create(slug='memy', name='Memy')
        self.op = User.objects.create_user('autor', 'a@x.pl', 'haslo12345')
        self.reader = User.objects.create_user('czytelnik', 'c@x.pl', 'haslo12345')
        self.staff = User.objects.create_user('mod', 'm@x.pl', 'haslo12345', is_staff=True)
        self.trusted = make_trusted('zaufany')
        self.post = Post.objects.create(title='Egzamin 2009', category=self.cat,
                                        body='Odpowiedź brzmiała 41.', year=2009,
                                        status='published', submitted_by=self.op)

    def url(self):
        return f'/api/posts/{self.post.slug}/suggestions/'

    def suggest(self, user, changes, rationale='bo tak było naprawdę'):
        self.client.force_authenticate(user)
        return self.client.post(self.url(), {'changes': changes, 'rationale': rationale}, format='json')


class SuggestingTests(Base):
    def test_an_anonymous_visitor_cannot_suggest(self):
        r = self.client.post(self.url(), {'changes': {'year': 2010}, 'rationale': 'x'}, format='json')
        self.assertIn(r.status_code, (401, 403))

    def test_any_logged_in_reader_can_suggest(self):
        """The person who knows the year is wrong is usually not the author."""
        r = self.suggest(self.reader, {'year': 2011})
        self.assertEqual(r.status_code, 201)
        s = EditSuggestion.objects.get()
        self.assertEqual(s.changes, {'year': 2011})
        self.assertEqual(s.base, {'year': 2009})       # what it said when they wrote it
        self.assertEqual(s.status, 'pending')
        self.post.refresh_from_db()
        self.assertEqual(self.post.year, 2009)         # nothing applied yet

    def test_a_reason_is_required(self):
        self.assertEqual(self.suggest(self.reader, {'year': 2011}, rationale='  ').status_code, 400)

    def test_a_change_that_changes_nothing_is_refused(self):
        self.assertEqual(self.suggest(self.reader, {'year': 2009}).status_code, 400)
        self.assertEqual(self.suggest(self.reader, {}).status_code, 400)

    def test_fields_outside_the_allowlist_are_refused(self):
        """`status`, `featured` and `submitted_by` are not editorial opinions."""
        for bad in ({'status': 'published'}, {'featured': True}, {'submitted_by': 1}):
            self.assertEqual(self.suggest(self.reader, bad).status_code, 400)

    def test_the_latex_guard_still_applies(self):
        """A suggestion writes to `body`, so it meets the same guard an edit does —
        otherwise this endpoint would be the way around it."""
        self.assertEqual(self.suggest(self.reader, {'body': r'\def\x{boom}\x'}).status_code, 400)
        self.assertEqual(self.suggest(self.reader, {'body': 'x' * (MAX_POST_CHARS + 1)}).status_code, 400)
        self.assertEqual(self.suggest(self.reader, {'year': 3000}).status_code, 400)   # range check

    def test_one_pending_suggestion_per_person_per_post(self):
        self.assertEqual(self.suggest(self.reader, {'year': 2011}).status_code, 201)
        self.assertEqual(self.suggest(self.reader, {'title': 'Inny'}).status_code, 400)

    def test_an_escalated_post_accepts_nothing(self):
        create_escalation(self.post, self.trusted, 'materiał do NASK')
        self.assertIn(self.suggest(self.reader, {'year': 2011}).status_code, (403, 404))


class DecidingTests(Base):
    def setUp(self):
        super().setUp()
        self.suggest(self.reader, {'year': 2011, 'title': 'Egzamin 2011'})
        self.sug = EditSuggestion.objects.get()

    def decide(self, user, decision, note=''):
        self.client.force_authenticate(user)
        return self.client.post(f'/api/suggestions/{self.sug.pk}/decide/',
                                {'decision': decision, 'note': note}, format='json')

    def test_the_author_can_accept_and_the_old_version_is_kept(self):
        r = self.decide(self.op, 'accept')
        self.assertEqual(r.status_code, 200)
        self.post.refresh_from_db()
        self.assertEqual(self.post.year, 2011)
        self.assertEqual(self.post.title, 'Egzamin 2011')

        rev = PostRevision.objects.get()
        self.assertEqual(rev.data['year'], 2009)            # what it USED to say
        self.assertEqual(rev.data['title'], 'Egzamin 2009')
        self.assertEqual(rev.source, 'suggestion')
        self.assertEqual(rev.changed_by, self.op)

    def test_staff_can_accept_too(self):
        """Authors of folklore go away; the archive does not."""
        self.assertEqual(self.decide(self.staff, 'accept').status_code, 200)

    def test_a_stranger_cannot_accept(self):
        self.assertEqual(self.decide(self.reader, 'accept').status_code, 403)
        self.post.refresh_from_db()
        self.assertEqual(self.post.year, 2009)

    def test_a_trusted_moderator_cannot_accept(self):
        """Deliberate: a suggestion is a claim about content, not about whether content
        may stay up. Trusted means 'may hide things', not 'may rewrite other people'."""
        self.assertEqual(self.decide(self.trusted, 'accept').status_code, 403)

    def test_rejecting_keeps_the_record_and_changes_nothing(self):
        r = self.decide(self.op, 'reject', note='pamiętam inaczej')
        self.assertEqual(r.status_code, 200)
        self.sug.refresh_from_db()
        self.assertEqual(self.sug.status, 'rejected')
        self.assertEqual(self.sug.decision_note, 'pamiętam inaczej')
        self.post.refresh_from_db()
        self.assertEqual(self.post.year, 2009)
        self.assertEqual(PostRevision.objects.count(), 0)

    def test_deciding_twice_is_refused(self):
        self.decide(self.op, 'accept')
        self.assertEqual(self.decide(self.op, 'reject').status_code, 400)

    def test_a_post_that_moved_on_answers_409(self):
        """Accepting a stale diff would silently revert whoever edited in between."""
        self.post.year = 2010
        self.post.save(update_fields=['year'])
        r = self.decide(self.op, 'accept')
        self.assertEqual(r.status_code, 409)
        self.assertIn('year', r.data['fields'])
        self.post.refresh_from_db()
        self.assertEqual(self.post.year, 2010)        # untouched
        self.sug.refresh_from_db()
        self.assertEqual(self.sug.status, 'pending')  # still decidable once looked at

    def test_the_suggester_can_withdraw_their_own(self):
        self.client.force_authenticate(self.reader)
        r = self.client.post(f'/api/suggestions/{self.sug.pk}/withdraw/', {}, format='json')
        self.assertEqual(r.status_code, 200)
        self.sug.refresh_from_db()
        self.assertEqual(self.sug.status, 'withdrawn')

    def test_somebody_else_cannot_withdraw_it(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.post(f'/api/suggestions/{self.sug.pk}/withdraw/', {},
                                          format='json').status_code, 403)


class VisibilityTests(Base):
    def setUp(self):
        super().setUp()
        self.suggest(self.reader, {'year': 2011})

    def test_who_sees_the_suggestions_on_a_post(self):
        self.client.force_authenticate(None)
        self.assertEqual(len(self.client.get(self.url()).data), 0)      # a stranger: none
        self.client.force_authenticate(self.reader)
        self.assertEqual(len(self.client.get(self.url()).data), 1)      # their own
        self.client.force_authenticate(self.op)
        self.assertEqual(len(self.client.get(self.url()).data), 1)      # the author: all
        self.client.force_authenticate(self.staff)
        self.assertEqual(len(self.client.get(self.url()).data), 1)

    def test_a_third_party_sees_nothing_of_somebody_elses_suggestion(self):
        other = User.objects.create_user('ktos', 'k@x.pl', 'haslo12345')
        self.client.force_authenticate(other)
        self.assertEqual(len(self.client.get(self.url()).data), 0)

    def test_the_inbox_shows_what_is_waiting_on_me(self):
        self.client.force_authenticate(self.op)
        self.assertEqual(len(self.client.get('/api/suggestions/').data), 1)
        self.client.force_authenticate(self.trusted)
        self.assertEqual(len(self.client.get('/api/suggestions/').data), 0)


class RevisionTests(Base):
    def test_history_is_not_public(self):
        """A removal request under art. 81 or RODO must not leave the removed thing one
        click away in the diff."""
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(f'/api/posts/{self.post.slug}/revisions/').status_code, (401, 403))
        self.client.force_authenticate(self.reader)
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/revisions/').status_code, 403)
        for who in (self.op, self.trusted, self.staff):
            self.client.force_authenticate(who)
            self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/revisions/').status_code, 200)

    def test_an_ordinary_edit_is_recorded_too(self):
        """History has to cover every change, not only the ones that came from a
        suggestion — otherwise it shows a post springing into being fully formed."""
        self.post.status = 'pending'
        self.post.save(update_fields=['status'])
        self.client.force_authenticate(self.op)
        r = self.client.patch(f'/api/posts/{self.post.slug}/',
                              {'title': 'Poprawiony tytuł'}, format='json')
        self.assertEqual(r.status_code, 200)
        rev = PostRevision.objects.get()
        self.assertEqual(rev.data['title'], 'Egzamin 2009')
        self.assertEqual(rev.source, 'author')

    def test_an_edit_that_changes_nothing_writes_no_revision(self):
        self.post.status = 'pending'
        self.post.save(update_fields=['status'])
        self.client.force_authenticate(self.op)
        self.client.patch(f'/api/posts/{self.post.slug}/', {'title': self.post.title}, format='json')
        self.assertEqual(PostRevision.objects.count(), 0)
