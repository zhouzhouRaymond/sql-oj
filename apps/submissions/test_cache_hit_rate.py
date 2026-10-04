"""判题结果缓存的命中率测试。

缓存实现见 ``judge_cache.py``：同一（题目 + 规范化 SQL + 用例 + 环境指纹）
在 TTL 内只应真正判题一次。本文件在 ``_judge_with_guards`` 这一层统计：
重复提交命中缓存后不再调用判题服务，命中率 = hits / (hits + misses)。

测试不依赖数据库，可直接在本地或 CI 运行。
"""
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from . import judge_cache
from .judging import _judge_with_guards

QUESTION_ID = 42
SQL = 'select id from courses'
CREATE_TABLE_SQL = 'CREATE TABLE courses (id INT);'
CASES = [{'test_input': '', 'expected_output': 'id\n1'}]

ACCEPTED_RESULT = {
    'passed': True,
    'execution_status': 'ACCEPTED',
    'score': 100,
    'details': [{'test_case_id': 0, 'passed': True, 'actual_output': 'id\n1'}],
}
WRONG_ANSWER_RESULT = {
    'passed': False,
    'execution_status': 'WRONG_ANSWER',
    'score': 0,
    'details': [{'test_case_id': 0, 'passed': False, 'actual_output': ''}],
}
TRANSIENT_ERROR_RESULT = {
    'passed': False,
    'execution_status': 'ERROR',
    'score': 0,
    'details': [],
}
SCHEMA_CASES = [{
    'test_input': '',
    'expected_schema': {'tables': {'t': {'columns': []}}},
    'probes': [],
}]
SCHEMA_ACCEPTED_RESULT = {
    'passed': True,
    'execution_status': 'ACCEPTED',
    'score': 100,
    'details': [{
        'test_case_id': 0,
        'passed': True,
        'actual_output': '表 t:',
        'checks': [{'name': '表 t', 'passed': True, 'detail': ''}],
    }],
}


@override_settings(JUDGE_RESULT_CACHE_TTL=3600)
class JudgeResultCacheHitRateTests(SimpleTestCase):
    """同一份判题输入重复提交时，后续请求应当命中缓存。"""

    def setUp(self):
        cache.clear()
        judge_cache.reset_cache_stats()

    def _judge(self, sql=SQL, cases=None):
        return _judge_with_guards(
            QUESTION_ID, sql, cases or CASES, CREATE_TABLE_SQL
        )

    def test_repeated_identical_submissions_judge_only_once(self):
        with patch(
            'apps.submissions.judging.judge_submission_strict',
            return_value=dict(ACCEPTED_RESULT),
        ) as judge:
            results = [self._judge() for _ in range(10)]

        self.assertEqual(judge.call_count, 1)
        self.assertTrue(all(r['execution_status'] == 'ACCEPTED' for r in results))
        stats = judge_cache.cache_stats()
        self.assertEqual(stats['hits'], 9)
        self.assertEqual(stats['misses'], 1)
        self.assertAlmostEqual(stats['hit_rate'], 0.9, places=4)

    def test_equivalent_sql_forms_share_one_cache_entry(self):
        with patch(
            'apps.submissions.judging.judge_submission_strict',
            return_value=dict(WRONG_ANSWER_RESULT),
        ) as judge:
            self._judge('select  id   from courses')
            self._judge('SELECT id FROM courses')

        self.assertEqual(judge.call_count, 1)
        stats = judge_cache.cache_stats()
        self.assertEqual(stats['hits'], 1)
        self.assertAlmostEqual(stats['hit_rate'], 0.5, places=4)

    def test_transient_errors_are_not_cached(self):
        with patch(
            'apps.submissions.judging.judge_submission_strict',
            return_value=dict(TRANSIENT_ERROR_RESULT),
        ) as judge:
            self._judge()
            self._judge()
            self._judge()

        # ERROR 属于瞬时故障，每次都重新判题，不会被旧错误污染
        self.assertEqual(judge.call_count, 3)
        stats = judge_cache.cache_stats()
        self.assertEqual(stats['hits'], 0)
        self.assertEqual(stats['misses'], 3)

    def test_mixed_workload_reports_expected_hit_rate(self):
        sqls = [f'select id from courses where id = {i}' for i in range(5)]
        with patch(
            'apps.submissions.judging.judge_submission_strict',
            return_value=dict(ACCEPTED_RESULT),
        ) as judge:
            # 5 条不同 SQL 各重复 20 次，交错提交
            for _ in range(20):
                for sql in sqls:
                    self._judge(sql)

        self.assertEqual(judge.call_count, 5)
        stats = judge_cache.cache_stats()
        self.assertEqual(stats['lookups'], 100)
        self.assertEqual(stats['hits'], 95)
        self.assertAlmostEqual(stats['hit_rate'], 0.95, places=4)

    @override_settings(JUDGE_RESULT_CACHE_TTL=0)
    def test_disabled_cache_never_reports_a_hit_rate(self):
        with patch(
            'apps.submissions.judging.judge_submission_strict',
            return_value=dict(ACCEPTED_RESULT),
        ) as judge:
            self._judge()
            self._judge()
            self._judge()

        self.assertEqual(judge.call_count, 3)
        stats = judge_cache.cache_stats()
        # 关闭缓存时的查询不计入命中率分母，避免被误读成「命中率 0」
        self.assertEqual(stats['lookups'], 0)
        self.assertEqual(stats['lookups_while_disabled'], 3)
        self.assertEqual(stats['hit_rate'], 0.0)

    def test_schema_mode_results_are_cached_like_query_mode(self):
        with patch(
            'apps.submissions.judging.judge_submission_strict',
            return_value=dict(SCHEMA_ACCEPTED_RESULT),
        ) as judge:
            for _ in range(5):
                _judge_with_guards(
                    QUESTION_ID, 'create table t (id int)', SCHEMA_CASES, '',
                    judge_mode='schema',
                )

        self.assertEqual(judge.call_count, 1)
        stats = judge_cache.cache_stats()
        self.assertEqual(stats['hits'], 4)
        self.assertEqual(stats['misses'], 1)
