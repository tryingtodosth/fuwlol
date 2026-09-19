r"""Demo portraits, so the gallery is judgeable before anybody uploads a photograph.

The person this runs against — `kwant-niepewny` — is FICTIONAL, like everybody in
`archive/management/commands/seed_demo.py`, and that is not a detail. This command sets
`image_consent='granted'` on somebody, which is the flag that lets strangers publish
photographs of them; doing that to a real member of staff from a seed script would be the
archive inventing a consent nobody gave. A fictional lecturer can consent to anything,
including a rectangle of flat colour with his own name written on it.

The images are drawn by Pillow rather than shipped as files, the same way `seed_demo._png`
draws post illustrations: a repository of a humour archive should not carry binary blobs
it cannot account for, and a generated PNG is reproducible, tiny and obviously not a
photograph of anybody.

Idempotent: every row is looked up by a stable marker name before it is created, so
running it twice leaves the same four portraits and the same two votes. It DOES re-assert
`image_consent='granted'`, which means running it again undoes a consent you flipped by
hand to try the revocation path — stated here rather than guarded, because restoring the
demo state is what a seed is for and because the only person it can do that to is
fictional. Never point this command at a real entry.
"""
import hashlib
import io

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw

from archive.models import Person

from portraits.models import Portrait, PortraitVote
from portraits.rules import record

PERSON_SLUG = 'kwant-niepewny'
SOURCE = 'Zdjęcie demonstracyjne wygenerowane przez seed_portraits — postać fikcyjna.'
# (marker filename, caption, source note, background colour, status)
DEMO = [
    ('portret-demo-1.png', 'Podczas wykładu z mechaniki kwantowej', SOURCE, (23, 94, 76), 'published'),
    ('portret-demo-2.png', 'Przy tablicy, w trakcie dowodu, który się nie zmieścił', SOURCE, (168, 66, 4), 'published'),
    ('portret-demo-3.png', 'Nieoznaczone — dokładna data nieznana z przyczyn zasadniczych', SOURCE, (60, 60, 90), 'published'),
    # One waiting for a decision, so /moderacja/portrety has something in it out of the
    # box — the same reason seed_demo leaves one post in the post queue. A moderation
    # surface with nothing on it is a surface nobody can tell apart from a broken one.
    ('portret-demo-4.png', 'Zgłoszenie czekające na moderację',
     'Zdjęcie demonstracyjne — czeka w kolejce, żeby było co obejrzeć w /moderacja/portrety.',
     (90, 60, 20), 'pending'),
]


def _png(text, color, size=(480, 600)):
    """A portrait-shaped rectangle with a caption. Portrait-shaped on purpose: the page
    draws these at 130 px wide and a landscape demo image would make the layout look right
    for the wrong reason."""
    img = Image.new('RGB', size, color)
    d = ImageDraw.Draw(img)
    d.rectangle([14, 14, size[0] - 15, size[1] - 15], outline=(255, 255, 255), width=3)
    d.ellipse([size[0] // 2 - 90, 120, size[0] // 2 + 90, 300], fill=(255, 255, 255))
    d.ellipse([size[0] // 2 - 140, 330, size[0] // 2 + 140, 620], fill=(255, 255, 255))
    d.text((30, size[1] - 46), text, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


class Command(BaseCommand):
    help = 'Demo portraits for the fictional dr Kwant Niepewny (idempotent).'

    def handle(self, *args, **opts):
        person = Person.objects.filter(slug=PERSON_SLUG).first()
        if person is None:
            self.stdout.write(self.style.WARNING(
                f'Nie ma osoby „{PERSON_SLUG}” — najpierw `manage.py seed_demo`.'))
            return
        if person.image_consent != 'granted':
            person.image_consent = 'granted'
            person.save(update_fields=['image_consent'])
            self.stdout.write(f'{person.full_name}: zgoda na wizerunek = wyrażona (postać fikcyjna).')

        uploader = User.objects.filter(username='claude-slop').first()
        voters = list(User.objects.filter(username__in=['dziekan', 'doktorant']))
        if uploader is None:
            self.stdout.write(self.style.WARNING('Brak konta demo „claude-slop” — najpierw `manage.py seed_demo`.'))
            return

        made = []
        for name, caption, source_note, color, status in DEMO:
            portrait = Portrait.objects.filter(person=person, original_name=name).first()
            if portrait is None:
                data = _png(f'{person.full_name} — demo', color)
                portrait = Portrait.objects.create(
                    person=person, uploaded_by=uploader, uploaded_by_username=uploader.username,
                    file=ContentFile(data, name=name), original_name=name, caption=caption,
                    source_note=source_note, rights_confirmed=True, status=status,
                    sha256=hashlib.sha256(data).hexdigest())
                if status == 'published':
                    record(portrait, uploader, 'publish', reason='seed_portraits', previous_status='')
            if portrait.status == 'published':
                made.append(portrait)

        # Both demo voters pick the SECOND photograph, not the first. That is the point of
        # the demo: the winner is decided by the vote, and only falls back to "the oldest
        # one" on a tie — a seed where the oldest also happens to win proves neither.
        winner = made[1] if len(made) > 1 else made[0]
        for voter in voters:
            PortraitVote.objects.get_or_create(portrait=winner, user=voter)

        total = Portrait.objects.filter(person=person).count()
        waiting = Portrait.objects.filter(person=person, status='pending').count()
        self.stdout.write(self.style.SUCCESS(
            f'Portrety demo dla {person.full_name}: {total} w bazie '
            f'({len(made)} w galerii, {waiting} w kolejce), '
            f'głosy: {PortraitVote.objects.filter(portrait__person=person).count()}.'))
