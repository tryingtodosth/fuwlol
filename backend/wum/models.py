"""fuw.lol — what the side app (MedApp, deployed here as **WUM** at `fuw.lol/fum`) keeps on this
server, now that it keeps anything at all.

Until 2026-10 the app stored nothing here: everything a visitor did stayed in their browser and
the one call it made was `POST /api/feedback/`. Three tables arrive with this app, and the line
between them and the patient's health data is the whole design:

**`WumProfile`** — a WUM account is a Django `User` with this 1:1 row. The row is the mark: the
archive's login, moderation and chat ask `rules.is_wum_account()` to tell the two populations
apart, and a WUM account gets none of the archive's powers. `User.email` stays BLANK for these
accounts (the contact address lives here, on the profile), so the archive's e-mail uniqueness
rule never collides with a WUM sign-up and a WUM address never becomes an archive login.

**`Template`** — a fictional example patient (the write side of the app's own
`medapp.export/2` document) that the app lists and lets a person "start from". Authored in the
app, exported, pasted into the admin or POSTed by staff; never a real person's record. This is
what makes new demo data a row instead of an image rebuild.

**`Publication`** — the one piece of health-shaped data this server holds: a record a person
chose to publish, already ANONYMISED BY THE APP before it left the phone (`projectForPublication`
in the medapp repository builds it field by field; `rules.payload_problems` here is defence in
depth, not the boundary). The row keeps the link to the account for exactly one reason: so the
person can withdraw it with one tap. The public read (`PublicationPublicSerializer`) exposes an
opaque uuid, the payload and the month — never the account, never the username.

**`Practice`, `Visit`, `PracticeNote`** (2026-10, the practice round) — the one place this
server holds something a person SAID about a body, and it is said knowingly and to somebody: a
practitioner (a physiotherapist, for now) opens a practice with weekly hours; a patient with a WUM
account asks for a visit into those hours and types a reason in their own words; the
practitioner confirms, declines, completes, and keeps append-only notes about the patient, each
either private to the practice or shared with the patient. The practice's diary and notes are
THE PRACTITIONER'S record (the way the clinic's register is the clinic's in the app's vet half),
kept under the practitioner's account; a visit is the one row both can see. Nothing here reads
the patient's health stores: the app does not send them, and `rules.VISIT_*` caps and
`note_problems` keep what IS sent to a sentence or a page of text. The sign-up disclaimer every
account agreed to still stands — a prototype, nothing clinically reviewed, no real health data.

**What is NOT here**: no symptom map, no medicines, no emergency card, no sync. Health data stays
on the device under the patient's retention mode, as before. No IP hash either: an account is
already an identity, and the feedback table's reason for hashing one (thirty anonymous notes
from one laptop) does not apply.

Lifecycle rules, same as `consent/`: one `status` field, never two booleans; a withdrawn or
superseded publication is KEPT, not deleted — the row is the evidence of what was agreed to and
when (`consent_text_version`), and a change of mind writes a new row (root `CLAUDE.md` rule 6).
"""
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

# The shape of a published record. MIRRORED in MedApp's `src/lib/privacy/project.ts` as
# PUBLICATION_VERSION — change one, change the other (pinned by tests on both sides). A payload
# that declares another version is refused with 409, because the app that sent it and the app
# that will render it disagree about what the fields mean.
PAYLOAD_VERSION = 'wum.publication/1'

# A template is the app's own export document minus everything that is not an example patient.
# MIRRORED in MedApp's `src/lib/templates/types.ts` (TEMPLATE_DOCUMENT_VERSION, TEMPLATE_KEYS).
TEMPLATE_DOCUMENT_VERSION = 'medapp.export/2'
TEMPLATE_KEYS = ('schemaVersion', 'exportedAt', 'patient', 'symptoms', 'checkIns', 'medications',
                 'doseEvents', 'appointments', 'vitals', 'emergency', 'careTeam', 'documents')
# Export keys that are a PERSON's consent state or audit trail and have no place in an example.
# Their presence is refused outright rather than stripped: a document that carries them was not
# made for this table.
TEMPLATE_REFUSED_KEYS = ('grants', 'accessLog', 'accessRequests', 'preferences',
                         'emergencyAccessPolicy', 'bookingRequests')

# Size caps on the raw JSON, in bytes. A projected record of one person is a few kilobytes; an
# example patient with a year of dose events is tens. Both MIRRORED in MedApp
# (`src/lib/api/wum.ts` MAX_PUBLICATION_BYTES, `src/lib/templates/parse.ts` MAX_TEMPLATE_BYTES).
MAX_PUBLICATION_BYTES = 128 * 1024
MAX_TEMPLATE_BYTES = 256 * 1024

NAME_MAX = 80
CONTACT_MAX = 120
PHONE_MAX = 40

