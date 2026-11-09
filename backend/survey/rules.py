"""survey — the rules of the questionnaire endpoints, in one module (root CLAUDE.md, boundary 2).

The questionnaire itself — which questions exist, their wording and order, the heading that says
the goal is preparation of research, the three acknowledgements ticked before the first question
and the 18+ gate — lives in the client (the medapp repository's `src/lib/survey/`). This server
knows three things about a survey: its slug, the version of its definition that is current, and
the version of the consent text that is current, with that text pinned here as the evidence of
what was agreed to. Everything `clean_answers` checks is about the SHAPE of a submission, never
its meaning: a key that looks like a question id, a value that is one of five plain JSON kinds, a
total that fits in a row. Which ids exist is the client's business, and the analysis side filters
by the ids it knows.

One way back to one's own sheet, opt-in and a one-way hash on this side: a key this server
generates and hands back once (`new_key` / `hash_key`; the person keeps it, or its QR, and
`POST /api/survey/withdraw/` with it blanks the sheet). A sheet without one cannot be found again
— which is the point and the price of anonymity. Until SURVEY-R3 (2026-11-07, version 2) there
was a second way, an e-mail kept as an HMAC: dropped, because a hashed address is pseudonymous
rather than anonymous (whoever holds the table and the salt can test a candidate) and a
withdrawal by mail showed the controller the address — the key does the same job without either.

Every constant here is MIRRORED in the medapp repository's `src/lib/survey/api.ts` — a separate
repository, so nothing can import across. Change one, change the other, and keep the comment
that says so. `tests.py MirroredConstantsTests` pins this side.
"""
import hashlib
import json
import re
import secrets

from django.utils import timezone

# The surveys this server accepts, by slug, each with the version of its definition the client
# must be running. A sheet from an older build is refused with 400 keyed `version` and the
# client tells the person to reload — storing answers against a question list that has since
# changed would be a dataset nobody can analyse. The title is the heading the client shows and
# names the goal: preparation of a student observational study (version 2, SURVEY-R3: the word
# was "experiment" until 2026-11-07; the first consent statement changed with it, under the same
# date, because no sheet had been received — version 2 is what tells the two apart). Version 3
# (SURVEY-R4, 2026-11-09): the questions on recency, frequency, microdosing, dose pattern and
# interval name "klasycznych psychodelików" themselves, because a respondent could not tell whether
# they asked about classic psychedelics or the other substances of the question before; ids and the
# wire contract are unchanged, the version tells sheets answered under the old wording apart.
# MIRRORED in the medapp repository's `src/lib/survey/api.ts` as SURVEYS — change one, change the other.
SURVEYS = {
    'psychodeliki-retro-2026': {
        'version': 3,
        'title': 'Psychodeliki – ankieta retrospektywna w ramach przygotowań do studenckiego badania obserwacyjnego',
    },
}

# The consent text, as the client shows it: three acknowledgements, each a REQUIRED checkbox
# before the first question. The DATE is the version. A sheet carries the version it was ticked
# under (`SurveyResponse.consent_version`), so what was agreed to stays on record after the
# wording changes; a sheet ticked under an older text is refused with 400 keyed
# `consent_version` and the client tells the person to reload. Change a word here → bump the
# date here AND in the client, or every sheet answers 400.
# MIRRORED in `src/lib/survey/api.ts` (medapp) as CONSENT_VERSION — change one, change the other.
CONSENT_VERSION = '2026-11-07'
# MIRRORED in `src/lib/survey/api.ts` (medapp) as CONSENT_STATEMENTS — byte-identical, like
# consent/rules.WISH_LABELS ↔ lib/consent.ts.
CONSENT_STATEMENTS = (
    'Chcę podzielić się moim doświadczeniem w celach przygotowań do studenckiego badania obserwacyjnego.',
    'Projekt nie jest powiązany z żadną uczelnią.',
    'Administrator danych: Piotr Putyło, admin@fuw.lol.',
)
# The controller named in the third acknowledgement (LEGAL.md §9b); the mailbox is the one a
# human reads (settings.FUWLOL_CONTACT_EMAIL in production).
CONTROLLER = 'Piotr Putyło'
CONTROLLER_EMAIL = 'admin@fuw.lol'

