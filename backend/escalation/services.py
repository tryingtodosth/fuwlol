"""The two actions in this app: requesting an escalation, and head-admin deciding it.
Everything else (visibility, permissions) reacts to the state these leave behind."""
import logging

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .evidence import snapshot_target
from .models import Escalation
from .quarantine import quarantine, release
from .visibility import is_head_admin

logger = logging.getLogger('security')

ALREADY_PENDING = 'Ta treść już czeka na decyzję administracji.'
NOT_PENDING = 'To zgłoszenie zostało już rozpatrzone.'
REASON_REQUIRED = 'Podaj powód zgłoszenia do administracji.'


@transaction.atomic
def create_escalation(target, actor, reason):
    """Any trusted/staff moderator (the caller's own permission class already checked
    that) may call this for any Post, Comment, or board Message. The reason is mandatory —
    it is the one piece of this that a human wrote, not the system. The DB's unique
    constraint (not a pre-check) is what actually stops two concurrent requests from
    double-escalating the same target — a pre-check alone would race."""
    reason = (reason or '').strip()
    if not reason:
        raise ValidationError({'reason': [REASON_REQUIRED]})
    ct = ContentType.objects.get_for_model(type(target))
    try:
        with transaction.atomic():
            esc = Escalation.objects.create(content_type=ct, object_id=target.pk,
                                            requested_by=actor, reason=reason[:4000])
            esc.evidence_ref = snapshot_target(esc, target)
            esc.save(update_fields=['evidence_ref'])
            # the frozen copy is written; now the live files leave the public path
            quarantine(target)
    except IntegrityError:
        raise ValidationError({'detail': ALREADY_PENDING})
    logger.info('escalation.created id=%s target=%s:%s by=%s(%s)',
               esc.pk, ct.model, target.pk, actor.username, actor.pk)
    return esc


@transaction.atomic
def decide_escalation(escalation, actor, decision, note=''):
    """`decision` is 'approve' (the package is finished, ready for a human head-admin to
    forward through Dyżurnet.pl) or 'decline' (not NASK-worthy; normal moderation on the
    target un-freezes). `select_for_update` + the `status != 'pending'` check is what makes
    two simultaneous decide calls resolve to exactly one outcome, not two."""
    if decision not in ('approve', 'decline'):
        raise ValidationError({'decision': ['approve albo decline.']})
    esc = Escalation.objects.select_for_update().get(pk=escalation.pk)
    if esc.status != 'pending':
        raise ValidationError({'detail': [NOT_PENDING]})
    esc.status = 'approved' if decision == 'approve' else 'declined'
    esc.decided_by = actor
    esc.decision_note = (note or '').strip()[:2000]
    esc.decided_at = timezone.now()
    esc.save(update_fields=['status', 'decided_by', 'decision_note', 'decided_at'])
    if esc.status == 'declined' and esc.target is not None:
        release(esc.target)  # no-op if the content is also nuked
    logger.info('escalation.decided id=%s status=%s by=%s(%s)',
               esc.pk, esc.status, actor.username, actor.pk)
    return esc


def visible_escalations_for(user):
    """Every escalation view/queryset funnels through this — a `has_permission` check
    alone is not enough if a queryset elsewhere forgets to filter, so the queryset itself
    is empty for anybody who is not head-admin, fail-closed."""
    if not is_head_admin(user):
        return Escalation.objects.none()
    return Escalation.objects.select_related('requested_by', 'decided_by', 'content_type')