TEMPLATE_STATUS_CHOICES = [
    ('draft', 'Szkic'),
    ('published', 'Opublikowany'),
    ('retired', 'Wycofany'),
]
PUBLICATION_STATUS_CHOICES = [
    ('published', 'Opublikowana'),
    ('withdrawn', 'Wycofana przez osobę'),
    ('superseded', 'Zastąpiona nowszą'),
]
# The one state in which a row is somebody's CURRENT publication. Everything else is history.
LIVE_STATUSES = ('published',)

# --- the practice round -----------------------------------------------------------------------

# What a practitioner may call themselves. Closed, so a screen can translate it; `other` is the
# escape hatch and the app shows it as such. MIRRORED in MedApp `src/lib/api/wum.ts` PROFESSIONS.
PROFESSION_CHOICES = [
    ('physiotherapist', 'Fizjoterapeuta / fizjoterapeutka'),
    ('dietitian', 'Dietetyk / dietetyczka'),
    ('psychologist', 'Psycholog / psycholożka'),
    ('nurse', 'Pielęgniarz / pielęgniarka'),
    ('other', 'Inny zawód'),
]
PROFESSIONS = tuple(k for k, _ in PROFESSION_CHOICES)

VISIT_STATUS_CHOICES = [
    ('requested', 'Zgłoszona'),
    ('confirmed', 'Potwierdzona'),
    ('declined', 'Odrzucona'),
    ('cancelled', 'Odwołana'),
    ('completed', 'Odbyta'),
    ('no_show', 'Nieobecność'),
]
# Statuses that still hold the slot: they block an overlapping visit and are drawn in the diary.
VISIT_HOLDING_STATUSES = ('requested', 'confirmed')
VISIT_CREATED_BY_CHOICES = [('patient', 'pacjent'), ('practitioner', 'gabinet')]

DISPLAY_NAME_MAX = 80
ABOUT_MAX = 600
# The patient's own words about why they are coming — a sentence, not a history. MIRRORED in
# MedApp `src/lib/api/wum.ts` (VISIT_REASON_MAX, VISIT_NOTE_MAX, PRACTICE_NOTE_MAX).
VISIT_REASON_MAX = 300
VISIT_NOTE_MAX = 300
PRACTICE_NOTE_MAX = 4000
# How far ahead a patient may ask for a visit, and how many days of slots one call may list.
VISIT_HORIZON_DAYS = 60
SLOT_MINUTES_MIN, SLOT_MINUTES_MAX = 15, 180
HOURS_MAX_ENTRIES = 14


