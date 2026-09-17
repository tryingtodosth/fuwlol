from django.db import migrations, models


def backfill(apps, schema_editor):
    from archive.search import index_fields
    Post = apps.get_model('archive', 'Post')
    for p in Post.objects.all().iterator():
        p.search_text, p.search_math = index_fields(p.title, p.summary, p.body, p.format)
        p.save(update_fields=['search_text', 'search_math'])


class Migration(migrations.Migration):
    dependencies = [('archive', '0002_comment_moderation_alter_post_status_and_more')]
    operations = [
        migrations.AddField(model_name='post', name='rights_confirmed', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='post', name='search_text', field=models.TextField(blank=True, editable=False)),
        migrations.AddField(model_name='post', name='search_math', field=models.TextField(blank=True, editable=False)),
        migrations.AddField(model_name='report', name='good_faith', field=models.BooleanField(default=False)),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
