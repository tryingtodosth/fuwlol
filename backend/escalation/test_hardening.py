"""The side doors a second audit found around the escalation freeze and the moderation
tiers: the Django admin, the media path, counts, the author's own delete, the reporter's
e-mail — and the throttle/identity holes next to them."""
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from archive import moderation as rules
from archive.models import Attachment, Category, Comment, Post, Report, Tag
from archive.tests import png_bytes
from board.models import Message
from .models import Escalation
from .services import create_escalation, decide_escalation
from .tests import make_trusted


class Base(APITestCase):
    def setUp(self):
        cache.clear()
        override = override_settings(MEDIA_ROOT=tempfile.mkdtemp(), EVIDENCE_ROOT=tempfile.mkdtemp())
        override.enable()
        self.addCleanup(override.disable)
        self.superuser = User.objects.create_superuser('szef', 's@x.pl', 'haslo12345')
        self.staff = User.objects.create_user('mod', 'm@x.pl', 'haslo12345', is_staff=True)
        self.trusted = make_trusted('zaufany')
        self.plain = User.objects.create_user('ola', 'o@x.pl', 'haslo12345')
        self.cat = Category.objects.create(slug='memy', name='Memy')
        self.tag = Tag.objects.create(slug='sesja', name='sesja')
        self.post = Post.objects.create(title='Zły wpis', category=self.cat, body='treść',
                                        status='published', submitted_by=self.plain)
        self.post.tags.add(self.tag)
        self.att = Attachment.objects.create(post=self.post, file=SimpleUploadedFile('a.png', png_bytes()),
                                             original_name='a.png', kind='image')

    def as_(self, u):
        self.client.force_authenticate(u)


class AdminSideDoorTests(Base):
    """A staff moderator with admin access must not read a pending-NASK item at /admin/."""

    def setUp(self):
        super().setUp()
        self.staff.is_superuser = False
        self.staff.save()
        from django.contrib.auth.models import Permission
        self.staff.user_permissions.set(Permission.objects.filter(content_type__app_label__in=['archive', 'board']))
        create_escalation(self.post, self.trusted, 'bardzo złe')
        self.client.force_login(self.staff)

    def test_the_changelist_and_change_page_hide_it_from_staff(self):
        r = self.client.get('/admin/archive/post/')
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('Zły wpis', r.content.decode())
        r = self.client.get(f'/admin/archive/post/{self.post.pk}/change/')
        self.assertIn(r.status_code, (302, 403, 404))  # never the form
        self.assertNotIn('Zły wpis', r.content.decode())

    def test_its_attachments_actions_and_reports_hide_too(self):
        Report.objects.create(post=self.post, reason='other', note='sekret')
        rules.record('hide', self.staff, post=self.post, reason='x', previous_status='published')
        for url in ('/admin/archive/attachment/', '/admin/archive/moderationaction/', '/admin/archive/report/'):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertNotIn('Zły wpis', r.content.decode(), url)

    def test_head_admin_still_sees_it(self):
        self.client.force_login(self.superuser)
        self.assertIn('Zły wpis', self.client.get('/admin/archive/post/').content.decode())

    def test_an_escalated_board_message_hides_in_the_admin(self):
        m = Message.objects.create(nick='x', body='wiadomość do NASK')
        create_escalation(m, self.trusted, 'bardzo złe')
        self.assertNotIn('wiadomość do NASK', self.client.get('/admin/board/message/').content.decode())


