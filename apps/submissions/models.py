from django.db import models
from django.conf import settings


class Submission(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='submissions')
    question = models.ForeignKey('questions.Question', on_delete=models.CASCADE, related_name='submissions')
    exam = models.ForeignKey('exams.Exam', on_delete=models.SET_NULL, null=True, blank=True, related_name='submissions')
    submitted_sql = models.TextField()
    submission_time = models.DateTimeField(auto_now_add=True)
    execution_status = models.CharField(max_length=50, blank=True, default='')
    score = models.IntegerField(default=0)
    # 判题用例明细（判题服务返回后落库，供前端回显"失败的测试用例"）：
    #   {"cases": [{"test_case_id": 0, "passed": false, "actual_output": "...", "error_message": ""}],
    #    "error_message": "整体执行失败原因（如建表语句报错）"}
    # 注意：judge 服务只返回「实际输出」，不返回用例输入与预期输出，
    # 因此该字段可以安全地按需回显，不会泄露隐藏用例答案。
    judge_details = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'submission'
