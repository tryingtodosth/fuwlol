r"""The portrait rules, in one place — and there is exactly one place on purpose.

Four endpoints ask questions about portraits (the gallery, the upload, the vote, the
moderation queue), and three of them can be reached with an id in the URL, which means no
queryset filter runs for them at all. An endpoint that re-derives "may this be shown" is
how two surfaces start disagreeing about somebody's face, so every one of them calls into
this module and none of them decides anything itself.

The shape of the answers follows the house rule that **a refusal carries its reason**:
`upload_block_reason` and `vote_block_reason` return a Polish sentence, not a boolean.
"you are not logged in", "this person said no" and "your three photos are still in the
queue" are the same `False` to a caller and three completely different things to a reader,
and the frontend prints whichever one came back.

**Consent is a queryset filter, not a cron job.** `visible_q` starts from
`person__image_consent == 'granted'` AND `person__is_listed`, so the instant somebody's
entry is set to 'refused' or 'opted_out' — in the admin, or by the person themself through
the claims flow — every gallery read in this app matches zero rows. Nothing has to run;
nothing can be forgotten; there is no window in which the photographs are still up because
a job has not fired yet. The rows and the files stay (a decision is kept, see models.py),
they simply stop being reachable. `moderate` re-checks the same thing before it may put a
portrait back up, because an id in a URL never meets a filter.
"""
import hashlib

from django.db import transaction
from django.db.models import Count, Q
from rest_framework.exceptions import PermissionDenied, ValidationError

from archive.moderation import is_trusted
# The archive's own 409 ("the world moved"), reused rather than defined a third time.
from archive.people import Conflict
from archive.validators import kind_for, strip_image_metadata

from .models import Portrait, PortraitAction, PortraitVote

# How many photographs of one person one account may have waiting for a moderator at once.
# Not a spam limit so much as a fairness one: three is enough to offer a choice, and a
# queue of thirty from one uploader is a queue nobody works through.
MAX_PENDING_PER_UPLOADER = 3
# And how many may be live at once for one person. Raised from 30 to 100 when the gallery
# learnt to paginate: the old number was doing two jobs, and only one of them was real.
# "The page stops loading" stopped being true the moment a request returns twelve rows
# instead of all of them — but "a vote across an unbounded pile stops meaning anything"
# is still true, and so is the moderator time each photograph costs. A hundred is where a
# gallery of one person stops being a gallery and starts being somebody's camera roll.
MAX_PUBLISHED_PER_PERSON = 100

CONSENT_PAGE = '/ludzie/zgoda'
LOGIN_TO_UPLOAD = 'Zaloguj się, żeby dodać zdjęcie.'
LOGIN_TO_VOTE = 'Zaloguj się, żeby zagłosować.'
NO_CONSENT = ('Ta osoba nie wyraziła zgody na publikację wizerunku (art. 81 pr. aut.) — '
              f'zdjęć nie przyjmujemy. Jak to działa: {CONSENT_PAGE}')
GALLERY_OFF = ('Galeria tej osoby jest wyłączona — nie ma zgody na publikację wizerunku '
               '(art. 81 pr. aut.).')
PENDING_CAP = (f'Masz już {MAX_PENDING_PER_UPLOADER} zdjęcia tej osoby w kolejce. '
               'Poczekaj na decyzję moderacji — to nie jest konkurs na liczbę zgłoszeń.')
PUBLISHED_CAP = (f'W galerii tej osoby jest już {MAX_PUBLISHED_PER_PERSON} zdjęć — '
                 'komplet. Zagłosuj na któreś z nich albo poczekaj, aż któreś zniknie.')
BAD_PAGING = 'Parametry stronicowania muszą być liczbami całkowitymi nieujemnymi.'
BAD_LIMIT = 'Limit musi być większy od zera.'
ONLY_PUBLISHED_VOTES = 'Głosować można tylko na opublikowane zdjęcia.'
NOT_AN_IMAGE = 'Portret musi być obrazem (JPG, PNG, GIF, WebP).'
RIGHTS_REQUIRED = 'Bez tego oświadczenia nie przyjmujemy zdjęcia.'
UNKNOWN_DECISION = 'Nieznana decyzja.'
PUBLISH_NEEDS_CONSENT = ('Nie można opublikować zdjęcia osoby, która nie potwierdziła zgody '
                         'na wizerunek (art. 81 pr. aut.).')

