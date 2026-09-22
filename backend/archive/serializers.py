import re
import json

from django.contrib.auth.models import User
from rest_framework import serializers

from . import moderation as rules
from . import latexguard
from . import people as people_rules
from . import subjects as subject_rules
from .models import (Attachment, Category, Comment, CommentAttachment, Person, Post,
                     Reaction, Report, Subject, Tag, REACTION_CHOICES)
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


class AliasSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['slug', 'name']


class PersonSerializer(serializers.ModelSerializer):
    """One directory row / the profile header. `post_count`, `year_min` and `year_max`
    come from `people.annotate_people` and are simply absent when a Person is embedded in
    a post (DRF skips a read-only field the instance does not have). `name` is the bare
    name; `full_name` carries the title, the way the faculty directory prints it."""
    post_count = serializers.IntegerField(read_only=True)
    year_min = serializers.IntegerField(read_only=True)
    year_max = serializers.IntegerField(read_only=True)
    aliases = AliasSerializer(many=True, read_only=True)
    letter = serializers.CharField(read_only=True)
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Person
        fields = ['slug', 'name', 'full_name', 'degree', 'surname', 'letter', 'role', 'unit', 'bio', 'sex',
                  'image_consent', 'aliases', 'post_count', 'year_min', 'year_max']


class TagSerializer(serializers.ModelSerializer):
    post_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Tag
        fields = ['slug', 'name', 'post_count']


class SubjectSerializer(serializers.ModelSerializer):
    """One row of /przedmioty, and the three fields a post carries about its courses.
    `post_count` comes from `views._published_count` and, exactly like `PersonSerializer`'s,
    is simply absent when the Subject is embedded in a post — DRF skips a read-only field
    the instance does not have, so the post payload stays three keys wide."""
    post_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Subject
        fields = ['slug', 'name', 'short', 'post_count']


class AttachmentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = ['id', 'url', 'original_name', 'kind', 'caption', 'order']

    def get_url(self, obj):
        """'' for an attachment whose bytes are gone (shredded after a NASK report) or
        held (quarantined). The row survives so the post still knows it had a file and the
        body's `![](zdjecie.jpg)` reference still resolves to something — it just resolves
        to a removed file rather than to a broken URL."""
        if getattr(obj, 'storage_key', ''):
            return obj.public_url
        if not obj.file:
            return ''
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
    subjects = SubjectSerializer(many=True, read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    submitted_by = serializers.SerializerMethodField()
    catalog_no = serializers.CharField(read_only=True)
    cover = serializers.SerializerMethodField()
    reaction_counts = serializers.SerializerMethodField()
    comment_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Post
        fields = ['id', 'slug', 'catalog_no', 'title', 'summary', 'category', 'category_name', 'format',
                 'year', 'year_precision', 'date_note', 'people', 'subjects', 'tags', 'submitted_by', 'status',
                 'featured', 'trusted_only', 'locked', 'views', 'cover', 'reaction_counts', 'comment_count',
                 'published_at', 'created_at']

    # Whether the post is locked is public (the card says so); whether YOU may read it is
    # derived per caller. The frontend must never re-derive `locked` from `trusted_only` —
    # the author's own exception lives in `can_read_body` and nowhere else.
    locked = serializers.SerializerMethodField()

    def get_locked(self, obj):
        return not rules.can_read_body(self._user(), obj)

    def _user(self):
        req = self.context.get('request')
        return req.user if req else None

    def to_representation(self, obj):
        """A „kontrowersyjny" post keeps its place in the list and loses what it is about.

        The same shape as `CommentSerializer.to_representation` below: the row stays, the
        content goes. The filing (people, subjects, tags) goes with the body — a post is
        usually locked precisely because of whom it names, and `views._filtered` refuses to
        match those axes for the same caller, so the chip and the filter agree.

        `summary` goes because `auto_summary` builds it out of the first 200 characters of
        the body: keeping it would be theatre. The counts are zeroed because „47 × cringe"
        characterises content the caller may not read."""
        d = super().to_representation(obj)
        if not d.get('locked'):
            return d
        # Only keys this serializer actually declares — the list and the detail shapes
        # differ, and inventing a key here would put `body` on a card that has none.
        blanked = {'body': '', 'summary': '', 'source_note': '', 'source_url': '',
                   'cover': None, 'my_reaction': None, 'attachments': [],
                   'people': [], 'subjects': [], 'tags': [],
                   'reaction_counts': dict.fromkeys(REACTION_KINDS, 0), 'comment_count': 0}
        for key, empty in blanked.items():
            if key in d:
                d[key] = empty
        return d

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
    review_note = serializers.SerializerMethodField()
    moderation_notice = serializers.SerializerMethodField()
    moderation = serializers.SerializerMethodField()

    lock_notice = serializers.SerializerMethodField()

    class Meta(PostListSerializer.Meta):
        fields = PostListSerializer.Meta.fields + ['body', 'source_note', 'source_url', 'attachments',
                                                   'my_reaction', 'can_edit', 'review_note',
                                                   'can_moderate', 'moderation_notice', 'moderation',
                                                   'lock_notice']

    def get_lock_notice(self, obj):
        """The sentence the page shows in place of the body. Polish, written here, displayed
        verbatim — a refusal carries its reason."""
        return rules.LOCKED_NOTICE if not rules.can_read_body(self._user(), obj) else None

    def _trusted(self):
        # One trust lookup per serializer (the context dict is shared by a many=True list),
        # not one per post on the board.
        if '_trusted' not in self.context:
            req = self.context.get('request')
            self.context['_trusted'] = rules.is_trusted(req.user if req else None)
        return self.context['_trusted']

    def get_can_moderate(self, obj):
        return self._trusted()

    def get_review_note(self, obj):
        """A moderator's note to the author is for the author (and staff), not the public."""
        req = self.context.get('request')
        user = req.user if req else None
        if user is not None and getattr(user, 'is_authenticated', False) and (user.is_staff or obj.submitted_by_id == user.id):
            return obj.review_note
        return ''

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


class M2MInput(serializers.Field):
    """A many-to-many payload that keeps its shape until `_items` reads it.

    `CharField` cannot do this job: over multipart the value is a string, but over a JSON
    body it is a real list — and for `people` a list whose entries may be objects. A
    `CharField` rejects both with „Not a valid string" before the serializer ever sees them,
    which is why the JSON shape this class exists for was documented and did not work.

    Nothing is validated here on purpose. What a legal entry IS belongs to the rule modules
    (`people.resolve_people`, `subjects.resolve_subjects`), which is also where the refusal
    can say something useful about it; a field that pre-guessed the shape would have to
    guess it twice."""
    default_error_messages = {}

    def to_internal_value(self, data):
        return data

    def to_representation(self, value):  # write_only, so this is never reached
        return value


class PostWriteSerializer(serializers.ModelSerializer):
    """Multipart-friendly. `people`, `subjects` and `tags` arrive as a JSON list (a JSON
    *string* over multipart, a real list over a JSON body) or, still, as a comma-separated
    list of slugs — the shape the editor sent before it had pickers, kept because the API
    is a public surface and a script somebody wrote against it should not break. `files`
    are repeated form fields and `captions` a JSON list aligned to them.

    `people` is the one that carries objects as well as strings:

        ["jan-kowalski", {"name": "Anna Nowak", "degree": "dr", "role": "wykładowczyni"}]

    A string is an existing person's slug; an object names somebody who may not exist yet.
    `people.resolve_people` decides what that means — including that naming a person who
    already exists reuses them rather than minting a twin — and this serializer does not
    re-derive any of it."""
    category = serializers.SlugRelatedField(slug_field='slug', queryset=Category.objects.all())
    people = M2MInput(required=False, write_only=True)
    subjects = M2MInput(required=False, write_only=True)
    tags = M2MInput(required=False, write_only=True)
    rights_confirmed = serializers.BooleanField(required=False, write_only=True)

    class Meta:
        model = Post
        fields = ['title', 'category', 'format', 'body', 'summary', 'year', 'year_precision',
                  'date_note', 'source_note', 'source_url', 'people', 'subjects', 'tags',
                  'rights_confirmed', 'trusted_only']

    @staticmethod
    def _items(raw):
        """The three shapes one many-to-many field can arrive in, as a plain Python list
        whose entries are strings OR dicts. Kept separate from `_slugs` because only
        `people` may carry a dict, and flattening one into `str()` is how a new person
        silently became the slug "{'name': 'Anna Nowak'}"."""
        if not raw:
            return []
        if isinstance(raw, (list, tuple)):  # a JSON body, not multipart
            return list(raw)
        raw = str(raw).strip()
        if raw.startswith('['):
            try:
                parsed = json.loads(raw)
            except ValueError:
                parsed = None
            if isinstance(parsed, list):
                return parsed
        return [s.strip() for s in raw.split(',') if s.strip()]

    @classmethod
    def _slugs(cls, raw):
        """`_items` for the fields that are only ever names/slugs (tags)."""
        return [str(s) for s in cls._items(raw)]

    def _actor(self):
        req = self.context.get('request')
        return getattr(req, 'user', None)

    def validate_year(self, v):
        if v is not None and not (1900 <= v <= 2100):
            raise serializers.ValidationError('Rok spoza zakresu 1900–2100.')
        return v

    def validate(self, data):
        # On a PATCH the body may simply not be in the payload, and "absent" is not
        # "empty": reading it straight out of `data` meant that changing only the title of
        # a post with no attachments was refused as having no content at all.
        body = data['body'] if 'body' in data else (getattr(self.instance, 'body', '') or '')
        if not (body or '').strip() and not self.context.get('has_files'):
            raise serializers.ValidationError({'body': 'Wpis musi mieć treść albo plik.'})
        problem = latexguard.check_source(body or '', max_chars=latexguard.MAX_POST_CHARS)
        if problem:
            raise serializers.ValidationError({'body': problem})
        # „Kontrowersyjne" goes on freely — it only ever takes reach away. Taking it OFF is
        # a moderation decision the moment a moderator made it, or the author would answer
        # „ogranicz to" by clicking it back. `author_may_unlock` reads the audit trail;
        # there is no second flag to keep in step.
        if (self.instance is not None and 'trusted_only' in data and not data['trusted_only']
                and self.instance.trusted_only and not rules.author_may_unlock(self.instance, self._actor())):
            raise serializers.ValidationError({'trusted_only': rules.LOCKED_BY_MODERATOR})
        if self.instance is None and not data.get('rights_confirmed'):
            raise serializers.ValidationError({'rights_confirmed': 'Potwierdź, że masz prawo opublikować tę treść (regulamin w „O archiwum”).'})
        if 'summary' in data and not (data.get('summary') or '').strip():
            data['summary'] = auto_summary(body, data.get('format') or 'text')
        elif 'summary' not in data and self.instance is None:
            data['summary'] = auto_summary(body, data.get('format') or 'text')
        return data

    def _apply_m2m(self, post, data):
        """Runs inside the view's `transaction.atomic()`, which is what makes it safe for
        `resolve_people`/`resolve_subjects` to CREATE rows here rather than in `validate`:
        a refusal anywhere in this method rolls the new people and subjects back with the
        post. Doing it in `validate` would leave a proposed person behind every time a
        later field failed."""
        if 'people' in data:
            post.people.set(people_rules.resolve_people(self._items(data['people']), self._actor()))
        if 'subjects' in data:
            post.subjects.set(subject_rules.resolve_subjects(self._items(data['subjects']), self._actor()))
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

    M2M_FIELDS = ('people', 'subjects', 'tags')

    def _take_m2m(self, data):
        """Pull the many-to-many payloads out of `data` (they are not model fields) and hand
        back only the ones that were actually sent. Absent is not empty: a PATCH that does
        not mention `subjects` must leave the post's subjects alone, while `subjects=[]`
        clears them."""
        sent = {}
        for field in self.M2M_FIELDS:
            value = data.pop(field, None)
            if value is not None:
                sent[field] = value
        return sent

    def create(self, data):
        m2m = self._take_m2m(data)
        data['rights_confirmed'] = bool(data.get('rights_confirmed'))
        post = Post.objects.create(**data)
        self._apply_m2m(post, m2m)
        return post

    def update(self, post, data):
        data.pop('rights_confirmed', None)
        m2m = self._take_m2m(data)
        for k, v in data.items():
            setattr(post, k, v)
        post.save()
        self._apply_m2m(post, m2m)
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

    def validate_body(self, value):
        problem = latexguard.check_source(value or '', max_chars=latexguard.MAX_COMMENT_CHARS)
        if problem:
            raise serializers.ValidationError(problem)
        return value

    def get_author(self, obj):
        return '' if obj.is_removed else _display(obj.author)

    def to_representation(self, obj):
        """A removed or moderated comment stays in the thread as a placeholder (its id and
        `parent` keep the replies attached) with the content blanked. A trusted reader gets
        a hidden comment's real body/author back; a nuked one only staff.

        Escalation is checked independently of `moderation` — an escalated comment is
        typically still `moderation='visible'` (escalating never touches that field), so
        the ordinary hidden/nuked branch below would never catch it on its own."""
        d = super().to_representation(obj)
        req = self.context.get('request')
        user = req.user if req else None
        if obj.is_removed:
            d['body'] = ''
            d['attachments'] = []
        elif rules.is_escalated(obj) and not rules.is_head_admin(user):
            d['body'] = ''
            d['author'] = ''
            d['author_id'] = None
            d['attachments'] = []
        elif obj.moderation != 'visible' and not rules.can_see_comment(user, obj):
            d['body'] = ''
            d['author'] = ''
            d['author_id'] = None  # a placeholder names nobody
            d['attachments'] = []
        return d


class ReportSerializer(serializers.ModelSerializer):
    post = serializers.SlugRelatedField(slug_field='slug', queryset=Post.objects.all())

    def validate_post(self, post):
        # The same answer whether the slug is unknown, hidden, nuked or escalated — a
        # report endpoint must not be an oracle for what exists behind the curtain.
        req = self.context.get('request')
        if not rules.can_see_post(req.user if req else None, post):
            raise serializers.ValidationError('Nie znaleziono takiego wpisu.')
        return post

    class Meta:
        model = Report
        fields = ['id', 'post', 'contact_email', 'reason', 'note', 'good_faith', 'created_at']
        read_only_fields = ['created_at']


class MinePostSerializer(PostListSerializer):
    """/posts/mine/ — the list shape plus the moderator's note to the author, which is the
    author's own statement of reasons (art. 17 DSA) and nobody else's business."""

    class Meta(PostListSerializer.Meta):
        fields = PostListSerializer.Meta.fields + ['review_note']


class ModerationPostSerializer(PostDetailSerializer):
    """The moderator's card. Everything the detail payload has, plus the reports — and, on
    each person, whether this post is the first published thing that will ever have named
    them (`is_new`).

    That flag is the moderation half of "a person is created by naming them": a submitter
    who types „prof. Kwark Dolny" into the editor has proposed a new row in a public index
    of named human beings, and the person who decides whether that index gets the row is the
    same person who decides whether the post gets published. Without the mark the two
    decisions look like one, and the second one is invisible.

    Derived, both halves of it: `created_by_id` says somebody named them rather than staff
    or the seed, and a recount of their published posts says nobody has yet. No flag, no
    second lifecycle — publish the post and they stop being new by themselves."""
    reports = serializers.SerializerMethodField()
    people = serializers.SerializerMethodField()

    class Meta(PostDetailSerializer.Meta):
        fields = PostDetailSerializer.Meta.fields + ['reports']

    def get_people(self, obj):
        rows = list(obj.people.all())
        data = PersonSerializer(rows, many=True, context=self.context).data
        proposed = [p for p in rows if p.created_by_id]
        # One recount, and only when there is something to recount — most posts name nobody
        # new and pay nothing. `annotate_people` is the same count the directory shows, so
        # "new here" and "absent from /ludzie" cannot drift apart.
        counts = {}
        if proposed:
            counts = {p.pk: p.post_count for p in
                      people_rules.annotate_people(Person.objects.filter(pk__in=[p.pk for p in proposed]))}
        for row, person in zip(data, rows):
            row['is_new'] = bool(person.created_by_id) and not counts.get(person.pk, 0)
        return data

    def get_reports(self, obj):
        """Every trusted reader sees THAT a post was reported and why; the reporter's own
        words and contact address are for staff only — 'trusted' is any confirmed student
        address, and a 'this is about me, take it down' report names a person."""
        req = self.context.get('request')
        staff = rules.is_staff(req.user if req else None)
        return [{'id': r.id, 'reason': r.reason, 'created_at': r.created_at,
                 'note': r.note if staff else '', 'contact_email': r.contact_email if staff else '',
                 # a formal notice in the sense of art. 16 DSA: reporter named + good-faith statement
                 'formal': bool(r.good_faith and (r.contact_email or r.reporter_id))}
                for r in obj.reports.filter(resolved=False)]


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
