"""The moderation rules, in one place.

Two tiers, named the same way as in accounts/models.py:

* ``trusted`` — a user who confirmed an institutional e-mail (accounts.trust.is_trusted),
  or staff. They see the moderation board, may HIDE content, RESTORE hidden content, and
  pull the NUCLEAR option on something illegal or disgusting.
* ``staff`` — Django's `is_staff`, the real administration. Only they can read what was
  nuked, and only they can bring it back.

What each state means to a reader:

    published / visible   everybody
    hidden                trusted + staff (and, for a post, its own author — they wrote it),
                          shown with a notice; the public sees a 404 / a placeholder
    nuked                 staff only; a trusted user sees a stub on the board (id, catalog
                          number, who, when, why) and never the title, body or files

Every hide / restore / nuke writes a `ModerationAction`, so the board can show who did it,
when and why. The functions raise DRF exceptions (403 / 400) so a view can call them
directly; nothing here knows about serializers or HTTP beyond that.
"""
from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission

from escalation.quarantine import quarantine, release
from escalation.visibility import is_escalated, is_head_admin

from .models import CRITICAL_STATUSES, ModerationAction

NUKE_NEEDS_REASON = 'Opcja nuklearna wymaga podania powodu.'
ONLY_STAFF_UNNUKE = 'Treść ukrytą nuklearnie może przywrócić tylko administracja.'
NOT_TRUSTED = 'Ta czynność wymaga potwierdzonego adresu instytucjonalnego (FUW, UW, PAN).'
ESCALATED = 'Ta treść czeka na decyzję administracji.'
LOCKED_NOTICE = ('Ten wpis jest oznaczony jako kontrowersyjny — treść, pliki i komentarze widzą '
                 'tylko osoby z potwierdzonym adresem instytucjonalnym (FUW, UW, PAN).')
LOCKED_BY_MODERATOR = 'Ograniczenie nałożył moderator — zdjąć je może tylko moderator.'

# The public status a restore may put a post back into. 'hidden' / 'nuked' are never a
# restore target — see `_restore_target`.
PUBLIC_STATUSES = ('published', 'pending', 'rejected')


# --- who is who -----------------------------------------------------------------------

def is_staff(user):
    return bool(user is not None and getattr(user, 'is_authenticated', False) and user.is_staff)


def _affiliation_trusted(user):
    """The accounts half answers this. Imported lazily so the archive loads (and its
    tests run) in either build order — without accounts.trust nobody but staff is trusted,
    which is the safe direction to fail in."""
    try:
        from accounts.trust import is_trusted as accounts_is_trusted
    except ImportError:
        return False
    return accounts_is_trusted(user)


