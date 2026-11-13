"""vetdir — every constant, closed vocabulary and rule the directory's endpoints ask, in one module
(root CLAUDE.md, boundary 2).

A veterinary clinic that runs MedApp's vet app lists itself (VETDIR-S1, the medapp repository's
`docs/work/VETDIR-S1-BRIEF.md`): a public card of structured facts — no free paragraph, no price,
no person's name, no photo — and, where the clinic chose it, a form on which a pet owner with no
account asks for a visit. Staff confirm or decline the request in the vet app. Nothing here ranks,
rates or reviews anything.

Every constant below with a MIRRORED comment is copied by hand in the medapp repository's
`src/lib/vetdir/api.ts` (a separate repository, nothing imports across) and pinned on both sides:
`tests.py MirroredConstantsTests` here, `scripts/vetdir-check.mjs` group A there. Change one,
change the other.

The vocabulary is `wum`'s on purpose (the hours-window shape, VISIT_REASON_MAX, a transition table
mirrored on both sides with the client only hiding buttons), so the two can be merged later; the
rows are not `wum`'s, because those belong to accounts and the directory has none.
"""
import hashlib
import hmac
import re
import secrets
from datetime import date, datetime, timedelta

from django.utils import timezone

# --- consent -------------------------------------------------------------------------------------

# The listing statement the clinic ticks in `/vet/settings` (MedApp's `vd_consent` in en / pl / uk).
# The date is the version; a listing carries the version it was ticked under. Change a word → bump
# both sides, or every listing is 400 `consent_version`.
# MIRRORED in medapp `src/lib/vetdir/api.ts` as CONSENT_VERSION.
CONSENT_VERSION = 'vetdir-2026-11-13'
CONSENT_TEXT_EN = (
    'Publish this card on a public page of this app, with the phone and the hours as I entered '
    'them. Requests from pet owners are held on a tester service at fuw.lol with nobody on call; '
    'I can change or remove the page at any time with this clinic\'s key.'
)

# --- closed vocabularies -------------------------------------------------------------------------

# The kinds of veterinary practice the Polish act on veterinary practices names (ZLZ art. 3 as read
# for VETDIR-SCOPE §3): an office, an outpatient clinic, a veterinary hospital, a clinic.
# MIRRORED in medapp `src/lib/vetdir/api.ts` as REGISTER_TYPES.
REGISTER_TYPES = ('gabinet', 'przychodnia', 'lecznica', 'klinika')
# The animals a clinic says it treats, and the one an owner names in a request.
# MIRRORED in medapp `src/lib/vetdir/api.ts` as SPECIES.
SPECIES = ('dog', 'cat', 'rabbit', 'rodent', 'bird', 'reptile', 'horse', 'farm', 'other')
# The kinds of service. A kind, never a price, never a person.
# MIRRORED in medapp `src/lib/vetdir/api.ts` as SERVICES.
SERVICES = ('consultation', 'vaccination', 'microchipping', 'pet_passport', 'surgery', 'dentistry',
            'imaging', 'laboratory', 'hospitalisation', 'home_visits')
# The languages spoken at the desk.
# MIRRORED in medapp `src/lib/vetdir/api.ts` as LANGUAGES.
LANGUAGES = ('pl', 'en', 'uk', 'de', 'ru', 'fr', 'es', 'it')
# What the page says about out of hours (UC-069). A choice from this list plus an optional phone.
# MIRRORED in medapp `src/lib/vetdir/api.ts` as OUT_OF_HOURS.
OUT_OF_HOURS = ('none', 'open_24h', 'on_call_phone', 'other_clinic')
# The part of the day an owner wishes for. Staff set the time; no slot is computed anywhere.
# MIRRORED in medapp `src/lib/vetdir/api.ts` as PARTS_OF_DAY.
PARTS_OF_DAY = ('morning', 'afternoon', 'evening', 'any')

