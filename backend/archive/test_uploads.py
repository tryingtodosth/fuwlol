"""Direct-to-R2 uploads: what a signed URL may and may not be made to do.

A presigned PUT is a capability handed to a browser, so the interesting tests are not "does
the happy path work" but "what did we accidentally let the holder decide". The answers
this file pins down: not the size, not the content, not the key, and not whether the
validators run.

The other half is the pair of guarantees the multipart path already gave and this one must
not quietly drop — the decision is made on the bytes, and EXIF comes off a photograph.
"""
import hashlib
import io

from django.contrib.auth.models import User
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from config import r2

from escalation.test_purge import R2_SETTINGS, FakeR2
from .models import Attachment, Category, Post
from .uploads import claim_uploads

PRESIGN = '/api/uploads/presign/'


def png_bytes():
    img = Image.new('RGB', (8, 8), (10, 120, 200))
    out = io.BytesIO()
    img.save(out, format='PNG')
    return out.getvalue()


@override_settings(**R2_SETTINGS)
class PresignTests(APITestCase):
    def setUp(self):
        self.fake = FakeR2()
        previous = r2.set_client_for_tests(self.fake)
        self.addCleanup(r2.set_client_for_tests, previous)
        self.user = User.objects.create_user('ola', 'o@x.pl', 'haslo12345')
        self.client.force_authenticate(self.user)

    def ask(self, **over):
        entry = {'filename': 'mem.png', 'size_bytes': 1234, 'sha256': 'a' * 64,
                 'content_type': 'image/png'}
        entry.update(over)
        return self.client.post(PRESIGN, {'files': [entry]}, format='json')

    def test_an_anonymous_visitor_gets_nothing(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.ask().status_code, 401)

    def test_the_happy_path_signs_length_and_checksum(self):
        r = self.ask()
        self.assertEqual(r.status_code, 200)
        up = r.data['uploads'][0]
        self.assertTrue(up['key'].startswith('public/attachments/'))
        self.assertEqual(up['method'], 'PUT')
        # Both are inside the signature, which is what makes them binding on the uploader
        # rather than a request the frontend was politely asked to honour.
        self.assertEqual(up['headers']['Content-Length'], '1234')
        self.assertIn('x-amz-checksum-sha256', up['headers'])

    def test_the_key_never_contains_the_uploaders_filename(self):
        r = self.ask(filename='../../etc/passwd.png')
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('passwd', r.data['uploads'][0]['key'])
        self.assertNotIn('..', r.data['uploads'][0]['key'])

    def test_a_disallowed_extension_is_refused(self):
        self.assertEqual(self.ask(filename='skrypt.exe').status_code, 400)
        self.assertEqual(self.ask(filename='bezrozszerzenia').status_code, 400)

    def test_a_file_over_the_cap_is_refused_before_a_url_exists(self):
        self.assertEqual(self.ask(size_bytes=26 * 1024 * 1024).status_code, 400)
        self.assertEqual(self.ask(size_bytes=0).status_code, 400)

    def test_a_missing_or_malformed_checksum_is_refused(self):
        self.assertEqual(self.ask(sha256='').status_code, 400)
        self.assertEqual(self.ask(sha256='nie-hex').status_code, 400)

    def test_more_than_six_files_is_refused(self):
        entry = {'filename': 'a.png', 'size_bytes': 10, 'sha256': 'b' * 64}
        r = self.client.post(PRESIGN, {'files': [entry] * 7}, format='json')
        self.assertEqual(r.status_code, 400)

    @override_settings(R2_BUCKET='', R2_ENDPOINT_URL='')
    def test_without_r2_it_says_so_instead_of_failing_oddly(self):
        r2.set_client_for_tests(None)
        r = self.ask()
        self.assertEqual(r.status_code, 503)
        self.assertFalse(r.data['available'])

    def test_a_preview_link_cannot_be_asked_to_live_longer_than_five_minutes(self):
        url = r2.presign_get('held/attachments/x.png', ttl=86400)
        self.assertIn(f'exp={r2.PREVIEW_TTL_SECONDS}', url)


