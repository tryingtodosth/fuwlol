"""What goes in and what comes out. The rules live in consent/rules.py; nothing here
decides anything, and the one row shape is defined once so the queue, the decision
response and the tests cannot drift apart."""
from rest_framework import serializers

from . import rules
from .models import PersonClaim


class ClaimRequestSerializer(serializers.Serializer):
    """The form on somebody's profile. `agree` is the consent checkbox and is not
    decoration: `PersonClaim.consent_text_version` records WHICH text was ticked, and a
    row that says a text was agreed to without the person having ticked anything is the
    one kind of evidence worse than none.

    `website` is a honeypot — a field no human sees, filled in by scripts that fill in
    everything. Anything in it and the request is answered 202 like every other, which is
    the only answer that tells a bot nothing."""
    email = serializers.EmailField()
    wish = serializers.ChoiceField(choices=sorted(rules.WISH_LABELS))
    note = serializers.CharField(required=False, allow_blank=True, max_length=PersonClaim.NOTE_MAX)
    agree = serializers.BooleanField()
    website = serializers.CharField(required=False, allow_blank=True, max_length=200)

    def validate_agree(self, value):
        if value is not True:
            raise serializers.ValidationError(rules.NEED_AGREEMENT)
        return value


class EmailOnlySerializer(serializers.Serializer):
    email = serializers.EmailField()


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=64)


class ManageChangeSerializer(TokenSerializer):
    wish = serializers.ChoiceField(choices=sorted(rules.WISH_LABELS))


class DecideSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=['approve', 'reject'])
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)


def claim_row(claim, with_signals=True):
    """One row of the staff queue, and the body of a decision response.

    The address is shown in full, not masked: this is the one screen whose entire job is
    deciding whether that address plausibly belongs to that person, and a masked address
    cannot be judged. It is staff-only, and `signals` says out loud what can be read off it
    so that nobody has to squint at the string themselves.
    """
    row = {
        'id': claim.pk,
        'person': {'slug': claim.person.slug, 'full_name': claim.person.full_name},
        'email': claim.email,
        'wish': claim.wish,
        'wish_label': rules.WISH_LABELS.get(claim.wish, claim.wish),
        'note': claim.note,
        'status': claim.status,
        'created_at': claim.created_at,
        'verified_at': claim.verified_at,
        'applied_at': claim.applied_at,
        'decided_by': claim.decided_by.username if claim.decided_by_id else None,
        'decided_at': claim.decided_at,
        'decision_note': claim.decision_note,
        'consent_text_version': claim.consent_text_version,
    }
    if with_signals:
        row['signals'] = rules.signals(claim)
    return row
