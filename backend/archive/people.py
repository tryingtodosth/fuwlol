r"""The people rules — whose post is whose, and how a name is filed.

`Person` is the archive's cast: a lecturer, a legendary student, the porter. Two things
about a person are decided here and nowhere else, because both are asked by more than one
endpoint (the directory, the profile, the `?person=` browse filter, the stats), and an
endpoint that re-derives a rule is how two pages start disagreeing.

**Whose post is whose.** A post names a person directly (`Post.people`) or through one of
the person's *aliases* — the nicknames every lecturer collects — which are ordinary `Tag`
rows attached to the person (`Person.aliases`). To the submitter "Hamiltonianka" is a tag
like any other; to the reader it is a link to prof. Hamiltonian. This is what makes a tag
typed into a post long before the person existed still count the moment somebody attaches
it: no re-filing, no second copy of the post, and the original bug — a person mentioned
only as a tag never reaching their page — cannot recur. `person_posts_q` is the rule;
`annotate_people` and the browse filter both ask it.

**How a name is filed.** The faculty directory this page copies (fuw.edu.pl/osoby-fuw.html)
files people by surname under a letter of the Polish alphabet. A folklore name does not
always have a surname ("Pani z portierni") and usually arrives with a title glued to the
front ("dr Kwant Niepewny"), so `split_degree` peels the title off, `derive_surname` takes
the last word, and `sort_key_for` folds it (no case, no diacritics — `search.normalize_text`)
so that Łoś files next to Lis whatever the database's collation thinks. The *letter* shown
in the index keeps its diacritic: Ż is its own letter in the faculty's alphabet strip, and
it is here too.
"""
import logging
import re

from django.db.models import IntegerField, OuterRef, Q, Subquery
from django.utils.text import slugify
from rest_framework.exceptions import APIException, NotFound, ValidationError

from .search import normalize_text

log = logging.getLogger('security')

# Leading tokens that are a title, not a name — lower-case, as written in Polish usage. The
# split stops at the first token that is not one of these, so "dr hab. Jan Nowak" gives
# ('dr hab.', 'Jan Nowak') and a name with no title comes back unchanged.
HONORIFICS = frozenset({'prof.', 'prof', 'dr', 'dr.', 'hab.', 'hab', 'mgr', 'mgr.', 'inż.', 'inz.',
                        'lic.', 'doc.', 'doc', 'ks.', 'red.', 'płk', 'płk.', 'n.', 'med.'})
# The alphabet strip of the faculty directory, in its order. Letters no Polish surname
# starts with (Ą, Ę, Ń, Ó, Q, X) are absent there and absent here; a person whose surname
# does start with one still gets a row — the strip just has no shortcut to it.
LETTERS = list('ABCĆDEFGHIJKLŁMNOPRSŚTUVWYZŻ')
MAX_ALIASES = 12
ALIAS_MAX_LEN = 60
PERSON_NAME_MIN = 2
PERSON_NAME_MAX = 120
# How many people one post may INVENT. A post is about one lecturer, sometimes a lecturer
# and a student; five is already a crowd. The cap is on creations, not on how many people a
# post names — picking twenty existing people is odd but harmless, while minting twenty is
# how a directory becomes a guestbook.
MAX_NEW_PEOPLE_PER_POST = 5
# Unknown, unlisted and opted-out all sound like this. That is the point: `is_listed=False`
# is how somebody who asked to be taken out of the archive is kept out of it, and an error
# message that distinguished the three would turn this endpoint into a lookup service for
# exactly the people who asked not to be looked up.
NO_SUCH_PERSON = 'Nie ma takiej osoby w spisie — wpisz imię i nazwisko, żeby dodać nową.'


class Conflict(APIException):
    status_code = 409
    default_detail = 'Konflikt.'


# --- filing ---------------------------------------------------------------------------

def split_degree(name):
    """('dr hab.', 'Jan Nowak') from 'dr hab. Jan Nowak'; ('', name) when there is nothing
    to peel — or when peeling would leave nothing, for a person actually called "Doc"."""
    tokens = (name or '').split()
    i = 0
    while i < len(tokens) and tokens[i].lower() in HONORIFICS:
        i += 1
    if i == 0 or i == len(tokens):
        return '', ' '.join(tokens)
    return ' '.join(tokens[:i]), ' '.join(tokens[i:])


def derive_surname(name):
    """The last word of the name without its title, punctuation trimmed: 'Nowak' from
    'dr Jan Nowak', 'portierni' from 'Pani z portierni'. A heuristic, not a rule — which is
    why `Person.surname` is an editable field that this only fills when blank."""
    _, rest = split_degree(name)
    tokens = rest.split()
    return tokens[-1].strip('.,;:()"\'') if tokens else ''


