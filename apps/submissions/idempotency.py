"""判题提交幂等去重。

硬性约束（推荐架构「幂等校验」）：相同提交不重复创建判题任务。

以「学生 + 题目 + 考试 + SQL 规范化结果」为维度，在短窗口内复用最近一次
提交：命中缓存窗口或发现仍在 ``PENDING`` 的相同提交时，直接返回既有记录，
不再新建 Submission、不再入队判题。
"""
from __future__ import annotations

import hashlib
import os

from django.core.cache import cache

from .judging import PENDING
from .normalization import normalize_sql


def _ttl() -> int:
    try:
        return int(os.environ.get("JUDGE_IDEMPOTENCY_TTL", "30"))
    except ValueError:
        return 30


def idempotency_key(user_id, question_id, exam_id, submitted_sql) -> str:
    """幂等键：用户 + 题目 + 考试 + SQL 规范化结果的哈希。"""
    digest = hashlib.sha256(normalize_sql(submitted_sql).encode("utf-8")).hexdigest()
    return f"judge:submit:idem:{user_id}:{question_id}:{exam_id or 0}:{digest}"


def remember_submission(idem_key: str, submission_id: int) -> None:
    """记录「该幂等键已对应某条提交」，供窗口内重复提交复用。"""
    ttl = _ttl()
    if ttl > 0:
        cache.set(idem_key, submission_id, ttl)


def find_duplicate_submission(model, user, question, exam_id, submitted_sql, idem_key):
    """找出可复用的重复提交：先看窗口内最近一次，再看仍在 PENDING 的相同提交。"""
    ttl = _ttl()
    if ttl > 0:
        cached_id = cache.get(idem_key)
        if cached_id:
            duplicate = model.objects.filter(id=cached_id).first()
            if duplicate is not None:
                return duplicate
    return (
        model.objects.filter(
            student=user,
            question=question,
            exam_id=exam_id,
            submitted_sql=submitted_sql,
            execution_status=PENDING,
        )
        .order_by("-id")
        .first()
    )
