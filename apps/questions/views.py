from rest_framework import viewsets, permissions, status, filters
from rest_framework.response import Response

from .models import Question, Answer, TestCase
from .serializers import (
    QuestionSerializer, QuestionStudentSerializer,
    AnswerSerializer, TestCaseSerializer
)
from apps.users.permissions import IsTeacher


class QuestionViewSet(viewsets.ModelViewSet):
    """题目管理 ViewSet"""
    queryset = Question.objects.all().prefetch_related('answers', 'test_cases')
    # 支持 ?ordering=id / -created_at 等排序（学生题库按题号升序拉取）
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['id', 'created_at', 'title', 'difficulty']

    def get_serializer_class(self):
        """学生看不到答案，教师看到完整信息"""
        if self.request.user.user_type == 'student':
            return QuestionStudentSerializer
        return QuestionSerializer

    def get_queryset(self):
        """学生只能看到「对学生可见」的题目；教师可见全部（含已隐藏）。

        考试中的题目由考试接口（/exams/{id}/start/）单独下发，
        因此隐藏题目不会影响已安排的考试。
        """
        qs = super().get_queryset()
        if getattr(self.request.user, 'user_type', None) == 'student':
            qs = qs.filter(is_visible=True)
        return qs

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [permissions.IsAuthenticated(), IsTeacher()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        question = serializer.save(teacher=self.request.user)
        # 批量创建答案
        answers_data = self.request.data.get('answers', [])
        for ans in answers_data:
            Answer.objects.create(question=question, correct_sql=ans['correct_sql'])
        # 批量创建测试用例
        test_cases_data = self.request.data.get('test_cases', [])
        for tc in test_cases_data:
            TestCase.objects.create(question=question, **tc)

    def update(self, request, *args, **kwargs):
        """更新题目时同步更新 answers 和 test_cases"""
        question = self.get_object()
        response = super().update(request, *args, **kwargs)

        # 更新 answers（替换策略：全删再全建）
        answers_data = request.data.get('answers')
        if answers_data is not None:
            question.answers.all().delete()
            for ans in answers_data:
                Answer.objects.create(question=question, correct_sql=ans['correct_sql'])

        # 更新 test_cases
        test_cases_data = request.data.get('test_cases')
        if test_cases_data is not None:
            question.test_cases.all().delete()
            for tc in test_cases_data:
                TestCase.objects.create(question=question, **tc)

        return response
