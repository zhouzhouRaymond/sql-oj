from django.db import migrations, models


class Migration(migrations.Migration):

    # 依赖 questions 应用当前的叶节点迁移（0003），避免出现多个叶节点
    dependencies = [
        ('questions', '0003_alter_question_options_question_title'),
    ]

    operations = [
        migrations.AddField(
            model_name='question',
            name='show_case_details',
            field=models.BooleanField(
                default=False, verbose_name='失败时向学生展示用例输入与预期输出'
            ),
        ),
    ]
