"""提交查询参数解析（query_params.py）单元测试，不依赖数据库。"""
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .query_params import parse_time_range, to_int


class ToIntTests(SimpleTestCase):
    def test_returns_integer(self):
        self.assertEqual(to_int('42', 'question_id'), 42)

    def test_invalid_value_raises_validation_error(self):
        for raw in ('abc', None, ''):
            with self.subTest(raw=raw):
                with self.assertRaises(ValidationError):
                    to_int(raw, 'exam')


class ParseTimeRangeTests(SimpleTestCase):
    def test_empty_range_returns_none(self):
        self.assertEqual(parse_time_range(None, ''), (None, None))

    def test_date_only_range_covers_whole_day(self):
        start, end = parse_time_range('2026-10-02', '2026-10-02')
        self.assertEqual((start.hour, start.minute, start.second), (0, 0, 0))
        self.assertEqual((end.hour, end.minute, end.second, end.microsecond),
                         (23, 59, 59, 999999))

    def test_minute_precision_end_covers_whole_minute(self):
        _start, end = parse_time_range(None, '2026-10-02 10:30')
        self.assertEqual((end.hour, end.minute, end.second, end.microsecond),
                         (10, 30, 59, 999999))

    def test_invalid_value_returns_none(self):
        self.assertEqual(parse_time_range('not-a-date', 'also-bad'), (None, None))

    def test_naive_values_are_made_aware(self):
        start, end = parse_time_range('2026-10-02', '2026-10-02 10:30')
        self.assertTrue(timezone.is_aware(start))
        self.assertTrue(timezone.is_aware(end))
