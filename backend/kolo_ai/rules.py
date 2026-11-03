"""Every rule of the Koło AI app that more than one endpoint needs (root CLAUDE.md, boundary 2).

The numbers come from the Koło's regulamin (kolo_ai_zebrania/regulamin.txt in the owner's
working tree, not in this repository):

- § 5 ust. 1–2: a member is a student or doktorant of the University; doktoranci at most half
  of the members. Anybody else is a sympatyk (§ 7) with no vote.
- § 10a: remote votes — at least 48 h; eligible = in the register when the vote OPENS; quorum
  = at least half of the eligible took part, no second term; secret votes unlinkable; results
  hidden until the close; 1/5 of members can move the matter to a meeting before it opens.
- § 10 ust. 3: a Walne vote is announced at least 7 days ahead; § 10a ust. 3: Zarząd 2 days.
- § 12 ust. 4: elections need an absolute majority of the valid votes.

Majorities (pinned by tests, because this is where vote-counting scripts usually go wrong):
- `zwykla`: za > przeciw; an abstention counts towards the quorum and nowhere else;
- `bezwzgledna`, `3/5`, `2/3`: the denominator is EVERY valid vote including abstentions, so an
  abstention works against the motion.
"""
import random
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import EmailValidator
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from .models import (Ballot, Comment, LoginLink, Member, MemberAction, Objection, Participation, Poll,
                     Session, Vote, hash_secret, new_secret)

# The wording a person agrees to on the join form. Mirrored in frontend/src/lib/kolo.ts
# CONSENT_VERSION — change both, and the text there.
CONSENT_VERSION = '2026-11-03'
# The founder-data wording on ai.fuw.lol (frontend/src/routes/ai/+page.svelte). Mirrored in
# frontend/src/lib/kolo.svelte.ts FOUNDER_CONSENT_VERSION.
FOUNDER_CONSENT_VERSION = '2026-11-03-zal'

YES_NO = ['za', 'przeciw', 'wstrzymuję się']
ABSTAIN = 'wstrzymuję się'
MIN_DURATION = timedelta(hours=48)
NOTICE = {Poll.WALNE: timedelta(days=7), Poll.ZARZAD: timedelta(days=2)}

# Addresses that can belong to a student or doktorant of the University. Being one of these is
# necessary for a vote, not sufficient: staff and graduates hold them too, which is why the
# person's own declaration (`Member.affiliation`) decides between członek and sympatyk.
UW_DOMAINS = ('uw.edu.pl', 'fuw.edu.pl', 'mimuw.edu.pl', 'astrouw.edu.pl')
STUDENT_DOMAIN = 'student.uw.edu.pl'

_email_validator = EmailValidator()


def normalize_email(raw):
    """The address as stored, or None. Strict like accounts.trust.match_domain: lowercase
    ASCII, one '@', no quotes or whitespace, Django's validator."""
    if not isinstance(raw, str):
        return None
    e = raw.strip().lower()
    if not e or not e.isascii() or any(c.isspace() for c in e) or '"' in e or "'" in e or e.count('@') != 1:
        return None
    try:
        _email_validator(e)
    except ValidationError:
        return None
    return e


def _domain(email):
    return email.rsplit('@', 1)[1]


# Domains people type for the UW student mailbox that receive no mail at all (no MX, no A):
# a link sent there never arrives, so the form says so instead of answering 202.
DEAD_DOMAINS = {'stud.uw.edu.pl': STUDENT_DOMAIN, 'students.uw.edu.pl': STUDENT_DOMAIN}


def dead_domain_problem(email):
    """An error for an address at a domain that takes no mail, naming the likely one, or None."""
    right = DEAD_DOMAINS.get(_domain(email))
    if right is None:
        return None
    local = email.rsplit('@', 1)[0]
    return f'Na adresy @{_domain(email)} poczta nie dochodzi. Skrzynka studencka UW to {local}@{right}.'


def is_uw_email(email):
    d = _domain(email)
    return any(d == u or d.endswith('.' + u) for u in UW_DOMAINS)


