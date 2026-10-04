"""CREATE TABLE 结构判题的回归测试：一组表结构题（结构 diff + 行为探针）。

需要连到判题库（judge-db）。每个用例都在临时 schema 中执行并回滚，
不会留下任何数据。运行：

    docker compose exec -T judge-service python -m unittest -v test_schema_judge
"""
import os
import unittest
from uuid import uuid4

import psycopg2
from psycopg2 import sql

from schema_judge import (
    diff_schema,
    introspect_schema,
    normalize_check,
    normalize_default,
    run_probes,
    suggest_probes,
)

REFERENCE_DDL = """
CREATE TABLE students (
    id SERIAL PRIMARY KEY,
    email VARCHAR(50) NOT NULL UNIQUE,
    age INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT age_non_negative CHECK (age >= 0)
);
"""


def _connect():
    return psycopg2.connect(
        host=os.environ.get('JUDGE_DB_HOST', '127.0.0.1'),
        port=int(os.environ.get('JUDGE_DB_PORT', '5432')),
        dbname=os.environ.get('JUDGE_DB_NAME', 'judge_db'),
        user=os.environ.get('JUDGE_DB_USER', 'judge_user'),
        password=os.environ.get('JUDGE_DB_PASSWORD', 'judge_pass'),
        connect_timeout=5,
    )


def _statements(sql_text):
    return [stmt.strip() for stmt in (sql_text or '').split(';') if stmt.strip()]


def _snapshot(sql_text):
    """在临时 schema 中执行 DDL 并返回结构快照（执行后回滚，不留下数据）。"""
    conn = _connect()
    schema_name = f"t_{uuid4().hex[:10]}"
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema_name)))
            cur.execute(
                sql.SQL('SET LOCAL search_path = {}').format(sql.Identifier(schema_name))
            )
            for statement in _statements(sql_text):
                cur.execute(statement)
            snapshot = introspect_schema(cur, schema_name)
        return snapshot
    finally:
        conn.rollback()
        conn.close()


def _judge(submitted_sql, expected_schema, probes=None):
    """在临时 schema 中判一次 CREATE TABLE，返回逐项检查结果。"""
    conn = _connect()
    schema_name = f"t_{uuid4().hex[:10]}"
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema_name)))
            cur.execute(
                sql.SQL('SET LOCAL search_path = {}').format(sql.Identifier(schema_name))
            )
            for statement in _statements(submitted_sql):
                cur.execute(statement)
            actual = introspect_schema(cur, schema_name)
            checks = diff_schema(expected_schema, actual)
            if probes:
                checks.extend(run_probes(cur, probes))
        return checks
    finally:
        conn.rollback()
        conn.close()


def _suggest(sql_text):
    """在临时 schema 中执行参考 DDL 并返回自动生成/验证过的探针。"""
    conn = _connect()
    schema_name = f"t_{uuid4().hex[:10]}"
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema_name)))
            cur.execute(
                sql.SQL('SET LOCAL search_path = {}').format(sql.Identifier(schema_name))
            )
            for statement in _statements(sql_text):
                cur.execute(statement)
            snapshot = introspect_schema(cur, schema_name)
            return suggest_probes(cur, snapshot)
    finally:
        conn.rollback()
        conn.close()


def _failed_names(checks):
    return {check['name'] for check in checks if not check['passed']}


class NormalizationTests(unittest.TestCase):
    def test_serial_default_normalizes_to_serial(self):
        self.assertEqual(
            normalize_default("nextval('students_id_seq'::regclass)"), 'serial'
        )

    def test_check_definition_strips_keyword_and_parens(self):
        self.assertEqual(normalize_check('CHECK ((age >= 0))'), 'age >= 0')

    def test_check_conditions_are_canonicalized(self):
        self.assertEqual(
            normalize_check('CHECK (0 <= age)'),
            normalize_check('CHECK (age >= 0)'),
        )
        self.assertEqual(
            normalize_check('CHECK (price >= 0 AND price <= 100)'),
            normalize_check('CHECK (price <= 100 AND price >= 0)'),
        )
        self.assertEqual(
            normalize_check('CHECK (score BETWEEN 1 AND 5)'),
            normalize_check('CHECK (score >= 1 AND score <= 5)'),
        )
        self.assertNotEqual(
            normalize_check('CHECK (age > 0)'),
            normalize_check('CHECK (age >= 0)'),
        )


