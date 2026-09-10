import json

from django.contrib.auth.models import User
from rest_framework import serializers

from .models import (Attachment, Category, Comment, CommentAttachment, Person, Post,
                     Reaction, Report, Tag, REACTION_CHOICES)
from .validators import kind_for

REACTION_KINDS = [k for k, _ in REACTION_CHOICES]


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

    class Meta(PostListSerializer.Meta):
        fields = PostListSerializer.Meta.fields + ['body', 'source_note', 'source_url', 'attachments',
                                                   'my_reaction', 'can_edit', 'review_note']

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
        fields = ['id', 'author', 'author_id', 'parent', 'format', 'body', 'attachments', 'is_removed', 'created_at']
        read_only_fields = ['is_removed', 'created_at']

    def get_author(self, obj):
        return '' if obj.is_removed else _display(obj.author)

    def to_representation(self, obj):
        d = super().to_representation(obj)
        if obj.is_removed:
            d['body'] = ''
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
