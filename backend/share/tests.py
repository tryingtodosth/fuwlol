"""What a scraper is told, and — more to the point — what it is not.

The tests that matter most here are the negative ones. A link preview is fetched by a
robot and cached on somebody else's servers for days, so a leak through this surface
outlives the takedown that was supposed to stop it: the assertion that a hidden, pending,
nuked, quarantined and escalated post all produce the SAME BYTES as a slug that never
existed is the whole security argument of the app, written down.
"""
import tempfile
from html.parser import HTMLParser

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from archive.models import Attachment, Category, Person, Post, Subject, Tag
from escalation.models import Escalation

from .previews import clean_text, preview_for

SITE = 'https://fuw.lol'
FB = 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)'
BROWSER = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
           'Chrome/140.0 Safari/537.36')


class Head(HTMLParser):
    """The tags a scraper would read, from the bytes we actually sent.

    A parser rather than a regex over the response body on purpose: it proves the document
    parses at all, which is the first thing an escaping bug breaks."""

    def __init__(self, html):
        super().__init__()
        self.meta, self.links, self.title, self.h1 = {}, {}, '', ''
        self._in = ''
        self.article_tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'meta':
            key = a.get('property') or a.get('name') or ''
            if key == 'article:tag':
                self.article_tags.append(a.get('content', ''))
            else:
                self.meta[key] = a.get('content', '')
        elif tag == 'link' and a.get('rel'):
            self.links[a['rel']] = a.get('href', '')
        elif tag in ('title', 'h1'):
            self._in = tag

    def handle_endtag(self, tag):
        self._in = ''

    def handle_data(self, data):
        if self._in == 'title':
            self.title += data
        elif self._in == 'h1':
            self.h1 += data


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), FUWLOL_SITE_URL=SITE,
                   FUWLOL_SHARE_REDIRECT_HUMANS='1')
