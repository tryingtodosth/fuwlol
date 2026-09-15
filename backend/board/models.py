"""fuw.lol — the shoutbox.

One flat stream of short messages, newest first, open to anybody with or without an
account: the kind of chat board every faculty page had in 2004, kept on purpose.

Three rules the model exists to hold. **No pictures** — links yes, LaTeX yes (`format`),
but nothing that turns the stream into an image board; that is enforced in the serializer,
where the refusal can be a sentence in Polish. **2048 characters**, which is `2 ** 11` and
also about as much as anybody should shout at once. And **hiding, not deleting**: a
moderated message keeps its row and its place in the numbering, so it can be put back and
so `?since=` polling never sees the stream renumber underneath it.

`ip_hash` is how abuse is traced without keeping anybody's address: the same visitor
always hashes to the same string, and the string cannot be turned back into an address.
"""
import hashlib

from django.conf import settings
from django.db import models
from django.db.models import Q

# 2 ** 11 = 2048 characters. Enforced in the serializer rather than as a model max_length,
# so going over gives a Polish sentence instead of a silent truncation.
MAX_LEN = 2 ** 11

FORMAT_CHOICES = [('text', 'Tekst / Markdown'), ('latex', 'LaTeX')]
DEFAULT_NICK = 'Anonim'


def hash_ip(ip: str) -> str:
    """SHA-256 of the address salted with SECRET_KEY. Enough to tell that two messages
    came from the same place; never enough to recover where that place was."""
    if not ip:
        return ''
    return hashlib.sha256(f'{ip}{settings.SECRET_KEY}'.encode()).hexdigest()


class Message(models.Model):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                               related_name='board_messages', on_delete=models.SET_NULL)
    nick = models.CharField(max_length=30)
    body = models.TextField()
    format = models.CharField(max_length=8, choices=FORMAT_CHOICES, default='text')
    ip_hash = models.CharField(max_length=64, blank=True)
    is_hidden = models.BooleanField(default=False)
    hidden_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                  related_name='+', on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']
        verbose_name = 'wiadomość'
        verbose_name_plural = 'wiadomości'

    def __str__(self):
        return f'{self.nick}: {self.body[:40]}'

    @property
    def is_guest(self) -> bool:
        """A message written without an account. The author FK is SET_NULL, so a deleted
        account's old messages honestly become guest messages rather than vanishing."""
        return self.author_id is None


class Report(models.Model):
    """A flag on a message — anybody may send one, but only a report from a signed-in,
    *trusted* account (`accounts.trust.is_trusted`) ever moves anything: see
    `board/moderation.py` for the auto-hide quorum and the reputation settlement a
    moderator's hide/restore triggers afterwards. A guest report is still worth keeping —
    it is a signal in the moderation queue — it just never counts on its own.

    `upheld` starts `None` (open); a moderator's hide/restore resolves every open report on
    the message at once and stamps this True/False, which is what board/moderation.py reads
    to decide who gets +1 / -1 reputation."""
    REASONS = [('spam', 'Spam'), ('offensive', 'Obraźliwe'), ('illegal', 'Niezgodne z prawem'),
               ('privacy', 'Dotyczy mnie'), ('other', 'Inne')]
    message = models.ForeignKey(Message, related_name='reports', on_delete=models.CASCADE)
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                 related_name='board_reports', on_delete=models.SET_NULL)
    ip_hash = models.CharField(max_length=64, blank=True)
    reason = models.CharField(max_length=10, choices=REASONS)
    note = models.TextField(blank=True)
    resolved = models.BooleanField(default=False)
    upheld = models.BooleanField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            # One report per signed-in reporter per message — not per guest: an IP is not an
            # identity (NAT, campus wifi), so guests are throttled instead (board/views.py),
            # not deduplicated.
            models.UniqueConstraint(fields=['message', 'reporter'], condition=Q(reporter__isnull=False),
                                    name='board_one_report_per_user'),
        ]

    def __str__(self):
        return f'zgłoszenie #{self.message_id} ({self.get_reason_display()})'
