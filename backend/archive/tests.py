import io
import tempfile

from django.test import override_settings

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APITestCase

from .models import Category, Comment, Person, Post, Report


def png_bytes(w=8, h=8):
    buf = io.BytesIO()
    Image.new('RGB', (w, h), (200, 30, 30)).save(buf, format='PNG')
    return buf.getvalue()


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class Base(APITestCase):
    def setUp(self):
        self.cat = Category.objects.create(slug='memy', name='Memy')
        self.person = Person.objects.create(slug='kwant', name='dr Kwant')
        self.staff = User.objects.create_user('mod', 'm@x.pl', 'haslo12345', is_staff=True)
        self.user = User.objects.create_user('ola', 'o@x.pl', 'haslo12345')
        self.other = User.objects.create_user('bartek', 'b@x.pl', 'haslo12345')

    def login(self, u):
        self.client.force_authenticate(u)

    def make_published(self, title='Wpis', **kw):
        return Post.objects.create(title=title, category=self.cat, body='treść', status='published', **kw)


class AuthTests(APITestCase):
    def test_register_login_me(self):
        r = self.client.post('/api/auth/register/', {'username': 'nowy', 'password': 'bardzo-tajne-1'})
        self.assertEqual(r.status_code, 201, r.data)
        token = r.data['token']
        r = self.client.post('/api/auth/login/', {'username': 'nowy', 'password': 'bardzo-tajne-1'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['token'], token)
        r = self.client.get('/api/auth/me/', HTTP_AUTHORIZATION=f'Token {token}')
        self.assertEqual(r.data['username'], 'nowy')
        r = self.client.post('/api/auth/login/', {'username': 'nowy', 'password': 'zle'})
        self.assertEqual(r.status_code, 401)

    def test_duplicate_username_rejected(self):
        User.objects.create_user('nowy', '', 'x')
        r = self.client.post('/api/auth/register/', {'username': 'Nowy', 'password': 'bardzo-tajne-1'})
        self.assertEqual(r.status_code, 400)


class SubmissionTests(Base):
    def test_text_post_with_image_waits_for_moderation(self):
        self.login(self.user)
        f = SimpleUploadedFile('zdjecie.png', png_bytes(), content_type='image/png')
        r = self.client.post('/api/posts/', {
            'title': 'Mem o sesji', 'category': 'memy', 'format': 'text', 'body': 'Patrz ![](zdjecie.png)',
            'year': 2020, 'people': 'kwant', 'tags': 'sesja, Pasteura 5', 'files': [f]}, format='multipart')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['status'], 'pending')
        self.assertEqual(r.data['attachments'][0]['original_name'], 'zdjecie.png')
        self.assertEqual(r.data['attachments'][0]['kind'], 'image')
        self.assertEqual([p['slug'] for p in r.data['people']], ['kwant'])
        self.assertEqual(sorted(t['slug'] for t in r.data['tags']), ['pasteura-5', 'sesja'])
        slug = r.data['slug']
        # invisible in the public list, visible to its own author, invisible to somebody else
        self.assertEqual(self.client.get('/api/posts/').data['count'], 0)
        self.assertEqual(self.client.get(f'/api/posts/{slug}/').status_code, 200)
        self.login(self.other)
        self.assertEqual(self.client.get(f'/api/posts/{slug}/').status_code, 404)
        # the moderator publishes it
        self.login(self.staff)
        r = self.client.post(f'/api/posts/{slug}/moderate/', {'decision': 'publish', 'note': 'ok'})
        self.assertEqual(r.status_code, 200)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/posts/').data['count'], 1)
        self.assertEqual(self.client.get(f'/api/posts/{slug}/').data['catalog_no'], f'FUW-{r.data["id"]:04d}')

    def test_latex_post(self):
        self.login(self.user)
        body = r'\documentclass{article}\begin{document}$E=mc^2$ \includegraphics{a.png}\end{document}'
        f = SimpleUploadedFile('a.png', png_bytes(), content_type='image/png')
        r = self.client.post('/api/posts/', {'title': 'Zadanie', 'category': 'memy', 'format': 'latex',
                                             'body': body, 'files': [f]}, format='multipart')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['format'], 'latex')
        self.assertEqual(r.data['body'], body)

    def test_auto_summary_drops_maths_and_syntax(self):
        self.login(self.user)
        r = self.client.post('/api/posts/', {'title': 'X', 'category': 'memy', 'body': 'Oto **mem** i wzór $\\int_0^1 x\\,dx$. Koniec.'})
        self.assertEqual(r.data['summary'], 'Oto mem i wzór $\\int_0^1 x\\,dx$. Koniec.')
        r = self.client.post('/api/posts/', {'title': 'Y', 'category': 'memy', 'format': 'latex',
                                             'body': '\\section*{Zad} Policz \\[ e^x \\] \\textbf{teraz}.'})
        self.assertEqual(r.data['summary'], 'Zad Policz $e^x$ teraz.')
        r = self.client.post('/api/posts/', {'title': 'Z', 'category': 'memy', 'body': 'x', 'summary': 'własne'})
        self.assertEqual(r.data['summary'], 'własne')

    def test_staff_publish_immediately(self):
        self.login(self.staff)
        r = self.client.post('/api/posts/', {'title': 'X', 'category': 'memy', 'body': 'y'})
        self.assertEqual(r.data['status'], 'published')

    def test_disguised_executable_rejected(self):
        self.login(self.user)
        f = SimpleUploadedFile('virus.png', b'MZ\x90\x00' + b'\x00' * 100, content_type='image/png')
        r = self.client.post('/api/posts/', {'title': 'X', 'category': 'memy', 'body': 'y', 'files': [f]}, format='multipart')
        self.assertEqual(r.status_code, 400)
        self.assertIn('files', r.data)
        self.assertEqual(Post.objects.count(), 0)

    def test_unknown_extension_and_fake_pdf_rejected(self):
        self.login(self.user)
        for name, data in [('a.exe', b'MZ'), ('a.pdf', b'not a pdf')]:
            f = SimpleUploadedFile(name, data)
            r = self.client.post('/api/posts/', {'title': 'X', 'category': 'memy', 'body': 'y', 'files': [f]}, format='multipart')
            self.assertEqual(r.status_code, 400, name)

    def test_empty_post_rejected(self):
        self.login(self.user)
        r = self.client.post('/api/posts/', {'title': 'X', 'category': 'memy', 'body': '  '})
        self.assertEqual(r.status_code, 400)

    def test_anonymous_cannot_submit(self):
        r = self.client.post('/api/posts/', {'title': 'X', 'category': 'memy', 'body': 'y'})
        self.assertEqual(r.status_code, 401)

    def test_jpeg_metadata_is_stripped(self):
        img = Image.new('RGB', (8, 8), (1, 2, 3))
        buf = io.BytesIO()
        exif = Image.Exif()
        exif[0x010f] = 'PhoneMaker'
        img.save(buf, format='JPEG', exif=exif)
        self.login(self.user)
        f = SimpleUploadedFile('p.jpg', buf.getvalue(), content_type='image/jpeg')
        r = self.client.post('/api/posts/', {'title': 'X', 'category': 'memy', 'body': 'y', 'files': [f]}, format='multipart')
        self.assertEqual(r.status_code, 201, r.data)
        stored = Post.objects.get().attachments.get().file
        with stored.open('rb') as fh:
            self.assertEqual(dict(Image.open(fh).getexif()), {})

    def test_author_edits_rejected_post_back_into_queue(self):
        self.login(self.user)
        p = Post.objects.create(title='X', category=self.cat, body='y', status='rejected', submitted_by=self.user)
        r = self.client.patch(f'/api/posts/{p.slug}/', {'body': 'poprawione'})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['status'], 'pending')
        self.login(self.other)
        self.assertEqual(self.client.patch(f'/api/posts/{p.slug}/', {'body': 'hack'}).status_code, 404)


