r"""fuw.lol — the archive.

A `Post` is one archived thing: a meme, a quote, a legendary exam problem, a photo, a
story, a scan. Its `body` is either plain text/Markdown or a LaTeX source (`format`),
and its pictures/files hang off it as `Attachment`s. Files are referenced from the body
by their ORIGINAL file name (`![](zdjecie.jpg)` / `\includegraphics{zdjecie.jpg}`), and
the frontend maps that name to the stored file's URL at render time — so a post and
its files can be submitted in one multipart request with nothing uploaded ahead of time.

Dates are fuzzy on purpose: an archive of folklore rarely knows the exact day, so a
post carries a `year` plus how sure we are of it (`year_precision`) and a free-text note.
"""
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from .validators import validate_upload


FORMAT_CHOICES = [('text', 'Tekst / Markdown'), ('latex', 'LaTeX')]
# 'hidden' — taken off the public page; readable by trusted users on the moderation board.
# 'nuked'  — the nuclear option: readable by staff only. Rules live in archive/moderation.py.
#            This is the CIVIL end state (art. 81 pr. aut., art. 212 k.k., RODO): the post
#            stops being readable, and its files are held outside the public path rather
#            than destroyed, because a copyright or defamation claim has to be defensible
#            years later and the file is the evidence.
# 'quarantined' / 'purged' — the CRIMINAL end states, and the reason this list has five
#            entries rather than three. They are written by exactly one module,
#            escalation/services.py, as a projection of the Escalation row that owns the
#            workflow; nothing else may set them. See LEGAL.md "The two takedowns".
STATUS_CHOICES = [('pending', 'Czeka na moderację'), ('published', 'Opublikowany'),
                  ('rejected', 'Odrzucony'), ('hidden', 'Ukryty'), ('nuked', 'Ukryty nuklearnie'),
                  ('quarantined', 'Kwarantanna krytyczna'), ('purged', 'Usunięty trwale')]
# Never visible to anybody through the ordinary managers, whatever else a queryset says.
CRITICAL_STATUSES = ('quarantined', 'purged')
# The same two tiers for a comment, on their own field: `is_removed` stays the author's
# own deletion tombstone, `moderation` is what a trusted user or staff did to it.
COMMENT_MODERATION_CHOICES = [('visible', 'Widoczny'), ('hidden', 'Ukryty'), ('nuked', 'Ukryty nuklearnie')]
MODERATION_ACTION_CHOICES = [('hide', 'ukrycie'), ('restore', 'przywrócenie'), ('nuke', 'ukrycie nuklearne'),
                             ('unnuke', 'przywrócenie po opcji nuklearnej'), ('publish', 'publikacja'),
                             ('reject', 'odrzucenie'), ('quarantine', 'kwarantanna krytyczna'),
                             ('purge', 'trwałe usunięcie po zgłoszeniu do NASK'),
                             ('feature', 'wyróżnienie'), ('unfeature', 'cofnięcie wyróżnienia')]
PRECISION_CHOICES = [('exact', 'dokładnie'), ('approx', 'około'),
                     ('decade', 'dekada'), ('unknown', 'nieznany')]
REACTION_CHOICES = [('lol', 'lol'), ('classic', 'klasyk'), ('wow', 'wow'), ('cringe', 'cringe')]
KIND_CHOICES = [('image', 'obraz'), ('pdf', 'PDF'), ('audio', 'audio'), ('video', 'wideo'), ('other', 'inne')]


