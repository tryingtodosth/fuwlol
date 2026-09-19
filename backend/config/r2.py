"""Cloudflare R2 — the one place that talks to object storage.

Two apps need it and they need opposite things, which is exactly why it is one module
rather than a helper in each: `archive` hands a browser a signed URL so the bytes go
straight to R2 and never touch the VPS (a 25 MB upload through Django would occupy a
gunicorn worker for the whole transfer, and six of them would occupy every worker there
is), and `escalation` deletes an object for good, which is the one operation in this
project that must not be able to silently do nothing.

**Nothing here is configured in a bare clone.** `is_configured()` is false without the
`FUWLOL_R2_*` environment, every entry point checks it, and the callers turn that into an
honest refusal — a 503 on the upload endpoint, a raised `R2Unavailable` on the shred path.
The one thing this module will never do is report success for an operation it did not
perform: a purge that cannot reach R2 has to fail loudly, because the whole legal value of
the purge is that the bytes are gone, and "probably gone" is not a defence under
art. 202 § 4b k.k.

Two details that are load-bearing rather than decorative:

* **The presigned PUT is signed over `ContentLength` and `ChecksumSHA256`.** A presigned
  URL is a capability handed to a browser we do not control, so anything we do not sign is
  something the uploader chooses freely. Signing the length makes the 25 MB cap binding at
  R2 rather than being a number the frontend was politely asked to respect, and signing
  the checksum makes R2 itself reject bytes that are not the bytes that were declared —
  which is what lets `HeadObject` later return a sha256 we did not compute ourselves and
  did not have to download 25 MB to learn.
* **Keys are random and carry no user input.** The uploader's filename is untrusted and is
  kept only as `Attachment.original_name`, for display and for the `![](zdjecie.jpg)` body
  references. A key that embedded it would put an attacker's string into a URL path, a
  Content-Disposition header and every log line that follows.
"""
import base64
import binascii
import logging
import os
import uuid
from functools import lru_cache

from django.conf import settings

logger = logging.getLogger('security')

# `public/` is what the site serves and what Cloudflare is allowed to cache; `held/` is
# where an escalated or nuked object goes so that every URL ever handed out stops
# resolving (quarantine.py's job, for R2-backed files).
#
# THE HELD OBJECTS BELONG IN A DIFFERENT BUCKET, and that is not a refinement. An R2
# custom domain publishes the WHOLE bucket, so with one bucket `pliki.fuw.lol/held/<key>`
# is as public as `pliki.fuw.lol/public/<key>` — and since the old code derived the held
# key by swapping the prefix, anyone who had kept an attachment's URL could fetch it after
# it was quarantined by editing one word. That is exactly the reader quarantine exists to
# stop, and it was measured against the live bucket (HTTP 200) rather than reasoned about.
#
# So: R2_QUARANTINE_BUCKET is a private bucket with no custom domain. Unset, this falls
# back to the held/ prefix in the same bucket and says so in the security log every time —
# the fallback keeps escalation working on a half-configured deployment, because refusing
# to quarantine is worse than quarantining imperfectly, but it is never silent.
PUBLIC_PREFIX = 'public/'
HELD_PREFIX = 'held/'

# A head-admin's preview of quarantined material: the shortest TTL that is still usable.
PREVIEW_TTL_SECONDS = 300
# How long a browser has to start and finish one upload.
UPLOAD_TTL_SECONDS = 900


class R2Unavailable(RuntimeError):
    """R2 is not configured, or boto3 is missing. Never swallowed into a success path."""


def is_configured() -> bool:
    return bool(getattr(settings, 'R2_BUCKET', '') and getattr(settings, 'R2_ENDPOINT_URL', '')
                and getattr(settings, 'R2_ACCESS_KEY_ID', '') and getattr(settings, 'R2_SECRET_ACCESS_KEY', ''))


