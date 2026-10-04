import csv
from datetime import timedelta
from urllib.parse import quote

from django.db.models import Max, Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action

from .models import Exam, ExamAttempt, ExamQuestion
from .serializers import ExamSerializer
from .services import finalize_expired_attempts
from apps.users.permissions import IsTeacher
from apps.users.models import User
from apps.questions.models import Question
from apps.submissions.models import Submission


class ExamViewSet(viewsets.ModelViewSet):
    """考试管理 ViewSet"""
    serializer_class = ExamSerializer

    def get_queryset(self):
        user = self.request.user
        # 固定排序：避免分页顺序不稳定导致考试列表重复/遗漏
        base_qs = Exam.objects.all().prefetch_related(
            'exam_questions__question', 'students'
        ).order_by('id')
        if user.user_type == 'teacher':
            # 教师：可见所有教师创建的考试（考试为全校共享，任何人都能查看与编辑）
            return base_qs
        # 学生：仅「对学生可见」的考试，且为全部开放或自己被指定的
        return base_qs.filter(
            Q(is_visible=True) & (Q(student_scope='all') | Q(students=user))
        ).distinct()

    def get_permissions(self):
        if self.action in (
            'create', 'update', 'partial_update', 'destroy',
            'export', 'reset_attempt',
        ):
            return [permissions.IsAuthenticated(), IsTeacher()]
        return [permissions.IsAuthenticated()]

    def _validate_question_ids(self, questions_data):
        """验证 exam_questions 中的题目ID是否合法"""
        if not questions_data:
            return None
        question_ids = [q.get('question') for q in questions_data if q.get('question')]
        existing_ids = set(
            Question.objects.filter(id__in=question_ids).values_list('id', flat=True)
        )
        invalid_ids = [qid for qid in question_ids if qid not in existing_ids]
        if invalid_ids:
            return invalid_ids
        return None

    def perform_create(self, serializer):
        # 验证题目ID
        questions_data = self.request.data.get('exam_questions', [])
        invalid_ids = self._validate_question_ids(questions_data)
        if invalid_ids:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(
                {'exam_questions': f'以下题目ID不存在: {invalid_ids}'}
            )

        exam = serializer.save(teacher=self.request.user)
        # 批量创建考试题目关联
        for q in questions_data:
            ExamQuestion.objects.create(
                exam=exam,
                question_id=q['question'],
                score=q['score']
            )
        # 处理指定学生
        student_ids = self.request.data.get('student_ids', [])
        if student_ids:
            exam.students.set(student_ids)

    def update(self, request, *args, **kwargs):
        exam = self.get_object()

        # 允许部分更新（PUT 也不强制要求全字段，避免前端日期选择器等组件未发送未修改的字段时报错）
        kwargs['partial'] = True

        # 验证题目ID
        questions_data = request.data.get('exam_questions')
        if questions_data is not None:
            invalid_ids = self._validate_question_ids(questions_data)
            if invalid_ids:
                return Response(
                    {'exam_questions': f'以下题目ID不存在: {invalid_ids}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        response = super().update(request, *args, **kwargs)
        # 更新 exam_questions
        if questions_data is not None:
            exam.exam_questions.all().delete()
            for q in questions_data:
                ExamQuestion.objects.create(
                    exam=exam,
                    question_id=q['question'],
                    score=q['score']
                )
        # 更新指定学生
        student_ids = request.data.get('student_ids')
        if student_ids is not None:
            exam.students.set(student_ids)
        return response

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """学生开始考试（校验时间 + 只能考一次）"""
        exam = self.get_object()
        now = timezone.now()
        if now < exam.start_time:
            return Response({'error': '考试尚未开始'}, status=status.HTTP_400_BAD_REQUEST)
        if now > exam.end_time:
            return Response({'error': '考试已结束'}, status=status.HTTP_400_BAD_REQUEST)

        # 兜底交卷：本学生此前的作答若已过截止时间且从未交卷，先用服务端草稿交上
        auto_submitted = bool(
            finalize_expired_attempts(now=now, exam=exam, student=request.user)
        )

        # 考试时间内每人只能考一次：已提交过（存在作答记录）则不能再次进入
        if Submission.objects.filter(exam=exam, student=request.user).exists():
            if auto_submitted:
                return Response(
                    {
                        'error': '作答时间已到，系统已按你最后保存的作答自动交卷',
                        'auto_submitted': True,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {'error': '你已参加过本次考试，不能重复参加'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 本次作答的截止时间：优先「考试总时长」，且不晚于考试结束时间。
        # 用 ExamAttempt 持久化，刷新页面后仍按同一截止时间倒计时。
        deadline = exam.end_time
        if exam.duration_minutes:
            deadline = min(
                now + timedelta(minutes=exam.duration_minutes), exam.end_time
            )

        attempt, _created = ExamAttempt.objects.get_or_create(
            exam=exam, student=request.user, defaults={'deadline': deadline},
        )

        remaining = int((attempt.deadline - now).total_seconds())
        if remaining <= 0:
            return Response(
                {'error': '本场考试作答时间已结束，请联系教师重置考试次数'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        questions = [
            {
                'id': eq.question.id,
                'description': eq.question.description,
                'score': eq.score,
            }
            for eq in exam.exam_questions.all()
        ]
        return Response({
            'message': '开始考试',
            'exam_title': exam.title,
            'total_score': exam.total_score,
            'questions': questions,
            'remaining_seconds': remaining,
            'duration_minutes': exam.duration_minutes,
            # 服务端保存的作答草稿：换设备（本机没有本地草稿）时据此恢复作答
            'draft': attempt.draft_answers or {},
            'draft_updated_at': attempt.draft_updated_at,
        })

    @action(detail=True, methods=['post'], url_path='draft')
    def save_draft(self, request, pk=None):
        """同步作答草稿（服务端暂存）。

        - 换设备 / 换浏览器后 `start` 会带回这份草稿，可接着作答；
        - 学生到点前关掉浏览器时，服务端按这份草稿兜底交卷
          （见 ``services.finalize_expired_attempts``）。

        请求体：{"answers": {"题目 id": "SQL", ...}}
        """
        exam = self.get_object()
        now = timezone.now()
        if now < exam.start_time:
            return Response({'error': '考试尚未开始'}, status=status.HTTP_400_BAD_REQUEST)
        if now > exam.end_time:
            return Response({'error': '考试已结束'}, status=status.HTTP_400_BAD_REQUEST)
        if Submission.objects.filter(exam=exam, student=request.user).exists():
            return Response(
                {'error': '你已提交过本次考试，不能重复提交'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        attempt = ExamAttempt.objects.filter(exam=exam, student=request.user).first()
        if attempt is None:
            return Response(
                {'error': '尚未开始考试，无法同步作答'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        remaining = int((attempt.deadline - now).total_seconds())
        if remaining <= 0:
            return Response(
                {'error': '本场考试作答时间已结束，请联系教师重置考试次数'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        answers = request.data.get('answers')
        if not isinstance(answers, dict):
            return Response(
                {'error': 'answers 必须为 {题目 id: SQL} 形式的对象'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 只保留非空作答，控制落库体积
        attempt.draft_answers = {
            str(question_id): str(sql)
            for question_id, sql in answers.items()
            if str(sql or '').strip()
        }
        attempt.draft_updated_at = now
        attempt.save(update_fields=['draft_answers', 'draft_updated_at'])
        return Response({
            'saved': True,
            'draft_updated_at': attempt.draft_updated_at,
            'remaining_seconds': remaining,
        })

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """学生提交试卷（批量提交考试中所有题目的答案）"""
        exam = self.get_object()
        now = timezone.now()

        # 校验考试时间
        if now < exam.start_time:
            return Response({'error': '考试尚未开始'}, status=status.HTTP_400_BAD_REQUEST)
        if now > exam.end_time:
            return Response({'error': '考试已结束'}, status=status.HTTP_400_BAD_REQUEST)

        # 考试时间内每人只能考一次：已提交过则不能再提交
        if Submission.objects.filter(exam=exam, student=request.user).exists():
            return Response(
                {'error': '你已提交过本次考试，不能重复提交'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        answers = request.data.get('answers', [])
        if not answers:
            return Response({'error': 'answers 为必填，格式: [{"question_id": 1, "submitted_sql": "..."}]'},
                            status=status.HTTP_400_BAD_REQUEST)

        from apps.submissions.status import PENDING

        from .services import create_exam_submission

        results = []
        queue_full = False
        created_count = 0

        for ans in answers:
            question_id = ans.get('question_id')
            submitted_sql = ans.get('submitted_sql', '')

            if not question_id or not submitted_sql:
                results.append({
                    'question_id': question_id,
                    'error': 'question_id 和 submitted_sql 为必填',
                    'execution_status': 'ERROR',
                    'score': 0,
                })
                continue

            # 先落库为待判题，再交给后台线程判题；得分由后台按考试分值换算
            submission, error = create_exam_submission(
                exam, request.user, question_id, submitted_sql,
            )
            if submission is None:          # 题目不存在
                results.append({
                    'question_id': question_id,
                    'error': error,
                    'execution_status': 'ERROR',
                    'score': 0,
                })
                continue
            if error:                       # 判题队列已满
                queue_full = True
                results.append({
                    'question_id': question_id,
                    'submission_id': submission.id,
                    'execution_status': 'ERROR',
                    'score': 0,
                    'error': error,
                })
                continue

            created_count += 1
            results.append({
                'question_id': question_id,
                'submission_id': submission.id,
                'execution_status': PENDING,
                'score': 0,
            })

        # 交卷成功后不再需要服务端草稿（否则换设备登录时会把旧草稿填回来）
        if created_count:
            ExamAttempt.objects.filter(exam=exam, student=request.user).update(
                draft_answers={}, draft_updated_at=None,
            )

        return Response({
            'exam_id': exam.id,
            'exam_title': exam.title,
            'queued': not queue_full,
            'exam_total_score': exam.total_score,
            'results': results,
        }, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['post'], url_path='reset-attempt')
    def reset_attempt(self, request, pk=None):
        """重置某位学生在本场考试的作答记录（教师端「重置考试次数」，按个人）。

        删除该学生在本场考试的全部提交，使其可以重新参加考试。
        """
        exam = self.get_object()
        student_id = request.data.get('student_id')
        if not student_id:
            return Response({'error': 'student_id 为必填'},
                            status=status.HTTP_400_BAD_REQUEST)

        student = User.objects.filter(id=student_id, user_type='student').first()
        if student is None:
            return Response({'error': '学生不存在'}, status=status.HTTP_404_NOT_FOUND)

        deleted, _ = Submission.objects.filter(exam=exam, student=student).delete()
        # 同时清除其作答会话，使该生重置后重新获得完整考试时长
        ExamAttempt.objects.filter(exam=exam, student=student).delete()
        return Response({
            'message': f'已重置「{student.name}」在本场考试的作答记录，可重新参加考试',
            'student_id': student.id,
            'deleted': deleted,
        })

    def _exam_ranking(self, exam, include_unsubmitted=False):
        """考试排名：同一题多次提交只取最高分，再按学生求和。

        返回按得分降序（同分按学号升序）排列的列表，字段与前端约定保持一致：
        student__id / student__username / student__display_name / student_name /
        total / submitted / last_submit。

        include_unsubmitted=True 时，把「已进入考试但未提交」的学生也列出
        （得分 0、submitted=False），便于教师在排名弹窗中重置其考试次数。
        """
        best_per_question = (
            Submission.objects
            .filter(exam=exam)
            .values('student_id', 'question_id')
            .annotate(best=Max('score'))
        )
        totals = {}
        for row in best_per_question:
            student_id = row['student_id']
            totals[student_id] = totals.get(student_id, 0) + (row['best'] or 0)

        users = {
            user.id: user
            for user in User.objects.filter(id__in=list(totals.keys()))
        }
        last_submit = {
            row['student_id']: row['last']
            for row in (
                Submission.objects
                .filter(exam=exam)
                .values('student_id')
                .annotate(last=Max('submission_time'))
            )
        }

        ranking = []
        for student_id, total in totals.items():
            user = users.get(student_id)
            ranking.append({
                'student__id': student_id,
                'student__username': user.username if user else '',
                'student__display_name': user.display_name if user else '',
                'student_name': user.name if user else '',
                'total': total,
                'submitted': True,
                'last_submit': last_submit.get(student_id),
            })

        # 可选：把「已进入考试但未提交」的考生也列出来（得分 0）
        if include_unsubmitted:
            for attempt in (
                ExamAttempt.objects
                .filter(exam=exam)
                .exclude(student_id__in=list(totals.keys()))
                .select_related('student')
            ):
                user = attempt.student
                ranking.append({
                    'student__id': user.id,
                    'student__username': user.username,
                    'student__display_name': user.display_name,
                    'student_name': user.name,
                    'total': 0,
                    'submitted': False,
                    'last_submit': None,
                })

        ranking.sort(key=lambda row: (-row['total'], row['student__id']))
        return ranking

    @action(detail=True, methods=['get'])
    def result(self, request, pk=None):
        """查看考试结果与排名（含已进入但未提交的考生，便于教师重置次数）"""
        exam = self.get_object()
        # 兜底交卷：教师看排名时统一兜底全场；学生只看自己的，避免替他人触发写操作
        if request.user.user_type == 'teacher':
            finalize_expired_attempts(exam=exam)
        else:
            finalize_expired_attempts(exam=exam, student=request.user)
        ranking = self._exam_ranking(exam, include_unsubmitted=True)
        for row in ranking:
            row.pop('last_submit', None)  # 排名弹窗不需要该字段
        return Response({
            'exam_title': exam.title,
            'ranking': ranking,
        })

    @action(detail=False, methods=['get'], url_path='my-scores')
    def my_scores(self, request):
        """当前学生每场考试的得分（同一题多次提交只取最高分后求和）。

        供学生端「考试记录」列表展示「得分」列；返回的考试 id 也可用于判断
        该生是否参加过某场考试。统计口径与教师端排名 / 成绩单导出一致。
        """
        # 兜底交卷：本人到点未交卷但有草稿的考试先交上，得分才不会漏
        finalize_expired_attempts(student=request.user)
        rows = (
            Submission.objects
            .filter(student=request.user, exam__isnull=False)
            .values('exam_id', 'question_id')
            .annotate(best=Max('score'))
        )
        scores = {}
        for row in rows:
            exam_id = row['exam_id']
            scores[exam_id] = scores.get(exam_id, 0) + (row['best'] or 0)
        return Response({'scores': scores})

    @action(detail=True, methods=['get'])
    def export(self, request, pk=None):
        """导出考试成绩单（CSV）。仅教师可用，且考试结束后才可导出。"""
        exam = self.get_object()
        if timezone.now() < exam.end_time:
            return Response(
                {'error': '考试结束后才能导出成绩'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 导出前先兜底交卷，避免「关掉浏览器没交卷」的考生成绩漏掉
        finalize_expired_attempts(exam=exam)
        ranking = self._exam_ranking(exam)

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        # 写入 UTF-8 BOM，保证 Excel 打开中文不乱码
        response.write('\ufeff')
        writer = csv.writer(response)
        writer.writerow(['排名', '登录名', '姓名', '得分', '考试总分', '最近提交时间'])
        for index, row in enumerate(ranking, start=1):
            last = row.get('last_submit')
            writer.writerow([
                index,
                row['student__username'],
                row['student_name'],
                row['total'],
                exam.total_score,
                timezone.localtime(last).strftime('%Y-%m-%d %H:%M:%S') if last else '',
            ])

        filename = f'{exam.title}-成绩单.csv'
        response['Content-Disposition'] = (
            'attachment; filename="scores.csv"; '
            f"filename*=UTF-8''{quote(filename)}"
        )
        return response
