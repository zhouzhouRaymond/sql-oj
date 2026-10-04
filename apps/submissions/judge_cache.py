"""判题结果缓存：按「题目 ID + SQL 规范化 + 用例 + 环境指纹」命中。

复用 Django 缓存框架：默认 LocMem（单进程），在 ``CACHES`` 指向 Redis
时自动变成跨进程共享缓存（见 README / settings）。缓存只保存判题服务
返回的结果字典，不保存用例输入/期望输出，避免泄露答案。

命中缓存的提交仍走异步链路（工作者直接落结果），只是不再调用判题容器，
从而降低容器占用、提升重复提交的响应速度。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from django.conf import settings
from django.core.cache import cache

from .normalization import result_cache_key


def _ttl() -> int:
    """缓存有效期（秒），可用 ``JUDGE_RESULT_CACHE_TTL`` 覆盖；<=0 视为禁用。"""
    try:
        return int(getattr(settings, "JUDGE_RESULT_CACHE_TTL", 3600))
    except (TypeError, ValueError):
        return 3600


def cache_enabled() -> bool:
    return _ttl() > 0


def build_key(
    question_id: int,
    sql: str,
    test_cases: Iterable[Dict[str, Any]],
) -> str:
    return result_cache_key(question_id, sql, test_cases)


def get_cached_result(
    question_id: int, sql: str, test_cases: Iterable[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """命中则返回判题结果字典，未命中/缓存关闭返回 ``None``。"""
    if not cache_enabled():
        return None
    cached = cache.get(build_key(question_id, sql, test_cases))
    return cached if isinstance(cached, dict) else None


def set_cached_result(
    question_id: int,
    sql: str,
    test_cases: Iterable[Dict[str, Any]],
    result: Dict[str, Any],
) -> None:
    """写入判题结果缓存；缓存关闭时为空操作。"""
    if not cache_enabled() or not isinstance(result, dict):
        return
    cache.set(build_key(question_id, sql, test_cases), result, _ttl())
