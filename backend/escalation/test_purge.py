"""The criminal path, end to end — and every way somebody could see what they must not.

Two questions are being answered here, and they are not the same question.

The first is access: a trusted student volunteer moderating a meme archive must never be
able to reach material in critical quarantine, and neither must a staff account. That is
not only a privacy rule; under art. 202 § 4a/b k.k. looking at it is itself an exposure,
and nobody acquires that by volunteering. So the tests try every door — the API detail
endpoint, the moderation board, the escalation list, the Django admin, and the ORM itself.

The second is the purge: that after a report to Dyżurnet.pl, every copy is gone — R2, the
local media file, the quarantine copy AND the frozen evidence copy — that the immutable
record survives it, and above all that a FAILED purge can never leave destroyed bytes with
no record of what was destroyed. That last one is the property the whole ordering in
shred.py exists to provide, so it is tested by breaking the delete on purpose.
"""
import io
import tempfile
from pathlib import Path

from django.contrib.auth.models import Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from config import r2

from archive.models import Attachment, Post
from .models import EvidenceAuditLog
from .services import confirm_nask_report_and_purge, create_escalation, decide_escalation
from .tests import Base

R2_SETTINGS = dict(R2_BUCKET='fuwlol-test', R2_ENDPOINT_URL='https://example.r2.cloudflarestorage.com',
                   R2_ACCESS_KEY_ID='key', R2_SECRET_ACCESS_KEY='secret',
                   R2_PUBLIC_BASE_URL='https://pliki.fuw.lol',
                   R2_QUARANTINE_BUCKET='fuwlol-test-quarantine')


class NotFound(Exception):
    response = {'Error': {'Code': '404'}}


class FakeR2:
    """An in-memory bucket. Small on purpose: the point of the tests below is what this
    project does, not what botocore does, and a double that is easy to break in a specific
    way (`fail_delete`) is what makes the fail-safe test possible at all."""

    def __init__(self):
        self.objects = {}
        self.fail_delete = False
        self.deleted = []

    def put_object(self, Bucket, Key, Body, ContentType='', **kw):
        import hashlib
        data = Body if isinstance(Body, bytes) else Body.read()
        self.objects[Key] = {'body': data, 'content_type': ContentType, 'bucket': Bucket,
                             'sha256': hashlib.sha256(data).hexdigest()}
        return {}

    def head_object(self, Bucket, Key, **kw):
        o = self.objects.get(Key)
        # The bucket is checked, not ignored: a double that answers for any bucket would
        # hide a routing bug, and routing is the whole point of the quarantine bucket.
        if o is None or o['bucket'] != Bucket:
            raise NotFound()
        import base64
        import binascii
        return {'ContentLength': len(o['body']), 'ContentType': o['content_type'],
                'ChecksumSHA256': base64.b64encode(binascii.unhexlify(o['sha256'])).decode()}

    def get_object(self, Bucket, Key, Range=None, **kw):
        o = self.objects[Key]
        if o['bucket'] != Bucket:
            raise NotFound()
        body = o['body']
        if Range:
            end = int(Range.split('-')[1]) + 1
            body = body[:end]
        return {'Body': io.BytesIO(body)}

    def copy_object(self, Bucket, Key, CopySource, **kw):
        src = self.objects[CopySource['Key']]
        if src['bucket'] != CopySource['Bucket']:
            raise NotFound()
        self.objects[Key] = dict(src, bucket=Bucket)
        return {}

    def delete_object(self, Bucket, Key, **kw):
        if self.fail_delete:
            raise RuntimeError('R2 niedostępne')
        o = self.objects.get(Key)
        if o is not None and o['bucket'] != Bucket:
            raise NotFound()
        self.deleted.append(Key)
        self.objects.pop(Key, None)
        return {}

    def bucket_of(self, key):
        return self.objects[key]['bucket']

    def generate_presigned_url(self, op, Params, ExpiresIn):
        return f'https://example.r2/{Params["Key"]}?op={op}&exp={ExpiresIn}'


