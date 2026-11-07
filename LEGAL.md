# fuw.lol — the law the code answers to

Polish law plus the EU Digital Services Act, as they bear on an amateur, community-run archive of
faculty folklore that publishes named human beings, their photographs, and the occasional exam
problem somebody else wrote. This file is where the *legal* reasoning lives; the engineering that
follows from it lives in `DESIGN.md` and in each app's `CLAUDE.md`, and points back here.

**Nothing in this file has been checked by a lawyer.** Much of it comes from a Gemini Deep Research
report (`docs/gemini/legal.txt`, indexed in `docs/gemini/note.md`) that gives no sources; the
mechanisms were checked against how the law is generally understood, the court signatures were not.
The terms of use at `/o-archiwum` deliberately cite only the two rulings that are common knowledge
(V CSK 51/17, NSA III OSK 2603/23). Treat the rest as a good intern's notes, and refresh them once a
semester — the DSA and the case law both move.

Article shorthand: *pr. aut.* = ustawa o prawie autorskim i prawach pokrewnych; *k.k.* = kodeks karny;
*KC* = kodeks cywilny; *RODO* = GDPR; *DSA* = Regulation (EU) 2022/2065.

---

## 1. The contact point

`FUWLOL_CONTACT_EMAIL` (`admin@fuw.lol` in production) is the mailbox a human reads: the DSA art. 12
point of contact, where RODO requests arrive, and where Dyżurnet replies. Human mail stays on OVH's
mail service; the application's own SMTP (Brevo) only ever *sends* the one message that matters,
the address-verification mail that admits somebody to the trusted tier (`deploy/OVH.md`).

## 2. Content somebody else made

- **The uploader declares their rights.** `Post.rights_confirmed` is required on every new post and
  is the *submitter's* statement, nothing more — it is not consent from anybody the post is about
  (§3). A meme built on somebody else's picture leans on parody (art. 29¹ pr. aut.), not on the
  quotation right, and the report says so; the declaration puts that on the uploader.
