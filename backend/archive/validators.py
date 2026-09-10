"""Upload checks. The extension and the browser's Content-Type are both chosen by the
uploader, so the decision is made on the BYTES: Pillow has to decode an image, a PDF
has to start with %PDF, audio/video have to carry their container signature. The
original bytes are kept (a re-encode would kill animated GIFs, which are half of
what a meme archive is), except that JPEG/PNG have their metadata stripped in
`strip_image_metadata` — a phone photo of a lecture hall carries GPS coordinates."""
import io

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

IMAGE_EXT = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
PDF_EXT = {'pdf'}
AUDIO_EXT = {'mp3', 'ogg', 'm4a', 'wav'}
VIDEO_EXT = {'mp4', 'webm'}
OTHER_EXT = {'txt', 'tex'}
ALLOWED_EXT = IMAGE_EXT | PDF_EXT | AUDIO_EXT | VIDEO_EXT | OTHER_EXT

MAX_PIXELS = 40_000_000  # decompression-bomb guard, checked from the header before decoding


def kind_for(name):
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if ext in IMAGE_EXT:
        return 'image'
    if ext in PDF_EXT:
        return 'pdf'
    if ext in AUDIO_EXT:
        return 'audio'
    if ext in VIDEO_EXT:
        return 'video'
    return 'other'


def _head(f, n=64):
    f.seek(0)
    data = f.read(n)
    f.seek(0)
    return data


def validate_upload(f):
    name = getattr(f, 'name', '') or ''
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if ext not in ALLOWED_EXT:
        raise ValidationError(f'Niedozwolony typ pliku: .{ext or "?"} (dozwolone: {", ".join(sorted(ALLOWED_EXT))}).')
    size = getattr(f, 'size', None)
    if size is not None and size > settings.MAX_UPLOAD_BYTES:
        raise ValidationError('Plik jest za duży (limit 25 MB).')
    head = _head(f)
    if ext in IMAGE_EXT:
        try:
            img = Image.open(f)
            if img.width * img.height > MAX_PIXELS:
                raise ValidationError('Obraz ma za dużo pikseli.')
            img.verify()
        except UnidentifiedImageError:
            raise ValidationError('To nie jest prawidłowy obraz.')
        except ValidationError:
            raise
        except Exception:
            raise ValidationError('Nie udało się odczytać obrazu.')
        finally:
            f.seek(0)
    elif ext in PDF_EXT:
        if not head.startswith(b'%PDF'):
            raise ValidationError('To nie jest prawidłowy PDF.')
    elif ext in AUDIO_EXT:
        ok = head.startswith(b'ID3') or head[:2] in (b'\xff\xfb', b'\xff\xf3', b'\xff\xf2') \
            or head.startswith(b'OggS') or head.startswith(b'RIFF') or b'ftyp' in head[:16]
        if not ok:
            raise ValidationError('To nie jest prawidłowy plik audio.')
    elif ext in VIDEO_EXT:
        if not (b'ftyp' in head[:16] or head.startswith(b'\x1aE\xdf\xa3')):
            raise ValidationError('To nie jest prawidłowy plik wideo.')
    else:
        if b'\x00' in head:
            raise ValidationError('Plik tekstowy zawiera dane binarne.')


def strip_image_metadata(f):
    """Return a new in-memory file for JPEG/PNG with EXIF/ICC gone; anything else is
    returned untouched (GIF/WebP may be animated and carry nothing sensitive)."""
    name = getattr(f, 'name', '') or ''
    ext = name.rsplit('.', 1)[-1].lower()
    if ext not in {'jpg', 'jpeg', 'png'}:
        return f
    f.seek(0)
    img = Image.open(f)
    from PIL import ImageOps
    img = ImageOps.exif_transpose(img)
    out = io.BytesIO()
    if ext == 'png':
        img.save(out, format='PNG', optimize=True)
    else:
        img = img.convert('RGB') if img.mode not in ('RGB', 'L') else img
        img.save(out, format='JPEG', quality=90)
    out.seek(0)
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(name, out.read(), content_type=f'image/{"jpeg" if ext != "png" else "png"}')
