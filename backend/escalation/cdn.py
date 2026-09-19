"""Telling Cloudflare to forget a URL it is allowed to keep.

Quarantine takes an object off this origin's public path. That is one half of the job and
the smaller half: the edge in front has its own copy, served from Warsaw, for as long as
its TTL says — and the URL of an attachment was in an API response every reader saw, so
the copies that matter are exactly the ones we do not control.

Unconfigured, this logs that the edge was not purged and returns False. It never returns
True for a purge it did not perform, because the caller writes that answer into a security
log that a person may later have to rely on.
"""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger('security')

API = 'https://api.cloudflare.com/client/v4/zones/{zone}/purge_cache'
TIMEOUT = 10


def is_configured() -> bool:
    return bool(getattr(settings, 'CLOUDFLARE_ZONE_ID', '') and getattr(settings, 'CLOUDFLARE_PURGE_TOKEN', ''))


def purge_urls(urls) -> bool:
    """Best effort by nature — a network call to a third party inside a moderation action
    that must not fail because of it. Returns whether the edge actually confirmed."""
    urls = [u for u in urls if u]
    if not urls:
        return True
    if not is_configured():
        logger.warning('cdn.purge skipped (unconfigured) urls=%d — edge copies remain until TTL', len(urls))
        return False
    req = urllib.request.Request(
        API.format(zone=settings.CLOUDFLARE_ZONE_ID),
        data=json.dumps({'files': urls[:30]}).encode(),
        headers={'Authorization': f'Bearer {settings.CLOUDFLARE_PURGE_TOKEN}',
                 'Content-Type': 'application/json'},
        method='POST')
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            ok = bool(json.loads(r.read().decode()).get('success'))
    except (urllib.error.URLError, ValueError, OSError):
        logger.exception('cdn.purge failed urls=%d', len(urls))
        return False
    logger.info('cdn.purge ok=%s urls=%d', ok, len(urls))
    return ok
