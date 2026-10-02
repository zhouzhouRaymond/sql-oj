from django.db import migrations, models


def backfill_display_name(apps, schema_editor):
    """把已有用户的自定义用户名回填为登录名，保证升级后界面展示不变"""
    User = apps.get_model('users', 'User')
    User.objects.filter(display_name='').update(display_name=models.F('username'))


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='display_name',
            field=models.CharField(
                blank=True, default='', max_length=50, verbose_name='用户名'
            ),
        ),
        migrations.RunPython(backfill_display_name, migrations.RunPython.noop),
    ]