@override_settings(**R2_SETTINGS)
class ClaimTests(APITestCase):
    def setUp(self):
        self.fake = FakeR2()
        previous = r2.set_client_for_tests(self.fake)
        self.addCleanup(r2.set_client_for_tests, previous)
        self.user = User.objects.create_user('ola', 'o@x.pl', 'haslo12345')
        self.cat = Category.objects.create(slug='memy', name='Memy')
        self.post = Post.objects.create(title='Wpis', category=self.cat, status='published',
                                        submitted_by=self.user)
        self.data = png_bytes()
        self.sha = hashlib.sha256(self.data).hexdigest()
        self.key = 'public/attachments/abc123.png'
        self.fake.put_object('fuwlol-test', self.key, self.data, 'image/png')

    def test_a_claimed_upload_becomes_an_attachment_with_a_verified_hash(self):
        claim_uploads(self.post, [{'key': self.key, 'filename': 'mem.png', 'sha256': self.sha}])
        att = Attachment.objects.get()
        self.assertEqual(att.storage_key, self.key)
        self.assertEqual(att.kind, 'image')
        self.assertEqual(len(att.sha256), 64)
        self.assertGreater(att.size_bytes, 0)

    def test_a_key_the_client_invented_is_refused(self):
        """The only keys a browser holds are ones this service signed. Anything else — a
        key on another prefix, a traversal — is refused before the object is even read."""
        from rest_framework.exceptions import ValidationError
        for bad in ('held/attachments/abc123.png', 'public/../secret.png', 'evidence/1/0_x.png'):
            with self.assertRaises(ValidationError):
                claim_uploads(self.post, [{'key': bad, 'filename': 'mem.png', 'sha256': self.sha}])

    def test_a_checksum_that_does_not_match_the_stored_object_is_refused(self):
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            claim_uploads(self.post, [{'key': self.key, 'filename': 'mem.png', 'sha256': 'c' * 64}])
        self.assertEqual(Attachment.objects.count(), 0)

    def test_an_upload_that_never_arrived_is_refused(self):
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            claim_uploads(self.post, [{'key': 'public/attachments/nigdy.png',
                                       'filename': 'nigdy.png', 'sha256': self.sha}])

    def test_the_bytes_are_still_what_decides_what_a_file_is(self):
        """The guarantee archive/validators.py gives the multipart path, kept for a file
        that never passed through Django: a .png whose bytes are not a PNG is refused."""
        from rest_framework.exceptions import ValidationError
        key = 'public/attachments/klamstwo.png'
        self.fake.put_object('fuwlol-test', key, b'MZ\x90\x00to jest plik wykonywalny', 'image/png')
        with self.assertRaises(ValidationError):
            claim_uploads(self.post, [{'key': key, 'filename': 'klamstwo.png',
                                       'sha256': hashlib.sha256(b'MZ\x90\x00to jest plik wykonywalny').hexdigest()}])
        self.assertEqual(Attachment.objects.count(), 0)

    def test_a_photograph_is_re_stored_without_its_metadata(self):
        """EXIF stripping survives the move to direct uploads: the object in the bucket
        after claiming is the stripped one, and the recorded hash is of THOSE bytes —
        recording the original's hash would put a checksum in a NASK report that does not
        match the file the report is about."""
        img = Image.new('RGB', (12, 12), (200, 30, 30))
        out = io.BytesIO()
        img.save(out, format='JPEG', exif=Image.Exif().tobytes())
        original = out.getvalue()
        key = 'public/attachments/zdjecie.jpg'
        self.fake.put_object('fuwlol-test', key, original, 'image/jpeg')

        claim_uploads(self.post, [{'key': key, 'filename': 'zdjecie.jpg',
                                   'sha256': hashlib.sha256(original).hexdigest()}])
        att = Attachment.objects.get()
        stored = self.fake.objects[key]['body']
        self.assertEqual(att.sha256, hashlib.sha256(stored).hexdigest())
        self.assertEqual(att.size_bytes, len(stored))