# How a gallery may be ordered. `votes` is the gallery's own order and the one
# `current_portrait` reads the winner off, so it leads with the vote count and falls back
# to age — the same tie-break, in one place, used by both.
SORT_ORDERS = {
    'votes': ('-vote_count', 'created_at', 'id'),
    'new': ('-created_at', '-id'),
    'old': ('created_at', 'id'),
}
# The statuses a caller may ASK for. What they actually get is this intersected with
# `visible_q`, which is why 'pending' is a legitimate thing for anybody to ask: a plain
# user gets their own, a moderator gets the queue, and an anonymous visitor gets nothing
# at all rather than a refusal. The filter narrows; it never widens.
STATUS_FILTERS = ('published', 'pending', 'hidden', 'rejected', 'all')
DEFAULT_STATUS = 'published'
# Twelve is two rows of the compact strip on a phone and one on a desktop; sixty is the
# most one request will serve, because past that the page is paying for rows nobody has
# scrolled to yet.
DEFAULT_LIMIT = 12
MAX_LIMIT = 60

# What each decision means as a target state. A dict rather than a chain of ifs because
# "already in that state" is then one comparison instead of four, and 409 is what the
# caller gets — the world moved, their request was not malformed.
DECISION_TARGET = {'publish': 'published', 'reject': 'rejected',
                   'hide': 'hidden', 'restore': 'published'}
# The decisions that put a photograph in front of the public. These are the ones that have
# to ask about consent again; taking something DOWN is never blocked by anything.
PUBLISHING_DECISIONS = ('publish', 'restore')


# --- who is who ------------------------------------------------------------------------

def _authenticated(user):
    return user is not None and getattr(user, 'is_authenticated', False)


def can_moderate(user):
    """The trusted tier, exactly as everywhere else in this project (a confirmed
    FUW/UW/PAN address, or staff). Portraits get no tier of their own: the people who can
    take a meme down are the people who can take a photograph of a colleague down, and
    inventing a fourth tier for one feature is how a permission model stops being
    explainable."""
    return is_trusted(user)


def consent_granted(person):
    """The one question art. 81 asks, and the one `visible_q` is built on. `is_listed` is
    part of it because an opt-out sets both — somebody who asked to leave the archive has
    not left it while their photographs are still on a page."""
    return person.image_consent == 'granted' and person.is_listed


# --- may I? ------------------------------------------------------------------------------

def upload_block_reason(user, person) -> str:
    """'' when this user may add a photograph of this person; otherwise the sentence the
    page will print. Checked in the order a reader would ask the questions: who are you,
    did this person agree, and only then how much is already here."""
    if not _authenticated(user):
        return LOGIN_TO_UPLOAD
    if not consent_granted(person):
        return NO_CONSENT
    pending = Portrait.objects.filter(person=person, uploaded_by=user, status='pending').count()
    if pending >= MAX_PENDING_PER_UPLOADER:
        return PENDING_CAP
    if Portrait.objects.filter(person=person, status='published').count() >= MAX_PUBLISHED_PER_PERSON:
        return PUBLISHED_CAP
    return ''


def vote_block_reason(user, portrait) -> str:
    """'' when this user may vote on this photograph. A pending portrait is votable by
    nobody, including the trusted user who can see it in the queue: a vote is the public
    choosing between photographs that are actually up."""
    if not _authenticated(user):
        return LOGIN_TO_VOTE
    if portrait.status != 'published':
        return ONLY_PUBLISHED_VOTES
    if not consent_granted(portrait.person):
        return GALLERY_OFF
    return ''


# --- what may I see? ---------------------------------------------------------------------

def visible_q(user) -> Q:
    """The gallery's visibility rule as a `Q`, for `Portrait.objects.filter(...)`.

    Everything is under the consent gate, staff included, and that is deliberate rather
    than an oversight: while a person has not said yes, there is no reader of this API for
    whom their photographs are a legitimate thing to be served — not the uploader, not the
    moderator, not the administrator. The rows stay and the admin can still reach them
    through Django's own panel, which is where a legal removal request gets handled and
    where the access is logged as staff access rather than dressed up as a gallery.

    Above that gate: the public sees `published`. The trusted tier also sees `pending`
    (that IS the queue) and `hidden` (so a takedown can be undone by whoever did it). An
    uploader sees their own `pending` and `rejected` ones, so "where did my photo go" has
    an answer on the page instead of in an e-mail we have no backend to send.
    """
    base = Q(status='published')
    if can_moderate(user):
        base |= Q(status__in=('pending', 'hidden'))
    if _authenticated(user):
        base |= Q(uploaded_by=user, status__in=('pending', 'rejected'))
    return Q(person__image_consent='granted', person__is_listed=True) & base


def with_votes(qs, sort='votes'):
    """Vote counts as a `COUNT` over an indexed FK — recount, never increment — and one of
    the three orders. `votes` is the default because it is the gallery's own order and the
    one `current_portrait` reads the winner off the top of, so the two agree by
    construction rather than by both remembering the same tuple."""
    return (qs.annotate(vote_count=Count('votes', distinct=True))
            .order_by(*SORT_ORDERS.get(sort, SORT_ORDERS['votes'])))


