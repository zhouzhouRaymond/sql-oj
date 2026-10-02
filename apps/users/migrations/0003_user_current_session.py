from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_user_display_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='current_session',
            # 单点登录：记录当前唯一有效的会话标识，新登录会覆盖它
            field=models.CharField(
                blank=True, default='', max_length=64,
                verbose_name='当前会话标识',
            ),
        ),
    ]
