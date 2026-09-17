import math
import random

from django.conf import settings
from django.db import transaction
from django.db.models import Count, F, Max, Min, OuterRef, Prefetch, Q, Subquery
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from escalation.views import escalate_and_respond

from . import moderation as rules
from .models import (Attachment, Category, Comment, CommentAttachment, ModerationAction, Person, Post,
                     Reaction, Report, Tag)
from .serializers import (CategorySerializer, CommentSerializer, ModerationPostSerializer,
                          PersonSerializer, PostDetailSerializer, PostListSerializer,
                          PostWriteSerializer, ReportSerializer, TagSerializer, REACTION_KINDS,
                          board_comment_payload, board_post_payload)
from .validators import kind_for, strip_image_metadata, validate_upload

PUBLISHED = Q(status='published')
# Newest audit line first, with the actor already joined — for the board and the action responses.
ACTIONS_PREFETCH = Prefetch('actions', queryset=ModerationAction.objects.select_related('actor'))


def _not_escalated(qs, post_field=None, user=None):
    """The one choke point almost every Post/Comment queryset in this file runs through
    (post_queryset/comment_queryset build on this). Escalated rows are excluded for
    everybody except head-admin — who still reviews them primarily through the escalation
    app's frozen evidence (escalation/views.py), but is not structurally blocked from the
    live endpoints either, the same as `visible_posts_q`/`can_see_post`.
    `post_field` additionally excludes rows whose *post* (not the row itself) is escalated —
    for comments, which live under a post that might be the escalated one."""
    from escalation.visibility import active_escalation_ids, is_head_admin
    if is_head_admin(user):
        return qs
    qs = qs.exclude(pk__in=active_escalation_ids(qs.model))
    if post_field:
        qs = qs.exclude(**{f'{post_field}__in': active_escalation_ids(Post)})
    return qs


def _escalated_comment_ids():
    from escalation.visibility import active_escalation_ids
    return active_escalation_ids(Comment)


def post_queryset(user=None):
    return _not_escalated(Post.objects.select_related('category', 'submitted_by')
            .prefetch_related('people', 'tags', 'attachments', 'reactions')
            # a moderated comment is a placeholder in the thread, not a comment on the card
            .annotate(comment_count=Count('comments', filter=Q(comments__is_removed=False,
                                                                comments__moderation='visible')
                                          & ~Q(comments__pk__in=_escalated_comment_ids()), distinct=True)),
            user=user)


def post_for_board(pk):
    return post_queryset().prefetch_related(ACTIONS_PREFETCH).get(pk=pk)


def comment_queryset(user=None):
    return _not_escalated(Comment.objects.select_related('author', 'post')
                          .prefetch_related('attachments', ACTIONS_PREFETCH), post_field='post_id', user=user)


def _published_count(qs, rel='posts'):
    from escalation.visibility import active_escalation_ids
    # a tag/person/category whose only post is under escalation must not count it —
    # the count would be the one place left that says the post exists
    cond = Q(**{f'{rel}__status': 'published'}) & ~Q(**{f'{rel}__pk__in': active_escalation_ids(Post)})
    return qs.annotate(post_count=Count(rel, filter=cond))


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CategorySerializer

    def get_queryset(self):
        return _published_count(Category.objects.all())

    lookup_field = 'slug'
    pagination_class = None


class PersonViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PersonSerializer

    def get_queryset(self):
        return _published_count(Person.objects.filter(is_listed=True))

    lookup_field = 'slug'
    pagination_class = None


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TagSerializer

    def get_queryset(self):
        return _published_count(Tag.objects.all()).filter(post_count__gt=0)

    lookup_field = 'slug'
    pagination_class = None


class FixedScopeThrottle(ScopedRateThrottle):
    """A ScopedRateThrottle whose scope is FIXED at construction. The stock class reads the
    scope from `view.throttle_scope` inside allow_request, so an instance given `.scope`
    by hand and returned from get_throttles() on a view without that attribute allowed
    everything — which is exactly what happened to post_create/escalate here until a
    test asked. Per-action scopes on one ViewSet need this."""

    def __init__(self, scope):
        self.scope = scope
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)

    def allow_request(self, request, view):
        # SimpleRateThrottle.allow_request, minus the view lookup
        if self.rate is None:
            return True
        self.key = self.get_cache_key(request, view)
        if self.key is None:
            return True
        self.history = self.cache.get(self.key, [])
        self.now = self.timer()
        while self.history and self.history[-1] <= self.now - self.duration:
            self.history.pop()
        if len(self.history) >= self.num_requests:
            return self.throttle_failure()
        return self.throttle_success()


