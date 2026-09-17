from django.contrib import admin

from escalation.adminmixin import HideEscalatedMixin

from .models import Attachment, Category, Comment, ModerationAction, Person, Post, Report, Tag


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0


@admin.register(Post)
class PostAdmin(HideEscalatedMixin, admin.ModelAdmin):
    list_display = ['catalog_no', 'title', 'category', 'format', 'year', 'status', 'featured', 'submitted_by', 'created_at']
    list_filter = ['status', 'category', 'format', 'featured']
    search_fields = ['title', 'body', 'summary']
    inlines = [AttachmentInline]
    filter_horizontal = ['people', 'tags']
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
admin.site.register(Person, list_display=['name', 'role', 'is_listed'])
admin.site.register(Tag)
