r"""The consent rules, in one place — and there is exactly one place on purpose.

Seven endpoints ask questions about a claim (request, confirm, manage-link, manage read,
manage change, withdraw, staff decide), five of them arrive with a token or an id in the
URL, and every one of them can change what the public may read about a named human being.
An endpoint that re-derives "what does this wish actually do" is how the profile page and
the moderation queue start disagreeing about whether somebody consented, so all of them
call in here and none of them decides anything itself.

**What each wish does, mechanically** (the copy the person reads is `WISH_LABELS`; the
public explanation is /ludzie/zgoda):

    images_ok   Person.image_consent = 'granted'   — the ✓ badge appears, the portrait
                gallery opens (portraits/rules.py filters on exactly this field)
    no_images   Person.image_consent = 'refused'   — every post of theirs WITH AN IMAGE
                attachment is hidden
    no_mention  Person.image_consent = 'opted_out' — is_listed = False, and EVERY post of
                theirs is hidden for a moderator to go through one at a time

"Whose posts" is `archive.people.person_posts_q`, which is where nicknames live: a post
tagged „Hamiltonianka” is prof. Hamiltonian's post, and a rule that re-derived this from
`Post.people` alone would leave exactly the posts a person is most likely to mind.

**Hidden, not deleted, and that is not a hedge.** A post naming somebody who wants out is
not automatically unlawful — it may be a quote that is fine once the name comes off, or a
photograph that is fine once it is cropped. What the law requires is that it stops being
disseminated (art. 81 ust. 1 pr. aut., RODO art. 17 and 21); what it does not require is
that the archive destroy its own record of a decision. So the posts go to the moderation
board, where a human decides what a lawful version looks like, and the claimant is told
that in those words rather than being promised a deletion nobody performed.

**Why the hide is done here and not through `archive.moderation.hide_post`.** That
function demands a *trusted actor* — the tier system — and the actor here is the person
themself, who has no account and whose authority over their own image does not come from
this site's tiers at all. So the bodies are mirrored rather than called: the same status
change, the same "a hide answers the reports it was answering", the same
`ModerationAction` audit line (with `actor=None`, because no user did this), and the same
refusal to touch anything under escalation. What is added is `ConsentHide`, which records
which posts THIS claim hid and what each one's status was — the difference between a
precaution that can be taken back and one that cannot.

**The audit reason never contains the claimant's address.** It names the mechanism, so
that a moderator reading the board knows why the post left the page and a curious reader
who talks their way into the board learns nothing about who wrote to us.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from accounts.trust import mask_email, match_domain
from archive.models import Person, Post
from archive.moderation import record, require_not_escalated
# The archive's own 409 ("the world moved"), reused rather than defined a third time.
from archive.people import Conflict, person_posts_q
from archive.search import normalize_text

from .models import ConsentHide, PersonClaim, new_token

log = logging.getLogger('security')

# The dated version of the consent text the claimant agreed to (the checkbox on
# PersonClaimBox.svelte plus /ludzie/zgoda). BUMP THIS whenever that wording changes in a
# way that changes what somebody agreed to: an approved claim is evidence, and evidence
# that cannot say which text it refers to is a date and an address, not a consent.
CONSENT_TEXT_VERSION = '2026-09-19'

WISH_LABELS = {
    'images_ok': 'Zdjęcia ze mną mogą tu być',
    'no_images': 'Wzmianki tak, zdjęć nie',
    'no_mention': 'Nie chcę być w archiwum',
}
# wish -> Person.image_consent
WISH_CONSENT = {'images_ok': 'granted', 'no_images': 'refused', 'no_mention': 'opted_out'}
# How much each wish takes away. Only used to compare two wishes: a NEW wish that is
# lower than the one it replaces is a loosening, and a loosening has to give back what
# the stricter one took (see `decide` and `change_wish`).
STRICTNESS = {'images_ok': 0, 'no_images': 1, 'no_mention': 2}
# The two that take content away. These are the ones applied precautionarily, because
# being wrong about them costs a hidden post and being wrong the other way costs a person
# their control over their own face.
TIGHTENING = ('no_images', 'no_mention')

# At most this many unconfirmed claims per person per 24 h, so that one bored visitor
# cannot mail a lecturer forty times from our server. Counted AFTER the caller's own
# older unused claim has been replaced, so a person retrying their own form is not
# spending the budget on themselves.
MAX_SENT_PER_PERSON_PER_DAY = 3

# The statuses a post can be hidden FROM. 'published' is the obvious one; 'pending' is
# here because a pending post is a post that becomes public the moment a moderator says
# yes, and leaving it in the queue would mean the wish quietly expires. A post that is
# already hidden, nuked, rejected or in criminal quarantine is left exactly where it is —
# and gets no ConsentHide row, which is what stops a later revert from resurrecting
# something a moderator took down for reasons of their own.
HIDEABLE = ('published', 'pending')

HIDE_REASON = {
    'no_images': 'na wniosek osoby, której wpis dotyczy (brak zgody na wizerunek, art. 81 pr. aut.)',
    'no_mention': 'na wniosek osoby, której wpis dotyczy (wycofanie z archiwum, art. 21 RODO)',
}
RESTORE_REASON = 'przywrócenie po zmianie lub cofnięciu wniosku osoby, której wpis dotyczy'

BAD_WISH = 'Nieznana opcja.'
NEED_AGREEMENT = 'Bez zaznaczenia oświadczenia nie możemy zapisać wyboru.'
BAD_TOKEN = 'Link wygasł albo został już użyty.'
ALREADY_DECIDED = 'Ten wniosek został już rozpatrzony.'
NOT_VERIFIED = 'Ten wniosek nie został jeszcze potwierdzony ze skrzynki.'
MAIL_FAILED = 'Nie udało się wysłać wiadomości. Spróbuj ponownie później.'


class BadToken(APIException):
    """400 with a plain `detail`. A token that is expired, used or simply wrong gets the
    SAME sentence in every case: the three are indistinguishable to whoever is guessing,
    and that is the point."""
    status_code = 400
    default_detail = BAD_TOKEN


class MailFailed(APIException):
    """503. Only ever raised when the mail IS the product (the confirmation link, the
    settings link) — nothing was sent, so saying so leaks nothing and saves the person
    from waiting for a message that will never arrive. A notification that fails after a
    decision has already been recorded is logged instead: the decision stands."""
    status_code = 503
    default_detail = MAIL_FAILED


# --- looking a person up ----------------------------------------------------------------

def person_for_claim(slug):
    """The person whose entry may be claimed, or 404.

    Not listed → 404, and that includes somebody who has already opted out. It is the same
    answer their profile gives (`PersonViewSet` filters `is_listed=True`), which is the
    whole point: "there is no such person here" and "that person asked to be taken out"
    must be one answer, or the endpoint becomes a way to ask who opted out."""
    return get_object_or_404(Person.objects.filter(is_listed=True), slug=slug)


def person_for_manage(slug):
    """The person whose settings link may be asked for — listed or not, because the one
    thing somebody who opted out must never lose is the way back. The endpoint answers 202
    whatever happens, so this is not an oracle; `None` simply means nothing to send."""
    return Person.objects.filter(slug=slug).first()


# --- asking for the link ------------------------------------------------------------------

def _clean_email(email):
    return (email or '').strip().lower()


def _confirm_link(claim):
    return f'{settings.FUWLOL_SITE_URL}/ludzie/{claim.person.slug}/potwierdz?token={claim.token}'


def _manage_link(claim):
    return f'{settings.FUWLOL_SITE_URL}/ludzie/{claim.person.slug}/ustawienia?token={claim.manage_token}'


def _send(subject, body, email, *, critical):
    """One send, one decision about what a failure means. `critical` mail is the product
    (the link) — a failure is a 503 and the caller undoes what it did. Everything else is
    a notification about something that has already happened, and a failure is a log line,
    because rolling back a recorded decision because SMTP hiccuped would be worse."""
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email])
        return True
    except Exception:
        log.exception('consent mail failed (critical=%s) to=%s', critical, mask_email(email))
        if critical:
            raise MailFailed()
        return False


@transaction.atomic
def request_claim(person, email, wish, note, request=None, user=None):
    """„Jesteś tą osobą?” — step one: send a link to the mailbox and wait.

    Returns `{'sent_to': masked, 'sent': bool}` and the view answers 202 either way. The
    caller is told nothing about whether this person already has a claim, whether the
    address is known, or whether the daily cap swallowed this one, because every one of
    those answers is a question somebody could ask about a colleague's mailbox by filling
    in our form.

    The caps: one claim in flight per (person, address) — a second request replaces the
    first, exactly like `accounts.VerifyRequestView`, so a person who lost the mail is
    never locked out by their own retry — and `MAX_SENT_PER_PERSON_PER_DAY` unconfirmed
    claims per person per day, so this endpoint cannot be used to post somebody's mailbox.
    """
    if wish not in WISH_LABELS:
        raise ValidationError({'wish': [BAD_WISH]})
    email = _clean_email(email)
    note = (note or '').strip()[:PersonClaim.NOTE_MAX]
    masked = mask_email(email)

    # The caller's own older unused attempt makes way for this one (and stops counting).
    PersonClaim.objects.filter(person=person, email__iexact=email, status='sent').delete()
    recent = PersonClaim.objects.filter(person=person, status='sent',
                                        created_at__gt=timezone.now() - PersonClaim.VALID_FOR).count()
    if recent >= MAX_SENT_PER_PERSON_PER_DAY:
        log.info('consent claim capped person=%s', person.slug)
        return {'sent_to': masked, 'sent': False}

    claim = PersonClaim.objects.create(
        person=person, email=email, wish=wish, note=note,
        consent_text_version=CONSENT_TEXT_VERSION,
        requester_ip=(request.META.get('REMOTE_ADDR') if request is not None else None) or None,
        requester_user_agent=((request.META.get('HTTP_USER_AGENT') or '')[:1000] if request is not None else ''),
        user=user if (user is not None and getattr(user, 'is_authenticated', False)) else None)
    # NOTE, DELIBERATELY, IS NOT IN THIS MAIL. Neither is the wish. A form that lets a
    # stranger put text into a message we send to an address the same stranger chose is a
    # spam relay with our domain on it; the name, the link and the validity are all this
    # message needs to do its one job.
    body = (f'Cześć,\n\n'
            f'ktoś poprosił o ustawienie zgody na wizerunek dla strony „{claim.person.full_name}” '
            f'w archiwum fuw.lol i podał ten adres.\n\n'
            f'Kliknij, żeby potwierdzić, że to Twoja skrzynka:\n\n{_confirm_link(claim)}\n\n'
            f'Link działa 24 godziny i tylko raz.\n\n'
            f'Jeśli to nie Ty — zignoruj tę wiadomość. Bez kliknięcia nic się nie stanie, '
            f'a my nie dowiemy się, że ją dostałaś lub dostałeś.\n')
    try:
        _send('fuw.lol — potwierdź, że to Twoja skrzynka', body, email, critical=True)
    except MailFailed:
        claim.delete()  # nothing was sent; do not leave a link nobody received
        raise
    log.info('consent claim requested person=%s wish=%s', person.slug, wish)
    return {'sent_to': masked, 'sent': True}


# --- confirming the mailbox ---------------------------------------------------------------

def _claim_by_token(token):
    token = (token or '').strip()
    claim = PersonClaim.objects.filter(token=token).select_related('person').first() if token else None
    if claim is None or not claim.token_is_valid:
        raise BadToken()
    return claim


@transaction.atomic
def confirm(token):
    """The click that proves somebody can read that mailbox.

    Returns `{ok, wish, applied, message}`. The message is the honest one: it says what
    happened *now* and what is still waiting for a human, because "dziękujemy" alone
    would let somebody who has just asked to disappear walk away believing they had.
    """
    claim = _claim_by_token(token)
    claim.status, claim.verified_at = 'verified', timezone.now()
    claim.save(update_fields=['status', 'verified_at'])
    result = maybe_apply_precaution(claim)
    log.info('consent claim verified id=%s person=%s wish=%s applied=%s',
             claim.pk, claim.person.slug, claim.wish, bool(result))
    return {'ok': True, 'wish': claim.wish, 'wish_label': WISH_LABELS[claim.wish],
            'applied': claim.applied_at is not None,
            'person': {'slug': claim.person.slug, 'full_name': claim.person.full_name},
            'message': _confirm_message(claim, result)}


def maybe_apply_precaution(claim):
    """Apply a *tightening* wish immediately, but only from an institutional mailbox.

    The asymmetry this encodes is the whole design. A fraudulent `images_ok` is real,
    irreversible harm to a real person: it puts a public badge on somebody's name saying
    they agreed, and opens a photo gallery on the strength of it. A fraudulent `no_images`
    costs some posts a few days off the page until staff look. Those are not the same
    risk, so they do not get the same caution.

    `accounts.trust.match_domain` is the signal, and it is a weak one on purpose: it says
    the sender can read mail at fuw.edu.pl, not that they are the person named. That is
    enough to hide something for a day and nowhere near enough to publish a consent, which
    is exactly the line drawn here. Returns the apply result, or None.
    """
    if claim.wish not in TIGHTENING:
        return None
    if match_domain(claim.email) is None:
        return None
    return apply_wish(claim)


def _confirm_message(claim, applied):
    label = WISH_LABELS[claim.wish]
    if claim.wish == 'images_ok':
        return ('Adres potwierdzony. Wybór: „' + label + '”. Teraz patrzy na to administracja — '
                'odznaka „zgoda na wizerunek” jest publiczna, więc sprawdzamy, czy adres pasuje do osoby. '
                'Decyzję wyślemy na ten sam adres.')
    what = 'wpisy ze zdjęciami' if claim.wish == 'no_images' else 'wpisy z Twoim nazwiskiem'
    if applied:
        n = applied.get('hidden', 0)
        return (f'Adres potwierdzony. Ukryliśmy {n} ' + ('wpis' if n == 1 else 'wpisów') +
                f' od ręki, bo piszesz z adresu instytucjonalnego — nie czekamy z tym na moderatora. '
                f'Administracja jeszcze to sprawdzi; jeśli okaże się, że to pomyłka, {what} wrócą, '
                f'a Ty dostaniesz wiadomość z powodem.')
    return ('Adres potwierdzony. Wniosek trafił do administracji — z adresu spoza uczelni nie ukrywamy '
            'wpisów od razu, bo w drugą stronę też da się tego nadużyć. Zwykle to kwestia godzin. '
            'Jeśli sprawa jest pilna, użyj przycisku „Zgłoś / poproś o usunięcie” przy konkretnym wpisie — '
            'to osobna, szybsza ścieżka i działa też bez tego wszystkiego.')


# --- applying and reverting a wish ---------------------------------------------------------

def _posts_for(claim):
    """The posts this claim is about: the person's posts (named OR tagged with one of
    their nicknames — `person_posts_q`), narrowed to those carrying an image when the wish
    is only about photographs. `.distinct()` because that Q spans two many-to-many joins
    and a post that is both named and tagged would otherwise come back twice."""
    qs = Post.objects.filter(person_posts_q(claim.person))
    if claim.wish == 'no_images':
        qs = qs.filter(attachments__kind='image')
    return qs.distinct()


def _hide_for(claim):
    """Hide what this claim covers. Idempotent per post, and it records what it did.

    Mirrors `archive.moderation.hide_post` rather than calling it — see the module
    docstring for why — including `_resolve_reports`: a hide IS the answer to "take this
    down", so the reports it answers close with it.
    """
    hidden, skipped = 0, 0
    if claim.wish == 'images_ok':
        return hidden, skipped
    reason = HIDE_REASON[claim.wish]
    for post in _posts_for(claim):
        if post.status not in HIDEABLE:
            continue
        try:
            require_not_escalated(post)
        except PermissionDenied:
            # Escalated content is invisible to everybody already, so the wish is moot for
            # it; and nothing below head-admin may learn that an escalation exists, which
            # is why this is counted for the log and never mentioned to the claimant.
            skipped += 1
            continue
        row, created = ConsentHide.objects.get_or_create(
            claim=claim, post=post, defaults={'previous_status': post.status})
        if not created and row.previous_status != post.status:
            row.previous_status = post.status
            row.save(update_fields=['previous_status'])
        previous = post.status
        post.status = 'hidden'
        post.save()
        post.reports.filter(resolved=False).update(resolved=True)
        record('hide', None, post=post, reason=reason, previous_status=previous)
        hidden += 1
    if skipped:
        log.info('consent hide skipped %s escalated post(s) claim=%s', skipped, claim.pk)
    return hidden, skipped


@transaction.atomic
def apply_wish(claim):
    """Write the wish onto the Person and onto their posts. Idempotent.

    `previous_consent` / `previous_listed` are captured only the first time, because they
    are the way back to the world as it was before this claim — re-capturing them on a
    re-run would record the state this claim itself created, and the way back would lead
    in a circle.

    Re-running is a real case, not a defensive nicety: when a looser wish replaces a
    stricter one, the stricter claim's hides are reverted first and this runs again to
    re-hide the narrower set (`no_images` after `no_mention` keeps the photographs down
    and gives the text back).

    `is_listed` is only ever set to False here, never back to True: putting somebody back
    in the directory is `revert`'s job, and it has the old value to put back.
    """
    person = claim.person
    first_time = claim.applied_at is None
    if first_time:
        claim.previous_consent, claim.previous_listed = person.image_consent, person.is_listed
    fields = ['image_consent']
    person.image_consent = WISH_CONSENT[claim.wish]
    if claim.wish == 'no_mention':
        person.is_listed = False
        fields.append('is_listed')
    person.save(update_fields=fields)
    hidden, skipped = _hide_for(claim)
    claim.applied_at = claim.applied_at or timezone.now()
    claim.save(update_fields=['applied_at', 'previous_consent', 'previous_listed'])
    log.info('consent applied claim=%s person=%s wish=%s hidden=%s', claim.pk, person.slug, claim.wish, hidden)
    return {'hidden': hidden, 'skipped_escalated': skipped}


def _applied_since(claim):
    """Has any other claim written itself onto this person since this one did? If so,
    `revert` must not put the old consent back — it would overwrite a newer, live wish
    with a state the person has already moved on from."""
    if claim.applied_at is None:
        return False
    return (PersonClaim.objects.filter(person_id=claim.person_id, applied_at__isnull=False)
            .exclude(pk=claim.pk).filter(applied_at__gte=claim.applied_at).exists())


@transaction.atomic
def revert(claim):
    """The exact inverse of `apply_wish` — precaution that cannot be taken back is not
    precaution, it is a decision made by whoever filled in the form first.

    Exact means exact: only the posts in this claim's own `ConsentHide` rows, only those
    still `hidden` (a post a moderator has since nuked stays nuked), and each one back to
    the status IT had, which is why `previous_status` is on the row rather than assumed to
    be 'published' — a post that was still in the queue goes back to the queue.
    """
    if claim.applied_at is None:
        return {'restored': 0, 'skipped': 0}
    restored, skipped = 0, 0
    for row in claim.hides.select_related('post'):
        post = row.post
        if post.status != 'hidden':
            skipped += 1
            continue
        try:
            require_not_escalated(post)
        except PermissionDenied:
            skipped += 1
            continue
        post.status = row.previous_status
        post.save()  # Post.save() stamps published_at the first time a post goes live
        record('restore', None, post=post, reason=RESTORE_REASON, previous_status='hidden')
        restored += 1
    claim.applied_at = None
    claim.save(update_fields=['applied_at'])
    person = claim.person
    if not _applied_since(claim):
        person.image_consent = claim.previous_consent or 'unknown'
    # Whether the person is in the directory is RECOUNTED rather than toggled back: they
    # are off it while ANY still-applied claim says `no_mention`, and on it otherwise —
    # unless they were already off it before this claim touched them. Putting
    # `previous_listed` back directly gets the overlap wrong in both directions (two
    # opt-outs, of which one is withdrawn, would re-list somebody who is still asking to
    # be gone; and a looser wish replacing an opt-out would leave them off the list
    # forever, because the newer claim's `previous_listed` remembers the opt-out's world).
    still_out = PersonClaim.objects.filter(person_id=person.pk, wish='no_mention',
                                           applied_at__isnull=False).exists()
    person.is_listed = not (still_out or claim.previous_listed is False)
    person.save(update_fields=['image_consent', 'is_listed'])
    log.info('consent reverted claim=%s restored=%s skipped=%s', claim.pk, restored, skipped)
    return {'restored': restored, 'skipped': skipped}


def _supersede_previous(person, claim):
    """Every other approved claim of this person steps aside for `claim` — and gives back
    everything it took, whichever direction the change goes.

    **Reverting the old claim unconditionally is the point, not a shortcut.** The obvious
    version reverts only a loosening, and it leaves a trap on the other path: a person who
    asks for "no photos" and later for "take me out entirely" would have the photo posts
    hidden by the FIRST claim, which is now superseded and can never be reverted again —
    so withdrawing the second claim would restore everything except those, permanently,
    with no row left that knows why. Undoing the old claim first and letting the new one
    re-hide what it wants leaves exactly one applied claim, owning exactly the posts it
    hid, at every instant.

    Order is the other half of the correctness. The revert runs BEFORE the new wish is
    applied, because `_hide_for` only touches posts that are currently visible: applying
    first and reverting second would leave the new claim owning nothing and then hand
    every post back, and somebody who asked for "mentions yes, photos no" would find
    their photographs back up.

    `apply_wish` is idempotent and re-runs its hide pass, which is what makes this safe
    when the new claim has already been applied precautionarily."""
    for old in (PersonClaim.objects.filter(person=person, status='approved')
                .exclude(pk=claim.pk).order_by('-applied_at', '-id')):
        revert(old)
        # The new claim inherits the world from before the one it replaces. If it had
        # already been applied precautionarily, what it recorded as "the state before me"
        # is the state the OLD claim had created — and that state has just been reverted
        # out of existence, so keeping the reference would resurrect it the day this claim
        # is withdrawn ('refused' coming back from a claim nobody is relying on any more).
        # When the new claim has not been applied yet there is nothing to fix: `apply_wish`
        # captures the state after this revert, which is the same answer.
        if claim.applied_at is not None:
            claim.previous_consent, claim.previous_listed = old.previous_consent, old.previous_listed
            claim.save(update_fields=['previous_consent', 'previous_listed'])
        old.status = 'superseded'
        old.manage_token, old.manage_token_expires_at = None, None
        old.save(update_fields=['status', 'manage_token', 'manage_token_expires_at'])


def _rotate_manage_token(claim, save=True):
    claim.manage_token = new_token()
    claim.manage_token_expires_at = timezone.now() + PersonClaim.MANAGE_VALID_FOR
    if save:
        claim.save(update_fields=['manage_token', 'manage_token_expires_at'])
    return claim.manage_token


# --- the staff decision ----------------------------------------------------------------

@transaction.atomic
def decide(claim, actor, decision, note=''):
    """Staff say yes or no. 409 if the world has already moved.

    Approval is the moment this archive accepts "this mailbox is this person", and from
    then on the mailbox decides by itself (`change_wish`, `withdraw_claim`) — which is why
    the approval mail carries the settings link. A rejection undoes any precaution first,
    and then says why: an unexplained "no" to somebody asking about their own face is the
    one refusal nobody should have to guess at.
    """
    if decision not in ('approve', 'reject'):
        raise ValidationError({'decision': ['Decyzja: approve albo reject.']})
    if claim.status in ('approved', 'rejected', 'superseded', 'withdrawn'):
        raise Conflict(ALREADY_DECIDED)
    if claim.status != 'verified':
        raise Conflict(NOT_VERIFIED)
    note = (note or '').strip()[:2000]
    claim.decided_by, claim.decided_at, claim.decision_note = actor, timezone.now(), note

    if decision == 'approve':
        _supersede_previous(claim.person, claim)
        apply_wish(claim)  # idempotent; re-runs the hide pass after a loosening gave posts back
        _rotate_manage_token(claim, save=False)
        claim.status = 'approved'
        claim.save()
        _mail_decision(claim, approved=True)
    else:
        revert(claim)
        claim.status = 'rejected'
        claim.manage_token, claim.manage_token_expires_at = None, None
        claim.save()
        _mail_decision(claim, approved=False)
    log.info('consent decided claim=%s person=%s decision=%s by=%s',
             claim.pk, claim.person.slug, decision, getattr(actor, 'username', '?'))
    return claim


def _wish_effect_line(wish):
    return {
        'images_ok': 'Na Twojej stronie widać teraz odznakę „✓ zgoda na wizerunek”, a czytelnicy mogą '
                     'zgłaszać zdjęcia do galerii. Każdy wpis nadal można zgłosić osobno.',
        'no_images': 'Wpisy z Twoim zdjęciem są zdjęte ze strony i czekają na przegląd moderatora.',
        'no_mention': 'Twoja strona zniknęła ze spisu osób, a wpisy z Twoim nazwiskiem są zdjęte ze strony '
                      'i moderator przechodzi je po kolei. Ukryte — nie skasowane: to człowiek decyduje, '
                      'co z każdym z nich dalej, i dlatego to trwa.',
    }[wish]


def _mail_decision(claim, approved):
    label = WISH_LABELS[claim.wish]
    if approved:
        body = (f'Cześć,\n\n'
                f'potwierdziliśmy Twój wybór dla strony „{claim.person.full_name}” w archiwum fuw.lol.\n\n'
                f'Twój wybór: {label}.\n{_wish_effect_line(claim.wish)}\n\n'
                f'Możesz to zmienić albo wycofać w każdej chwili — tym linkiem:\n\n{_manage_link(claim)}\n\n'
                f'Link działa 24 godziny; nowy wyślesz sobie sama lub sam ze strony osoby, '
                f'z tego samego adresu.\n')
        if claim.decision_note:
            body += f'\nOd administracji: {claim.decision_note}\n'
        _send('fuw.lol — Twój wybór został potwierdzony', body, claim.email, critical=False)
        return
    powod = claim.decision_note or ('Nie udało nam się potwierdzić, że adres należy do tej osoby.')
    body = (f'Cześć,\n\n'
            f'nie przyjęliśmy wniosku dotyczącego strony „{claim.person.full_name}” w archiwum fuw.lol.\n\n'
            f'Wybór, o który chodziło: {label}.\nPowód: {powod}\n\n'
            f'Jeśli to pomyłka po naszej stronie — napisz na {settings.FUWLOL_CONTACT_EMAIL}.\n'
            f'Jeśli chodzi Ci o jeden konkretny wpis, szybsza jest ścieżka „Zgłoś / poproś o usunięcie” '
            f'przy tym wpisie; działa też bez potwierdzania adresu.\n')
    _send('fuw.lol — wniosek nie został przyjęty', body, claim.email, critical=False)


# --- the settings link, and what the mailbox may do with it ------------------------------

def send_manage_link(person, email):
    """„Wyślij mi link do ustawień”. 202 whatever happens, so this is not a way to ask
    whether an address has claimed a person.

    RODO art. 7 ust. 3: withdrawing consent must be as easy as giving it. Giving it was
    one form and one click in a mailbox; taking it back is one form and one click in the
    same mailbox, and it costs no account, no password and no second review.
    """
    email = _clean_email(email)
    claim = (PersonClaim.objects.filter(person=person, email__iexact=email, status='approved')
             .select_related('person').order_by('-applied_at', '-id').first()) if person else None
    if claim is None:
        return {'sent_to': mask_email(email), 'sent': False}
    _rotate_manage_token(claim)
    body = (f'Cześć,\n\n'
            f'oto link do ustawień zgody dla strony „{claim.person.full_name}” w archiwum fuw.lol:\n\n'
            f'{_manage_link(claim)}\n\n'
            f'Link działa 24 godziny. Możesz nim zmienić swój wybór albo wycofać go całkiem.\n\n'
            f'Jeśli to nie Ty prosiłaś lub prosiłeś o ten link — zignoruj tę wiadomość, '
            f'nic się bez kliknięcia nie zmieni.\n')
    _send('fuw.lol — link do Twoich ustawień', body, claim.email, critical=True)
    return {'sent_to': mask_email(email), 'sent': True}


def claim_for_manage(token):
    """The live claim behind a settings link, or 400. Approved only: the magic link is the
    thing the staff approval created, and a `verified` claim that nobody has decided yet
    has nothing to manage."""
    token = (token or '').strip()
    claim = (PersonClaim.objects.filter(manage_token=token, status='approved')
             .select_related('person').first()) if token else None
    if claim is None or not claim.manage_token_is_valid:
        raise BadToken()
    return claim


def manage_state(token):
    claim = claim_for_manage(token)
    return {'person': {'slug': claim.person.slug, 'full_name': claim.person.full_name},
            'current_wish': claim.wish, 'current_wish_label': WISH_LABELS[claim.wish],
            'email_masked': mask_email(claim.email),
            'consent_text_version': claim.consent_text_version}


@transaction.atomic
def change_wish(token, wish):
    """The same verified mailbox changes its mind — and it takes effect now.

    No second review, deliberately. The staff check exists to answer "is this really that
    person", and it has already been answered for this mailbox; putting a queue in front
    of a withdrawal would make taking consent back harder than giving it, which is the one
    thing RODO art. 7 ust. 3 names outright.

    A change is a NEW row, never an edit: the old one is the evidence of what was agreed
    to and when, and evidence that gets overwritten every time somebody changes their mind
    can only ever tell you about the last time. The settings link MOVES to the new row, so
    the link already sitting in somebody's mailbox keeps opening their current wish.
    """
    claim = claim_for_manage(token)
    if wish not in WISH_LABELS:
        raise ValidationError({'wish': [BAD_WISH]})
    if wish == claim.wish:
        return {'ok': True, 'wish': wish, 'wish_label': WISH_LABELS[wish],
                'message': 'Nic nie zmieniamy — to już jest Twój wybór.'}
    now = timezone.now()
    fresh = PersonClaim.objects.create(
        person=claim.person, email=claim.email, wish=wish, note='',
        consent_text_version=CONSENT_TEXT_VERSION, status='approved',
        verified_at=claim.verified_at or now, decided_at=now,
        decision_note='Zmiana przez osobę, z potwierdzonej skrzynki — bez ponownej weryfikacji.',
        user_id=claim.user_id, requester_ip=None, requester_user_agent='')
    # The link follows the live row rather than being reissued, so the mail already in the
    # person's inbox does not die the moment they use it.
    fresh.manage_token, fresh.manage_token_expires_at = claim.manage_token, claim.manage_token_expires_at
    claim.manage_token, claim.manage_token_expires_at = None, None
    claim.save(update_fields=['manage_token', 'manage_token_expires_at'])
    fresh.save(update_fields=['manage_token', 'manage_token_expires_at'])
    _supersede_previous(fresh.person, fresh)  # reverts `claim` first when this is a loosening
    result = apply_wish(fresh)
    body = (f'Cześć,\n\n'
            f'zmieniłaś lub zmieniłeś swój wybór dla strony „{fresh.person.full_name}” w archiwum fuw.lol.\n\n'
            f'Nowy wybór: {WISH_LABELS[wish]}.\n{_wish_effect_line(wish)}\n\n'
            f'Jeśli to nie Ty — napisz natychmiast na {settings.FUWLOL_CONTACT_EMAIL}.\n')
    _send('fuw.lol — zmiana Twojego wyboru', body, fresh.email, critical=False)
    log.info('consent wish changed person=%s from=%s to=%s', fresh.person.slug, claim.wish, wish)
    return {'ok': True, 'wish': wish, 'wish_label': WISH_LABELS[wish],
            'message': _change_message(wish, result)}


def _change_message(wish, result):
    if wish == 'images_ok':
        n = result.get('hidden', 0)
        base = 'Gotowe — odznaka „✓ zgoda na wizerunek” jest już na Twojej stronie.'
        return base if not n else base
    n = result.get('hidden', 0)
    if n:
        return f'Gotowe. Ukryliśmy {n} ' + ('wpis.' if n == 1 else 'wpisów.')
    return 'Gotowe. Nie było nic do ukrycia — albo już było ukryte.'


@transaction.atomic
def withdraw_claim(token):
    """„To jednak nie ja”. The row stays (it is the record of a decision, and of who made
    it), but everything it did is undone and the settings link dies with it."""
    claim = claim_for_manage(token)
    result = revert(claim)
    claim.status = 'withdrawn'
    claim.manage_token, claim.manage_token_expires_at = None, None
    claim.save(update_fields=['status', 'manage_token', 'manage_token_expires_at'])
    log.info('consent claim withdrawn id=%s person=%s', claim.pk, claim.person.slug)
    n = result.get('restored', 0)
    tail = f' Przywróciliśmy {n} ' + ('wpis.' if n == 1 else 'wpisów.') if n else ''
    return {'ok': True, 'message': 'Wycofane. Twój wybór przestał obowiązywać, a odznaka zniknęła.' + tail}


# --- what the staff queue sees ------------------------------------------------------------

def signals(claim):
    """Plausibility signals for the person deciding. Signals, not a score, and not a
    decision: each one is a fact with an obvious failure mode, and the human weighs them.

    * `domain_trusted` / `institution` — the address is at an institution we recognise.
      Strong-ish, and the one that already bought a precautionary hide.
    * `name_tokens_in_local_part` — a piece of the person's name (≥3 letters, folded the
      way search folds, so „Łoś” matches „los”) appears before the @. Often absent for
      perfectly real people: an address rarely matches a nickname, and „Pani z portierni”
      has no surname to match at all. Its absence means nothing; its presence means
      something.
    * `account` — a user here registered with that address. Not authority (nobody proved
      anything by typing an address into a registration form), just context.
    * `earlier_claims` — how many other claims this person's entry has already had. Two
      different mailboxes claiming one lecturer is the pattern worth looking at.
    """
    from django.contrib.auth.models import User
    domain = match_domain(claim.email)
    local = claim.email.split('@', 1)[0] if '@' in claim.email else claim.email
    folded_local = normalize_text(local)
    tokens = [normalize_text(t) for t in f'{claim.person.surname} {claim.person.name}'.split()]
    match = any(t and len(t) >= 3 and t in folded_local for t in tokens)
    account = User.objects.filter(email__iexact=claim.email).values_list('username', flat=True).first()
    return {
        'domain_trusted': domain is not None,
        'institution': domain.institution if domain is not None else None,
        'name_tokens_in_local_part': match,
        'account': account,
        'earlier_claims': PersonClaim.objects.filter(person_id=claim.person_id).exclude(pk=claim.pk).count(),
    }
