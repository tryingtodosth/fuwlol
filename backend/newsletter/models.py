"""fuw.lol — the MedApp newsletter's list: an e-mail address somebody gave in order to get news.

Built for MedApp's vet clinic app on https://medapp.net (a static copy on another host, which
signs people up here across origins, with JavaScript, never by sending them to this site). The
only mail sent from here is the confirmation (mail.py), from the medapp.net mailbox; an issue is
sent by whoever exports the active rows from the admin, with each row's unsubscribe link.

Four decisions the model exists to hold.

**Double opt-in.** A sign-up is `pending` until the person opens the link mailed to the address
and presses the button on medapp.net (`POST confirm/`). Only `active` rows are exported. A
pending row older than PENDING_DAYS is deleted at the next sign-up (views.py), so an address
somebody else typed is forgotten without anybody doing anything.

**One row per address, and the answer never says whether it was already here.** Every sign-up is
answered 202 `{ok: true}` — new, pending, active, unsubscribed, honeypot, cooldown alike — and the
difference goes only to the mailbox: a confirmation link, or "already on the list".

**No key is stored; the links are signed.** The confirmation link carries a timestamped signature
of the row id and its `subscribed_at` (`django.core.signing`, salt below), so it expires after
CONFIRM_DAYS and a newer sign-up voids an older link; the unsubscribe link signs the row id and
never expires, so every issue can carry it. SECRET_KEY rotation voids both — say so in the issue.

**Consent is a version and a date, nothing more.** The words are the app's (MedApp's
`nl_consent` message in en / pl / uk); the version string pins which wording the person ticked.
No IP address or hash of one, no user agent: the list does not need them.
"""
from datetime import timedelta

from django.core import signing
from django.db import models

# RFC 5321's path limit. MIRRORED in MedApp's `src/lib/newsletter/api.ts` as EMAIL_MAX.
EMAIL_MAX = 254
# The consent wording's version. MIRRORED in MedApp's `src/lib/newsletter/api.ts` as
# CONSENT_VERSION — change the wording there, bump both, or every sign-up is refused (400).
CONSENT_VERSION = 'newsletter-2026-11-10'
CONSENT_TEXT_EN = (
    'Send me occasional e-mails about this app: news, calls for clinics and reviewers. '
    'My address is kept on fuw.lol only for this, and I can unsubscribe at any time.'
)
# How long a confirmation link works, and how long an unconfirmed row is kept.
# CONFIRM_DAYS is MIRRORED in MedApp's `src/lib/newsletter/api.ts` (the page says it).
CONFIRM_DAYS = 7
PENDING_DAYS = 30
# At most one mail to one address in this many minutes, whatever the requests say.
MAIL_COOLDOWN_MINUTES = 10
CONFIRM_SALT = 'newsletter.confirm'
UNSUBSCRIBE_SALT = 'newsletter.unsubscribe'
# A token is at most this long. MIRRORED in MedApp's `src/lib/newsletter/api.ts` as TOKEN_MAX.
TOKEN_MAX = 200
# Which copy a sign-up came from: its Origin header decides (settings.FUWLOL_NEWSLETTER_ORIGINS),
# never the body. A request from any other origin is refused (views.py).
SOURCE_CHOICES = [('medapp', 'medapp.net')]
# One field for the lifecycle (root CLAUDE.md: never two booleans).
STATUS_CHOICES = [('pending', 'Niepotwierdzony'), ('active', 'Zapisany'), ('unsubscribed', 'Wypisany')]


def _stamp(when):
    # Microseconds: a newer sign-up must void an older link even within the same second.
    return round(when.timestamp() * 1_000_000)


class Subscriber(models.Model):
    # Lower-cased and stripped by the serializer, so one person is one row.
    email = models.EmailField(max_length=EMAIL_MAX, unique=True)
    locale = models.CharField(max_length=8, blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='medapp')
    consent_version = models.CharField(max_length=40)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    # When the current consent was given (re-set by a new sign-up), confirmed, ended; and when
    # the last mail went to the address (the cooldown).
    subscribed_at = models.DateTimeField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)
    mailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-subscribed_at']
        verbose_name = 'subskrybent'
        verbose_name_plural = 'subskrybenci'

    def __str__(self):
        return self.email

    def confirm_token(self):
        return signing.TimestampSigner(salt=CONFIRM_SALT).sign_object(
            {'i': self.pk, 't': _stamp(self.subscribed_at)})

    def unsubscribe_token(self):
        return signing.Signer(salt=UNSUBSCRIBE_SALT).sign(str(self.pk))

    @staticmethod
    def from_confirm_token(token):
        """(row, 'ok') | (None, 'expired') | (None, 'unknown')."""
        try:
            data = signing.TimestampSigner(salt=CONFIRM_SALT).unsign_object(
                token, max_age=timedelta(days=CONFIRM_DAYS))
        except signing.SignatureExpired:
            return None, 'expired'
        except (signing.BadSignature, ValueError):
            return None, 'unknown'
        row = Subscriber.objects.filter(pk=data.get('i')).first() if isinstance(data, dict) else None
        if row is None or _stamp(row.subscribed_at) != data.get('t'):
            return None, 'unknown'
        return row, 'ok'

    @staticmethod
    def from_unsubscribe_token(token):
        try:
            pk = signing.Signer(salt=UNSUBSCRIBE_SALT).unsign(token)
        except signing.BadSignature:
            return None
        return Subscriber.objects.filter(pk=int(pk)).first() if pk.isdigit() else None
