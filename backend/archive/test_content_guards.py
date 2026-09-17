"""What the Gemini research changed in the code (docs/gemini/, see docs/gemini/note.md):
search that understands Polish prose and LaTeX at once, a refusal of TeX macro bombs on
every write path, the uploader's rights declaration, and the DSA-shaped report notice."""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from board.models import Message
from .latexguard import check_source
from .models import Category, Post, Report
from .search import canonicalize_math, index_fields, normalize_text, query_parts


class SearchNormalisationTests(APITestCase):
    def setUp(self):
        self.cat = Category.objects.create(slug='memy', name='Memy')
        self.p = Post.objects.create(title='Całkowanie przez części', category=self.cat, status='published',
                                     body='Policz $\\dfrac{1}{1 + x^2}$ i $\\int\\limits_0^\\infty e^{-x}\\,dx$.')

    def test_canonical_form(self):
        self.assertEqual(canonicalize_math('\\dfrac{1}{1 + x^2}'), '\\frac{1}{1+x^{2}}')
        self.assertEqual(canonicalize_math('a  \\le   b'), 'a\\leq b')
        self.assertEqual(canonicalize_math('\\alpha x'), '\\alpha x')  # not \\alphax
        self.assertEqual(normalize_text('Całkowanie, PRZEZ części!'), 'calkowanie przez czesci')

    def test_the_columns_are_filled_on_save(self):
        self.p.refresh_from_db()
        self.assertIn('calkowanie przez czesci', self.p.search_text)
        self.assertIn('\\frac{1}{1+x^{2}}', self.p.search_math)
        self.assertNotIn('\\frac', self.p.search_text)  # formulas do not pollute the prose column

    def test_a_query_matches_across_spelling_and_brace_variants(self):
        for q in ('calkowanie', 'CAŁKOWANIE', 'x^{2}', '$x^2$', '\\frac{1}{1+x^2}', '1+x^{2}', '\\int_0^\\infty'):
            r = self.client.get('/api/posts/', {'q': q})
            self.assertEqual([x['id'] for x in r.data['results']], [self.p.pk], q)
        r = self.client.get('/api/posts/', {'q': 'y^{3}'})
        self.assertEqual(r.data['results'], [])

    def test_query_parts(self):
        self.assertEqual(query_parts('całka $x^2$'), ('calka', 'x^{2}'))
        self.assertEqual(query_parts('winda')[1], '')

    def test_latex_prose_drops_commands(self):
        text, math = index_fields('T', '', '\\section{Zadanie} Oblicz \\[\\frac12\\]', 'latex')
        self.assertEqual(text, 't zadanie oblicz')
        self.assertEqual(math, '\\frac12')


class MacroBombTests(APITestCase):
    def setUp(self):
        self.cat = Category.objects.create(slug='memy', name='Memy')
        self.user = User.objects.create_user('ola', 'o@x.pl', 'haslo12345')
        self.client.force_authenticate(self.user)
        self.post = Post.objects.create(title='W', category=self.cat, status='published', body='x')

    def test_the_guard_itself(self):
        self.assertIsNone(check_source('Zwykły tekst z $x^2$ i \\newcommand{\\R}{\\mathbb{R}} $\\R$.'))
        self.assertIn('def', check_source('\\def\\x{\\x\\x}\\x'))
        self.assertIn('samego siebie', check_source('\\newcommand{\\x}{\\x\\x} \\x'))
        self.assertIn('samego siebie', check_source('\\newenvironment{loopy}{\\begin{loopy}}{}'))
        self.assertIn('limit', check_source('a' * 61_000))
        self.assertIn('limit', check_source('\\begin{itemize}' * 401))

    def test_a_post_with_a_macro_bomb_is_refused(self):
        r = self.client.post('/api/posts/', {'title': 'B', 'category': 'memy', 'format': 'latex',
                                             'body': '\\def\\x{\\x\\x}\\x', 'rights_confirmed': 'true'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('def', str(r.data['body']))

    def test_a_comment_and_a_chat_message_too(self):
        r = self.client.post(f'/api/posts/{self.post.slug}/comments/', {'body': '\\newcommand{\\y}{\\y}\\y'})
        self.assertEqual(r.status_code, 400)
        r = self.client.post('/api/board/', {'body': '$\\def\\x{\\x\\x}\\x$', 'website': ''})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Message.objects.count(), 0)

    def test_an_honest_newcommand_passes(self):
        r = self.client.post('/api/posts/', {'title': 'OK', 'category': 'memy', 'format': 'latex',
                                             'body': '\\newcommand{\\R}{\\mathbb{R}}\\begin{document}$\\R$\\end{document}',
                                             'rights_confirmed': 'true'})
        self.assertEqual(r.status_code, 201, r.data)


class RightsDeclarationTests(APITestCase):
    def setUp(self):
        self.cat = Category.objects.create(slug='memy', name='Memy')
        self.user = User.objects.create_user('ola', 'o@x.pl', 'haslo12345')
        self.client.force_authenticate(self.user)

    def test_a_new_post_needs_the_declaration(self):
        r = self.client.post('/api/posts/', {'title': 'B', 'category': 'memy', 'body': 'x'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('rights_confirmed', r.data)
        r = self.client.post('/api/posts/', {'title': 'B', 'category': 'memy', 'body': 'x', 'rights_confirmed': 'true'})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(Post.objects.get().rights_confirmed)

    def test_an_edit_does_not_ask_again(self):
        self.client.post('/api/posts/', {'title': 'B', 'category': 'memy', 'body': 'x', 'rights_confirmed': 'true'})
        p = Post.objects.get()
        r = self.client.patch(f'/api/posts/{p.slug}/', {'title': 'B2', 'body': 'x'})  # an edit sends the body, as the form does
        self.assertEqual(r.status_code, 200, r.data)


class DsaNoticeTests(APITestCase):
    def setUp(self):
        self.cat = Category.objects.create(slug='memy', name='Memy')
        self.staff = User.objects.create_user('mod', 'm@x.pl', 'haslo12345', is_staff=True)
        self.author = User.objects.create_user('ola', 'o@x.pl', 'haslo12345')
        self.post = Post.objects.create(title='W', category=self.cat, status='published', body='x', submitted_by=self.author)

    def test_good_faith_is_stored_and_a_formal_notice_is_marked_for_staff(self):
        r = self.client.post('/api/reports/', {'post': self.post.slug, 'reason': 'privacy', 'note': 'to ja',
                                               'contact_email': 'ja@x.pl', 'good_faith': True})
        self.assertEqual(r.status_code, 201, r.data)
        self.client.post('/api/reports/', {'post': self.post.slug, 'reason': 'other'})  # anonymous, no statement
        self.assertEqual(Report.objects.filter(good_faith=True).count(), 1)
        self.client.force_authenticate(self.staff)
        rows = self.client.get('/api/posts/queue/').data['results'][0]['reports']
        self.assertEqual(sorted(x['formal'] for x in rows), [False, True])

    def test_the_author_gets_the_review_note_in_mine(self):
        self.post.status, self.post.review_note = 'rejected', 'brak zgody osoby na zdjęciu'
        self.post.save()
        self.client.force_authenticate(self.author)
        row = self.client.get('/api/posts/mine/').data['results'][0]
        self.assertEqual(row['review_note'], 'brak zgody osoby na zdjęciu')
