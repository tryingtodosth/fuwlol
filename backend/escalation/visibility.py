"""What every other app asks before it decides who may see a piece of content.

Nothing here ever raises toward "visible": `is_escalated` fails CLOSED — if the query
itself breaks, the answer is "yes, treat it as escalated", because the failure mode of a
bug in this file must be content disappearing, never a CSAM report becoming readable
again by mistake.
"""
import logging

from django.contrib.contenttypes.models import ContentType

logger = logging.getLogger('security')

ACTIVE_STATUSES = ('pending', 'approved')


def is_head_admin(user) -> bool:
    """The one tier above `is_staff` — Django's own `is_superuser`, reused rather than
    inventing a fourth flag. Its whole strength is operational: grant it to as few real
    people as possible."""
    return bool(user is not None and getattr(user, 'is_authenticated', False) and user.is_superuser)


def active_escalation_ids(model_cls):
    """Object ids of `model_cls` currently under a pending/approved escalation — for
    excluding them from a queryset with `.exclude(pk__in=...)`."""
    from .models import Escalation
    ct = ContentType.objects.get_for_model(model_cls)
    return list(Escalation.objects.filter(content_type=ct, status__in=ACTIVE_STATUSES)
                .values_list('object_id', flat=True))


def is_escalated(obj) -> bool:
    """True if `obj` (a Post, Comment, or board Message instance) currently has a
    pending/approved escalation. Object-level twin of `active_escalation_ids`, for a single
    instance a caller already has in hand (can_see_post, can_see_comment, HideView, …)."""
    try:
        from .models import Escalation
        ct = ContentType.objects.get_for_model(type(obj))
        return Escalation.objects.filter(content_type=ct, object_id=obj.pk,
                                         status__in=ACTIVE_STATUSES).exists()
    except Exception:
        logger.exception('escalation.is_escalated failed closed for %r', obj)
        return True