def gallery_queryset(user, person, *, sort='votes', status=DEFAULT_STATUS, mine=False):
    """One person's photographs, narrowed the way the caller asked and then narrowed again
    by `visible_q` — in that order, and the order matters. The filter is the caller's
    question; the visibility rule is our answer to it, and an answer must never be wider
    than the rule allows. `status='pending'` from an anonymous visitor therefore comes back
    empty rather than refused: for them those rows are not there to be refused.

    `mine` with no explicit status implies `status='all'`. Showing somebody their own
    uploads and silently dropping the ones still in the queue would answer a question
    nobody asked — "which of my photographs got through" is exactly the question the
    checkbox is for, and the pending ones are half the answer.
    """
    qs = Portrait.objects.filter(visible_q(user), person=person).select_related('person', 'uploaded_by')
    if mine:
        if not _authenticated(user):
            return Portrait.objects.none()
        qs = qs.filter(uploaded_by=user)
    if status != 'all':
        qs = qs.filter(status=status)
    return with_votes(qs, sort)


def queue_queryset(user, *, sort='old', person_slug=''):
    """Everything waiting for a decision, across every person — oldest first by default,
    because a queue worked newest-first is a queue with a permanent tail."""
    if not can_moderate(user):
        return Portrait.objects.none()
    qs = Portrait.objects.filter(visible_q(user), status='pending').select_related('person', 'uploaded_by')
    if person_slug:
        qs = qs.filter(person__slug=person_slug)
    return with_votes(qs, sort if sort in ('new', 'old') else 'old')


# --- reading the query string ---------------------------------------------------------

def read_choice(params, key, allowed, default):
    """A query parameter out of a fixed set. An unknown value is a 400 rather than a quiet
    fall back to the default: `?sort=newest` is a typo somebody needs to be told about,
    and silently serving `votes` for it is how a bug survives a demo."""
    value = (params.get(key) or '').strip() or default
    if value not in allowed:
        raise ValidationError({key: f'Dozwolone wartości: {", ".join(allowed)}.'})
    return value


def read_flag(params, key):
    return (params.get(key) or '').strip().lower() in ('1', 'true', 'tak', 'yes', 'on')


def read_paging(params):
    """`(offset, limit)`.

    A value that is not a whole number, or a negative offset, is a 400 — the request is
    malformed and pretending otherwise hides a broken client. A limit ABOVE the maximum is
    clamped instead: "give me everything" is a reasonable thing for a caller to ask, and
    `MAX_LIMIT` rows is a reasonable answer to it. A limit of zero or less is not a page,
    so it is a 400 too.
    """
    raw_offset, raw_limit = params.get('offset'), params.get('limit')
    try:
        offset = int(raw_offset) if raw_offset not in (None, '') else 0
        limit = int(raw_limit) if raw_limit not in (None, '') else DEFAULT_LIMIT
    except (TypeError, ValueError):
        raise ValidationError({'detail': BAD_PAGING})
    if offset < 0:
        raise ValidationError({'offset': BAD_PAGING})
    if limit < 1:
        raise ValidationError({'limit': BAD_LIMIT})
    return offset, min(limit, MAX_LIMIT)


def current_portrait(person):
    """The photograph that IS the profile picture: most votes, and on a tie the one that
    was here first. `None` while consent is not granted — which is what makes the person
    page fall back to the silhouette the instant consent is withdrawn, without the page
    itself having to know anything about art. 81.

    The tie-break is 'oldest wins' rather than 'newest wins' on purpose: it makes the
    result stable. A newest-wins tie would let the profile photo change every time
    somebody uploaded another copy of a picture nobody voted for.
    """
    if not consent_granted(person):
        return None
    return with_votes(Portrait.objects.filter(person=person, status='published')).first()


def my_vote_ids(user, portraits):
    """The subset of these portraits this user has voted for — one query for the whole
    gallery rather than one per thumbnail."""
    if not _authenticated(user) or not portraits:
        return set()
    return set(PortraitVote.objects.filter(user=user, portrait__in=portraits)
               .values_list('portrait_id', flat=True))


# --- the actions ---------------------------------------------------------------------------

def record(portrait, actor, action, reason='', previous_status=''):
    """One audit line. Every transition in this module goes through it; nothing writes a
    `status` without one."""
    return PortraitAction.objects.create(portrait=portrait, actor=actor, action=action,
                                         reason=reason, previous_status=previous_status)


