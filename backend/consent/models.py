r"""fuw.lol — "Jesteś tą osobą?": the person a post is about registers their own wish.

Until this app existed, consent was a checkbox on the *uploader's* side
(`Post.rights_confirmed` — the submitter swearing they have it) and an anonymous
`Report(reason='privacy')` on the subject's side, one post at a time. Neither makes the
PERSON the unit, and the person is the unit the law uses: art. 81 ust. 1 pr. aut. makes
disseminating somebody's image conditional on THAT PERSON's consent, and a lecturer is
not an "osoba powszechnie znana" whose image may be used because of what they do
(the exception in art. 81 ust. 2 pkt 1 is about public figures acting publicly, not about
anybody who stands in front of a room). RODO art. 7 ust. 3 then says withdrawing consent
must be as easy as giving it, and art. 21 gives a right to object at any time.

So: a `PersonClaim` is one person's wish about one `Person` entry, proven from a mailbox
they control, and an approved row is this archive's **evidence of consent** — who said
what, from which address, when, and to which version of the consent text
(`consent_text_version`). It is therefore never deleted. A change of mind writes a NEW
row and marks the old one `superseded`, because "what did they agree to in March" is a
question a court can ask, and a row that was edited in place cannot answer it.

The lifecycle is one field:

    sent ──confirm the mailbox──► verified ──staff decision──► approved
      │                             │                              │
      │ (link expires, 24 h)        └── reject ──► rejected        ├── the person changes
      ▼                                                            │   their mind ──► superseded
     nothing happened                                              └── "that is not me
                                                                       after all" ──► withdrawn

Two asymmetries are deliberate and are the whole design:

1. **A fraudulent `images_ok` is real harm; a fraudulent `no_images` only hides content
   until staff reject it.** So the two *tightening* wishes are applied precautionarily at
   `verified` already — but only from an institutional mailbox (`accounts.trust.match_domain`),
   which is the one cheap signal that the sender is who they say. Precaution is reversible:
   `ConsentHide` records exactly which posts this claim hid and what status each had, so a
   rejection puts back those posts, to those statuses, and nothing a moderator hid for
   reasons of their own.
2. **The first wish needs a human; every later one does not.** Approval is what establishes
   "this mailbox is this person". After that the mailbox IS the identity, and a change or a
   withdrawal applies at once — because RODO art. 7 ust. 3 does not let us put a review
   queue in front of somebody taking their consent back.

Staff (`is_staff`), not the trusted tier, decide. Confirming that a stranger really is
dr Kwant Niepewny is a different power from "hide this fast", and the trusted tier —
a confirmed FUW/UW/PAN address — is scoped to the second one.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

# Worded for the person, not for the lawyer. The mechanical meaning of each is in
# consent/rules.py (`apply_wish`), and the public explanation is /ludzie/zgoda.
WISH_CHOICES = [
    ('images_ok', 'Zdjęcia ze mną mogą tu być'),
    ('no_images', 'Wzmianki tak, zdjęć nie'),
    ('no_mention', 'Nie chcę być w archiwum'),
]
STATUS_CHOICES = [
    ('sent', 'Wysłano link potwierdzający'),
    ('verified', 'Skrzynka potwierdzona — czeka na administrację'),
    ('approved', 'Zatwierdzony'),
    ('rejected', 'Odrzucony'),
    ('superseded', 'Zastąpiony nowszym'),
    ('withdrawn', 'Wycofany przez osobę'),
]
# The states in which the row is the person's CURRENT wish. Everything else is history,
# and history is kept rather than deleted (see the module docstring).
LIVE_STATUSES = ('approved',)


def new_token():
    return secrets.token_urlsafe(32)


class PersonClaim(models.Model):
    """One wish, from one mailbox, about one person's entry.

    The claimant usually has **no account here** — a lecturer who finds their name in a
    meme archive is not going to register first — so the identity this row carries is an
    e-mail address plus the proof that somebody could read what we sent to it. `user` is
    filled only when a logged-in account happened to be the one claiming, as a signal for
    the staff queue; it is never what authorises anything.
    """
    VALID_FOR = timedelta(hours=24)
    MANAGE_VALID_FOR = timedelta(hours=24)
    NOTE_MAX = 1000

    person = models.ForeignKey('archive.Person', related_name='claims', on_delete=models.CASCADE)
    email = models.EmailField()
    wish = models.CharField(max_length=12, choices=WISH_CHOICES)
    # Free text from the claimant to the moderator ("I am the person in FUW-0042, that
    # photo is from a funeral"). It is shown in the staff queue and NEVER put in an e-mail:
    # a form that mails a stranger's text to an address the same stranger chose is a spam
    # relay with extra steps.
    note = models.TextField(blank=True, max_length=NOTE_MAX)
    # The confirmation link. Single use in the only sense that matters: it is accepted
    # only while `status == 'sent'`, and confirming moves the row to 'verified'.
    token = models.CharField(max_length=64, unique=True, default=new_token)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='sent')
    # WHICH consent text was agreed to. A consent that cannot say what it consented to is
    # not evidence of anything; bumped in consent/rules.py when the wording changes.
    consent_text_version = models.CharField(max_length=20)
    # Evidence of consent — who, from where, when — for the same reason and on the same
    # terms as `Post.submitter_ip`: kept for SUBMITTER_IP_RETENTION_DAYS and then blanked
    # by `manage.py forget_claim_ips`, EXCEPT on approved rows, which are the evidence.
    requester_ip = models.GenericIPAddressField(null=True, blank=True)
    requester_user_agent = models.TextField(blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                             related_name='person_claims', on_delete=models.SET_NULL)

    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    # Null until the wish has been written onto the Person and the posts. ONE nullable
    # timestamp rather than a boolean plus a date: "applied but we do not know when" and
    # "not applied but dated" are states nobody should be able to represent. Cleared by
    # `rules.revert`, which is what makes "applied right now?" a single question.
    applied_at = models.DateTimeField(null=True, blank=True)
    # What the Person looked like before this claim first applied — the only way back.
    previous_consent = models.CharField(max_length=10, blank=True)
    previous_listed = models.BooleanField(null=True, blank=True)

    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   related_name='+', on_delete=models.SET_NULL)
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)

    # The magic link for later changes (/ludzie/<slug>/ustawienia?token=…). Rotated on
    # every request for one, and carried over to the row that replaces this one, so the
    # link in somebody's mailbox keeps opening THEIR current wish rather than a fossil.
    manage_token = models.CharField(max_length=64, unique=True, null=True, blank=True)
    manage_token_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['person', 'status']), models.Index(fields=['email'])]
        verbose_name = 'wniosek osoby'
        verbose_name_plural = 'wnioski osób'

    def __str__(self):
        return f'{self.person_id} · {self.get_wish_display()} ({self.get_status_display()})'

    @property
    def token_is_valid(self):
        return self.status == 'sent' and self.created_at > timezone.now() - self.VALID_FOR

    @property
    def manage_token_is_valid(self):
        return bool(self.manage_token and self.manage_token_expires_at
                    and self.manage_token_expires_at > timezone.now())


class ConsentHide(models.Model):
    """One post that one claim took off the page, and what status it had before.

    Without this, "undo the precaution" would have to mean "restore everything hidden that
    mentions this person", which would also un-hide whatever a moderator hid last week for
    reasons that have nothing to do with consent. The row is the difference between a
    reversible precaution and a mess.
    """
    claim = models.ForeignKey(PersonClaim, related_name='hides', on_delete=models.CASCADE)
    post = models.ForeignKey('archive.Post', related_name='consent_hides', on_delete=models.CASCADE)
    previous_status = models.CharField(max_length=16)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        constraints = [models.UniqueConstraint(fields=['claim', 'post'], name='one_hide_per_claim_per_post')]

    def __str__(self):
        return f'{self.post_id} ← {self.claim_id} ({self.previous_status})'
