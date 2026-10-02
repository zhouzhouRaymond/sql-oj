from django.db import models
from django.conf import settings


class Exam(models.Model):
    STUDENT_SCOPE_CHOICES = [
        ('all', '所有学生'),
        ('specified', '指定学生'),
    ]
    title = models.CharField(max_length=255)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    total_score = models.IntegerField()
    # 考试总时长（分钟）。0 表示不限时，只受考试起止时间约束。
    # 学生进入考试后按该时长倒计时，倒计时结束自动交卷。
    duration_minutes = models.PositiveIntegerField('考试时长（分钟）', default=0)
    student_scope = models.CharField(
        max_length=10, choices=STUDENT_SCOPE_CHOICES, default='all'
    )
    students = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='assigned_exams',
        limit_choices_to={'user_type': 'student'}
    )
    # 是否对学生公开。关闭后学生看不到、也无法进入该考试；
    # 教师端始终可见，便于正式发布前先隐藏（如草稿或已归档的考试）。
    is_visible = models.BooleanField('对学生可见', default=True)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, related_name='exams'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'exam'


class ExamQuestion(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='exam_questions')
    question = models.ForeignKey('questions.Question', on_delete=models.CASCADE)
    score = models.IntegerField()

    class Meta:
        db_table = 'exam_question'
        unique_together = ('exam', 'question')


class ExamAttempt(models.Model):
    """学生在某场考试的作答会话（记录开始时间与截止时间）。

    用于「考试总时长」倒计时：同一个截止时间在刷新页面后继续生效，
    避免通过刷新重置计时；同时让教师能看到「已进入但未提交」的考生并重置。
    此外持久化一份「中间作答草稿」（服务端），用于换设备恢复作答，
    以及学生在到点前关掉浏览器时由服务端按最后草稿兜底交卷。
    """

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='exam_attempts',
    )
    started_at = models.DateTimeField(auto_now_add=True)
    deadline = models.DateTimeField()
    # 最近一次同步上来的作答草稿：{题目 id: SQL}，空表示还没有作答
    draft_answers = models.JSONField('作答草稿', default=dict, blank=True)
    draft_updated_at = models.DateTimeField('草稿同步时间', null=True, blank=True)

    class Meta:
        db_table = 'exam_attempt'
        unique_together = ('exam', 'student')
