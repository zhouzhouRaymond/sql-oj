"""提交查询参数解析工具。

提交列表的过滤（``views.SubmissionViewSet``）与单题统计的时间筛选
（``views_stats.StatsViewSet``）共用同一套解析规则，避免两端对
``start`` / ``end`` 的处理出现分歧。
"""
import re
from datetime import datetime, time

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.exceptions import ValidationError

# 只给日期（2026-10-02）或只精确到分钟（2026-10-02 10:30）
_DATE_ONLY_RE = re.compile(r'^\d{4}-\d{1,2}-\d{1,2}$')
_MINUTE_ONLY_RE = re.compile(r'^\d{4}-\d{1,2}-\d{1,2}[T ]\d{1,2}:\d{1,2}$')


def to_int(raw, field):
    """把查询参数转成整数；非法值返回 400，避免直接抛 ValueError 变成 500。"""
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValidationError({field: '必须为整数'})


def parse_time_range(start_raw, end_raw):
    """把 ``?start=&end=`` 解析为带时区的 datetime。

    - 支持 ``YYYY-MM-DD``（end 自动补到当天 23:59:59.999999）、
      ``YYYY-MM-DD HH:mm``（end 补到该分钟的 59.999999 秒）或完整 ISO 时间；
    - 为空则返回 None，表示该侧不做时间限制。
    """
    def to_datetime(raw, is_end=False):
        raw = (raw or '').strip()
        if not raw:
            return None
        if _DATE_ONLY_RE.match(raw):
            # 只给日期：start 取当天 00:00:00，end 取当天 23:59:59.999999
            day = parse_date(raw)
            if day is None:
                return None
            value = datetime.combine(day, time.max if is_end else time.min)
        else:
            value = parse_datetime(raw)
            if value is None:
                return None
            if is_end and _MINUTE_ONLY_RE.match(raw):
                # 结束时间只精确到分钟时，按「该分钟的最后一刻」处理，
                # 否则同一分钟内 10:30:30 这样的提交会被漏掉
                value = value.replace(second=59, microsecond=999999)
        if timezone.is_naive(value):
            value = timezone.make_aware(value)
        return value

    return to_datetime(start_raw), to_datetime(end_raw, is_end=True)


__all__ = ['to_int', 'parse_time_range']
