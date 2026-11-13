"""vetdir — a clinic's public card and the visit requests pet owners send it (VETDIR-S1).

Two tables. **No IP address, no user agent, no account** in either: the clinic is known by a key
it holds, the owner by a signed link mailed to the address they typed. `tests.py` pins both field
sets; do not add any of those "for debugging".

`Listing` — one clinic's card. `status` is the one lifecycle field (`pending` until the clinic
presses the link mailed to its address, then `listed`, or `unlisted` by the key or an admin).
Whether the page is public is DERIVED (`rules.is_public`: listed and refreshed by a key-holder
call within LISTING_IDLE_DAYS), never a second flag. The key is stored only as its SHA-256; the
plain key was returned once and lives in the clinic's browser and its backups. `card` is the
cleaned structured card (`rules.clean_card`) — there is no free paragraph to store.

`VisitRequest` — one owner's wish: a day and a part of the day, never a time slot. Its personal
fields are blanked by `rules.sweep` (REQUEST_KEEP_DAYS after a terminal state or the wished day;
REQUEST_UNCONFIRMED_DAYS after it was sent unconfirmed); the row stays, empty (root rule 6).

`example` (Amendment 1, both tables): rows made by `manage.py vetdir_seed_examples` — fictional,
marked on every page that draws them, mailed nobody, removed by its `--clear`; never made by a
migration or at start-up.

Tokens are signed, never stored: the listing's confirmation link signs the row and its
`created_at`; a request's confirmation link signs the row and its `created_at` and expires with
REQUEST_UNCONFIRMED_DAYS; a request's cancel link signs the row and never expires, so every mail
can carry it. SECRET_KEY rotation voids them all.
"""
from datetime import timedelta

from django.core import signing
from django.db import models

from . import rules

LISTING_CONFIRM_SALT = 'vetdir.listing.confirm'
REQUEST_CONFIRM_SALT = 'vetdir.request.confirm'
REQUEST_CANCEL_SALT = 'vetdir.request.cancel'


def _stamp(when):
    return round(when.timestamp() * 1_000_000)


class Listing(models.Model):
    public_id = models.CharField(max_length=16, unique=True)
    key_hash = models.CharField(max_length=64)
    # The clinic's address for the confirmation mail only; never in any answer.
    email = models.EmailField(max_length=rules.EMAIL_MAX)
    locale = models.CharField(max_length=8, blank=True)
    # Which copy listed it (its Origin, settings.FUWLOL_VETDIR_ORIGINS): where mailed links point.
    source = models.CharField(max_length=20, default='medapp')
    consent_version = models.CharField(max_length=40)
    status = models.CharField(max_length=12, choices=[(s, s) for s in rules.LISTING_STATUSES],
                              default='pending')
    card = models.JSONField(default=dict)
    created_at = models.DateTimeField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    unlisted_at = models.DateTimeField(null=True, blank=True)
    # The last call made with the key (or the confirmation): the idle clock.
    seen_at = models.DateTimeField()
    mailed_at = models.DateTimeField(null=True, blank=True)
    # Amendment 1: a fictional row made by `manage.py vetdir_seed_examples`. Its card says so on the
    # page, a request to it is answered 202 and kept and mailed nowhere, and `--clear` removes it.
    example = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'przychodnia w katalogu'
        verbose_name_plural = 'przychodnie w katalogu'

    def __str__(self):
        return f'{self.card.get("name", "?")} ({self.public_id})'

    def confirm_token(self):
        return signing.TimestampSigner(salt=LISTING_CONFIRM_SALT).sign_object(
            {'l': self.pk, 't': _stamp(self.created_at)})

    @staticmethod
    def from_confirm_token(token):
        """(row, 'ok') | (None, 'expired') | (None, 'unknown')."""
        try:
            data = signing.TimestampSigner(salt=LISTING_CONFIRM_SALT).unsign_object(
                token, max_age=timedelta(days=rules.LISTING_CONFIRM_DAYS))
        except signing.SignatureExpired:
            return None, 'expired'
        except (signing.BadSignature, ValueError):
            return None, 'unknown'
        row = Listing.objects.filter(pk=data.get('l')).first() if isinstance(data, dict) else None
        if row is None or _stamp(row.created_at) != data.get('t'):
            return None, 'unknown'
        return row, 'ok'


class VisitRequest(models.Model):
    public_id = models.CharField(max_length=16, unique=True)
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='requests')
    status = models.CharField(max_length=16, choices=[(s, s) for s in rules.REQUEST_STATUSES],
                              default='pending_email')
    owner_name = models.CharField(max_length=rules.OWNER_NAME_MAX, blank=True)
    phone = models.CharField(max_length=rules.PHONE_MAX, blank=True)
    email = models.CharField(max_length=rules.EMAIL_MAX, blank=True)
    species = models.CharField(max_length=12)
    animal_name = models.CharField(max_length=rules.ANIMAL_NAME_MAX, blank=True)
    day = models.DateField()
    part_of_day = models.CharField(max_length=12)
    reason = models.CharField(max_length=rules.VISIT_REASON_MAX, blank=True)
    locale = models.CharField(max_length=8, blank=True)
    created_at = models.DateTimeField()
    email_confirmed_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    # The start staff set when they confirmed; the end is theirs (the diary's), not ours.
    start = models.DateTimeField(null=True, blank=True)
    blanked_at = models.DateTimeField(null=True, blank=True)
    # Amendment 1: made by the seed command for an example listing; never mailed.
    example = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['listing', 'status'])]

    def __str__(self):
        return f'{self.public_id} ({self.status})'

    def confirm_token(self):
        return signing.TimestampSigner(salt=REQUEST_CONFIRM_SALT).sign_object(
            {'r': self.pk, 't': _stamp(self.created_at)})

    def cancel_token(self):
        return signing.Signer(salt=REQUEST_CANCEL_SALT).sign(str(self.pk))

    @staticmethod
    def from_confirm_token(token):
        try:
            data = signing.TimestampSigner(salt=REQUEST_CONFIRM_SALT).unsign_object(
                token, max_age=timedelta(days=rules.REQUEST_UNCONFIRMED_DAYS))
        except signing.SignatureExpired:
            return None, 'expired'
        except (signing.BadSignature, ValueError):
            return None, 'unknown'
        row = VisitRequest.objects.filter(pk=data.get('r')).first() if isinstance(data, dict) else None
        if row is None or _stamp(row.created_at) != data.get('t'):
            return None, 'unknown'
        return row, 'ok'

    @staticmethod
    def from_cancel_token(token):
        try:
            pk = signing.Signer(salt=REQUEST_CANCEL_SALT).unsign(token)
        except signing.BadSignature:
            return None
        return VisitRequest.objects.filter(pk=int(pk)).first() if pk.isdigit() else None
