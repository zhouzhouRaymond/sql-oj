import os

import requests
from typing import List, Dict, Any

# 判题服务地址，可通过环境变量 JUDGE_SERVICE_URL 覆盖（容器化部署时指向 judge-service 服务）
JUDGE_SERVICE_URL = os.environ.get("JUDGE_SERVICE_URL", "http://localhost:8080/judge")

def judge_submission(submitted_sql: str, test_cases: List[Dict], create_table_sql: str = "") -> Dict[str, Any]:
    """
    调用判题服务进行 SQL 判题
    
    参数:
        submitted_sql: 学生提交的 SQL 语句
        test_cases: 测试用例列表，每个测试用例包含:
            - expected_output: 预期输出字符串（如 "name|age\nAlice|20"）
            - test_input: 可选的测试数据准备语句（多条可用分号分隔）
        create_table_sql: 建表语句（可选，多条可用分号分隔）
    
    返回:
        判题结果字典，格式:
        {
            "passed": bool,
            "execution_status": str,  # ACCEPTED / WRONG_ANSWER / TIMEOUT / ERROR
            "score": int,
            "details": [...]
        }
    """
    formatted_cases = []
    for tc in test_cases:
        formatted_cases.append({
            "expected_output": tc.get("expected_output", ""),  
            "test_input": tc.get("test_input", "")
        })
    
    payload = {
        "submitted_sql": submitted_sql,
        "test_cases": formatted_cases,
        "create_table_sql": create_table_sql,
        "timeout": 30
    }
    
    try:
        response = requests.post(JUDGE_SERVICE_URL, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.Timeout:
        return {
            "passed": False,
            "execution_status": "TIMEOUT",
            "score": 0,
            "details": []
        }
    except Exception as e:
        return {
            "passed": False,
            "execution_status": "ERROR",
            "score": 0,
            "details": []
        }