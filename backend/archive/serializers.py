import re
import json

from django.contrib.auth.models import User
from rest_framework import serializers

from . import moderation as rules
from .models import (Attachment, Category, Comment, CommentAttachment, Person, Post,
                     Reaction, Report, Tag, REACTION_CHOICES)
from .validators import kind_for

HIDDEN_NOTICE = 'Ten wpis jest ukryty — widzą go tylko zweryfikowani użytkownicy.'
NUKED_NOTICE = 'Ten wpis jest ukryty nuklearnie — widzi go tylko administracja.'

REACTION_KINDS = [k for k, _ in REACTION_CHOICES]

MATH_RE = re.compile(r'\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$[^$\n]+\$')


def auto_summary(body, fmt, limit=200):
    """A one-line teaser from the body when the author wrote none: maths KEPT as `$…$`
    (summaries are typeset wherever they show, MathText.svelte), display maths made inline,
    LaTeX/Markdown syntax stripped outside maths, clipped at a word — never inside a formula."""
    s = re.sub(r'\$\$([\s\S]*?)\$\$|\\\[([\s\S]*?)\\\]|\\\(([\s\S]*?)\\\)',
               lambda m: ' $' + (m.group(1) or m.group(2) or m.group(3) or '').strip() + '$ ', body)
    parts = re.split(r'(\$[^$\n]*\$)', s)  # odd indexes are maths, left untouched
    s = ''.join(part if i % 2 else _strip_syntax(part, fmt) for i, part in enumerate(parts))
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'\s+([.,;:!?)])', r'\1', s)
    if len(s) > limit:
        cut = s[:limit]
        if cut.count('$') % 2:  # do not cut inside a formula
            cut = cut[:cut.rfind('$')]
        s = (cut[:cut.rfind(' ')] if ' ' in cut else cut).rstrip() + '…'
    return s


def _strip_syntax(s, fmt):
    if fmt == 'latex':
        s = re.sub(r'(^|[^\\])%.*$', r'\1', s, flags=re.M)
        s = re.sub(r'\\(begin|end|documentclass|usepackage|includegraphics|label|ref)\s*(\[[^\]]*\])?\s*\{[^}]*\}', ' ', s)
        s = re.sub(r'\\[a-zA-Z@]+\*?', ' ', s)
        s = re.sub(r'[{}&~^_\\]', ' ', s)
    else:
        s = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', s)
        s = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', s)
        s = re.sub(r'^\s{0,3}(#{1,6}\s+|>\s?|[-*+]\s+)', '', s, flags=re.M)
        s = re.sub(r'`{1,3}|\*\*|__|\*|_', '', s)
    return s


class CategorySerializer(serializers.ModelSerializer):
    post_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ['slug', 'name', 'description', 'emoji', 'post_count']


class PersonSerializer(serializers.ModelSerializer):
    post_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Person
        fields = ['slug', 'name', 'role', 'bio', 'post_count']


class TagSerializer(serializers.ModelSerializer):
    post_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Tag
        fields = ['slug', 'name', 'post_count']


class AttachmentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = ['id', 'url', 'original_name', 'kind', 'caption', 'order']

    def get_url(self, obj):
        req = self.context.get('request')
        return req.build_absolute_uri(obj.file.url) if req else obj.file.url


class CommentAttachmentSerializer(AttachmentSerializer):
    class Meta(AttachmentSerializer.Meta):
        model = CommentAttachment
        fields = ['id', 'url', 'original_name', 'kind', 'order']


def _display(user):
    return user.username if user else ''


class PostListSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(slug_field='slug', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    people = PersonSerializer(many=True, read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    submitted_by = serializers.SerializerMethodField()
    catalog_no = serializers.CharField(read_only=True)
    cover = serializers.SerializerMethodField()
    reaction_counts = serializers.SerializerMethodField()
    comment_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Post
        fields = ['id', 'slug', 'catalog_no', 'title', 'summary', 'category', 'category_name', 'format',
                 'year', 'year_precision', 'date_note', 'people', 'tags', 'submitted_by', 'status',
                 'featured', 'views', 'cover', 'reaction_counts', 'comment_count', 'published_at', 'created_at']

    def get_submitted_by(self, obj):
        return _display(obj.submitted_by)

    def get_cover(self, obj):
        for a in obj.attachments.all():
            if a.kind == 'image':
                return AttachmentSerializer(a, context=self.context).data['url']
        return None

    def get_reaction_counts(self, obj):
        counts = dict.fromkeys(REACTION_KINDS, 0)
        for r in obj.reactions.all():
            counts[r.kind] = counts.get(r.kind, 0) + 1
        return counts


class PostDetailSerializer(PostListSerializer):
    attachments = AttachmentSerializer(many=True, read_only=True)
    my_reaction = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_moderate = serializers.SerializerMethodField()
    moderation_notice = serializers.SerializerMethodField()
    moderation = serializers.SerializerMethodField()

    class Meta(PostListSerializer.Meta):
        fields = PostListSerializer.Meta.fields + ['body', 'source_note', 'source_url', 'attachments',
                                                   'my_reaction', 'can_edit', 'review_note',
                                                   'can_moderate', 'moderation_notice', 'moderation']

    def _trusted(self):
        # One trust lookup per serializer (the context dict is shared by a many=True list),
        # not one per post on the board.
        if '_trusted' not in self.context:
            req = self.context.get('request')
            self.context['_trusted'] = rules.is_trusted(req.user if req else None)
        return self.context['_trusted']

    def get_can_moderate(self, obj):
        return self._trusted()

    def get_moderation_notice(self, obj):
        if obj.status == 'hidden':
            return HIDDEN_NOTICE
        if obj.status == 'nuked':
            return NUKED_NOTICE
        return None

    def get_moderation(self, obj):
        """The newest hide/nuke line (who, when, why) — for trusted readers only. The author
        of a hidden post sees the notice above, not the reason: a reason may name the
        person who asked for the takedown."""
        if obj.status not in ('hidden', 'nuked') or not self._trusted():
            return None
        return rules.action_block(obj, obj.status)

    def get_my_reaction(self, obj):
        req = self.context.get('request')
        if not req or not req.user.is_authenticated:
            return None
        r = next((r for r in obj.reactions.all() if r.user_id == req.user.id), None)
        return r.kind if r else None

    def get_can_edit(self, obj):
        req = self.context.get('request')
        u = req.user if req else None
        return bool(u and u.is_authenticated and (u.is_staff or obj.submitted_by_id == u.id))


class PostWriteSerializer(serializers.ModelSerializer):
    """Multipart-friendly: `people`/`tags` arrive as comma-separated slugs (or a JSON
    list), `files` as repeated form fields, `captions` as a JSON list aligned to them."""
    category = serializers.SlugRelatedField(slug_field='slug', queryset=Category.objects.all())
    people = serializers.CharField(required=False, allow_blank=True, write_only=True)
    tags = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = Post
        fields = ['title', 'category', 'format', 'body', 'summary', 'year', 'year_precision',
                  'date_note', 'source_note', 'source_url', 'people', 'tags']

    @staticmethod
    def _slugs(raw):
        if not raw:
            return []
        raw = raw.strip()
        if raw.startswith('['):
            try:
                return [str(s) for s in json.loads(raw)]
            except ValueError:
                pass
        return [s.strip() for s in raw.split(',') if s.strip()]

    def validate_year(self, v):
        if v is not None and not (1900 <= v <= 2100):
            raise serializers.ValidationError('Rok spoza zakresu 1900–2100.')
        return v

    def validate(self, data):
        if not (data.get('body') or '').strip() and not self.context.get('has_files'):
            raise serializers.ValidationError({'body': 'Wpis musi mieć treść albo plik.'})
        if 'summary' in data and not (data.get('summary') or '').strip():
            data['summary'] = auto_summary(data.get('body') or '', data.get('format') or 'text')
        elif 'summary' not in data and self.instance is None:
            data['summary'] = auto_summary(data.get('body') or '', data.get('format') or 'text')
        return data

    def _apply_m2m(self, post, data):
        if 'people' in data:
            post.people.set(Person.objects.filter(slug__in=self._slugs(data['people'])))
        if 'tags' in data:
            tags = []
            for s in self._slugs(data['tags']):
                from django.utils.text import slugify
                slug = slugify(s)[:60]
                if not slug:
                    continue
                tag, _ = Tag.objects.get_or_create(slug=slug, defaults={'name': s[:60]})
                tags.append(tag)
            post.tags.set(tags)

    def create(self, data):
        people, tags = data.pop('people', None), data.pop('tags', None)
        post = Post.objects.create(**data)
        self._apply_m2m(post, {k: v for k, v in [('people', people), ('tags', tags)] if v is not None})
        return post

    def update(self, post, data):
        people, tags = data.pop('people', None), data.pop('tags', None)
        for k, v in data.items():
            setattr(post, k, v)
        post.save()
        self._apply_m2m(post, {k: v for k, v in [('people', people), ('tags', tags)] if v is not None})
        return post


class CommentSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()
    author_id = serializers.IntegerField(read_only=True)
    attachments = CommentAttachmentSerializer(many=True, read_only=True)
    parent = serializers.PrimaryKeyRelatedField(queryset=Comment.objects.all(), required=False, allow_null=True)

    class Meta:
        model = Comment
        fields = ['id', 'author', 'author_id', 'parent', 'format', 'body', 'attachments', 'is_removed',
                  'moderation', 'created_at']
        read_only_fields = ['is_removed', 'moderation', 'created_at']

    def get_author(self, obj):
        return '' if obj.is_removed else _display(obj.author)

    def to_representation(self, obj):
        """A removed or moderated comment stays in the thread as a placeholder (its id and
        `parent` keep the replies attached) with the content blanked. A trusted reader gets
        a hidden comment's real body/author back; a nuked one only staff."""
        d = super().to_representation(obj)
        req = self.context.get('request')
        if obj.is_removed:
            d['body'] = ''
            d['attachments'] = []
        elif obj.moderation != 'visible' and not rules.can_see_comment(req.user if req else None, obj):
            d['body'] = ''
            d['author'] = ''
            d['author_id'] = None  # a placeholder names nobody
            d['attachments'] = []
        return d


class ReportSerializer(serializers.ModelSerializer):
    post = serializers.SlugRelatedField(slug_field='slug', queryset=Post.objects.all())

    class Meta:
        model = Report
        fields = ['id', 'post', 'contact_email', 'reason', 'note', 'created_at']
        read_only_fields = ['created_at']


class ModerationPostSerializer(PostDetailSerializer):
    reports = serializers.SerializerMethodField()

    class Meta(PostDetailSerializer.Meta):
        fields = PostDetailSerializer.Meta.fields + ['reports']

    def get_reports(self, obj):
        return [{'id': r.id, 'reason': r.reason, 'note': r.note, 'contact_email': r.contact_email,
                 'created_at': r.created_at} for r in obj.reports.filter(resolved=False)]


# --- the moderation board --------------------------------------------------------------

def board_post_payload(post, request):
    """One board row for a post. Hidden: the full moderation payload plus the audit line.
    Nuked, for anybody who is not staff: ONLY the stub — id, catalog number, status, and
    who/when/why — no title, no body, no files, not even the slug."""
    block = rules.action_block(post, post.status)
    if post.status == 'nuked' and not rules.is_staff(request.user):
        return {'id': post.id, 'catalog_no': post.catalog_no, 'status': 'nuked',
                'moderation': {'actor': block['actor'], 'reason': block['reason'], 'at': block['at']}}
    d = ModerationPostSerializer(post, context={'request': request}).data
    d['moderation'] = block
    return d


def board_comment_payload(comment, request):
    """One board row for a comment; the CommentSerializer already blanks what the caller
    may not see. Nuked, for non-staff: {id, post_id, moderation} and nothing else."""
    block = rules.action_block(comment, comment.moderation)
    if comment.moderation == 'nuked' and not rules.is_staff(request.user):
        return {'id': comment.id, 'post_id': comment.post_id,
                'moderation': {'actor': block['actor'], 'reason': block['reason'], 'at': block['at']}}
    d = CommentSerializer(comment, context={'request': request}).data
    d['post_id'] = comment.post_id
    # Where the comment lives — only if the reader may see that post at all (a hidden
    # comment on a nuked post must not leak the post's title to a trusted reader).
    if rules.can_see_post(request.user, comment.post):
        d['post_slug'], d['post_title'] = comment.post.slug, comment.post.title
    d['moderation'] = block
    return d