# One status field per lifecycle (root CLAUDE.md).
# MIRRORED in medapp `src/lib/vetdir/api.ts` as LISTING_STATUSES.
LISTING_STATUSES = ('pending', 'listed', 'unlisted')
# MIRRORED in medapp `src/lib/vetdir/api.ts` as REQUEST_STATUSES.
REQUEST_STATUSES = ('pending_email', 'requested', 'confirmed', 'declined', 'cancelled')
# Who may move a request where — THE one table. `owner` acts through a signed link in a mail,
# `clinic` with the clinic's key. Anything not in it is refused (400 `status`); nothing leaves a
# terminal state (`declined`, `cancelled`). The client only hides buttons.
# MIRRORED in medapp `src/lib/vetdir/api.ts` as REQUEST_TRANSITIONS.
REQUEST_TRANSITIONS = {
    'pending_email': {'requested': 'owner', 'cancelled': 'owner'},
    'requested': {'confirmed': 'clinic', 'declined': 'clinic', 'cancelled': 'owner'},
    'confirmed': {'cancelled': 'owner'},
}
TERMINAL_STATUSES = ('declined', 'cancelled')
# What the clinic's list shows: never a request whose owner has not pressed the link.
CLINIC_VISIBLE_STATUSES = ('requested', 'confirmed', 'declined', 'cancelled')

# --- limits --------------------------------------------------------------------------------------

# MIRRORED in medapp `src/lib/vetdir/api.ts` (each by the same name).
NAME_MAX = 120
ADDRESS_MAX = 200
TOWN_MAX = 80
PHONE_MAX = 40
EMAIL_MAX = 254
OWNER_NAME_MAX = 80
ANIMAL_NAME_MAX = 60
# `wum`'s VISIT_REASON_MAX: the one sentence beside a request.
VISIT_REASON_MAX = 300
# `wum`'s HOURS_MAX_ENTRIES: windows in a week.
HOURS_MAX_ENTRIES = 14
# A request names a day from today to today + this many days, in the clinic's wall clock.
REQUEST_HORIZON_DAYS = 60
# A confirmed start may lie this far ahead of now at most (staff may move the day).
CONFIRM_START_MAX_DAYS = 120
# A listing not refreshed by a key-holder call for this long stops being public — the end of an
# orphaned listing whose key was lost.
LISTING_IDLE_DAYS = 180
# A listing's confirmation link works this long; a listing never confirmed is deleted after
# LISTING_PENDING_DAYS (it was never public and holds an address somebody typed).
LISTING_CONFIRM_DAYS = 7
LISTING_PENDING_DAYS = 30
# A request's personal fields are blanked this many days after a terminal state or after the
# wished day; an unconfirmed one after REQUEST_UNCONFIRMED_DAYS, which is also how long its link works.
REQUEST_KEEP_DAYS = 30
REQUEST_UNCONFIRMED_DAYS = 2
# At most one mail per address per this many minutes for the same thing.
MAIL_COOLDOWN_MINUTES = 10
# A clinic's key: `secrets.token_urlsafe(32)` is 43 characters; the lookup accepts some slack.
KEY_MAX = 128
# A signed token in a mailed link.
TOKEN_MAX = 200
# The public ids: 12 URL-safe characters (72 random bits), so ids cannot be walked.
ID_RE = re.compile(r'^[A-Za-z0-9_-]{12}$')
# A phone as typed: digits, spaces, +, -, ( ), at least six digits (checked apart).
PHONE_RE = re.compile(r'^[+0-9 ()\-./]{6,40}$')
HHMM_RE = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
DAY_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
LOCALE_RE = re.compile(r'^[a-z]{2,3}(-[A-Za-z]{2})?$')
CONTROL_RE = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')

# The clinic's wall clock, as `wum`'s PRACTICE_TZ: hours and days are read in it whatever zone the
# owner's phone is in.
CLINIC_TZ = timezone.get_default_timezone()

# --- ids, keys, tokens ---------------------------------------------------------------------------


def new_public_id():
    return secrets.token_urlsafe(9)


def new_key():
    """The clinic's key: 256 bits, URL-safe, handed back ONCE in the 201 and kept as a hash."""
    return secrets.token_urlsafe(32)


def hash_key(key):
    return hashlib.sha256(key.encode()).hexdigest()


def key_matches(listing, key):
    """Constant-time comparison of a presented key with the listing's hash."""
    if not isinstance(key, str):
        return False
    key = key.strip()
    if not key or len(key) > KEY_MAX or not listing.key_hash:
        return False
    return hmac.compare_digest(hash_key(key), listing.key_hash)


