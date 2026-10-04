"""考试服务层的无数据库单元测试。"""
from django.test import SimpleTestCase

from .services import draft_answers_as_list


class DraftAnswersTests(SimpleTestCase):
    def test_empty_draft_returns_empty_list(self):
        self.assertEqual(draft_answers_as_list(None), [])
        self.assertEqual(draft_answers_as_list({}), [])

    def test_skips_blank_answers(self):
        draft = {'1': 'select 1', '2': '   ', '3': None}
        self.assertEqual(
            draft_answers_as_list(draft),
            [{'question_id': 1, 'submitted_sql': 'select 1'}],
        )

    def test_coerces_question_id_to_int(self):
        draft = {'7': 'select 1'}
        self.assertEqual(
            draft_answers_as_list(draft),
            [{'question_id': 7, 'submitted_sql': 'select 1'}],
        )

    def test_ignores_non_numeric_question_ids(self):
        draft = {'abc': 'select 1', '5': 'select 2'}
        self.assertEqual(
            draft_answers_as_list(draft),
            [{'question_id': 5, 'submitted_sql': 'select 2'}],
        )
