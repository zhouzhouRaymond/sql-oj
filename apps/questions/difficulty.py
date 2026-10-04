"""基于历史提交数据推荐题目难度。

设计取舍：

- 以「学生通过率」而非「提交通过率」为准，同一学生反复提交不应影响难度判断；
- 只统计学生提交，教师的试做不参与；
- 样本不足时不给建议（``recommended_difficulty=None``），避免一两个学生的结果
  把结论带偏。
"""
from __future__ import annotations

from typing import Optional, TypedDict

DIFFICULTY_LABELS = {'easy': '简单', 'medium': '中等', 'hard': '困难'}

#: 给出建议所需的最少尝试学生数；低于该值只展示通过率，不推荐难度
MIN_SAMPLE_SIZE = 3
#: 达到该尝试人数视为样本充分，建议置信度为 high
SOLID_SAMPLE_SIZE = 10

#: 学生通过率阈值：>= EASY_PASS_RATE 判为简单，>= HARD_PASS_RATE 判为中等，低于则困难
EASY_PASS_RATE = 0.8
HARD_PASS_RATE = 0.4


class DifficultyRecommendation(TypedDict):
    """难度建议结果：``recommended_difficulty`` 为 None 表示样本不足。"""

    recommended_difficulty: Optional[str]
    confidence: str
    reason: str


def recommend_difficulty(
    *, attempted_students: int, passed_students: int
) -> DifficultyRecommendation:
    """按学生通过率给出难度建议。

    :param attempted_students: 尝试过该题的学生数（去重）
    :param passed_students: 至少通过一次该题的学生数（去重）
    """
    attempted = max(0, int(attempted_students or 0))
    passed = min(max(0, int(passed_students or 0)), attempted)

    if attempted == 0:
        return {
            'recommended_difficulty': None,
            'confidence': 'none',
            'reason': '还没有学生提交，无法给出难度建议',
        }
    if attempted < MIN_SAMPLE_SIZE:
        return {
            'recommended_difficulty': None,
            'confidence': 'low',
            'reason': f'仅 {attempted} 名学生尝试，样本不足（建议至少 {MIN_SAMPLE_SIZE} 名）',
        }

    rate = passed / attempted
    if rate >= EASY_PASS_RATE:
        recommended = 'easy'
        reason = f'{attempted} 名学生中 {passed} 人通过（{rate:.0%}），大多数人能完成，适合标记为简单'
    elif rate >= HARD_PASS_RATE:
        recommended = 'medium'
        reason = f'{attempted} 名学生中 {passed} 人通过（{rate:.0%}），通过率适中，适合标记为中等'
    else:
        recommended = 'hard'
        reason = f'{attempted} 名学生中 {passed} 人通过（{rate:.0%}），通过率偏低，适合标记为困难'

    confidence = 'high' if attempted >= SOLID_SAMPLE_SIZE else (
        'medium' if attempted >= 5 else 'low'
    )
    return {
        'recommended_difficulty': recommended,
        'confidence': confidence,
        'reason': reason,
    }