def is_student_email(email):
    return _domain(email) == STUDENT_DOMAIN


def auto_admit():
    """Off until the Koło is entered in the register: before that nobody is a member yet
    (§ 5 ust. 3), so every confirmed address waits in `pending_approval`."""
    return getattr(settings, 'FUWLOL_KOLO_AUTO_ADMIT', False)


# --- membership ---------------------------------------------------------------------------

def voting_members():
    return Member.objects.filter(status=Member.MEMBER, role=Member.CZLONEK)


def admission_problem(member, role):
    """Why `member` cannot be entered in the register with `role`, or None."""
    if member.email_confirmed_at is None and member.status != Member.INVITED:
        return 'Adres e-mail nie został jeszcze potwierdzony.'
    if role == Member.SYMPATYK:
        return None
    if member.affiliation == Member.INNY:
        return 'Członkiem może być tylko student lub doktorant UW (§ 5 ust. 1); ta osoba może zostać sympatykiem.'
    if not is_uw_email(member.email):
        return 'Członkostwo wymaga adresu poczty uniwersyteckiej UW; z tym adresem można zostać sympatykiem.'
    if member.affiliation == Member.DOKTORANT:
        others = voting_members().exclude(pk=member.pk)
        n, d = others.count(), others.filter(affiliation=Member.DOKTORANT).count()
        if 2 * (d + 1) > n + 1:
            return 'Doktoranci mogą stanowić najwyżej połowę członków Koła (§ 5 ust. 2).'
    return None


def _move(member, to, actor, action, reason=''):
    MemberAction.objects.create(member=member, actor=actor, action=action, from_status=member.status,
                                to_status=to, reason=reason)
    member.status = to


def admit(member, role, actor, reason=''):
    """Enter in the register. The caller has checked `admission_problem`."""
    now = timezone.now()
    _move(member, Member.MEMBER, actor, 'admit', reason)
    member.role, member.approved_at, member.left_at = role, now, None
    member.save(update_fields=['status', 'role', 'approved_at', 'left_at'])


def reject(member, actor, reason):
    _move(member, Member.REJECTED, actor, 'reject', reason)
    member.save(update_fields=['status'])


def leave(member, actor, reason):
    _move(member, Member.LEFT, actor, 'leave', reason)
    member.left_at = timezone.now()
    member.save(update_fields=['status', 'left_at'])


def email_confirmed(member):
    """A mailed link was opened: the address is the person's. Moves the lifecycle on."""
    now = timezone.now()
    if member.email_confirmed_at is None:
        member.email_confirmed_at = now
        member.save(update_fields=['email_confirmed_at'])
    if member.status == Member.INVITED:
        role = member.role
        if admission_problem(member, role) is None:
            admit(member, role, None, 'zaproszenie przyjęte')
        else:  # e.g. the doktorant cap moved since the invitation: a person decides
            _move(member, Member.PENDING_APPROVAL, None, 'invite_needs_review')
            member.save(update_fields=['status'])
    elif member.status == Member.PENDING_EMAIL:
        if (auto_admit() and member.affiliation == Member.STUDENT and is_student_email(member.email)
                and admission_problem(member, Member.CZLONEK) is None):
            admit(member, Member.CZLONEK, None, 'deklaracja studenta z adresem student.uw.edu.pl')
        else:
            _move(member, Member.PENDING_APPROVAL, None, 'email_confirmed')
            member.save(update_fields=['status'])


# --- links, sessions, mail ----------------------------------------------------------------

def site_url(path=''):
    return settings.FUWLOL_KOLO_SITE_URL.rstrip('/') + path


def make_link(member, valid_for=LoginLink.VALID_FOR):
    raw = new_secret()
    LoginLink.objects.create(member=member, token_hash=hash_secret(raw), expires_at=timezone.now() + valid_for)
    return site_url(f'/link?token={raw}')


