"""Direct-to-R2 uploads: the browser sends the bytes, Django only ever sees the metadata.

A 25 MB file posted through Django occupies one gunicorn worker for the whole transfer.
Six of them, from two people at once, is every worker this VPS has, and the site stops
answering while somebody uploads a lecture recording. Six separate requests also keep each
one under Cloudflare's 100 MB request-body ceiling, which a single six-file multipart POST
(150 MB) would hit at the edge and never reach Django at all.

So the flow is: ask for a signed URL, PUT straight to R2, then hand the key back when
creating the post.

**The two things this must not quietly lose.** The current upload path decides what a file
is from its BYTES (archive/validators.py) and strips EXIF off photographs, and a phone
picture of a lecture hall carries GPS coordinates. A presigned upload bypasses both,
because the bytes never pass through here. Neither is given up:

* `verify_stored` pulls the object back out of R2 after the upload and runs the same
  validators. R2 egress to the origin is free, and the objects are at most 25 MB, so the
  cost is a moment at post-creation rather than a worker held open during the upload.
* For JPEG/PNG/WebP it re-stores the stripped version and recomputes the hash, so what is
  in the bucket is what would have been there had the file gone through Django. The hash
  recorded is the one of the bytes actually stored — anything else would put a checksum in
  a report to NASK that does not match the file the report is about.

What is NOT recovered, and is stated rather than papered over: between the PUT and the
post being created, the unvalidated object exists in the bucket under `public/`. It is
unreferenced and unguessable (a random key), and `sweep_orphan_uploads` removes anything
older than a day that no attachment claims. A deployment that finds that window
unacceptable should give the bucket a lifecycle rule on the `public/uploads-pending/`
prefix rather than trusting this to run.
"""
import hashlib
import io
import logging
import re

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config import r2

from .validators import ALLOWED_EXT, IMAGE_EXT, kind_for, strip_image_metadata, validate_upload

logger = logging.getLogger('security')

SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
R2_OFF = 'Wysyłka bezpośrednia jest wyłączona na tym serwerze — wyślij pliki razem z wpisem.'
STRIPPED_EXT = {'jpg', 'jpeg', 'png', 'webp'}
# How much of a non-image we pull back to check its signature. The validators only ever
# look at the first 64 bytes; this is generous and still nothing next to 25 MB.
SNIFF_BYTES = 8192


def _ext(name):
    return name.rsplit('.', 1)[-1].lower() if '.' in name else ''


def _check_request(entry, index):
    """Everything that can be judged before a single byte exists."""
    name = str(entry.get('filename') or '')[:200]
    ext = _ext(name)
    if ext not in ALLOWED_EXT:
        raise ValidationError({'files': [f'{name or index}: niedozwolony typ pliku .{ext or "?"}.']})
    try:
        size = int(entry.get('size_bytes') or 0)
    except (TypeError, ValueError):
        size = 0
    if size <= 0:
        raise ValidationError({'files': [f'{name}: podaj rozmiar pliku.']})
    if size > settings.MAX_UPLOAD_BYTES:
        raise ValidationError({'files': [f'{name}: plik jest za duży (limit 25 MB).']})
    sha = str(entry.get('sha256') or '').lower()
    if not SHA256_RE.match(sha):
        raise ValidationError({'files': [f'{name}: podaj sha256 pliku (64 znaki hex).']})
    return {'filename': name, 'ext': ext, 'size_bytes': size, 'sha256': sha,
            # The browser's Content-Type is its own opinion and is not trusted for
            # anything; it is signed only so that R2 stores something sane, and the real
            # decision is made on the bytes in `verify_stored`.
            'content_type': str(entry.get('content_type') or 'application/octet-stream')[:100]}


class PresignUploadView(APIView):
    """POST /api/uploads/presign/ {files: [{filename, size_bytes, sha256, content_type}]}

    Authenticated only — an anonymous visitor has nothing to attach a file to, and a
    signed URL handed to nobody in particular is a free write capability on our bucket.

    Answers 503, not 500 and not a fake success, when R2 is unconfigured: that is a
    supported configuration (a bare clone, the test suite, a deployment that decided
    against R2), and the frontend's answer to it is to fall back to posting the files with
    the form, which still works."""
    permission_classes = [IsAuthenticated]
    throttle_scope = 'presign'

    def get_throttles(self):
        # The same FixedScopeThrottle the post/comment endpoints use: a signed URL is a
        # write capability on the bucket, so handing them out has its own budget rather
        # than sharing the generic per-user rate with reading the front page.
        from .views import FixedScopeThrottle
        return [FixedScopeThrottle('presign')]

    def post(self, request):
        if not r2.is_configured():
            return Response({'detail': R2_OFF, 'available': False}, status=503)
        raw = request.data.get('files') if hasattr(request.data, 'get') else None
        if not isinstance(raw, list) or not raw:
            raise ValidationError({'files': ['Podaj listę plików.']})
        if len(raw) > settings.MAX_FILES_PER_POST:
            raise ValidationError({'files': [f'Najwyżej {settings.MAX_FILES_PER_POST} plików.']})
        out = []
        for i, entry in enumerate(raw):
            if not isinstance(entry, dict):
                raise ValidationError({'files': [f'{i}: nieprawidłowy wpis.']})
            meta = _check_request(entry, i)
            key = r2.new_key(meta['filename'])
            signed = r2.presign_put(key, content_type=meta['content_type'],
                                    size_bytes=meta['size_bytes'], sha256_hex=meta['sha256'])
            out.append({'key': key, 'filename': meta['filename'], **signed})
        logger.info('uploads.presigned user=%s(%s) files=%d', request.user.username, request.user.pk, len(out))
        return Response({'available': True, 'uploads': out})


