"""Demo content so the site is judgeable before anybody uploads anything.
Every person here is FICTIONAL on purpose — the archive must never ship invented
claims about real staff. Idempotent; --reset wipes and recreates the demo rows."""
import io
import random
import secrets

from django.conf import settings

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone
from PIL import Image, ImageDraw

from archive.models import Attachment, Category, Comment, Person, Post, Reaction, Subject, Tag

CATEGORIES = [
    ('memy', 'Memy', '🖼️', 'Obrazki, przeróbki, szablony z życia Wydziału.'),
    ('cytaty', 'Cytaty', '💬', 'Złote myśli z sal wykładowych i korytarzy Pasteura 5.'),
    ('legendarne-zadania', 'Legendarne zadania', '📝', 'Zadania z kolokwiów i egzaminów, które przeszły do historii.'),
    ('zdjecia', 'Zdjęcia', '📷', 'Fotografie z wydarzeń, wyjazdów, laboratoriów.'),
    ('historie', 'Historie i anegdoty', '📖', 'Opowieści, które każdy rocznik słyszał w innej wersji.'),
    ('dokumenty', 'Dokumenty i skany', '📄', 'Ogłoszenia, kartki z drzwi, ulotki, gazetki.'),
    ('folklor', 'Folklor', '🎵', 'Piosenki, tradycje, obrzędy przejścia, otrzęsiny.'),
    ('internet', 'Stare strony i fora', '🌐', 'Zrzuty z dawnych stron kół naukowych, forów i list dyskusyjnych.'),
]
# Shaped like a row of the faculty directory (title, name, unit) — /ludzie copies that page.
# `aliases` are nicknames: a post tagged with one is this person's post (archive/people.py).
PEOPLE = [
    dict(slug='kwant-niepewny', degree='dr', name='Kwant Niepewny', sex='m',
         role='postać fikcyjna — wykładowca mechaniki kwantowej',
         unit='Instytut Fizyki Teoretycznej, Zakład Zjawisk Nieoznaczonych (fikcyjny)',
         bio='Fikcyjny bohater wydziałowych anegdot. Wszelka zbieżność z prawdziwymi osobami jest przypadkowa.',
         aliases=['Kwant', 'Niepewny']),
    dict(slug='helena-hamiltonian', degree='prof. dr hab.', name='Helena Hamiltonian', sex='f',
         role='postać fikcyjna — mechanika klasyczna',
         unit='Instytut Fizyki Teoretycznej, Katedra Kolokwiów o 7:30 (fikcyjna)',
         bio='Fikcyjna profesor, słynna z kolokwiów o godzinie 7:30.',
         aliases=['Hamiltonianka']),
    dict(slug='pani-z-portierni', degree='', name='Pani z portierni', surname='Portierni', sex='f',
         role='postać fikcyjna — instytucja',
         unit='Portiernia główna, Pasteura 5 (etat od zawsze)',
         bio='Zbiorowa, fikcyjna postać wszystkich portierni Pasteura 5.',
         aliases=['Portiernia']),
]
TAGS = ['kolokwium', 'egzamin', 'Pasteura 5', 'mechanika', 'kwanty', 'laboratorium', 'sesja', 'otrzesiny', 'stolowka', 'analiza']
# Which course each demo post happened on. The rows themselves are seeded by migration 0008
# from the Faculty's own programme, so this only has to name their slugs — and a post with
# no course is normal (the winda and the hymn happened to everybody, on no subject at all).
POST_SUBJECTS = {
    'Energia jest zawsze zachowana. Wasza — niekoniecznie.': ['mechanika', 'mechanika-klasyczna'],
    'Ja po trzecim kolokwium z analizy': ['analiza-matematyczna-i'],
    'Kartka z drzwi laboratorium: „Nie dotykać. Serio.”': ['ii-pracownia-fizyczna'],
    'Zadanie 3 z kolokwium, którego nikt nie rozwiązał': ['mechanika-kwantowa-i'],
    'Egzamin, na którym odpowiedź brzmiała 42': ['analiza-matematyczna-ii'],
}