class Category(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    emoji = models.CharField(max_length=8, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


SEX_CHOICES = [('', 'nie podano'), ('m', 'mężczyzna'), ('f', 'kobieta')]
# What the person THEMSELF said about their image (art. 81 pr. aut.). 'unknown' is the
# default and the honest one: the uploader's rights declaration on a post is the uploader's
# statement, not the person's. The other three are written by the claims flow (a confirmed
# mailbox, then a staff decision) or by staff in the admin — never by a submitter:
#   granted    photos of me may be here; the profile shows the badge, a portrait may be uploaded
#   refused    mention me if you must, but no photos
#   opted_out  take me out of the archive altogether (goes with is_listed=False)
IMAGE_CONSENT_CHOICES = [('unknown', 'nieznana'), ('granted', 'wyrażona'),
                         ('refused', 'odmówiona — bez zdjęć'), ('opted_out', 'wycofana — poza archiwum')]


class Person(models.Model):
    """Somebody the folklore is about — a lecturer, a legendary student, a janitor.
    `is_listed=False` keeps a person out of the index while their posts stay reachable;
    removal requests come in through `Report` and, once a person has claimed their entry,
    through their own consent settings.

    Modelled on the faculty's own directory (fuw.edu.pl/osoby-fuw.html), which is what the
    /ludzie page copies: a title column, a surname to file under, a unit line under the
    name, a 130 px photo or a silhouette in its place. `surname` and `sort_key` are filled
    by archive/people.py at save time — `surname` only when blank, so a correction made in
    the admin sticks. Nicknames are `aliases`: ordinary Tag rows that make a tagged post
    the person's post (see archive/people.py)."""
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=120, help_text='bez tytułu — ten idzie do osobnego pola')
    degree = models.CharField(max_length=40, blank=True,
                              help_text='tytuł/stopień, jak w spisie osób: dr, prof. dr hab., mgr inż.')
    surname = models.CharField(max_length=80, blank=True,
                               help_text='do sortowania i litery w spisie; puste = ostatni wyraz nazwy')
    sort_key = models.CharField(max_length=120, blank=True, db_index=True, editable=False)
    role = models.CharField(max_length=120, blank=True)
    unit = models.CharField(max_length=160, blank=True,
                            help_text='jednostka, jak w spisie: „Instytut Fizyki Teoretycznej, Katedra…”')
    bio = models.TextField(blank=True)
    sex = models.CharField(max_length=1, choices=SEX_CHOICES, blank=True, default='',
                           help_text='tylko po to, by dobrać sylwetkę zastępczą ze spisu osób')
    image_consent = models.CharField(max_length=10, choices=IMAGE_CONSENT_CHOICES, default='unknown')
    aliases = models.ManyToManyField('Tag', related_name='alias_of', blank=True,
                                     help_text='ksywki — wpis otagowany ksywką jest wpisem tej osoby')
    # The folded bare name, filled at save: what "is this person already here?" is asked
    # against when somebody names a person in the editor instead of picking one. Folding is
    # search.normalize_text, so „dr Anna Nowak", „Anna Nowak" and „ANNA NOWAK" are one
    # person, and a twin cannot be created by typing the same name with a different shift key.
    name_key = models.CharField(max_length=160, blank=True, db_index=True, editable=False)
    is_listed = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name='+',
                                   on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ['sort_key', 'name']

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f'{self.degree} {self.name}'.strip()

    @property
    def letter(self):
        from .people import letter_for
        return letter_for(self.surname, self.name)

    def save(self, *args, **kwargs):
        from .search import normalize_text
        from .people import derive_surname, sort_key_for
        if not self.surname:
            self.surname = derive_surname(self.name)
        self.sort_key = sort_key_for(self.surname, self.name)
        self.name_key = normalize_text(self.name)[:160]
        super().save(*args, **kwargs)


class Tag(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=60)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Subject(models.Model):
    """A university subject (*przedmiot*) — „Mechanika klasyczna", „II Pracownia fizyczna".

    A third axis next to tags and people, and it exists because the other two answered the
    question badly. „mechanika" as a free tag is one of forty spellings of itself; a person
    is who the story is ABOUT, which is not the same as what the story is FROM. A course is
    the unit a physics student actually remembers things by — you do not recall the year, you
    recall that it happened on Elektrodynamika.

    The table is seeded from the Faculty's own first- and second-cycle programmes
    (migration 0008), and anybody with an account may add one by naming it in the editor:
    `created_by` is NULL for the seeded rows and set for a named one, which is exactly what
    `/api/subjects/` uses to decide what to list (a named subject appears once it has a
    published post; a seeded one is always there, because it is an offer, not a claim).
    Duplicates are expected and are a moderator's merge in the admin — refusing a near-match
    at submission time would refuse „Mechanika klasyczna R", which is a different course.

    Unlike `Person`, nothing here is about a human being: there is no consent question, no
    opt-out, and `short` („AM1") is decoration. That is the whole reason it is a separate
    model rather than another flavour of `Tag` with a flag."""
    # 120, not the SlugField default of 50: „Elektrodynamika klasyczna z elementami klasycznej
    # teorii pola" is a real course, and a slug truncated to 50 would silently merge it with
    # whatever else starts the same way — a get_or_create keyed on a lossy slug is a merge.
    slug = models.SlugField(unique=True, max_length=120)
    name = models.CharField(max_length=120)
    short = models.CharField(max_length=20, blank=True,
                             help_text='skrót, jakim mówi o przedmiocie rocznik: AM1, MK, II Prac.')
    order = models.PositiveIntegerField(default=0, help_text='kolejność w spisie; seed numeruje wg roku studiów')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name='+',
                                   on_delete=models.SET_NULL,
                                   help_text='puste = przedmiot z programu studiów (seed/admin)')
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


