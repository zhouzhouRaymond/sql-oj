#!/usr/bin/env python3
"""判题服务并发压测工具（仅用标准库，宿主机或任意容器内都能直接运行）。

用法：
    python judge_service/load_test.py                        # 默认压本机 8080，跑并发阶梯
    python judge_service/load_test.py --url http://judge-service:8080/judge
    python judge_service/load_test.py --mode sustained --concurrency 32 --duration 15
    python judge_service/load_test.py --heavy                # 换成 CPU 型重负载
    python judge_service/load_test.py --max-concurrency 64 --json result.json

两种负载：
    light（默认）    1 个用例：建表 + 插 200 行 + SELECT id ... ORDER BY id
    heavy（--heavy） 4 个用例：建表 + 插 800 行 + 800×800 自连接聚合（CPU 型）

输出每档并发的吞吐（req/s）、成功率、p50/p95/p99/max 延迟与响应状态分布；
出现非判题响应（HTTP 错误 / 客户端失败）时退出码为 1，便于 CI 判定。
每条工作线程复用一条 HTTP keep-alive 连接，避免把「每次重连」的开销算进被测服务。

注意：绝对数值与运行机器强相关，使用时关注形状而非绝对值——
吞吐平台期出现在哪、延迟是否随并发线性增长、瓶颈容器的 CPU 是否顶格。
实测参考见 docs/judge_api_new.md 第 10 节。
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import queue
import sys
import threading
import time
from collections import Counter
from urllib.parse import urlparse

DEFAULT_URL = "http://localhost:8080/judge"
# 正常判题结果；其余状态（HTTP 错误、ERROR:原因、客户端失败等）都算作「非判题响应」
JUDGE_STATUSES = ("ACCEPTED", "WRONG_ANSWER")
# 服务间令牌请求头：main() 里按 --token / JUDGE_SERVICE_TOKEN 填充
EXTRA_HEADERS = {}


def build_payload(cases=1, rows=200, heavy=False):
    """构造判题请求体（字段与 docs/judge_api_new.md 3.2 一致）。"""
    insert = ("INSERT INTO bench (id, name) VALUES "
              + ",".join(f"({i}, 'n{i}')" for i in range(1, rows + 1)) + ";")
    if heavy:
        submitted = "SELECT count(*) AS c FROM bench a, bench b"
        expected = "c\n" + str(rows * rows)
    else:
        submitted = "SELECT id FROM bench ORDER BY id"
        expected = "id\n" + "\n".join(str(i) for i in range(1, rows + 1))
    return {
        "submitted_sql": submitted,
        "create_table_sql": "CREATE TABLE bench (id INT, name TEXT);",
        "test_cases": [{"test_input": insert, "expected_output": expected}
                       for _ in range(cases)],
        "timeout": 30,
    }


def target_of(url):
    """把 URL 拆成 (host, port, path)。"""
    parsed = urlparse(url)
    return parsed.hostname or "localhost", parsed.port or 80, parsed.path or "/"


def new_connection(host, port, timeout=120):
    """新建一条 HTTP 连接（由各工作线程长期复用，保持 keep-alive）。"""
    return http.client.HTTPConnection(host, port, timeout=timeout)


def one_request(conn, path, body):
    """在给定连接上发一次判题请求。

    返回 (耗时秒, 状态, conn)：
    - 状态取 execution_status，或 CLIENT_FAIL / HTTP_xxx / BAD_BODY 等错误标记；
    - 连接异常时第三个值为 None，调用方需重建连接。
    """
    payload = json.dumps(body).encode()
    t0 = time.perf_counter()
    try:
        conn.request("POST", path, body=payload,
                     headers={"Content-Type": "application/json",
                              "Content-Length": str(len(payload)),
                              **EXTRA_HEADERS})
        response = conn.getresponse()
        raw = response.read()
    except Exception as exc:                      # 连接失败 / 客户端超时
        return time.perf_counter() - t0, "CLIENT_FAIL:" + type(exc).__name__, None
    dt = time.perf_counter() - t0
    if response.status != 200:
        return dt, f"HTTP_{response.status}", conn
    try:
        data = json.loads(raw)
    except Exception:
        return dt, "BAD_BODY", conn
    status = data.get("execution_status", "?")
    if status == "ERROR":
        # 带上服务端给出的原因（建表失败、服务繁忙等），否则 ERROR 无法定位
        detail = " ".join(str(data.get("error_message") or "").split())[:60]
        return dt, f"ERROR:{detail}" if detail else "ERROR", conn
    return dt, status, conn


def percentile(sorted_values, q):
    if not sorted_values:
        return 0.0
    return sorted_values[min(len(sorted_values) - 1, int(round(q * (len(sorted_values) - 1))))]


def _run_workers(host, port, path, body, workers, next_task, timeout=120):
    """启动 workers 条线程跑任务，返回 (已排序延迟列表, 状态计数)。

    ``next_task()`` 返回 None 表示该线程已无任务；每条线程复用一条 keep-alive 连接。
    """
    latencies, statuses, lock = [], Counter(), threading.Lock()

    def worker():
        conn = new_connection(host, port, timeout)
        try:
            while True:
                if next_task() is None:
                    return
                dt, status, conn = one_request(conn, path, body)
                if conn is None:                   # 连接坏了，换一条继续
                    conn = new_connection(host, port, timeout)
                with lock:
                    latencies.append(dt)
                    statuses[status] += 1
        finally:
            conn.close()

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    latencies.sort()
    return latencies, statuses


def run_batch(host, port, path, body, concurrency, total):
    """closed-loop 档位：concurrency 个线程共同打完 total 个请求。"""
    pending = queue.Queue()
    for _ in range(total):
        pending.put(1)

    def next_task():
        try:
            pending.get_nowait()
            return True
        except queue.Empty:
            return None

    t0 = time.perf_counter()
    latencies, statuses = _run_workers(host, port, path, body, concurrency, next_task)
    wall = time.perf_counter() - t0
    return wall, latencies, statuses


def run_fixed_duration(host, port, path, body, concurrency, duration):
    """sustained 档位：固定并发持续压一段时间（每个线程持续发请求）。"""
    deadline = time.perf_counter() + duration

    def next_task():
        return True if time.perf_counter() < deadline else None

    t0 = time.perf_counter()
    latencies, statuses = _run_workers(host, port, path, body, concurrency, next_task)
    wall = time.perf_counter() - t0
    return wall, latencies, statuses


def print_row(label, wall, latencies, statuses):
    """打印一档结果，返回 (吞吐, 成功数, 总数)；非判题响应单独列出。"""
    total = sum(statuses.values())
    ok = sum(count for status, count in statuses.items() if status in JUDGE_STATUSES)
    rps = total / wall if wall else 0.0
    print(f"{label:>6} | {total:>5} | {wall:>7.2f} | {rps:>7.1f} | {ok:>5}/{total:<5} | "
          f"{percentile(latencies, .5) * 1000:>8.1f} | {percentile(latencies, .95) * 1000:>8.1f} | "
          f"{percentile(latencies, .99) * 1000:>9.1f} | "
          f"{(max(latencies) * 1000) if latencies else 0:>9.1f}")
    for status, count in statuses.most_common():
        if status not in JUDGE_STATUSES:
            print(f"         !! {status} x{count}")
    return rps, ok, total


def main():
    parser = argparse.ArgumentParser(
        description="判题服务并发压测（吞吐 / 延迟 / 状态分布）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="判题接口地址")
    parser.add_argument("--mode", choices=("ramp", "sustained"), default="ramp",
                        help="ramp=并发阶梯；sustained=固定并发持续压")
    parser.add_argument("--max-concurrency", type=int, default=128,
                        help="ramp 模式的阶梯上限")
    parser.add_argument("--concurrency", type=int, default=32,
                        help="sustained 模式的固定并发")
    parser.add_argument("--duration", type=float, default=15.0,
                        help="sustained 模式的持续秒数")
    parser.add_argument("--cases", type=int, default=0,
                        help="每个请求的用例数（默认 light=1 / heavy=4）")
    parser.add_argument("--rows", type=int, default=0,
                        help="每个用例插入的行数（默认 light=200 / heavy=800）")
    parser.add_argument("--heavy", action="store_true", help="使用 CPU 型重负载")
    parser.add_argument("--json", dest="json_out", default="",
                        help="把每档结果同时写成 JSON 文件")
    parser.add_argument("--token", default=os.environ.get("JUDGE_SERVICE_TOKEN", ""),
                        help="判题服务鉴权令牌（默认取 JUDGE_SERVICE_TOKEN）")
    args = parser.parse_args()

    if args.token.strip():
        EXTRA_HEADERS["X-Judge-Token"] = args.token.strip()
    else:
        print("warn: 未提供 JUDGE_SERVICE_TOKEN，判题服务开启鉴权时会返回 401",
              file=sys.stderr)

    cases = args.cases or (4 if args.heavy else 1)
    rows = args.rows or (800 if args.heavy else 200)
    body = build_payload(cases=cases, rows=rows, heavy=args.heavy)
    host, port, path = target_of(args.url)

    print(f"target  = {args.url}")
    print(f"payload = {'heavy' if args.heavy else 'light'} "
          f"(cases={cases}, rows={rows}, sql={body['submitted_sql']})")
    try:
        t0 = time.perf_counter()
        health = new_connection(host, port, timeout=10)
        health.request("GET", "/health")
        health_resp = health.getresponse()
        health_body = health_resp.read().decode().strip()
        health.close()
        print(f"health  = {health_resp.status} {health_body} "
              f"({time.perf_counter() - t0:.3f}s)")
    except Exception as exc:
        print(f"health  = FAILED ({exc})", file=sys.stderr)
        return 2

    print("\n[single request]")
    smoke = new_connection(host, port)
    for i in range(3):
        dt, status, smoke = one_request(smoke, path, body)
        if smoke is None:
            smoke = new_connection(host, port)
        print(f"  #{i + 1}: {dt * 1000:>8.1f} ms -> {status}")
    smoke.close()

    print(f"\n{'     C':>6} | {'    N':>5} | {'wall s':>7} | {'req/s':>7} | {'ok':>11} | "
          f"{'p50 ms':>8} | {'p95 ms':>8} | {'p99 ms':>9} | {'max ms':>9}")
    print("-" * 105)

    results, errors = [], 0
    if args.mode == "ramp":
        levels = [c for c in (1, 2, 4, 8, 16, 32, 64, 128) if c <= args.max_concurrency]
        if args.max_concurrency > 128:
            levels.append(args.max_concurrency)
        batches = [
            (c, lambda c=c: run_batch(host, port, path, body, c, min(240, max(40, c * 4))))
            for c in levels
        ]
    else:
        batches = [(args.concurrency,
                    lambda: run_fixed_duration(host, port, path, body,
                                               args.concurrency, args.duration))]

    for concurrency, run in batches:
        wall, latencies, statuses = run()
        rps, ok, count = print_row(str(concurrency), wall, latencies, statuses)
        errors += count - ok
        results.append({
            "concurrency": concurrency, "requests": count, "wall_s": round(wall, 2),
            "rps": round(rps, 1), "ok": ok, "errors": count - ok,
            "p50_ms": round(percentile(latencies, .5) * 1000, 1),
            "p95_ms": round(percentile(latencies, .95) * 1000, 1),
            "max_ms": round((latencies[-1] if latencies else 0) * 1000, 1),
        })

    print("-" * 105)
    peak = max(results, key=lambda item: item["rps"])
    print(f"peak throughput     = {peak['rps']} req/s @ C={peak['concurrency']}")
    print(f"non-judge responses = {errors}")
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fp:
            json.dump({"target": args.url, "heavy": args.heavy, "cases": cases, "rows": rows,
                       "results": results}, fp, ensure_ascii=False, indent=2)
        print(f"json written to     = {args.json_out}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
