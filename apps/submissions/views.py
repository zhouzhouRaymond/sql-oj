"""提交与判题接口。

核心流程：校验参数与考试时间 → 幂等去重 → 落库为 PENDING → 入队判题 →
立即返回 202，前端轮询提交详情拿结果。落库与入队的共用逻辑在
``services.create_submission``。统计接口见 ``views_stats``。
"""
from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.exams.models import Exam
from apps.questions.models import Question
from apps.users.throttles import (
    SubmitGlobalThrottle,
    SubmitQuestionThrottle,
    SubmitUserThrottle,
)

from .models import Submission
from .query_params import parse_time_range, to_int
from .serializers import SubmissionListSerializer, SubmissionSerializer
from .services import create_submission


class SubmissionViewSet(viewsets.ModelViewSet):
    """提交与判题 ViewSet"""
    # 默认按提交时间倒序，保证列表分页后仍是「由近到远」的顺序
    queryset = Submission.objects.all().order_by('-submission_time')
    serializer_class = SubmissionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        """列表不返回体积较大的 submitted_sql，详情才返回（供前端懒加载）"""
        if self.action == 'list':
            return SubmissionListSerializer
        return SubmissionSerializer

    def get_throttles(self):
        """提交判题走三级限流（用户级 / 题目级 / 全局），其余动作不限流。"""
        if self.action == 'submit':
            return [
                SubmitUserThrottle(),
                SubmitQuestionThrottle(),
                SubmitGlobalThrottle(),
            ]
        return super().get_throttles()

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.user_type == 'student':
            qs = qs.filter(student=self.request.user)
        elif self.request.user.user_type == 'teacher':
            # 教师可以看到所有学生的提交记录，也能看到自己产生的提交
            # （例如教师在题目页试用提交，提交后需能轮询到该条记录，否则会 404）
            qs = qs.filter(
                Q(student__user_type='student') | Q(student=self.request.user)
            )

        # 可选过滤：按题目 / 学生 / 考试 / 时间段收窄
        # （教师端「学生提交记录」下钻、教师端「考试提交情况」/ 学生端考试结果页都用它）
        # 学生视角在上面已限定为「本人提交」，这里的 student_id 只会进一步收窄，
        # 因此不会借此看到他人提交。
        question_id = self.request.query_params.get('question_id')
        if question_id:
            qs = qs.filter(question_id=to_int(question_id, 'question_id'))
        student_id = self.request.query_params.get('student_id')
        if student_id:
            qs = qs.filter(student_id=to_int(student_id, 'student_id'))
        exam_id = self.request.query_params.get('exam')
        if exam_id:
            qs = qs.filter(exam_id=to_int(exam_id, 'exam'))
        start, end = parse_time_range(
            self.request.query_params.get('start'),
            self.request.query_params.get('end'),
        )
        if start:
            qs = qs.filter(submission_time__gte=start)
        if end:
            qs = qs.filter(submission_time__lte=end)
        return qs

    @action(detail=False, methods=['post'])
    def submit(self, request):
        """学生提交 SQL 并触发判题（立即返回 202，前端轮询详情）。"""
        question_id = request.data.get('question_id')
        exam_id = request.data.get('exam_id')
        submitted_sql = request.data.get('submitted_sql')

        if not question_id or not submitted_sql:
            return Response(
                {'error': 'question_id 和 submitted_sql 为必填'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        exam = None
        if exam_id:
            try:
                exam = Exam.objects.get(id=exam_id)
            except Exam.DoesNotExist:
                return Response(
                    {'error': '考试不存在'}, status=status.HTTP_404_NOT_FOUND
                )
            now = timezone.now()
            if not (exam.start_time <= now <= exam.end_time):
                return Response(
                    {'error': '不在考试时间内'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            question = Question.objects.get(id=question_id)
        except Question.DoesNotExist:
            return Response(
                {'error': '题目不存在'}, status=status.HTTP_404_NOT_FOUND
            )

        # 幂等去重 / 落库 / 入队都在 service 里；请求线程不等待判题完成
        result = create_submission(request.user, question, submitted_sql, exam=exam)
        if result.queue_full:
            return Response(
                {
                    'error': '判题服务繁忙，请稍后重试',
                    'submission_id': result.submission.id,
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            SubmissionSerializer(result.submission).data,
            status=status.HTTP_202_ACCEPTED,
        )
