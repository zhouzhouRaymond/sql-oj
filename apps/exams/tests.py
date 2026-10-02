from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.questions.models import Question
from apps.submissions.models import Submission
from apps.users.models import User
from .models import Exam, ExamAttempt


class ExamVisibilityTests(APITestCase):
    """教师可控制考试是否对学生可见（is_visible）。"""

    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='t_exam_vis', password='pass1234', user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='s_exam_vis', password='pass1234', user_type='student',
        )
        now = timezone.now()
        self.visible = Exam.objects.create(
            title='公开考试', start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1), total_score=100,
            teacher=self.teacher, is_visible=True,
        )
        self.hidden = Exam.objects.create(
            title='隐藏考试', start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1), total_score=100,
            teacher=self.teacher, is_visible=False,
        )

    def _list_ids(self):
        resp = self.client.get('/api/exams/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return [row['id'] for row in resp.data['results']]

    def test_new_exam_is_visible_by_default(self):
        now = timezone.now()
        exam = Exam.objects.create(
            title='默认可见', start_time=now,
            end_time=now + timedelta(hours=1), total_score=100,
            teacher=self.teacher,
        )
        self.assertTrue(exam.is_visible)

    def test_student_list_excludes_hidden_exam(self):
        self.client.force_authenticate(self.student)
        ids = self._list_ids()
        self.assertIn(self.visible.id, ids)
        self.assertNotIn(self.hidden.id, ids)

    def test_student_cannot_enter_hidden_exam(self):
        self.client.force_authenticate(self.student)
        self.assertEqual(
            self.client.get(f'/api/exams/{self.hidden.id}/').status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.post(f'/api/exams/{self.hidden.id}/start/').status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_teacher_list_includes_hidden_exam(self):
        self.client.force_authenticate(self.teacher)
        self.assertIn(self.hidden.id, self._list_ids())
        self.assertIn(self.visible.id, self._list_ids())

    def test_teacher_can_toggle_exam_visibility(self):
        self.client.force_authenticate(self.teacher)
        resp = self.client.patch(
            f'/api/exams/{self.visible.id}/',
            {'is_visible': False}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.visible.refresh_from_db()
        self.assertFalse(self.visible.is_visible)

        self.client.force_authenticate(self.student)
        self.assertNotIn(self.visible.id, self._list_ids())

    def test_student_cannot_toggle_exam_visibility(self):
        self.client.force_authenticate(self.student)
        resp = self.client.patch(
            f'/api/exams/{self.visible.id}/',
            {'is_visible': False}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.visible.refresh_from_db()
        self.assertTrue(self.visible.is_visible)


class ExamExportTests(APITestCase):
    """考试成绩导出（考试结束后可用）+ 排名按「每题最高分」计算。"""

    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='t_export', password='pass1234', user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='s_export', password='pass1234', user_type='student',
        )
        now = timezone.now()
        self.ended = Exam.objects.create(
            title='已结束考试', start_time=now - timedelta(hours=2),
            end_time=now - timedelta(hours=1), total_score=100,
            teacher=self.teacher, student_scope='all',
        )
        self.running = Exam.objects.create(
            title='进行中考试', start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1), total_score=100,
            teacher=self.teacher, student_scope='all',
        )
        self.question = Question.objects.create(
            description='题目', difficulty='easy', teacher=self.teacher,
        )

    def _submit(self, exam, score):
        return Submission.objects.create(
            student=self.student, question=self.question, exam=exam,
            submitted_sql='SELECT 1', score=score,
            execution_status='ACCEPTED',
        )

    def test_cannot_export_before_exam_ends(self):
        self.client.force_authenticate(self.teacher)
        resp = self.client.get(f'/api/exams/{self.running.id}/export/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('结束后', resp.data['error'])

    def test_student_cannot_export(self):
        self.client.force_authenticate(self.student)
        resp = self.client.get(f'/api/exams/{self.ended.id}/export/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_teacher_can_export_after_exam_ends(self):
        self._submit(self.ended, 40)
        self.client.force_authenticate(self.teacher)
        resp = self.client.get(f'/api/exams/{self.ended.id}/export/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('text/csv', resp['Content-Type'])
        self.assertIn('attachment', resp['Content-Disposition'])
        body = resp.content.decode('utf-8')
        self.assertIn('排名', body)
        self.assertIn('登录名', body)
        self.assertIn(self.student.username, body)
        self.assertIn('40', body)

    def test_ranking_counts_best_score_per_question(self):
        # 同一题提交两次：只计最高分，不能累加
        self._submit(self.ended, 10)
        self._submit(self.ended, 30)
        self.client.force_authenticate(self.teacher)
        resp = self.client.get(f'/api/exams/{self.ended.id}/result/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['ranking'][0]['total'], 30)


class ExamSingleAttemptTests(APITestCase):
    """考试时间内每位学生只能考一次；教师可按个人重置考试次数。"""

    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='t_once', password='pass1234', user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='s_once', password='pass1234', user_type='student',
        )
        now = timezone.now()
        self.exam = Exam.objects.create(
            title='单次考试', start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1), total_score=100,
            teacher=self.teacher, student_scope='all',
        )
        self.question = Question.objects.create(
            description='题目', difficulty='easy', teacher=self.teacher,
        )

    def _take(self):
        return Submission.objects.create(
            student=self.student, question=self.question, exam=self.exam,
            submitted_sql='SELECT 1', score=10, execution_status='ACCEPTED',
        )

    def test_student_can_start_before_submitting(self):
        self.client.force_authenticate(self.student)
        resp = self.client.post(f'/api/exams/{self.exam.id}/start/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_cannot_start_again_after_submitting(self):
        self._take()
        self.client.force_authenticate(self.student)
        resp = self.client.post(f'/api/exams/{self.exam.id}/start/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('已参加过', resp.data['error'])

    def test_cannot_submit_twice(self):
        self._take()
        self.client.force_authenticate(self.student)
        resp = self.client.post(
            f'/api/exams/{self.exam.id}/submit/',
            {'answers': [
                {'question_id': self.question.id, 'submitted_sql': 'SELECT 1'},
            ]},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('已提交过', resp.data['error'])

    def test_teacher_can_reset_student_attempt(self):
        self._take()
        self.client.force_authenticate(self.teacher)
        resp = self.client.post(
            f'/api/exams/{self.exam.id}/reset-attempt/',
            {'student_id': self.student.id}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['deleted'], 1)
        self.assertFalse(
            Submission.objects.filter(exam=self.exam, student=self.student).exists()
        )

        # 重置后该学生可以重新开始考试
        self.client.force_authenticate(self.student)
        self.assertEqual(
            self.client.post(f'/api/exams/{self.exam.id}/start/').status_code,
            status.HTTP_200_OK,
        )

    def test_reset_requires_student_id(self):
        self.client.force_authenticate(self.teacher)
        resp = self.client.post(
            f'/api/exams/{self.exam.id}/reset-attempt/', {}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_student_cannot_reset_attempt(self):
        self.client.force_authenticate(self.student)
        resp = self.client.post(
            f'/api/exams/{self.exam.id}/reset-attempt/',
            {'student_id': self.student.id}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class ExamDurationTests(APITestCase):
    """考试总时长：进入考试后按剩余时间倒计时，刷新不会重置计时。"""

    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='t_dur', password='pass1234', user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='s_dur', password='pass1234', user_type='student',
        )
        now = timezone.now()
        self.exam = Exam.objects.create(
            title='限时考试', start_time=now - timedelta(minutes=10),
            end_time=now + timedelta(hours=2), total_score=100,
            teacher=self.teacher, student_scope='all', duration_minutes=30,
        )

    def test_new_exam_defaults_to_no_time_limit(self):
        now = timezone.now()
        exam = Exam.objects.create(
            title='不限时', start_time=now, end_time=now + timedelta(hours=1),
            total_score=100, teacher=self.teacher,
        )
        self.assertEqual(exam.duration_minutes, 0)

    def test_start_returns_remaining_seconds(self):
        self.client.force_authenticate(self.student)
        resp = self.client.post(f'/api/exams/{self.exam.id}/start/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # 30 分钟 = 1800 秒（允许几秒执行误差）
        self.assertLessEqual(resp.data['remaining_seconds'], 30 * 60)
        self.assertGreater(resp.data['remaining_seconds'], 30 * 60 - 10)

    def test_restart_does_not_reset_countdown(self):
        self.client.force_authenticate(self.student)
        self.client.post(f'/api/exams/{self.exam.id}/start/')
        # 模拟已经过去一段时间（把截止时间改到 100 秒后）
        ExamAttempt.objects.filter(exam=self.exam, student=self.student).update(
            deadline=timezone.now() + timedelta(seconds=100),
        )
        resp = self.client.post(f'/api/exams/{self.exam.id}/start/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertLessEqual(resp.data['remaining_seconds'], 101)

    def test_start_blocked_after_countdown_ends(self):
        ExamAttempt.objects.create(
            exam=self.exam, student=self.student,
            deadline=timezone.now() - timedelta(seconds=1),
        )
        self.client.force_authenticate(self.student)
        resp = self.client.post(f'/api/exams/{self.exam.id}/start/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('作答时间已结束', resp.data['error'])

    def test_duration_capped_by_exam_end_time(self):
        now = timezone.now()
        short = Exam.objects.create(
            title='窗口很短', start_time=now - timedelta(minutes=10),
            end_time=now + timedelta(minutes=5), total_score=100,
            teacher=self.teacher, student_scope='all', duration_minutes=120,
        )
        self.client.force_authenticate(self.student)
        resp = self.client.post(f'/api/exams/{short.id}/start/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertLessEqual(resp.data['remaining_seconds'], 5 * 60 + 1)

    def test_exam_without_duration_uses_window(self):
        now = timezone.now()
        unlimited = Exam.objects.create(
            title='不限时', start_time=now - timedelta(minutes=1),
            end_time=now + timedelta(minutes=45), total_score=100,
            teacher=self.teacher, student_scope='all', duration_minutes=0,
        )
        self.client.force_authenticate(self.student)
        resp = self.client.post(f'/api/exams/{unlimited.id}/start/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreater(resp.data['remaining_seconds'], 44 * 60)

    def test_unsubmitted_participant_listed_in_ranking(self):
        ExamAttempt.objects.create(
            exam=self.exam, student=self.student,
            deadline=timezone.now() + timedelta(minutes=10),
        )
        self.client.force_authenticate(self.teacher)
        resp = self.client.get(f'/api/exams/{self.exam.id}/result/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data['ranking']), 1)
        row = resp.data['ranking'][0]
        self.assertEqual(row['student__username'], self.student.username)
        self.assertFalse(row['submitted'])

    def test_reset_clears_attempt_and_grants_full_time(self):
        ExamAttempt.objects.create(
            exam=self.exam, student=self.student,
            deadline=timezone.now() - timedelta(seconds=1),
        )
        self.client.force_authenticate(self.teacher)
        resp = self.client.post(
            f'/api/exams/{self.exam.id}/reset-attempt/',
            {'student_id': self.student.id}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(
            ExamAttempt.objects.filter(exam=self.exam, student=self.student).exists()
        )

        self.client.force_authenticate(self.student)
        again = self.client.post(f'/api/exams/{self.exam.id}/start/')
        self.assertEqual(again.status_code, status.HTTP_200_OK)
        self.assertGreater(again.data['remaining_seconds'], 30 * 60 - 10)


class ExamMyScoresTests(APITestCase):
    """学生查看自己每场考试的得分（GET /api/exams/my-scores/）。

    口径与教师端排名 / 成绩单导出一致：同一题多次提交只取最高分，再把各题最高分求和；
    不含练习提交（exam 为空），也不含其他学生的提交。
    """

    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='t_myscore', password='pass1234', user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='s_myscore', password='pass1234', user_type='student',
        )
        self.other = User.objects.create_user(
            username='s_myscore_other', password='pass1234', user_type='student',
        )
        now = timezone.now()
        self.exam = Exam.objects.create(
            title='得分考试A', start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1), total_score=100,
            teacher=self.teacher, student_scope='all',
        )
        self.exam2 = Exam.objects.create(
            title='得分考试B', start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1), total_score=50,
            teacher=self.teacher, student_scope='all',
        )
        self.q1 = Question.objects.create(
            description='题1', difficulty='easy', teacher=self.teacher,
        )
        self.q2 = Question.objects.create(
            description='题2', difficulty='easy', teacher=self.teacher,
        )

    def _submit(self, exam, question, score, student=None):
        return Submission.objects.create(
            student=student or self.student, question=question, exam=exam,
            submitted_sql='SELECT 1', score=score, execution_status='ACCEPTED',
        )

    def _scores(self):
        resp = self.client.get('/api/exams/my-scores/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return {int(exam_id): value for exam_id, value in resp.data['scores'].items()}

    def test_sums_best_score_per_question(self):
        # 题1 提交两次（5、8）只取最高分 8；题2 提交一次 7 → 合计 15
        self._submit(self.exam, self.q1, 5)
        self._submit(self.exam, self.q1, 8)
        self._submit(self.exam, self.q2, 7)

        self.client.force_authenticate(self.student)
        self.assertEqual(self._scores(), {self.exam.id: 15})

    def test_scores_are_per_exam(self):
        self._submit(self.exam, self.q1, 10)
        self._submit(self.exam2, self.q1, 4)
        self._submit(self.exam2, self.q2, 6)

        self.client.force_authenticate(self.student)
        self.assertEqual(self._scores(), {self.exam.id: 10, self.exam2.id: 10})

    def test_ignores_other_students_and_practice_submissions(self):
        self._submit(self.exam, self.q1, 9)
        # 其他学生的提交不参与统计
        self._submit(self.exam, self.q2, 10, student=self.other)
        # 练习提交（exam 为空）不参与统计
        self._submit(None, self.q1, 10)

        self.client.force_authenticate(self.student)
        self.assertEqual(self._scores(), {self.exam.id: 9})

    def test_matches_ranking_total(self):
        self._submit(self.exam, self.q1, 3)
        self._submit(self.exam, self.q1, 9)
        self._submit(self.exam, self.q2, 6)

        self.client.force_authenticate(self.student)
        my_total = self._scores()[self.exam.id]

        # 与教师端排名里本人得分保持一致
        self.client.force_authenticate(self.teacher)
        resp = self.client.get(f'/api/exams/{self.exam.id}/result/')
        row = next(
            item for item in resp.data['ranking']
            if item['student__id'] == self.student.id
        )
        self.assertEqual(my_total, row['total'])

    def test_requires_login(self):
        self.assertEqual(
            self.client.get('/api/exams/my-scores/').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


class ExamDraftAndAutoSubmitTests(APITestCase):
    """作答草稿（服务端同步，换设备可恢复）与到点兜底交卷。

    对应「学生答题时误关浏览器」的场景：
    - 作答内容会定时同步到服务端，换设备登录也能接着答；
    - 到点仍未交卷时，服务端按最后同步的草稿自动交卷，成绩不会漏。
    """

    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='t_draft', password='pass1234', user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='s_draft', password='pass1234', user_type='student',
        )
        now = timezone.now()
        self.exam = Exam.objects.create(
            title='草稿考试', start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1), total_score=100,
            teacher=self.teacher, student_scope='all', duration_minutes=30,
        )
        self.q1 = Question.objects.create(
            description='草稿题1', difficulty='easy', teacher=self.teacher,
        )
        self.q2 = Question.objects.create(
            description='草稿题2', difficulty='easy', teacher=self.teacher,
        )

    def _start(self):
        self.client.force_authenticate(self.student)
        return self.client.post(f'/api/exams/{self.exam.id}/start/')

    def _save_draft(self, answers):
        self.client.force_authenticate(self.student)
        return self.client.post(
            f'/api/exams/{self.exam.id}/draft/', {'answers': answers}, format='json',
        )

    def _expire_attempt(self):
        ExamAttempt.objects.filter(exam=self.exam, student=self.student).update(
            deadline=timezone.now() - timedelta(seconds=1)
        )

    def test_draft_saved_and_returned_on_reenter(self):
        self._start()
        resp = self._save_draft({
            str(self.q1.id): 'SELECT 1', str(self.q2.id): 'SELECT 2',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data['saved'])
        self.assertTrue(resp.data['draft_updated_at'])

        # 换设备重新进入：服务端把草稿带回来
        again = self._start()
        self.assertEqual(again.status_code, status.HTTP_200_OK)
        self.assertEqual(
            again.data['draft'],
            {str(self.q1.id): 'SELECT 1', str(self.q2.id): 'SELECT 2'},
        )

    def test_draft_ignores_blank_answers(self):
        self._start()
        self._save_draft({str(self.q1.id): 'SELECT 1', str(self.q2.id): '   '})
        again = self._start()
        self.assertEqual(again.data['draft'], {str(self.q1.id): 'SELECT 1'})

    def test_draft_requires_starting_exam(self):
        resp = self._save_draft({str(self.q1.id): 'SELECT 1'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('尚未开始', resp.data['error'])

    def test_draft_rejected_after_deadline(self):
        self._start()
        self._expire_attempt()
        resp = self._save_draft({str(self.q1.id): 'SELECT 1'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('作答时间已结束', resp.data['error'])

    def test_draft_rejected_after_submitting(self):
        self._start()
        self._save_draft({str(self.q1.id): 'SELECT 1'})
        self.client.force_authenticate(self.student)
        submitted = self.client.post(
            f'/api/exams/{self.exam.id}/submit/',
            {'answers': [{'question_id': self.q1.id, 'submitted_sql': 'SELECT 1'}]},
            format='json',
        )
        self.assertEqual(submitted.status_code, status.HTTP_202_ACCEPTED)

        resp = self._save_draft({str(self.q2.id): 'SELECT 2'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_submit_clears_draft(self):
        self._start()
        self._save_draft({str(self.q1.id): 'SELECT 1'})
        self.client.force_authenticate(self.student)
        self.client.post(
            f'/api/exams/{self.exam.id}/submit/',
            {'answers': [{'question_id': self.q1.id, 'submitted_sql': 'SELECT 1'}]},
            format='json',
        )
        attempt = ExamAttempt.objects.get(exam=self.exam, student=self.student)
        self.assertEqual(attempt.draft_answers, {})
        self.assertIsNone(attempt.draft_updated_at)

    def test_fallback_auto_submit_uses_last_draft(self):
        """到点未交卷：教师看排名时触发兜底，本次作答按最后草稿交上。"""
        self._start()
        self._save_draft({str(self.q1.id): 'SELECT 1'})
        self._expire_attempt()

        self.client.force_authenticate(self.teacher)
        resp = self.client.get(f'/api/exams/{self.exam.id}/result/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        submissions = Submission.objects.filter(exam=self.exam, student=self.student)
        self.assertEqual(submissions.count(), 1)
        self.assertEqual(submissions.first().submitted_sql, 'SELECT 1')
        # 排名里该生变成「已提交」
        row = next(
            item for item in resp.data['ranking']
            if item['student__id'] == self.student.id
        )
        self.assertTrue(row['submitted'])

    def test_start_informs_auto_submitted_student(self):
        self._start()
        self._save_draft({str(self.q1.id): 'SELECT 1'})
        self._expire_attempt()

        again = self._start()
        self.assertEqual(again.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(again.data['auto_submitted'])
        self.assertIn('自动交卷', again.data['error'])

    def test_no_auto_submit_without_draft(self):
        """从未作答（没有草稿）的考生保持「未提交」，提示语不变。"""
        self._start()
        self._expire_attempt()

        again = self._start()
        self.assertEqual(again.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('作答时间已结束', again.data['error'])
        self.assertFalse(
            Submission.objects.filter(exam=self.exam, student=self.student).exists()
        )

    def test_my_scores_triggers_fallback_auto_submit(self):
        """学生查看自己的得分时也会兜底交卷（保证成绩不漏）。"""
        self._start()
        self._save_draft({str(self.q1.id): 'SELECT 1'})
        self._expire_attempt()

        self.client.force_authenticate(self.student)
        resp = self.client.get('/api/exams/my-scores/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        scores = {int(k): v for k, v in resp.data['scores'].items()}
        self.assertIn(self.exam.id, scores)
        self.assertTrue(
            Submission.objects.filter(exam=self.exam, student=self.student).exists()
        )


class ExamSharedAcrossTeachersTests(APITestCase):
    """考试对所有教师共享：任何教师都能看到 / 编辑其他教师创建的考试；学生能看到所有教师的考试。"""

    def setUp(self):
        cache.clear()
        self.teacher_a = User.objects.create_user(
            username='t_share_a', password='pass1234', user_type='teacher',
            display_name='甲老师',
        )
        self.teacher_b = User.objects.create_user(
            username='t_share_b', password='pass1234', user_type='teacher',
            display_name='乙老师',
        )
        self.student = User.objects.create_user(
            username='s_share', password='pass1234', user_type='student',
        )
        now = timezone.now()
        self.exam_a = Exam.objects.create(
            title='甲老师的考试', start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1), total_score=100,
            teacher=self.teacher_a, student_scope='all',
        )
        self.exam_b = Exam.objects.create(
            title='乙老师的考试', start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1), total_score=100,
            teacher=self.teacher_b, student_scope='all',
        )

    def _list_rows(self):
        resp = self.client.get('/api/exams/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return resp.data['results']

    def test_teacher_sees_exams_created_by_others(self):
        self.client.force_authenticate(self.teacher_b)
        ids = [row['id'] for row in self._list_rows()]
        self.assertIn(self.exam_a.id, ids)
        self.assertIn(self.exam_b.id, ids)

    def test_list_exposes_creator_name_and_username(self):
        self.client.force_authenticate(self.teacher_b)
        row = next(r for r in self._list_rows() if r['id'] == self.exam_a.id)
        self.assertEqual(row['teacher_name'], '甲老师')
        self.assertEqual(row['teacher_username'], 't_share_a')

    def test_teacher_can_edit_others_exam_and_creator_unchanged(self):
        self.client.force_authenticate(self.teacher_b)
        resp = self.client.patch(
            f'/api/exams/{self.exam_a.id}/', {'is_visible': False}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.exam_a.refresh_from_db()
        self.assertFalse(self.exam_a.is_visible)
        # 谁编辑都不会改变创建人
        self.assertEqual(self.exam_a.teacher_id, self.teacher_a.id)

    def test_teacher_can_read_others_exam_detail_and_result(self):
        self.client.force_authenticate(self.teacher_b)
        self.assertEqual(
            self.client.get(f'/api/exams/{self.exam_a.id}/').status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.get(f'/api/exams/{self.exam_a.id}/result/').status_code,
            status.HTTP_200_OK,
        )

    def test_teacher_can_delete_others_exam(self):
        self.client.force_authenticate(self.teacher_b)
        resp = self.client.delete(f'/api/exams/{self.exam_a.id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Exam.objects.filter(id=self.exam_a.id).exists())

    def test_student_sees_exams_of_all_teachers(self):
        self.client.force_authenticate(self.student)
        ids = [row['id'] for row in self._list_rows()]
        self.assertIn(self.exam_a.id, ids)
        self.assertIn(self.exam_b.id, ids)

    def test_student_still_cannot_modify_exams(self):
        self.client.force_authenticate(self.student)
        self.assertEqual(
            self.client.patch(
                f'/api/exams/{self.exam_a.id}/', {'is_visible': False}, format='json',
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.delete(f'/api/exams/{self.exam_a.id}/').status_code,
            status.HTTP_403_FORBIDDEN,
        )

