r"""Portraits — the photograph at the top of a person's page, chosen by a vote.

The faculty directory this archive imitates (fuw.edu.pl/osoby-fuw.html) puts a 130 px
photo next to every name. We start from a silhouette, because we have no photographs and
— more to the point — no right to any. Art. 81 pr. aut. makes the publication of a
likeness conditional on the consent of the person portrayed, and that consent belongs to
THEM, not to whoever happens to hold the camera or the upload form. So this app exists
twice over: once as a small gallery with a vote, and once as the machinery that makes the
gallery disappear the moment the consent behind it does.

Three tables, and each of them is one of this project's standing rules made concrete:

* `Portrait` — one uploaded photograph, with ONE `status` field for its whole lifecycle
  (pending → published / rejected / hidden). Two booleans would make "rejected but still
  published" representable, and every read site would then have to defend against a state
  nobody meant to create.
* `PortraitVote` — one row per (portrait, user), which is how the count is always a
  `COUNT` over an indexed foreign key rather than a counter somebody has to remember to
  decrement. A recount cannot drift; an increment that misses one code path is wrong for
  ever. The *rule* on top of it — one vote per user per PERSON, movable between that
  person's photographs — lives in `portraits/rules.py`, because it spans rows and two
  endpoints ask it.
* `PortraitAction` — the audit line. `archive.ModerationAction` is post/comment-specific
  (it has a `post` and a `comment` column and a choice list built around nuking); bolting
  a third nullable target onto it would make every existing query wider for no gain.

**Nothing is hard-deleted.** A rejected portrait stays as a row with its file held, for
the same reason a nuked post does (DESIGN.md, "The two takedowns"): a decision about
somebody's likeness is exactly the kind of thing that gets disputed later, and the file is
the evidence of what was actually decided. Withdrawn consent does not delete either — it
makes `rules.visible_q` match nothing, which is a filter every read goes through, so the
gallery goes dark at once and by construction rather than after a batch job gets round to
it.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from archive.models import attachment_path
from archive.validators import validate_upload

# The lifecycle, as ONE field. 'hidden' is a moderator taking a published photo down;
# 'rejected' is a moderator refusing one that never went up. They are deliberately not the
# same word: the author of a rejected upload is told their photo was not accepted, while a
# hidden one was live and is now not, which is what a person asking "take that down" is
# owed an answer about.
PORTRAIT_STATUS_CHOICES = [
    ('pending', 'Czeka na moderację'),
    ('published', 'Opublikowane'),
    ('rejected', 'Odrzucone'),
    ('hidden', 'Ukryte'),
]
PORTRAIT_ACTION_CHOICES = [
    ('publish', 'publikacja'),
    ('reject', 'odrzucenie'),
    ('hide', 'ukrycie'),
    ('restore', 'przywrócenie'),
]


class Portrait(models.Model):
    """One photograph of one person, uploaded by one account.

    `file` goes through `archive.models.attachment_path`, so the stored name is a random
    UUID and the uploader's own filename never reaches the filesystem — it is untrusted
    input, and it is kept separately in `original_name` because an archive that throws
    away provenance is a folder of pictures. The bytes themselves are judged by
    `archive.validators` (Pillow has to decode them) and JPEG/PNG/WebP are re-saved
    without EXIF: a phone photo of a lecture hall carries the coordinates of the lecture
    hall, and a portrait carries them at the moment somebody stood in front of a person.

    `rights_confirmed` mirrors `Post.rights_confirmed` and is required on upload. It is
    the UPLOADER's declaration and nothing more — it says they may publish this file, not
    that the person in it agreed to be published. That second question is answered by
    `Person.image_consent`, which only the person (through the claims flow) or staff may
    set, and which `rules.visible_q` re-checks on every single read. Keeping the two apart
    is the whole legal point: art. 81 asks the person, not the photographer.

    `sha256` is the digest of the bytes as STORED — after metadata stripping, not before —
    so that a hash quoted in an answer to a removal request identifies the file that was
    actually served.
    """
    person = models.ForeignKey('archive.Person', related_name='portraits', on_delete=models.CASCADE)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    related_name='portraits', on_delete=models.SET_NULL)
    # Kept as text as well, like PostRevision.changed_by_username: the account may be
    # deleted, the record of who put a photograph of somebody on the internet may not.
    uploaded_by_username = models.CharField(max_length=150, blank=True)
    file = models.FileField(upload_to=attachment_path, validators=[validate_upload])
    original_name = models.CharField(max_length=200, blank=True)
    caption = models.CharField(max_length=200, blank=True)
    # "Skąd to zdjęcie" — provenance is half of what an archive is for, and on a portrait
    # it is also the first thing anybody asks when a person writes in about it.
    source_note = models.CharField(max_length=300, blank=True)
    rights_confirmed = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=PORTRAIT_STATUS_CHOICES, default='pending')
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    related_name='+', on_delete=models.SET_NULL)
    sha256 = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        # Oldest first, in both places it matters: it is the direction the tie-break runs
        # (equal votes → the photograph that was here first wins) and it is the order a
        # queue should be worked in. One ordering that is right twice beats two that are
        # each right once.
        ordering = ['created_at', 'id']
        indexes = [models.Index(fields=['person', 'status'])]

    def __str__(self):
        return f'{self.person.name} #{self.pk} ({self.get_status_display()})'


class PortraitVote(models.Model):
    """One person, one portrait, one row — and `unique_together` so that two clicks that
    race each other cannot become two votes.

    The interesting rule is not here but in `rules.cast_vote`: a vote belongs to a PERSON's
    gallery, not to a photograph, so casting one where you already have one moves it, and
    casting it again where it already is takes it back. A table with a unique constraint
    per photograph cannot express that on its own, which is exactly why the rule is a
    module every endpoint asks instead of a constraint two endpoints half-remember.
    """
    portrait = models.ForeignKey(Portrait, related_name='votes', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='portrait_votes', on_delete=models.CASCADE)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        unique_together = [('portrait', 'user')]

    def __str__(self):
        return f'#{self.portrait_id} ← {self.user_id}'


class PortraitAction(models.Model):
    """Who decided what about which photograph, when, and why.

    `previous_status` is the state the portrait was in before the decision, for the same
    reason `ModerationAction` keeps one: it is the difference between "a moderator hid a
    published photo" and "a moderator refused one that was never up", and those two
    sentences are the answer to different questions from different people.

    The row survives the portrait's own changes of state and is never edited. A moderation
    log that can be rewritten is a log nobody can rely on, including us.
    """
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                              related_name='portrait_actions', on_delete=models.SET_NULL)
    portrait = models.ForeignKey(Portrait, related_name='actions', on_delete=models.CASCADE)
    action = models.CharField(max_length=10, choices=PORTRAIT_ACTION_CHOICES)
    reason = models.TextField(blank=True)
    previous_status = models.CharField(max_length=10, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.get_action_display()} — portret #{self.portrait_id}'
