import requests
from django.db.models import Q
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.submissions.judge import (
    JUDGE_HTTP_TIMEOUT,
    judge_service_base_url,
    judge_service_headers,
)
from apps.users.permissions import IsTeacher

from .models import Answer, Question, TestCase
from .serializers import QuestionSerializer, QuestionStudentSerializer


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
        """按角色与筛选参数返回题目列表。

        考试中的题目由考试接口（/exams/{id}/start/）单独下发，
        因此隐藏题目不会影响已安排的考试。

        支持查询参数：
        - ``search``：只匹配题号（纯数字时精确匹配）与题目名称，描述不参与；
        - ``difficulty``：easy / medium / hard，非法值忽略；
        - ``is_visible``：true / false，仅教师生效（学生始终只看可见题目）。
        """
        qs = super().get_queryset()
        if getattr(self.request.user, 'user_type', None) == 'student':
            qs = qs.filter(is_visible=True)
        else:
            visible = self.request.query_params.get('is_visible')
            if visible in ('true', 'false'):
                qs = qs.filter(is_visible=(visible == 'true'))

        keyword = (self.request.query_params.get('search') or '').strip()
        if keyword:
            # 只匹配「题号」与「题目名称」：描述里出现的关键词/数字不参与，
            # 避免搜 1 时把描述里含 1 的题目全部带出来
            matched = Q(title__icontains=keyword)
            if keyword.isdigit():
                matched |= Q(id=int(keyword))
            qs = qs.filter(matched)

        difficulty = (self.request.query_params.get('difficulty') or '').strip()
        if difficulty in {value for value, _ in Question.DIFFICULTY_CHOICES}:
            qs = qs.filter(difficulty=difficulty)

        return qs

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy', 'introspect'):
            return [permissions.IsAuthenticated(), IsTeacher()]
        return [permissions.IsAuthenticated()]

    @action(detail=False, methods=['post'])
    def introspect(self, request):
        """教师端出题辅助：参考 DDL → 期望结构（并自动生成/验证行为探针）。

        请求体：``{reference_sql, setup_sql?, suggest_probes?}``
        响应：``{expected_schema, suggested_probes, error_message}``
        """
        reference_sql = str(request.data.get('reference_sql') or '').strip()
        if not reference_sql:
            return Response(
                {'error': 'reference_sql 为必填'}, status=status.HTTP_400_BAD_REQUEST
            )
        payload = {
            'sql': reference_sql,
            'setup_sql': request.data.get('setup_sql') or '',
            'suggest_probes': bool(request.data.get('suggest_probes', True)),
        }
        try:
            response = requests.post(
                judge_service_base_url() + '/introspect',
                json=payload,
                timeout=JUDGE_HTTP_TIMEOUT + 30,
                headers=judge_service_headers(),
            )
            response.raise_for_status()
            return Response(response.json())
        except requests.RequestException as exc:
            return Response(
                {'error': f'判题服务不可用: {exc}'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except ValueError:
            return Response(
                {'error': '判题服务返回非法 JSON'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

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
