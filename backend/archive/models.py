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
#            workflow; nothing else may set them. See DESIGN.md "The two takedowns".
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
                             ('purge', 'trwałe usunięcie po zgłoszeniu do NASK')]
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


class Person(models.Model):
    """Somebody the folklore is about — a lecturer, a legendary student, a janitor.
    `is_listed=False` keeps a person out of the index while their posts stay
    reachable; removal requests come in through `Report`."""
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=120, blank=True)
    bio = models.TextField(blank=True)
    is_listed = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Tag(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=60)

    class Meta:
        ordering = ['name']

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