class QuarantineTests(Base):
    """The bytes leave MEDIA_ROOT with the content, and come back only when nothing holds them."""

    def _live(self):
        import os
        from django.conf import settings
        return os.path.isfile(os.path.join(settings.MEDIA_ROOT, self.att.file.name))

    def test_escalating_moves_the_file_out_and_declining_moves_it_back(self):
        self.assertTrue(self._live())
        esc = create_escalation(self.post, self.trusted, 'bardzo złe')
        self.assertFalse(self._live())
        decide_escalation(esc, self.superuser, 'decline')
        self.assertTrue(self._live())

    def test_approving_keeps_it_out(self):
        esc = create_escalation(self.post, self.trusted, 'bardzo złe')
        decide_escalation(esc, self.superuser, 'approve')
        self.assertFalse(self._live())

    def test_nuke_moves_it_out_and_unnuke_back(self):
        rules.nuke_post(self.post, self.staff, 'ohyda')
        self.assertFalse(self._live())
        rules.restore_post(self.post, self.staff)
        self.assertTrue(self._live())

    def test_declining_an_escalation_on_a_nuked_post_leaves_it_out(self):
        rules.nuke_post(self.post, self.staff, 'ohyda')
        esc = create_escalation(self.post, self.staff, 'bardzo złe')
        decide_escalation(esc, self.superuser, 'decline')
        self.assertFalse(self._live())  # still nuked
        rules.restore_post(self.post, self.superuser)
        self.assertTrue(self._live())

    def test_the_evidence_copy_is_untouched_by_the_move(self):
        esc = create_escalation(self.post, self.trusted, 'bardzo złe')
        self.as_(self.superuser)
        d = self.client.get(f'/api/moderation/escalations/{esc.pk}/').data
        self.assertEqual(len(d['evidence']['files']), 1)
        r = self.client.get(f"/api/moderation/escalations/{esc.pk}/evidence/{d['evidence']['files'][0]['stored_as']}")
        self.assertEqual(r.status_code, 200)


class OracleTests(Base):
    def test_counts_do_not_admit_an_escalated_post(self):
        self.assertEqual(self.client.get('/api/tags/').data[0]['post_count'], 1)
        create_escalation(self.post, self.trusted, 'bardzo złe')
        self.assertEqual(self.client.get('/api/tags/').data, [])  # a tag with no visible post is not listed
        self.assertEqual(self.client.get('/api/posts/stats/').data['attachments'], 0)

    def test_reporting_an_escalated_post_looks_like_reporting_nothing(self):
        create_escalation(self.post, self.trusted, 'bardzo złe')
        r = self.client.post('/api/reports/', {'post': self.post.slug, 'reason': 'other'})
        self.assertEqual(r.status_code, 400)
        r2 = self.client.post('/api/reports/', {'post': 'nie-ma-takiego', 'reason': 'other'})
        self.assertEqual(r2.status_code, 400)
        self.assertEqual(Report.objects.count(), 0)

    def test_the_author_cannot_delete_an_escalated_comment(self):
        c = Comment.objects.create(post=self.post, author=self.plain, body='zły komentarz')
        create_escalation(c, self.trusted, 'bardzo złe')
        self.as_(self.plain)
        self.assertEqual(self.client.delete(f'/api/comments/{c.pk}/').status_code, 404)
        c.refresh_from_db()
        self.assertFalse(c.is_removed)

    def test_an_escalated_comment_is_not_a_parent_for_a_reply(self):
        c = Comment.objects.create(post=self.post, author=self.plain, body='zły komentarz')
        create_escalation(c, self.trusted, 'bardzo złe')
        self.as_(self.plain)
        r = self.client.post(f'/api/posts/{self.post.slug}/comments/', {'body': 'odp', 'parent': c.pk})
        self.assertEqual(r.status_code, 400)


class TierLeakTests(Base):
    def test_a_reporters_contact_and_note_are_for_staff_only(self):
        # a hidden post with an OPEN report on the board (a hide resolves reports, so the
        # report is filed after the hide — as a second complaint would be)
        rules.hide_post(self.post, self.staff, 'x')
        Report.objects.create(post=self.post, reason='privacy', note='to ja na zdjęciu', contact_email='ja@x.pl')
        self.as_(self.staff)
        staff_view = self.client.get('/api/moderation/board/').data['posts'][0]
        self.assertEqual(staff_view['reports'][0]['contact_email'], 'ja@x.pl')
        self.assertEqual(staff_view['reports'][0]['note'], 'to ja na zdjęciu')
        self.as_(self.trusted)
        trusted_view = self.client.get('/api/moderation/board/').data['posts'][0]
        self.assertEqual(trusted_view['reports'][0]['reason'], 'privacy')  # that it was reported, and why
        self.assertEqual(trusted_view['reports'][0]['contact_email'], '')  # never whose
        self.assertEqual(trusted_view['reports'][0]['note'], '')

    def test_the_review_note_is_for_the_author_and_staff(self):
        self.post.review_note = 'popraw tytuł'
        self.post.save()
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/').data['review_note'], '')
        self.as_(self.plain)
        self.assertEqual(self.client.get(f'/api/posts/{self.post.slug}/').data['review_note'], 'popraw tytuł')


