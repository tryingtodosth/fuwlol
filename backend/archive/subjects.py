r"""The subject rules — what a *przedmiot* is, and how one comes into being.

`Subject` is the third way a post is filed, next to tags (anything) and people (whom it is
about). It is the university course the thing happened on, and it earns its own table for
the reason the model's docstring gives: a free tag „mechanika" is forty spellings of itself,
and the axis a physics student actually remembers by is the course.

Two rules live here because two endpoints ask them — the write path (`PostWriteSerializer`)
and the read path (`SubjectViewSet`) — and an endpoint that re-derives one is how the
editor and the browse page start disagreeing about what exists.

**A subject may be created by naming it.** Any account may; there is no queue, because
unlike a person a subject is not a claim about a human being. The de-duplication is a plain
`get_or_create` on the slug and deliberately nothing cleverer: fuzzy matching would collapse
„Mechanika klasyczna" and „Mechanika klasyczna R", which the Faculty runs as two different
courses for two different tracks. Genuine duplicates are a moderator's merge in the admin
(`SubjectAdmin.merge`), which is cheap, and the alternative — refusing a near-match at
submission time — is not.

**The slug folds Polish properly.** `django.utils.text.slugify` drops „ł" altogether (NFKD
leaves it undecomposed and the ASCII encode throws it away), so „Fizyka ciała stałego" would
file itself as `fizyka-ciaa-staego`. `search.normalize_text` already maps ł→l on the way into
the search index, and the same fold is what a subject slug is built from — one folding rule
for the whole app.
"""
import logging
import re

from django.utils.text import slugify
from rest_framework.exceptions import ValidationError

from .search import normalize_text

log = logging.getLogger('security')

SUBJECT_NAME_MIN = 2
SUBJECT_NAME_MAX = 120
# A post happens on one course, occasionally two ("Analiza" and "Algebra" in the same
# exam week). Six is generous and it is the number that stops a single submission from
# minting a hundred rows nobody will ever merge. Tags are uncapped because a tag is free
# text that costs a row and nothing else; a subject shows up in a public index.
MAX_SUBJECTS_PER_POST = 6
# Where a named subject files itself: after every seeded row (the programme uses 10…400),
# alphabetically among its own kind. The programme is an offer; a named one is a guess.
NAMED_SUBJECT_ORDER = 900

NOT_A_NAME = 'Przedmiot to nazwa zajęć, nie adres.'


def subject_slug(name):
    """`fizyka-ciala-stalego` from „Fizyka ciała stałego" — and from `fizyka-ciala-stalego`,
    because a slug folds to itself. That is what lets the write path take a slug straight
    from the picker and a name typed by hand through exactly one lookup."""
    return slugify(normalize_text(name))[:120]


def clean_subject_name(raw):
    """(name, slug) or DRF 400. The refusal says which of the two rules was broken, because
    „za długa" and „to jest adres" want different fixes from the person typing."""
    name = re.sub(r'\s+', ' ', str(raw or '')).strip()
    if '@' in name or re.search(r'https?://|www\.', name, re.I):
        raise ValidationError({'subjects': NOT_A_NAME})
    if not SUBJECT_NAME_MIN <= len(name) <= SUBJECT_NAME_MAX:
        raise ValidationError({'subjects': f'Nazwa przedmiotu: od {SUBJECT_NAME_MIN} do {SUBJECT_NAME_MAX} znaków.'})
    slug = subject_slug(name)
    if not slug:
        raise ValidationError({'subjects': 'Nazwa przedmiotu musi zawierać litery lub cyfry.'})
    return name, slug


def resolve_subjects(items, user):
    """A list of names and/or slugs → the `Subject` rows to attach, in the order given and
    without duplicates. Anything that does not exist yet is created and credited to `user`
    (NULL stays the mark of a row that came from the Faculty's programme, and that is what
    `SubjectViewSet` lists unconditionally).

    Called from inside the post's transaction, so a refusal further down the write path
    takes the rows it made with it rather than leaving orphans behind.
    """
    from .models import Subject
    out, seen = [], set()
    for item in items:
        # A picker chip may arrive as an object even here (the three pickers share one
        # component); either of its two identifying keys folds to the same slug.
        raw = (item.get('slug') or item.get('name')) if isinstance(item, dict) else item
        raw = str(raw or '').strip()
        if not raw:
            continue
        name, slug = clean_subject_name(raw)
        subject = Subject.objects.filter(slug=slug).first()
        if subject is None:
            if user is None or not getattr(user, 'is_authenticated', False):
                raise ValidationError({'subjects': 'Nowy przedmiot może dodać tylko zalogowana osoba.'})
            if len(seen) >= MAX_SUBJECTS_PER_POST:
                raise ValidationError({'subjects': f'Najwyżej {MAX_SUBJECTS_PER_POST} przedmiotów w jednym wpisie.'})
            subject = Subject.objects.create(slug=slug, name=name[:SUBJECT_NAME_MAX],
                                             order=NAMED_SUBJECT_ORDER, created_by=user)
            log.info('subject created slug=%s by=%s', subject.slug, getattr(user, 'username', '?'))
        if subject.pk not in seen:
            seen.add(subject.pk)
            out.append(subject)
        if len(out) > MAX_SUBJECTS_PER_POST:
            raise ValidationError({'subjects': f'Najwyżej {MAX_SUBJECTS_PER_POST} przedmiotów w jednym wpisie.'})
    return out