class BrowseTests(Base):
    def test_filters_and_sort(self):
        a = self.make_published('Alfa', year=2001)
        b = self.make_published('Beta', year=2015)
        b.people.add(self.person)
        Post.objects.create(title='Ukryty', category=self.cat, body='x', status='hidden', year=2015)
        self.assertEqual(self.client.get('/api/posts/?year_from=2010').data['count'], 1)
        self.assertEqual(self.client.get('/api/posts/?person=kwant').data['results'][0]['slug'], b.slug)
        self.assertEqual(self.client.get('/api/posts/?q=alf').data['results'][0]['slug'], a.slug)
        self.assertEqual([p['slug'] for p in self.client.get('/api/posts/?sort=old').data['results']], [a.slug, b.slug])
        tl = self.client.get('/api/posts/timeline/').data
        self.assertEqual(tl['years'], [{'year': 2001, 'count': 1}, {'year': 2015, 'count': 1}])
        self.assertEqual(self.client.get('/api/posts/stats/').data['posts'], 2)
        self.assertIn(self.client.get('/api/posts/random/').data['slug'], {a.slug, b.slug})
        self.assertEqual(self.client.get('/api/categories/').data[0]['post_count'], 2)

    def test_retrieve_counts_views(self):
        p = self.make_published()
        self.client.get(f'/api/posts/{p.slug}/')
        self.client.get(f'/api/posts/{p.slug}/')
        p.refresh_from_db()
        self.assertEqual(p.views, 2)