TEXT_POSTS = [
    ('cytaty', 'Energia jest zawsze zachowana. Wasza — niekoniecznie.', 2009, 'approx',
     'Zapisane na marginesie notatek, semestr zimowy.',
     "Wypowiedziane podobno na pierwszym wykładzie z mechaniki, tuż po ogłoszeniu terminów kolokwiów.\n\n"
     "> Energia jest zawsze zachowana. Wasza — niekoniecznie.\n\nWersja alternatywna, słyszana w 2013: „Pęd też.”",
     ['helena-hamiltonian'], ['kolokwium', 'mechanika']),
    ('historie', 'Winda, która jeździła tylko w górę', 2004, 'decade', 'Zdarzenie legendarne, data niepewna.',
     "Przez cały semestr winda w skrzydle B zatrzymywała się tylko na piętrach parzystych, ale wyłącznie jadąc w górę. "
     "W dół — na wszystkich. Nikt nie zgłosił usterki, bo *działało*.\n\n"
     "Według jednej wersji przyczyną był student, który podłączył przycisk pod licznik Geigera. Według drugiej — Pani z portierni.",
     ['pani-z-portierni'], ['Pasteura 5']),
    ('folklor', 'Hymn kolejki do dziekanatu', 1998, 'approx', 'Przekazywane ustnie.',
     "Śpiewane na melodię, której nikt nie pamięta:\n\n"
     "```\nStoję w kolejce, godzina trzecia,\nnumer pięćdziesiąt, przede mną trzecia,\n"
     "okienko drugie zamknięte na klucz,\nale dziekanat ma dobry gust.\n```",
     [], ['sesja']),
    ('internet', 'Strona koła naukowego z 2001 roku', 2001, 'exact', 'Zrzut z archiwum internetowego.',
     "Tło w gwiazdki, licznik odwiedzin (1337), przycisk „Best viewed in Netscape” i sekcja *Linki* z jednym linkiem — do siebie samej.",
     [], ['internet' if False else 'Pasteura 5']),
    ('dokumenty', 'Kartka z drzwi laboratorium: „Nie dotykać. Serio.”', 2016, 'exact', 'Zdjęcie kartki, laboratorium na parterze.',
     "Kartka wisiała trzy lata. Pod spodem ktoś dopisał: „a jak dotknę?”, a pod tym ktoś inny: „to się dowiesz”.",
     [], ['laboratorium']),
    ('memy', 'Ja po trzecim kolokwium z analizy', 2019, 'exact', 'Grupa rocznika 2018.',
     "Klasyk. Szablon z kotem, podpis wewnątrz obrazka.", [], ['analiza', 'kolokwium', 'Hamiltonianka']),
    ('zdjecia', 'Stołówka o 12:15, zdjęcie archiwalne', 2007, 'approx', 'Aparat cyfrowy, 3 Mpix.',
     "Kolejka sięgała klatki schodowej. Zupa: ogórkowa. Pogoda: nieistotna.", [], ['stolowka']),
]
LATEX_POSTS = [
    ('legendarne-zadania', 'Zadanie 3 z kolokwium, którego nikt nie rozwiązał', 2011, 'exact',
     'Kolokwium II z mechaniki kwantowej, grupa wtorkowa.',
     r"""\documentclass{article}
\usepackage{amsmath}
\begin{document}
\section*{Zadanie 3 (10 pkt)}
Cząstka o masie $m$ znajduje się w nieskończonej studni potencjału o szerokości $a$.
W chwili $t=0$ jej funkcja falowa ma postać
\[
\psi(x,0) = \frac{1}{\sqrt{2}}\left(\phi_1(x) + \phi_2(x)\right),
\]
gdzie $\phi_n$ są stanami własnymi hamiltonianu.

\begin{enumerate}
\item Wyznacz $\langle x\rangle(t)$.
\item Po jakim czasie cząstka \emph{zmieni zdanie}?
\item (Dodatkowe) Uzasadnij, dlaczego punkt 2 nie ma sensu, a mimo to został oceniony.
\end{enumerate}

\textbf{Uwaga.} Podpunkt 2 był podobno testem na czytanie ze zrozumieniem. Nikt go nie zdał.
\end{document}""", ['kwant-niepewny'], ['kolokwium', 'kwanty']),
    ('legendarne-zadania', 'Egzamin, na którym odpowiedź brzmiała 42', 2015, 'approx', 'Egzamin poprawkowy, sala 0.06.',
     r"""\documentclass{article}
\usepackage{amsmath}
\begin{document}
\section*{Zadanie 1}
Oblicz
\[
\int_0^{\infty} \frac{x^{3}}{e^{x}-1}\,\mathrm{d}x .
\]
\section*{Komentarz archiwisty}
Wynik to $\pi^4/15 \approx 6{,}49$, ale zgodnie z legendą trzy osoby napisały \textbf{42} i dostały pół punktu
,,za odwagę''. Legenda nie precyzuje, kto oceniał.
\end{document}""", ['helena-hamiltonian'], ['egzamin', 'analiza']),
]


