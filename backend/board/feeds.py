"""The RSS half of "an RSS kind of old-school chat board".

A plain Django syndication feed — it needs no entry in INSTALLED_APPS, and with
`django.contrib.sites` absent it falls back to the requesting host for the domain.

The description is the RAW body, deliberately: a reader is a reader, and no RSS client
is going to typeset our `$\\int$`. Whoever wants it rendered follows the link.
"""
from django.conf import settings
from django.contrib.syndication.views import Feed

from escalation.visibility import active_escalation_ids

from .models import Message

FEED_SIZE = 50


def site_url() -> str:
    # Another agent may or may not have added FUWLOL_SITE_URL; the dev frontend is the default.
    return getattr(settings, 'FUWLOL_SITE_URL', 'http://localhost:5173').rstrip('/')


class BoardFeed(Feed):
    title = 'fuw.lol — czat'
    description = 'Tablica pogaduszek archiwum Wydziału Fizyki UW'

    @property
    def link(self):
        return f'{site_url()}/czat'

    def items(self):
        # The feed has no signed-in caller to be a head-admin, so escalated messages are
        # unconditionally excluded — never surfaced through RSS to anyone.
        return (Message.objects.filter(is_hidden=False)
                .exclude(pk__in=active_escalation_ids(Message))[:FEED_SIZE])

    def item_title(self, item):
        return f'{item.nick}: {item.body[:70]}'

    def item_description(self, item):
        return item.body

    def item_link(self, item):
        return f'{site_url()}/czat#m{item.pk}'

    def item_pubdate(self, item):
        return item.created_at

    def item_author_name(self, item):
        return item.nick
