"""SQL 规范化与判题缓存指纹。

硬性约束：判题结果缓存键必须包含「题目 ID、SQL 规范化结果、用例」，
并可叠加「判题环境指纹」以便环境（DB/判题服务版本）变化时自动失效。

设计要点：

- :func:`normalize_sql` 只做**语义等价**的改写：去注释、压缩多余空白、
  统一关键字大小写。字符串字面量（含其中的空格/大小写）原样保留，
  避免把两条语义不同的 SQL 归一到同一个缓存键上。
- :func:`cases_fingerprint` 对用例（``test_input`` + ``expected_output``）
  做稳定哈希；用例（含顺序）变化即换键，避免用旧结果误判。
- :func:`judge_env_fingerprint` 由环境变量提供，缺省内置一个与当前
  judge-db / judge-service 版本对应的常量。
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Iterable, Optional

import sqlparse
from sqlparse import tokens as T


def normalize_sql(sql: Optional[str]) -> str:
    """把 SQL 规范化为**语义等价**的规范形式，用于缓存键与幂等判重。

    - 去掉 ``--`` / ``/* */`` 注释；
    - 把连续空白压缩为单个空格；
    - 关键字统一为大写；
    - 字符串字面量、标识符原样保留（不改变大小写，不压缩内部空白）。
    """
    if not sql:
        return ""

    parts: list[str] = []
    for statement in sqlparse.parse(sql):
        for token in statement.flatten():
            # 注释按空白处理：直接丢弃会让相邻 token 粘连（如 "1--x\nFROM"）
            if token.is_whitespace or token.ttype in T.Comment:
                if parts and parts[-1] != " ":
                    parts.append(" ")
                continue
            value = token.value
            if token.ttype in T.Keyword:
                value = value.upper()
            parts.append(value)

    return "".join(parts).strip()


def _digest(parts: Iterable[str]) -> str:
    """对若干字符串做稳定的 sha256 指纹（用不可见分隔符避免歧义拼接）。"""
    hasher = hashlib.sha256()
    for part in parts:
        hasher.update(b"\x1f")
        hasher.update((part or "").encode("utf-8"))
    return hasher.hexdigest()


def cases_fingerprint(test_cases: Iterable[Dict[str, Any]]) -> str:
    """对用例列表（顺序敏感）生成指纹。

    序列化整个用例字典：查询模式的 ``test_input`` / ``expected_output`` 与
    schema 模式的 ``expected_schema`` / ``probes`` 任一变化都会换键。
    """
    return _digest(
        json.dumps(case, sort_keys=True, ensure_ascii=False, default=str)
        for case in test_cases
    )


def judge_env_fingerprint() -> str:
    """判题环境指纹：DB 版本 / 判题服务版本等变化时用于失效缓存。

    可通过 ``JUDGE_ENV_FINGERPRINT`` 显式覆盖（例如发布新判题容器时改它）。
    """
    override = os.environ.get("JUDGE_ENV_FINGERPRINT")
    if override:
        return override
    # 缺省值与当前判题容器版本对应；升级判题容器/DB 时请同步修改
    return "judge-db:postgres15|judge-service:2.4.0"


def result_cache_key(
    question_id: int,
    sql: str,
    test_cases: Iterable[Dict[str, Any]],
    env_fingerprint: Optional[str] = None,
    judge_mode: str = 'query',
    strictness: str = 'subset',
    compare_names: bool = False,
) -> str:
    """按硬性约束拼出结果缓存键：题目 ID + 判题参数 + SQL 规范化 + 用例 + 环境指纹。"""
    normalized = normalize_sql(sql)
    cases_fp = cases_fingerprint(test_cases)
    env_fp = env_fingerprint or judge_env_fingerprint()
    options = f'{judge_mode}:{strictness}:{int(bool(compare_names))}'
    payload = _digest([str(question_id), options, normalized, cases_fp, env_fp])
    return f"judge:result:{payload}"