def open_link(raw):
    """The member behind a live link, marking it used; None for anything else."""
    if not raw:
        return None
    now = timezone.now()
    with transaction.atomic():
        link = (LoginLink.objects.select_for_update().select_related('member')
                .filter(token_hash=hash_secret(raw), used_at__isnull=True, expires_at__gt=now).first())
        if link is None:
            return None
        link.used_at = now
        link.save(update_fields=['used_at'])
        email_confirmed(link.member)
        return link.member


def new_session(member):
    raw = new_secret()
    Session.objects.create(member=member, key_hash=hash_secret(raw), expires_at=timezone.now() + Session.VALID_FOR)
    return raw


def mail(to, subject, body):
    """Raises on an SMTP failure; the views answer 503 rather than pretend (rule 7)."""
    send_mail(f'Koło AI — {subject}', body + f'\n\n—\nKoło AI · {site_url()}\n'
              f'Administrator danych: Piotr Putyło, {settings.FUWLOL_CONTACT_EMAIL}\n',
              settings.DEFAULT_FROM_EMAIL, [to])


# --- polls --------------------------------------------------------------------------------

def phase(poll, now=None):
    """draft | announced (before the opening) | open | closed | cancelled | moved."""
    if poll.status != Poll.ANNOUNCED:
        return poll.status
    now = now or timezone.now()
    if now < poll.opens_at:
        return 'announced'
    return 'open' if now < poll.closes_at else 'closed'


def eligible(poll):
    """Who may vote: in the register when the vote opened (§ 10a ust. 2) — later admissions do
    not vote, a member who left after the opening still does. Derived from timestamps, so it is
    the same answer whenever it is asked and needs no snapshot job."""
    q = Member.objects.filter(role=Member.CZLONEK, status__in=[Member.MEMBER, Member.LEFT],
                              approved_at__lte=poll.opens_at).filter(Q(left_at__isnull=True) | Q(left_at__gt=poll.opens_at))
    if poll.organ == Poll.ZARZAD:
        q = q.filter(zarzad=True)
    return q


def can_see(member, poll):
    if member is None:
        return False
    if member.can_manage:
        return True
    if poll.status == Poll.DRAFT or member.status != Member.MEMBER or member.role != Member.CZLONEK:
        return False
    return poll.organ == Poll.WALNE or member.zarzad


def visible_polls(member):
    if member is None:
        return Poll.objects.none()
    if member.can_manage:
        return Poll.objects.all()
    if member.status != Member.MEMBER or member.role != Member.CZLONEK:
        return Poll.objects.none()
    q = Poll.objects.exclude(status=Poll.DRAFT)
    return q if member.zarzad else q.filter(organ=Poll.WALNE)


def has_voted(poll, member):
    model = Vote if poll.mode == Poll.JAWNE else Participation
    return model.objects.filter(poll=poll, member=member).exists()


def vote_block_reason(poll, member, option):
    p = phase(poll)
    if p != 'open':
        return 'Głosowanie nie jest otwarte.'
    if not eligible(poll).filter(pk=member.pk).exists():
        return 'Nie jesteś uprawniony do głosowania w tej sprawie (§ 10a ust. 2).'
    if not isinstance(option, int) or isinstance(option, bool) or not 0 <= option < len(poll.options):
        return 'Nie ma takiej odpowiedzi.'
    if has_voted(poll, member):
        return 'Głos został już oddany i nie można go zmienić.'
    return None


def cast(poll, member, option):
    """One transaction: for a secret vote the two halves land together or not at all."""
    with transaction.atomic():
        Poll.objects.select_for_update().get(pk=poll.pk)
        reason = vote_block_reason(poll, member, option)
        if reason:
            return reason
        if poll.mode == Poll.JAWNE:
            Vote.objects.create(poll=poll, member=member, option=option)
        else:
            Participation.objects.create(poll=poll, member=member)
            Ballot.objects.create(poll=poll, option=option)
    return None