# `answers` is an object of at most this many question ids.
# MIRRORED in `src/lib/survey/api.ts` (medapp) as MAX_KEYS — change one, change the other.
MAX_KEYS = 200
# A question id: lowercase ASCII, a letter first, at most 40 characters. `fullmatch` — a
# trailing newline is not a match.
# MIRRORED in `src/lib/survey/api.ts` (medapp) as KEY_RE — change one, change the other.
KEY_RE = re.compile(r'^[a-z][a-z0-9_]{0,39}$')
# A free-text answer, measured after stripping.
# MIRRORED in `src/lib/survey/api.ts` (medapp) as MAX_STRING — change one, change the other.
MAX_STRING = 300
# The one free text allowed to be long: the closing remarks about the questionnaire itself
# (SURVEY-R4, 2026-11-09, the study team's decision). Every other text stays at MAX_STRING.
# MIRRORED in `src/lib/survey/api.ts` (medapp) as REMARKS_KEY / MAX_REMARKS — change one, change the other.
REMARKS_KEY = 'survey_remarks'
MAX_REMARKS = 1_000_000
# A multiple-choice answer: a list of at most MAX_LIST short strings of at most MAX_LIST_ITEM
# characters each (option ids, or the "other" text).
# MIRRORED in `src/lib/survey/api.ts` (medapp) as MAX_LIST — change one, change the other.
MAX_LIST = 50
# MIRRORED in `src/lib/survey/api.ts` (medapp) as MAX_LIST_ITEM — change one, change the other.
MAX_LIST_ITEM = 200
# An integer answer (a scale, a count, a year): |value| at most this.
# MIRRORED in `src/lib/survey/api.ts` (medapp) as MAX_INT — change one, change the other.
MAX_INT = 1_000_000
# The whole `answers` object serialised as UTF-8 JSON — bytes, not characters.
# MIRRORED in `src/lib/survey/api.ts` (medapp) as MAX_ANSWERS_BYTES — change one, change the other.
# 4 MiB: MAX_REMARKS characters at four UTF-8 bytes each, plus every other answer.
MAX_ANSWERS_BYTES = 4_194_304
# `duration_s`: how long the questionnaire took, in seconds; a day is the ceiling. Outside it
# the value is dropped to null, never refused — a timer is not worth losing a sheet over.
# MIRRORED in `src/lib/survey/api.ts` (medapp) as MAX_DURATION_S — change one, change the other.
MAX_DURATION_S = 86400
# The key handed back once: `secrets.token_urlsafe(32)` is 43 characters; the lookup accepts a
# little slack for a pasted one and nothing like a payload.
# MIRRORED in `src/lib/survey/api.ts` (medapp) as MAX_KEY — change one, change the other.
MAX_KEY = 128
# `pl`, `en`, `uk`, and a regional pair like `pt-BR`. Anything else is dropped, not refused —
# the same shape as feedback/serializers.py, matched with `fullmatch`.
LOCALE_RE = re.compile(r'^[a-z]{2}(-[A-Za-z]{2})?$')
# Control characters other than \n and \t have no business in a typed answer, and they are the
# usual carrier of terminal and spreadsheet trouble in an export; a string holding one is refused.
CONTROL_RE = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')

ANSWERS_NOT_AN_OBJECT = 'Odpowiedzi muszą być obiektem JSON: identyfikator pytania → odpowiedź.'
ANSWERS_EMPTY = 'Brak odpowiedzi.'

def _string_problem(key, text, limit):
    """None when `text` (already stripped) is an acceptable string of at most `limit` characters."""
    if len(text) > limit:
        return f'Odpowiedź „{key}” jest za długa (najwyżej {limit} znaków).'
    if CONTROL_RE.search(text):
        return f'Odpowiedź „{key}” zawiera niedozwolone znaki sterujące.'
    return None


