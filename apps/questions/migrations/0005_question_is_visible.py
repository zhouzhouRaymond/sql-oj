from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('questions', '0004_question_show_case_details'),
    ]

    operations = [
        # 教师可控制题目是否对学生公开；已有题目默认全部公开，保持行为不变
        migrations.AddField(
            model_name='question',
            name='is_visible',
            field=models.BooleanField(default=True, verbose_name='对学生可见'),
        ),
    ]