# --- the card ------------------------------------------------------------------------------------

def _text_problem(value, limit, required=True):
    if not isinstance(value, str):
        return 'Wymagany tekst.' if required else 'Nieprawidłowy tekst.'
    v = value.strip()
    if required and not v:
        return 'To pole jest wymagane.'
    if len(v) > limit:
        return f'Najwyżej {limit} znaków.'
    if CONTROL_RE.search(v):
        return 'Niedozwolone znaki sterujące.'
    return None


def phone_problem(value, required=True):
    if value in (None, '') and not required:
        return None
    problem = _text_problem(value, PHONE_MAX, required)
    if problem:
        return problem
    v = value.strip()
    if not PHONE_RE.fullmatch(v) or sum(c.isdigit() for c in v) < 6:
        return 'Numer telefonu: cyfry, spacje, „+”, „-”, nawiasy; co najmniej sześć cyfr.'
    return None


def _minutes(hhmm):
    h, m = hhmm.split(':')
    return int(h) * 60 + int(m)


def hours_problems(hours):
    """`wum.rules.hours_problems`' rule: a list of {weekday 0 (Monday)…6, open, close} in the
    clinic's wall clock, several windows a day allowed when they do not overlap. Polish sentences;
    empty means the list may be saved."""
    if not isinstance(hours, list):
        return ['Godziny muszą być listą okien.']
    if len(hours) > HOURS_MAX_ENTRIES:
        return [f'Najwyżej {HOURS_MAX_ENTRIES} okien w tygodniu.']
    problems = []
    seen = {}
    for i, win in enumerate(hours):
        if not isinstance(win, dict):
            problems.append(f'Okno {i + 1} musi być obiektem.')
            continue
        wd, o, c = win.get('weekday'), win.get('open'), win.get('close')
        if not isinstance(wd, int) or isinstance(wd, bool) or not 0 <= wd <= 6:
            problems.append(f'Okno {i + 1}: dzień tygodnia to liczba 0 (poniedziałek) – 6 (niedziela).')
            continue
        if not isinstance(o, str) or not isinstance(c, str) or not HHMM_RE.match(o) or not HHMM_RE.match(c):
            problems.append(f'Okno {i + 1}: godziny w postaci „HH:MM”.')
            continue
        if _minutes(o) >= _minutes(c):
            problems.append(f'Okno {i + 1}: otwarcie musi być przed zamknięciem.')
            continue
        for (po, pc) in seen.get(wd, []):
            if _minutes(o) < pc and po < _minutes(c):
                problems.append(f'Okno {i + 1} nachodzi na inne okno tego samego dnia.')
                break
        seen.setdefault(wd, []).append((_minutes(o), _minutes(c)))
    return problems


def _subset_problem(value, vocabulary, required):
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        return 'Lista identyfikatorów.'
    if len(set(value)) != len(value):
        return 'Powtórzona pozycja.'
    unknown = [v for v in value if v not in vocabulary]
    if unknown:
        return 'Nieznana pozycja: ' + ', '.join(sorted(unknown))[:80] + '.'
    if required and not value:
        return 'Wybierz co najmniej jedną pozycję.'
    return None


# The card's keys, in order. A key not in this list is dropped, never stored.
# MIRRORED in medapp `src/lib/vetdir/api.ts` as CARD_KEYS.
CARD_KEYS = ('name', 'register_type', 'address', 'town', 'phone', 'hours', 'species', 'services',
             'languages', 'out_of_hours', 'out_of_hours_phone', 'accepts_requests')


