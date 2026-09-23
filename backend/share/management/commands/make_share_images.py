r"""Draws the three fallback share cards into frontend/static/, once.

    ../.venv/bin/python manage.py make_share_images

**Why they are files in the repository rather than a view.** A card that is rendered on
demand is a card that Facebook fetches while Postgres is busy, cached for a week by
somebody else's CDN, and impossible to look at before it goes out. These three never
change — they carry no post, no name and no count — so they are drawn once, committed, and
served by nginx from the SPA build like the favicon. The command stays so that the next
person can change the wording without reverse-engineering a PNG.

**Why 1200×630.** It is the size every scraper's documentation asks for, and — the part
that matters here — it clears Facebook's 200×200 floor with room to spare. The faculty's
own silhouettes are 130×130: linking one directly would mean Messenger showing no picture
at all, which is the bug this whole app exists to fix. So the silhouette goes INSIDE the
card, in a bordered cell, exactly as the faculty's directory prints a photograph.

The look is `frontend/src/app.css`, measured from www.fuw.edu.pl: a #d9d9d9 banner, the
#175e4c bar, #444 text on white, a ✱ in front of the headline, 1 px #ccc rules.
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

WIDTH, HEIGHT = 1200, 630
GREEN = (23, 94, 76)
BANNER = (217, 217, 217)
TEXT = (68, 68, 68)
DARK = (34, 34, 34)
LINE = (204, 204, 204)
WHITE = (255, 255, 255)
RUST = (168, 66, 4)

FONT_DIRS = ['/usr/share/fonts/truetype/dejavu', '/usr/share/fonts/TTF',
             '/usr/local/share/fonts', '/Library/Fonts']
TAGLINE = 'archiwum folkloru Wydziału Fizyki UW'
SUBLINE = 'memy · cytaty z wykładów · legendarne zadania · kartki z drzwi pracowni'


def _font(name: str, size: int):
    from PIL import ImageFont
    for directory in FONT_DIRS:
        path = Path(directory) / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    raise CommandError(f'Nie znalazłem czcionki {name} — zainstaluj fonts-dejavu-core '
                       f'(szukałem w: {", ".join(FONT_DIRS)}).')


def _frame(draw, title_font, sub_font, small_font):
    """The banner, the green bar and the footer rule — the parts every card shares, and
    the parts that make it recognisable as this site at thumbnail size."""
    draw.rectangle([0, 0, WIDTH, 150], fill=BANNER)
    # The logo mark from Header.svelte, drawn rather than rasterised: a green square, a
    # pediment, four columns and a plinth. It is the faculty's building, abstracted.
    x, y, s = 60, 40, 70
    draw.rectangle([x, y, x + s, y + s], fill=GREEN)
    draw.polygon([(x + s * 0.5, y + s * 0.13), (x + s * 0.91, y + s * 0.37),
                  (x + s * 0.09, y + s * 0.37)], fill=WHITE)
    for i, cx in enumerate((0.13, 0.30, 0.59, 0.76)):
        draw.rectangle([x + s * cx, y + s * 0.41, x + s * (cx + 0.11), y + s * 0.74], fill=WHITE)
    draw.rectangle([x + s * 0.07, y + s * 0.76, x + s * 0.93, y + s * 0.85], fill=WHITE)

    draw.text((150, 48), 'fuw.lol', font=title_font, fill=DARK)
    draw.text((152, 108), 'ARCHIWUM WYDZIAŁU FIZYKI UW', font=small_font, fill=TEXT)
    draw.rectangle([0, 150, WIDTH, 196], fill=GREEN)
    draw.text((60, 160), 'Strona główna    Przeglądaj    Ludzie    Przedmioty    Oś czasu',
              font=sub_font, fill=WHITE)
    draw.line([0, HEIGHT - 6, WIDTH, HEIGHT - 6], fill=LINE, width=2)


def _default_card(out: Path):
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)
    _frame(draw, _font('DejaVuSans-Bold.ttf', 52), _font('DejaVuSans.ttf', 20),
           _font('DejaVuSans.ttf', 19))
    star = _font('DejaVuSans.ttf', 44)
    head = _font('DejaVuSans-Bold.ttf', 44)
    body = _font('DejaVuSans.ttf', 26)
    draw.text((60, 310), '✱', font=star, fill=RUST)
    draw.text((110, 312), TAGLINE, font=head, fill=DARK)
    draw.text((110, 386), SUBLINE, font=body, fill=TEXT)
    draw.line([60, 460, WIDTH - 60, 460], fill=LINE, width=1)
    draw.text((60, 490), 'fuw.lol', font=_font('DejaVuSans-Bold.ttf', 30), fill=GREEN)
    draw.text((200, 496), '— zbierane i moderowane przez czytelników', font=body, fill=TEXT)
    img.save(out, 'PNG', optimize=True)
    return out


def _person_card(out: Path, silhouette: Path, label: str):
    """The faculty's own placeholder, in the faculty's own frame. The silhouette is scaled
    with NEAREST, not a smooth filter: it is a 130 px black-and-white drawing, and every
    interpolating filter turns its flat areas into grey mush at this size."""
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)
    _frame(draw, _font('DejaVuSans-Bold.ttf', 52), _font('DejaVuSans.ttf', 20),
           _font('DejaVuSans.ttf', 19))

    photo = Image.open(silhouette).convert('RGBA')
    photo = photo.resize((260, 260), Image.NEAREST)
    cell = Image.new('RGB', (260, 260), WHITE)
    cell.paste(photo, (0, 0), photo)
    img.paste(cell, (60, 280))
    draw.rectangle([59, 279, 60 + 260, 280 + 260], outline=LINE, width=1)

    head = _font('DejaVuSans-Bold.ttf', 40)
    body = _font('DejaVuSans.ttf', 26)
    draw.text((360, 290), '✱', font=_font('DejaVuSans.ttf', 40), fill=RUST)
    draw.text((405, 292), 'Spis osób', font=head, fill=DARK)
    draw.text((405, 360), label, font=body, fill=TEXT)
    draw.text((405, 400), 'Zdjęcie tylko za zgodą osoby (art. 81 pr. aut.).', font=body, fill=TEXT)
    draw.line([360, 460, WIDTH - 60, 460], fill=LINE, width=1)
    draw.text((360, 486), 'fuw.lol — archiwum Wydziału Fizyki UW', font=body, fill=GREEN)
    img.save(out, 'PNG', optimize=True)
    return out


class Command(BaseCommand):
    help = 'Rysuje karty podglądu (og-default.png, og-osoba-m.png, og-osoba-f.png, og-osoba.png) w frontend/static/.'

    def add_arguments(self, parser):
        parser.add_argument('--out', default='', help='katalog docelowy (domyślnie frontend/static)')

    def handle(self, *args, **options):
        out_dir = Path(options['out']) if options['out'] else Path(settings.BASE_DIR).parent / 'frontend' / 'static'
        if not out_dir.is_dir():
            raise CommandError(f'Nie ma katalogu {out_dir}.')
        img_dir = out_dir / 'img'
        written = [_default_card(out_dir / 'og-default.png')]
        # The first two silhouettes are the faculty directory's own; the third is ours, drawn
        # in their style for a person whose `sex` nobody has set (previews.PERSON_CARDS).
        for sex, filename, label in (('m', 'anonymousmabw.png', 'Osoba bez zdjęcia w archiwum.'),
                                     ('f', 'anonymousfebw.png', 'Osoba bez zdjęcia w archiwum.'),
                                     ('', 'anonymousbw.png', 'Osoba bez zdjęcia w archiwum.')):
            silhouette = img_dir / filename
            if not silhouette.exists():
                raise CommandError(f'Brakuje sylwetki {silhouette} — to plik ze spisu osób FUW.')
            card = out_dir / (f'og-osoba-{sex}.png' if sex else 'og-osoba.png')
            written.append(_person_card(card, silhouette, label))
        for path in written:
            self.stdout.write(self.style.SUCCESS(f'zapisano {path}'))
