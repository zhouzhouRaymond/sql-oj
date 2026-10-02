from django.db import migrations, models


class Migration(migrations.Migration):
    """作答会话增加「服务端草稿」：换设备可恢复作答 + 到点兜底交卷。"""

    dependencies = [
        ('exams', '0005_exam_duration_and_attempt'),
    ]

    operations = [
        # 最近一次同步的作答草稿（{题目 id: SQL}）与同步时间
        migrations.AddField(
            model_name='examattempt',
            name='draft_answers',
            field=models.JSONField(
                blank=True, default=dict, verbose_name='作答草稿'
            ),
        ),
        migrations.AddField(
            model_name='examattempt',
            name='draft_updated_at',
            field=models.DateTimeField(
                blank=True, null=True, verbose_name='草稿同步时间'
            ),
        ),
    ]