def clean_card(data):
    """`(card, None)` — the card to store, built key by key from CARD_KEYS — or `(None, problems)`,
    a dict field → [Polish sentence] for a 400."""
    if not isinstance(data, dict):
        return None, {'card': ['Karta musi być obiektem JSON.']}
    problems = {}
    for key, limit in (('name', NAME_MAX), ('address', ADDRESS_MAX), ('town', TOWN_MAX)):
        p = _text_problem(data.get(key), limit)
        if p:
            problems[key] = [p]
    if data.get('register_type') not in REGISTER_TYPES:
        problems['register_type'] = ['Wybierz rodzaj zakładu z listy.']
    p = phone_problem(data.get('phone'))
    if p:
        problems['phone'] = [p]
    hp = hours_problems(data.get('hours', []))
    if hp:
        problems['hours'] = hp
    for key, vocabulary, required in (('species', SPECIES, True), ('services', SERVICES, False),
                                      ('languages', LANGUAGES, True)):
        p = _subset_problem(data.get(key, []), vocabulary, required)
        if p:
            problems[key] = [p]
    if data.get('out_of_hours') not in OUT_OF_HOURS:
        problems['out_of_hours'] = ['Wybierz z listy, co dzieje się poza godzinami.']
    p = phone_problem(data.get('out_of_hours_phone', ''), required=False)
    if p:
        problems['out_of_hours_phone'] = [p]
    if not isinstance(data.get('accepts_requests', False), bool):
        problems['accepts_requests'] = ['Tak albo nie.']
    if problems:
        return None, problems
    hours = sorted(({'weekday': w['weekday'], 'open': w['open'], 'close': w['close']}
                    for w in data.get('hours', [])), key=lambda w: (w['weekday'], w['open']))
    card = {
        'name': data['name'].strip(),
        'register_type': data['register_type'],
        'address': data['address'].strip(),
        'town': data['town'].strip(),
        'phone': data['phone'].strip(),
        'hours': hours,
        # In the vocabulary's order, so the page reads the same whatever order was ticked.
        'species': [s for s in SPECIES if s in data.get('species', [])],
        'services': [s for s in SERVICES if s in data.get('services', [])],
        'languages': [s for s in LANGUAGES if s in data.get('languages', [])],
        'out_of_hours': data['out_of_hours'],
        'out_of_hours_phone': (data.get('out_of_hours_phone') or '').strip(),
        'accepts_requests': data.get('accepts_requests', False) is True,
    }
    return card, None


def clean_locale(value):
    value = (value or '').strip().lower() if isinstance(value, str) else ''
    return value if len(value) <= 8 and LOCALE_RE.fullmatch(value) else ''


EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


def email_problem(value):
    if not isinstance(value, str) or not value.strip():
        return 'Podaj adres e-mail.'
    v = value.strip()
    if len(v) > EMAIL_MAX or not EMAIL_RE.fullmatch(v) or CONTROL_RE.search(v):
        return 'Nieprawidłowy adres e-mail.'
    return None


# --- visibility, derived -------------------------------------------------------------------------

def is_public(listing, now=None):
    """A listing is on its public page only when it is `listed` AND a key-holder call refreshed it
    within LISTING_IDLE_DAYS. Derived, never toggled (root CLAUDE.md)."""
    now = now or timezone.now()
    return listing.status == 'listed' and listing.seen_at >= now - timedelta(days=LISTING_IDLE_DAYS)


def accepts_requests(listing, now=None):
    return is_public(listing, now) and bool((listing.card or {}).get('accepts_requests'))


# --- the request ---------------------------------------------------------------------------------

# What an owner may send, and nothing else: an unknown key is dropped. `website` is the honeypot.
# MIRRORED in medapp `src/lib/vetdir/api.ts` as REQUEST_KEYS.
REQUEST_KEYS = ('owner_name', 'phone', 'email', 'species', 'animal_name', 'day', 'part_of_day',
                'reason', 'locale')


def clinic_today(now=None):
    return timezone.localtime(now or timezone.now(), CLINIC_TZ).date()


