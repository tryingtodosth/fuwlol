"""fuw.lol — one note about a page of an app, sent by whoever was looking at it.

Built for MedApp, which is deployed beside the archive as `skoki` (fuw.lol/fwumu) and has
no backend of its own: the *only* call that app makes to a server is this one. Somebody at a
feedback session taps a button, says what they mean in one field, and the note arrives here
with the place it came from already attached.

Three decisions the model exists to hold.

**`location` is filled in by the app, never by the person.** The whole reason this exists is
that "the dose list forgets the 22:00 row" is worth nothing without knowing which screen said
it, and a reporter who has to name the screen writes about the naming instead of the bug. It is
untrusted input all the same — anybody can POST this endpoint with anything — so it is
validated as a path and only ever displayed as text; see `serializers.py`.

**A blank `location` is still a note worth keeping.** Refusing the submission because the
hidden field did not arrive would lose the one sentence the session was held to collect.

**No health data, ever.** MedApp holds symptom maps, medicines and emergency cards; this
endpoint takes a comment, a screen path and a language, and the widget on the other side sends
nothing else. A note that quotes a symptom does so because its author typed it, which is their
own say — but nothing about this table is a place for a patient record, and `LEGAL.md` §4's
retention story applies to `ip_hash` here exactly as it does to the board.
"""
from django.conf import settings
from django.db import models

# 4096 characters — twice the board's limit, because a bug report that has to be cut short is a
# bug report somebody has to come back and ask about. Enforced in the serializer, so going over
# is a sentence rather than a silent truncation.
# MIRRORED in frontend `src/lib/feedback/api.ts` (MedApp) as MAX_LEN — change one, change the other.
MAX_LEN = 2 ** 12

# The four buttons the widget shows, in the order it shows them.
# MIRRORED in MedApp's `src/lib/feedback/api.ts` as KINDS — change one, change the other. The
# labels here are Polish because this is what the admin queue reads; the app draws its own,
# translated, from its paraglide messages.
KIND_CHOICES = [
    ('bug', 'Błąd'),
    ('suggestion', 'Sugestia'),
    ('idea', 'Pomysł'),
    ('comment', 'Komentarz'),
]

# Which deployed app a note came from. One value today; a second surface (the archive itself,
# say) would add one here rather than a second table with the same five columns.
APP_CHOICES = [('skoki', 'MedApp (skoki)')]

# The lifecycle, as ONE field (root CLAUDE.md: never two booleans). `new` is the queue,
# `triaged` means somebody has read it and knows where it belongs, `done` means it was acted
# on or answered, `spam` means it was neither and should stop showing up.
STATUS_CHOICES = [
    ('new', 'Nowa'),
    ('triaged', 'Przejrzana'),
    ('done', 'Załatwiona'),
    ('spam', 'Spam'),
]


class Feedback(models.Model):
    app = models.CharField(max_length=20, choices=APP_CHOICES, default='skoki')
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    text = models.TextField()
    # The screen the note was written on, as the app's own router spells it and with the
    # locale prefix taken off: `/care/medicines`, not `/fwumu/pl/care/medicines`. Blank when
    # the app could not tell.
    location = models.CharField(max_length=200, blank=True)
    # The interface language the reporter was reading, so a note in Ukrainian is not a mystery.
    locale = models.CharField(max_length=8, blank=True)
    # HMAC-SHA256 under FUWLOL_IP_SALT — `board.models.hash_ip`, the one place that hashes an
    # address in this project. Enough to see that thirty notes came from one laptop; never the
    # address itself.
    ip_hash = models.CharField(max_length=64, blank=True)
    # Who wrote it, IF they happened to be signed in to fuw.lol in the same browser. MedApp has
    # no accounts and sends no token, so in practice this is null and the note is anonymous.
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                               related_name='feedback_notes', on_delete=models.SET_NULL)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='new')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']
        verbose_name = 'uwaga'
        verbose_name_plural = 'uwagi'
        indexes = [
            # The two questions the queue asks: "what is unread" and "what came from this
            # screen". Both on a table that only ever grows.
            models.Index(fields=['status', '-id'], name='feedback_status_recent'),
            models.Index(fields=['location'], name='feedback_location'),
        ]

    def __str__(self):
        return f'{self.get_kind_display()} @ {self.location or "?"}: {self.text[:40]}'
