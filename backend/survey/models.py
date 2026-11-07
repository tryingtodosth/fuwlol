"""fuw.lol — one anonymous answer sheet of a research questionnaire, from the LSD copy of MedApp.

LSD (`fuw.lol/lsd`, the `lsd` container) is a second deployment of MedApp that carries a
retrospective questionnaire about psychedelic use, run as preparation for a student experiment by
a project **not affiliated with any university**; the controller is Piotr Putyło
(`admin@fuw.lol`, `rules.CONTROLLER`). The questionnaire, its heading, the three acknowledgements
and the 18+ gate are the client's; this table is where a finished sheet lands, and the only thing
the server knows about the person is what they chose to answer — plus, if they opted in, one of
two hashed ways for them to find their own sheet again.

**Privacy is the point, and the schema is the mechanism.** What people answer here is health
data and data about an offence — art. 9 and art. 10 RODO — and the client promises anonymity. So
the row has:

- **no `ip_hash`** (feedback/ and board/ keep one; this table must not — even a salted hash
  says "the same device as that other row", which is the one correlation a survey about an
  offence must never offer);
- **no `author` / `user` FK** — the view never reads `request.user`, so a visitor who happens
  to be signed in to the archive in the same browser is not attached to their answers;
- **no user agent**; and
- **no timestamp: `received_on` is a DATE, on purpose.** Every proxy in front of this service
  (Cloudflare, Caddy, nginx, gunicorn) writes an access log with the second a
  `POST /api/survey/` arrived and the address it came from. A `created_at` to the second would
  let anybody holding the database and one of those logs join a row to an address by time
  alone. A date cannot be joined that way, and the day is still enough for "how many came in
  after the lecture". What remains is the `id`, which orders the rows WITHIN a day — accepted,
  and written down in `CLAUDE.md`.

**Two opt-in ways back, both one-way hashes.** The person may leave an e-mail, kept only as
`contact_hash` (HMAC under the salt — `rules.hash_contact`): they write to the controller from
that address and `manage.py survey_withdraw --email` finds the sheet. Or they may ask for a key,
generated here, handed back ONCE in the 201 and kept only as `key_hash`; `POST
/api/survey/withdraw/` with it blanks the sheet. Neither hash is shown in the admin. A sheet
with neither cannot be found again by anybody.

Everything else about the row is the survey's business: which questionnaire (`survey`), which
version of its definition (`version`), which consent text was ticked (`consent_version`), the
interface language, how long it took, and the answers as JSON under the client's question ids.
`rules.py` says what shape they may have.
"""
from django.db import models

# The lifecycle, as ONE field (root CLAUDE.md: never two booleans). `received` is a sheet;
# `withdrawn` is a sheet whose answers were blanked at the person's request (`rules.withdraw`).
STATUS_CHOICES = [
    ('received', 'Przyjęta'),
    ('withdrawn', 'Wycofana'),
]


class SurveyResponse(models.Model):
    # The slug of the questionnaire — a key of `rules.SURVEYS`. Indexed on its own and in the
    # pair below: the export asks "this survey", the admin asks "this survey, since this day".
    survey = models.CharField(max_length=60, db_index=True)
    # The version of the client's survey definition the answers were given against.
    version = models.PositiveSmallIntegerField()
    # The date-version of the consent text (`rules.CONSENT_VERSION`) whose three statements the
    # person ticked. The evidence of what was agreed to, like `WumProfile.agreed_text_version`.
    consent_version = models.CharField(max_length=10)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='received')
    # A DATE too, for the same reason as `received_on`; null until withdrawn.
    withdrawn_on = models.DateField(null=True, blank=True)
    # The interface language the person was reading (`pl`, `en`, …); blank when it did not say.
    locale = models.CharField(max_length=8, blank=True)
    # Seconds from the first screen to the submission, as the client measured it; null when it
    # did not say, or said something impossible (`rules.MAX_DURATION_S`).
    duration_s = models.PositiveIntegerField(null=True, blank=True)
    # `{question_id: answer}` — strings, integers, booleans, nulls and lists of strings only
    # (`rules.clean_answers`). Stored as given, strings stripped; never rendered by anything.
    # `{}` once withdrawn.
    answers = models.JSONField()
    # HMAC of the e-mail the person CHOSE to leave for a later request (`rules.hash_contact`);
    # '' when none — the common case. Never the address.
    contact_hash = models.CharField(max_length=64, blank=True)
    # SHA-256 of the key the person CHOSE to receive (`rules.hash_key`); '' when none. The plain
    # key was returned once and is not here.
    key_hash = models.CharField(max_length=64, blank=True, db_index=True)
    # A DATE, not a datetime — see the module docstring. Deliberately no `created_at`.
    received_on = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ['-id']
        verbose_name = 'odpowiedź ankiety'
        verbose_name_plural = 'odpowiedzi ankiet'
        indexes = [models.Index(fields=['survey', 'received_on'], name='survey_survey_received')]

    def __str__(self):
        return f'{self.survey} v{self.version} #{self.id} ({self.received_on}, {self.get_status_display()})'
