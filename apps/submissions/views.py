from django.utils import timezone
from django.db.models import Count, Q, Avg, Max, Sum
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action

from .models import Submission
from .serializers import SubmissionSerializer
from .judging import JudgeQueueFull, PENDING, enqueue_judge
from apps.questions.models import Question
from apps.exams.models import Exam
from apps.users.models import User
from apps.users.permissions import IsTeacher


class SubmissionViewSet(viewsets.ModelViewSet):
    """提交与判题 ViewSet"""
    queryset = Submission.objects.all()
    serializer_class = SubmissionSerializer

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
                'total_submissions': total,
                'passed': passed,
                'passed_questions': passed_questions,
                'rate': round(passed / total, 2) if total else 0,
            })
        stats.sort(key=lambda x: x['rate'], reverse=True)
        return Response(stats)