@override_settings(**R2_SETTINGS)
class R2Base(Base):
    def setUp(self):
        super().setUp()
        self.fake = FakeR2()
        previous = r2.set_client_for_tests(self.fake)
        self.addCleanup(r2.set_client_for_tests, previous)
        self.post.submitter_ip = '198.51.100.7'
        self.post.submitter_user_agent = 'Mozilla/5.0 (przeglądarka studenta)'
        self.post.save()
        self.body = b'\x89PNG\r\n\x1a\n-udawany-plik'
        import hashlib
        self.sha = hashlib.sha256(self.body).hexdigest()
        self.key = 'public/attachments/deadbeef.png'
        self.fake.put_object('fuwlol-test', self.key, self.body, 'image/png')
        self.att = Attachment.objects.create(post=self.post, storage_key=self.key, sha256=self.sha,
                                             size_bytes=len(self.body), content_type='image/png',
                                             original_name='zdjecie.png', kind='image')

    def escalate(self):
        return create_escalation(self.post, self.trusted, 'podejrzenie materiału przestępczego')

    def approved(self):
        esc = self.escalate()
        return decide_escalation(esc, self.superuser, 'approve')


class NobodyElseCanSeeItTests(R2Base):
    """Quarantined material, from every direction somebody might come at it."""

    def test_the_default_manager_does_not_return_it_at_all(self):
        self.escalate()
        self.assertFalse(Post.objects.filter(pk=self.post.pk).exists())
        self.assertTrue(Post.all_objects.filter(pk=self.post.pk).exists())
        self.assertEqual(Post.all_objects.get(pk=self.post.pk).status, 'quarantined')

    def test_the_public_detail_endpoint_is_a_404(self):
        self.escalate()
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/').status_code, 404)

    def test_a_trusted_moderator_gets_a_404_and_an_empty_board(self):
        self.escalate()
        self.as_(self.trusted)
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/').status_code, 404)
        board = self.client.get('/api/moderation/board/')
        self.assertNotIn(self.post.pk, [p.get('id') for p in board.data.get('posts', [])])

    def test_staff_gets_a_404_too(self):
        """`is_staff` is the tier that reads nuked content. It is NOT this tier."""
        self.escalate()
        self.as_(self.staff)
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/').status_code, 404)

    def test_staff_cannot_list_or_open_the_quarantine_queue(self):
        esc = self.escalate()
        self.as_(self.staff)
        self.assertEqual(self.client.get('/api/moderation/escalations/').status_code, 403)
        self.assertEqual(self.client.get(f'/api/moderation/escalations/{esc.pk}/').status_code, 403)
        self.assertEqual(self.client.get('/api/moderation/evidence-audit/').status_code, 403)

    def test_the_head_admin_can_still_read_it(self):
        """The one exception, and it has to work: somebody has to look at the thing to
        decide about it, and the manager filter must not lock the responsible person out."""
        self.escalate()
        self.as_(self.superuser)
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/').status_code, 200)
        self.assertEqual(len(self.client.get('/api/moderation/escalations/').data), 1)

    def test_a_granted_permission_is_head_admin_without_being_a_superuser(self):
        second = User.objects.create_user('wicedziekan', 'w@x.pl', 'haslo12345')
        second.user_permissions.add(Permission.objects.get(codename='can_manage_critical_quarantine'))
        second = User.objects.get(pk=second.pk)  # permission caching
        self.escalate()
        self.as_(second)
        self.assertEqual(self.client.get('/api/moderation/escalations/').status_code, 200)
        self.assertFalse(second.is_superuser)

    def test_the_object_leaves_the_public_bucket_entirely(self):
        """An R2 custom domain publishes the WHOLE bucket, so moving an object to a
        `held/` prefix inside the same bucket hides it from nobody. Measured against the
        real bucket before this was fixed: the held URL answered HTTP 200."""
        self.escalate()
        self.att.refresh_from_db()
        self.assertTrue(self.att.storage_key.startswith('held/'))
        self.assertNotIn(self.key, self.fake.objects)            # gone from where it was
        self.assertEqual(self.fake.bucket_of(self.att.storage_key), 'fuwlol-test-quarantine')
        self.assertEqual(self.att.public_url, '')

    def test_the_held_key_cannot_be_derived_from_the_public_one(self):
        """The old code swapped the prefix, so anyone who had kept an attachment's URL
        could reach the quarantined object by editing one word of it."""
        self.escalate()
        self.att.refresh_from_db()
        uuid_part = self.key.rsplit('/', 1)[-1]
        self.assertNotIn(uuid_part, self.att.storage_key)
        self.assertNotEqual(self.att.storage_key, self.key.replace('public/', 'held/', 1))

    def test_a_release_gives_the_object_a_new_public_name(self):
        """Not the name it had before: the old URL may sit in a cache or somebody's
        history, and releasing content should not resurrect an address that was handed
        out while the content was under review."""
        esc = self.escalate()
        old_key = self.key
        decide_escalation(esc, self.superuser, 'decline')
        self.att.refresh_from_db()
        self.assertTrue(self.att.storage_key.startswith('public/'))
        self.assertNotEqual(self.att.storage_key, old_key)
        self.assertEqual(self.fake.bucket_of(self.att.storage_key), 'fuwlol-test')

    def test_a_decline_puts_everything_back(self):
        esc = self.escalate()
        decide_escalation(esc, self.superuser, 'decline')
        self.post.refresh_from_db()
        self.att.refresh_from_db()
        self.assertEqual(self.post.status, 'published')
        self.assertTrue(self.att.storage_key.startswith('public/'))
        self.assertTrue(Post.objects.filter(pk=self.post.pk).exists())
        self.assertTrue(self.att.public_url.startswith('https://pliki.fuw.lol/'))