class CreateTableRegressionTests(unittest.TestCase):
    """一组表结构题：正确答案通过、各类错误结构被准确指出。"""

    @classmethod
    def setUpClass(cls):
        try:
            cls.expected = _snapshot(REFERENCE_DDL)
        except psycopg2.Error as exc:  # pragma: no cover - 仅环境不可用时触发
            raise unittest.SkipTest(f'judge-db 不可用: {exc}')

    def test_reference_answer_passes(self):
        checks = _judge(REFERENCE_DDL, self.expected)
        self.assertTrue(all(check['passed'] for check in checks), checks)

    def test_equivalent_type_spelling_passes(self):
        submitted = """
        CREATE TABLE students (
            id SERIAL PRIMARY KEY,
            email character varying(50) NOT NULL UNIQUE,
            age integer NOT NULL DEFAULT 0,
            CONSTRAINT age_non_negative CHECK (age >= 0)
        );
        """
        checks = _judge(submitted, self.expected)
        self.assertTrue(all(check['passed'] for check in checks), checks)

    def test_extra_column_is_allowed_in_mvp(self):
        submitted = """
        CREATE TABLE students (
            id SERIAL PRIMARY KEY,
            email VARCHAR(50) NOT NULL UNIQUE,
            age INTEGER NOT NULL DEFAULT 0,
            nickname TEXT,
            CONSTRAINT age_non_negative CHECK (age >= 0)
        );
        """
        checks = _judge(submitted, self.expected)
        self.assertTrue(all(check['passed'] for check in checks), checks)

    def test_missing_column_is_reported(self):
        submitted = """
        CREATE TABLE students (
            id SERIAL PRIMARY KEY,
            email VARCHAR(50) NOT NULL UNIQUE
        );
        """
        failed = _failed_names(_judge(submitted, self.expected))
        self.assertIn('字段 students.age', failed)

    def test_wrong_type_is_reported(self):
        submitted = """
        CREATE TABLE students (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            age INTEGER NOT NULL DEFAULT 0,
            CONSTRAINT age_non_negative CHECK (age >= 0)
        );
        """
        failed = _failed_names(_judge(submitted, self.expected))
        self.assertIn('字段 students.email 类型', failed)

    def test_missing_not_null_is_reported(self):
        submitted = """
        CREATE TABLE students (
            id SERIAL PRIMARY KEY,
            email VARCHAR(50) NOT NULL UNIQUE,
            age INTEGER DEFAULT 0,
            CONSTRAINT age_non_negative CHECK (age >= 0)
        );
        """
        failed = _failed_names(_judge(submitted, self.expected))
        self.assertIn('字段 students.age 非空', failed)

    def test_missing_primary_key_is_reported(self):
        submitted = """
        CREATE TABLE students (
            id INTEGER,
            email VARCHAR(50) NOT NULL UNIQUE,
            age INTEGER NOT NULL DEFAULT 0,
            CONSTRAINT age_non_negative CHECK (age >= 0)
        );
        """
        failed = _failed_names(_judge(submitted, self.expected))
        self.assertIn('表 students 主键', failed)

    def test_missing_unique_is_reported(self):
        submitted = """
        CREATE TABLE students (
            id SERIAL PRIMARY KEY,
            email VARCHAR(50) NOT NULL,
            age INTEGER NOT NULL DEFAULT 0,
            CONSTRAINT age_non_negative CHECK (age >= 0)
        );
        """
        failed = _failed_names(_judge(submitted, self.expected))
        self.assertIn('表 students 唯一约束 (email)', failed)

    def test_wrong_check_is_reported(self):
        submitted = """
        CREATE TABLE students (
            id SERIAL PRIMARY KEY,
            email VARCHAR(50) NOT NULL UNIQUE,
            age INTEGER NOT NULL DEFAULT 0,
            CONSTRAINT age_non_negative CHECK (age > 0)
        );
        """
        failed = _failed_names(_judge(submitted, self.expected))
        self.assertIn('表 students CHECK (age >= 0)', failed)

    def test_different_column_order_passes(self):
        submitted = """
        CREATE TABLE students (
            age INTEGER NOT NULL DEFAULT 0,
            email VARCHAR(50) NOT NULL UNIQUE,
            id SERIAL PRIMARY KEY,
            CONSTRAINT age_non_negative CHECK (age >= 0)
        );
        """
        checks = _judge(submitted, self.expected)
        self.assertTrue(all(check['passed'] for check in checks), checks)


