from django.db import models
from django.conf import settings


class Question(models.Model):
    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]
    JUDGE_MODE_CHOICES = [
        ('query', '查询结果'),
        ('schema', '表结构'),
    ]
    JUDGE_STRICTNESS_CHOICES = [
        ('subset', '宽松：多出的列/约束/索引不判错'),
        ('exact', '严格：对象集合必须与期望一致'),
    ]
    description = models.TextField()
    title = models.CharField(max_length=255, blank=True, default='')
    # 判题模式：query=执行 SQL 比较结果集；schema=DDL 结构判题（CREATE TABLE 等）
    judge_mode = models.CharField(
        '判题模式', max_length=10, choices=JUDGE_MODE_CHOICES, default='query'
    )
    # schema 模式的严格度；compare_names 为真时要求约束名/索引名与期望一致
    judge_strictness = models.CharField(
        '结构严格度', max_length=10, choices=JUDGE_STRICTNESS_CHOICES, default='subset'
    )
    judge_compare_names = models.BooleanField('比对约束/索引名称', default=False)
    sample_input = models.TextField(blank=True, null=True)
    sample_output = models.TextField(blank=True, null=True)
    create_table_sql = models.TextField(blank=True, null=True)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES)
    # 答题失败时，是否向学生展示隐藏用例的「测试输入」与「预期输出」。
    # 默认关闭：开启后学生可据此构造硬编码答案绕过判题，仅建议用于教学演示。
    show_case_details = models.BooleanField(
        '失败时向学生展示用例输入与预期输出', default=False
    )
    # 是否在学生题库中公开展示。关闭后学生看不到、也无法打开该题；
    # 已安排在考试中的题目不受影响（考试内容由考试接口单独下发）。
    is_visible = models.BooleanField('对学生可见', default=True)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, related_name='questions'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'question'
        ordering = ['-created_at']


class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    correct_sql = models.TextField()

    class Meta:
        db_table = 'answer'


class TestCase(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='test_cases')
    test_input = models.TextField(blank=True, null=True)
    # query 模式：期望结果集字符串；schema 模式下留空
    expected_output = models.TextField(blank=True, default='')
    # schema 模式：期望结构快照（由 judge-service 的 /introspect 生成）
    expected_schema = models.JSONField(default=dict, blank=True)
    # schema 模式：行为探针列表，形如
    # [{"sql": "...", "expect": "ok"|"error", "error_code": "23505", "description": "..."}]
    probes = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = 'test_case'