def _unique_slug(model, base):
    base = slugify(base)[:60] or 'wpis'
    slug = base
    n = 2
    # `all_objects` on purpose: `objects` hides quarantined/purged posts, and a slug that
    # looks free only because the post holding it is invisible is an IntegrityError later.
    manager = getattr(model, 'all_objects', model.objects)
    while manager.filter(slug=slug).exists():
        slug = f'{base}-{n}'
        n += 1
    return slug


class PostQuerySet(models.QuerySet):
    def critical(self):
        """The rows the default manager hides. Only escalation/ and the head-admin views
        have any business calling this, and both reach it through `Post.all_objects`."""
        return self.filter(status__in=CRITICAL_STATUSES)


class PostManager(models.Manager.from_queryset(PostQuerySet)):
    """The default manager, and deliberately not a complete view of the table.

    Everything in this project that lists posts — the public API, the moderation board a
    trusted student reads, the staff admin, the search index, the sitemap, `manage.py
    shell` — goes through `Post.objects`, so `Post.objects` is where "a post in criminal
    quarantine does not exist" is cheapest to guarantee. `archive/moderation.py` also
    filters, and `escalation/visibility.py` re-checks per object; this is the third layer,
    and the only one that is on by default rather than by being remembered.

    The cost is real and is the reason `all_objects` exists next to it: a filtered default
    manager means `Post.objects.get(pk=...)` raises `DoesNotExist` for a quarantined post
    even for a head-admin, and `Meta.base_manager_name = 'all_objects'` is what keeps
    `attachment.post` and `comment.post` resolving so the escalation machinery can still
    read the row it is deciding about."""

    def get_queryset(self):
        return super().get_queryset().exclude(status__in=CRITICAL_STATUSES)


class Post(models.Model):
    slug = models.SlugField(unique=True, max_length=70, blank=True)
    title = models.CharField(max_length=200)
    category = models.ForeignKey(Category, related_name='posts', on_delete=models.PROTECT)
    format = models.CharField(max_length=8, choices=FORMAT_CHOICES, default='text')
    body = models.TextField(blank=True)
    summary = models.CharField(max_length=300, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    year_precision = models.CharField(max_length=8, choices=PRECISION_CHOICES, default='approx')
    date_note = models.CharField(max_length=120, blank=True)
    source_note = models.CharField(max_length=300, blank=True)
    source_url = models.URLField(blank=True)
    people = models.ManyToManyField(Person, related_name='posts', blank=True)
    subjects = models.ManyToManyField(Subject, related_name='posts', blank=True)
    tags = models.ManyToManyField(Tag, related_name='posts', blank=True)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     related_name='posts', on_delete=models.SET_NULL)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    related_name='+', on_delete=models.SET_NULL)
    featured = models.BooleanField(default=False)
    views = models.PositiveIntegerField(default=0)
    # The uploader's declaration (regulamin, /o-archiwum): they hold the rights or act within
    # parody/pastiche (art. 29¹ pr. aut.), and have consent for every recognisable person
    # (art. 81). Required on create; kept as evidence, never shown to readers.
    rights_confirmed = models.BooleanField(default=False)
    # Derived at save time (archive/search.py): folded prose and canonical formulas.
    search_text = models.TextField(blank=True, editable=False)
    search_math = models.TextField(blank=True, editable=False)
    # The identifying half of an art. 18 DSA report, and nothing else. A hash — which is
    # what board/models.py keeps for chat — is the right answer when the question is "same
    # visitor?", and useless when the question is the only one that matters here: WHO does
    # Dyżurnet.pl / the police ask the ISP about. Kept for SUBMITTER_IP_RETENTION_DAYS and
    # then blanked by `manage.py forget_submitter_ips`; copied into an EvidenceAuditLog
    # row at the moment of a report, which is the one place it outlives that window.
    submitter_ip = models.GenericIPAddressField(null=True, blank=True)
    submitter_user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    objects = PostManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ['-published_at', '-created_at']
        # Related descriptors (`attachment.post`, `comment.post`) and `refresh_from_db` use
        # the base manager. Pointing it at the unfiltered one keeps the escalation and
        # shred paths able to load the very rows the default manager exists to hide.
        base_manager_name = 'all_objects'

    def __str__(self):
        return self.title

    @property
    def catalog_no(self):
        return f'FUW-{self.pk:04d}' if self.pk else ''

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _unique_slug(Post, self.title)
        if self.status == 'published' and self.published_at is None:
            self.published_at = timezone.now()
        from .search import index_fields
        self.search_text, self.search_math = index_fields(self.title, self.summary, self.body, self.format)
        super().save(*args, **kwargs)