def clean_answers(answers):
    """Return `(clean, None)` — the normalised copy to store (strings stripped, nothing else
    touched) — or `(None, <Polish sentence>)` naming the first thing wrong with the answers.

    Only the shape is checked; see the module docstring. `key` is echoed in a sentence only
    after it matched `KEY_RE` (lowercase ASCII), except in the bad-key sentence, where it is
    cut short.
    """
    if not isinstance(answers, dict):
        return None, ANSWERS_NOT_AN_OBJECT
    if not answers:
        return None, ANSWERS_EMPTY
    if len(answers) > MAX_KEYS:
        return None, f'Za dużo odpowiedzi (najwyżej {MAX_KEYS}).'
    clean = {}
    for key, value in answers.items():
        if not isinstance(key, str) or not KEY_RE.fullmatch(key):
            return None, f'Nieprawidłowy identyfikator pytania: {repr(key)[:48]}.'
        # bool before int: in Python a bool IS an int, and `true` must stay a boolean.
        if value is None or isinstance(value, bool):
            clean[key] = value
        elif isinstance(value, int):
            if abs(value) > MAX_INT:
                return None, f'Odpowiedź „{key}” jest poza zakresem liczb (±{MAX_INT}).'
            clean[key] = value
        elif isinstance(value, str):
            text = value.strip()
            problem = _string_problem(key, text, MAX_REMARKS if key == REMARKS_KEY else MAX_STRING)
            if problem:
                return None, problem
            clean[key] = text
        elif isinstance(value, list):
            if len(value) > MAX_LIST:
                return None, f'Odpowiedź „{key}” ma za dużo pozycji (najwyżej {MAX_LIST}).'
            items = []
            for item in value:
                if not isinstance(item, str):
                    return None, f'Odpowiedź „{key}” może być listą tylko krótkich tekstów.'
                text = item.strip()
                problem = _string_problem(key, text, MAX_LIST_ITEM)
                if problem:
                    return None, problem
                items.append(text)
            clean[key] = items
        else:
            # A float, a nested object, anything else: not one of the five kinds.
            return None, f'Odpowiedź „{key}” ma nieobsługiwany typ.'
    if len(json.dumps(clean, ensure_ascii=False).encode('utf-8')) > MAX_ANSWERS_BYTES:
        return None, f'Odpowiedzi są za duże (najwyżej {MAX_ANSWERS_BYTES} bajtów).'
    return clean, None


def new_key():
    """The one-time key handed back to a person who asked for one: 256 bits, URL-safe."""
    return secrets.token_urlsafe(32)


def hash_key(key):
    """SHA-256 of the key, which is what the row keeps (kolo_ai keeps its session keys the same
    way). The key is random and long, so no salt is needed; the plain key exists only in the
    person's hands."""
    return hashlib.sha256(key.encode()).hexdigest()


def find_by_key(key):
    """The sheet behind a pasted key, or None — for an unknown key, a withdrawn sheet is still
    found (the holder may call withdraw twice)."""
    from .models import SurveyResponse
    if not isinstance(key, str):
        return None
    key = key.strip()
    if not key or len(key) > MAX_KEY:
        return None
    return SurveyResponse.objects.filter(key_hash=hash_key(key)).first()


def withdraw(row):
    """Blank the answers, mark the sheet withdrawn with today's DATE, keep
    the key hash so a second call finds the same row and does nothing. Returns True when the
    row changed. The row itself stays (root CLAUDE.md rule 6) — empty, so the count of sheets
    ever received is still right and the id is not reused."""
    if row.status == 'withdrawn':
        return False
    row.answers = {}
    row.status = 'withdrawn'
    row.withdrawn_on = timezone.localdate()
    row.save(update_fields=['answers', 'status', 'withdrawn_on'])
    return True