class ProbeRegressionTests(unittest.TestCase):
    """行为探针：唯一 / 非空 / CHECK 是否真的生效。"""

    @classmethod
    def setUpClass(cls):
        try:
            cls.expected = _snapshot(REFERENCE_DDL)
        except psycopg2.Error as exc:  # pragma: no cover
            raise unittest.SkipTest(f'judge-db 不可用: {exc}')

    PROBES = [
        {'sql': "INSERT INTO students (email) VALUES ('a@a.com')", 'expect': 'ok',
         'description': '插入合法行'},
        {'sql': (
            "INSERT INTO students (email) VALUES ('dup@a.com');"
            "INSERT INTO students (email) VALUES ('dup@a.com')"
         ), 'expect': 'error',
         'error_code': '23505', 'description': '唯一约束拒绝重复邮箱'},
        {'sql': "INSERT INTO students (email, age) VALUES ('b@b.com', NULL)",
         'expect': 'error', 'error_code': '23502', 'description': '非空约束拒绝 NULL'},
        {'sql': "INSERT INTO students (email, age) VALUES ('c@c.com', -1)",
         'expect': 'error', 'error_code': '23514', 'description': 'CHECK 拒绝负数年龄'},
    ]

    def test_probes_pass_on_correct_answer(self):
        checks = _judge(REFERENCE_DDL, self.expected, probes=self.PROBES)
        probe_checks = [c for c in checks if c['name'] in {
            '插入合法行', '唯一约束拒绝重复邮箱', '非空约束拒绝 NULL', 'CHECK 拒绝负数年龄',
        }]
        self.assertEqual(len(probe_checks), 4)
        self.assertTrue(all(c['passed'] for c in probe_checks), probe_checks)

    def test_unique_probe_catches_missing_constraint(self):
        without_unique = """
        CREATE TABLE students (
            id SERIAL PRIMARY KEY,
            email VARCHAR(50) NOT NULL,
            age INTEGER NOT NULL DEFAULT 0,
            CONSTRAINT age_non_negative CHECK (age >= 0)
        );
        """
        checks = _judge(
            without_unique, self.expected,
            probes=[self.PROBES[1]],
        )
        self.assertTrue(
            any(
                c['name'] == '唯一约束拒绝重复邮箱' and not c['passed']
                for c in checks
            ),
            checks,
        )

    def test_probe_expecting_error_fails_when_statement_succeeds(self):
        checks = _judge(
            REFERENCE_DDL, self.expected,
            probes=[{
                'sql': "INSERT INTO students (email, age) VALUES ('ok@ok.com', 1)",
                'expect': 'error', 'error_code': '23505',
                'description': '故意配错的探针',
            }],
        )
        self.assertEqual(_failed_names(checks), {'故意配错的探针'})

    def test_probe_expecting_ok_fails_when_statement_errors(self):
        checks = _judge(REFERENCE_DDL, self.expected, probes=[{
            'sql': "INSERT INTO students (email, age) VALUES ('x', -1)",
            'expect': 'ok', 'description': '预期成功但会违反 CHECK',
        }])
        self.assertIn('预期成功但会违反 CHECK', _failed_names(checks))

    def test_probe_error_code_mismatch_is_reported(self):
        checks = _judge(REFERENCE_DDL, self.expected, probes=[{
            'sql': "INSERT INTO students (email, age) VALUES ('x', -1)",
            'expect': 'error', 'error_code': '23505', 'description': '错误码不匹配',
        }])
        self.assertIn('错误码不匹配', _failed_names(checks))

    def test_empty_probe_is_skipped(self):
        checks = _judge(REFERENCE_DDL, self.expected, probes=[{'sql': '   '}])
        self.assertFalse(any(c['name'].startswith('探针') for c in checks))

    def test_legacy_expected_snapshot_still_judges(self):
        legacy = {'tables': {'students': {
            'columns': self.expected['tables']['students']['columns'],
            'primary_key': ['id'],
            'unique': [['email']],
            'checks': ['age >= 0'],
        }}}
        checks = _judge(REFERENCE_DDL, legacy)
        self.assertTrue(all(c['passed'] for c in checks), checks)

    def test_suggested_probes_are_generated_and_validated(self):
        probes = _suggest(REFERENCE_DDL)
        codes = {probe.get('error_code') for probe in probes}
        self.assertIn('23505', codes)  # 主键 / 唯一约束拒绝重复值
        self.assertIn('23502', codes)  # 非空列拒绝 NULL
        self.assertTrue(all(probe['sql'].strip() for probe in probes))
        self.assertTrue(all(probe.get('description') for probe in probes))