def attachment_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'bin'
    return f'attachments/{uuid.uuid4().hex}.{ext}'


class Attachment(models.Model):
    """One file on a post, stored EITHER locally under MEDIA_ROOT (`file`) OR in Cloudflare
    R2 (`storage_key`), never both. The two coexist because the local path is what a bare
    clone, the test suite and every row created before R2 use, and because a deployment
    must be able to turn R2 off again without the archive losing its pictures.

    `sha256` is not decoration: it is what a Dyżurnet.pl report is keyed on, what proves
    the file forwarded to NASK is the file that was here, and — after a purge — the only
    thing about the bytes that legally may still exist. For an R2 upload it is verified by
    R2 itself against the checksum we signed (config/r2.py), not taken on trust from the
    browser that sent it."""
    post = models.ForeignKey(Post, related_name='attachments', on_delete=models.CASCADE)
    file = models.FileField(upload_to=attachment_path, validators=[validate_upload], blank=True)
    storage_key = models.CharField(max_length=300, blank=True, db_index=True)
    sha256 = models.CharField(max_length=64, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=100, blank=True)
    original_name = models.CharField(max_length=200)
    kind = models.CharField(max_length=8, choices=KIND_CHOICES, default='other')
    caption = models.CharField(max_length=200, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    @property
    def is_remote(self) -> bool:
        return bool(self.storage_key)

    @property
    def public_url(self) -> str:
        """'' once the object has been moved off the public prefix or shredded — the
        serializer turns that into an absent URL rather than a broken one."""
        if not self.storage_key:
            return ''
        from config import r2
        return '' if r2.is_held(self.storage_key) else r2.public_url(self.storage_key)


class Reaction(models.Model):
    post = models.ForeignKey(Post, related_name='reactions', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    kind = models.CharField(max_length=8, choices=REACTION_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('post', 'user')]


class Comment(models.Model):
    post = models.ForeignKey(Post, related_name='comments', on_delete=models.CASCADE)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    parent = models.ForeignKey('self', null=True, blank=True, related_name='replies', on_delete=models.CASCADE)
    format = models.CharField(max_length=8, choices=FORMAT_CHOICES, default='text')
    body = models.TextField()
    is_removed = models.BooleanField(default=False)
    moderation = models.CharField(max_length=8, choices=COMMENT_MODERATION_CHOICES, default='visible')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


class CommentAttachment(models.Model):
    comment = models.ForeignKey(Comment, related_name='attachments', on_delete=models.CASCADE)
    file = models.FileField(upload_to=attachment_path, validators=[validate_upload])
    original_name = models.CharField(max_length=200)
    kind = models.CharField(max_length=8, choices=KIND_CHOICES, default='image')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']


class Report(models.Model):
    """"Take this down" / "this is wrong" — open to anonymous visitors, because the
    person a post is about may well not have an account here."""
    REASONS = [('privacy', 'Dotyczy mnie i chcę usunięcia'), ('wrong', 'Nieprawda / błąd'),
               ('offensive', 'Obraźliwe'), ('copyright', 'Prawa autorskie'), ('other', 'Inne')]
    post = models.ForeignKey(Post, related_name='reports', on_delete=models.CASCADE)
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    contact_email = models.EmailField(blank=True)
    reason = models.CharField(max_length=10, choices=REASONS)
    note = models.TextField(blank=True)
    # Art. 16 DSA: a notice creates 'actual knowledge' only when it names the reporter,
    # explains why the content is illegal and carries a good-faith statement. The form asks
    # for all three; a report without them is still queued (a signal is a signal), and the
    # moderator sees which ones are formal notices.
    good_faith = models.BooleanField(default=False)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class ModerationAction(models.Model):
    """Who did what to which post/comment, when, and why — the moderation board's audit
    line. Every hide/restore/nuke goes through archive/moderation.py, which writes one of
    these; the board and the detail endpoint read the newest one per target.

    `previous_status` is the state the target was in before the action (a post's `status`,
    a comment's `moderation`). It is what lets a restore put a post back where it was —
    'published' if it was live, 'pending' if it was still in the queue — instead of
    publishing something that was never approved."""
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                              related_name='moderation_actions', on_delete=models.SET_NULL)
    post = models.ForeignKey(Post, null=True, blank=True, related_name='actions', on_delete=models.CASCADE)
    comment = models.ForeignKey(Comment, null=True, blank=True, related_name='actions', on_delete=models.CASCADE)
    action = models.CharField(max_length=12, choices=MODERATION_ACTION_CHOICES)
    reason = models.TextField(blank=True)
    previous_status = models.CharField(max_length=16, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        target = self.post.catalog_no if self.post_id else f'komentarz #{self.comment_id}'
        return f'{self.get_action_display()} — {target}'


# The fields a stranger may propose changing. Deliberately scalar text and dates only:
# category, people, tags and attachments are NOT here, because each has its own shape
# (slug sets, uploaded bytes) and its own abuse surface, and "suggest an edit" is a
# different feature from "re-file this post". Named once so the serializer, the API and
# the history all agree on what a revision even is.
SUGGESTABLE_FIELDS = ('title', 'summary', 'body', 'format', 'year', 'year_precision',
                      'date_note', 'source_note', 'source_url')
SUGGESTION_STATUS = [('pending', 'Czeka'), ('accepted', 'Przyjęta'),
                     ('rejected', 'Odrzucona'), ('withdrawn', 'Wycofana')]
REVISION_SOURCE = [('author', 'edycja autora'), ('moderator', 'edycja moderacji'),
                   ('suggestion', 'przyjęta poprawka')]


class PostRevision(models.Model):
    """What the post said BEFORE a change — one row per change, never per read.

    Stored as the previous state rather than the new one, so the live `Post` row is always
    the current version and history is simply "everything it used to be", newest first.
    The alternative — a row per version including the current — means every read has to
    work out which row is live, and gets it wrong once.

    NOT public. An archive of folklore gets removal requests under art. 81 pr. aut. and
    RODO, and a public history would mean that taking somebody's name out of a post left
    it one click away in the diff — which is not removal, it is relocation. Visible to the
    post's author, to trusted moderators and to staff, who are the people who need to know
    what changed and who changed it.
    """
    post = models.ForeignKey(Post, related_name='revisions', on_delete=models.CASCADE)
    data = models.JSONField()  # the SUGGESTABLE_FIELDS as they were before this change
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   related_name='+', on_delete=models.SET_NULL)
    # Kept as text too: the account may go, the record of who changed the archive may not.
    changed_by_username = models.CharField(max_length=150, blank=True)
    source = models.CharField(max_length=10, choices=REVISION_SOURCE, default='author')
    suggestion = models.ForeignKey('EditSuggestion', null=True, blank=True,
                                   related_name='+', on_delete=models.SET_NULL)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.post_id} @ {self.created_at:%Y-%m-%d %H:%M}'