def letter_for(surname, name=''):
    s = (surname or name or '').strip()
    return s[:1].upper() if s else ''


def sort_key_for(surname, name):
    """Folded 'surname, then the rest of the name' — what the directory orders by:
    ('Łoś', 'dr Jan Łoś') → 'los jan'. The surname is not repeated, so two people who share
    one order by their first names, as they do in the faculty's list."""
    _, rest = split_degree(name)
    s = normalize_text(surname)
    others = [t for t in normalize_text(rest).split() if t != s]
    return ' '.join([s] + others).strip()[:120]


# --- whose post is whose ---------------------------------------------------------------

def person_posts_q(ref):
    """Posts that are this person's: named directly, or tagged with one of their aliases.
    `ref` is a Person, a pk, or `OuterRef('pk')` inside a subquery. Callers that filter a
    Post queryset with this must `.distinct()` — the OR spans two many-to-many joins."""
    return Q(people=ref) | Q(tags__alias_of=ref)


def person_posts_slug_q(slug):
    return Q(people__slug=slug) | Q(tags__alias_of__slug=slug)


class _Over(Subquery):
    """An SQL aggregate over the rows of a correlated subquery. Django's own
    `Count(..., distinct=True)` cannot express "distinct posts reachable through EITHER of
    two many-to-many joins" without double counting a post that is both named and tagged;
    wrapping the subquery and aggregating outside it can."""
    output_field = IntegerField()

    def __init__(self, queryset, expression):
        self.template = f'(SELECT {expression} FROM (%(subquery)s) _p)'
        super().__init__(queryset)


def _public_posts():
    """What counts towards a person: published, not under escalation, and not restricted to
    the trusted tier — a person whose only post is in quarantine must not carry a count that
    says the post exists (`views._published_count` keeps the same clause for categories and
    tags).

    `trusted_only` is here for the same reason and one more: the count is viewer-independent
    on purpose (every card, every preview and the sitemap print the same number), and a
    „kontrowersyjny" post is blanked of its people and unreachable through `?person=` for a
    stranger. Counting it would put the one number that says „there is something about this
    person" back on a public page. A trusted reader therefore sees a count lower than the
    list they can open — the honest direction, and `archive/CLAUDE.md` says so."""
    from escalation.visibility import active_escalation_ids
    from .models import Post
    qs = Post.objects.filter(status='published', trusted_only=False)
    escalated = active_escalation_ids(Post)
    if escalated:
        qs = qs.exclude(pk__in=escalated)
    return qs


def annotate_people(qs):
    """`post_count`, `year_min`, `year_max` on each person, from the posts the public may see."""
    posts = _public_posts().filter(person_posts_q(OuterRef('pk'))).order_by().values('id', 'year')
    return qs.annotate(post_count=_Over(posts, 'COUNT(DISTINCT id)'),
                       year_min=_Over(posts, 'MIN(year)'),
                       year_max=_Over(posts, 'MAX(year)'))


# --- aliases ----------------------------------------------------------------------------

def clean_alias(name):
    name = re.sub(r'\s+', ' ', name or '').strip()
    if not 2 <= len(name) <= ALIAS_MAX_LEN:
        raise ValidationError({'name': f'Ksywka: od 2 do {ALIAS_MAX_LEN} znaków.'})
    if '@' in name or re.search(r'https?://|www\.', name, re.I):
        raise ValidationError({'name': 'Ksywka to nazwa, nie adres.'})
    slug = slugify(name)[:60]
    if not slug:
        raise ValidationError({'name': 'Ksywka musi zawierać litery lub cyfry.'})
    return name, slug


def add_alias(person, name, actor):
    """Attach a nickname as an alias. The Tag is created if it did not exist, so posts tagged
    with it later — or earlier — are the person's. One nickname belongs to one person:
    "Profesor" shared by two lecturers would file every "Profesor" post under both, which is
    a claim about two real people that nobody made. Raises DRF 400 / 409."""
    from .models import Tag
    name, slug = clean_alias(name)
    if person.aliases.filter(slug=slug).exists():
        raise ValidationError({'name': 'Ta osoba ma już taką ksywkę.'})
    if person.aliases.count() >= MAX_ALIASES:
        raise ValidationError({'name': f'Najwyżej {MAX_ALIASES} ksywek na osobę.'})
    tag, _ = Tag.objects.get_or_create(slug=slug, defaults={'name': name})
    other = tag.alias_of.exclude(pk=person.pk).first()
    if other is not None:
        raise Conflict(f'Ksywka „{tag.name}” należy już do: {other.name}.')
    person.aliases.add(tag)
    log.info('person alias added person=%s tag=%s by=%s', person.slug, tag.slug, getattr(actor, 'username', '?'))
    return tag


