"""fuw.lol — escalation to NASK (Dyżurnet.pl).

The one state in the whole system where "trusted" and even "staff" mean nothing: the
moment a row here exists as `pending` or `approved`, its target (a Post, a Comment, or a
board Message — anything, via a GenericForeignKey rather than three nullable columns, so
this app never has to import archive/board's models) is invisible to EVERYONE except
`is_head_admin` — see `escalation/visibility.py`, which archive and board both call from
their own visibility rules.

There is no automated call out to NASK here. `decide_escalation` (services.py) on `approve`
freezes a hashed evidence package (evidence.py) for a human head-admin to forward through
Dyżurnet.pl's own reporting channel — this app's job ends at "here is the complete,
tamper-evident package", deliberately, because nothing should be able to unilaterally
contact a national authority from user-triggered code.
"""
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Q

STATUS_CHOICES = [
    ('pending', 'Czeka na administrację'),
    ('approved', 'Potwierdzone — do przekazania do NASK'),
    ('declined', 'Odrzucone przez administrację'),
    ('purged', 'Przekazane do NASK i trwale usunięte'),
]
# While the row is in one of these, the target is invisible to everyone but head-admin and
# its files are off the public path. 'purged' is NOT among them: by then there are no files
# and no readable target left, only the audit row — see EvidenceAuditLog.
ACTIVE_STATUSES = ('pending', 'approved')


class Escalation(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey('content_type', 'object_id')

    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    reason = models.TextField()  # mandatory: the record if this is ever asked about again

    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default='pending')
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name='+')
    decision_note = models.TextField(blank=True)
    # sha256 of the frozen evidence package (evidence.py) — proof of what was captured, and
    # when, independent of whatever later happens to the live content or its files.
    evidence_ref = models.CharField(max_length=64, blank=True)

    # Filled by the one action that ends this row's life: a head-admin stating that they
    # have forwarded the package through Dyżurnet.pl's own channel and that the bytes may
    # now be destroyed. The reference is whatever Dyżurnet gave back and is optional,
    # because their form does not always return one — an absent reference must not be a
    # reason to keep illegal material a day longer.
    # What `status` the target had before this escalation projected 'quarantined' onto it,
    # so a decline puts it back exactly where it was instead of guessing. Kept here rather
    # than read back out of ModerationAction because this app deliberately never imports
    # archive's models — see the module docstring.
    target_previous_status = models.CharField(max_length=16, blank=True)

    reported_to_nask_at = models.DateTimeField(null=True, blank=True)
    nask_case_reference = models.CharField(max_length=120, blank=True)
    purged_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        permissions = [
            # So that "head-admin" can be granted to one more real person without handing
            # them the whole Django superuser flag. `visibility.is_head_admin` accepts
            # either; everything else in the project asks that one function.
            ('can_manage_critical_quarantine', 'Może przeglądać i zamykać kwarantannę krytyczną'),
        ]
        constraints = [
            models.UniqueConstraint(fields=['content_type', 'object_id'], condition=Q(status='pending'),
                                    name='escalation_one_pending_per_target'),
        ]

    def __str__(self):
        return f'#{self.pk} {self.content_type.model}:{self.object_id} ({self.get_status_display()})'


class EvidenceAuditLog(models.Model):
    """What is left of a criminal file after the file is gone — and the reason the file
    being gone is survivable.

    Art. 202 § 4b k.k. criminalises possessing or storing this material, and Polish law
    offers a hobbyist platform no chain-of-custody exemption for holding a copy "for the
    investigation". Art. 18 DSA, at the same time, requires informing the authorities. Both
    are satisfied by the same move: forward everything to Dyżurnet.pl, then destroy every
    copy here and keep only this row — a hash, an address, a user-agent, and timestamps.
    None of that is the material; all of it is what an investigator actually asks for,
    because the sha256 identifies the file in any collection they already hold and the
    address plus timestamp is what an ISP answers a subscriber query on.

    One row per FILE, not per report: each binary has its own hash, and a post can carry
    six. A report that removed three files writes three rows sharing one escalation.

    The row is append-only, enforced in `save`/`delete` rather than by convention. A log
    that a later bug can edit is not evidence of anything, and this is the only record that
    a lawful destruction — rather than a quiet one — ever happened.
    """
    escalation = models.ForeignKey(Escalation, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='audit_rows')
    # 'post' | 'comment' | 'message' — the criminal path is not Post-only, because a
    # comment attachment and a chat upload are the same offence and the same duty.
    target_kind = models.CharField(max_length=16)
    # The target's primary key. Named for the commonest case; holds the comment's or the
    # board message's pk when `target_kind` says so.
    original_post_id = models.PositiveBigIntegerField()

    file_sha256 = models.CharField(max_length=64, db_index=True)
    # Where the destroyed object lived: an R2 key, or a MEDIA_ROOT-relative path. Metadata
    # about a deletion, never a way back to anything.
    storage_location = models.CharField(max_length=300, blank=True)
    original_name = models.CharField(max_length=200, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)

    uploader_ip = models.GenericIPAddressField(null=True, blank=True)
    uploader_user_agent = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(null=True, blank=True)

    reported_to_nask_at = models.DateTimeField()
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name='+')
    # Kept as text as well as by FK: the account can be deleted, the record of who made
    # this decision may not be.
    reported_by_username = models.CharField(max_length=150, blank=True)
    nask_case_reference = models.CharField(max_length=120, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'wpis rejestru dowodowego'
        verbose_name_plural = 'rejestr dowodowy'

    def __str__(self):
        return f'{self.target_kind}:{self.original_post_id} {self.file_sha256[:12]}…'

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError('EvidenceAuditLog is append-only; an existing row cannot be modified.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('EvidenceAuditLog is append-only; a row cannot be deleted.')
