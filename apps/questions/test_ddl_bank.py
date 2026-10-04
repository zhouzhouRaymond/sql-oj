"""DDL 题库内容校验与导入命令测试。"""
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from apps.users.models import User

from .ddl_exercise_bank import (
    CATEGORIES,
    DDL_EXERCISES,
    supported_exercises,
    validate_bank,
)
from .models import Answer, Question

FAKE_SCHEMA = {
    'tables': {
        't': {
            'columns': [
                {'name': 'id', 'type': 'integer', 'not_null': True, 'default': 'serial'},
            ],
        },
    },
}


class DdlBankStructureTests(SimpleTestCase):
    def test_bank_is_valid(self):
        self.assertEqual(validate_bank(), [])

    def test_bank_covers_every_category_with_many_questions(self):
        supported = supported_exercises()
        self.assertGreaterEqual(len(supported), 25)
        self.assertEqual({item['category'] for item in supported}, set(CATEGORIES))

    def test_unsupported_items_are_documented(self):
        for item in DDL_EXERCISES:
            if item.get('supported', True):
                continue
            with self.subTest(slug=item['slug']):
                # 暂不支持的题目不应带探针（否则导入时会被跳过却看起来可用）
                self.assertEqual(item['probes'], [])

    def test_supported_items_have_reference_answer(self):
        for item in supported_exercises():
            with self.subTest(slug=item['slug']):
                self.assertTrue(item['reference_sql'].strip())
                self.assertIn(item['difficulty'], ('easy', 'medium', 'hard'))
                self.assertIn(item['category'], CATEGORIES)


class SeedDdlExercisesTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='t_ddl_seed', password='x', user_type='teacher',
        )

    def _seed(self, *args):
        call_command('seed_ddl_exercises', '--teacher', 't_ddl_seed', *args)

    @patch(
        'apps.questions.management.commands.seed_ddl_exercises.verify_reference',
        return_value={'execution_status': 'ACCEPTED'},
    )
    @patch(
        'apps.questions.management.commands.seed_ddl_exercises.introspect_reference',
        return_value=FAKE_SCHEMA,
    )
    def test_seed_creates_schema_questions_and_verifies(self, introspect, verify):
        self._seed('--limit', '3', '--verify')

        questions = Question.objects.filter(judge_mode='schema')
        self.assertEqual(questions.count(), 3)
        self.assertEqual(verify.call_count, 3)
        expected_answers = {
            item['title']: item['reference_sql']
            for item in supported_exercises()[:3]
        }
        for question in questions:
            self.assertEqual(question.test_cases.count(), 1)
            case = question.test_cases.first()
            self.assertEqual(case.expected_schema, FAKE_SCHEMA)
            self.assertEqual(case.expected_output, '')
            # 标准答案要写入 Answer.correct_sql，教师端才能看到正确答案
            self.assertEqual(question.answers.count(), 1)
            self.assertEqual(
                question.answers.first().correct_sql,
                expected_answers[question.title],
            )

    @patch(
        'apps.questions.management.commands.seed_ddl_exercises.introspect_reference',
        return_value=FAKE_SCHEMA,
    )
    def test_seed_is_idempotent(self, introspect):
        self._seed('--limit', '2')
        self._seed('--limit', '2')

        questions = Question.objects.filter(judge_mode='schema')
        self.assertEqual(questions.count(), 2)
        for question in questions:
            self.assertEqual(question.test_cases.count(), 1)

    @patch(
        'apps.questions.management.commands.seed_ddl_exercises.introspect_reference',
        return_value=FAKE_SCHEMA,
    )
    def test_dry_run_writes_nothing(self, introspect):
        self._seed('--limit', '2', '--dry-run')
        self.assertFalse(Question.objects.filter(judge_mode='schema').exists())

    @patch(
        'apps.questions.management.commands.seed_ddl_exercises.introspect_reference',
        return_value=FAKE_SCHEMA,
    )
    def test_reseed_replaces_stale_answer(self, introspect):
        self._seed('--limit', '1')
        question = Question.objects.get(judge_mode='schema')
        Answer.objects.filter(question=question).update(correct_sql='STALE')

        self._seed('--limit', '1')

        self.assertEqual(question.answers.count(), 1)
        self.assertNotEqual(question.answers.first().correct_sql, 'STALE')

    def test_reset_removes_imported_questions(self):
        title = DDL_EXERCISES[0]['title']
        Question.objects.create(
            title=title, description='x', difficulty='easy',
            teacher=self.teacher, judge_mode='schema',
        )
        call_command('seed_ddl_exercises', '--reset')
        self.assertFalse(Question.objects.filter(title=title).exists())

    @patch(
        'apps.questions.management.commands.seed_ddl_exercises.introspect_reference',
        side_effect=CommandError('参考 DDL 内省失败: boom'),
    )
    def test_introspect_failure_is_reported_and_writes_nothing(self, introspect):
        with self.assertRaises(CommandError):
            self._seed('--limit', '1')
        self.assertFalse(Question.objects.filter(judge_mode='schema').exists())

    @patch(
        'apps.questions.management.commands.seed_ddl_exercises.verify_reference',
        return_value={'execution_status': 'WRONG_ANSWER', 'details': []},
    )
    @patch(
        'apps.questions.management.commands.seed_ddl_exercises.introspect_reference',
        return_value=FAKE_SCHEMA,
    )
    def test_reference_answer_rejected_stops_import(self, introspect, verify):
        with self.assertRaises(CommandError):
            self._seed('--limit', '1', '--verify')
        self.assertFalse(Question.objects.filter(judge_mode='schema').exists())

    @patch(
        'apps.questions.management.commands.seed_ddl_exercises.introspect_reference',
        return_value=FAKE_SCHEMA,
    )
    def test_category_filter_limits_imported_questions(self, introspect):
        self._seed('--category', 'alter')
        questions = Question.objects.filter(judge_mode='schema')
        self.assertEqual(questions.count(), 5)  # 5 道 ALTER 题
        expected_titles = {
            item['title'] for item in supported_exercises() if item['category'] == 'alter'
        }
        self.assertEqual({q.title for q in questions}, expected_titles)
