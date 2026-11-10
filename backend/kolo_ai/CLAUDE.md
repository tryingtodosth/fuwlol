# kolo_ai — Koło AI at ai.fuw.lol: the register of members, remote votes (§ 10a), the status feed

Koło AI is a student organisation at the Faculty of Physics (in registration at BOK UW since
2026-11-03). This app is its electronic register of members and its remote-voting system, both
defined by the Koło's **regulamin**. That document lives outside this repository, in the owner's
`~/Projects/AI/kolo_ai_zebrania/regulamin.txt`. Every rule below cites its paragraph, so when the
regulamin changes, this file and `rules.py` change with it. 45 tests (`tests.py`) and one browser
script (`frontend/e2e/kolo.mjs`, 16 checks).

## Not the archive

- Its own people: `Member`, keyed by e-mail. A member is **not** a `User`.
- Its own credentials (`auth.py`): `Authorization: Kolo <session>` for a member, and
  `Authorization: KoloKey <key>` for the status-publishing script. `request.user` stays anonymous.
- An archive token opens nothing here, and a Koło session opens nothing in the archive. Both
  directions are pinned by tests.
- The frontend keeps the session under `localStorage['fuwlol.kolo']`. `lib/api.ts` sends it on
  `/kolo/…` paths only and never sends the archive token there.
- Served at **ai.fuw.lol** by the same nginx and the same SPA:
  - `src/hooks.ts` `reroute` maps that host's paths under `/ai`;
  - nginx answers 308 on `fuw.lol/ai`, `/AI` and every other case variant;
  - the root `+layout.svelte` drops the archive's chrome for `/ai` routes;
  - crawlers on that host get the plain shell, not an archive preview (`$fuwlol_archive_host` map).

## Lifecycles (one `status` each)

- **Member:** `pending_email` → `pending_approval` → `member` | `rejected`; `invited` → `member`;
  `member` → `left`. Every transition writes a `MemberAction`.
- **Poll:** `draft` → `announced` → `cancelled` | `moved`. **Open and closed are derived from
  `opens_at` and `closes_at` (`rules.phase`), never stored**, so no cron flips them.
- **StatusEntry:** `published` → `withdrawn`.

Nothing is deleted except by `kolo_forget_unconfirmed` (RODO retention, see below).

## Rules (`rules.py`) — the regulamin in code

- **Joining is signing up on the list.** The form is the membership declaration of § 5 ust. 4. It
  answers the same 202 ("Oczekujesz na zatwierdzenie…") for a new address and a known one, so it
  is not an oracle; a known address gets a login link instead.
- **The mailed link confirms the address and logs in.** It is single-use, valid 24 h (7 days for
  an invitation), and stored hashed. Sessions are stored hashed too.
- **Who can be a member with a vote** (`admission_problem`, § 5 ust. 1–2):
  - the person declares `student` or `doktorant`, and the address is a UW one (`UW_DOMAINS`);
  - `inny` is a sympatyk at most, whatever the address, because a `fuw.edu.pl` mailbox can belong
    to staff or a graduate;
  - doktoranci can be at most half of the members.
- **Admission:**
  - `FUWLOL_KOLO_AUTO_ADMIT=1` admits a confirmed `student` at `student.uw.edu.pl` straight away.
    It stays **off until the Koło is in the BOK register**; until then nobody is a member
    (§ 5 ust. 3), so everybody waits for a manager.
  - An invitation from a manager counts as the approval.
  - A refusal requires a reason (§ 5 ust. 5: a Zarząd resolution with reasons).
- **Who may vote** (`eligible`, § 10a ust. 2): members of the register **when the vote opens**,
  derived from `approved_at` and `left_at`. Someone admitted later does not vote; someone who left
  later still does. A Zarząd vote is limited to `zarzad=True`.
- **Announcing** (`announce_problem`):
  - the vote lasts at least 48 h (§ 10a ust. 4);
  - notice is at least 7 days for the Walne (§ 10 ust. 3) and 2 days for the Zarząd (§ 10a ust. 3);
  - `trial=True` (próba, no legal effect) skips the notice period, and nothing else.
- **Quorum and majorities** (`tally`, `outcome`):
  - quorum: at least half of the eligible took part, with no second term (§ 10a ust. 5);
  - `zwykla` = za > przeciw;
  - `bezwzgledna`, `3/5`, `2/3` count **abstentions in the denominator**;
  - elections always need an absolute majority (§ 12 ust. 4); a single candidate gets a `przeciw`
    option; with no winner, the note names the two for the next round.
- **Results stay hidden until the close** (§ 10a ust. 6). Named votes of an open vote are shown
  only to those who could see the vote.
