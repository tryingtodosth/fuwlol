"""Somebody who is not the author knowing better — and the archive keeping what it said before.

Two things that only make sense together. A suggestion without history means an accepted
edit quietly replaces the record, and an archive that cannot show what it used to say is
asking to be trusted rather than checked. History without suggestions means only the
author can ever fix anything, and the author is usually the person who got it wrong.

**Who decides.** The post's own author, or staff. Not trusted moderators: a suggestion is
a claim about content, not about whether content may stay up, and the author is the person
with the standing to say "no, that is the version I remember". Staff are there because an
author may be long gone — this is an archive of folklore, and the accounts outlive nobody.

**Validation goes through PostWriteSerializer, not around it.** The body is LaTeX-or-
Markdown and `latexguard.check_source` is what stops a macro bomb; the year has a range;
an empty body is refused unless there are files. A suggestion is a second way to write to
exactly those fields, and a second entry point with its own idea of what is valid is how
the first one's rules stop being rules. So the proposed post is assembled — current values
overlaid with the change — and handed to the same serializer an ordinary edit uses.

**Why `base` exists.** A suggestion is written against what the post said at that moment
and decided later, possibly much later. Applying the diff blindly would silently revert
whatever happened in between. So the values those fields had when the suggestion was
written are stored alongside it, and acceptance compares before it writes: if they moved,
the answer is 409 and a human looks again. 409 rather than 400, because the request was
fine — the world moved.
"""
import logging

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import SUGGESTABLE_FIELDS, EditSuggestion, PostRevision

logger = logging.getLogger('security')

NOT_YOURS = 'Poprawki do tego wpisu rozpatruje jego autor albo administracja.'
NO_CHANGES = 'Nie zaproponowano żadnej zmiany.'
UNKNOWN_FIELD = 'Tego pola nie można zmienić poprawką.'
RATIONALE_REQUIRED = 'Napisz, dlaczego uważasz, że tak jest lepiej.'
ALREADY_DECIDED = 'Ta poprawka została już rozpatrzona.'
MOVED = ('Wpis zmienił się od czasu napisania tej poprawki. Odrzuć ją i poproś o nową, '
         'albo nanieś zmianę ręcznie — inaczej cofnęłaby cudzą edycję.')


class Conflict(ValidationError):
    """409, not 400: the request was well formed, the world moved underneath it."""
    status_code = 409

    def __init__(self, detail, fields=()):
        super().__init__({'detail': detail, 'fields': list(fields)})


def current_values(post) -> dict:
    """The post's tracked fields as they are now. One definition, used for the snapshot,
    for `base`, and for the staleness check, so those three can never disagree."""
    return {f: getattr(post, f) for f in SUGGESTABLE_FIELDS}


def snapshot(post, actor, source, *, data=None, suggestion=None, note=''):
    """Freeze what the post says BEFORE it is changed. Call this inside the same
    transaction as the change, never after — a snapshot written afterwards records the new
    state and the history silently loses a version.

    `data` exists for the one caller that cannot follow that rule: the ordinary edit path
    saves through a serializer, so the only way to know the old values is to have taken
    them first. It hands them back here rather than re-reading a row that has moved on."""
    return PostRevision.objects.create(
        post=post, data=current_values(post) if data is None else data, changed_by=actor,
        changed_by_username=getattr(actor, 'username', '')[:150],
        source=source, suggestion=suggestion, note=(note or '')[:2000])


def clean_changes(post, raw) -> dict:
    """Validate the PROPOSED POST, not the diff in isolation.

    A diff can be individually plausible and collectively invalid — clearing the body of a
    post that has no files, for instance. So the change is overlaid on the current values
    and the result is put through the serializer that guards an ordinary edit."""
    from .serializers import PostWriteSerializer

    if not isinstance(raw, dict) or not raw:
        raise ValidationError({'changes': [NO_CHANGES]})
    unknown = [k for k in raw if k not in SUGGESTABLE_FIELDS]
    if unknown:
        raise ValidationError({'changes': [f'{UNKNOWN_FIELD} ({", ".join(sorted(unknown))})']})

    merged = {**current_values(post), **raw}
    s = PostWriteSerializer(instance=post, data=merged, partial=True,
                            context={'has_files': post.attachments.exists()})
    s.is_valid(raise_exception=True)

    # Only what was actually asked for. The serializer may fill in a summary of its own;
    # adopting that here would put words in the suggester's mouth and show a diff they
    # did not write.
    cleaned = {k: s.validated_data.get(k, raw[k]) for k in raw}
    changed = {k: v for k, v in cleaned.items() if v != getattr(post, k)}
    if not changed:
        raise ValidationError({'changes': [NO_CHANGES]})
    return changed


