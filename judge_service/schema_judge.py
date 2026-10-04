"""DDL 结构判题：schema 快照 + 语义 diff + 行为探针 + 探针自动生成。

查询判题是「执行 SQL 比较结果集」；DDL 没有结果集，正确性体现在**最终 schema
状态**与**约束是否真的生效**上。这里分三步：

1. introspection：把临时 schema 里的表/列/主键/唯一/CHECK/外键/索引读成规范化快照；
2. diff：与期望快照做语义比较，支持两档严格度与「是否比对对象名称」；
3. probes：行为探针（可自动生成并验证）确认约束真的起作用。

所有对象都在判题服务为每个用例创建的临时 schema 中，事务回滚即销毁。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

import psycopg2

# pg_constraint.confdeltype / confupdtype 编码 -> 可读动作
_FK_ACTIONS = {
    'a': 'no action',
    'r': 'restrict',
    'c': 'cascade',
    'n': 'set null',
    'd': 'set default',
}

_TABLES_SQL = """
SELECT c.relname
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = %s AND c.relkind IN ('r', 'p')
 ORDER BY c.relname
"""

_COLUMNS_SQL = """
SELECT c.relname,
       a.attname,
       pg_catalog.format_type(a.atttypid, a.atttypmod),
       a.attnotnull,
       pg_catalog.pg_get_expr(ad.adbin, ad.adrelid)
  FROM pg_attribute a
  JOIN pg_class c ON c.oid = a.attrelid
  JOIN pg_namespace n ON n.oid = c.relnamespace
  LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
 WHERE n.nspname = %s AND c.relkind IN ('r', 'p')
   AND a.attnum > 0 AND NOT a.attisdropped
 ORDER BY c.relname, a.attnum
"""

_CONSTRAINTS_SQL = """
SELECT c.relname,
       con.contype,
       con.conname,
       COALESCE((
           SELECT array_agg(a.attname ORDER BY k.ord)
             FROM unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord)
             JOIN pg_attribute a
               ON a.attrelid = con.conrelid AND a.attnum = k.attnum
       ), '{}'),
       pg_catalog.pg_get_constraintdef(con.oid)
  FROM pg_constraint con
  JOIN pg_class c ON c.oid = con.conrelid
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = %s AND con.contype IN ('p', 'u', 'c')
 ORDER BY c.relname, con.contype, con.conname
"""

_FOREIGN_KEYS_SQL = """
SELECT c.relname,
       con.conname,
       rc.relname,
       (SELECT array_agg(a.attname ORDER BY k.ord)
          FROM unnest(con.conkey) WITH ORDINALITY AS k(attnum, ord)
          JOIN pg_attribute a
            ON a.attrelid = con.conrelid AND a.attnum = k.attnum),
       (SELECT array_agg(a.attname ORDER BY k.ord)
          FROM unnest(con.confkey) WITH ORDINALITY AS k(attnum, ord)
          JOIN pg_attribute a
            ON a.attrelid = con.confrelid AND a.attnum = k.attnum),
       con.confdeltype,
       con.confupdtype
  FROM pg_constraint con
  JOIN pg_class c ON c.oid = con.conrelid
  JOIN pg_class rc ON rc.oid = con.confrelid
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = %s AND con.contype = 'f'
 ORDER BY c.relname, con.conname
"""

_INDEXES_SQL = """
SELECT c.relname,
       ic.relname,
       i.indisunique,
       am.amname,
       pg_catalog.pg_get_expr(i.indpred, i.indrelid),
       (SELECT array_agg(pg_catalog.pg_get_indexdef(i.indexrelid, k, true) ORDER BY k)
          FROM generate_series(1, i.indnkeyatts) AS k),
       (SELECT array_agg(a.attname ORDER BY k.ord)
          FROM unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord)
          JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
         WHERE k.ord > i.indnkeyatts),
       (SELECT array_agg((k.opt & 1) ORDER BY k.ord)
          FROM unnest(i.indoption) WITH ORDINALITY AS k(opt, ord)),
       (SELECT array_agg((k.opt & 2) ORDER BY k.ord)
          FROM unnest(i.indoption) WITH ORDINALITY AS k(opt, ord)),
       (i.indisprimary OR EXISTS (
           SELECT 1 FROM pg_constraint con WHERE con.conindid = i.indexrelid
       ))
  FROM pg_index i
  JOIN pg_class ic ON ic.oid = i.indexrelid
  JOIN pg_class c ON c.oid = i.indrelid
  JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_am am ON am.oid = ic.relam
 WHERE n.nspname = %s AND c.relkind IN ('r', 'p')
 ORDER BY c.relname, ic.relname