class SharePreviewTests(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(slug='memy', name='Memy', description='Obrazki z zajęć.')
        self.author = User.objects.create_user('ola', 'o@x.pl', 'haslo12345')
        self.post = Post.objects.create(
            title='List otwarty do Magnificencji Dziekana', category=self.cat, status='published',
            body='Treść', summary='Studenci proszą o $\\Delta t > 0$ między kolokwiami.',
            published_at=timezone.now(), submitted_by=self.author)
        self.tag = Tag.objects.create(slug='kolokwium', name='kolokwium')
        self.post.tags.add(self.tag)
        self.person = Person.objects.create(slug='helena-hamiltonian', name='Helena Hamiltonian',
                                            degree='prof. dr hab.', role='wykładowczyni',
                                            unit='Instytut Fizyki Teoretycznej', sex='f')
        self.post.people.add(self.person)
        # update_or_create: migration 0008 seeds the Faculty's own programme, and
        # „Mechanika klasyczna" is on it — a plain create hits the unique slug.
        self.subject, _ = Subject.objects.update_or_create(
            slug='mechanika-klasyczna', defaults={'name': 'Mechanika klasyczna', 'short': 'MK'})
        self.post.subjects.add(self.subject)

    # --- helpers -------------------------------------------------------------------------

    def fetch(self, path, ua=FB, **params):
        return self.client.get(f'/share{path}', params, HTTP_USER_AGENT=ua)

    def head(self, path, **params):
        response = self.fetch(path, **params)
        return response, Head(response.content.decode())

    def attach(self, kind='image', **kwargs):
        return Attachment.objects.create(post=self.post, original_name='zdjecie.png',
                                         kind=kind, **kwargs)

    # --- a post --------------------------------------------------------------------------

    def test_post_card_carries_every_tag_a_scraper_reads(self):
        response, head = self.head('/wpis/' + self.post.slug)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'public, max-age=300')
        # CorsMiddleware appends 'origin' to the same header; ours has to be in there too
        self.assertIn('User-Agent', response['Vary'])
        self.assertEqual(head.title, 'List otwarty do Magnificencji Dziekana — fuw.lol')
        self.assertEqual(head.meta['og:title'], head.title)
        self.assertEqual(head.meta['og:type'], 'article')
        self.assertEqual(head.meta['og:site_name'], 'fuw.lol')
        self.assertEqual(head.meta['og:locale'], 'pl_PL')
        self.assertEqual(head.meta['og:url'], f'{SITE}/wpis/{self.post.slug}')
        self.assertEqual(head.links['canonical'], head.meta['og:url'])
        self.assertEqual(head.meta['twitter:card'], 'summary_large_image')
        self.assertEqual(head.article_tags, ['kolokwium'])
        self.assertTrue(head.meta['article:published_time'].startswith(str(timezone.now().year)))
        # no picture on this post: the generated card stands in rather than nothing
        self.assertEqual(head.meta['og:image'], f'{SITE}/og-default.png')
        self.assertTrue(head.meta['og:image:alt'])
        # the minimal page is readable without JavaScript
        self.assertEqual(head.h1, head.title)
        self.assertIn(head.meta['og:url'], response.content.decode())

    def test_maths_delimiters_come_off_and_the_formula_stays(self):
        _, head = self.head('/wpis/' + self.post.slug)
        self.assertEqual(head.meta['og:description'],
                         'Studenci proszą o \\Delta t > 0 między kolokwiami.')
        self.assertNotIn('$', head.meta['og:description'])

    def test_description_is_clipped_at_a_word(self):
        self.post.summary = 'Kolokwium ' * 40
        self.post.save()
        _, head = self.head('/wpis/' + self.post.slug)
        description = head.meta['og:description']
        self.assertLessEqual(len(description), 200)
        self.assertTrue(description.endswith('…'))
        self.assertNotIn('Kolokwiu…', description)  # cut between words, not inside one

    def test_a_title_cannot_break_out_of_the_tags(self):
        """The one test this file exists to have. A moderator approved the text; nobody
        parsed it."""
        self.post.title = '</title><script>alert("xss")</script>'
        self.post.summary = 'Cytat: "cała sala" & reszta <b>pogrubiona</b>'
        self.post.save()
        response, head = self.head('/wpis/' + self.post.slug)
        body = response.content.decode()
        self.assertNotIn('<script>', body)
        self.assertNotIn('</title><script>', body)
        self.assertIn('&lt;script&gt;', body)
        # and the parser still read them back as the original text, character for character
        self.assertEqual(head.title, '</title><script>alert("xss")</script> — fuw.lol')
        self.assertEqual(head.meta['og:description'],
                         'Cytat: "cała sala" & reszta <b>pogrubiona</b>')

    def test_post_without_a_summary_falls_back_to_category_and_year(self):
        self.post.summary = ''
        self.post.year, self.post.year_precision = 2011, 'approx'
        self.post.save()
        _, head = self.head('/wpis/' + self.post.slug)
        self.assertIn('Memy', head.meta['og:description'])
        self.assertIn('ok. 2011', head.meta['og:description'])

    # --- images --------------------------------------------------------------------------

    def test_local_attachment_is_made_absolute(self):
        self.attach(file=SimpleUploadedFile('zdjecie.png', b'\x89PNG fake'))
        _, head = self.head('/wpis/' + self.post.slug)
        self.assertTrue(head.meta['og:image'].startswith(f'{SITE}/media/attachments/'))

    @override_settings(R2_PUBLIC_BASE_URL='https://pliki.fuw.lol')
    def test_r2_attachment_keeps_its_own_hostname(self):
        self.attach(storage_key='public/abc123.png')
        _, head = self.head('/wpis/' + self.post.slug)
        self.assertEqual(head.meta['og:image'], 'https://pliki.fuw.lol/public/abc123.png')

    @override_settings(R2_PUBLIC_BASE_URL='https://pliki.fuw.lol')
    def test_quarantined_object_falls_back_to_the_default_card(self):
        """`public_url` is '' for a held key. A preview that passed that '' through would
        publish a broken image; one that kept the URL would publish the picture that was
        just taken down."""
        self.attach(storage_key='held/abc123.png')
        _, head = self.head('/wpis/' + self.post.slug)
        self.assertEqual(head.meta['og:image'], f'{SITE}/og-default.png')

    def test_non_image_attachment_is_not_the_cover(self):
        self.attach(file=SimpleUploadedFile('skan.pdf', b'%PDF-1.4'), kind='pdf')
        _, head = self.head('/wpis/' + self.post.slug)
        self.assertEqual(head.meta['og:image'], f'{SITE}/og-default.png')

    # --- what a stranger may not see -------------------------------------------------------

    def _generic_404(self, path):
        response = self.fetch(path)
        self.assertEqual(response.status_code, 404, path)
        return response.content

    def test_every_invisible_post_looks_exactly_like_a_slug_that_never_existed(self):
        nothing = self._generic_404('/wpis/nie-ma-takiego-wpisu')
        for status in ('pending', 'hidden', 'rejected', 'nuked', 'quarantined', 'purged'):
            Post.all_objects.filter(pk=self.post.pk).update(status=status)
            self.assertEqual(self._generic_404('/wpis/' + self.post.slug), nothing,
                             f'status={status} leaked something')

    def test_an_escalated_post_looks_the_same_although_it_is_published(self):
        nothing = self._generic_404('/wpis/nie-ma-takiego-wpisu')
        Escalation.objects.create(content_type=ContentType.objects.get_for_model(Post),
                                  object_id=self.post.pk, requested_by=self.author,
                                  reason='zgłoszenie')
        self.assertEqual(self.post.status, 'published')
        self.assertEqual(self._generic_404('/wpis/' + self.post.slug), nothing)

    def test_the_generic_card_says_nothing_about_the_archive_it_refused(self):
        response = self.fetch('/wpis/' + 'nie-ma-takiego')
        head = Head(response.content.decode())
        self.assertEqual(head.meta['og:title'], 'fuw.lol — archiwum Wydziału Fizyki UW')
        self.assertEqual(head.meta['robots'], 'noindex, follow')
        self.assertNotIn('canonical', head.links)

    def test_a_restricted_post_looks_the_same_as_a_slug_that_never_existed(self):
        """The site shows a stranger the title and a lock; a scraper gets neither.

        A preview carries the summary (a body excerpt) and the cover into somebody else's
        cache and Google's index, where they outlive any later decision — so the teaser
        stops at the edge of the site (`previews._post`, house rule 5)."""
        nothing = self._generic_404('/wpis/nie-ma-takiego-wpisu')
        Post.objects.filter(pk=self.post.pk).update(trusted_only=True)
        self.assertEqual(self._generic_404('/wpis/' + self.post.slug), nothing)

    def test_a_restricted_post_is_gone_from_every_count(self):
        second = Post.objects.create(title='Drugi', category=self.cat, status='published',
                                     trusted_only=True)
        second.tags.add(self.tag)
        _, head = self.head('/przegladaj', category='memy')
        self.assertIn('1 wpis ', head.meta['og:description'])

    def test_a_hidden_post_is_gone_from_every_count(self):
        second = Post.objects.create(title='Drugi', category=self.cat, status='hidden')
        second.tags.add(self.tag)
        _, head = self.head('/przegladaj', category='memy')
        self.assertIn('1 wpis ', head.meta['og:description'])

    # --- people ----------------------------------------------------------------------------

    def test_person_card_uses_the_silhouette_for_the_right_sex(self):
        response, head = self.head('/ludzie/helena-hamiltonian')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(head.title, 'prof. dr hab. Helena Hamiltonian — fuw.lol')
        self.assertEqual(head.meta['og:type'], 'profile')
        self.assertEqual(head.meta['og:image'], f'{SITE}/og-osoba-f.png')
        self.assertIn('sylwetka zastępcza', head.meta['og:image:alt'])
        self.assertEqual(head.meta['og:description'],
                         'wykładowczyni · Instytut Fizyki Teoretycznej · 1 wpis w archiwum')

    def test_person_plural_follows_polish_rather_than_english(self):
        for n, expected in ((2, '2 wpisy'), (5, '5 wpisów'), (12, '12 wpisów'), (22, '22 wpisy')):
            Post.objects.filter(title__startswith='Dodatkowy').delete()
            for i in range(n - 1):
                extra = Post.objects.create(title=f'Dodatkowy {i}', category=self.cat, status='published')
                extra.people.add(self.person)
            _, head = self.head('/ludzie/helena-hamiltonian')
            self.assertIn(expected, head.meta['og:description'])

    def test_a_man_gets_the_other_silhouette_and_an_unknown_sex_the_neutral_one(self):
        Person.objects.create(slug='kwant-niepewny', name='Kwant Niepewny', sex='m')
        Person.objects.create(slug='pani-z-portierni', name='Pani z portierni', sex='')
        _, head = self.head('/ludzie/kwant-niepewny')
        self.assertEqual(head.meta['og:image'], f'{SITE}/og-osoba-m.png')
        _, head = self.head('/ludzie/pani-z-portierni')
        self.assertEqual(head.meta['og:image'], f'{SITE}/og-osoba.png')
        self.assertIn('sylwetka zastępcza', head.meta['og:image:alt'])

    def test_an_unlisted_person_has_no_preview(self):
        self.person.is_listed = False
        self.person.save()
        self._generic_404('/ludzie/helena-hamiltonian')

    def test_a_person_named_only_on_a_post_still_in_the_queue_has_no_preview(self):
        """`visible_people(None)` is the rule, not `is_listed`: until the post that named
        somebody is published, there is no public page about that human being."""
        proposed = Person.objects.create(slug='nowa-osoba', name='Nowa Osoba', created_by=self.author)
        pending = Post.objects.create(title='Czeka', category=self.cat, status='pending')
        pending.people.add(proposed)
        self._generic_404('/ludzie/nowa-osoba')
        pending.status = 'published'
        pending.save()
        self.assertEqual(self.fetch('/ludzie/nowa-osoba').status_code, 200)

    def test_a_portrait_replaces_the_silhouette_when_consent_was_given(self):
        from portraits.models import Portrait
        self.person.image_consent = 'granted'
        self.person.save()
        Portrait.objects.create(person=self.person, uploaded_by=self.author, status='published',
                                file=SimpleUploadedFile('twarz.png', b'\x89PNG fake'),
                                original_name='twarz.png', rights_confirmed=True)
        _, head = self.head('/ludzie/helena-hamiltonian')
        self.assertIn('/media/attachments/', head.meta['og:image'])
        self.assertTrue(head.meta['og:image'].startswith(SITE))

    def test_withdrawn_consent_takes_the_portrait_out_of_the_preview_too(self):
        from portraits.models import Portrait
        self.person.image_consent = 'granted'
        self.person.save()
        Portrait.objects.create(person=self.person, uploaded_by=self.author, status='published',
                                file=SimpleUploadedFile('twarz.png', b'\x89PNG fake'),
                                original_name='twarz.png', rights_confirmed=True)
        self.person.image_consent = 'refused'
        self.person.save()
        _, head = self.head('/ludzie/helena-hamiltonian')
        self.assertEqual(head.meta['og:image'], f'{SITE}/og-osoba-f.png')

    # --- the filtered browse pages ------------------------------------------------------------

    def test_category_tag_subject_and_person_filters(self):
        _, head = self.head('/przegladaj', category='memy')
        self.assertEqual(head.meta['og:url'], f'{SITE}/przegladaj?category=memy')
        self.assertIn('Obrazki z zajęć.', head.meta['og:description'])
        self.assertIn('1 wpis', head.meta['og:description'])

        _, head = self.head('/przegladaj', tag='kolokwium')
        self.assertEqual(head.title, '#kolokwium — fuw.lol')
        self.assertEqual(head.meta['og:url'], f'{SITE}/przegladaj?tag=kolokwium')

        _, head = self.head('/przegladaj', person='helena-hamiltonian')
        self.assertEqual(head.title, 'prof. dr hab. Helena Hamiltonian — fuw.lol')
        self.assertEqual(head.meta['og:url'], f'{SITE}/przegladaj?person=helena-hamiltonian')

        _, head = self.head('/przegladaj', subject='mechanika-klasyczna')
        self.assertEqual(head.title, 'Mechanika klasyczna (MK) — fuw.lol')
        self.assertEqual(head.meta['og:url'], f'{SITE}/przegladaj?subject=mechanika-klasyczna')

    def test_a_subject_somebody_named_but_never_wrote_about_is_not_counted(self):
        """/przedmioty lists the Faculty's programme plus named subjects that have a
        published post. The card's number has to be that list's length, not the table's."""
        before = self.head('/przedmioty')[1].meta['og:description']
        Subject.objects.create(slug='zgadywanka', name='Zgadywanka', created_by=self.author)
        after = self.head('/przedmioty')[1].meta['og:description']
        self.assertEqual(before, after)
        self.assertNotIn('zgadywanka', self.client.get('/share/sitemap.xml').content.decode())

    def test_a_subject_has_its_own_page_too(self):
        _, head = self.head('/przedmioty/mechanika-klasyczna')
        self.assertEqual(head.meta['og:url'], f'{SITE}/przedmioty/mechanika-klasyczna')

    def test_an_unknown_filter_is_a_404_not_an_empty_card(self):
        for key in ('category', 'tag', 'person', 'subject'):
            response = self.fetch('/przegladaj', **{key: 'nie-ma-takiego'})
            self.assertEqual(response.status_code, 404, key)

    def test_nothing_from_the_query_string_is_echoed(self):
        """A preview renders on somebody else's screen under our domain. If `?q=` were
        reflected, anybody could compose a fuw.lol link whose card says anything at all."""
        response = self.fetch('/przegladaj', q='<b>Wydział wypłaca 5000 zł</b>')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('5000', response.content.decode())

    def test_a_tag_with_nothing_published_is_not_a_page(self):
        Tag.objects.create(slug='sierota', name='sierota')
        self._generic_404('/przegladaj?tag=sierota')

    # --- the standing pages ---------------------------------------------------------------------

    def test_standing_pages_and_the_home_page(self):
        response, head = self.head('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('1 wpis', head.meta['og:description'])
        self.assertEqual(head.links['canonical'], f'{SITE}/')

        for path, expected in (('/ludzie', 'Osoby — fuw.lol'),
                               ('/przedmioty', 'Przedmioty — fuw.lol'),
                               ('/przegladaj', 'Przeglądaj archiwum — fuw.lol'),
                               ('/os-czasu', 'Oś czasu — fuw.lol'),
                               ('/czat', 'Czat — fuw.lol'),
                               ('/o-archiwum', 'O archiwum — fuw.lol'),
                               ('/ludzie/zgoda', 'Zgoda na wizerunek — fuw.lol'),
                               ('/losowe', 'Losowy wpis — fuw.lol')):
            response, head = self.head(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertEqual(head.title, expected)
            self.assertEqual(head.meta['og:image'], f'{SITE}/og-default.png')

    def test_a_trailing_slash_is_the_same_page(self):
        _, head = self.head('/wpis/' + self.post.slug + '/')
        self.assertEqual(head.meta['og:url'], f'{SITE}/wpis/{self.post.slug}')

    def test_application_pages_are_not_for_indexing(self):
        for path in ('/logowanie', '/dodaj', '/moderacja', '/losowe'):
            response, head = self.head(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertEqual(head.meta['robots'], 'noindex, follow', path)

    def test_a_path_this_site_does_not_serve_is_a_404(self):
        self._generic_404('/jakas-strona')
        self._generic_404('/wpis/za/gleboko')

    # --- who gets the page at all -------------------------------------------------------------

    def test_a_person_who_lands_here_is_sent_to_the_real_page(self):
        response = self.client.get(f'/share/wpis/{self.post.slug}', HTTP_USER_AGENT=BROWSER)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], f'{SITE}/wpis/{self.post.slug}')

    def test_the_redirect_keeps_the_filter_that_was_shared(self):
        response = self.client.get('/share/przegladaj', {'category': 'memy'}, HTTP_USER_AGENT=BROWSER)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], f'{SITE}/przegladaj?category=memy')

    def test_every_listed_crawler_gets_the_tags(self):
        for ua in ('facebookexternalhit/1.1', 'Twitterbot/1.0', 'WhatsApp/2.23', 'TelegramBot',
                   'Slackbot-LinkExpanding 1.0', 'Discordbot/2.0', 'Mozilla/5.0 (compatible; Googlebot/2.1)',
                   'SkypeUriPreview Preview/0.5', 'Signal Desktop 7.0', 'LinkedInBot/1.0'):
            response = self.client.get(f'/share/wpis/{self.post.slug}', HTTP_USER_AGENT=ua)
            self.assertEqual(response.status_code, 200, ua)

    @override_settings(FUWLOL_SHARE_REDIRECT_HUMANS='0')
    def test_mode_a_serves_everybody_the_same_document(self):
        response = self.client.get(f'/share/wpis/{self.post.slug}', HTTP_USER_AGENT=BROWSER)
        self.assertEqual(response.status_code, 200)

    def test_head_is_answered_like_get(self):
        response = self.client.head(f'/share/wpis/{self.post.slug}', HTTP_USER_AGENT=FB)
        self.assertEqual(response.status_code, 200)

    # --- the two delivery modes -----------------------------------------------------------------

    def test_the_tags_are_spliced_into_the_real_spa_shell_when_one_is_configured(self):
        """Mode (a): Django serves the built index.html with our tags in its head. fuw.lol
        does not run this way (the build lives in the other container), which is exactly
        why it is tested — the switch must not be discovered broken on the day it is made."""
        with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, encoding='utf-8') as fh:
            # As app.html really is: a title AND the generic fallback card underneath it.
            fh.write('<!doctype html><html lang="pl"><head><meta charset="utf-8">'
                     '<title>fuw.lol</title>'
                     '<meta name="description" content="Ogolny opis calego serwisu.">'
                     '<meta property="og:title" content="fuw.lol">'
                     '<meta property="og:image" content="https://fuw.lol/og-default.png">'
                     '<meta name="twitter:card" content="summary_large_image">'
                     '<link rel="icon" href="/favicon.svg">'
                     '<link rel="stylesheet" href="/_app/x.css"></head>'
                     '<body><div id="app"></div></body></html>')
            index = fh.name
        with override_settings(FUWLOL_SPA_INDEX=index):
            response, head = self.head('/wpis/' + self.post.slug)
        body = response.content.decode()
        self.assertEqual(body.count('<title>'), 1)
        self.assertEqual(head.title, 'List otwarty do Magnificencji Dziekana — fuw.lol')
        # The generic card must not survive next to the real one: a scraper reads the
        # FIRST og:title it finds, so a leftover would beat everything this app does.
        self.assertEqual(body.count('property="og:title"'), 1)
        self.assertEqual(head.meta['og:title'], head.title)
        self.assertEqual(body.count('name="description"'), 1)
        self.assertEqual(body.count('name="twitter:card"'), 1)
        self.assertNotIn('Ogolny opis', body)
        self.assertIn('<div id="app"></div>', body)          # the application is still there
        self.assertEqual(head.links['icon'], '/favicon.svg')  # and so is everything it had
        self.assertIn('/_app/x.css', body)                    # including its stylesheet
        self.assertIn('<meta charset="utf-8">', body)

    @override_settings(FUWLOL_SPA_INDEX='/nie/ma/takiego/pliku.html')
    def test_a_missing_spa_shell_falls_back_to_the_minimal_page(self):
        response, head = self.head('/wpis/' + self.post.slug)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(head.meta['og:title'], head.title)

    # --- the sitemap ----------------------------------------------------------------------------

    def test_sitemap_lists_what_is_public_and_nothing_else(self):
        from xml.etree import ElementTree
        hidden = Post.objects.create(title='Ukryty', category=self.cat, status='hidden')
        response = self.client.get('/share/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        tree = ElementTree.fromstring(body)  # it has to parse, or Google ignores the lot
        locations = [e.text for e in tree.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
        self.assertIn(f'{SITE}/wpis/{self.post.slug}', locations)
        self.assertNotIn(f'{SITE}/wpis/{hidden.slug}', locations)
        self.assertIn(f'{SITE}/ludzie/helena-hamiltonian', locations)
        self.assertIn(f'{SITE}/przedmioty/mechanika-klasyczna', locations)
        self.assertIn(f'{SITE}/przegladaj?category=memy', locations)
        self.assertIn(f'{SITE}/o-archiwum', locations)
        self.assertIn('<lastmod>', body)
        self.assertEqual(response['Cache-Control'], 'public, max-age=3600')

    def test_sitemap_does_not_invite_a_search_engine_to_a_restricted_post(self):
        Post.objects.filter(pk=self.post.pk).update(trusted_only=True)
        self.assertNotIn(self.post.slug, self.client.get('/share/sitemap.xml').content.decode())

    def test_sitemap_hides_an_escalated_post(self):
        Escalation.objects.create(content_type=ContentType.objects.get_for_model(Post),
                                  object_id=self.post.pk, requested_by=self.author, reason='x')
        self.assertNotIn(self.post.slug, self.client.get('/share/sitemap.xml').content.decode())


class RuleModuleTests(TestCase):
    """`preview_for` on its own — the shape of the answer, without an HTTP request around
    it, because that is how the next surface (an RSS card, an e-mail) would call it."""

    def test_clean_text_collapses_and_strips(self):
        self.assertEqual(clean_text('  a\n\n b \t c '), 'a b c')
        self.assertEqual(clean_text('wzór \\(a^2+b^2\\) i \\[c^2\\]'), 'wzór a^2+b^2 i c^2')
        self.assertEqual(clean_text('$$E=mc^2$$'), 'E=mc^2')
        self.assertEqual(clean_text('ab'), 'a b')

    def test_clean_text_never_exceeds_the_limit(self):
        self.assertLessEqual(len(clean_text('slowo ' * 100)), 200)

    def test_unknown_path_is_none_rather_than_an_empty_preview(self):
        self.assertIsNone(preview_for('/wpis/nic'))
        self.assertIsNone(preview_for('/zupelnie/inna/sciezka'))

    def test_doubled_slashes_cannot_smuggle_a_hostname_into_the_canonical_url(self):
        preview = preview_for('//evil.example.com')
        self.assertIsNone(preview)
        self.assertEqual(preview_for('//').url, preview_for('/').url)
