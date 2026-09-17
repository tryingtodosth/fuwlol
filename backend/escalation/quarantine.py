"""Taking the FILES of escalated / nuked content off the public path.

A row's status only governs what the API returns. The attachment bytes sit under
MEDIA_ROOT, which nginx serves straight from the volume with no auth and a 30-day cache
(frontend/nginx.conf) — and their absolute URLs were in every API response before the
content was escalated or nuked, so anyone who kept a URL, and every cache along the way,
could keep fetching the picture after "nobody can see this" became the rule.

So the moment content is escalated (escalation/services.py) or nuked
(archive/moderation.py) its files are MOVED to EVIDENCE_ROOT/quarantine/<relative path>.
The FileField keeps its name, so the row still knows what it had; the path just stops
resolving under MEDIA_ROOT (a 404, not a picture). A decline or an un-nuke moves them
back. Moves are idempotent both ways — content nuked and then escalated has its files
moved once, and released only when neither state still holds.

This is one origin's half of the job: a CDN in front (Cloudflare) has its own copy for as
long as its TTL says — purge it by URL after an escalation. Stated, not solved here.
"""
import logging
import shutil
from pathlib import Path

from django.conf import settings

logger = logging.getLogger('security')


def _files_of(target):
    manager = getattr(target, 'attachments', None)
    if manager is None or not hasattr(manager, 'all'):
        return []
    return [att.file for att in manager.all() if att.file]


def _paths(f):
    live = Path(settings.MEDIA_ROOT) / f.name
    held = Path(settings.EVIDENCE_ROOT) / 'quarantine' / f.name
    return live, held


def quarantine(target):
    """Move every attachment of `target` out of MEDIA_ROOT. Returns how many moved."""
    n = 0
    for f in _files_of(target):
        live, held = _paths(f)
        if not live.is_file():
            continue  # already held, or never written
        held.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.move(str(live), str(held))
        n += 1
    if n:
        logger.info('quarantine.hold target=%s:%s files=%d', type(target).__name__, target.pk, n)
    return n


def release(target):
    """Put the files back, unless something else still says they must stay held."""
    if still_held(target):
        return 0
    n = 0
    for f in _files_of(target):
        live, held = _paths(f)
        if not held.is_file():
            continue
        live.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(held), str(live))
        n += 1
    if n:
        logger.info('quarantine.release target=%s:%s files=%d', type(target).__name__, target.pk, n)
    return n


def read_bytes(f):
    """The bytes of an attachment FileField, from MEDIA_ROOT or — if a nuke already moved
    it — from quarantine. Evidence snapshots use this so escalating nuked content works."""
    live, held = _paths(f)
    for p in (live, held):
        if p.is_file():
            return p.read_bytes()
    raise FileNotFoundError(f.name)


def still_held(target):
    """True while ANY reason to hold the files remains: an active escalation, or a nuke
    (`status`/`moderation` == 'nuked' on the archive models)."""
    from .visibility import is_escalated
    if is_escalated(target):
        return True
    return getattr(target, 'status', None) == 'nuked' or getattr(target, 'moderation', None) == 'nuked'
