"""The rules every WUM endpoint asks, in one module (root `CLAUDE.md`: a rule that more than one
endpoint needs lives in one place, and the endpoints ask it).

Two things here are MIRRORED by hand in the medapp repository and pinned by tests on both sides:
the two consent-text versions and the forbidden-key list. Nothing can import across the repos.
"""
import json
import re

from django.db import transaction
from django.utils import timezone

from .models import (MAX_PUBLICATION_BYTES, MAX_TEMPLATE_BYTES, PAYLOAD_VERSION,
                     TEMPLATE_DOCUMENT_VERSION, TEMPLATE_KEYS, TEMPLATE_REFUSED_KEYS, Publication,
                     WumProfile)

# Stamped on every account (`WumProfile.agreed_text_version`) and every publication
# (`Publication.consent_text_version`). BUMP THE DATE when the wording of the sign-up disclaimers
# or of the publish statement changes, in ANY language — and bump the same constant in MedApp's
# `src/lib/api/wum.ts` (ACCOUNT_TEXT_VERSION, PUBLISH_TEXT_VERSION), or the app answers 409 on
# every sign-up until it is rebuilt. That 409 is the point: a person must never agree to a text
# the app no longer shows.
WUM_ACCOUNT_TEXT_VERSION = '2026-10-06'
WUM_PUBLISH_TEXT_VERSION = '2026-10-06'

# Keys a published payload may not contain ANYWHERE, however deep. The app's projection never
# emits them (it builds the payload field by field, so a new `Persona` field cannot leak through by
# default); this list is the server's second look, and a hit is a bug on the sending side, refused
# with 400 keyed `payload`. MIRRORED in MedApp's `src/lib/privacy/project.ts` as
# NEVER_PUBLISHED_KEYS. NOTE: a bare `name` is deliberately NOT here — medicines carry one.
FORBIDDEN_PAYLOAD_KEYS = frozenset({
    'id', 'subjectId', 'displayName', 'legalName', 'firstName', 'surname', 'pronouns', 'gender',
    'identity', 'country', 'locale', 'guardian', 'carer', 'contacts', 'contact', 'phone', 'email',
    'careTeam', 'location', 'documents', 'doseEvents', 'position', 'createdAt', 'updatedAt', 'at',
    'onsetDate', 'date', 'startedOn',
})

# `30–39`: a ten-year band with an en dash, as `ageBand()` in the app writes it. A payload with a
# bare age or a date of birth in this field is refused.
AGE_BAND_RE = re.compile(r'^\d+–\d+$')
# The app's own export version string, e.g. `medapp.export/2`.
VERSION_RE = re.compile(r'^[a-z]+\.[a-z]+/\d+$')


def is_wum_account(user):
    """A signed-in user with a `WumProfile`. Anonymous / None → False. Never raises."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    return WumProfile.objects.filter(user=user).exists()


def _json_bytes(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))


def _forbidden_key(value, path=''):
    """The first forbidden key found anywhere in `value`, as a dotted path, or None."""
    if isinstance(value, dict):
        for k, v in value.items():
            here = f'{path}.{k}' if path else str(k)
            if k in FORBIDDEN_PAYLOAD_KEYS:
                return here
            found = _forbidden_key(v, here)
            if found:
                return found
    elif isinstance(value, list):
        for i, v in enumerate(value):
            found = _forbidden_key(v, f'{path}[{i}]')
            if found:
                return found
    return None


def payload_problems(payload, declared_version):
    """Why a payload may not be published, as Polish sentences; empty means it may."""
    problems = []
    if not isinstance(payload, dict):
        return ['Rekord musi być obiektem JSON.']
    if _json_bytes(payload) > MAX_PUBLICATION_BYTES:
        problems.append(f'Rekord jest za duży (najwyżej {MAX_PUBLICATION_BYTES // 1024} kB).')
    if payload.get('version') != declared_version:
        problems.append('Wersja rekordu w treści nie zgadza się z zadeklarowaną.')
    band = payload.get('ageBand')
    if not isinstance(band, str) or not AGE_BAND_RE.match(band):
        problems.append('Przedział wieku musi mieć postać „30–39”.')
    found = _forbidden_key(payload)
    if found:
        problems.append(f'Rekord zawiera pole, którego nie wolno publikować: {found}.')
    return problems


def template_problems(document):
    """Why a document may not be a template; empty means it may. Shape only — the app re-parses
    every value on import and drops what it does not understand, so this is the coarse sieve."""
    if not isinstance(document, dict):
        return ['Szablon musi być obiektem JSON.']
    problems = []
    if _json_bytes(document) > MAX_TEMPLATE_BYTES:
        problems.append(f'Szablon jest za duży (najwyżej {MAX_TEMPLATE_BYTES // 1024} kB).')
    if document.get('schemaVersion') != TEMPLATE_DOCUMENT_VERSION:
        problems.append(f'Szablon musi mieć schemaVersion „{TEMPLATE_DOCUMENT_VERSION}”.')
    refused = [k for k in TEMPLATE_REFUSED_KEYS if k in document]
    if refused:
        problems.append('Szablon nie może zawierać zgód ani dziennika dostępu: ' + ', '.join(refused) + '.')
    unknown = [k for k in document if k not in TEMPLATE_KEYS and k not in TEMPLATE_REFUSED_KEYS]
    if unknown:
        problems.append('Nieznane pola: ' + ', '.join(sorted(unknown)) + '.')
    patient = document.get('patient')
    if not isinstance(patient, dict):
        problems.append('Brak sekcji „patient”.')
    else:
        if not isinstance(patient.get('name'), str) or not patient['name'].strip():
            problems.append('Pacjent musi mieć imię (patient.name).')
        age = patient.get('age')
        if not isinstance(age, int) or isinstance(age, bool) or not 0 <= age <= 125:
            problems.append('Wiek pacjenta musi być liczbą całkowitą 0–125.')
    for key in ('symptoms', 'checkIns', 'medications', 'doseEvents', 'appointments', 'vitals',
                'careTeam', 'documents'):
        if key in document and (not isinstance(document[key], list)
                                or any(not isinstance(x, dict) for x in document[key])):
            problems.append(f'Sekcja „{key}” musi być listą obiektów.')
    if 'emergency' in document and not isinstance(document['emergency'], dict):
        problems.append('Sekcja „emergency” musi być obiektem.')
    return problems


@transaction.atomic
def publish(user, payload, version, text_version):
    """Create the account's new live publication, superseding any previous one. Returns
    `(row, superseded_public_id_or_None)`. One live publication per account is the rule: the
    public list is a list of PEOPLE's current records, not a history of edits."""
    previous = list(Publication.objects.select_for_update()
                    .filter(account=user, status='published').order_by('-created_at'))
    row = Publication.objects.create(account=user, payload=payload, payload_version=version,
                                     consent_text_version=text_version)
    for old in previous:
        old.status = 'superseded'
        old.superseded_by = row
        old.save(update_fields=['status', 'superseded_by'])
    return row, (previous[0].public_id if previous else None)


def withdraw(publication, user):
    """Withdraw the person's own live publication, at once and with no review (art. 7 ust. 3
    RODO). Returns the row, or None when it is not theirs or not live — the view answers 404 to
    both, so a stranger cannot tell which (root `CLAUDE.md` rule 5)."""
    if publication.account_id != user.id or publication.status != 'published':
        return None
    publication.status = 'withdrawn'
    publication.withdrawn_at = timezone.now()
    publication.save(update_fields=['status', 'withdrawn_at'])
    return publication
