import re
from datetime import datetime, time

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.db.models import Count, Q, Avg, Max, Sum
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError

from .models import Submission
from .serializers import SubmissionSerializer, SubmissionListSerializer
from .judging import JudgeQueueFull, PENDING, enqueue_judge
from apps.questions.models import Question
from apps.exams.models import Exam
from apps.users.models import User
from apps.users.permissions import IsTeacher


# 只给日期（2026-10-02）或只精确到分钟（2026-10-02 10:30）
_DATE_ONLY_RE = re.compile(r'^\d{4}-\d{1,2}-\d{1,2}$')
_MINUTE_ONLY_RE = re.compile(r'^\d{4}-\d{1,2}-\d{1,2}[T ]\d{1,2}:\d{1,2}$')


def _to_int(raw, field):
    """把查询参数转成整数；非法值返回 400，避免直接抛 ValueError 变成 500"""
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValidationError({field: '必须为整数'})


def _parse_time_range(start_raw, end_raw):
    """把 ?start=&end= 解析为带时区的 datetime。

    - 支持 YYYY-MM-DD（end 自动补到当天 23:59:59.999999）、
      YYYY-MM-DD HH:mm（end 补到该分钟的 59.999999 秒）或完整 ISO 时间
    - 为空则返回 None，表示该侧不做时间限制
    """
    def to_datetime(raw, is_end=False):
        raw = (raw or '').strip()
        if not raw:
            return None
        if _DATE_ONLY_RE.match(raw):
            # 只给日期：start 取当天 00:00:00，end 取当天 23:59:59.999999
            day = parse_date(raw)
            if day is None:
                return None
            value = datetime.combine(day, time.max if is_end else time.min)
        else:
            value = parse_datetime(raw)
            if value is None:
                return None
            if is_end and _MINUTE_ONLY_RE.match(raw):
                # 结束时间只精确到分钟时，按「该分钟的最后一刻」处理，
                # 否则同一分钟内 10:30:30 这样的提交会被漏掉
                value = value.replace(second=59, microsecond=999999)
        if timezone.is_naive(value):
            value = timezone.make_aware(value)
        return value

    return to_datetime(start_raw), to_datetime(end_raw, is_end=True)