def default_options(kind, candidates=()):
    """`uchwala` → za / przeciw / wstrzymuję się. `wybory` → the candidates and an abstention;
    a single candidate gets `przeciw` too, or the only way to oppose would be to abstain."""
    if kind == Poll.UCHWALA:
        return list(YES_NO)
    c = [x.strip() for x in candidates if x and x.strip()]
    return c + (['przeciw', ABSTAIN] if len(c) == 1 else [ABSTAIN])


def outcome(kind, options, counts, majority):
    """Pure: (passed: bool, winner: str|None, note: str). `counts` is per option."""
    total = sum(counts)
    if kind == Poll.UCHWALA:
        za, przeciw = counts[0], counts[1]
        if majority == 'zwykla':
            ok = za > przeciw
        elif majority == 'bezwzgledna':
            ok = 2 * za > total
        elif majority == '3/5':
            ok = total > 0 and 5 * za >= 3 * total
        elif majority == '2/3':
            ok = total > 0 and 3 * za >= 2 * total
        else:
            raise ValueError(majority)
        return ok, None, 'uchwała podjęta' if ok else 'uchwała nie została podjęta'
    # An election (§ 12 ust. 4): an absolute majority of the valid votes, abstentions included.
    names = [o for o in options if o not in ('przeciw', ABSTAIN)]
    for i, name in enumerate(names):
        if 2 * counts[i] > total:
            return True, name, f'wybrano: {name}'
    ranked = sorted(range(len(names)), key=lambda i: -counts[i])[:2]
    if len(names) == 1:
        return False, None, 'kandydat nie uzyskał bezwzględnej większości'
    return False, None, ('żaden kandydat nie uzyskał bezwzględnej większości; kolejne głosowanie: '
                         + ', '.join(names[i] for i in ranked))


def _shuffle_ballots(poll):
    """Rewrite the secret ballots in random order with fresh keys, once, after the close —
    so the physical row order stops lining up with the Participation rows (SECURITY.md)."""
    ballots = list(Ballot.objects.filter(poll=poll).values_list('option', flat=True))
    random.SystemRandom().shuffle(ballots)
    Ballot.objects.filter(poll=poll).delete()
    Ballot.objects.bulk_create([Ballot(poll=poll, option=o) for o in ballots])


def tally(poll):
    """The result of a CLOSED vote, or None while it is not closed (§ 10a ust. 6)."""
    if phase(poll) != 'closed':
        return None
    if poll.mode == Poll.TAJNE and poll.tallied_at is None:
        with transaction.atomic():
            locked = Poll.objects.select_for_update().get(pk=poll.pk)
            if locked.tallied_at is None:
                _shuffle_ballots(locked)
                locked.tallied_at = timezone.now()
                locked.save(update_fields=['tallied_at'])
            poll.tallied_at = locked.tallied_at
    source = Vote.objects if poll.mode == Poll.JAWNE else Ballot.objects
    by_option = dict(source.filter(poll=poll).values_list('option').annotate(n=Count('pk')))
    counts = [by_option.get(i, 0) for i in range(len(poll.options))]
    voters = sum(counts)
    entitled = eligible(poll).count()
    quorum = entitled > 0 and 2 * voters >= entitled
    passed, winner, note = outcome(poll.kind, poll.options, counts, poll.majority)
    if not quorum:
        passed, winner, note = False, None, 'brak kworum: głosowało mniej niż połowa uprawnionych (§ 10a ust. 5)'
    return {'counts': counts, 'voters': voters, 'eligible': entitled, 'quorum': quorum,
            'passed': passed, 'winner': winner, 'note': note}


def voters(poll):
    """Who took part — for the protocol (§ 10a ust. 8). For a secret vote this is the
    Participation list, which says nothing about how anybody voted."""
    model = Vote if poll.mode == Poll.JAWNE else Participation
    return Member.objects.filter(pk__in=model.objects.filter(poll=poll).values('member')).order_by('name')


