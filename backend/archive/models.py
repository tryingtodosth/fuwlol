"""fuw.lol — the archive.

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
STATUS_CHOICES = [('pending', 'Czeka na moderację'), ('published', 'Opublikowany'),
                  ('rejected', 'Odrzucony'), ('hidden', 'Ukryty')]
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
    while model.objects.filter(slug=slug).exists():
        slug = f'{base}-{n}'
        n += 1
    return slug


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
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    related_name='+', on_delete=models.SET_NULL)
    featured = models.BooleanField(default=False)
    views = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-published_at', '-created_at']

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
        super().save(*args, **kwargs)


def attachment_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'bin'
    return f'attachments/{uuid.uuid4().hex}.{ext}'


class Attachment(models.Model):
    post = models.ForeignKey(Post, related_name='attachments', on_delete=models.CASCADE)
    file = models.FileField(upload_to=attachment_path, validators=[validate_upload])
    original_name = models.CharField(max_length=200)
    kind = models.CharField(max_length=8, choices=KIND_CHOICES, default='other')
    caption = models.CharField(max_length=200, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']


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
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
