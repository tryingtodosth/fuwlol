from django.contrib import admin
from .models import Attachment, Category, Comment, ModerationAction, Person, Post, Report, Tag


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
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


admin.site.register(Category)
admin.site.register(Person, list_display=['name', 'role', 'is_listed'])
admin.site.register(Tag)
admin.site.register(Comment, list_display=['post', 'author', 'created_at', 'is_removed', 'moderation'],
                    list_filter=['moderation'])
admin.site.register(ModerationAction, list_display=['created_at', 'action', 'actor', 'post', 'comment', 'previous_status'],
                    list_filter=['action'], readonly_fields=['created_at'])
admin.site.register(Report, list_display=['post', 'reason', 'reporter', 'resolved', 'created_at'], list_filter=['resolved', 'reason'])