@lru_cache(maxsize=1)
def _client():
    """boto3 is imported here and nowhere else, and only when R2 is actually configured, so
    a clone without the dependency still runs the whole test suite — the tests that cover
    the shred path inject a fake through `set_client_for_tests`."""
    if not is_configured():
        raise R2Unavailable('R2 is not configured (FUWLOL_R2_*).')
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:  # pragma: no cover - only on a deployment missing the dep
        raise R2Unavailable('boto3 is not installed.') from exc
    return boto3.client(
        's3',
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name='auto',
        config=Config(signature_version='s3v4', retries={'max_attempts': 3, 'mode': 'standard'}),
    )


_test_client = None


def set_client_for_tests(client):
    """Tests hand in a double. Returns the previous value so a test can put it back."""
    global _test_client
    previous, _test_client = _test_client, client
    return previous


def client():
    if _test_client is not None:
        return _test_client
    return _client()


def bucket() -> str:
    return getattr(settings, 'R2_BUCKET', '')


def quarantine_bucket() -> str:
    """The private bucket held objects live in, or '' when none is configured."""
    return getattr(settings, 'R2_QUARANTINE_BUCKET', '') or ''


def bucket_for(key: str) -> str:
    """Which bucket a key lives in. Every operation below routes through this, so a held
    object is read, previewed and deleted in the right place without any caller having to
    know there are two buckets."""
    if is_held(key) and quarantine_bucket():
        return quarantine_bucket()
    return bucket()


# --- keys ------------------------------------------------------------------------------

def new_key(original_name: str) -> str:
    """`public/attachments/<uuid>.<ext>`. The extension is the only thing taken from the
    uploader's filename, lower-cased, and only after the byte-level validators have agreed
    with it — see archive/validators.py, which decides on content, not on the name."""
    ext = original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else 'bin'
    ext = ''.join(c for c in ext if c.isalnum())[:8] or 'bin'
    return f'{PUBLIC_PREFIX}attachments/{uuid.uuid4().hex}.{ext}'


def held_key(key: str) -> str:
    """A NEW random name under `held/`, not the public key with its prefix rewritten.

    Renaming matters even with a separate bucket, and matters enormously without one: a
    derivable held key means the quarantined object's address is known to everybody who
    ever saw the public one. The extension is kept so a head-admin's preview still renders."""
    ext = key.rsplit('.', 1)[-1] if '.' in key.rsplit('/', 1)[-1] else 'bin'
    return f'{HELD_PREFIX}{uuid.uuid4().hex}.{ext}'


def public_key(key: str) -> str:
    """The reverse, for a release: also a fresh name, because the old public URL may sit
    in somebody's cache or history and should not come back to life."""
    ext = key.rsplit('.', 1)[-1] if '.' in key.rsplit('/', 1)[-1] else 'bin'
    return f'{PUBLIC_PREFIX}attachments/{uuid.uuid4().hex}.{ext}'


def is_held(key: str) -> bool:
    return key.startswith(HELD_PREFIX)


def public_url(key: str) -> str:
    base = getattr(settings, 'R2_PUBLIC_BASE_URL', '').rstrip('/')
    return f'{base}/{key}' if base else ''


# --- checksums -------------------------------------------------------------------------

def sha256_hex_to_b64(hex_digest: str) -> str:
    """R2 speaks base64 in `x-amz-checksum-sha256`; everything else in this project (the
    evidence manifest, the audit log, what a head-admin forwards to Dyżurnet) speaks hex,
    because hex is what a person reads back over the phone without transcription errors."""
    return base64.b64encode(binascii.unhexlify(hex_digest)).decode()


def sha256_b64_to_hex(b64_digest: str) -> str:
    return binascii.hexlify(base64.b64decode(b64_digest)).decode()


# --- the operations ----------------------------------------------------------------------

def presign_put(key: str, *, content_type: str, size_bytes: int, sha256_hex: str) -> dict:
    """A one-shot capability to write exactly these bytes to exactly this key.

    The returned `headers` are not advisory: every one of them is inside the signature, so
    a browser that changes any of them gets a 403 from R2 rather than a stored object."""
    checksum = sha256_hex_to_b64(sha256_hex)
    url = client().generate_presigned_url(
        'put_object',
        Params={'Bucket': bucket(), 'Key': key, 'ContentType': content_type,
                'ContentLength': size_bytes, 'ChecksumSHA256': checksum},
        ExpiresIn=UPLOAD_TTL_SECONDS,
    )
    return {
        'url': url,
        'method': 'PUT',
        'headers': {'Content-Type': content_type, 'Content-Length': str(size_bytes),
                    'x-amz-checksum-sha256': checksum},
        'expires_in': UPLOAD_TTL_SECONDS,
    }


