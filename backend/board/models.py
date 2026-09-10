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
