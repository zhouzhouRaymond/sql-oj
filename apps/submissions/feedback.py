"""判题反馈脱敏：学生默认只看到"哪一类检查没过"，不看到期望结构细节。

schema 判题返回的 ``checks`` 含具体列名、约束名、期望类型等信息，属于答案信息。
教师，或题目开启 ``show_case_details`` 时展示明细；否则只给分类汇总，避免学生
据此反推标准答案。
"""
from collections import Counter
from typing import Any, Dict

# 检查项名称关键词 -> 面向学生的分类
_CATEGORY_KEYWORDS = (
    ('字段', '字段定义'),
    ('主键', '约束'),
    ('唯一约束', '约束'),
    ('CHECK', '约束'),
    ('外键', '约束'),
    ('索引', '索引'),
)


def _category(check_name: str) -> str:
    for keyword, category in _CATEGORY_KEYWORDS:
        if keyword in check_name:
            return category
    return '行为校验'


def summarize_schema_failures(case: Dict[str, Any]) -> str:
    """把失败的检查项汇总成"分类 + 数量"，不暴露期望结构细节。"""
    checks = case.get('checks') or []
    failed = [check for check in checks if not check.get('passed')]
    if not failed:
        return '结构校验未通过'
    groups = Counter(_category(str(check.get('name') or '')) for check in failed)
    parts = '、'.join(f'{name} {count} 项' for name, count in groups.items())
    return f'结构校验未通过：{parts}（共 {len(failed)} 项）'


def student_case_message(case: Dict[str, Any]) -> str:
    """非明细模式下给学生的用例错误信息。"""
    if case.get('checks'):
        return summarize_schema_failures(case)
    # 查询模式：执行错误/超时等属于学生自己的运行信息，原样返回
    return case.get('error_message') or ''


__all__ = ['summarize_schema_failures', 'student_case_message']
