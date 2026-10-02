from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0003_exam_student_scope_exam_students'),
    ]

    operations = [
        # 教师可控制考试是否对学生公开；已有考试默认全部公开，保持行为不变
        migrations.AddField(
            model_name='exam',
            name='is_visible',
            field=models.BooleanField(default=True, verbose_name='对学生可见'),
        ),
    ]