class WumProfile(models.Model):
    """The mark that makes a `User` a WUM account, plus the four optional fields the person may
    fill in about themselves. All four are OPTIONAL and none is ever published: the publication
    payload is built on the phone from the health stores, and this row is not among them."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name='wum_profile',
                                on_delete=models.CASCADE)
    first_name = models.CharField(max_length=NAME_MAX, blank=True)
    surname = models.CharField(max_length=NAME_MAX, blank=True)
    contact_email = models.EmailField(max_length=CONTACT_MAX, blank=True)
    contact_phone = models.CharField(max_length=PHONE_MAX, blank=True)
    # WHICH sign-up text was agreed to (rules.WUM_ACCOUNT_TEXT_VERSION at the time). A consent
    # that cannot say what it consented to is not evidence of anything.
    agreed_text_version = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'konto WUM'
        verbose_name_plural = 'konta WUM'

    def __str__(self):
        return f'WUM: {self.user.username}'


class Template(models.Model):
    """One example patient. `document` is the app's export document (see TEMPLATE_KEYS) and is
    validated by `rules.template_problems` on every write path — the API and the admin form."""
    slug = models.SlugField(max_length=60, unique=True)
    title = models.CharField(max_length=120)
    # The language the example was written in (its notes, medicine reasons, appointment prep).
    locale = models.CharField(max_length=8)
    summary = models.CharField(max_length=300, blank=True)
    document = models.JSONField()
    document_version = models.CharField(max_length=20, default=TEMPLATE_DOCUMENT_VERSION)
    status = models.CharField(max_length=10, choices=TEMPLATE_STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   related_name='wum_templates', on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title']
        verbose_name = 'szablon pacjenta'
        verbose_name_plural = 'szablony pacjentów'

    def __str__(self):
        return f'{self.title} ({self.slug}, {self.get_status_display()})'


class Publication(models.Model):
    """One published, anonymised record. See the module docstring for what it is and is not."""
    # The ONLY identifier that ever leaves this server. Not the pk: a sequential id would let a
    # reader count accounts and guess at neighbours.
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    # PROTECT, not CASCADE: an account is deactivated, never deleted, while it has publications —
    # deleting the user would delete the evidence of what they agreed to.
    account = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='wum_publications',
                                on_delete=models.PROTECT)
    payload = models.JSONField()
    payload_version = models.CharField(max_length=30)
    consent_text_version = models.CharField(max_length=20)
    status = models.CharField(max_length=12, choices=PUBLICATION_STATUS_CHOICES, default='published')
    created_at = models.DateTimeField(auto_now_add=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    superseded_by = models.ForeignKey('self', null=True, blank=True, related_name='+',
                                      on_delete=models.SET_NULL)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'publikacja'
        verbose_name_plural = 'publikacje'
        indexes = [
            # The two questions asked: "what is live, newest first" and "what does this account have".
            models.Index(fields=['status', '-created_at'], name='wum_pub_status_recent'),
            models.Index(fields=['account', 'status'], name='wum_pub_account_status'),
        ]

    @property
    def published_month(self):
        """`YYYY-MM` in the site's time zone — the only time information a reader gets. A day
        would narrow a record to the people who opened the app that day."""
        return timezone.localtime(self.created_at).strftime('%Y-%m')

    def __str__(self):
        return f'{self.public_id} ({self.get_status_display()})'


class Practice(models.Model):
    """A practitioner's practice: the name patients see, the profession, weekly hours and the slot
    length the hours are cut into. One per account; the row is the mark that makes a WUM account a
    practitioner (`rules.is_practitioner`), the way `WumProfile` is the mark of a WUM account."""
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, related_name='wum_practice',
                                 on_delete=models.PROTECT)
    display_name = models.CharField(max_length=DISPLAY_NAME_MAX)
    profession = models.CharField(max_length=20, choices=PROFESSION_CHOICES)
    about = models.CharField(max_length=ABOUT_MAX, blank=True)
    # Shown in the public list patients book from. Off until the practitioner says so: a practice
    # being set up is not yet taking patients.
    listed = models.BooleanField(default=False)
    slot_minutes = models.PositiveSmallIntegerField(default=45)
    # [{"weekday": 0..6 (Monday first), "open": "HH:MM", "close": "HH:MM"}, …] in Europe/Warsaw
    # wall-clock time; validated by `rules.hours_problems` on every write path.
    hours = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_name']
        verbose_name = 'gabinet'
        verbose_name_plural = 'gabinety'

    def __str__(self):
        return f'{self.display_name} ({self.get_profession_display()})'


class Visit(models.Model):
    """One slot in a practice's diary: a patient's visit, or the practitioner's own block (a
    meeting, leave) when `patient` is null. Rows are never deleted — a declined or cancelled visit
    is history, and the diary says so."""
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    practice = models.ForeignKey(Practice, related_name='visits', on_delete=models.PROTECT)
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                related_name='wum_visits', on_delete=models.PROTECT)
    start = models.DateTimeField()
    # Exclusive.
    end = models.DateTimeField()
    status = models.CharField(max_length=10, choices=VISIT_STATUS_CHOICES, default='requested')
    # The patient's own words. Goes to the practitioner and nowhere else.
    reason = models.CharField(max_length=VISIT_REASON_MAX, blank=True)
    # The practitioner's word on the row: a decline reason the patient sees, or a block's label.
    note = models.CharField(max_length=VISIT_NOTE_MAX, blank=True)
    created_by = models.CharField(max_length=12, choices=VISIT_CREATED_BY_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['start', 'id']
        verbose_name = 'wizyta'
        verbose_name_plural = 'wizyty'
        indexes = [
            models.Index(fields=['practice', 'start'], name='wum_visit_practice_start'),
            models.Index(fields=['patient', 'start'], name='wum_visit_patient_start'),
        ]

    @property
    def holds_slot(self):
        return self.status in VISIT_HOLDING_STATUSES

    def __str__(self):
        who = self.patient.username if self.patient_id else '(blokada)'
        return f'{self.practice.display_name} · {who} · {self.start:%Y-%m-%d %H:%M} · {self.get_status_display()}'


class PracticeNote(models.Model):
    """A practitioner's note about a patient. APPEND-ONLY: `save()` on an existing row is refused
    except to share it, and `delete()` always — a correction is a new note that names the one it
    amends (`amends`). Private to the practice unless `shared_with_patient`, and sharing is one way:
    once the patient could read it, pretending otherwise would be a lie in the record."""
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    practice = models.ForeignKey(Practice, related_name='notes', on_delete=models.PROTECT)
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='wum_practice_notes',
                                on_delete=models.PROTECT)
    visit = models.ForeignKey(Visit, null=True, blank=True, related_name='notes',
                              on_delete=models.SET_NULL)
    body = models.TextField()
    shared_with_patient = models.BooleanField(default=False)
    shared_at = models.DateTimeField(null=True, blank=True)
    amends = models.ForeignKey('self', null=True, blank=True, related_name='amended_by',
                               on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    SHARE_FIELDS = frozenset({'shared_with_patient', 'shared_at'})

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'notatka gabinetu'
        verbose_name_plural = 'notatki gabinetu'
        indexes = [
            models.Index(fields=['practice', 'patient', '-created_at'], name='wum_note_practice_patient'),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            fields = set(kwargs.get('update_fields') or ())
            if not fields or not fields <= self.SHARE_FIELDS:
                raise ValueError('PracticeNote is append-only; write a new note that amends this one.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('PracticeNote rows are never deleted.')

    def __str__(self):
        return f'{self.practice.display_name} → {self.patient.username} · {self.created_at:%Y-%m-%d}'
