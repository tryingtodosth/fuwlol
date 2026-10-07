"""The rules every WUM endpoint asks, in one module (root `CLAUDE.md`: a rule that more than one
endpoint needs lives in one place, and the endpoints ask it).

Two things here are MIRRORED by hand in the medapp repository and pinned by tests on both sides:
the two consent-text versions and the forbidden-key list. Nothing can import across the repos.
"""
import json
import re
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone

from .models import (HOURS_MAX_ENTRIES, MAX_PUBLICATION_BYTES, MAX_TEMPLATE_BYTES, PAYLOAD_VERSION,
                     PRACTICE_NOTE_MAX, SLOT_MINUTES_MAX, SLOT_MINUTES_MIN, TEMPLATE_DOCUMENT_VERSION,
                     TEMPLATE_KEYS, TEMPLATE_REFUSED_KEYS, VISIT_HOLDING_STATUSES, VISIT_HORIZON_DAYS,
                     Practice, PracticeNote, Publication, Visit, WumProfile)

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


# --- the practice round -----------------------------------------------------------------------

HHMM_RE = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
# The practice's wall clock. Hours are written in it and slots are cut in it, whatever zone the
# patient's phone is in — the same reason the app's booking module has `HOSPITAL_TZ`.
PRACTICE_TZ = timezone.get_default_timezone()


def is_practitioner(user):
    """A WUM account that has opened a practice. Anonymous / None → False. Never raises."""
    if not is_wum_account(user):
        return False
    return Practice.objects.filter(owner=user).exists()


def _minutes(hhmm):
    h, m = hhmm.split(':')
    return int(h) * 60 + int(m)


def hours_problems(hours):
    """Why a weekly-hours list may not be saved, as Polish sentences; empty means it may. A list
    of {weekday, open, close} in the practice's wall clock; several windows a day are fine as
    long as they do not overlap."""
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
        wd = win.get('weekday')
        o, c = win.get('open'), win.get('close')
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


def slot_minutes_problems(n):
    if not isinstance(n, int) or isinstance(n, bool) or not SLOT_MINUTES_MIN <= n <= SLOT_MINUTES_MAX or n % 5:
        return [f'Długość wizyty: {SLOT_MINUTES_MIN}–{SLOT_MINUTES_MAX} minut, co 5.']
    return []


def note_problems(body):
    if not isinstance(body, str) or not body.strip():
        return ['Notatka nie może być pusta.']
    if len(body) > PRACTICE_NOTE_MAX:
        return [f'Notatka jest za długa (najwyżej {PRACTICE_NOTE_MAX} znaków).']
    return []


def _holding(practice, start, end, exclude_pk=None):
    qs = Visit.objects.filter(practice=practice, status__in=VISIT_HOLDING_STATUSES,
                              start__lt=end, end__gt=start)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs


def windows_for(practice, day):
    """The practice's open windows on a local calendar `day`, as aware (start, end) pairs."""
    out = []
    for win in practice.hours or []:
        if win.get('weekday') != day.weekday():
            continue
        o = datetime.combine(day, datetime.strptime(win['open'], '%H:%M').time())
        c = datetime.combine(day, datetime.strptime(win['close'], '%H:%M').time())
        out.append((timezone.make_aware(o, PRACTICE_TZ), timezone.make_aware(c, PRACTICE_TZ)))
    return out


def open_slots(practice, from_day, days, now=None):
    """Open slots from `from_day` for `days` days: the hours cut into `slot_minutes`, minus the
    past and minus anything that holds a slot. `days` is clamped to 1..VISIT_HORIZON_DAYS, and
    nothing beyond `now + VISIT_HORIZON_DAYS` is offered."""
    now = now or timezone.now()
    days = max(1, min(int(days), VISIT_HORIZON_DAYS))
    horizon = now + timedelta(days=VISIT_HORIZON_DAYS)
    first = timezone.make_aware(datetime.combine(from_day, datetime.min.time()), PRACTICE_TZ)
    last = first + timedelta(days=days)
    held = list(_holding(practice, first, last).values_list('start', 'end'))
    step = timedelta(minutes=practice.slot_minutes)
    out = []
    for i in range(days):
        day = from_day + timedelta(days=i)
        for (o, c) in windows_for(practice, day):
            t = o
            while t + step <= c:
                s, e = t, t + step
                t = e
                if s <= now or s > horizon:
                    continue
                if any(hs < e and he > s for (hs, he) in held):
                    continue
                out.append((s, e))
    return out


