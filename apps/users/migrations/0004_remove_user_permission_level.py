from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_user_current_session'),
    ]

    operations = [
        # 教师即管理员：所有教师都拥有账号管理等全部管理功能，
        # 不再需要单独的 permission_level（admin/teacher）概念。
        migrations.RemoveField(
            model_name='user',
            name='permission_level',
        ),
    ]
