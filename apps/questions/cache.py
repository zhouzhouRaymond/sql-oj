"""题目判题元数据缓存（题目元数据 / 用例本地缓存）。

判题时每道题都需要 ``create_table_sql`` 与有序用例；这里把它们打包缓存，
避免每次判题都回查数据库。

一致性策略：

- ``Question`` / ``TestCase`` 变更时通过信号立即失效对应缓存；
- 同时设置兜底 TTL（``JUDGE_QUESTION_CACHE_TTL``，默认 300s），
  防止多进程 LocMem 缓存下某个 worker 长期持有旧数据；
- 缓存后端为 Redis 时，失效对所有进程立即生效。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from django.conf import settings
from django.core.cache import cache

_PREFIX = "judge:question-bundle:"


def _ttl() -> int:
    try:
        return int(getattr(settings, "JUDGE_QUESTION_CACHE_TTL", 300))
    except (TypeError, ValueError):
        return 300


def bundle_key(question_id) -> str:
    return f"{_PREFIX}{question_id}"


def build_bundle(question_id) -> Optional[Dict[str, Any]]:
    """从数据库构建判题所需题目包；题目不存在返回 ``None``。"""
    from .models import Question

    question = Question.objects.filter(id=question_id).first()
    if question is None:
        return None
    cases: List[Dict[str, Any]] = list(
        question.test_cases.order_by("id").values("test_input", "expected_output")
    )
    return {
        "question_id": question.id,
        "create_table_sql": question.create_table_sql or "",
        "test_cases": cases,
    }


def get_bundle(question_id) -> Optional[Dict[str, Any]]:
    """取题目包（命中缓存则直接返回）。"""
    ttl = _ttl()
    if ttl <= 0:
        return build_bundle(question_id)

    key = bundle_key(question_id)
    cached = cache.get(key)
    if isinstance(cached, dict):
        return cached

    bundle = build_bundle(question_id)
    if bundle is not None:
        cache.set(key, bundle, ttl)
    return bundle


def invalidate(question_id) -> None:
    """失效某道题的判题元数据缓存（题目/用例变更时调用）。"""
    if question_id:
        cache.delete(bundle_key(question_id))
