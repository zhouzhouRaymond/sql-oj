"""判题消息队列（Redis 后端状态机 + Worker 命令）测试。"""
import io
import os
import time
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.submissions import job_queue
from apps.submissions.job_queue import RedisJudgeQueue


class FakeRedis:
    """仅实现判题队列用到的最小 Redis 命令集，用于验证状态机。"""

    def __init__(self):
        self.lists = {}
        self.zsets = {}

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)
        return len(self.lists[key])

    def brpoplpush(self, src, dst, timeout=0):
        if not self.lists.get(src):
            return None
        value = self.lists[src].pop()
        self.lists.setdefault(dst, []).insert(0, value)
        return str(value).encode()

    def lrem(self, key, count, value):
        kept, removed = [], 0
        for item in self.lists.get(key, []):
            if removed < count and str(item) == str(value):
                removed += 1
                continue
            kept.append(item)
        self.lists[key] = kept
        return removed

    def zadd(self, key, mapping):
        self.zsets.setdefault(key, {}).update(mapping)
        return len(mapping)

    def zrem(self, key, member):
        return 1 if self.zsets.get(key, {}).pop(str(member), None) is not None else 0

    def zrangebyscore(self, key, minimum, maximum):
        low = float("-inf") if minimum == "-inf" else float(minimum)
        return [
            name.encode()
            for name, score in self.zsets.get(key, {}).items()
            if low <= score <= float(maximum)
        ]

    def llen(self, key):
        return len(self.lists.get(key, []))


class RedisJudgeQueueTests(SimpleTestCase):
    def setUp(self):
        self.client = FakeRedis()
        self.queue = RedisJudgeQueue(self.client, visibility_timeout=60)

    def test_enqueue_reserve_ack_roundtrip(self):
        self.queue.enqueue(11)
        self.assertEqual(self.queue.depth(), 1)

        submission_id = self.queue.reserve(timeout=0)
        self.assertEqual(submission_id, "11")
        self.assertEqual(self.queue.depth(), 0)
        self.assertEqual(self.queue.inflight(), 1)

        self.queue.ack(submission_id)
        self.assertEqual(self.queue.inflight(), 0)

    def test_reserve_is_fifo(self):
        self.queue.enqueue(1)
        self.queue.enqueue(2)
        self.assertEqual(self.queue.reserve(timeout=0), "1")
        self.assertEqual(self.queue.reserve(timeout=0), "2")

    def test_empty_reserve_returns_none(self):
        self.assertIsNone(self.queue.reserve(timeout=0))

    def test_stale_inflight_is_requeued(self):
        self.queue.enqueue(7)
        submission_id = self.queue.reserve(timeout=0)
        # 把时间戳改成很早，模拟 Worker 崩溃后超过可见性超时
        self.client.zsets[job_queue.INFLIGHT_TS_KEY][submission_id] = time.time() - 999

        self.assertEqual(self.queue.requeue_stale(), 1)
        self.assertEqual(self.queue.depth(), 1)
        self.assertEqual(self.queue.inflight(), 0)
        self.assertEqual(self.queue.reserve(timeout=0), "7")

    def test_failed_task_requeues_immediately(self):
        self.queue.enqueue(9)
        submission_id = self.queue.reserve(timeout=0)
        self.queue.requeue(submission_id)
        self.assertEqual(self.queue.depth(), 1)
        self.assertEqual(self.queue.inflight(), 0)


class BackendSelectionTests(SimpleTestCase):
    def test_auto_without_url_is_local(self):
        with mock.patch.dict(os.environ, {"JUDGE_QUEUE_BACKEND": "auto"}, clear=False):
            os.environ.pop("REDIS_URL", None)
            os.environ.pop("JUDGE_QUEUE_REDIS_URL", None)
            self.assertEqual(job_queue.backend_name(), "local")
            self.assertFalse(job_queue.use_redis())

    def test_auto_with_url_is_redis(self):
        env = {"JUDGE_QUEUE_BACKEND": "auto", "REDIS_URL": "redis://localhost:6379/0"}
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertEqual(job_queue.backend_name(), "redis")
            self.assertTrue(job_queue.use_redis())

    def test_explicit_local_wins(self):
        env = {"JUDGE_QUEUE_BACKEND": "local", "REDIS_URL": "redis://localhost:6379/0"}
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertFalse(job_queue.use_redis())


class JudgeWorkerCommandTests(SimpleTestCase):
    def test_local_backend_prints_guidance_and_returns(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"JUDGE_QUEUE_BACKEND": "local"}, clear=False):
            call_command("judge_worker", stdout=out, stderr=err)
        self.assertIn("redis", err.getvalue())