TABLE_DDL = """
CREATE TABLE t (
    id SERIAL PRIMARY KEY,
    email VARCHAR(100) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);
"""


class IndexJudgeTests(unittest.TestCase):
    """索引结构判题：唯一/复合/部分索引、严格度、名称比对。"""

    @classmethod
    def setUpClass(cls):
        try:
            cls.expected_unique = _snapshot(
                TABLE_DDL + 'CREATE UNIQUE INDEX uq_t_email ON t (email);'
            )
            cls.expected_plain = _snapshot(
                TABLE_DDL + 'CREATE INDEX idx_t_email ON t (email);'
            )
        except psycopg2.Error as exc:  # pragma: no cover
            raise unittest.SkipTest(f'judge-db 不可用: {exc}')

    def test_reference_index_passes(self):
        actual = _snapshot(TABLE_DDL + 'CREATE UNIQUE INDEX uq_t_email ON t (email);')
        checks = diff_schema(self.expected_unique, actual)
        self.assertTrue(all(c['passed'] for c in checks), checks)

    def test_missing_index_is_reported(self):
        actual = _snapshot(TABLE_DDL)
        failed = _failed_names(diff_schema(self.expected_unique, actual))
        self.assertIn('表 t 索引 (email)', failed)

    def test_missing_unique_flag_is_reported(self):
        actual = _snapshot(TABLE_DDL + 'CREATE INDEX uq_t_email ON t (email);')
        failed = _failed_names(diff_schema(self.expected_unique, actual))
        self.assertIn('表 t 索引 (email)', failed)

    def test_partial_index_predicate_is_compared(self):
        expected = _snapshot(
            TABLE_DDL + 'CREATE UNIQUE INDEX uq_active ON t (email) WHERE active;'
        )
        actual = _snapshot(TABLE_DDL + 'CREATE UNIQUE INDEX uq_active ON t (email);')
        failed = _failed_names(diff_schema(expected, actual))
        self.assertIn('表 t 索引 (email)', failed)

    def test_name_is_ignored_by_default_and_checked_on_demand(self):
        actual = _snapshot(TABLE_DDL + 'CREATE INDEX idx_renamed ON t (email);')
        self.assertTrue(all(c['passed'] for c in diff_schema(self.expected_plain, actual)))
        failed = _failed_names(
            diff_schema(self.expected_plain, actual, compare_names=True)
        )
        self.assertIn('表 t 索引 (email)', failed)

    def test_unique_constraint_satisfies_unique_index_in_subset_mode(self):
        # 「建唯一索引」也可以用它等价的 UNIQUE 约束完成（多解）
        actual = _snapshot(
            TABLE_DDL + 'ALTER TABLE t ADD CONSTRAINT uq_t_email UNIQUE (email);'
        )
        checks = diff_schema(self.expected_unique, actual)
        self.assertTrue(all(c['passed'] for c in checks), checks)

    def test_expression_index_is_compared(self):
        expected = _snapshot(
            TABLE_DDL + 'CREATE UNIQUE INDEX uq_lower ON t (lower(email));'
        )
        same = _snapshot(TABLE_DDL + 'CREATE UNIQUE INDEX uq_lower ON t (lower(email));')
        self.assertTrue(all(c['passed'] for c in diff_schema(expected, same)))

        different = _snapshot(TABLE_DDL + 'CREATE UNIQUE INDEX uq_lower ON t (email);')
        failed = _failed_names(diff_schema(expected, different))
        self.assertTrue(any('lower(' in name for name in failed), failed)

    def test_desc_and_nulls_order_is_compared(self):
        expected = _snapshot(
            TABLE_DDL + 'CREATE INDEX idx_order ON t (email DESC NULLS FIRST);'
        )
        same = _snapshot(
            TABLE_DDL + 'CREATE INDEX idx_order ON t (email DESC NULLS FIRST);'
        )
        self.assertTrue(all(c['passed'] for c in diff_schema(expected, same)))

        default_order = _snapshot(TABLE_DDL + 'CREATE INDEX idx_order ON t (email);')
        failed = _failed_names(diff_schema(expected, default_order))
        self.assertIn('表 t 索引 (email)', failed)