class ThrottleTests(Base):
    def test_comments_have_their_own_rate(self):
        from rest_framework.throttling import SimpleRateThrottle
        self.as_(self.plain)
        with patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'comment_create': '2/hour'}):
            for i in range(2):
                self.assertEqual(self.client.post(f'/api/posts/{self.post.slug}/comments/', {'body': f'k{i}'}).status_code, 201)
            self.assertEqual(self.client.post(f'/api/posts/{self.post.slug}/comments/', {'body': 'k3'}).status_code, 429)

    def test_post_creation_is_actually_rate_limited(self):
        # the scope used to be set on a bare ScopedRateThrottle, which reads it off the view
        # and therefore never limited anything — a regression test for FixedScopeThrottle
        from rest_framework.throttling import SimpleRateThrottle
        self.as_(self.plain)
        body = {'title': 'Nowy', 'category': 'memy', 'format': 'text', 'body': 'x', 'rights_confirmed': 'true'}
        with patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'post_create': '1/hour'}):
            self.assertEqual(self.client.post('/api/posts/', body).status_code, 201)
            self.assertEqual(self.client.post('/api/posts/', {'rights_confirmed': 'true', **body, 'title': 'Drugi'}).status_code, 429)

    def test_login_is_also_limited_per_username_across_addresses(self):
        from rest_framework.throttling import SimpleRateThrottle
        with patch.dict(SimpleRateThrottle.THROTTLE_RATES, {'login_user': '2/min', 'login': '100/min'}), \
                override_settings(FUWLOL_TRUST_PROXY=True, FUWLOL_PROXY_HOPS=1):
            for i in range(2):
                r = self.client.post('/api/auth/login/', {'username': 'ola', 'password': 'zle'}, HTTP_X_FORWARDED_FOR=f'10.0.0.{i}')
                self.assertEqual(r.status_code, 401)
            r = self.client.post('/api/auth/login/', {'username': 'OLA', 'password': 'zle'}, HTTP_X_FORWARDED_FOR='10.0.0.9')
            self.assertEqual(r.status_code, 429)  # a third host, same account, capitalised — still counted


class IdentityTests(Base):
    def test_a_guest_nick_may_not_be_a_username_in_disguise(self):
        for nick in ('Pіotr', 'o.la', 'O_LA'):  # Cyrillic і; punctuation; case
            User.objects.get_or_create(username='Piotr')
            r = self.client.post('/api/board/', {'nick': nick, 'body': 'hej', 'website': ''})
            self.assertEqual(r.status_code, 400, nick)

    def test_ip_hash_uses_its_own_salt(self):
        from board.models import hash_ip
        with override_settings(FUWLOL_IP_SALT='sól-a'):
            a = hash_ip('1.2.3.4')
        with override_settings(FUWLOL_IP_SALT='sól-b'):
            b = hash_ip('1.2.3.4')
        self.assertNotEqual(a, b)
        self.assertEqual(len(a), 64)

    def test_webp_metadata_is_dropped(self):
        import io
        from PIL import Image
        from archive.validators import strip_image_metadata
        buf = io.BytesIO()
        img = Image.new('RGB', (4, 4), (1, 2, 3))
        exif = img.getexif()
        exif[0x010F] = 'Telefon'  # Make
        img.save(buf, format='WEBP', exif=exif.tobytes())
        self.assertTrue(Image.open(io.BytesIO(buf.getvalue())).getexif())
        out = strip_image_metadata(SimpleUploadedFile('p.webp', buf.getvalue()))
        self.assertFalse(Image.open(io.BytesIO(out.read())).getexif())


class SeedTests(Base):
    def test_seed_demo_never_resets_an_existing_password(self):
        from django.core.management import call_command
        dz = User.objects.create_user('dziekan', 'd@x.pl', 'moje-nowe-haslo-9', is_staff=True, is_superuser=True)
        call_command('seed_demo', verbosity=0)
        dz.refresh_from_db()
        self.assertTrue(dz.check_password('moje-nowe-haslo-9'))