def is_trusted(user):
    """Staff, or a confirmed institutional address whose domain is still active."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_staff:
        return True
    return _affiliation_trusted(user)


class IsTrusted(BasePermission):
    """DRF permission: the moderation board and the hide / restore / nuke endpoints."""
    message = NOT_TRUSTED

    def has_permission(self, request, view):
        return is_trusted(request.user)


# --- who may see what -----------------------------------------------------------------

def can_see_post(user, post):
    """Full read access to a post. `visible_posts_q` is the queryset twin; keep them in step.

    Escalation is checked FIRST and overrides everything after it, staff included: the one
    state in this app where `is_staff` stops meaning anything (see escalation/visibility.py)."""
    if is_escalated(post) and not is_head_admin(user):
        return False
    if post.status in CRITICAL_STATUSES:
        # Not covered by the check above once the escalation is closed: a 'purged' post
        # has no open escalation, and without this the staff tier — which reads nuked
        # content — would inherit the text of something reported to NASK. The criminal
        # statuses answer to head-admin alone, for as long as the row exists.
        return is_head_admin(user)
    if post.status == 'published':
        return True
    if post.status == 'nuked':
        return is_staff(user)
    is_author = bool(user is not None and getattr(user, 'is_authenticated', False)
                     and post.submitted_by_id == user.id)
    if post.status == 'hidden':
        return is_trusted(user) or is_author
    return is_staff(user) or is_author  # pending / rejected: the queue and the author


def visible_posts_q(user):
    """The same rule as `can_see_post`, as a Q for `Post.objects.filter(...)`."""
    from django.db.models import Q

    from escalation.visibility import active_escalation_ids
    from .models import Post

    if is_head_admin(user):
        return Q(pk__isnull=False)  # the one caller escalation does not filter away from
    # Queryset twin of the CRITICAL_STATUSES check in can_see_post, and it has to be here
    # rather than relying on PostManager: the API's own queryset is built from
    # `Post.all_objects` precisely so a head-admin can reach these rows, which makes this
    # Q the thing that keeps everybody else out of them.
    critical = ~Q(status__in=CRITICAL_STATUSES)
    if is_staff(user):
        # NOT a bare Q(): an empty Q OR'd with another Q collapses to the other one in
        # Django (`Q() | Q(status='nuked')` == `Q(status='nuked')`), which would let staff
        # hide only nuked posts. A truthy match-all Q survives every combination.
        base = Q(pk__isnull=False)
    else:
        base = Q(status='published')
        if is_trusted(user):
            base |= Q(status='hidden')
        if user is not None and getattr(user, 'is_authenticated', False):
            # own posts at any stage — except nuked, which nobody but staff ever reads again
            base |= Q(submitted_by=user) & ~Q(status='nuked')
    base &= critical
    escalated = active_escalation_ids(Post)
    if escalated:
        base &= ~Q(pk__in=escalated)
    return base


def can_read_body(user, post):
    """The CONTENT of a post whose existence the caller may already see.

    A second, narrower question than `can_see_post`, and it presupposes it. A `trusted_only`
    („kontrowersyjny") post keeps its place in every public list — title, category, year,
    catalogue number — and withholds what it is about: body, summary, cover, files, filing
    and the comment thread. `readable_q` is the queryset twin; keep the two in step, the
    same way `can_see_post` and `visible_posts_q` are.

    The author is inside whatever their tier: they wrote it, they may still be editing it,
    and /moje would otherwise show them a lock over their own submission. Staff arrive
    through `is_trusted`, which they always are."""
    if not getattr(post, 'trusted_only', False):
        return True
    if is_trusted(user):
        return True
    return bool(user is not None and getattr(user, 'is_authenticated', False)
                and post.submitted_by_id == user.id)


def readable_q(user):
    """`can_read_body` as a Q, for the clauses that must not match a body nobody may read.

    NOT a bare `Q()` in the trusted branch: an empty Q collapses into whatever it is
    combined with (the trap `visible_posts_q` documents above), and here that would quietly
    turn the gate it guards into a no-op."""
    from django.db.models import Q

    if is_trusted(user):
        return Q(pk__isnull=False)
    q = Q(trusted_only=False)
    if user is not None and getattr(user, 'is_authenticated', False):
        q |= Q(submitted_by=user)
    return q


def can_see_comment(user, comment):
    """The real body/author of a comment. A comment on a nuked post is staff-only
    regardless of its own state: it belongs to content the reader may not see."""
    if is_escalated(comment) and not is_head_admin(user):
        return False
    if is_staff(user):
        return True
    if comment.post.status == 'nuked':
        return False
    if comment.moderation == 'visible':
        return True
    if comment.moderation == 'hidden':
        return is_trusted(user)
    return False  # nuked


# --- the actions ----------------------------------------------------------------------

def _require_trusted(actor):
    if not is_trusted(actor):
        raise PermissionDenied(NOT_TRUSTED)


def require_not_escalated(target):
    """Every normal moderation action (hide/restore/nuke/moderate) refuses outright while
    an escalation is pending or approved — including for staff. The only way out is
    `escalation.services.decide_escalation`, so there is exactly one path that ever moves
    escalated content between states, not two competing ones. Public (no leading
    underscore): archive/views.py's `moderate` action calls this directly too."""
    if is_escalated(target):
        raise PermissionDenied(ESCALATED)


def _clean_reason(reason, required=False):
    reason = (reason or '').strip()[:2000]
    if required and not reason:
        raise ValidationError({'reason': NUKE_NEEDS_REASON})
    return reason


def record(action, actor, *, post=None, comment=None, reason='', previous_status=''):
    """One audit line. Called by everything below and by the staff `moderate` decision."""
    return ModerationAction.objects.create(actor=actor, post=post, comment=comment, action=action,
                                           reason=reason, previous_status=previous_status)


def _resolve_reports(post):
    # A hide or a nuke IS the answer to "take this down"; the reports it was answering close.
    post.reports.filter(resolved=False).update(resolved=True)


def _restore_target(post):
    """Where a restored post goes back to: the status it had before it was (first) hidden.
    A nuke on top of a hide records 'hidden' as its previous status, so walk back past
    those to the last public one. A post with no history (hidden before this module
    existed) goes by whether it was ever published."""
    for a in post.actions.filter(action__in=('hide', 'nuke')).order_by('-created_at', '-id'):
        if a.previous_status in PUBLIC_STATUSES:
            return a.previous_status
    return 'published' if post.published_at else 'pending'


@transaction.atomic
def hide_post(post, actor, reason=''):
    _require_trusted(actor)
    require_not_escalated(post)
    if post.status == 'hidden':
        raise ValidationError({'detail': 'Ten wpis jest już ukryty.'})
    if post.status == 'nuked':
        raise PermissionDenied(ONLY_STAFF_UNNUKE)
    reason = _clean_reason(reason)
    previous = post.status
    post.status, post.reviewed_by = 'hidden', actor
    post.save()
    _resolve_reports(post)
    return record('hide', actor, post=post, reason=reason, previous_status=previous)


@transaction.atomic
def nuke_post(post, actor, reason):
    _require_trusted(actor)
    require_not_escalated(post)
    reason = _clean_reason(reason, required=True)
    if post.status == 'nuked':
        raise ValidationError({'detail': 'Ten wpis jest już ukryty nuklearnie.'})
    previous = post.status
    post.status, post.reviewed_by = 'nuked', actor
    post.save()
    quarantine(post)  # the files leave the public path with the post (escalation/quarantine.py)
    _resolve_reports(post)
    return record('nuke', actor, post=post, reason=reason, previous_status=previous)


@transaction.atomic
def restore_post(post, actor):
    """Hidden → back where it was (trusted). Nuked → back where it was (STAFF ONLY)."""
    _require_trusted(actor)
    require_not_escalated(post)
    if post.status == 'nuked' and not is_staff(actor):
        raise PermissionDenied(ONLY_STAFF_UNNUKE)
    if post.status not in ('hidden', 'nuked'):
        raise ValidationError({'detail': 'Ten wpis nie jest ukryty.'})
    previous = post.status
    post.status, post.reviewed_by = _restore_target(post), actor
    post.save()  # Post.save() stamps published_at if this is the first time it goes live
    if previous == 'nuked':
        release(post)
    return record('unnuke' if previous == 'nuked' else 'restore', actor, post=post, previous_status=previous)


def _comment_target_check(comment, actor):
    """A comment on a nuked post is off limits to everybody but staff, whatever its own state."""
    if comment.post.status == 'nuked' and not is_staff(actor):
        raise PermissionDenied(ONLY_STAFF_UNNUKE)


@transaction.atomic
def hide_comment(comment, actor, reason=''):
    _require_trusted(actor)
    require_not_escalated(comment)
    _comment_target_check(comment, actor)
    if comment.moderation == 'hidden':
        raise ValidationError({'detail': 'Ten komentarz jest już ukryty.'})
    if comment.moderation == 'nuked':
        raise PermissionDenied(ONLY_STAFF_UNNUKE)
    reason = _clean_reason(reason)
    previous = comment.moderation
    comment.moderation = 'hidden'
    comment.save(update_fields=['moderation'])
    return record('hide', actor, comment=comment, reason=reason, previous_status=previous)


@transaction.atomic
def nuke_comment(comment, actor, reason):
    _require_trusted(actor)
    require_not_escalated(comment)
    _comment_target_check(comment, actor)
    reason = _clean_reason(reason, required=True)
    if comment.moderation == 'nuked':
        raise ValidationError({'detail': 'Ten komentarz jest już ukryty nuklearnie.'})
    previous = comment.moderation
    comment.moderation = 'nuked'
    comment.save(update_fields=['moderation'])
    quarantine(comment)
    return record('nuke', actor, comment=comment, reason=reason, previous_status=previous)


@transaction.atomic
def restore_comment(comment, actor):
    """A comment has no queue to go back to: a restore always makes it visible again."""
    _require_trusted(actor)
    require_not_escalated(comment)
    _comment_target_check(comment, actor)
    if comment.moderation == 'nuked' and not is_staff(actor):
        raise PermissionDenied(ONLY_STAFF_UNNUKE)
    if comment.moderation == 'visible':
        raise ValidationError({'detail': 'Ten komentarz nie jest ukryty.'})
    previous = comment.moderation
    comment.moderation = 'visible'
    comment.save(update_fields=['moderation'])
    if previous == 'nuked':
        release(comment)
    return record('unnuke' if previous == 'nuked' else 'restore', actor, comment=comment, previous_status=previous)


# --- reading the audit line ------------------------------------------------------------

def latest_action(obj):
    """The newest ModerationAction on a post/comment (prefetch 'actions' when serializing
    many). On a hidden/nuked target this is the hide/nuke that put it there — a restore
    always moves the target out of those states, so nothing newer can be in the way."""
    return next(iter(obj.actions.all()), None)


def action_block(obj, status):
    """{status, action, actor, reason, at, previous_status} for the board and the detail
    endpoint; `actor` is a username (or None for a row whose account is gone / a legacy
    hidden post with no history)."""
    a = latest_action(obj)
    if a is None:
        return {'status': status, 'action': None, 'actor': None, 'reason': '', 'at': None, 'previous_status': ''}
    return {'status': status, 'action': a.action, 'actor': a.actor.username if a.actor_id else None,
            'reason': a.reason, 'at': a.created_at, 'previous_status': a.previous_status}


@transaction.atomic
def set_featured(post, actor, featured: bool):
    """Pin / unpin — the trusted tier, same as hide and restore.

    It is not a moderation state and gets no `status` of its own: `featured` is one
    boolean that decides whether a post appears in the homepage strip. It IS audited,
    though, because it changes what every reader sees first, and "who put this on the
    front page" is a question that gets asked.

    Only a published post can be pinned. Pinning something hidden, pending or rejected
    would queue it to appear on the homepage the moment it went live, which is not a
    decision anybody made deliberately. Unpinning is always allowed — including on a post
    that has since been hidden, so a pin can always be undone."""
    _require_trusted(actor)
    require_not_escalated(post)
    if featured and post.status != 'published':
        raise ValidationError({'detail': 'Wyróżnić można tylko opublikowany wpis.'})
    if post.featured == featured:
        raise ValidationError({'detail': 'Ten wpis już jest w tym stanie.'})
    post.featured = featured
    post.save(update_fields=['featured'])
    return record('feature' if featured else 'unfeature', actor, post=post,
                  previous_status=post.status)


@transaction.atomic
def set_trusted_only(post, actor, trusted_only: bool):
    """Lock / unlock a post to the trusted tier — the trusted tier's own, audited, like
    `set_featured`.

    Not a `status`: the post stays exactly where it is in its lifecycle and this decides
    only who reads its content (`can_read_body`). Unlike pinning there is no published-only
    rule — restricting something still in the queue is a decision about what will be
    published, and it is the one a moderator most often wants to make.

    It IS audited, and the row is what `author_may_unlock` later reads: an author may undo
    their own tick, never a moderator's."""
    _require_trusted(actor)
    require_not_escalated(post)
    if post.trusted_only == trusted_only:
        raise ValidationError({'detail': 'Ten wpis już jest w tym stanie.'})
    post.trusted_only = trusted_only
    post.save(update_fields=['trusted_only'])
    return record('lock' if trusted_only else 'unlock', actor, post=post,
                  previous_status=post.status)


def author_may_unlock(post, user):
    """May this caller take „kontrowersyjne" off through the ordinary edit form?

    Derived from the audit trail rather than carried in a second flag — the way
    `_restore_target` derives where a restore goes. A moderator's lock is a moderation
    decision, and an author answering it by unticking the box would undo it silently;
    their own tick is theirs to undo. Trusted callers use `set_trusted_only` and never
    reach this."""
    if is_trusted(user):
        return True
    return not post.actions.filter(action='lock').exclude(actor=user).exists()