class StrictnessTests(unittest.TestCase):
    """subset（默认）允许额外对象；exact 要求对象集合完全一致。"""

    @classmethod
    def setUpClass(cls):
        try:
            cls.expected = _snapshot(
                TABLE_DDL + 'CREATE INDEX idx_t_email ON t (email);'
            )
        except psycopg2.Error as exc:  # pragma: no cover
            raise unittest.SkipTest(f'judge-db 不可用: {exc}')

    def test_extra_index_allowed_in_subset(self):
        actual = _snapshot(
            TABLE_DDL
            + 'CREATE INDEX idx_t_email ON t (email);'
            + 'CREATE INDEX idx_t_active ON t (active);'
        )
        checks = diff_schema(self.expected, actual, strictness='subset')
        self.assertTrue(all(c['passed'] for c in checks), checks)

    def test_extra_index_rejected_in_exact(self):
        actual = _snapshot(
            TABLE_DDL
            + 'CREATE INDEX idx_t_email ON t (email);'
            + 'CREATE INDEX idx_t_active ON t (active);'
        )
        failed = _failed_names(diff_schema(self.expected, actual, strictness='exact'))
        self.assertIn('表 t 索引 (active)', failed)

    def test_extra_column_rejected_in_exact(self):
        actual = _snapshot(
            TABLE_DDL.replace(
                'active BOOLEAN NOT NULL DEFAULT TRUE',
                'active BOOLEAN NOT NULL DEFAULT TRUE, nickname TEXT',
            )
            + 'CREATE INDEX idx_t_email ON t (email);'
        )
        failed = _failed_names(diff_schema(self.expected, actual, strictness='exact'))
        self.assertIn('字段 t.nickname', failed)


FK_DDL = """
CREATE TABLE parents (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL
);
CREATE TABLE children (
    id SERIAL PRIMARY KEY,
    parent_id INTEGER NOT NULL REFERENCES parents(id) ON DELETE CASCADE
);
"""


class ForeignKeyProbeTests(unittest.TestCase):
    """外键自动探针：孤儿数据与删除父行的动作。"""

    def test_cascade_probes_include_orphan_and_successful_delete(self):
        probes = _suggest(FK_DDL)
        codes = {probe.get('error_code') for probe in probes}
        self.assertIn('23503', codes)  # 孤儿数据被拒绝
        delete_probes = [p for p in probes if '删除' in p['description']]
        self.assertTrue(delete_probes, probes)
        # CASCADE：删除父行应当成功
        self.assertEqual(delete_probes[0]['expect'], 'ok')

    def test_restrict_delete_probe_expects_error(self):
        probes = _suggest(FK_DDL.replace('ON DELETE CASCADE', 'ON DELETE RESTRICT'))
        delete_probes = [p for p in probes if '删除' in p['description']]
        self.assertTrue(delete_probes, probes)
        self.assertEqual(delete_probes[0]['expect'], 'error')
        self.assertEqual(delete_probes[0]['error_code'], '23503')

    def test_set_null_probe_on_not_null_column_expects_error(self):
        probes = _suggest(FK_DDL.replace('ON DELETE CASCADE', 'ON DELETE SET NULL'))
        delete_probes = [p for p in probes if '删除' in p['description']]
        self.assertTrue(delete_probes, probes)
        # 子表外键列是 NOT NULL，SET NULL 会触发非空违约
        self.assertEqual(delete_probes[0]['expect'], 'error')
        self.assertEqual(delete_probes[0]['error_code'], '23502')