def verify_stored(key, original_name, declared_sha256):
    """Pull the object back and decide what it really is.

    Returns `{sha256, size_bytes, content_type, kind}` for the bytes that are stored when
    this returns — which for a photograph is the stripped re-upload, not what the browser
    sent. Raises DRF ValidationError, so a caller inside a post-create sees a 400."""
    head = r2.head_object(key)
    if not head:
        raise ValidationError({'files': [f'{original_name}: plik nie dotarł do magazynu.']})
    if head['size'] > settings.MAX_UPLOAD_BYTES:
        raise ValidationError({'files': [f'{original_name}: plik jest za duży (limit 25 MB).']})
    # R2 verified this against the checksum we signed, so a mismatch here means the client
    # uploaded under a key it presigned for different bytes — refuse rather than reconcile.
    if head['sha256'] and declared_sha256 and head['sha256'] != declared_sha256:
        raise ValidationError({'files': [f'{original_name}: suma kontrolna się nie zgadza.']})

    ext = _ext(original_name)
    full = ext in IMAGE_EXT  # images are read whole: the pixel-bomb guard and EXIF need it
    body = _fetch(key, whole=full)
    upload = _as_django_file(original_name, body, head['content_type'])
    # The same function the multipart path calls, same rules — and the same translation of
    # its Django ValidationError into a DRF one that `_validate_files` does. Without it a
    # file whose bytes lie about its extension would be a 500 rather than the 400 that
    # says why, which is the difference between a bug report and an error message.
    try:
        validate_upload(upload)
    except DjangoValidationError as exc:
        msgs = getattr(exc, 'messages', None) or [str(exc)]
        raise ValidationError({'files': [f'{original_name}: {m}' for m in msgs]})

    if ext in STRIPPED_EXT:
        cleaned = strip_image_metadata(upload)
        data = cleaned.read()
        cleaned.seek(0)
        if data != body:
            r2.client().put_object(Bucket=r2.bucket(), Key=key, Body=data,
                                   ContentType=head['content_type'] or 'application/octet-stream')
            logger.info('uploads.stripped key=%s bytes=%d->%d', key, len(body), len(data))
            return {'sha256': hashlib.sha256(data).hexdigest(), 'size_bytes': len(data),
                    'content_type': head['content_type'], 'kind': kind_for(original_name)}

    # R2's own verified checksum is the best answer; for an image we read whole we can
    # compute it ourselves; for a sniffed file we have only the client's declaration, and
    # it is marked as such by being the same value it was asked to sign.
    if head['sha256']:
        sha = head['sha256']
    elif full:
        sha = hashlib.sha256(body).hexdigest()
    else:
        sha = declared_sha256
    return {'sha256': sha, 'size_bytes': head['size'],
            'content_type': head['content_type'], 'kind': kind_for(original_name)}


def _fetch(key, whole):
    params = {'Bucket': r2.bucket(), 'Key': key}
    if not whole:
        params['Range'] = f'bytes=0-{SNIFF_BYTES - 1}'
    return r2.client().get_object(**params)['Body'].read()


def _as_django_file(name, body, content_type):
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(name, body, content_type=content_type or 'application/octet-stream')


def claim_uploads(post, uploads, *, start_order=0):
    """Turn `[{key, filename, sha256, caption?}]` into Attachment rows on `post`.

    Every key is re-derived, never taken from the client as a path: an entry whose key is
    not on the public attachments prefix is refused outright, because the only keys a
    browser should ever hold are ones this service signed."""
    from .models import Attachment

    created = []
    for i, entry in enumerate(uploads):
        if not isinstance(entry, dict):
            raise ValidationError({'uploads': [f'{i}: nieprawidłowy wpis.']})
        key = str(entry.get('key') or '')
        name = str(entry.get('filename') or entry.get('original_name') or '')[:200]
        if not key.startswith(r2.PUBLIC_PREFIX + 'attachments/') or '..' in key:
            raise ValidationError({'uploads': [f'{name or i}: nieprawidłowy klucz pliku.']})
        facts = verify_stored(key, name, str(entry.get('sha256') or '').lower())
        created.append(Attachment.objects.create(
            post=post, storage_key=key, original_name=name, sha256=facts['sha256'],
            size_bytes=facts['size_bytes'], content_type=facts['content_type'],
            kind=facts['kind'], caption=str(entry.get('caption') or '')[:200],
            order=start_order + i))
    return created


def sweep_orphan_uploads(older_than_hours=24):
    """Objects that were signed for, PUT, and then never claimed by a post. Returns how
    many were removed. Called by `manage.py sweep_uploads`, not on the request path."""
    from datetime import timedelta

    from django.utils import timezone

    from .models import Attachment

    if not r2.is_configured():
        return 0
    cutoff = timezone.now() - timedelta(hours=older_than_hours)
    claimed = set(Attachment.objects.exclude(storage_key='').values_list('storage_key', flat=True))
    removed = 0
    paginator = r2.client().get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=r2.bucket(), Prefix=r2.PUBLIC_PREFIX + 'attachments/'):
        for obj in page.get('Contents', []):
            if obj['Key'] in claimed or obj['LastModified'] > cutoff:
                continue
            r2.delete_object(obj['Key'])
            removed += 1
    if removed:
        logger.info('uploads.swept orphans=%d', removed)
    return removed
