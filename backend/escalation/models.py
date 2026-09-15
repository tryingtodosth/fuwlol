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
    ('approved', 'Zatwierdzone — zgłoszone do NASK'),
    ('declined', 'Odrzucone przez administrację'),
]


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

    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['content_type', 'object_id'], condition=Q(status='pending'),
                                    name='escalation_one_pending_per_target'),
        ]

    def __str__(self):
        return f'#{self.pk} {self.content_type.model}:{self.object_id} ({self.get_status_display()})'
