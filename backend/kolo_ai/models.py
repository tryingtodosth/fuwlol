"""Koło AI (fuw.lol/ai): members, remote votes under § 10a of the Koło's regulamin, and the
public status feed.

A member is NOT an archive `User`. The Koło keeps its own register (`Member`, keyed by
e-mail) with its own sessions, the same separation `wum/` has: nothing here gives or takes
an archive power, and the archive's token never opens this app (`auth.py`).

Lifecycles are one `status` each (root CLAUDE.md "Shapes that repeat"):

- Member:  pending_email → pending_approval → member | rejected ;  invited → member ;  member → left
- Poll:    draft → announced → (open/closed by the clock) ;  draft|announced → cancelled | moved
           — open and closed are DERIVED from `opens_at`/`closes_at` (`rules.phase`), never
           stored, so nothing needs a cron to flip them.
- StatusEntry: published → withdrawn

Every member transition writes a `MemberAction`. Nothing here is deleted: a member leaves,
a poll is cancelled, a status entry is withdrawn, a comment is hidden.

The secret ballot is two tables written in one transaction (`rules.cast`): `Participation`
says THAT somebody voted, `Ballot` says WHAT was voted and carries neither the member, nor a
time, nor a sequential key. That is what the application guarantees; what it cannot
guarantee against the operator of the database is in SECURITY.md "Koło AI".
"""
import hashlib
import secrets
import uuid

from django.db import models
from django.utils import timezone


def new_secret():
    return secrets.token_urlsafe(32)


def hash_secret(raw):
    """Links and sessions are stored hashed: a database dump is not a set of live logins."""
    return hashlib.sha256(raw.encode()).hexdigest()


class Member(models.Model):
    PENDING_EMAIL, INVITED, PENDING_APPROVAL, MEMBER, REJECTED, LEFT = (
        'pending_email', 'invited', 'pending_approval', 'member', 'rejected', 'left')
    STATUSES = [
        (PENDING_EMAIL, 'czeka na potwierdzenie adresu'),
        (INVITED, 'zaproszony'),
        (PENDING_APPROVAL, 'oczekuje na zatwierdzenie'),
        (MEMBER, 'wpisany do ewidencji'),
        (REJECTED, 'odmowa wpisu'),
        (LEFT, 'członkostwo ustało'),
    ]
    CZLONEK, SYMPATYK = 'czlonek', 'sympatyk'
    ROLES = [(CZLONEK, 'członek (prawo głosu)'), (SYMPATYK, 'sympatyk (bez prawa głosu, § 7)')]

    STUDENT, DOKTORANT, INNY = 'student', 'doktorant', 'inny'
    AFFILIATIONS = [(STUDENT, 'student UW'), (DOKTORANT, 'doktorant UW'), (INNY, 'ani student, ani doktorant UW')]

    email = models.EmailField(unique=True)  # lowercased by rules.normalize_email before it gets here
    name = models.CharField(max_length=120)  # as in the register of members
    status = models.CharField(max_length=20, choices=STATUSES, default=PENDING_EMAIL)
    role = models.CharField(max_length=10, choices=ROLES, default=SYMPATYK)  # czlonek only via rules.admit
    # The person's own declaration (§ 5 ust. 1–2): `inny` is a sympatyk at most, whatever the
    # address — a fuw.edu.pl mailbox belongs to staff and graduates too; doktoranci are capped.
    affiliation = models.CharField(max_length=10, choices=AFFILIATIONS, default=STUDENT)
    funkcja = models.CharField(max_length=80, blank=True)  # "Prezes", "Sekretarz", … — shown, not a power
    zarzad = models.BooleanField(default=False)  # sits on the Zarząd: eligible in Zarząd votes
    can_manage = models.BooleanField(default=False)  # approves members, runs votes, posts status
    agreed_text_version = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    email_confirmed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)  # entry into the register (ewidencja)
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} <{self.email}>'


class MemberAction(models.Model):
    """One row per transition: who did it, from what to what, and why (a refusal needs a
    Zarząd resolution with reasons, § 5 ust. 5 — the reason field is where it is quoted)."""
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name='actions')
    actor = models.ForeignKey(Member, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    action = models.CharField(max_length=30)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    reason = models.TextField(blank=True)
    at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['at', 'id']


class LoginLink(models.Model):
    """A link mailed to a member's address. Opening it confirms the address AND logs in:
    joining, being invited and logging in are the same mail with different words."""
    VALID_FOR = timezone.timedelta(hours=24)
    INVITE_VALID_FOR = timezone.timedelta(days=7)

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='links')
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)


class Session(models.Model):
    VALID_FOR = timezone.timedelta(days=30)

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='sessions')
    key_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)


class PublishKey(models.Model):
    """A key that may post status entries and nothing else — for the script that publishes
    progress right after each step (`publikuj_status.py` in kolo_ai_zebrania). Created and
    revoked with `manage.py kolo_publish_key`; the raw key is printed once."""
    name = models.CharField(max_length=60)
    key_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


class StatusEntry(models.Model):
    PUBLISHED, WITHDRAWN = 'published', 'withdrawn'
    STATUSES = [(PUBLISHED, 'opublikowany'), (WITHDRAWN, 'wycofany')]

    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)  # plain text, shown with line breaks, never as HTML
    status = models.CharField(max_length=10, choices=STATUSES, default=PUBLISHED)
    published_at = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=80)  # "klucz: claude", "zarząd: Jan Kowalski"

    class Meta:
        ordering = ['-published_at', '-id']
        verbose_name_plural = 'status entries'