def announce_problem(poll, now=None):
    now = now or timezone.now()
    if poll.status != Poll.DRAFT:
        return 'Zawiadomić można tylko projekt głosowania.'
    if poll.closes_at - poll.opens_at < MIN_DURATION:
        return 'Głosowanie musi trwać co najmniej 48 godzin (§ 10a ust. 4).'
    if len(poll.options) < 2:
        return 'Głosowanie potrzebuje co najmniej dwóch odpowiedzi.'
    if not poll.trial and poll.opens_at - now < NOTICE[poll.organ]:
        days = NOTICE[poll.organ].days
        return f'Zawiadomienie musi wyjść co najmniej {days} dni przed rozpoczęciem głosowania (§ 10 ust. 3, § 10a ust. 3).'
    return None


def notify_announced(poll):
    """Mail every eligible-as-of-now person. Returns how many mails failed (the poll stays
    announced; the manager sees the number and can resend by hand)."""
    people = voting_members()
    if poll.organ == Poll.ZARZAD:
        people = people.filter(zarzad=True)
    fmt = '%d.%m.%Y %H:%M'
    tz = timezone.get_current_timezone()
    body = (f'{"[PRÓBA — bez skutków prawnych] " if poll.trial else ""}'
            f'Zawiadomienie o głosowaniu zdalnym ({poll.get_organ_display()}, § 10a regulaminu)\n\n'
            f'W sprawie: {poll.title}\n'
            f'Głosowanie {poll.get_mode_display()}, od {poll.opens_at.astimezone(tz).strftime(fmt)} '
            f'do {poll.closes_at.astimezone(tz).strftime(fmt)}.\n\n'
            f'{poll.body}\n\n'
            f'Obrady i głosowanie: {site_url(f"/glosowania/{poll.pk}")}\n'
            f'Jeśli uważasz, że sprawa powinna trafić na zebranie, możesz tego zażądać przed rozpoczęciem '
            f'głosowania (§ 10a ust. 7).\n')
    failed = 0
    for m in people:
        try:
            mail(m.email, f'głosowanie: {poll.title}', body)
        except Exception:
            failed += 1
    return failed


def object_to(poll, member):
    """§ 10a ust. 7. Returns a refusal or None; moves the poll when 1/5 is reached."""
    if phase(poll) != 'announced':
        return 'Żądanie można zgłosić tylko przed rozpoczęciem głosowania.'
    if member.status != Member.MEMBER or member.role != Member.CZLONEK:
        return 'Żądanie może zgłosić członek Koła.'
    with transaction.atomic():
        locked = Poll.objects.select_for_update().get(pk=poll.pk)
        Objection.objects.get_or_create(poll=locked, member=member)
        n = Objection.objects.filter(poll=locked).count()
        if 5 * n >= voting_members().count():
            locked.status = Poll.MOVED
            locked.save(update_fields=['status'])
            poll.status = Poll.MOVED
    return None


def can_comment(member, poll):
    return can_see(member, poll) and phase(poll) in ('announced', 'open')


def visible_comments(poll):
    return Comment.objects.filter(poll=poll, hidden_at__isnull=True).select_related('member')


def founder_problem(member):
    """Why `member` may not file founder data, or None. A founder is a student or doktorant of the
    University (art. 111 PSWiN; § 5 ust. 1, § 5 ust. 3), writing from a confirmed UW address."""
    if member.status not in (Member.PENDING_APPROVAL, Member.MEMBER):
        return 'Dane założyciela może podać osoba z potwierdzonym adresem, która jest na liście.'
    if member.affiliation == Member.INNY or not is_uw_email(member.email):
        return 'Założycielem może być tylko student lub doktorant UW piszący z adresu UW.'
    return None


# Texts managers edit on ai.fuw.lol; the default is what shows until somebody does.
SETTINGS = {
    'founders_notice': ('Listę założycieli podpisujemy na zebraniu założycielskim we wtorek 3 listopada 2026 '
                        'w godz. 11:00–11:40, sala 0.03 FUW (Pasteura 5). Wpisz dane poniżej wcześniej – na miejscu '
                        'tylko się podpiszesz.'),
}


def setting(key):
    from .models import Setting
    row = Setting.objects.filter(key=key).first()
    return row.value if row else SETTINGS[key]
