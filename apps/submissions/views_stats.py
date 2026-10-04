"""提交相关的统计分析接口（教师端看板使用）。

与 ``views.SubmissionViewSet`` 分开存放：提交/判题是核心链路，
统计是只读的旁路功能，拆开后 ``views.py`` 只保留提交相关逻辑。
"""
from django.db.models import Count, Exists, OuterRef, Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.questions.models import Question
from apps.users.models import User

from .models import Submission
from .query_params import parse_time_range
from .status import ACCEPTED


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
        total_passed = Submission.objects.filter(execution_status=ACCEPTED).count()
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
                question=q, execution_status=ACCEPTED
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
        student_with_subs = User.objects.filter(
            user_type='student'
        ).filter(
            Exists(Submission.objects.filter(student=OuterRef('pk')))
        )
        stats = []
        for s in student_with_subs:
            subs = Submission.objects.filter(student=s)
            total = subs.count()
            passed = subs.filter(execution_status=ACCEPTED).count()
            # 通过题目数
            passed_questions = subs.filter(
                execution_status=ACCEPTED
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

        start, end = parse_time_range(
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
        accepted_submissions = submissions.filter(execution_status=ACCEPTED).count()
        # 通过人数：至少有一次 ACCEPTED 的学生数（去重）
        passed_students = submissions.filter(
            execution_status=ACCEPTED
        ).values('student').distinct().count()

        # 学生通过率排名：按学生聚合该时间段内本题的提交情况
        ranking = []
        rows = (
            submissions.values('student__id', 'student__username', 'student__display_name')
            .annotate(
                total=Count('id'),
                accepted=Count('id', filter=Q(execution_status=ACCEPTED)),
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