def remove_alias(person, tag_slug, actor):
    """Detach a nickname. A tag left with no owner and no posts is deleted — it only ever
    existed for the alias."""
    tag = person.aliases.filter(slug=tag_slug).first()
    if tag is None:
        raise NotFound('Ta osoba nie ma takiej ksywki.')
    person.aliases.remove(tag)
    log.info('person alias removed person=%s tag=%s by=%s', person.slug, tag.slug, getattr(actor, 'username', '?'))
    if not tag.posts.exists() and not tag.alias_of.exists():
        tag.delete()


# --- who the directory shows ------------------------------------------------------------

def visible_people_q(user):
    """Which people /ludzie lists, as a queryset filter over `annotate_people`'s output.

    Only meaningful on a queryset that has been through `annotate_people` — it leans on the
    `post_count` annotation. Most callers want `visible_people(user)` below, which does both
    and cannot be held wrong.

    Derived, never toggled — there is no "approved" flag on a person, because a flag is a
    second lifecycle to keep in step with the first one, and it would be wrong the moment a
    post is published, hidden or rejected. Instead:

      * `post_count > 0`  — somebody published something that names them. This is the
        ordinary case and the reason the rule works: a person named on a post that is still
        in the moderation queue is invisible, and appears by themself the instant the post
        goes live. Nothing has to remember to list them.
      * `created_by IS NULL` — seeded, or made by staff in the admin. An entry somebody put
        there on purpose stays there with no posts at all.
      * `created_by == me` — the person I proposed while writing a post. I can see what I
        named; a stranger cannot, so a rejected submission never leaves a stranger a
        readable page about a named human being.

    Staff get no bypass and need none: the moderator reads proposed people off the post
    under review (`ModerationPostSerializer`), and when they merge a duplicate they want to
    search the people who ARE published — which is what this returns.
    """
    cond = Q(post_count__gt=0) | Q(created_by__isnull=True)
    if user is not None and getattr(user, 'is_authenticated', False):
        cond |= Q(created_by=user)
    return cond


def visible_people(user):
    """THE queryset of people `user` may see, annotated and filed: `is_listed`, then
    `visible_people_q`, then the directory's own ordering.

    This is the shape every caller should use — the API's list and profile, a link-preview
    renderer, anything that answers "may this person be shown to whoever is asking". Handing
    out only the `Q` was not enough: it depends on the `post_count` annotation, so a caller
    who filtered without annotating first would get a crash at best and an unfiltered list
    at worst, and "at worst" here means publishing a page about a named human being that a
    submission was still waiting to justify."""
    from .models import Person
    return (annotate_people(Person.objects.filter(is_listed=True).prefetch_related('aliases'))
            .filter(visible_people_q(user))
            .order_by('sort_key', 'name'))


# --- naming a person into existence ------------------------------------------------------

def clean_person_name(raw):
    """('dr hab.', 'Jan Nowak') from whatever was typed into the name box, or DRF 400.

    The title is peeled off with `split_degree` because people type it into the name field
    every single time — the faculty's own directory prints it in a separate column, and so
    does /ludzie, so a Person whose `name` is "dr Jan Nowak" would render as "dr dr Jan
    Nowak" and file itself under D."""
    name = re.sub(r'\s+', ' ', str(raw or '')).strip()
    if '@' in name or re.search(r'https?://|www\.', name, re.I):
        raise ValidationError({'people': 'Osoba to imię i nazwisko, nie adres ani link.'})
    if not PERSON_NAME_MIN <= len(name) <= PERSON_NAME_MAX:
        raise ValidationError({'people': f'Imię i nazwisko: od {PERSON_NAME_MIN} do {PERSON_NAME_MAX} znaków.'})
    # `split_degree` deliberately refuses to peel a name down to nothing — somebody may
    # actually be called "Doc" — so "dr hab." comes back as a NAME rather than as a title
    # with nothing behind it. For filing that is the right answer; for creating a row in a
    # directory of people it is not, so the all-honorifics case is checked here instead.
    if all(t.lower() in HONORIFICS for t in name.split()):
        raise ValidationError({'people': 'Sam tytuł to jeszcze nie osoba — dopisz imię i nazwisko.'})
    degree, rest = split_degree(name)
    return degree, rest.strip()