- **Teaching materials** (a lecturer's exam problem, a scanned handout) are the lecturer's or the
  university's. The report covers the ground; nothing in the code depends on the answer beyond the
  uploader's declaration and the report path below.
- **Open, and not asked of anyone yet:** whether a parody of the whole Faculty website (the look is a
  measured copy, on purpose — `DESIGN.md`) is a trademark or personal-rights risk for a legal
  person; and whether a *fictional* person (the seed data's "prof. Hamiltonian") protects anything
  under art. 81 pr. aut. and art. 23 KC once everybody knows who is meant.

## 3. A person's image and name — art. 81 pr. aut., art. 23 KC

A university lecturer is **not** a publicly known person for the purposes of art. 81 (V CSK 51/17),
so publishing their likeness needs their consent, and a student's likeness needs it all the more.
The archive therefore keeps two separate statements and never lets one stand in for the other:

| Statement | Whose | Field | Written by |
|---|---|---|---|
| "I have the right to post this" | the uploader | `Post.rights_confirmed` | the uploader, at submission |
| "Pictures of me may / may not be here" | the person depicted | `Person.image_consent` | the `consent` app or staff — never a submitter |

`Person.image_consent` is `unknown | granted | refused | opted_out`. It is written by the
**„Jesteś tą osobą?”** flow (`backend/consent/`): the person gives an e-mail and one of three wishes
worded for them — *zdjęcia ze mną mogą tu być* (`images_ok`), *wzmianki tak, zdjęć nie*
(`no_images`), *nie chcę być w archiwum* (`no_mention`); a link proves the mailbox; staff approve or
reject. Only `granted` opens the portrait gallery, and every gallery read re-checks it, so a
withdrawal empties the gallery at the next request.

**The approved claim is the evidence of consent** (art. 7 ust. 1 RODO) and is never deleted; a later
change writes a new row and marks the old one `superseded`. **Withdrawal is as easy as consent**
(art. 7 ust. 3 RODO): a link to the same mailbox changes the wish at once, with no second review.
The asymmetry in the flow is deliberate — a fraudulent "yes, publish my photos" is real harm, a
fraudulent "hide my photos" only hides content until staff reject it — so the two tightening wishes
take effect at mailbox verification when the address is at a `TrustedDomain`, and everything else
waits for a human. `/ludzie/zgoda` explains all of this to the person, because a badge nobody can
look up is a rumour.

A name matching somebody who opted out is **refused, never reused**, when a submitter types it into
the people picker: reusing would let anybody undo an art. 81 opt-out by typing a name
(`archive/people.py`).

## 4. Personal data — RODO

- **Raw addresses are kept for one purpose and then forgotten.** `Post.submitter_ip` and the
  user-agent exist to be the identifying half of an art. 18 DSA report; `manage.py
  forget_submitter_ips` blanks them after `FUWLOL_SUBMITTER_IP_RETENTION_DAYS` (90). An escalation
  freezes them into the evidence manifest first, so a report assembled next month still carries
  them. `forget_claim_ips` does the same for consent claims — except approved rows, which *are* the
  evidence that somebody agreed. Kept past their purpose, addresses are the RODO problem, not the
  solution.
- Chat and evidence hash visitor addresses with `FUWLOL_IP_SALT`; rotating the salt stops old
  `ip_hash` values correlating.
- Photographs lose EXIF (a phone writes GPS into every picture) before they are stored.
- A reporter's e-mail and note are visible to staff only; a moderator's review note is returned to
  the author only; an audit line written on a person's request says „na wniosek osoby, której wpis
  dotyczy” and never the address.
- Lists of grades and similar personal data have their own case law (NSA III OSK 2603/23); the terms
  of use cite it.

## 5. DSA — notice and action

The service is a hosting provider under art. 6 DSA (not art. 14 of the old Polish e-services act),
which brings the notice-and-action duties of arts. 16, 17 and 20:

- **A report is a formal art. 16 notice** when it carries an e-mail and a good-faith statement
  (`Report.good_faith`); the moderation queue marks such reports „formalne (DSA)”. Anonymous reports
  are still accepted — the person a post is about may have no account.
- **The author of a rejected or hidden post sees the reason and the appeal path** (arts. 17 and 20),
  in „Moje wpisy” and on the post itself.
- **Not built:** confirmation of receipt to the reporter (art. 16 ust. 4) — there is no mail backend
  beyond address verification. The same missing piece blocks password reset and the head-admin
  alert for a new escalation (`PRODUCT.md` "Left open").

## 6. The two takedowns, and why they end differently

Taking something down is not one thing here, because the law it answers to is not one law.

**Civil — copyright, defamation, a photo of somebody who never agreed** (art. 81 pr. aut.,
art. 212 k.k., RODO). This is `nuked`: the post stops being readable by anybody below staff, and
its files are HELD — moved off the public path, kept. A claim of this kind can be litigated years
later and the file is the evidence; destroying it would destroy our own defence. This is what the
task brief calls `SOFT_DELETED`, and it deliberately does not get a second status name: two names
for one state is how an illegal state becomes representable.

**Criminal — suspected CSAM or comparable material** (art. 202 k.k., art. 18 DSA). This ends the
opposite way, because the opposite duty applies: art. 202 § 4b k.k. criminalises *possessing* the
material, and Polish law gives an amateur platform no chain-of-custody exemption for keeping a
copy "for the investigation". So the material is reported and then destroyed, and the two steps
happen in that order and only that order — once the bytes are gone this service cannot produce
them again for an investigator who asks.

    escalate ──► quarantined ──► approved ──► [head-admin forwards to Dyżurnet.pl themselves]
                     │                              │
                     │ decline                      ▼ confirmed_dispatch=true
                     ▼                         audit rows written  ──►  bytes destroyed  ──►  purged
              back where it was

`Post.status` gains `quarantined` and `purged`, written by exactly one module
(`escalation/services.py`) as a projection of the `Escalation` row that owns the workflow — and
`PostManager`, the DEFAULT manager, excludes both. That is the layer which catches the call site
nobody thought about: the public API, the board, the admin, the search index, `manage.py shell`.
`Post.all_objects` is the unfiltered escape hatch, used by the escalation machinery, by the API's
own queryset (so a head-admin can still reach what they are responsible for), by `_unique_slug`,
and by `Meta.base_manager_name` so related access keeps working. Comments and board messages have
no status to project onto and stay governed by the `Escalation` row alone — the criminal path is
not Post-only, because an attachment on a comment is the same offence and the same duty.

**Access is head-admin only, and that is a safety rule before it is a privacy one.** A trusted
student volunteering to moderate a meme archive must not acquire art. 202 § 4a/b exposure by
volunteering. `is_head_admin` accepts either `is_superuser` or a grantable
`escalation.can_manage_critical_quarantine`, so "as few people as possible" can be two people
without the second one getting the keys to everything else. Media previews for a head-admin are R2
presigned GETs capped at **five minutes** (`config/r2.PREVIEW_TTL_SECONDS`) — they are bearer
capabilities, so they are minutes, not hours.

**The purge itself** (`escalation/shred.py`) destroys every copy: the R2 object, the MEDIA_ROOT
file, the `EVIDENCE_ROOT/quarantine/` copy and the frozen evidence copy. Missing one would make
the purge a fiction, and the fiction is the dangerous part — an audit row saying the material was
destroyed while a copy sits on the VPS is exactly the state the statute punishes. A database
transaction cannot roll back a deleted R2 object, so the ordering is chosen instead of pretending
to be atomic: **audit rows commit, then bytes die, then the purge is marked**. A crash in the
middle leaves an incomplete purge — visible, retryable, and finished by running the action again
(the audit rows are not duplicated). The opposite order would leave destroyed bytes with no record
of what was destroyed, which nothing can repair. A failed shred answers **409** with the list of
copies that survived, never a silent success.

What outlives it is `EvidenceAuditLog`: one append-only row per destroyed file (`save` on an
existing row and `delete` both raise), holding the sha256, the uploader's IP and user-agent, the
timestamps, who reported it and the Dyżurnet reference. None of that is the material; all of it is
what an investigator actually asks for.

**The storage has to cooperate.** The R2 bucket must have versioning OFF and no lifecycle rule that
retains deleted objects, or the hard delete is not a delete and the audit row is a lie
(`.env.example`, `deploy/OVH.md`). Quarantined objects go to a *separate, private* bucket, because an
R2 custom domain publishes the whole bucket — measured, not assumed: a held object in the public
bucket still answered 200.

## 7. Reporting to Dyżurnet — the human step

The application never contacts an authority by itself. `escalation/nask.py` assembles what
Dyżurnet.pl's form asks for — target URL, publication and capture timestamps in UTC, uploader IP and
user-agent, every sha256, the package hash — as JSON and as Polish text to paste, and a head-admin
sends it. The purge endpoint refuses unless the escalation is already `approved` *and*
`confirmed_dispatch` is explicitly true: calling the endpoint is not itself the statement "I have
sent it". Approving is the statement that the package is complete; declining returns the content to
ordinary moderation. Everything is a row in the database and a line in the `security` log.

## 8. The terms of use at `/o-archiwum`

Built from the legal report's list of what a service like this has to say: what the archive is,
the uploader's declaration, the removal paths (including „dotyczy mnie, proszę usunąć” for the
person concerned), the trusted tier and what it may do, escalation, the contact point. A warning
about other people's likeness sits beside the people picker. Change moderation copy and the terms
together — a refusal the terms do not describe is a refusal the reader cannot appeal.

## 9. WUM — accounts and published records (`backend/wum/`)

The side app at `fuw.lol/fum` (MedApp, a separate repository) kept nothing on this server until
2026-10. Now it keeps two kinds of row, and both are this operator's to answer for under RODO:

- **An account** (`WumProfile` on a Django `User`): a username, a password hash and four
  optional fields the person typed about themselves (first name, surname, contact e-mail, phone).
  The sign-up screen says, before the tick, that the app is at an early stage, that nothing in it
  is clinically reviewed, that it is not a medical record and that no real health data should be
  entered; `agreed_text_version` records which wording was agreed to. No e-mail verification, no
  password reset (the mail gap of §10), no self-service deletion: an
  account is deactivated in the admin on request, and its rows are kept.
- **A publication** (`Publication`): a record the person chose to publish, anonymised by the app
  on the phone before it was sent — no name, no legal name, no pronouns, no country or place, no
  contacts, no care-team names, an age band instead of an age, months instead of dates, free text
  only if separately ticked with a warning. The row keeps the link to the account for one purpose:
  withdrawal. Withdrawal is one tap, applies at once and needs no review (art. 7 ust. 3 RODO); the
  row is marked `withdrawn` and kept as the evidence of what was agreed to and when
  (`consent_text_version`), like a `PersonClaim`. The public read never carries the account.

What is **not** here: the person's health data. Symptoms, medicines, the emergency card and the
access log stay in the browser under the app's own retention modes, exactly as before; nothing
syncs. The app refuses to publish a record of a person under 18; this server cannot verify an age.

Two things a lawyer has to say before this is promoted rather than merely running: that this
operator is the controller of these rows (the medapp repository's `issues.md` ISS-033 and ISS-011
ask who, for the app as a whole), and that a single person's minimised record — which cannot be
k-anonymous, whatever the projection removes — may be published on an opt-in basis with the
wording the app shows. Withdrawn payloads also survive in the restic backups until a sweeper
exists (`wum/CLAUDE.md` "Left open").

## 9a. Koło AI — the register of members and remote votes (`backend/kolo_ai/`)

**The controller is Piotr Putyło, contact `admin@fuw.lol`** (decided 2026-11-03, while the Koło is
being registered; it is not a legal person, and once it is registered the University's own rules
may name another controller). The join form at ai.fuw.lol says so, together with the purpose
(the register of members, the list of sympatycy, notices and votes), the rights (access,
correction, erasure, withdrawal of consent, by mail to that address) and the retention. The
consent is versioned: `Member.agreed_text_version`, `rules.CONSENT_VERSION` ↔
`frontend/src/lib/kolo.svelte.ts`.

Retention: a member's row is kept for as long as the membership lasts. A `left` row is kept
afterwards because the register and past protocols refer to it, and how long it stays should be
written down when the first person leaves. An address nobody confirmed is deleted after 30 days
(`kolo_forget_unconfirmed`, nightly), because it is an e-mail typed by anybody with no agreement
behind it. Join and login answer the same way for known and unknown addresses, and both are
throttled per IP, because they send mail to the address that was typed.

Founder data (`FounderDetails`: phone, field of study, year, student number) exists for one purpose:
the BOK list of founders attached to the notice to the Rector (zarządzenie nr 170). The person
types it after logging in, with its own consent (`rules.FOUNDER_CONSENT_VERSION`). It is read only by
managers (`/zarzad/zalozyciele`) and printed onto the paper list that the founders sign. The person
can withdraw it (`DELETE me/founder/`). **It should be deleted once the Koło is registered**; the
paper list is the record. That step is manual for now (`kolo_ai/CLAUDE.md` "Left open").

What a vote keeps: the named row of an open vote (shown to members after the close, and in the
protocol); for a secret vote, the list of who took part (needed for the protocol, § 10a ust. 8) and
ballots that cannot be linked back to a person. Deliberation entries carry the member's name and
are visible to members only.

## 9b. LSD — the anonymous survey (`backend/survey/`)

The second copy of MedApp at `fuw.lol/lsd` carries a retrospective questionnaire about psychedelic
use, run as **preparation for a student observational study by a project that is not affiliated
with any university** (the word was "experiment" until the medapp SURVEY-R3 image of 2026-11-07,
version 2 of the questionnaire; the first acknowledgement changed with it, under the same consent
date, because no sheet had been received). **The controller is Piotr Putyło, contact `admin@fuw.lol`** (`survey/rules.CONTROLLER`),
and the questionnaire says so before the first question: its heading names the goal, and three
acknowledgements are required checkboxes — *Chcę podzielić się moim doświadczeniem w celach
przygotowań do studenckiego badania obserwacyjnego*, *Projekt nie jest powiązany z żadną uczelnią*,
*Administrator danych: Piotr Putyło, admin@fuw.lol* (`rules.CONSENT_STATEMENTS`, byte-identical in
the client; `rules.CONSENT_VERSION` is their date and every sheet records which version was ticked,
like `WumProfile.agreed_text_version`). What a person answers is **health data and data about an
offence — art. 9 and art. 10 RODO** — and the client promises anonymity, so the schema is built to
make the promise true rather than to rely on good behaviour:

- **What is stored** (`SurveyResponse`): the survey's slug and the version of its definition, the
  consent text's version, the interface language, how many seconds the sheet took, the answers as
  JSON under the client's question ids, and the **date** it arrived.
- **What is not**: no IP address and no hash of one (unlike the board and `feedback/`), no
  account — the view never reads `request.user`, so a visitor signed in to the archive in the
  same browser is not attached — no user agent, and **no timestamp**. The date is deliberate:
  every proxy in front of this service keeps an access log with the second a request arrived and
  the address it came from, and a `created_at` would let a row be joined to an address by time
  alone. A date cannot be joined that way and still answers "how many came in this week". The
  row's `id` orders sheets within a day; that is the accepted residue.
- **The way back is the person's choice, and a hash on this side.** Withdrawal of consent must be
  as easy as consent (art. 7 ust. 3 RODO), and an anonymous sheet cannot otherwise be found again,
  so the form offers one opt-in, after a second look that says it links the answers to the person:
  a key this server mints and hands back once (shown, saved, or as a QR drawn on the phone), kept
  as SHA-256 — `POST /api/survey/withdraw/` with it blanks the sheet at once, with no review and
  no account. Withdrawal keeps the row (status `withdrawn`, the date, the survey) with empty
  answers, so the count of sheets ever received stays right and nothing about the person remains.
  "Modify" is withdraw and send again. A sheet without a key cannot be withdrawn by anybody, and
  the form says so. **Until SURVEY-R3 (2026-11-07) there was a second opt-in, an e-mail kept as an
  HMAC under the salt** (`contact_hash`, dropped in `survey/0002`): removed because a keyed hash of
  an address is pseudonymisation, not anonymisation (whoever holds the table and the salt can test
  a candidate address), and because the withdrawal it enabled — a mail to `admin@fuw.lol` — put the
  person's address in front of the controller and in a mailbox. The key does the same job without
  either. No sheet had been received with the field.
- **Consent and the 18+ gate are on the client**, before the first question; this server cannot
  verify an age and does not try (as in §9). No confirmation mail is sent to the optional address
  (the mail gap of §10), so a typo there means no way back.
- **Retention**: the rows are kept until the study's analysis is done and exported
  (`manage.py export_survey`, which leaves both hashes out), after which the table may be emptied
  by the head admin in the Django admin (deletion is `is_superuser` only; nobody can edit a row).
  The export then lives with the study team, not here. Until the table is emptied the rows are
  also in the nightly restic dump of Postgres. When exactly "done" is, is left open in §10.
- **The documents at `/lsd/docs`** (since the medapp DOCS-R1 image, 2026-11-07) are the study's
  own working papers — the plan, the questionnaire's text, the procedures — published as read-only
  prose built into the image. They hold no data about anybody and make no call to this server; the
  only personal data on them is the controller's own name and address, which the consent text
  already names. One of them designs how the documents could be commented on and amended,
  anonymously or as a signed-in user, with the schema discipline of this section (no address, no
  account unless chosen, a date, a key as a hash, pre-moderation of anonymous entries); until that
  is built — and it is **not** — remarks go to `admin@fuw.lol`, as the pages say.

## 10. Left open

- Nothing here has been read by a lawyer. Before the archive is *promoted* rather than merely
  running, it should be.
- Art. 16 ust. 4 receipt confirmation, password reset and the head-admin alert all wait on one mail
  backend.
- Whether art. 26² pr. aut. (text-and-data-mining for research institutions) would ever apply to a
  history-recovery effort: it would not — fuw.lol is not a research institution
  (`docs/gemini/note.md`).
- Minors are not addressed anywhere: the audience is university students and staff, and nothing
  asks a registrant's age. (The side app refuses to *publish* under 18 on the phone — §9 — but its
  sign-up asks no age either; the survey's 18+ gate — §9b — is a checkbox on the phone too.)
- The survey table (§9b) has no retention clock of its own: "until the analysis is done and
  exported" is the study team's decision, and the date by which the head admin empties the table
  should be written here when the collection closes. Until then the rows, and the restic backups
  holding them, stay. Whether an ethics review of the student project's future modules is sought,
  and by whom, is the project's question, not this repository's.