"""


# --------------------------------------------------------------------------- #
# 规范化：期望与实际走同一套规则
# --------------------------------------------------------------------------- #
def _collapse(text: Optional[str]) -> str:
    return re.sub(r'\s+', ' ', (text or '').strip()).lower()


def normalize_type(data_type: Optional[str]) -> str:
    """``format_type`` 的输出已基本规范（integer / character varying(50)）。"""
    return _collapse(data_type)


def normalize_default(default_expr: Optional[str]) -> Optional[str]:
    """默认值规范化：serial 的 nextval(...) 统一成 ``serial``。"""
    if default_expr is None:
        return None
    text = _collapse(default_expr)
    if text.startswith('nextval('):
        return 'serial'
    return text.replace('current_timestamp', 'now()')


def normalize_check(definition: Optional[str]) -> str:
    """CHECK 约束定义规范化（含语义等价的粗粒度归一）。

    PostgreSQL 会把 BETWEEN 等语法展开成 ``>= AND <=``，这里再做一层：
    按 AND 拆分并排序各子条件、把「常量 关系运算符 列」翻转为「列 关系运算符 常量」。
    因此 ``age >= 0`` 与 ``0 <= age``、以及交换 AND 顺序的写法都能匹配。
    更复杂的逻辑等价（如 ``NOT (x < 0)``）不在此处理，交给行为探针兜底。
    """
    text = _collapse(definition)
    if text.startswith('check '):
        text = text[len('check '):].strip()
    return _canonical_condition(_strip_outer_parens(text))


def _canonical_condition(text: str) -> str:
    text = _expand_between(text)
    parts = [_canonical_atom(part) for part in _split_top_level_and(text)]
    return ' and '.join(sorted(part for part in parts if part))


_BETWEEN_RE = re.compile(r'(\S+)\s+between\s+(\S+)\s+and\s+(\S+)')


def _expand_between(text: str) -> str:
    """把 ``x between a and b`` 展开成 `x >= a and x <= b`（NOT BETWEEN 不处理）。

    必须放在按 AND 拆分之前，否则 BETWEEN 内部的 AND 会被误当成条件分隔符。
    """
    def replace(match: 're.Match') -> str:
        left, low, high = match.group(1), match.group(2), match.group(3)
        if left.lower() == 'not':
            return match.group(0)
        return f'{left} >= {low} and {left} <= {high}'

    return _BETWEEN_RE.sub(replace, text)


def _split_top_level_and(text: str) -> List[str]:
    """按顶层 AND 拆分（忽略括号内的 AND）。"""
    parts: List[str] = []
    depth = 0
    current: List[str] = []
    for token in re.split(r'(\s+and\s+)', text):
        if token.strip().lower() == 'and' and depth == 0:
            parts.append(''.join(current).strip())
            current = []
            continue
        depth += token.count('(') - token.count(')')
        current.append(token)
    parts.append(''.join(current).strip())
    return [part for part in parts if part]


def _canonical_atom(text: str) -> str:
    """把单个比较条件规范化：翻转「常量 比较符 列」并统一 ``!=``/``<>``。"""
    text = _strip_outer_parens(_collapse(text))
    match = re.match(r'^(.+?)\s*(<=|>=|<>|!=|=|<|>)\s*(.+)$', text)
    if not match:
        return text
    left = match.group(1).strip()
    operator = match.group(2)
    right = match.group(3).strip()
    if operator == '!=':
        operator = '<>'
    if _looks_literal(left) and not _looks_literal(right):
        left, right = right, left
        operator = {
            '<': '>', '<=': '>=', '>': '<', '>=': '<=', '=': '=', '<>': '<>',
        }[operator]
    return f'{left} {operator} {right}'


def _looks_literal(text: str) -> bool:
    return bool(
        re.match(r'^-?\d+(\.\d+)?$', text)
        or re.match(r"^'[^']*'$", text)
        or text in ('true', 'false', 'null')
    )


def _normalize_predicate(predicate: Optional[str]) -> Optional[str]:
    """部分索引的 WHERE 条件规范化（None 表示非部分索引）。"""
    if predicate is None:
        return None
    return _strip_outer_parens(_collapse(predicate))


def _strip_outer_parens(text: str) -> str:
    while text.startswith('(') and text.endswith(')') and _parens_balanced(text[1:-1]):
        text = text[1:-1].strip()
    return text


def _parens_balanced(text: str) -> bool:
    depth = 0
    for char in text:
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _qi(name: str) -> str:
    """PostgreSQL 标识符加引号。"""
    return '"' + str(name).replace('"', '""') + '"'


# --------------------------------------------------------------------------- #
# introspection
# --------------------------------------------------------------------------- #
def introspect_schema(cur, schema_name: str) -> Dict[str, Any]:
    """读取指定 schema 的规范化结构快照（只包含该 schema 内的表）。"""
    snapshot: Dict[str, Any] = {'tables': {}}

    cur.execute(_TABLES_SQL, (schema_name,))
    for (table_name,) in cur.fetchall():
        snapshot['tables'][table_name] = {
            'columns': [],
            'primary_key': {'name': None, 'columns': []},
            'unique': [],
            'checks': [],
            'foreign_keys': [],
            'indexes': [],
        }

    cur.execute(_COLUMNS_SQL, (schema_name,))
    for table_name, name, data_type, not_null, default_expr in cur.fetchall():
        entry = snapshot['tables'].get(table_name)
        if entry is None:
            continue
        entry['columns'].append({
            'name': name,
            'type': normalize_type(data_type),
            'not_null': bool(not_null),
            'default': normalize_default(default_expr),
        })

    cur.execute(_CONSTRAINTS_SQL, (schema_name,))
    for table_name, contype, conname, columns, definition in cur.fetchall():
        entry = snapshot['tables'].get(table_name)
        if entry is None:
            continue
        columns = list(columns or [])
        if contype == 'p':
            entry['primary_key'] = {'name': conname, 'columns': columns}
        elif contype == 'u':
            entry['unique'].append({'name': conname, 'columns': columns})
        elif contype == 'c':
            entry['checks'].append({
                'name': conname, 'expression': normalize_check(definition),
            })

    cur.execute(_FOREIGN_KEYS_SQL, (schema_name,))
    for table, conname, ref_table, columns, ref_columns, on_delete, on_update in cur.fetchall():
        entry = snapshot['tables'].get(table)
        if entry is None:
            continue
        entry['foreign_keys'].append({
            'name': conname,
            'columns': list(columns or []),
            'references': {'table': ref_table, 'columns': list(ref_columns or [])},
            'on_delete': _FK_ACTIONS.get(on_delete, on_delete),
            'on_update': _FK_ACTIONS.get(on_update, on_update),
        })

    cur.execute(_INDEXES_SQL, (schema_name,))
    for (
        table, name, unique, method, predicate, key_defs, include_cols,
        desc_flags, nulls_first_flags, from_constraint,
    ) in cur.fetchall():
        entry = snapshot['tables'].get(table)
        if entry is None:
            continue
        entry['indexes'].append({
            'name': name,
            'columns': [_collapse(item) for item in (key_defs or [])],
            'unique': bool(unique),
            'method': method,
            'predicate': _normalize_predicate(predicate),
            'include': list(include_cols or []),
            'desc': [bool(flag) for flag in (desc_flags or [])],
            'nulls_first': [bool(flag) for flag in (nulls_first_flags or [])],
            'from_constraint': bool(from_constraint),
        })

    return snapshot


# --------------------------------------------------------------------------- #
# 期望快照兼容处理（旧格式 -> 新格式）
# --------------------------------------------------------------------------- #
def normalize_expected(expected: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """把历史/手写的期望快照补齐成新格式，保证老数据仍可判题。"""
    tables = dict((expected or {}).get('tables') or {})
    for table in tables.values():
        pk = table.get('primary_key')
        if isinstance(pk, list):
            table['primary_key'] = {'name': None, 'columns': pk}
        elif isinstance(pk, dict):
            pk.setdefault('name', None)
            pk.setdefault('columns', [])
        else:
            table['primary_key'] = {'name': None, 'columns': []}

        unique = []
        for item in table.get('unique') or []:
            if isinstance(item, dict):
                unique.append({'name': item.get('name'), 'columns': list(item.get('columns') or [])})
            else:
                unique.append({'name': None, 'columns': list(item)})
        table['unique'] = unique

        checks = []
        for item in table.get('checks') or []:
            if isinstance(item, dict):
                checks.append({
                    'name': item.get('name'),
                    'expression': item.get('expression') or '',
                })
            else:
                checks.append({'name': None, 'expression': item})
        table['checks'] = checks

        for fk in table.get('foreign_keys') or []:
            fk.setdefault('name', None)
        table.setdefault('foreign_keys', [])
        indexes = []
        for index in table.get('indexes') or []:
            index.setdefault('columns', [])
            index.setdefault('desc', [False] * len(index['columns']))
            index.setdefault('nulls_first', [False] * len(index['columns']))
            index.setdefault('include', [])
            index.setdefault('predicate', None)
            index.setdefault('method', 'btree')
            index.setdefault('unique', False)
            index.setdefault('name', None)
            indexes.append(index)
        table['indexes'] = indexes
        table.setdefault('columns', [])
    return {'tables': tables}


# --------------------------------------------------------------------------- #
# 语义 diff
# --------------------------------------------------------------------------- #
def _check(name: str, passed: bool, detail: str = '') -> Dict[str, Any]:
    return {'name': name, 'passed': passed, 'detail': '' if passed else detail}


def diff_schema(
    expected: Optional[Dict[str, Any]],
    actual: Optional[Dict[str, Any]],
    strictness: str = 'subset',
    compare_names: bool = False,
) -> List[Dict[str, Any]]:
    """期望快照与实际快照的语义比较，返回逐项检查结果。

    strictness：
    - ``subset``（默认/宽松）：期望里的对象必须存在且匹配，多出来的列/约束/索引不判错；
    - ``exact``（严格）：对象集合必须与期望完全一致，多出来的对象判错。

    compare_names：是否要求约束名 / 索引名与期望一致（默认忽略名称）。
    """
    expected = normalize_expected(expected)
    checks: List[Dict[str, Any]] = []
    expected_tables = expected.get('tables') or {}
    actual_tables = (actual or {}).get('tables') or {}

    if not expected_tables:
        return [_check('期望结构', False, '用例未配置期望结构')]

    exact = strictness == 'exact'
    for table_name, expected_table in expected_tables.items():
        actual_table = actual_tables.get(table_name)
        if actual_table is None:
            checks.append(_check(f'表 {table_name}', False, '缺少表'))
            continue
        checks.extend(_diff_columns(table_name, expected_table, actual_table, exact))
        checks.extend(_diff_primary_key(table_name, expected_table, actual_table, compare_names))
        checks.extend(_diff_unique(table_name, expected_table, actual_table, compare_names, exact))
        checks.extend(_diff_foreign_keys(table_name, expected_table, actual_table, compare_names, exact))
        checks.extend(_diff_checks(table_name, expected_table, actual_table, compare_names, exact))
        checks.extend(_diff_indexes(table_name, expected_table, actual_table, compare_names, exact))
    return checks


def _diff_columns(table_name, expected_table, actual_table, exact) -> List[Dict[str, Any]]:
    actual_columns = {col['name']: col for col in actual_table.get('columns', [])}
    expected_columns = {col['name']: col for col in expected_table.get('columns', [])}
    checks = []
    for name, expected_col in expected_columns.items():
        label = f'字段 {table_name}.{name}'
        actual_col = actual_columns.get(name)
        if actual_col is None:
            checks.append(_check(label, False, '缺失'))
            continue
        checks.append(_check(label, True))
        checks.append(_check(
            f'{label} 类型',
            actual_col['type'] == expected_col['type'],
            '类型不符',
        ))
        checks.append(_check(
            f'{label} 非空',
            bool(actual_col['not_null']) == bool(expected_col['not_null']),
            '非空约束不符',
        ))
        checks.append(_check(
            f'{label} 默认值',
            actual_col['default'] == expected_col['default'],
            '默认值不符',
        ))
    if exact:
        for name in actual_columns.keys() - expected_columns.keys():
            checks.append(_check(f'字段 {table_name}.{name}', False, '存在多余的字段'))
    return checks


def _diff_primary_key(table_name, expected_table, actual_table, compare_names) -> List[Dict[str, Any]]:
    expected = expected_table.get('primary_key') or {'name': None, 'columns': []}
    if not expected.get('columns'):
        return []
    actual = actual_table.get('primary_key') or {'name': None, 'columns': []}
    matched = (
        set(actual.get('columns') or []) == set(expected.get('columns') or [])
        and (
            not compare_names
            or not expected.get('name')
            or actual.get('name') == expected.get('name')
        )
    )
    return [_check(f'表 {table_name} 主键', matched, '主键不匹配')]


def _diff_unique(table_name, expected_table, actual_table, compare_names, exact) -> List[Dict[str, Any]]:
    actual = actual_table.get('unique') or []
    matched_actual: set[int] = set()
    checks = []
    for expected in expected_table.get('unique') or []:
        label = f'表 {table_name} 唯一约束 ({", ".join(expected["columns"])})'
        found = _match_named(
            expected, actual, matched_actual,
            key=lambda item: tuple(item.get('columns') or []),
            compare_names=compare_names,
        )
        if found is None:
            checks.append(_check(label, False, '唯一约束缺失'))
        else:
            matched_actual.add(found)
            checks.append(_check(label, True))
    if exact:
        for index, item in enumerate(actual):
            if index not in matched_actual:
                checks.append(_check(
                    f'表 {table_name} 唯一约束 ({", ".join(item.get("columns") or [])})',
                    False, '存在多余的唯一约束',
                ))
    return checks


def _diff_foreign_keys(table_name, expected_table, actual_table, compare_names, exact) -> List[Dict[str, Any]]:
    actual = actual_table.get('foreign_keys') or []
    matched_actual: set[int] = set()
    checks = []
    for expected in expected_table.get('foreign_keys') or []:
        label = f'表 {table_name} 外键 ({", ".join(expected["columns"])})'
        found = _match_named(
            expected, actual, matched_actual,
            key=_fk_key,
            compare_names=compare_names,
        )
        if found is None:
            checks.append(_check(label, False, '外键缺失或动作不符'))
        else:
            matched_actual.add(found)
            checks.append(_check(label, True))
    if exact:
        for index, item in enumerate(actual):
            if index not in matched_actual:
                checks.append(_check(
                    f'表 {table_name} 外键 ({", ".join(item.get("columns") or [])})',
                    False, '存在多余的外键',
                ))
    return checks


def _diff_checks(table_name, expected_table, actual_table, compare_names, exact) -> List[Dict[str, Any]]:
    actual = actual_table.get('checks') or []
    matched_actual: set[int] = set()
    checks = []
    for expected in expected_table.get('checks') or []:
        label = f'表 {table_name} CHECK ({expected["expression"]})'
        found = _match_named(
            expected, actual, matched_actual,
            key=lambda item: item.get('expression') or '',
            compare_names=compare_names,
        )
        if found is None:
            checks.append(_check(label, False, 'CHECK 约束缺失或不符'))
        else:
            matched_actual.add(found)
            checks.append(_check(label, True))
    if exact:
        for index, item in enumerate(actual):
            if index not in matched_actual:
                checks.append(_check(
                    f'表 {table_name} CHECK ({item.get("expression")})',
                    False, '存在多余的 CHECK 约束',
                ))
    return checks


def _index_key(index: Dict[str, Any]) -> tuple:
    columns = tuple(index.get('columns') or [])
    desc = index.get('desc') or []
    nulls_first = index.get('nulls_first') or []
    return (
        columns,
        bool(index.get('unique')),
        index.get('method') or 'btree',
        _normalize_predicate(index.get('predicate')) or '',
        tuple(index.get('include') or []),
        tuple(bool(desc[i]) if i < len(desc) else False for i in range(len(columns))),
        tuple(bool(nulls_first[i]) if i < len(nulls_first) else False for i in range(len(columns))),
    )


def _diff_indexes(table_name, expected_table, actual_table, compare_names, exact) -> List[Dict[str, Any]]:
    actual = actual_table.get('indexes') or []
    matched_actual: set[int] = set()
    checks = []
    for expected in expected_table.get('indexes') or []:
        columns = ', '.join(expected.get('columns') or [])
        label = f'表 {table_name} 索引 ({columns})'
        found = _match_named(
            expected, actual, matched_actual,
            key=_index_key,
            compare_names=compare_names,
        )
        if found is None:
            checks.append(_check(label, False, '索引缺失或定义不符'))
        else:
            matched_actual.add(found)
            checks.append(_check(label, True))
    if exact:
        for index, item in enumerate(actual):
            if index not in matched_actual:
                checks.append(_check(
                    f'表 {table_name} 索引 ({", ".join(item.get("columns") or [])})',
                    False, '存在多余的索引',
                ))
    return checks


def _fk_key(fk: Dict[str, Any]) -> tuple:
    return (
        tuple(fk.get('columns') or []),
        (fk.get('references') or {}).get('table'),
        tuple((fk.get('references') or {}).get('columns') or []),
        fk.get('on_delete'),
        fk.get('on_update'),
    )


def _match_named(expected, actual, matched, key, compare_names: bool) -> Optional[int]:
    """按 key 匹配期望对象；compare_names 为真时还要求名称一致。"""
    expected_key = key(expected)
    for index, item in enumerate(actual):
        if index in matched:
            continue
        if key(item) != expected_key:
            continue
        if compare_names and expected.get('name') and item.get('name') != expected.get('name'):
            continue
        return index
    return None


# --------------------------------------------------------------------------- #
# 行为探针
# --------------------------------------------------------------------------- #
def _probe_outcome(cur, sql_text: str) -> Optional[str]:
    """执行一条探针并返回 SQLSTATE（成功返回 None）；用 SAVEPOINT 隔离。"""
    cur.execute('SAVEPOINT judge_probe')
    try:
        cur.execute(sql_text)
        return None
    except psycopg2.Error as exc:
        return getattr(exc, 'pgcode', None)
    finally:
        cur.execute('ROLLBACK TO SAVEPOINT judge_probe')
        cur.execute('RELEASE SAVEPOINT judge_probe')


def run_probes(cur, probes: Optional[Sequence[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """执行行为探针：断言语句成功、或按错误码断言失败。

    每条探针用 SAVEPOINT 包裹——期望报错的探针会让事务进入 aborted 状态，
    必须回滚到保存点才能继续执行后续探针。因此探针之间互不影响；需要前置数据的
    探针（例如「插入重复值」）应在同一条探针里用分号写成多语句脚本。
    """
    checks: List[Dict[str, Any]] = []
    for index, probe in enumerate(probes or []):
        probe = probe or {}
        sql_text = str(probe.get('sql') or '').strip()
        if not sql_text:
            continue
        expect = str(probe.get('expect') or 'ok').lower()
        error_code = probe.get('error_code') or None
        label = str(probe.get('description') or f'探针 {index + 1}')

        actual_code = _probe_outcome(cur, sql_text)
        if expect == 'error':
            if actual_code is None:
                checks.append(_check(label, False, '预期报错，实际执行成功'))
            elif error_code and actual_code != error_code:
                checks.append(_check(label, False, f'错误码不符（实际 {actual_code}）'))
            else:
                checks.append(_check(label, True))
        else:
            checks.append(_check(
                label, actual_code is None, '预期成功，实际执行失败',
            ))
    return checks


# --------------------------------------------------------------------------- #
# 探针自动生成（基于参考结构生成候选，并在参考结构上验证后才保留）
# --------------------------------------------------------------------------- #
def _sample_value(data_type: str) -> Optional[str]:
    """按规范化类型给出一个可用的示例值；不支持的类型返回 None。"""
    text = data_type or ''
    if any(key in text for key in ('int', 'numeric', 'decimal', 'real', 'double', 'money')):
        return '1'
    if 'bool' in text:
        return 'true'
    if 'character' in text or 'text' in text or 'char' in text or text == 'name':
        return "'sample'"
    if 'timestamp' in text or 'time' in text:
        return 'now()'
    if text == 'date':
        return 'current_date'
    return None


def _required_values(table: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """给「非空且无默认值」的列准备示例值；有列拿不到示例值时返回 None。"""
    values: Dict[str, str] = {}
    for column in table.get('columns') or []:
        if not column.get('not_null') or column.get('default') is not None:
            continue
        sample = _sample_value(column.get('type') or '')
        if sample is None:
            return None
        values[column['name']] = sample
    return values


def _insert_sql(table_name: str, values: Dict[str, str]) -> str:
    columns = ', '.join(_qi(name) for name in values)
    literals = ', '.join(values.values())
    return f'INSERT INTO {_qi(table_name)} ({columns}) VALUES ({literals})'


def _build_probe_candidates(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    tables = snapshot.get('tables') or {}
    for table_name, table in tables.items():
        required = _required_values(table)
        if required is None:
            continue

        # 唯一性：主键 + UNIQUE 约束 → 重复插入应报 23505
        keys: List[tuple[str, List[str]]] = []
        primary = (table.get('primary_key') or {}).get('columns') or []
        if primary:
            keys.append(('主键', primary))
        for unique in table.get('unique') or []:
            keys.append(('唯一约束', list(unique.get('columns') or [])))
        for label, columns in keys:
            values = dict(required)
            usable = True
            for column in columns:
                if column in values:
                    continue
                sample = _sample_value(_column_type(table, column))
                if sample is None:
                    usable = False
                    break
                values[column] = sample
            if not usable or not values:
                continue
            statement = _insert_sql(table_name, values)
            candidates.append({
                'sql': f'{statement}; {statement}',
                'expect': 'error',
                'error_code': '23505',
                'description': (
                    f'{table_name} {label}({", ".join(columns)}) 拒绝重复值'
                ),
            })

        # 非空：非空且无默认值的列 → 插入 NULL 应报 23502
        for column in table.get('columns') or []:
            if not column.get('not_null') or column.get('default') is not None:
                continue
            values = dict(required)
            values[column['name']] = 'NULL'
            statement = _insert_sql(table_name, values)
            candidates.append({
                'sql': statement,
                'expect': 'error',
                'error_code': '23502',
                'description': f'{table_name}.{column["name"]} 拒绝 NULL',
            })

        # 外键：孤儿数据（23503）与删除父行时的动作（CASCADE / SET NULL / RESTRICT）
        for fk in table.get('foreign_keys') or []:
            references = fk.get('references') or {}
            parent_name = references.get('table')
            parent = tables.get(parent_name)
            fk_columns = list(fk.get('columns') or [])
            ref_columns = list(references.get('columns') or [])
            if parent is None or not fk_columns or len(fk_columns) != len(ref_columns):
                continue
            parent_required = _required_values(parent)
            child_required = _required_values(table)
            if parent_required is None or child_required is None:
                continue

            parent_values = dict(parent_required)
            if not _fill_columns(parent, ref_columns, parent_values):
                continue
            child_values = dict(child_required)
            for column, ref_column in zip(fk_columns, ref_columns):
                child_values[column] = parent_values[ref_column]

            orphan_values = dict(child_required)
            if _fill_columns_with_sentinel(table, fk_columns, orphan_values):
                candidates.append({
                    'sql': _insert_sql(table_name, orphan_values),
                    'expect': 'error',
                    'error_code': '23503',
                    'description': (
                        f'{table_name}({", ".join(fk_columns)}) '
                        f'外键必须指向已存在的 {parent_name}'
                    ),
                })

            parent_insert = _insert_sql(parent_name, parent_values)
            child_insert = _insert_sql(table_name, child_values)
            where = ' AND '.join(
                f'{_qi(ref_column)} = {parent_values[ref_column]}'
                for column, ref_column in zip(fk_columns, ref_columns)
            )
            action = str(fk.get('on_delete') or 'no action').lower()
            if action in ('restrict', 'no action'):
                expect, error_code = 'error', '23503'
            elif action == 'set null' and not all(
                _column_not_null(table, column) for column in fk_columns
            ):
                expect, error_code = 'ok', None
            elif action == 'set null':
                expect, error_code = 'error', '23502'
            else:
                expect, error_code = 'ok', None
            probe: Dict[str, Any] = {
                'sql': (
                    f'{parent_insert}; {child_insert}; '
                    f'DELETE FROM {_qi(parent_name)} WHERE {where}'
                ),
                'expect': expect,
                'description': f'删除 {parent_name} 时的外键动作（{action}）',
            }
            if error_code:
                probe['error_code'] = error_code
            candidates.append(probe)
    return candidates


def _column_type(table: Dict[str, Any], column_name: str) -> str:
    for column in table.get('columns') or []:
        if column['name'] == column_name:
            return column.get('type') or ''
    return ''


def _column_not_null(table: Dict[str, Any], column_name: str) -> bool:
    for column in table.get('columns') or []:
        if column['name'] == column_name:
            return bool(column.get('not_null'))
    return False


def _fill_columns(table: Dict[str, Any], columns: List[str], values: Dict[str, str]) -> bool:
    """给指定列补示例值；有列拿不到示例值时返回 False。"""
    for column in columns:
        if column in values:
            continue
        sample = _sample_value(_column_type(table, column))
        if sample is None:
            return False
        values[column] = sample
    return True


def _fill_columns_with_sentinel(
    table: Dict[str, Any], columns: List[str], values: Dict[str, str]
) -> bool:
    """给外键列填一个"肯定不存在"的哨兵值；类型不支持时返回 False。"""
    for column in columns:
        sentinel = _sentinel_value(_column_type(table, column))
        if sentinel is None:
            return False
        values[column] = sentinel
    return True


def _sentinel_value(data_type: str) -> Optional[str]:
    text = data_type or ''
    if any(key in text for key in ('int', 'numeric', 'decimal', 'real', 'double', 'money')):
        return '999999999'
    if 'character' in text or 'text' in text or 'char' in text or text == 'name':
        return "'__missing_parent__'"
    return None


def suggest_probes(cur, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    """基于结构生成候选探针，并在当前（参考）结构上验证，只返回行为符合预期的。

    验证在同一个临时 schema 上执行并回滚，因此不会留下数据；生成不出来的
    （例如非空列拿不到示例值、或插入被外键拦住）会被自动丢弃，避免误报。
    """
    validated: List[Dict[str, Any]] = []
    for probe in _build_probe_candidates(snapshot):
        actual_code = _probe_outcome(cur, probe['sql'])
        if probe['expect'] == 'error':
            passed = actual_code == probe.get('error_code')
        else:
            passed = actual_code is None
        if passed:
            validated.append(probe)
    return validated


# --------------------------------------------------------------------------- #
# 渲染
# --------------------------------------------------------------------------- #
def render_snapshot(snapshot: Optional[Dict[str, Any]]) -> str:
    """把实际结构渲染成可读文本（学生自己创建的结构，不含期望值）。"""
    tables = (snapshot or {}).get('tables') or {}
    if not tables:
        return '（未创建任何表）'
    lines: List[str] = []
    for table_name in sorted(tables):
        table = tables[table_name]
        lines.append(f'表 {table_name}:')
        for column in table.get('columns', []):
            parts = [column['name'], column['type']]
            if column['not_null']:
                parts.append('NOT NULL')
            if column['default']:
                parts.append(f'DEFAULT {column["default"]}')
            lines.append('  ' + ' '.join(parts))
        primary = (table.get('primary_key') or {}).get('columns') or []
        if primary:
            lines.append('  主键: ' + ', '.join(primary))
        for unique in table.get('unique', []):
            lines.append('  唯一: ' + ', '.join(unique.get('columns') or []))
        for fk in table.get('foreign_keys', []):
            lines.append(
                '  外键: ' + ', '.join(fk['columns'])
                + ' -> ' + fk['references']['table']
                + '(' + ', '.join(fk['references']['columns']) + ')'
            )
        for check in table.get('checks', []):
            lines.append('  CHECK: ' + check.get('expression', ''))
        for index in table.get('indexes', []):
            flag = '唯一索引' if index.get('unique') else '索引'
            desc = index.get('desc') or []
            rendered = []
            for position, column in enumerate(index.get('columns') or []):
                rendered.append(column + (' DESC' if position < len(desc) and desc[position] else ''))
            lines.append(f'  {flag}: ' + ', '.join(rendered))
    return '\n'.join(lines)