class TimeMachineTests(Base):
    def test_before_filter_shows_the_archive_as_of_a_day(self):
        from datetime import datetime, timezone as tz
        old = self.make_published('Stary')
        Post.objects.filter(pk=old.pk).update(published_at=datetime(2026, 9, 1, 12, tzinfo=tz.utc))
        new = self.make_published('Nowy')
        Post.objects.filter(pk=new.pk).update(published_at=datetime(2026, 9, 20, 12, tzinfo=tz.utc))
        r = self.client.get('/api/posts/?before=2026-09-05')
        self.assertEqual([p['slug'] for p in r.data['results']], [old.slug])
        self.assertEqual(self.client.get('/api/posts/?before=2026-09-01').data['count'], 1)
        self.assertEqual(self.client.get('/api/posts/?before=2026-08-31').data['count'], 0)
        self.assertEqual(self.client.get('/api/posts/?before=garbage').data['count'], 2)

    def test_wayback_endpoint_validates_and_builds_embed_url(self):
        from unittest import mock
        self.assertEqual(self.client.get('/api/wayback/?date=2005').status_code, 400)
        with mock.patch('archive.wayback.urllib.request.urlopen', side_effect=OSError('offline')):
            r = self.client.get('/api/wayback/?date=2005-03-01')
        self.assertEqual(r.status_code, 200)
        self.assertIn('/web/20050301000000if_/http://www.fuw.edu.pl/', r.data['embed_url'])
        self.assertIsNone(r.data['timestamp'])
        self.assertEqual(r.data['earliest'], '1998-01-20')


class CommunityTests(Base):
    def test_reactions(self):
        p = self.make_published()
        self.login(self.user)
        r = self.client.post(f'/api/posts/{p.slug}/react/', {'kind': 'lol'})
        self.assertEqual(r.data['reaction_counts']['lol'], 1)
        r = self.client.post(f'/api/posts/{p.slug}/react/', {'kind': 'classic'})
        self.assertEqual((r.data['reaction_counts']['lol'], r.data['reaction_counts']['classic']), (0, 1))
        self.assertEqual(r.data['my_reaction'], 'classic')
        r = self.client.delete(f'/api/posts/{p.slug}/react/')
        self.assertIsNone(r.data['my_reaction'])
        self.assertEqual(self.client.post(f'/api/posts/{p.slug}/react/', {'kind': 'meh'}).status_code, 400)

    def test_comments_with_latex_and_image_and_threading(self):
        p = self.make_published()
        self.login(self.user)
        f = SimpleUploadedFile('szkic.png', png_bytes(), content_type='image/png')
        r = self.client.post(f'/api/posts/{p.slug}/comments/', {'body': 'Szkic: ![](szkic.png)', 'files': [f]}, format='multipart')
        self.assertEqual(r.status_code, 201, r.data)
        root = r.data['id']
        self.assertEqual(r.data['attachments'][0]['original_name'], 'szkic.png')
        r = self.client.post(f'/api/posts/{p.slug}/comments/', {'body': r'$\pi^4/15$', 'format': 'latex', 'parent': root})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['parent'], root)
        # a non-image on a comment is refused; a parent from another post is refused
        pdf = SimpleUploadedFile('x.pdf', b'%PDF-1.4 x')
        r = self.client.post(f'/api/posts/{p.slug}/comments/', {'body': 'x', 'files': [pdf]}, format='multipart')
        self.assertEqual(r.status_code, 400)
        q = self.make_published('Inny')
        r = self.client.post(f'/api/posts/{q.slug}/comments/', {'body': 'x', 'parent': root})
        self.assertEqual(r.status_code, 400)
        # tombstone
        self.login(self.other)
        self.assertEqual(self.client.delete(f'/api/comments/{root}/').status_code, 403)
        self.login(self.user)
        self.assertEqual(self.client.delete(f'/api/comments/{root}/').status_code, 204)
        listing = self.client.get(f'/api/posts/{p.slug}/comments/').data
        self.assertEqual(listing[0]['body'], '')
        self.assertEqual(listing[0]['attachments'], [])
        self.assertEqual(len(listing), 2)

    def test_anonymous_report_and_moderation_queue(self):
        p = self.make_published()
        r = self.client.post('/api/reports/', {'post': p.slug, 'reason': 'privacy', 'note': 'to ja', 'contact_email': 'ja@x.pl'})
        self.assertEqual(r.status_code, 201, r.data)
        self.login(self.user)
        self.assertEqual(self.client.get('/api/posts/queue/').status_code, 403)
        self.login(self.staff)
        q = self.client.get('/api/posts/queue/').data
        self.assertEqual(q['count'], 1)
        self.assertEqual(q['results'][0]['reports'][0]['reason'], 'privacy')
        r = self.client.post(f'/api/posts/{p.slug}/moderate/', {'decision': 'hide', 'note': 'na prośbę'})
        self.assertEqual(r.data['status'], 'hidden')
        self.assertTrue(Report.objects.get().resolved)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f'/api/posts/{p.slug}/').status_code, 404)