- **Secret ballot:** `Participation` (who) and `Ballot` (what) are written in one transaction.
  - Neither row has a timestamp, and both keys are random UUIDs.
  - On the first tally after the close, the ballots are rewritten in random order with fresh
    keys (`_shuffle_ballots`, `Poll.tallied_at`).
  - What this does not protect against is in `SECURITY.md` "Koło AI".
- **Moving to a meeting:** when 1/5 of the members object before the opening, the vote becomes
  `moved` (§ 10a ust. 7).
- **Deliberation:** the comments under a poll, plain text, open to whoever can see the vote while
  it is announced or open. A comment can be hidden; it is never deleted.
- **Who sees votes:** a member with a vote. A sympatyk and the public see the status feed only.

## The list of founders and editable texts

- **`FounderDetails`** (1:1 `Member`) holds what the BOK template asks for beyond name and
  e-mail: phone, `kierunek`, `etap`, `nr_albumu`, plus its own consent version.
  - Filed by the person on `/ai` (`me/founder/`, GET, PUT, DELETE), only while `pending_approval`
    or `member`, and only as a student or doktorant writing from a UW address (`rules.founder_problem`).
  - Managers read it (`founders/`, sorted by surname) and print it from `/ai/zarzad/zalozyciele`.
    That page is the BOK layout: 11 rows per page, filled rows first, then at least 22 blank rows
    rounded up to full pages, with the signature column always blank.
  - "Pobierz JSON" saves a file that `kolo_ai_zebrania/generuj.py` reads as `zalozyciele.json`, to
    produce the same list as DOCX and PDF.
- **`Setting`** holds texts a manager edits on the page (`rules.SETTINGS`, e.g. `founders_notice`:
  when and where the list is signed). The current values come in `info/` → `texts`; a manager
  changes one with `PUT settings/<key>/`.

## Commands

| Command | What |
|---|---|
| `kolo_invite EMAIL --name … [--manager] [--zarzad] [--funkcja …] [--print-link]` | the first manager gets in this way; also grants flags to an existing member |
| `kolo_publish_key create\|revoke\|list NAME` | the key for `publikuj_status.py`; printed once |
| `kolo_protocol ID` | Markdown protocol of a closed vote (§ 10a ust. 8); also `GET polls/<id>/protocol/` |
| `kolo_mail FILE\|- [--send] [--test ADDR] [--extra ADDR …]` | a mailing: one copy per person on `rules.mailing_recipients()`, each with its own unsubscribe link; without `--send` a dry run. `-` reads stdin, so a file from another machine goes in with `exec -T api python manage.py kolo_mail - --send < mail.txt` |
| `kolo_forget_unconfirmed` | **nightly cron**: unconfirmed sign-ups older than 30 days, plus used or expired links and sessions. The consent text promises the 30 days |

`can_manage`, `zarzad` and `funkcja` are set in the Django admin (`/admin/kolo_ai/member/`) or by
`kolo_invite`, never through the API. Ballots are not registered in the admin at all.

## Mailings and unsubscribing

- **Who gets a mailing:** `member`, `pending_approval` and `invited` rows with `mail_opt_out_at`
  empty. `pending_email` never: nobody confirmed that the address is theirs.
- **Unsubscribing never touches membership.** It sets `Member.mail_opt_out_at` and writes a
  `MemberAction` (`mail_off` / `mail_on`, status unchanged). Login links, invitations and
  decisions still go, because they answer something the person did.
- **The link** is `/wypisz?t=<signed row id>` (`rules.unsubscribe_token`, `django.core.signing`,
  salt `kolo_ai.unsubscribe`). It is never stored and never expires; rotating `SECRET_KEY` voids
  every old link. Opening the page changes nothing (mail scanners follow links); the button POSTs
  `unsubscribe/`. The same page can undo it.
- **One click from the mail client:** every copy carries `List-Unsubscribe: <…/api/kolo/unsubscribe/?t=…>,
  <mailto:…?subject=WYPISZ>` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click` (RFC 8058).
  The view takes that form-encoded POST; there is no GET.
- **Logged in:** the card on `/ai` has a switch (`PUT me/mail/`).
- An `--extra` address outside the register has no row and so no link; its copy says to reply WYPISZ.

## Left open

- **No reminder mail** 24 h before the close: that needs a cron job, which nothing here has yet.
- **Resending a notice:** when some notices fail to send, the panel shows how many. Resending is
  by hand.
- **The opiekun** is not copied on notices (§ 10 ust. 3, second sentence). Add it when their
  address is known.
- **Runoff:** the second round of an election is a new poll that a manager creates by hand.
- **Protocol:** the Markdown is not yet fed into `generuj.py` (a `typ = "zdalne"` there).
- **Founder data is not wiped automatically** after registration: delete the `FounderDetails` rows by hand once BOK has the paper list.
- **The initiative register** (§ 4 pkt 7, § 14 ust. 3 pkt 2) is not built.
- **Notice periods are not shortened by an urgent procedure**, because the regulamin has none.