def request_problems(practice, start, now=None):
    """Why a PATIENT may not ask for a visit at `start`: the slot must be one `open_slots` would
    offer — in the future, within the horizon, inside a window, on the slot grid, and free. Polish
    sentences; empty means it may."""
    now = now or timezone.now()
    if not practice.listed:
        return ['Ten gabinet nie przyjmuje teraz zgłoszeń.']
    if start <= now:
        return ['Ten termin już minął.']
    if start > now + timedelta(days=VISIT_HORIZON_DAYS):
        return [f'Można się umawiać najwyżej {VISIT_HORIZON_DAYS} dni naprzód.']
    local = timezone.localtime(start, PRACTICE_TZ)
    step = timedelta(minutes=practice.slot_minutes)
    end = start + step
    on_grid = False
    for (o, c) in windows_for(practice, local.date()):
        if o <= start and end <= c and int((start - o).total_seconds()) % int(step.total_seconds()) == 0:
            on_grid = True
            break
    if not on_grid:
        return ['Ten termin jest poza godzinami gabinetu.']
    if _holding(practice, start, end).exists():
        return ['Ten termin jest już zajęty.']
    return []


@transaction.atomic
def request_visit(practice, patient, start, reason, now=None):
    """A patient asks for a slot. Returns `(visit, problems)`: the row and no problems, or no row
    and the sentences. Serialised on the practice's rows so two phones asking for the same slot
    at the same moment get one visit and one refusal."""
    list(Visit.objects.select_for_update().filter(practice=practice, status__in=VISIT_HOLDING_STATUSES)
         .values_list('pk', flat=True))
    problems = request_problems(practice, start, now)
    if problems:
        return None, problems
    row = Visit.objects.create(practice=practice, patient=patient, start=start,
                               end=start + timedelta(minutes=practice.slot_minutes),
                               reason=(reason or '').strip(), created_by='patient')
    return row, []


@transaction.atomic
def practitioner_visit(practice, patient, start, end, note, now=None):
    """The practitioner writes in their own diary: a block (`patient` None) or a visit for a
    patient they booked by hand. Confirmed at once; may be outside the hours (a practitioner
    knows their own diary); may not overlap anything that holds a slot."""
    now = now or timezone.now()
    list(Visit.objects.select_for_update().filter(practice=practice, status__in=VISIT_HOLDING_STATUSES)
         .values_list('pk', flat=True))
    if end <= start:
        return None, ['Koniec musi być po początku.']
    if end - start > timedelta(hours=12):
        return None, ['Jeden wpis może trwać najwyżej 12 godzin.']
    if _holding(practice, start, end).exists():
        return None, ['Ten czas nachodzi na inny wpis w terminarzu.']
    row = Visit.objects.create(practice=practice, patient=patient, start=start, end=end,
                               status='confirmed', note=(note or '').strip(),
                               created_by='practitioner', decided_at=now)
    return row, []


# Who may move a visit where. The practitioner decides on a request and closes a confirmed visit;
# the patient may only cancel their own, and only one that has not ended. Anything else is refused
# and the view answers 400 keyed `status` — or 404 when the visit is not theirs at all.
PRACTITIONER_TRANSITIONS = {
    'requested': ('confirmed', 'declined'),
    'confirmed': ('cancelled', 'completed', 'no_show'),
}
PATIENT_TRANSITIONS = {
    'requested': ('cancelled',),
    'confirmed': ('cancelled',),
}


def transition(visit, to, actor, note=None, now=None):
    """Move `visit` to `to` as `actor` ('practitioner' | 'patient'). Returns the row, or None when
    the move is not allowed from this status for this actor. Stamps `decided_at` and keeps the
    practitioner's `note` when given."""
    now = now or timezone.now()
    allowed = PRACTITIONER_TRANSITIONS if actor == 'practitioner' else PATIENT_TRANSITIONS
    if to not in allowed.get(visit.status, ()):
        return None
    if actor == 'patient' and visit.end <= now:
        return None
    if actor == 'practitioner' and to in ('completed', 'no_show') and visit.start > now:
        return None
    visit.status = to
    visit.decided_at = now
    fields = ['status', 'decided_at', 'updated_at']
    if note is not None and actor == 'practitioner':
        visit.note = note.strip()
        fields.append('note')
    visit.save(update_fields=fields)
    return visit


def practice_patients(practice):
    """The people who have or had a visit here: one row per patient with the count and the last
    start, most recent first. A block has no patient and is not a person."""
    return (Visit.objects.filter(practice=practice, patient__isnull=False)
            .values('patient__username', 'patient__wum_profile__first_name', 'patient__wum_profile__surname',
                    'patient__wum_profile__contact_email', 'patient__wum_profile__contact_phone')
            .annotate(visits=Count('id'), last_start=Max('start'))
            .order_by('-last_start'))


def share_note(note):
    """One way: a note the patient could read stays readable."""
    if note.shared_with_patient:
        return note
    note.shared_with_patient = True
    note.shared_at = timezone.now()
    note.save(update_fields=['shared_with_patient', 'shared_at'])
    return note


def notes_for_patient(user):
    """What a PATIENT may read: the notes practitioners chose to share with them, newest first."""
    return (PracticeNote.objects.filter(patient=user, shared_with_patient=True)
            .select_related('practice', 'visit'))
