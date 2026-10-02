from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0004_exam_is_visible'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 考试总时长（分钟）：0 = 不限时。已有考试默认不限时，行为不变
        migrations.AddField(
            model_name='exam',
            name='duration_minutes',
            field=models.PositiveIntegerField(
                default=0, verbose_name='考试时长（分钟）'
            ),
        ),
        # 学生作答会话：持久化倒计时截止时间（刷新不重置）
        migrations.CreateModel(
            name='ExamAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('deadline', models.DateTimeField()),
                ('exam', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='attempts', to='exams.exam')),
                ('student', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='exam_attempts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'exam_attempt',
                'unique_together': {('exam', 'student')},
            },
        ),
    ]
