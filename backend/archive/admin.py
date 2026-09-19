from django.contrib import admin, messages
from django.db.models import Count

from escalation.adminmixin import HideEscalatedMixin

from .models import Attachment, Category, Comment, ModerationAction, Person, Post, Report, Subject, Tag


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0


@admin.register(Post)
class PostAdmin(HideEscalatedMixin, admin.ModelAdmin):
    list_display = ['catalog_no', 'title', 'category', 'format', 'year', 'status', 'featured', 'submitted_by', 'created_at']
    list_filter = ['status', 'category', 'format', 'featured']
    search_fields = ['title', 'body', 'summary']
    inlines = [AttachmentInline]
    filter_horizontal = ['people', 'subjects', 'tags']
    actions = ['publish', 'reject']

    @admin.action(description='Opublikuj')
    def publish(self, request, qs):
        for p in qs:
            p.status = 'published'
            p.reviewed_by = request.user
            p.save()

    @admin.action(description='Odrzuć')
    def reject(self, request, qs):
        qs.update(status='rejected', reviewed_by=request.user)


@admin.register(Comment)
class CommentAdmin(HideEscalatedMixin, admin.ModelAdmin):
    list_display = ['post', 'author', 'created_at', 'is_removed', 'moderation']
    list_filter = ['moderation']
    escalation_guards = (('pk', Comment), ('post', Post))


@admin.register(ModerationAction)
class ModerationActionAdmin(HideEscalatedMixin, admin.ModelAdmin):
    list_display = ['created_at', 'action', 'actor', 'post', 'comment', 'previous_status']
    list_filter = ['action']
    readonly_fields = ['created_at']
    escalation_guards = (('post', Post), ('comment', Comment))


@admin.register(Report)
class ReportAdmin(HideEscalatedMixin, admin.ModelAdmin):
    list_display = ['post', 'reason', 'reporter', 'resolved', 'created_at']
    list_filter = ['resolved', 'reason']
    escalation_guards = (('post', Post),)


@admin.register(Attachment)
class AttachmentAdmin(HideEscalatedMixin, admin.ModelAdmin):
    list_display = ['original_name', 'post', 'kind', 'order']
    escalation_guards = (('post', Post),)


admin.site.register(Category)


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    """The staff side of /ludzie. `image_consent` is editable here on purpose: until the
    claims flow writes it, a lecturer who says "sure, go ahead" in the corridor is recorded
    by whoever heard it — and the field's help text says so."""
    list_display = ['full_name', 'surname', 'unit', 'sex', 'image_consent', 'is_listed', 'created_at']
    list_filter = ['image_consent', 'sex', 'is_listed']
    search_fields = ['name', 'surname', 'degree', 'role', 'unit', 'aliases__name']
    filter_horizontal = ['aliases']
    readonly_fields = ['sort_key', 'name_key', 'created_at']
    fieldsets = [
        (None, {'fields': ['slug', 'degree', 'name', 'surname', 'sort_key', 'name_key', 'sex']}),
        ('Jak w spisie osób', {'fields': ['role', 'unit', 'bio', 'aliases']}),
        ('Wizerunek i widoczność', {'fields': ['image_consent', 'is_listed', 'created_by', 'created_at']}),
    ]


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    """The staff side of /przedmioty. `created_by` is the whole visibility rule in one
    column: empty means the row came from the Faculty's programme and is always listed,
    filled means somebody named it in the editor and it waits for a published post.

    The merge action is the other half of the deliberate decision NOT to fuzzy-match names
    on submission (archive/subjects.py): duplicates are allowed to happen and are cleaned up
    here, because „Mechanika klasyczna" and „Mechanika klasyczna R" are two real courses and
    an algorithm that merged them would be wrong in a way nobody could undo."""
    list_display = ['name', 'short', 'slug', 'order', 'post_count', 'created_by', 'created_at']
    list_filter = ['created_by']
    search_fields = ['name', 'short', 'slug']
    readonly_fields = ['created_at']
    prepopulated_fields = {'slug': ('name',)}
    actions = ['merge']

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(n_posts=Count('posts'))

    @admin.display(description='Wpisy', ordering='n_posts')
    def post_count(self, obj):
        return obj.n_posts

    @admin.action(description='Scal zaznaczone w jeden (zostaje ten z programu / najstarszy)')
    def merge(self, request, qs):
        """Every post filed under the selected rows is moved onto the survivor and the rest
        are deleted. The survivor is the seeded row if one is selected, else the lowest
        `order`, else the oldest — so merging a typo into the programme's own entry does the
        obvious thing without asking."""
        rows = list(qs.order_by('created_by_id', 'order', 'id'))
        if len(rows) < 2:
            self.message_user(request, 'Zaznacz co najmniej dwa przedmioty do scalenia.', level=messages.WARNING)
            return
        keep, rest = rows[0], rows[1:]
        moved = 0
        for other in rest:
            for post in other.posts.all():
                post.subjects.add(keep)
                post.subjects.remove(other)
                moved += 1
            other.delete()
        self.message_user(request, f'Scalono {len(rest)} przedmiot(y) w „{keep.name}”; przeniesiono {moved} wpis(ów).')


admin.site.register(Tag)
