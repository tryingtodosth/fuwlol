"""The two actions in this app: requesting an escalation, and head-admin deciding it.
Everything else (visibility, permissions) reacts to the state these leave behind."""
import logging

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .evidence import snapshot_target
from .models import Escalation, EvidenceAuditLog
from .quarantine import quarantine, release
from .visibility import is_head_admin

logger = logging.getLogger('security')

ALREADY_PENDING = 'Ta treść już czeka na decyzję administracji.'
NOT_PENDING = 'To zgłoszenie zostało już rozpatrzone.'
REASON_REQUIRED = 'Podaj powód zgłoszenia do administracji.'
NOT_APPROVED = ('Trwałe usunięcie jest możliwe dopiero po potwierdzeniu zgłoszenia '
                '(status „approved”) — i dopiero po przekazaniu pakietu do Dyżurnet.pl.')
ALREADY_PURGED = 'To zgłoszenie zostało już zamknięte trwałym usunięciem.'
NOT_CONFIRMED = ('Potwierdź wprost, że pakiet został przekazany do Dyżurnet.pl '
                 '(confirmed_dispatch=true). Bez tego nie wolno usunąć plików.')

# Statuses this app projects onto a target that has a `status` field (archive.Post). The
# projection is written HERE and nowhere else; archive/moderation.py refuses to touch an
# escalated target at all, so there is exactly one writer.
QUARANTINED = 'quarantined'
PURGED = 'purged'


def _projects_status(target) -> bool:
    """True for a target whose model knows the criminal statuses — archive.Post today.
    Duck-typed rather than `isinstance(target, Post)` because this app never imports
    archive's models; a Comment or a board Message simply has no status to project onto
    and stays governed by the Escalation row alone."""
    try:
        choices = dict(target._meta.get_field('status').choices or [])
    except Exception:
        return False
    return QUARANTINED in choices and PURGED in choices


def _project(target, status):
    if not _projects_status(target):
        return
    target.status = status
    target.save(update_fields=['status'])


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
            esc.target_previous_status = str(getattr(target, 'status', '') or '')[:16]
            esc.save(update_fields=['evidence_ref', 'target_previous_status'])
            # the frozen copy is written; now the live files leave the public path
            quarantine(target)
            # …and the row itself stops existing for the default manager (archive/models.py
            # PostManager), which is the layer that catches the call sites nobody thought
            # to filter. Written after quarantine so a failure there rolls this back too.
            _project(target, QUARANTINED)
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
        # Back where it came from — 'quarantined' was this app's projection and must not
        # outlive the escalation that wrote it. `release` is a no-op if the content is
        # also nuked, and `still_held` sees the restored status, not the quarantined one.
        _project(esc.target, esc.target_previous_status or 'hidden')
        release(esc.target)
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


@transaction.atomic
def _record_report(esc, actor, case_reference, records):
    """The first of the two commits described in shred.py: every destroyed file gets its
    immutable row BEFORE anything is destroyed. Idempotent — a retry after a failed shred
    finds the rows already there and adds none."""
    if esc.audit_rows.exists():
        return list(esc.audit_rows.all())
    from .nask import manifest_for
    manifest = manifest_for(esc)
    now = timezone.now()
    kind = (manifest.get('kind') or type(esc.target).__name__ if esc.target else '').lower()
    common = dict(
        escalation=esc, target_kind=kind[:16], original_post_id=esc.object_id,
        uploader_ip=manifest.get('submitter_ip') or None,
        uploader_user_agent=manifest.get('submitter_user_agent') or '',
        uploaded_at=esc.created_at,
        reported_to_nask_at=now, reported_by=actor,
        reported_by_username=getattr(actor, 'username', '')[:150],
        nask_case_reference=(case_reference or '').strip()[:120],
    )
    rows = []
    for rec in records:
        rows.append(EvidenceAuditLog.objects.create(
            file_sha256=(rec.get('sha256') or '')[:64],
            storage_location=(rec.get('storage_key') or rec.get('local_name') or '')[:300],
            original_name=(rec.get('original_name') or '')[:200],
            size_bytes=rec.get('size_bytes') or 0, **common))
    if not rows:
        # A text-only target (a board message, a post with no files) still produced a
        # report to a national authority, and that fact needs exactly one row. The hash
        # recorded is the frozen package's, since there is no binary to hash.
        rows.append(EvidenceAuditLog.objects.create(
            file_sha256=(esc.evidence_ref or '')[:64], storage_location='',
            original_name='(brak pliku — treść tekstowa)', size_bytes=0, **common))
    esc.reported_to_nask_at = now
    esc.nask_case_reference = common['nask_case_reference']
    esc.save(update_fields=['reported_to_nask_at', 'nask_case_reference'])
    return rows


def confirm_nask_report_and_purge(escalation, actor, *, confirmed_dispatch=False,
                                  case_reference='', note=''):
    """Head-admin: "I have forwarded this to Dyżurnet.pl. Destroy it."

    The order is the whole point and it is not negotiable: the package goes to NASK FIRST,
    by a human, through Dyżurnet's own channel, and only then does anything here get
    deleted — because once the bytes are gone this service cannot produce them again for
    an investigator who asks. `confirmed_dispatch` is that human statement, required
    explicitly rather than inferred from the endpoint having been called, and the case
    reference is optional because Dyżurnet's form does not always return one.

    Not decorated `@transaction.atomic`: this deliberately spans two commits around an
    irreversible remote delete. shred.py's module docstring explains why that ordering is
    the safe one and what a crash in the middle leaves behind (an incomplete purge, which
    running this again completes).
    """
    from . import shred

    if not confirmed_dispatch:
        raise ValidationError({'confirmed_dispatch': [NOT_CONFIRMED]})

    with transaction.atomic():
        esc = Escalation.objects.select_for_update().get(pk=escalation.pk)
        if esc.status == 'purged':
            raise ValidationError({'detail': [ALREADY_PURGED]})
        if esc.status != 'approved':
            raise ValidationError({'detail': [NOT_APPROVED]})
        target = esc.target
        records = shred.collect(esc, target)
        _record_report(esc, actor, case_reference, records)

    # --- irreversible, and outside any transaction that could pretend otherwise ---------
    shred.destroy(esc, records)   # raises ShredIncomplete; esc stays 'approved' for a retry

    with transaction.atomic():
        shred.strip_attachment_rows(records)
        if target is not None:
            _project(target, PURGED)
        esc.status = 'purged'
        esc.purged_at = timezone.now()
        esc.decision_note = ((esc.decision_note + '\n' if esc.decision_note else '')
                             + (note or '').strip())[:2000]
        esc.save(update_fields=['status', 'purged_at', 'decision_note'])

    logger.warning('escalation.purged id=%s files=%d by=%s(%s) nask_ref=%s',
                   esc.pk, len(records), actor.username, actor.pk, esc.nask_case_reference or '-')
    return esc
