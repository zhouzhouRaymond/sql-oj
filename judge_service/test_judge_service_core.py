"""判题服务核心纯函数测试（查询结果比较 / 多判题库分片 / 辅助函数）。

不依赖数据库，可直接运行：
    docker compose exec -T judge-service python -m unittest -v test_judge_service_core
"""
import unittest
from unittest import mock

import psycopg2
from psycopg2.pool import PoolError

import judge_service_new as core
from schema_judge import normalize_expected


class ResultCompareTests(unittest.TestCase):
    """查询判题的结果集比较：忽略列顺序/行顺序，保留重复行。"""

    def test_column_and_row_order_are_ignored(self):
        actual = {'columns': ['b', 'a'], 'rows': [[2, 1], [4, 3]]}
        expected = {'columns': ['a', 'b'], 'rows': [[3, 4], [1, 2]]}
        self.assertTrue(core.compare_result_sets(actual, expected))

    def test_duplicate_rows_are_preserved(self):
        actual = {'columns': ['a'], 'rows': [[1], [1]]}
        expected = {'columns': ['a'], 'rows': [[1]]}
        self.assertFalse(core.compare_result_sets(actual, expected))

    def test_column_set_must_match(self):
        actual = {'columns': ['a', 'b'], 'rows': []}
        expected = {'columns': ['a', 'c'], 'rows': []}
        self.assertFalse(core.compare_result_sets(actual, expected))

    def test_none_is_compared_as_empty_string(self):
        actual = {'columns': ['a'], 'rows': [[None]]}
        expected = {'columns': ['a'], 'rows': [['']]}
        self.assertTrue(core.compare_result_sets(actual, expected))

    def test_both_empty_result_sets_match(self):
        self.assertTrue(core.compare_result_sets({}, {}))


class OutputFormatTests(unittest.TestCase):
    def test_parse_output_string(self):
        parsed = core.parse_output_string('name|age\nAlice|20\nBob|30')
        self.assertEqual(parsed['columns'], ['name', 'age'])
        self.assertEqual(parsed['rows'], [['Alice', '20'], ['Bob', '30']])

    def test_parse_empty_output(self):
        self.assertEqual(core.parse_output_string(''), {'columns': [], 'rows': []})
        self.assertEqual(core.parse_output_string('   '), {'columns': [], 'rows': []})

    def test_format_result_set(self):
        self.assertEqual(
            core.format_result_set({'columns': ['a', 'b'], 'rows': [[1, 2]]}),
            'a|b\n1|2',
        )
        self.assertEqual(core.format_result_set({'columns': [], 'rows': []}), '')

    def test_split_statements_trims_and_drops_empty(self):
        self.assertEqual(
            core._split_statements('SELECT 1; ; SELECT 2 ;'),
            ['SELECT 1', 'SELECT 2'],
        )
        self.assertEqual(core._split_statements(None), [])

    def test_friendly_sql_error_includes_sqlstate(self):
        # psycopg2 异常只有在数据库抛出时才带 pgcode，这里手工构造一个带 SQLSTATE 的
        class UndefinedTable(psycopg2.errors.UndefinedTable):
            pgcode = '42P01'

        error = UndefinedTable('relation "t" does not exist')
        message = core._friendly_sql_error(error)
        self.assertIn('42P01', message)
        self.assertIn('does not exist', message)


class DbTargetTests(unittest.TestCase):
    def test_parse_multiple_targets_with_default_port(self):
        self.assertEqual(
            core._parse_db_targets('judge-db:15432, judge-db-2 ,,', 5432),
            [('judge-db', 15432), ('judge-db-2', 5432)],
        )

    def test_parse_empty_falls_back_to_single_host(self):
        targets = core._parse_db_targets('', 5432)
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0], (core.DB_HOST, core.DB_PORT))


class FakePool:
    def __init__(self, connections):
        self._connections = list(connections)
        self.returned = []
        self.closed = False

    def getconn(self):
        if not self._connections:
            raise PoolError('busy')
        return self._connections.pop()

    def putconn(self, conn, close=False):
        self.returned.append((conn, close))

    def closeall(self):
        self.closed = True


class MultiDbPoolTests(unittest.TestCase):
    """多判题库分片：轮询取连接，归还到原属池。"""

    def test_round_robin_across_pools(self):
        conn_a1, conn_b1 = object(), object()
        first, second = FakePool([conn_a1]), FakePool([conn_b1])
        pool = core.MultiDbPool([first, second])

        conn_a = pool.getconn()
        conn_b = pool.getconn()

        self.assertEqual({id(conn_a), id(conn_b)}, {id(conn_a1), id(conn_b1)})
        pool.putconn(conn_a)
        pool.putconn(conn_b)
        self.assertEqual(len(first.returned) + len(second.returned), 2)
        for conn, close in first.returned + second.returned:
            self.assertFalse(close)

    def test_falls_back_to_next_pool_when_busy(self):
        first, second = FakePool([]), FakePool(['b1'])
        pool = core.MultiDbPool([first, second])
        conn = pool.getconn()
        pool.putconn(conn)
        self.assertEqual(second.returned, [(conn, False)])

    def test_all_pools_busy_raises(self):
        pool = core.MultiDbPool([FakePool([]), FakePool([])])
        with self.assertRaises(PoolError):
            pool.getconn()

    def test_unknown_connection_is_closed(self):
        pool = core.MultiDbPool([FakePool(['a1'])])
        stray = mock.Mock()
        pool.putconn(stray)
        stray.close.assert_called_once()

    def test_closeall_delegates(self):
        first, second = FakePool(['a1']), FakePool(['b1'])
        core.MultiDbPool([first, second]).closeall()
        self.assertTrue(first.closed and second.closed)


class NormalizeExpectedTests(unittest.TestCase):
    """旧版期望快照（数组形式）要能升级成新格式。"""

    def test_legacy_shapes_are_normalized(self):
        legacy = {
            'tables': {
                't': {
                    'columns': [],
                    'primary_key': ['id'],
                    'unique': [['email']],
                    'checks': ['age >= 0'],
                    'foreign_keys': [{
                        'columns': ['p_id'],
                        'references': {'table': 'p', 'columns': ['id']},
                        'on_delete': 'cascade',
                        'on_update': 'no action',
                    }],
                },
            },
        }
        normalized = normalize_expected(legacy)['tables']['t']
        self.assertEqual(normalized['primary_key'], {'name': None, 'columns': ['id']})
        self.assertEqual(normalized['unique'], [{'name': None, 'columns': ['email']}])
        self.assertEqual(
            normalized['checks'], [{'name': None, 'expression': 'age >= 0'}]
        )
        self.assertIsNone(normalized['foreign_keys'][0]['name'])
        self.assertEqual(normalized['indexes'], [])


if __name__ == '__main__':
    unittest.main()