class SubmissionViewSet(viewsets.ModelViewSet):
    """提交与判题 ViewSet"""
    # 默认按提交时间倒序，保证列表分页后仍是「由近到远」的顺序
    queryset = Submission.objects.all().order_by('-submission_time')
    serializer_class = SubmissionSerializer

    def get_serializer_class(self):
        """列表不返回体积较大的 submitted_sql，详情才返回（供前端懒加载）"""
        if self.action == 'list':
            return SubmissionListSerializer
        return SubmissionSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated()]

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
            qs = qs.filter(question_id=_to_int(question_id, 'question_id'))
        student_id = self.request.query_params.get('student_id')
        if student_id:
            qs = qs.filter(student_id=_to_int(student_id, 'student_id'))
        exam_id = self.request.query_params.get('exam')
        if exam_id:
            qs = qs.filter(exam_id=_to_int(exam_id, 'exam'))
        start, end = _parse_time_range(
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
        """学生提交 SQL 并触发判题"""
        question_id = request.data.get('question_id')
        exam_id = request.data.get('exam_id')
        submitted_sql = request.data.get('submitted_sql')

        if not question_id or not submitted_sql:
            return Response(
                {'error': 'question_id 和 submitted_sql 为必填'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 考试模式下校验时间
        if exam_id:
            try:
                exam = Exam.objects.get(id=exam_id)
            except Exam.DoesNotExist:
                return Response({'error': '考试不存在'}, status=status.HTTP_404_NOT_FOUND)
            now = timezone.now()
            if not (exam.start_time <= now <= exam.end_time):
                return Response(
                    {'error': '不在考试时间内'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # 获取题目
        try:
            question = Question.objects.get(id=question_id)
        except Question.DoesNotExist:
            return Response({'error': '题目不存在'}, status=status.HTTP_404_NOT_FOUND)

        # 先落库为待判题，再交给后台线程判题，请求线程立即返回而不被阻塞
        submission = Submission.objects.create(
            student=request.user,
            question=question,
            exam_id=exam_id,
            submitted_sql=submitted_sql,
            execution_status=PENDING,
            score=0,
        )
        try:
            enqueue_judge(submission.id)
        except JudgeQueueFull:
            submission.execution_status = 'ERROR'
            submission.save(update_fields=['execution_status'])
            return Response(
                {'error': '判题服务繁忙，请稍后重试', 'submission_id': submission.id},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            SubmissionSerializer(submission).data,
            status=status.HTTP_202_ACCEPTED
        )


class StatsViewSet(viewsets.ViewSet):
    """统计分析 ViewSet"""
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def overview(self, request):
        """整体概览"""
        total_questions = Question.objects.count()
        total_submissions = Submission.objects.count()
        total_users = User.objects.count()

        # 计算平均通过率：所有提交中 ACCEPTED 的比例
        total_passed = Submission.objects.filter(execution_status='ACCEPTED').count()
        average_pass_rate = round(total_passed / total_submissions, 2) if total_submissions else 0

        return Response({
            'total_questions': total_questions,
            'total_submissions': total_submissions,
            'total_users': total_users,
            'average_pass_rate': average_pass_rate,
        })

    @action(detail=False, methods=['get'])
    def questions(self, request):
        """每题完成率（教师可见）"""
        if request.user.user_type != 'teacher':
            return Response({'error': '无权限'}, status=status.HTTP_403_FORBIDDEN)

        stats = []
        for q in Question.objects.all():
            # 尝试过该题的学生数
            attempted_students = Submission.objects.filter(
                question=q
            ).values('student').distinct().count()
            # 通过该题的学生数（至少有一次 ACCEPTED）
            passed_students = Submission.objects.filter(
                question=q, execution_status='ACCEPTED'
            ).values('student').distinct().count()
            total_submissions = Submission.objects.filter(question=q).count()
            stats.append({
                'question_id': q.id,
                'title': q.title,
                'total_submissions': total_submissions,
                'attempted_students': attempted_students,
                'passed_students': passed_students,
                'rate': round(passed_students / attempted_students, 2) if attempted_students else 0,
            })
        return Response(stats)

    @action(detail=False, methods=['get'])
    def students(self, request):
        """学生通过率排名（教师可见）"""
        if request.user.user_type != 'teacher':
            return Response({'error': '无权限'}, status=status.HTTP_403_FORBIDDEN)

        # 获取所有有提交记录的学生
        from django.db.models import Exists, OuterRef
        student_with_subs = User.objects.filter(
            user_type='student'
        ).filter(
            Exists(Submission.objects.filter(student=OuterRef('pk')))
        )
        stats = []
        for s in student_with_subs:
            subs = Submission.objects.filter(student=s)
            total = subs.count()
            passed = subs.filter(execution_status='ACCEPTED').count()
            # 通过题目数
            passed_questions = subs.filter(
                execution_status='ACCEPTED'
            ).values('question').distinct().count()
            stats.append({
                'student_id': s.id,
                'username': s.username,
                'name': s.name,
                'total_submissions': total,
                'passed': passed,
                'passed_questions': passed_questions,
                'rate': round(passed / total, 2) if total else 0,
            })
        stats.sort(key=lambda x: x['rate'], reverse=True)
        return Response(stats)

    @action(detail=False, methods=['get'])
    def question(self, request):
        """单题提交统计（教师可见），支持按时间段筛选

        查询参数：
        - question_id：必填
        - start / end：YYYY-MM-DD（含当天）、YYYY-MM-DD HH:mm（精确到分钟）
          或完整 ISO 时间；可省略表示不限

        仅统计学生提交（不含教师本人的试用提交）。
        """
        if request.user.user_type != 'teacher':
            return Response({'error': '无权限'}, status=status.HTTP_403_FORBIDDEN)

        question_id = request.query_params.get('question_id')
        if not question_id:
            return Response({'error': 'question_id 为必填'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            question = Question.objects.get(id=question_id)
        except (Question.DoesNotExist, ValueError):
            return Response({'error': '题目不存在'}, status=status.HTTP_404_NOT_FOUND)

        start, end = _parse_time_range(
            request.query_params.get('start'),
            request.query_params.get('end'),
        )

        submissions = Submission.objects.filter(
            question=question, student__user_type='student'
        )
        if start:
            submissions = submissions.filter(submission_time__gte=start)
        if end:
            submissions = submissions.filter(submission_time__lte=end)

        total_submissions = submissions.count()
        # 去重提交数：同一学生在时间段内多次提交只算一次
        distinct_submissions = submissions.values('student').distinct().count()
        accepted_submissions = submissions.filter(execution_status='ACCEPTED').count()
        # 通过人数：至少有一次 ACCEPTED 的学生数（去重）
        passed_students = submissions.filter(
            execution_status='ACCEPTED'
        ).values('student').distinct().count()

        # 学生通过率排名：按学生聚合该时间段内本题的提交情况
        ranking = []
        rows = (
            submissions.values('student__id', 'student__username', 'student__display_name')
            .annotate(
                total=Count('id'),
                accepted=Count('id', filter=Q(execution_status='ACCEPTED')),
            )
        )
        for row in rows:
            total = row['total']
            accepted = row['accepted']
            ranking.append({
                'student_id': row['student__id'],
                'username': row['student__username'],
                'name': row['student__display_name'] or row['student__username'],
                'total_submissions': total,
                'accepted_submissions': accepted,
                'pass_rate': round(accepted / total, 4) if total else 0,
                'passed': accepted > 0,
            })
        # 通过率降序 → 通过提交数多者优先 → 提交次数少者优先 → 用户名
        ranking.sort(key=lambda r: (
            -r['pass_rate'],
            -r['accepted_submissions'],
            r['total_submissions'],
            r['name'] or '',
        ))

        return Response({
            'question_id': question.id,
            'title': question.title,
            'start': start.isoformat() if start else None,
            'end': end.isoformat() if end else None,
            'total_submissions': total_submissions,
            'distinct_submissions': distinct_submissions,
            'accepted_submissions': accepted_submissions,
            'passed_students': passed_students,
            # 通过率统一以小数返回（0~1），前端再转百分比
            'pass_rate': round(accepted_submissions / total_submissions, 4) if total_submissions else 0,
            'student_pass_rate': round(passed_students / distinct_submissions, 4) if distinct_submissions else 0,
            'student_ranking': ranking,
        })