def can_decide(user, post) -> bool:
    from .moderation import is_staff
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    return is_staff(user) or (post.submitted_by_id is not None and post.submitted_by_id == user.id)


@transaction.atomic
def create_suggestion(post, user, changes, rationale):
    from .moderation import require_not_escalated

    require_not_escalated(post)
    rationale = (rationale or '').strip()
    if not rationale:
        raise ValidationError({'rationale': [RATIONALE_REQUIRED]})
    changed = clean_changes(post, changes)
    if EditSuggestion.objects.filter(post=post, suggested_by=user, status='pending').exists():
        raise ValidationError({'detail': 'Masz już nierozpatrzoną poprawkę do tego wpisu.'})
    sug = EditSuggestion.objects.create(
        post=post, suggested_by=user, suggested_by_username=user.username[:150],
        changes=changed, base={k: getattr(post, k) for k in changed},
        rationale=rationale[:4000])
    logger.info('suggestion.created id=%s post=%s by=%s(%s) fields=%s',
                sug.pk, post.pk, user.username, user.pk, ','.join(sorted(changed)))
    return sug


@transaction.atomic
def decide_suggestion(suggestion, actor, decision, note=''):
    """`accept` applies it (after snapshotting the old version), `reject` closes it.

    Rejected suggestions are kept, not deleted: what was proposed and turned down is part
    of how the archive came to say what it says, and a suggester who is told "no" deserves
    a record of it rather than their work disappearing."""
    from .moderation import require_not_escalated

    if decision not in ('accept', 'reject'):
        raise ValidationError({'decision': ['accept albo reject.']})
    sug = EditSuggestion.objects.select_for_update().get(pk=suggestion.pk)
    post = sug.post
    if not can_decide(actor, post):
        raise PermissionDenied(NOT_YOURS)
    require_not_escalated(post)
    if sug.status != 'pending':
        raise ValidationError({'detail': [ALREADY_DECIDED]})

    if decision == 'accept':
        stale = {k: v for k, v in sug.base.items() if getattr(post, k) != v}
        if stale:
            raise Conflict(MOVED, fields=sorted(stale))
        snapshot(post, actor, 'suggestion', suggestion=sug, note=sug.rationale)
        for field, value in sug.changes.items():
            setattr(post, field, value)
        post.save()  # recomputes the search index (Post.save)

    sug.status = 'accepted' if decision == 'accept' else 'rejected'
    sug.decided_by = actor
    sug.decision_note = (note or '').strip()[:2000]
    sug.decided_at = timezone.now()
    sug.save(update_fields=['status', 'decided_by', 'decision_note', 'decided_at'])
    logger.info('suggestion.decided id=%s status=%s by=%s(%s)',
                sug.pk, sug.status, actor.username, actor.pk)
    return sug


@transaction.atomic
def withdraw_suggestion(suggestion, actor):
    sug = EditSuggestion.objects.select_for_update().get(pk=suggestion.pk)
    if sug.suggested_by_id != getattr(actor, 'id', None):
        raise PermissionDenied('To nie jest twoja poprawka.')
    if sug.status != 'pending':
        raise ValidationError({'detail': [ALREADY_DECIDED]})
    sug.status = 'withdrawn'
    sug.decided_at = timezone.now()
    sug.save(update_fields=['status', 'decided_at'])
    return sug


def visible_suggestions_for(user, post):
    """The author and staff see every suggestion on their post; a suggester sees their
    own. Nobody else sees any — a rejected "this quote is actually about X" is a claim
    about a named person that was looked at and not accepted, and publishing those would
    make the suggestion box a way to say things the moderation queue would have stopped."""
    qs = EditSuggestion.objects.filter(post=post).select_related('suggested_by', 'decided_by')
    if can_decide(user, post):
        return qs
    if user is not None and getattr(user, 'is_authenticated', False):
        return qs.filter(suggested_by=user)
    return EditSuggestion.objects.none()


def can_see_revisions(user, post) -> bool:
    from .moderation import is_trusted
    return can_decide(user, post) or is_trusted(user)

