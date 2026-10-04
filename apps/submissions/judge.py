"""调用判题服务（FastAPI judge-service）的 HTTP 客户端。

判题服务地址可用环境变量 ``JUDGE_SERVICE_URL`` 覆盖（容器化部署时指向
``judge-service`` 服务）；SQL 硬超时与判题环境指纹见模块内常量。
"""
import os
from typing import Any, Dict, List

import requests

# 判题服务地址（默认本机 8080，容器内指向 judge-service 服务名）
JUDGE_SERVICE_URL = os.environ.get("JUDGE_SERVICE_URL", "http://localhost:8080/judge")
# 判题 HTTP 硬超时（秒）：应用层兜底，避免后台工作线程卡在一次失败调用上
JUDGE_HTTP_TIMEOUT = int(os.environ.get("JUDGE_HTTP_TIMEOUT", "35"))
# 单条 SQL 执行时间上限（秒）：作为请求体 timeout 的封顶，避免传入过大值
JUDGE_MAX_SQL_TIMEOUT = int(os.environ.get("JUDGE_MAX_SQL_TIMEOUT", "60"))


class JudgeTransportError(RuntimeError):
    """与判题服务通信层失败（连接/超时/非 2xx/坏响应），用于熔断统计。"""


def _build_payload(
    submitted_sql: str, test_cases: List[Dict], create_table_sql: str
) -> Dict[str, Any]:
    """构造判题请求体（字段与 docs/judge_api_new.md 3.2 一致）。"""
    formatted_cases = [
        {
            "expected_output": tc.get("expected_output", ""),
            "test_input": tc.get("test_input", ""),
        }
        for tc in test_cases
    ]
    # 请求侧硬超时上限：不超过 JUDGE_MAX_SQL_TIMEOUT，且留出连接开销
    sql_timeout = max(1, min(JUDGE_MAX_SQL_TIMEOUT, JUDGE_HTTP_TIMEOUT - 5))
    return {
        "submitted_sql": submitted_sql,
        "test_cases": formatted_cases,
        "create_table_sql": create_table_sql,
        "timeout": sql_timeout,
    }


def judge_submission_strict(
    submitted_sql: str, test_cases: List[Dict], create_table_sql: str = ""
) -> Dict[str, Any]:
    """调用判题服务；通信层失败时抛出 :class:`JudgeTransportError`。

    与 :func:`judge_submission` 不同，这里不把通信层错误降级成 ERROR 结果，
    而是上抛给上层统计失败率/触发熔断（区分「判题服务故障」与「学生 SQL 写错」）。
    """
    payload = _build_payload(submitted_sql, test_cases, create_table_sql)
    try:
        response = requests.post(
            JUDGE_SERVICE_URL, json=payload, timeout=JUDGE_HTTP_TIMEOUT
        )
        response.raise_for_status()
    except (requests.Timeout, requests.ConnectionError) as exc:
        raise JudgeTransportError(f"判题服务通信失败: {exc}") from exc
    except requests.HTTPError as exc:
        raise JudgeTransportError(f"判题服务返回错误: {exc}") from exc
    try:
        return response.json()
    except ValueError as exc:
        raise JudgeTransportError(f"判题服务响应非法 JSON: {exc}") from exc


def judge_submission(
    submitted_sql: str, test_cases: List[Dict], create_table_sql: str = ""
) -> Dict[str, Any]:
    """调用判题服务进行 SQL 判题（向后兼容：通信层失败降级为 TIMEOUT/ERROR 结果）。

    参数:
        submitted_sql: 学生提交的 SQL 语句
        test_cases: 测试用例列表，每项含 ``expected_output`` 与可选 ``test_input``
        create_table_sql: 建表语句（可选，多条可用分号分隔）

    返回:
        判题结果字典，含 ``passed`` / ``execution_status`` / ``score`` / ``details``。
    """
    try:
        return judge_submission_strict(submitted_sql, test_cases, create_table_sql)
    except JudgeTransportError:
        return {
            "passed": False,
            "execution_status": "TIMEOUT",
            "score": 0,
            "details": [],
        }