class PurgeRefusalTests(R2Base):
    def test_a_pending_escalation_cannot_be_purged(self):
        esc = self.escalate()
        self.as_(self.superuser)
        r = self.client.post(f'/api/moderation/escalations/{esc.pk}/purge/', {'confirmed_dispatch': True})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(EvidenceAuditLog.objects.count(), 0)
        self.att.refresh_from_db()   # quarantine moved it to held/ — but it still EXISTS
        self.assertIn(self.att.storage_key, self.fake.objects)

    def test_without_an_explicit_confirmation_nothing_is_destroyed(self):
        """Calling the endpoint is not the same statement as "I have sent it to NASK"."""
        esc = self.approved()
        self.as_(self.superuser)
        r = self.client.post(f'/api/moderation/escalations/{esc.pk}/purge/', {})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(EvidenceAuditLog.objects.count(), 0)
        self.att.refresh_from_db()
        self.assertIn(self.att.storage_key, self.fake.objects)

    def test_a_trusted_moderator_cannot_purge(self):
        esc = self.approved()
        self.as_(self.trusted)
        r = self.client.post(f'/api/moderation/escalations/{esc.pk}/purge/', {'confirmed_dispatch': True})
        self.assertEqual(r.status_code, 403)

    def test_purging_twice_is_refused(self):
        esc = self.approved()
        confirm_nask_report_and_purge(esc, self.superuser, confirmed_dispatch=True, case_reference='DYZ/1')
        self.as_(self.superuser)
        r = self.client.post(f'/api/moderation/escalations/{esc.pk}/purge/', {'confirmed_dispatch': True})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(EvidenceAuditLog.objects.count(), 1)