def presign_get(key: str, *, ttl: int = PREVIEW_TTL_SECONDS, filename: str = '') -> str:
    """A short-lived read URL. Used for exactly one thing — showing a head-admin what they
    are deciding about — so the default TTL is five minutes and callers do not get to raise
    it past that. The link is a bearer capability: anyone holding it can fetch the object
    until it expires, which is the reason it is minutes rather than hours."""
    ttl = max(30, min(int(ttl), PREVIEW_TTL_SECONDS))
    params = {'Bucket': bucket_for(key), 'Key': key}
    if filename:
        params['ResponseContentDisposition'] = f'attachment; filename="{os.path.basename(filename)}"'
    return client().generate_presigned_url('get_object', Params=params, ExpiresIn=ttl)


def head_object(key: str) -> dict:
    """`{size, content_type, sha256}` — sha256 in hex, straight from R2's own verification
    of the checksum we signed, or '' if the object carries none. Returns {} if the key does
    not exist, which is how the upload-completion check tells "never uploaded" from "there"."""
    try:
        r = client().head_object(Bucket=bucket_for(key), Key=key, ChecksumMode='ENABLED')
    except Exception as exc:  # botocore raises ClientError for 404 as well
        if _is_not_found(exc):
            return {}
        raise
    checksum = r.get('ChecksumSHA256') or ''
    return {'size': int(r.get('ContentLength') or 0),
            'content_type': r.get('ContentType') or '',
            'sha256': sha256_b64_to_hex(checksum) if checksum else ''}


def move_to_held(key: str) -> str:
    """Take an object off the public prefix. Copy-then-delete, in that order: a failed copy
    leaves the object where it was, which is recoverable, while a failed delete after a
    successful copy leaves a duplicate, which the next call cleans up. Returns the new key.

    The CDN in front keeps its own copy for as long as its TTL says; purging that is
    `escalation.cdn.purge_urls`, called by the same service that calls this."""
    if is_held(key):
        return key
    dest = held_key(key)
    target = quarantine_bucket() or bucket()
    if not quarantine_bucket():
        logger.error('r2.held NO QUARANTINE BUCKET — %s stays in the publicly served '
                     'bucket under a random name; set FUWLOL_R2_QUARANTINE_BUCKET', dest)
    c = client()
    c.copy_object(Bucket=target, Key=dest, CopySource={'Bucket': bucket(), 'Key': key})
    c.delete_object(Bucket=bucket(), Key=key)
    logger.info('r2.held %s/%s -> %s/%s', bucket(), key, target, dest)
    return dest


def move_to_public(key: str) -> str:
    """The reverse, for a declined escalation or an un-nuke."""
    if not is_held(key):
        return key
    dest = public_key(key)
    src = bucket_for(key)
    c = client()
    c.copy_object(Bucket=bucket(), Key=dest, CopySource={'Bucket': src, 'Key': key})
    c.delete_object(Bucket=src, Key=key)
    logger.info('r2.released %s/%s -> %s/%s', src, key, bucket(), dest)
    return dest


def delete_object(key: str) -> None:
    """Irreversible. The bucket must have versioning OFF and no lifecycle rule that keeps a
    copy, or this is a lie — `.env.example` says so where somebody creating the bucket will
    read it. Raises on failure; a shred that cannot prove the delete happened must not be
    recorded as one."""
    client().delete_object(Bucket=bucket_for(key), Key=key)
    logger.warning('r2.deleted bucket=%s key=%s', bucket_for(key), key)


def exists(key: str) -> bool:
    return bool(head_object(key))


def _is_not_found(exc) -> bool:
    code = getattr(exc, 'response', {}).get('Error', {}).get('Code', '') if hasattr(exc, 'response') else ''
    return str(code) in ('404', 'NoSuchKey', 'NotFound')
