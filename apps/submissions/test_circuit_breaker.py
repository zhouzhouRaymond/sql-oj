"""判题熔断器单元测试（使用 LocMem 缓存，不依赖数据库）。"""
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from .circuit_breaker import CircuitBreaker, JudgeCircuitOpen

OPEN_KEY = 'test:judge:breaker'


class CircuitBreakerTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        # 固定时钟，避免真实时间已越过冷却期导致断言不稳定
        self.clock = [1000.0]
        clock_patcher = patch(
            'apps.submissions.circuit_breaker.time.time',
            side_effect=lambda: self.clock[0],
        )
        clock_patcher.start()
        self.addCleanup(clock_patcher.stop)
        self.breaker = CircuitBreaker(threshold=2, cooldown=10.0, open_key=OPEN_KEY)

    def test_stays_closed_before_threshold(self):
        self.assertTrue(self.breaker.allow())
        self.breaker.record_failure()
        self.assertTrue(self.breaker.allow())

    def test_opens_after_consecutive_failures(self):
        self.breaker.record_failure()
        self.breaker.record_failure()

        self.assertFalse(self.breaker.allow())
        with self.assertRaises(JudgeCircuitOpen):
            self.breaker.ensure_allowed()

    def test_success_resets_failure_streak(self):
        self.breaker.record_failure()
        self.breaker.record_success()
        self.breaker.record_failure()
        # 只有「连续」失败才计数：失败 → 成功 → 失败不应触发熔断
        self.assertTrue(self.breaker.allow())

    def test_allows_probe_again_after_cooldown(self):
        self.breaker.record_failure()
        self.breaker.record_failure()

        self.clock[0] = 1005.0
        self.assertFalse(self.breaker.allow())
        self.clock[0] = 1011.0
        self.assertTrue(self.breaker.allow())

        # 探测成功即彻底恢复
        self.breaker.record_success()
        self.assertTrue(self.breaker.allow())