def _png(text, color):
    img = Image.new('RGB', (640, 400), color)
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 619, 379], outline=(255, 255, 255), width=4)
    d.text((40, 180), text, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return ContentFile(buf.getvalue(), name='demo.png')


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true')

    def handle(self, *args, **opts):
        if opts['reset']:
            Post.objects.filter(submitted_by__username__in=['dziekan', 'claude-slop', 'student', 'doktorant']).delete()
        # Passwords: the documented `fuwlol123` ONLY on a debug (local) server. Anywhere
        # else each demo account gets a random password, printed once here and never
        # written down — and an account that already exists is never re-passworded, so a
        # re-seed cannot silently revert a password somebody changed. `dziekan` is a
        # superuser (= head-admin for escalations), which is exactly why a known password
        # on it in production would be the worst credential on the box.
        def account(username, **defaults):
            u, created = User.objects.get_or_create(username=username, defaults=defaults)
            if created:
                pw = 'fuwlol123' if settings.DEBUG else secrets.token_urlsafe(18)
                u.set_password(pw); u.save()
                if not settings.DEBUG:
                    self.stdout.write(f'konto demo {username}: hasło {pw} (zapisz je teraz — nie zostanie pokazane ponownie)')
            return u
        admin = account('dziekan', is_staff=True, is_superuser=True, email='dziekan@fuw.lol')
        # Every post below was written by a language model, so it is attributed to an
        # account that says so. Splitting it between `dziekan` and a `student` account was
        # a coin flip in this file, and it read — on an archive whose whole premise is
        # provenance — as if a dean had written the folklore.
        ai = account('claude-slop', email='', first_name='Claude', last_name='(AI)')
        # a TRUSTED demo account: verified fuw.edu.pl affiliation, no staff flag
        doktorant = account('doktorant', email='doktorant@fuw.lol')
        try:
            from accounts.models import Profile, TrustedDomain
            dom = TrustedDomain.objects.filter(domain='fuw.edu.pl').first()
            # edit THROUGH the user object: is_trusted() reads the cached `user.profile`
            Profile.objects.get_or_create(user=doktorant)
            prof = doktorant.profile
            prof.affiliation_email, prof.affiliation_domain, prof.verified_at = 'doktorant@fuw.edu.pl', dom, timezone.now()
            prof.save()
        except ImportError:  # seeding before the accounts app grew profiles
            pass
        for i, (slug, name, emoji, desc) in enumerate(CATEGORIES):
            Category.objects.update_or_create(slug=slug, defaults={'name': name, 'emoji': emoji, 'description': desc, 'order': i})
        from django.utils.text import slugify
        for spec in PEOPLE:
            spec = dict(spec)
            slug, aliases = spec.pop('slug'), spec.pop('aliases', [])
            person, _ = Person.objects.update_or_create(slug=slug, defaults=spec)
            for a in aliases:
                person.aliases.add(Tag.objects.get_or_create(slug=slugify(a), defaults={'name': a})[0])
        for t in TAGS:
            Tag.objects.get_or_create(slug=slugify(t), defaults={'name': t})
        if Post.objects.filter(submitted_by__in=[admin, ai]).exists():
            self.stdout.write('Demo posts already present (use --reset).')
            return
        rnd = random.Random(7)
        created = []
        for cat, title, year, prec, note, body, people, tags in TEXT_POSTS:
            p = Post.objects.create(title=title, category=Category.objects.get(slug=cat), format='text', body=body,
                                    summary=body.split('\n')[0][:200], year=year, year_precision=prec, date_note=note,
                                    submitted_by=ai, status='published',
                                    source_note='Zbiory własne archiwum (demo).')
            p.people.set(Person.objects.filter(slug__in=people))
            p.subjects.set(Subject.objects.filter(slug__in=POST_SUBJECTS.get(title, [])))
            p.tags.set(Tag.objects.filter(slug__in=[slugify(t) for t in tags]))
            created.append(p)
        for cat, title, year, prec, note, body, people, tags in LATEX_POSTS:
            p = Post.objects.create(title=title, category=Category.objects.get(slug=cat), format='latex', body=body,
                                    summary='Treść zadania w LaTeX-u — kliknij, żeby zobaczyć.', year=year,
                                    year_precision=prec, date_note=note, submitted_by=ai, status='published',
                                    source_note='Odpis z zeszytu (demo).')
            p.people.set(Person.objects.filter(slug__in=people))
            p.subjects.set(Subject.objects.filter(slug__in=POST_SUBJECTS.get(title, [])))
            p.tags.set(Tag.objects.filter(slug__in=[slugify(t) for t in tags]))
            created.append(p)
        # pictures on the meme, the photo and the door note
        for p, color in zip([x for x in created if x.category.slug in ('memy', 'zdjecia', 'dokumenty')],
                            [(23, 94, 76), (168, 66, 4), (78, 107, 140)]):
            Attachment.objects.create(post=p, file=_png(p.title, color), original_name='demo.png', kind='image', caption='ilustracja demo')
        created[0].featured = True; created[0].save()
        created[-1].featured = True; created[-1].save()
        for p in created:
            for u, k in [(admin, 'classic'), (ai, 'lol')]:
                if rnd.random() < 0.7:
                    Reaction.objects.get_or_create(post=p, user=u, defaults={'kind': k})
        c = Comment.objects.create(post=created[-1], author=ai, body='Potwierdzam, byłem tam. Napisałem 41.')
        Comment.objects.create(post=created[-1], author=admin, parent=c, format='latex',
                               body=r'Poprawna odpowiedź: $\frac{\pi^4}{15}$. Pół punktu podtrzymuję.')
        # one pending submission so the moderation queue has something in it — and it names a
        # person who does not exist yet, which is the state the queue's newest affordance is
        # about. Until a moderator publishes this, `hubert-hipoteza` is invisible in /ludzie
        # to everybody except the account that proposed him (archive/people.visible_people)
        # and shows up on the moderator's card marked NOWA.
        waiting = Post.objects.create(title='Propozycja: nowy mem o sesji', category=Category.objects.get(slug='memy'),
                                      format='text', body='Czeka na moderację. Autor wpisał osobę, której nie było w spisie.',
                                      year=2026, year_precision='exact', submitted_by=ai, status='pending')
        proposed, _ = Person.objects.get_or_create(
            slug='hubert-hipoteza',
            defaults=dict(name='Hubert Hipoteza', degree='mgr', sex='m', created_by=ai,
                          role='postać fikcyjna — doktorant, którego nikt nie widział na żywo',
                          bio='Zaproponowany przy wpisie, jeszcze nieopublikowanym. Fikcyjny, jak wszyscy tutaj.'))
        waiting.people.add(proposed)
        waiting.subjects.set(Subject.objects.filter(slug='fizyka-statystyczna'))
        # the moderation board has something on it: one hidden post, one nuked post, one hidden comment
        from archive import moderation as rules
        hidden = Post.objects.create(title='Mem, który był trochę za bardzo', category=Category.objects.get(slug='memy'),
                                     format='text', body='Ukryty przez zweryfikowanego użytkownika — widać go na tablicy moderacji.',
                                     year=2022, year_precision='exact', submitted_by=ai, status='published')
        rules.hide_post(hidden, doktorant, 'Prosiła osoba na zdjęciu.')
        nuked = Post.objects.create(title='Wpis usunięty opcją nuklearną', category=Category.objects.get(slug='historie'),
                                    format='text', body='Tego nie zobaczy nikt poza administracją.', year=2021,
                                    year_precision='approx', submitted_by=ai, status='published')
        rules.nuke_post(nuked, admin, 'Treść niezgodna z prawem (demo).')
        hc = Comment.objects.create(post=created[0], author=ai, body='Ten komentarz został ukryty przez moderację.')
        rules.hide_comment(hc, doktorant, 'Spam.')
        self.stdout.write(self.style.SUCCESS(f'Seeded {len(created)} published posts. Konta: dziekan (staff, head-admin) / doktorant (zaufany) / claude-slop (autor tresci demo)'
                                             + (', hasło fuwlol123' if settings.DEBUG else ' — hasła wypisane wyżej przy pierwszym utworzeniu')))
