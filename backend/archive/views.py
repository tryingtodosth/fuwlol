import random

from django.conf import settings
from django.db import transaction
from django.db.models import Count, F, Max, Min, Q
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import (Attachment, Category, Comment, CommentAttachment, Person, Post, Reaction,
                     Report, Tag)
from .serializers import (CategorySerializer, CommentSerializer, ModerationPostSerializer,
                          PersonSerializer, PostDetailSerializer, PostListSerializer,
                          PostWriteSerializer, ReportSerializer, TagSerializer, REACTION_KINDS)
from .validators import kind_for, strip_image_metadata, validate_upload

PUBLISHED = Q(status='published')


def _published_count(qs, rel='posts'):
    return qs.annotate(post_count=Count(rel, filter=Q(**{f'{rel}__status': 'published'})))


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = _published_count(Category.objects.all())
    serializer_class = CategorySerializer
    lookup_field = 'slug'
    pagination_class = None


class PersonViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = _published_count(Person.objects.filter(is_listed=True))
    serializer_class = PersonSerializer
    lookup_field = 'slug'
    pagination_class = None


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = _published_count(Tag.objects.all()).filter(post_count__gt=0)
    serializer_class = TagSerializer
    lookup_field = 'slug'
    pagination_class = None


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
            t = ScopedRateThrottle()
            t.scope = 'post_create'
            return [t]
        return super().get_throttles()

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy', 'react', 'mine'):
            return [IsAuthenticated()]
        if self.action in ('queue', 'moderate'):
            return [IsAdminUser()]
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
        return (Post.objects.select_related('category', 'submitted_by')
                .prefetch_related('people', 'tags', 'attachments', 'reactions')
                .annotate(comment_count=Count('comments', filter=Q(comments__is_removed=False), distinct=True)))

    def get_queryset(self):
        qs = self._base()
        u = self.request.user
        if self.action in ('retrieve', 'update', 'partial_update', 'destroy', 'moderate'):
            if u.is_authenticated and u.is_staff:
                return qs
            if u.is_authenticated:
                return qs.filter(PUBLISHED | Q(submitted_by=u))
            return qs.filter(PUBLISHED)
        if self.action == 'mine':
            return qs.filter(submitted_by=u).order_by('-created_at')
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
        try:
            return [str(c) for c in json.loads(raw)]
        except ValueError:
            return []

    def create(self, request, *args, **kwargs):
        files = _validate_files(self._files(request), settings.MAX_FILES_PER_POST)
        s = PostWriteSerializer(data=request.data, context={'request': request, 'has_files': bool(files)})
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            # Staff publish straight away; everybody else waits for a moderator.
            post = s.save(submitted_by=request.user,
                          status='published' if request.user.is_staff else 'pending')
            self._attach(post, files, self._captions(request))
        post = self._base().get(pk=post.pk)
        return Response(PostDetailSerializer(post, context={'request': request}).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        post = self.get_object()
        if not request.user.is_staff and post.submitted_by_id != request.user.id:
            raise PermissionDenied()
        if not request.user.is_staff and post.status == 'published':
            raise PermissionDenied('Opublikowany wpis może zmienić tylko moderator — zgłoś poprawkę w komentarzu.')
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
        if not request.user.is_staff and not (post.submitted_by_id == request.user.id and post.status != 'published'):
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
        rows = (Post.objects.filter(PUBLISHED, year__isnull=False).values('year')
                .annotate(count=Count('id')).order_by('year'))
        undated = Post.objects.filter(PUBLISHED, year__isnull=True).count()
        return Response({'years': list(rows), 'undated': undated})

    @action(detail=False)
    def stats(self, request):
        pub = Post.objects.filter(PUBLISHED)
        years = pub.filter(year__isnull=False).aggregate(lo=Min('year'), hi=Max('year'))
        return Response({'posts': pub.count(), 'people': Person.objects.filter(is_listed=True).count(),
                         'tags': Tag.objects.count(), 'attachments': Attachment.objects.filter(post__status='published').count(),
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
        files = _validate_files(self._files(request), 3)
        for f in files:
            if kind_for(f.name) != 'image':
                raise ValidationError({'files': 'Do komentarza można dodać tylko obrazy.'})
        s = CommentSerializer(data=request.data, context={'request': request})
        s.is_valid(raise_exception=True)
        parent = s.validated_data.get('parent')
        if parent is not None and parent.post_id != post.pk:
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
        """{decision: publish|reject|hide|feature|unfeature|resolve_reports, note}"""
        post = self.get_object()
        decision = request.data.get('decision')
        note = (request.data.get('note') or '')[:2000]
        if decision == 'publish':
            post.status, post.review_note, post.reviewed_by = 'published', note, request.user
            if post.published_at is None:
                post.published_at = timezone.now()
        elif decision == 'reject':
            post.status, post.review_note, post.reviewed_by = 'rejected', note, request.user
        elif decision == 'hide':
            post.status, post.review_note, post.reviewed_by = 'hidden', note, request.user
        elif decision in ('feature', 'unfeature'):
            post.featured = decision == 'feature'
        elif decision == 'resolve_reports':
            post.reports.update(resolved=True)
        else:
            raise ValidationError({'decision': 'Nieznana decyzja.'})
        post.save()
        if decision in ('hide', 'reject'):
            post.reports.update(resolved=True)
        post = self._base().get(pk=post.pk)
        return Response(ModerationPostSerializer(post, context={'request': request}).data)


class CommentDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        c = Comment.objects.filter(pk=pk).first()
        if c is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if not (request.user.is_staff or c.author_id == request.user.id):
            raise PermissionDenied()
        c.is_removed = True
        c.save(update_fields=['is_removed'])
        c.attachments.all().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReportViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    queryset = Report.objects.all()
    serializer_class = ReportSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'report'

    def perform_create(self, s):
        s.save(reporter=self.request.user if self.request.user.is_authenticated else None)