def unique_person_slug(name):
    """A free slug for a new person, folded the same way a subject's is (ł → l, not ł → ∅).
    Trimmed short enough that the `-2`, `-3` disambiguator still fits in the column."""
    base = slugify(normalize_text(name))[:44] or 'osoba'
    from .models import Person
    slug, n = base, 2
    while Person.objects.filter(slug=slug).exists():
        slug = f'{base}-{n}'
        n += 1
    return slug


def _existing_person(slug):
    from .models import Person
    person = Person.objects.filter(slug=str(slug).strip(), is_listed=True).first()
    if person is None:
        raise ValidationError({'people': NO_SUCH_PERSON})
    return person


def _person_by_name(spec, user, new_so_far):
    """(person, created) for `{"name": "Anna Nowak", "degree": "dr", "role": "wykładowczyni"}`.

    The de-duplication is on `name_key` — the folded bare name — and it REUSES rather than
    creates, which is the whole point of naming people instead of ticking them: the third
    person to write about Anna Nowak must land on the same page as the first, not on a twin
    that splits her posts in half and files one copy under the wrong letter.

    A match that is no longer listed is refused with `NO_SUCH_PERSON`, the same sentence an
    unknown slug gets. Reusing the row would put somebody who asked to be taken out of the
    archive back into a post by typing their name, and creating a twin would do it worse;
    refusing is the only answer that keeps the opt-out meaning anything. It does leak that
    *some* person by that name is not available, which is the smaller harm and a deliberate
    trade — the alternative is an opt-out that anybody can undo with a keyboard.
    """
    from .models import Person
    typed_degree, name = clean_person_name(spec.get('name'))
    key = normalize_text(name)[:160]
    match = Person.objects.filter(name_key=key).first()
    if match is not None:
        if not match.is_listed:
            raise ValidationError({'people': NO_SUCH_PERSON})
        return match, False
    if user is None or not getattr(user, 'is_authenticated', False):
        raise ValidationError({'people': 'Nową osobę może dodać tylko zalogowana osoba.'})
    if new_so_far >= MAX_NEW_PEOPLE_PER_POST:
        raise ValidationError({'people': f'Najwyżej {MAX_NEW_PEOPLE_PER_POST} nowych osób w jednym wpisie — '
                                         'resztę wybierz z listy albo dodaj kolejnym wpisem.'})
    # what the user picked in the select wins; the title they glued to the name is the fallback
    degree = re.sub(r'\s+', ' ', str(spec.get('degree') or '')).strip()[:40] or typed_degree
    role = re.sub(r'\s+', ' ', str(spec.get('role') or '')).strip()[:120]
    person = Person.objects.create(slug=unique_person_slug(name), name=name, degree=degree,
                                   role=role, created_by=user)
    log.info('person proposed slug=%s by=%s', person.slug, getattr(user, 'username', '?'))
    return person, True


def resolve_people(items, user):
    """The write path's one entry point: a mixed list of slugs and new-person objects →
    the `Person` rows to attach, in order, without duplicates.

        ["jan-kowalski", {"name": "Anna Nowak", "degree": "dr", "role": "wykładowczyni"}]

    Called from inside the post's transaction (`PostWriteSerializer._apply_m2m`), so a
    refusal anywhere in the write path takes the people it created with it. Nothing else in
    the codebase may create a `Person` from user input — the admin and the seed are the
    other two doors, and both are staff.
    """
    out, seen, new_count = [], set(), 0
    for item in items:
        if isinstance(item, dict) and not str(item.get('slug') or '').strip():
            person, created = _person_by_name(item, user, new_count)
            new_count += 1 if created else 0
        else:
            person = _existing_person(item.get('slug') if isinstance(item, dict) else item)
        if person.pk not in seen:
            seen.add(person.pk)
            out.append(person)
    return out


def sweepable_people(before):
    """Proposed people nobody ever published anything about: named by a user (never seeded
    or staff-made), created before `before`, and with no post of ANY status behind them —
    `Post.all_objects`, so a person attached to something in criminal quarantine is not
    quietly deleted out from under the escalation that is holding it.

    A generator rather than a queryset: "has no posts at all, counting aliases" is the OR of
    two many-to-many joins, and `exists()` per candidate is both correct and, on the handful
    of rows this ever sees, cheaper than teaching the ORM to say it."""
    from .models import Person, Post
    for person in Person.objects.filter(created_by__isnull=False, created_at__lt=before):
        if not Post.all_objects.filter(person_posts_q(person)).exists():
            yield person