def clean_request(data, listing, now=None):
    """`(fields, None)` or `(None, problems)` like `clean_card`. The species must be one the clinic
    treats; the day today … today + REQUEST_HORIZON_DAYS in the clinic's wall clock."""
    if not isinstance(data, dict):
        return None, {'request': ['Zgłoszenie musi być obiektem JSON.']}
    problems = {}
    for key, limit in (('owner_name', OWNER_NAME_MAX), ('animal_name', ANIMAL_NAME_MAX)):
        p = _text_problem(data.get(key), limit)
        if p:
            problems[key] = [p]
    p = phone_problem(data.get('phone'))
    if p:
        problems['phone'] = [p]
    p = email_problem(data.get('email'))
    if p:
        problems['email'] = [p]
    treated = (listing.card or {}).get('species', [])
    if data.get('species') not in SPECIES or data.get('species') not in treated:
        problems['species'] = ['Wybierz zwierzę z listy tej przychodni.']
    if data.get('part_of_day') not in PARTS_OF_DAY:
        problems['part_of_day'] = ['Wybierz porę dnia z listy.']
    reason = data.get('reason', '')
    p = _text_problem(reason if reason is not None else '', VISIT_REASON_MAX, required=False)
    if p:
        problems['reason'] = [p]
    day = data.get('day')
    wished = None
    if isinstance(day, str) and DAY_RE.fullmatch(day):
        try:
            wished = date.fromisoformat(day)
        except ValueError:
            wished = None
    today = clinic_today(now)
    if wished is None:
        problems['day'] = ['Dzień w postaci RRRR-MM-DD.']
    elif not today <= wished <= today + timedelta(days=REQUEST_HORIZON_DAYS):
        problems['day'] = [f'Dzień od dziś do {REQUEST_HORIZON_DAYS} dni naprzód.']
    if problems:
        return None, problems
    return {
        'owner_name': data['owner_name'].strip(),
        'phone': data['phone'].strip(),
        'email': data['email'].strip().lower(),
        'species': data['species'],
        'animal_name': data['animal_name'].strip(),
        'day': wished,
        'part_of_day': data['part_of_day'],
        'reason': (reason or '').strip(),
        'locale': clean_locale(data.get('locale')),
    }, None


def parse_start(value, now=None):
    """The start staff set, an ISO instant with its offset; None when malformed or out of range."""
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        start = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if start.tzinfo is None:
        return None
    now = now or timezone.now()
    if start < now - timedelta(days=1) or start > now + timedelta(days=CONFIRM_START_MAX_DAYS):
        return None
    return start


def may_move(current, to, actor):
    return REQUEST_TRANSITIONS.get(current, {}).get(to) == actor


def move(req, to, actor, start=None, now=None):
    """Move `req` to `to` as `actor`; None when the table does not allow it. Stamps the moment."""
    if not may_move(req.status, to, actor):
        return None
    now = now or timezone.now()
    req.status = to
    fields = ['status']
    if to == 'requested':
        req.email_confirmed_at = now
        fields.append('email_confirmed_at')
    else:
        req.decided_at = now
        fields.append('decided_at')
    if to == 'confirmed':
        req.start = start
        fields.append('start')
    req.save(update_fields=fields)
    return req


# --- kept and swept ------------------------------------------------------------------------------

PERSONAL_REQUEST_FIELDS = ('owner_name', 'phone', 'email', 'animal_name', 'reason')


def sweep(now=None):
    """Blank what the directory no longer needs. Runs at every write (there is no scheduler) and
    from `manage.py vetdir_sweep`. Returns (requests blanked, listings deleted)."""
    from .models import Listing, VisitRequest
    now = now or timezone.now()
    today = clinic_today(now)
    keep = timedelta(days=REQUEST_KEEP_DAYS)
    live = VisitRequest.objects.filter(blanked_at__isnull=True)
    ids = set(live.filter(status='pending_email',
                          created_at__lt=now - timedelta(days=REQUEST_UNCONFIRMED_DAYS))
              .values_list('pk', flat=True))
    ids |= set(live.filter(status__in=TERMINAL_STATUSES, decided_at__lt=now - keep)
               .values_list('pk', flat=True))
    for row in live.filter(status__in=('requested', 'confirmed'), day__lt=today - keep):
        last = row.day
        if row.start is not None:
            last = max(last, timezone.localtime(row.start, CLINIC_TZ).date())
        if last < today - keep:
            ids.add(row.pk)
    blank = {f: '' for f in PERSONAL_REQUEST_FIELDS}
    blanked = VisitRequest.objects.filter(pk__in=ids).update(blanked_at=now, **blank) if ids else 0
    # A listing nobody confirmed was never public, and its address may be somebody else's.
    deleted, _ = Listing.objects.filter(
        status='pending', created_at__lt=now - timedelta(days=LISTING_PENDING_DAYS)).delete()
    return blanked, deleted