class Poll(models.Model):
    WALNE, ZARZAD = 'walne', 'zarzad'
    ORGANS = [(WALNE, 'Walne Zebranie'), (ZARZAD, 'Zarząd')]
    UCHWALA, WYBORY = 'uchwala', 'wybory'
    KINDS = [(UCHWALA, 'uchwała'), (WYBORY, 'wybory')]
    JAWNE, TAJNE = 'jawne', 'tajne'
    MODES = [(JAWNE, 'jawne'), (TAJNE, 'tajne')]
    MAJORITIES = [
        ('zwykla', 'zwykła większość (za > przeciw)'),
        ('bezwzgledna', 'bezwzględna większość ważnie oddanych głosów'),
        ('3/5', 'co najmniej 3/5 głosów'),
        ('2/3', 'co najmniej 2/3 głosów'),
    ]
    DRAFT, ANNOUNCED, CANCELLED, MOVED = 'draft', 'announced', 'cancelled', 'moved'
    STATUSES = [(DRAFT, 'projekt'), (ANNOUNCED, 'zawiadomione'), (CANCELLED, 'odwołane'),
                (MOVED, 'przeniesione na zebranie (§ 10a ust. 7)')]

    organ = models.CharField(max_length=10, choices=ORGANS, default=WALNE)
    kind = models.CharField(max_length=10, choices=KINDS, default=UCHWALA)
    title = models.CharField(max_length=200)  # "w sprawie …"
    body = models.TextField()  # the draft resolution, plain text
    mode = models.CharField(max_length=10, choices=MODES, default=JAWNE)
    # A yes/no vote is the default three; an election lists candidates and then the abstention.
    options = models.JSONField(default=list)
    majority = models.CharField(max_length=12, choices=MAJORITIES, default='zwykla')
    trial = models.BooleanField(default=False)  # próba: no legal effect, skips the notice periods
    status = models.CharField(max_length=10, choices=STATUSES, default=DRAFT)
    opens_at = models.DateTimeField()
    closes_at = models.DateTimeField()
    announced_at = models.DateTimeField(null=True, blank=True)
    # Set when the secret ballots were re-written in random order after the close (rules.tally),
    # so the physical order of the Ballot rows stops mirroring the Participation rows.
    tallied_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(Member, on_delete=models.PROTECT, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-opens_at', '-id']


class Vote(models.Model):
    """An OPEN vote: who and what, one per member, never changed."""
    poll = models.ForeignKey(Poll, on_delete=models.PROTECT, related_name='votes')
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name='+')
    option = models.PositiveSmallIntegerField()
    cast_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['poll', 'member'], name='kolo_vote_once')]


class Participation(models.Model):
    """A SECRET vote, half one: that this member voted. Never joined to a Ballot. A random key
    and no timestamp — a backup must not give the minute somebody voted to set beside the
    proxy's access log."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    poll = models.ForeignKey(Poll, on_delete=models.PROTECT, related_name='participations')
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name='+')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['poll', 'member'], name='kolo_participate_once')]


class Ballot(models.Model):
    """A SECRET vote, half two: what was voted. A random key, no member, no timestamp — the
    order of rows says nothing about the order of voters."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    poll = models.ForeignKey(Poll, on_delete=models.PROTECT, related_name='ballots')
    option = models.PositiveSmallIntegerField()


class Objection(models.Model):
    """A member's demand, before the vote opens, that the matter go to a meeting (§ 10a ust. 7)."""
    poll = models.ForeignKey(Poll, on_delete=models.PROTECT, related_name='objections')
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name='+')
    at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['poll', 'member'], name='kolo_object_once')]


class Comment(models.Model):
    """The deliberation under a poll (§ 10a ust. 4). Plain text; hidden, never deleted."""
    poll = models.ForeignKey(Poll, on_delete=models.PROTECT, related_name='comments')
    member = models.ForeignKey(Member, on_delete=models.PROTECT, related_name='+')
    body = models.TextField(max_length=4000)
    created_at = models.DateTimeField(default=timezone.now)
    hidden_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at', 'id']


class FounderDetails(models.Model):
    """What the BOK list of founders asks beyond name and address (zarządzenie nr 170, the
    "Lista założycieli organizacji" template): phone, field of study or doctoral school, year or
    stage, student number. Typed by the person, read by managers only, printed onto the paper list
    that the founders sign. Kept apart from `Member` because it is more sensitive and has a shorter
    life: it exists for the registration and is wiped after it (LEGAL.md 9a)."""
    member = models.OneToOneField(Member, on_delete=models.CASCADE, related_name='founder')
    phone = models.CharField(max_length=20)
    kierunek = models.CharField(max_length=120)  # field of study, or the doctoral school
    etap = models.CharField(max_length=40)  # year of study, or stage in the doctoral school
    nr_albumu = models.CharField(max_length=10)
    agreed_text_version = models.CharField(max_length=20)
    updated_at = models.DateTimeField(auto_now=True)


class Setting(models.Model):
    """A few texts a manager edits on the page itself (`rules.SETTINGS` lists the keys and their
    defaults), e.g. when and where the founders sign the paper list. Plain text, never HTML."""
    key = models.CharField(max_length=40, unique=True)
    value = models.TextField(max_length=1000)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=120, blank=True)