class PurgeTests(R2Base):
    def test_the_whole_thing(self):
        esc = self.approved()
        self.as_(self.superuser)
        r = self.client.post(f'/api/moderation/escalations/{esc.pk}/purge/',
                             {'confirmed_dispatch': True, 'case_reference': 'DYZ/2026/114'},
                             format='json')
        self.assertEqual(r.status_code, 200)

        # the bytes are gone from R2
        self.assertEqual(self.fake.objects, {})
        # the row survives as a tombstone, with nothing left pointing at bytes
        self.att.refresh_from_db()
        self.assertEqual(self.att.storage_key, '')
        self.assertEqual(self.att.size_bytes, 0)
        self.assertEqual(self.att.original_name, 'zdjecie.png')
        # the statuses
        self.post.refresh_from_db()
        esc.refresh_from_db()
        self.assertEqual(self.post.status, 'purged')
        self.assertEqual(esc.status, 'purged')
        self.assertIsNotNone(esc.purged_at)
        self.assertIsNotNone(esc.reported_to_nask_at)
        # and the only thing that outlives it
        row = EvidenceAuditLog.objects.get()
        self.assertEqual(row.file_sha256, self.sha)
        self.assertEqual(row.uploader_ip, '198.51.100.7')
        self.assertIn('przeglądarka studenta', row.uploader_user_agent)
        self.assertEqual(row.nask_case_reference, 'DYZ/2026/114')
        self.assertEqual(row.reported_by_username, 'szef')
        self.assertEqual(row.target_kind, 'post')
        self.assertEqual(row.original_post_id, self.post.pk)

    def test_after_the_purge_the_public_is_gone_and_the_head_admin_sees_a_tombstone(self):
        """What survives is deliberately asymmetric. To everybody else the post stops
        existing — 'purged' is not a readable status for any tier, so the rule that already
        governs statuses answers this without needing the escalation row to still be open.
        A head-admin can still open it, and finds a post with no files: the record that
        something was here and was destroyed, which is the thing they may later be asked
        about. What they cannot find, because it no longer exists anywhere, is the file."""
        esc = self.approved()
        confirm_nask_report_and_purge(esc, self.superuser, confirmed_dispatch=True)

        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/').status_code, 404)
        self.as_(self.trusted)
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/').status_code, 404)
        self.as_(self.staff)
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/').status_code, 404)

        self.as_(self.superuser)
        r = self.client.get(f'/api/posts/{self.post.slug}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual([a['url'] for a in r.data['attachments']], [''])

    def test_the_audit_row_cannot_be_edited_or_deleted(self):
        esc = self.approved()
        confirm_nask_report_and_purge(esc, self.superuser, confirmed_dispatch=True)
        row = EvidenceAuditLog.objects.get()
        row.nask_case_reference = 'przepisane'
        with self.assertRaises(ValueError):
            row.save()
        with self.assertRaises(ValueError):
            row.delete()
        self.assertEqual(EvidenceAuditLog.objects.get().nask_case_reference, '')

    def test_a_text_only_target_still_leaves_exactly_one_record(self):
        esc = create_escalation(self.msg, self.trusted, 'groźby')
        decide_escalation(esc, self.superuser, 'approve')
        confirm_nask_report_and_purge(esc, self.superuser, confirmed_dispatch=True, case_reference='DYZ/3')
        row = EvidenceAuditLog.objects.get()
        self.assertEqual(row.target_kind, 'message')
        self.assertEqual(row.file_sha256, esc.evidence_ref)


class FailSafeTests(R2Base):
    """The property the ordering in shred.py exists for: bytes are never destroyed without
    a record, and a purge that half-failed can be finished rather than needing a rescue."""

    def test_a_failed_delete_records_the_report_and_refuses_to_claim_success(self):
        esc = self.approved()
        self.fake.fail_delete = True
        self.as_(self.superuser)
        r = self.client.post(f'/api/moderation/escalations/{esc.pk}/purge/',
                             {'confirmed_dispatch': True, 'case_reference': 'DYZ/9'}, format='json')

        self.assertEqual(r.status_code, 409)          # the world moved, nothing is broken
        self.assertTrue(r.data['failures'])
        esc.refresh_from_db()
        self.post.refresh_from_db()
        self.assertEqual(esc.status, 'approved')      # NOT purged: the bytes are still there
        self.assertEqual(self.post.status, 'quarantined')
        self.assertEqual(EvidenceAuditLog.objects.count(), 1)   # …but the report IS on record
        self.att.refresh_from_db()
        self.assertNotEqual(self.att.storage_key, '')  # and the row still points at them

    def test_retrying_after_the_failure_completes_it_without_duplicating_the_record(self):
        esc = self.approved()
        self.fake.fail_delete = True
        self.as_(self.superuser)
        self.client.post(f'/api/moderation/escalations/{esc.pk}/purge/',
                         {'confirmed_dispatch': True, 'case_reference': 'DYZ/9'}, format='json')
        self.fake.fail_delete = False
        r = self.client.post(f'/api/moderation/escalations/{esc.pk}/purge/',
                             {'confirmed_dispatch': True, 'case_reference': 'DYZ/9'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(EvidenceAuditLog.objects.count(), 1)
        self.assertEqual(self.fake.objects, {})
        esc.refresh_from_db()
        self.assertEqual(esc.status, 'purged')

    def test_an_unconfigured_bucket_refuses_rather_than_pretending(self):
        """R2 goes away between the escalation and the purge — a plausible order, and the
        only one worth testing: breaking it BEFORE the escalation would be testing a
        deployment that could never have stored the file in the first place."""
        esc = self.approved()
        self.as_(self.superuser)
        with override_settings(R2_BUCKET='', R2_ENDPOINT_URL=''):
            r2.set_client_for_tests(None)
            r = self.client.post(f'/api/moderation/escalations/{esc.pk}/purge/',
                                 {'confirmed_dispatch': True}, format='json')
        self.assertEqual(r.status_code, 409)
        esc.refresh_from_db()
        self.assertEqual(esc.status, 'approved')


class LocalFileShredTests(Base):
    """The pre-R2 storage path, which every existing row and every bare clone still uses.
    Three copies exist by the time a purge runs, and the test names all three because
    missing one is what would make the purge a fiction."""

    def setUp(self):
        super().setUp()
        self.att = Attachment.objects.create(
            post=self.post, file=SimpleUploadedFile('notatka.txt', b'tresc pliku'),
            original_name='notatka.txt', kind='other')

    def test_every_local_copy_is_destroyed(self):
        from django.conf import settings
        esc = create_escalation(self.post, self.trusted, 'materiał przestępczy')
        decide_escalation(esc, self.superuser, 'approve')

        name = self.att.file.name          # 'attachments/<uuid>.txt' — the stored name
        quarantined = Path(settings.EVIDENCE_ROOT) / 'quarantine' / name
        evidence_dir = Path(settings.EVIDENCE_ROOT) / str(esc.pk)
        copies = lambda: sorted(p.name for p in evidence_dir.iterdir())  # noqa: E731
        self.assertTrue(quarantined.is_file())                     # moved off the public path
        self.assertEqual(len(copies()), 2)                         # manifest.json + the file

        confirm_nask_report_and_purge(esc, self.superuser, confirmed_dispatch=True)

        self.assertFalse((Path(settings.MEDIA_ROOT) / name).exists())
        self.assertFalse(quarantined.exists())
        self.assertEqual(copies(), ['manifest.json'])
        self.assertTrue((evidence_dir / 'manifest.json').is_file())  # the metadata stays
        row = EvidenceAuditLog.objects.get()
        self.assertEqual(len(row.file_sha256), 64)
        self.assertEqual(row.original_name, name)


class CommentAttachmentPurgeTests(Base):
    """A file on a COMMENT is the same offence and the same duty as a file on a post, and
    `CommentAttachment` is a different model with fewer columns. This is the test that
    would have caught the purge raising at its very last step — after the bytes were
    already gone, which is the one failure mode with nothing left to retry."""

    def test_a_comment_attachment_is_purged_like_any_other(self):
        from archive.models import Comment, CommentAttachment

        comment = Comment.objects.create(post=self.post, author=self.plain, body='a to zdjęcie')
        att = CommentAttachment.objects.create(
            comment=comment, file=SimpleUploadedFile('zal.txt', b'zawartosc'),
            original_name='zal.txt')
        name = att.file.name

        esc = create_escalation(comment, self.trusted, 'materiał przestępczy w komentarzu')
        decide_escalation(esc, self.superuser, 'approve')
        confirm_nask_report_and_purge(esc, self.superuser, confirmed_dispatch=True, case_reference='DYZ/7')

        from django.conf import settings
        self.assertFalse((Path(settings.MEDIA_ROOT) / name).exists())
        self.assertFalse((Path(settings.EVIDENCE_ROOT) / 'quarantine' / name).exists())
        att.refresh_from_db()
        self.assertEqual(att.file.name, '')
        row = EvidenceAuditLog.objects.get()
        self.assertEqual(row.target_kind, 'comment')
        self.assertEqual(row.original_post_id, comment.pk)
        self.assertEqual(len(row.file_sha256), 64)