class EditSuggestion(models.Model):
    """"I think this quote is misattributed" — from anybody with an account.

    The archive's whole value is other people knowing better: a year that is wrong by two,
    a lecturer's name spelled from memory, a LaTeX source that does not compile. Those
    people are usually not the author and usually not moderators, and before this they had
    nowhere to put it but a report, which is the channel for "take this down".

    `changes` holds only the fields being changed; `base` holds what those same fields said
    when the suggestion was written. Keeping both is what makes acceptance safe: if the
    post moved on in the meantime, applying the diff blindly would silently revert somebody
    else's edit, so `decide` compares and refuses with 409 instead.
    """
    post = models.ForeignKey(Post, related_name='edit_suggestions', on_delete=models.CASCADE)
    suggested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     related_name='edit_suggestions', on_delete=models.SET_NULL)
    suggested_by_username = models.CharField(max_length=150, blank=True)
    changes = models.JSONField()
    base = models.JSONField()
    # Mandatory: a diff without a reason is a puzzle for whoever has to decide about it.
    rationale = models.TextField()
    status = models.CharField(max_length=10, choices=SUGGESTION_STATUS, default='pending')
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   related_name='+', on_delete=models.SET_NULL)
    decision_note = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.UniqueConstraint(fields=['post', 'suggested_by'], condition=Q(status='pending'),
                                    name='one_pending_suggestion_per_person_per_post'),
        ]

    def __str__(self):
        return f'#{self.pk} {self.post_id} ({self.get_status_display()})'