def initial_status(user):
    """Trusted users publish without a queue, exactly as their posts do (DESIGN.md, "The
    trusted tier"). A confirmed member of the faculty adding a photograph to a colleague's
    page who has already agreed to have photographs is the case the queue exists to filter
    FOR, not to filter out."""
    return 'published' if can_moderate(user) else 'pending'


@transaction.atomic
def create_portrait(person, user, uploaded_file, caption='', source_note='', rights_confirmed=False):
    """Store one uploaded photograph. Raises DRF 400/403; never trusts the browser.

    The file is judged twice over before it becomes a row: the serializer has already run
    `archive.validators.validate_upload` on the bytes (Pillow must decode them, and a
    pixel budget is read from the header before anything is decoded), and here the
    decision that it is an *image at all* is re-made from the name the validator accepted
    — a portrait gallery that can be handed a PDF is a portrait gallery with a PDF in it.
    Then the metadata comes off, and only the stripped bytes are hashed and stored.
    """
    reason = upload_block_reason(user, person)
    if reason:
        raise PermissionDenied(reason)
    if not rights_confirmed:
        raise ValidationError({'rights_confirmed': RIGHTS_REQUIRED})
    if kind_for(getattr(uploaded_file, 'name', '') or '') != 'image':
        raise ValidationError({'file': NOT_AN_IMAGE})
    original_name = (getattr(uploaded_file, 'name', '') or '')[:200]
    stored = strip_image_metadata(uploaded_file)
    stored.seek(0)
    digest = hashlib.sha256(stored.read()).hexdigest()
    stored.seek(0)
    portrait = Portrait.objects.create(
        person=person, uploaded_by=user, uploaded_by_username=getattr(user, 'username', '')[:150],
        file=stored, original_name=original_name, caption=(caption or '')[:200],
        source_note=(source_note or '')[:300], rights_confirmed=True,
        status=initial_status(user), sha256=digest)
    if portrait.status == 'published':
        # A trusted upload skips the queue, but not the audit line: "who put this photo of
        # a colleague on their page" is a question that gets asked, and 'nobody decided,
        # it just appeared' is not an answer.
        record(portrait, user, 'publish', reason='zaufany użytkownik — bez kolejki',
               previous_status='')
    return portrait


@transaction.atomic
def cast_vote(user, portrait):
    """Toggle or move this user's single vote in this person's gallery.

    One vote per user per PERSON is what makes the result a choice rather than a
    popularity total: voting for a second photograph moves your vote off the first, and
    voting again for the one you already picked takes it back. Both come back as
    `(votes, my_vote)` where `votes` is a fresh COUNT of the rows — never a number we
    adjusted by one and hoped about.
    """
    reason = vote_block_reason(user, portrait)
    if reason:
        raise PermissionDenied(reason)
    same_person = PortraitVote.objects.filter(user=user, portrait__person_id=portrait.person_id)
    if same_person.filter(portrait=portrait).exists():
        same_person.filter(portrait=portrait).delete()
        mine = False
    else:
        same_person.delete()  # the vote moves; it is not a second one
        PortraitVote.objects.create(user=user, portrait=portrait)
        mine = True
    return portrait.votes.count(), mine


@transaction.atomic
def moderate(portrait, actor, decision, note=''):
    """publish / reject / hide / restore, from the trusted tier. Raises 403, 400 or 409.

    Reached by id, so every check here is an object-level one — `visible_q` never runs for
    this call. Two of them matter:

    * **409, not 400, when the portrait is already in the target state.** Two moderators
      opening the queue at the same time is the normal case, not a malformed request, and
      the second one needs to be told the world moved rather than that they typed
      something wrong.
    * **Publishing asks about consent again.** A photograph can sit in the queue for a
      week, and the person can withdraw consent on the Tuesday. The queue would not show
      it any more, but an id in a URL does not care what the queue shows.
    """
    if not can_moderate(actor):
        raise PermissionDenied('Ta czynność wymaga potwierdzonego adresu instytucjonalnego (FUW, UW, PAN).')
    target = DECISION_TARGET.get(decision)
    if target is None:
        raise ValidationError({'decision': UNKNOWN_DECISION})
    if decision in PUBLISHING_DECISIONS and not consent_granted(portrait.person):
        raise PermissionDenied(PUBLISH_NEEDS_CONSENT)
    if portrait.status == target:
        raise Conflict('To zdjęcie już jest w tym stanie.')
    previous = portrait.status
    portrait.status = target
    portrait.review_note = (note or '')[:2000]
    portrait.reviewed_by = actor
    portrait.save(update_fields=['status', 'review_note', 'reviewed_by'])
    record(portrait, actor, decision, reason=(note or '')[:2000], previous_status=previous)
    return portrait
