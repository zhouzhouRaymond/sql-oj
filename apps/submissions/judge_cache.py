"""判题结果缓存：按「题目 ID + SQL 规范化 + 用例 + 环境指纹」命中。

复用 Django 缓存框架：默认 LocMem（单进程），在 ``CACHES`` 指向 Redis
时自动变成跨进程共享缓存（见 README / settings）。缓存只保存判题服务
返回的结果字典，不保存用例输入/期望输出，避免泄露答案。

命中缓存的提交仍走异步链路（工作者直接落结果），只是不再调用判题容器，
从而降低容器占用、提升重复提交的响应速度。
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Iterable, Optional

from django.conf import settings
from django.core.cache import cache

from .normalization import result_cache_key

# 进程内的命中统计（用于监控缓存命中率；计数器本身不共享，缓存数据是否
# 共享取决于 CACHES 后端：LocMem 是单进程，Redis 是跨进程）。
_stats_lock = threading.Lock()
_hits = 0
_misses = 0
_lookups_while_disabled = 0


def _ttl() -> int:
    """缓存有效期（秒），可用 ``JUDGE_RESULT_CACHE_TTL`` 覆盖；<=0 视为禁用。"""
    try:
        return int(getattr(settings, "JUDGE_RESULT_CACHE_TTL", 3600))
    except (TypeError, ValueError):
        return 3600


def cache_enabled() -> bool:
    return _ttl() > 0


def reset_cache_stats() -> None:
    """清零命中统计（测试或按监控窗口重置时使用）。"""
    global _hits, _misses, _lookups_while_disabled
    with _stats_lock:
        _hits = _misses = _lookups_while_disabled = 0


def cache_stats() -> Dict[str, float]:
    """返回当前进程的结果缓存统计。

    ``hit_rate`` = hits / (hits + misses)，缓存关闭时的查询不计入分母，
    避免关闭缓存被误读成「命中率为 0」。
    """
    with _stats_lock:
        hits, misses, disabled = _hits, _misses, _lookups_while_disabled
    total = hits + misses
    return {
        'hits': hits,
        'misses': misses,
        'lookups': total,
        'lookups_while_disabled': disabled,
        'hit_rate': round(hits / total, 4) if total else 0.0,
    }


def build_key(
    question_id: int,
    sql: str,
    test_cases: Iterable[Dict[str, Any]],
    judge_mode: str = 'query',
    strictness: str = 'subset',
    compare_names: bool = False,
) -> str:
    return result_cache_key(
        question_id, sql, test_cases,
        judge_mode=judge_mode, strictness=strictness, compare_names=compare_names,
    )


def get_cached_result(
    question_id: int,
    sql: str,
    test_cases: Iterable[Dict[str, Any]],
    judge_mode: str = 'query',
    strictness: str = 'subset',
    compare_names: bool = False,
) -> Optional[Dict[str, Any]]:
    """命中则返回判题结果字典，未命中/缓存关闭返回 ``None``。"""
    global _hits, _misses, _lookups_while_disabled

    if not cache_enabled():
        with _stats_lock:
            _lookups_while_disabled += 1
        return None
    cached = cache.get(
        build_key(question_id, sql, test_cases, judge_mode, strictness, compare_names)
    )
    if isinstance(cached, dict):
        with _stats_lock:
            _hits += 1
        return cached
    with _stats_lock:
        _misses += 1
    return None


def set_cached_result(
    question_id: int,
    sql: str,
    test_cases: Iterable[Dict[str, Any]],
    result: Dict[str, Any],
    judge_mode: str = 'query',
    strictness: str = 'subset',
    compare_names: bool = False,
) -> None:
    """写入判题结果缓存；缓存关闭时为空操作。"""
    if not cache_enabled() or not isinstance(result, dict):
        return
    cache.set(
        build_key(question_id, sql, test_cases, judge_mode, strictness, compare_names),
        result, _ttl(),
    )