def _validate_files(files, limit):
    if len(files) > limit:
        raise ValidationError({'files': f'Najwyżej {limit} plików.'})
    cleaned = []
    for f in files:
        try:
            validate_upload(f)
        except Exception as e:  # django ValidationError → DRF 400
            msgs = getattr(e, 'messages', None) or [str(e)]
            raise ValidationError({'files': [f'{f.name}: {m}' for m in msgs]})
        cleaned.append(strip_image_metadata(f))
    return cleaned


class PostViewSet(viewsets.ModelViewSet):
    lookup_field = 'slug'

    def get_throttles(self):
        if self.action == 'create':
            return [FixedScopeThrottle('post_create')]
        if self.action == 'escalate':
            return [FixedScopeThrottle('escalate')]
        if self.action == 'comments' and self.request.method == 'POST':
            # a comment carries up to 3 × 25 MB of images; the global per-user rate alone
            # would let one account write gigabytes a minute
            return [FixedScopeThrottle('comment_create')]
        return super().get_throttles()

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy', 'react', 'mine'):
            return [IsAuthenticated()]
        if self.action in ('queue', 'moderate'):
            return [IsAdminUser()]
        if self.action in ('hide', 'restore', 'nuke', 'escalate'):
            return [rules.IsTrusted()]
        return []

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return PostWriteSerializer
        if self.action == 'list' or self.action == 'mine':
            return PostListSerializer
        if self.action == 'queue':
            return ModerationPostSerializer
        return PostDetailSerializer

    def _base(self):
        return post_queryset(self.request.user)

    def get_queryset(self):
        qs = self._base()
        u = self.request.user
        if self.action in ('retrieve', 'update', 'partial_update', 'destroy', 'moderate', 'comments'):
            # who may read what — the one rule, in archive/moderation.py
            return qs.filter(rules.visible_posts_q(u))
        if self.action in ('hide', 'restore', 'nuke', 'escalate'):
            # Trusted users (the permission class has already excluded everybody else) may
            # also RESOLVE a nuked post here, so that "restore" on one answers 403 — the
            # rules' honest refusal — instead of pretending it does not exist. They still
            # cannot reach somebody else's pending or rejected submission.
            return qs.filter(rules.visible_posts_q(u) | Q(status='nuked'))
        if self.action == 'mine':
            qs = qs.filter(submitted_by=u).order_by('-created_at')
            # nuked content is staff-only, its own author included
            return qs if u.is_staff else qs.exclude(status='nuked')
        if self.action == 'queue':
            return qs.filter(Q(status='pending') | Q(reports__resolved=False)).distinct().order_by('created_at')
        return self._filtered(qs.filter(PUBLISHED))

    def _filtered(self, qs):
        p = self.request.query_params
        if p.get('q'):
            q = p['q'].strip()
            qs = qs.filter(Q(title__icontains=q) | Q(summary__icontains=q) | Q(body__icontains=q)
                           | Q(tags__name__icontains=q) | Q(people__name__icontains=q)).distinct()
        if p.get('category'):
            qs = qs.filter(category__slug=p['category'])
        if p.get('tag'):
            qs = qs.filter(tags__slug=p['tag'])
        if p.get('person'):
            qs = qs.filter(people__slug=p['person'])
        if p.get('format') in ('text', 'latex'):
            qs = qs.filter(format=p['format'])
        if p.get('featured'):
            qs = qs.filter(featured=True)
        if p.get('before'):  # the time machine: the archive as it stood at the end of that day
            from datetime import datetime, time, timedelta
            try:
                day = datetime.strptime(p['before'][:10], '%Y-%m-%d').date()
                cutoff = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))
                qs = qs.filter(published_at__lt=cutoff)
            except ValueError:
                pass
        for key, lookup in (('year_from', 'year__gte'), ('year_to', 'year__lte'), ('year', 'year')):
            if p.get(key, '').isdigit():
                qs = qs.filter(**{lookup: int(p[key])})
        sort = p.get('sort', 'new')
        if sort == 'top':
            qs = qs.annotate(n_react=Count('reactions', distinct=True)).order_by('-n_react', '-published_at')
        elif sort == 'views':
            qs = qs.order_by('-views')
        elif sort == 'old':
            qs = qs.order_by('year', 'published_at')
        elif sort == 'year':
            qs = qs.order_by('-year', '-published_at')
        else:
            qs = qs.order_by('-published_at')
        return qs

    def retrieve(self, request, *args, **kwargs):
        post = self.get_object()
        if post.status == 'published':
            Post.objects.filter(pk=post.pk).update(views=F('views') + 1)
            post.views += 1
        return Response(self.get_serializer(post).data)

    def _files(self, request):
        return request.FILES.getlist('files')

    def _attach(self, post, files, captions):
        for i, f in enumerate(files):
            Attachment.objects.create(post=post, file=f, original_name=f.name[:200], kind=kind_for(f.name),
                                      caption=(captions[i] if i < len(captions) else '')[:200], order=i)

    def _captions(self, request):
        import json
        raw = request.data.get('captions')
        if not raw:
            return []
        if isinstance(raw, (list, tuple)):  # a JSON body, not multipart
            return [str(c) for c in raw]
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return []
        return [str(c) for c in parsed] if isinstance(parsed, list) else []

    def create(self, request, *args, **kwargs):
        files = _validate_files(self._files(request), settings.MAX_FILES_PER_POST)
        s = PostWriteSerializer(data=request.data, context={'request': request, 'has_files': bool(files)})
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            # Staff publish straight away — and so does a TRUSTED user (a confirmed FUW/UW/PAN
            # address): a verified member of the community is who the queue exists to check
            # for, so this is a small, deliberate widening. Everybody else waits for a moderator.
            post = s.save(submitted_by=request.user,
                          status='published' if rules.is_trusted(request.user) else 'pending')
            self._attach(post, files, self._captions(request))
        post = self._base().get(pk=post.pk)
        return Response(PostDetailSerializer(post, context={'request': request}).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        post = self.get_object()
        if not request.user.is_staff and post.submitted_by_id != request.user.id:
            raise PermissionDenied()
        if not request.user.is_staff and post.status == 'published':
            raise PermissionDenied('Opublikowany wpis może zmienić tylko moderator — zgłoś poprawkę w komentarzu.')
        if not request.user.is_staff and post.status not in ('pending', 'rejected'):
            # hidden: it is on the moderation board as evidence of what was taken down
            raise PermissionDenied('Ukryty wpis może zmienić tylko moderator.')
        files = _validate_files(self._files(request), settings.MAX_FILES_PER_POST)
        remove = [int(x) for x in request.data.getlist('remove_attachments') if str(x).isdigit()] \
            if hasattr(request.data, 'getlist') else []
        s = PostWriteSerializer(post, data=request.data, partial=True,
                                context={'request': request, 'has_files': bool(files) or post.attachments.exists()})
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            post = s.save()
            if remove:
                post.attachments.filter(id__in=remove).delete()
            if post.attachments.count() + len(files) > settings.MAX_FILES_PER_POST:
                raise ValidationError({'files': f'Najwyżej {settings.MAX_FILES_PER_POST} plików.'})
            self._attach(post, files, self._captions(request))
            if not request.user.is_staff and post.status == 'rejected':
                post.status = 'pending'  # an edited rejection goes back to the queue
                post.save(update_fields=['status'])
        post = self._base().get(pk=post.pk)
        return Response(PostDetailSerializer(post, context={'request': request}).data)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        post = self.get_object()
        # An author may withdraw their own submission while it is still in the queue (or was
        # rejected). Not a published one, and not a hidden one either: a hidden post is
        # what the moderation board is FOR, and deleting it would erase the evidence.
        if not request.user.is_staff and not (post.submitted_by_id == request.user.id
                                              and post.status in ('pending', 'rejected')):
            raise PermissionDenied()
        post.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False)
    def random(self, request):
        qs = self._filtered(self._base().filter(PUBLISHED))
        ids = list(qs.values_list('pk', flat=True))
        if not ids:
            return Response({'detail': 'Archiwum jest puste.'}, status=status.HTTP_404_NOT_FOUND)
        post = self._base().get(pk=random.choice(ids))
        return Response(PostDetailSerializer(post, context={'request': request}).data)

    @action(detail=False)
    def timeline(self, request):
        rows = (self._base().filter(PUBLISHED, year__isnull=False).values('year')
                .annotate(count=Count('id')).order_by('year'))
        undated = self._base().filter(PUBLISHED, year__isnull=True).count()
        return Response({'years': list(rows), 'undated': undated})

    @action(detail=False)
    def stats(self, request):
        pub = self._base().filter(PUBLISHED)
        years = pub.filter(year__isnull=False).aggregate(lo=Min('year'), hi=Max('year'))
        return Response({'posts': pub.count(), 'people': Person.objects.filter(is_listed=True).count(),
                         'tags': Tag.objects.count(), 'attachments': Attachment.objects.filter(post__in=pub).count(),
                         'year_min': years['lo'], 'year_max': years['hi'],
                         'pending': Post.objects.filter(status='pending').count()})

    @action(detail=False)
    def mine(self, request):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @action(detail=True, methods=['post', 'delete'])
    def react(self, request, slug=None):
        post = self.get_object()
        if request.method == 'DELETE':
            Reaction.objects.filter(post=post, user=request.user).delete()
        else:
            kind = request.data.get('kind')
            if kind not in REACTION_KINDS:
                raise ValidationError({'kind': 'Nieznana reakcja.'})
            Reaction.objects.update_or_create(post=post, user=request.user, defaults={'kind': kind})
        post = self._base().get(pk=post.pk)
        d = PostDetailSerializer(post, context={'request': request}).data
        return Response({'reaction_counts': d['reaction_counts'], 'my_reaction': d['my_reaction']})

    @action(detail=True, methods=['get', 'post'])
    def comments(self, request, slug=None):
        post = self.get_object()
        if request.method == 'GET':
            qs = post.comments.select_related('author').prefetch_related('attachments')
            return Response(CommentSerializer(qs, many=True, context={'request': request}).data)
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        if post.status != 'published':  # a hidden/nuked post takes no new comments — 404, like the public sees it
            return Response(status=status.HTTP_404_NOT_FOUND)
        files = _validate_files(self._files(request), 3)
        for f in files:
            if kind_for(f.name) != 'image':
                raise ValidationError({'files': 'Do komentarza można dodać tylko obrazy.'})
        s = CommentSerializer(data=request.data, context={'request': request})
        s.is_valid(raise_exception=True)
        parent = s.validated_data.get('parent')
        if parent is not None and (parent.post_id != post.pk or rules.is_escalated(parent)):
            raise ValidationError({'parent': 'Ten komentarz należy do innego wpisu.'})
        if not (s.validated_data.get('body') or '').strip() and not files:
            raise ValidationError({'body': 'Komentarz musi mieć treść albo obraz.'})
        with transaction.atomic():
            c = s.save(post=post, author=request.user)
            for i, f in enumerate(files):
                CommentAttachment.objects.create(comment=c, file=f, original_name=f.name[:200], kind='image', order=i)
        return Response(CommentSerializer(c, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @action(detail=False)
    def queue(self, request):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @action(detail=True, methods=['post'])
    def moderate(self, request, slug=None):
        """Staff: {decision: publish|reject|hide|nuke|feature|unfeature|resolve_reports, note}.
        hide/nuke go through the rules module like everybody else's, so they leave an audit
        line; publish/reject write one too, so the board can show a post's whole history."""
        post = self.get_object()
        rules.require_not_escalated(post)
        decision = request.data.get('decision')
        note = (request.data.get('note') or '')[:2000]
        previous = post.status
        if decision == 'publish':
            post.status, post.review_note, post.reviewed_by = 'published', note, request.user
            if post.published_at is None:
                post.published_at = timezone.now()
            post.save()
            rules.record('publish', request.user, post=post, reason=note, previous_status=previous)
        elif decision == 'reject':
            post.status, post.review_note, post.reviewed_by = 'rejected', note, request.user
            post.save()
            post.reports.update(resolved=True)
            rules.record('reject', request.user, post=post, reason=note, previous_status=previous)
        elif decision in ('hide', 'nuke'):
            post.review_note = note
            post.save(update_fields=['review_note'])
            (rules.hide_post if decision == 'hide' else rules.nuke_post)(post, request.user, note)
        elif decision in ('feature', 'unfeature'):
            post.featured = decision == 'feature'
            post.save(update_fields=['featured'])
        elif decision == 'resolve_reports':
            post.reports.update(resolved=True)
        else:
            raise ValidationError({'decision': 'Nieznana decyzja.'})
        post = self._base().get(pk=post.pk)
        return Response(ModerationPostSerializer(post, context={'request': request}).data)

    # --- the trusted tier: hide / restore / nuke ---------------------------------------

    def _reason(self, request):
        return (request.data.get('reason') or '') if hasattr(request.data, 'get') else ''

    @action(detail=True, methods=['post'])
    def hide(self, request, slug=None):
        """POST {reason?} — off the public page, onto the board. Resolves the post's open reports."""
        post = self.get_object()
        rules.hide_post(post, request.user, self._reason(request))
        return Response(board_post_payload(post_for_board(post.pk), request))

    @action(detail=True, methods=['post'])
    def restore(self, request, slug=None):
        """Back to where it was before it was hidden. A nuked post: staff only (403 otherwise)."""
        post = self.get_object()
        rules.restore_post(post, request.user)
        post = self._base().get(pk=post.pk)
        return Response(PostDetailSerializer(post, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def nuke(self, request, slug=None):
        """POST {reason} — the nuclear option; a reason is REQUIRED (400 without). From here on
        only staff can read the post; the response is whatever the caller may still see."""
        post = self.get_object()
        rules.nuke_post(post, request.user, self._reason(request))
        return Response(board_post_payload(post_for_board(post.pk), request))

    @action(detail=True, methods=['post'])
    def escalate(self, request, slug=None):
        """POST {reason} — report to NASK. A reason is REQUIRED. From this call on the post
        is invisible to EVERYONE but head-admin, staff included, until they decide
        (escalation.services.decide_escalation) — see archive/moderation.py's
        `require_not_escalated` for why every other moderation action refuses meanwhile."""
        return escalate_and_respond(request, self.get_object())


class CommentDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        c = Comment.objects.select_related('post').filter(pk=pk).first()
        if c is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        # escalated (the comment or its post): frozen for the author too — the one
        # mutation path that used to bypass require_not_escalated
        if not rules.is_head_admin(request.user) and (rules.is_escalated(c) or rules.is_escalated(c.post)):
            return Response(status=status.HTTP_404_NOT_FOUND)
        if not (request.user.is_staff or c.author_id == request.user.id):
            raise PermissionDenied()
        c.is_removed = True
        c.save(update_fields=['is_removed'])
        c.attachments.all().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CommentModerationView(APIView):
    """POST /api/comments/<id>/hide/ | /restore/ | /nuke/ | /escalate/ — the same rules as
    for a post."""
    permission_classes = [rules.IsTrusted]

    def get_throttles(self):
        if self.kwargs.get('verb') == 'escalate':
            return [FixedScopeThrottle('escalate')]
        return []

    def post(self, request, pk, verb):
        c = Comment.objects.select_related('author', 'post').filter(pk=pk).first()
        if c is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        # Escalated (the comment or its post) is checked BEFORE the nuked-post bypass below
        # — that bypass exists so a trusted user can reach a nuked comment and get a real
        # 403 instead of a 404, but an escalation must never be reachable that way either.
        if not rules.is_head_admin(request.user) and (rules.is_escalated(c.post) or rules.is_escalated(c)):
            return Response(status=status.HTTP_404_NOT_FOUND)
        # The comment's post must be one the actor may see. A nuked post's comments are
        # resolved anyway so the rules can answer 403 (staff only) rather than a 404.
        if not (rules.can_see_post(request.user, c.post) or c.post.status == 'nuked'):
            return Response(status=status.HTTP_404_NOT_FOUND)
        reason = request.data.get('reason') if hasattr(request.data, 'get') else ''
        if verb == 'hide':
            rules.hide_comment(c, request.user, reason)
        elif verb == 'nuke':
            rules.nuke_comment(c, request.user, reason)
        elif verb == 'escalate':
            return escalate_and_respond(request, c)
        else:
            rules.restore_comment(c, request.user)
        return Response(board_comment_payload(comment_queryset().get(pk=c.pk), request))


class ModerationBoardView(APIView):
    """GET /api/moderation/board/?status=hidden|nuked&kind=posts|comments&page=N

    Everything taken off the public page, newest action first, for trusted users and
    staff. One page (20) is cut from the merged, date-sorted stream of posts and comments
    and then split into the two lists, so `page` means the same thing whatever `kind` says.
    What a row contains depends on who is asking — see serializers.board_post_payload."""
    permission_classes = [rules.IsTrusted]
    page_size = 20

    @staticmethod
    def _last_action_at(**target):
        return Subquery(ModerationAction.objects.filter(**target)
                        .order_by('-created_at', '-id').values('created_at')[:1])

    def get(self, request):
        p = request.query_params
        statuses = [p['status']] if p.get('status') in ('hidden', 'nuked') else ['hidden', 'nuked']
        kinds = [p['kind']] if p.get('kind') in ('posts', 'comments') else ['posts', 'comments']
        staff = rules.is_staff(request.user)
        head_admin = rules.is_head_admin(request.user)

        rows = []  # (last action time, kind, pk) — light, so the whole board can be sorted
        if 'posts' in kinds:
            qs = Post.objects.filter(status__in=statuses).annotate(last_at=self._last_action_at(post=OuterRef('pk')))
            if not head_admin:
                # An escalated post vanishes from the board too, for staff and trusted
                # alike — not even a stub. See escalation/visibility.py.
                from escalation.visibility import active_escalation_ids
                qs = qs.exclude(pk__in=active_escalation_ids(Post))
            rows += [(at, 'posts', pk) for pk, at in qs.values_list('pk', 'last_at')]
        if 'comments' in kinds:
            qs = Comment.objects.filter(moderation__in=statuses)
            if not staff:  # a comment on a nuked post belongs to content they may not see
                qs = qs.exclude(post__status='nuked')
            if not head_admin:
                from escalation.visibility import active_escalation_ids
                qs = qs.exclude(pk__in=active_escalation_ids(Comment)).exclude(post_id__in=active_escalation_ids(Post))
            qs = qs.annotate(last_at=self._last_action_at(comment=OuterRef('pk')))
            rows += [(at, 'comments', pk) for pk, at in qs.values_list('pk', 'last_at')]
        # newest first; a legacy row with no audit line (hidden before this existed) sinks to the bottom
        rows.sort(key=lambda r: (r[0] is None, -(r[0].timestamp() if r[0] else 0)))

        page = int(p['page']) if p.get('page', '').isdigit() and int(p['page']) > 0 else 1
        pages = max(1, math.ceil(len(rows) / self.page_size))
        if page > pages:
            return Response({'detail': 'Nie ma takiej strony.'}, status=status.HTTP_404_NOT_FOUND)
        chunk = rows[(page - 1) * self.page_size: page * self.page_size]

        posts = {x.pk: x for x in post_queryset(request.user).prefetch_related(ACTIONS_PREFETCH)
                 .filter(pk__in=[pk for _, k, pk in chunk if k == 'posts'])}
        comments = {x.pk: x for x in comment_queryset(request.user)
                   .filter(pk__in=[pk for _, k, pk in chunk if k == 'comments'])}
        from rest_framework.utils.urls import remove_query_param, replace_query_param
        url = request.build_absolute_uri()
        return Response({
            'count': len(rows), 'page': page, 'pages': pages, 'page_size': self.page_size,
            'next': replace_query_param(url, 'page', page + 1) if page < pages else None,
            'previous': (remove_query_param(url, 'page') if page == 2 else replace_query_param(url, 'page', page - 1))
            if page > 1 else None,
            'posts': [board_post_payload(posts[pk], request) for _, k, pk in chunk if k == 'posts' and pk in posts],
            'comments': [board_comment_payload(comments[pk], request)
                         for _, k, pk in chunk if k == 'comments' and pk in comments],
        })


class ReportViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = Report.objects.all()
    serializer_class = ReportSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'report'

    def perform_create(self, s):
        s.save(reporter=self.request.user if self.request.user.is_authenticated else None)
