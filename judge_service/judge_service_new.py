import logging
import signal
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, closing, contextmanager
from typing import Any, Dict, Iterator, List, Literal, Optional, Tuple
from uuid import uuid4

import psycopg2
import uvicorn
from fastapi import FastAPI
from psycopg2 import sql
from psycopg2.errors import QueryCanceled
from psycopg2.pool import PoolError
from pydantic import BaseModel, Field

from judge_config import get_int, get_str
from container_pool import PoolUnavailableError, container_pool
from schema_judge import (
    diff_schema,
    introspect_schema,
    render_snapshot,
    run_probes,
    suggest_probes,
)

logger = logging.getLogger("judge_service")
logging.basicConfig(level=logging.INFO)

# 数据库相关配置统一从配置文件（judge_service/.env）读取，详见 judge_config.py 与 .env.example
DB_NAME = get_str("JUDGE_DB_NAME", "judge_db")
DB_USER = get_str("JUDGE_DB_USER", "judge_user")
DB_PASSWORD = get_str("JUDGE_DB_PASSWORD", "judge_pass")
DB_HOST = get_str("JUDGE_DB_HOST", "127.0.0.1")
DB_PORT = get_int("JUDGE_DB_PORT", 5433)  # 与 docker-compose.yml 端口映射一致
DB_READY_TIMEOUT = get_int("JUDGE_DB_READY_TIMEOUT", 60)
DB_POOL_MAX = get_int("JUDGE_DB_POOL_MAX", 20)
# 常驻（预热）连接数：psycopg2 仅在空闲连接数 < minconn 时复用连接，否则用完即关闭，
# 导致高并发下反复建连。默认与最大连接数相同，保持连接常驻、省掉重连开销。
DB_POOL_MIN = get_int("JUDGE_DB_POOL_MIN", DB_POOL_MAX)


def _parse_db_targets(raw: str, default_port: int):
    """解析多 judge-db 目标列表（JUDGE_DB_TARGETS，逗号分隔 host[:port]）。

    未配置时回退到单个 JUDGE_DB_HOST:JUDGE_DB_PORT，保持原有行为。
    """
    targets = []
    for item in (raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        host, _, port = item.partition(":")
        targets.append((host, int(port) if port.strip() else default_port))
    return targets or [(DB_HOST, DB_PORT)]


# 判题库目标：多个 judge-db 实例做连接分片，聚合 CPU 提升吞吐
DB_TARGETS = _parse_db_targets(get_str("JUDGE_DB_TARGETS", ""), DB_PORT)
SQL_TIMEOUT = 30
MAX_TIMEOUT = 300
# 单用例 wall-clock 硬超时 = 用例 timeout + 宽限；即便 statement_timeout 未生效也能中断
CASE_HARD_GRACE = get_int("JUDGE_CASE_HARD_GRACE", 5)
POLL_INTERVAL = 0.5
DB_CONNECT_TIMEOUT = get_int("JUDGE_DB_CONNECT_TIMEOUT", 2)  # 单次连接尝试超时（秒）
CASE_CONCURRENCY = get_int("JUDGE_CASE_CONCURRENCY", 4)  # 单个请求内测试用例的并行度
POOL_ACQUIRE_TIMEOUT = get_int("JUDGE_POOL_ACQUIRE_TIMEOUT", 10)  # 等待空闲连接的最长秒数
POLL_ACQUIRE_INTERVAL = 0.02  # 池耗尽时轮询等待空闲连接的间隔（秒）

# psycopg2 连接池，lifespan 启动时初始化
db_pool: Optional[Any] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 判题库容器由 docker-compose 创建（见 docker-compose.yml），权限收敛在容器 initdb 脚本完成
    global db_pool
    for host, port in DB_TARGETS:
        wait_for_db(host, port)
    db_pool = MultiDbPool([
        psycopg2.pool.ThreadedConnectionPool(
            DB_POOL_MIN, DB_POOL_MAX,
            host=host, port=port, database=DB_NAME,
            user=DB_USER, password=DB_PASSWORD,
        )
        for host, port in DB_TARGETS
    ])
    logger.info("判题库连接池已建立：targets=%s", DB_TARGETS)
    # 可选：启用容器预热池后，SQL 在专用池容器中执行（JUDGE_POOL_SIZE>0）
    if container_pool is not None:
        container_pool.start()
    yield
    if container_pool is not None:
        container_pool.stop()
    if db_pool is not None:
        db_pool.closeall()


app = FastAPI(title="SQL Judge Service", version="2.4.0", lifespan=lifespan)

class Probe(BaseModel):
    """schema 判题的行为探针：断言语句成功，或按错误码断言失败。"""
    sql: str = Field(..., min_length=1)
    expect: Literal["ok", "error"] = "ok"
    error_code: Optional[str] = None
    description: Optional[str] = None

class TestCase(BaseModel):
    # query 模式用 expected_output；schema 模式用 expected_schema + probes
    expected_output: str = ""
    test_input: Optional[str] = ""
    expected_schema: Optional[Dict[str, Any]] = None
    probes: List[Probe] = []

class JudgeRequest(BaseModel):
    submitted_sql: str = Field(..., min_length=1)
    test_cases: List[TestCase] = Field(..., min_length=1)
    create_table_sql: Optional[str] = ""
    timeout: int = Field(default=SQL_TIMEOUT, ge=1, le=MAX_TIMEOUT)
    # query：查询结果判题（默认，行为不变）；schema：CREATE TABLE 等 DDL 结构判题
    mode: Literal["query", "schema"] = "query"
    # schema 模式专用：subset=多出的对象不判错；exact=对象集合必须完全一致
    strictness: Literal["subset", "exact"] = "subset"
    # schema 模式专用：是否要求约束名/索引名与期望一致（默认忽略名称）
    compare_names: bool = False

class CheckResult(BaseModel):
    name: str
    passed: bool
    detail: str = ""

class TestCaseResult(BaseModel):
    test_case_id: int
    passed: bool
    actual_output: str
    error_message: Optional[str] = None
    # schema 模式：逐项检查结果（结构 diff + 探针）；query 模式为空
    checks: List[CheckResult] = []

class JudgeResponse(BaseModel):
    passed: bool
    execution_status: str
    score: int
    details: List[TestCaseResult]
    # 仅当执行状态为 ERROR 时可能携带原因（如建表语句失败），便于上层定位问题
    error_message: Optional[str] = None


# 结果集字典：{"columns": [列名...], "rows": [数据行...]}，供解析/比较/格式化统一使用
ResultSet = Dict[str, Any]

# 连接层错误（连接中断、连接已关闭等）：向上抛，由调用方统一返回 ERROR，而非计入用例失败。
# 注意：QueryCanceled 是 OperationalError 的子类，捕获时需先于本元组判断。
_CONNECTION_ERRORS = (psycopg2.OperationalError, psycopg2.InterfaceError)


def parse_output_string(s: str) -> Dict[str, Any]:
    """
    将 "col1|col2\nval1|val2" 格式的字符串解析为结果集字典。
    格式与 format_result_set 的输出完全对应。
    """
    if not s or not s.strip():
        return {"columns": [], "rows": []}

    lines = [line.rstrip("\r") for line in s.strip().splitlines()]
    if not lines:
        return {"columns": [], "rows": []}

    columns = lines[0].split("|")
    rows = [line.split("|") for line in lines[1:]]
    return {"columns": columns, "rows": rows}


def compare_result_sets(actual: Dict[str, Any], expected: Dict[str, Any]) -> bool:
    """
    比较两个结果集字典，忽略列顺序、行顺序，保留重复行。
    """
    actual_cols = actual.get("columns", [])
    actual_rows = actual.get("rows", [])
    expected_cols = expected.get("columns", [])
    expected_rows = expected.get("rows", [])

    # 两个结果集都为空（例如 INSERT/UPDATE 等无返回值语句）
    if not actual_cols and not expected_cols:
        return True

    if len(actual_cols) != len(expected_cols) or set(actual_cols) != set(expected_cols):
        return False

    try:
        col_index = [expected_cols.index(c) for c in actual_cols]
    except ValueError:
        return False

    def process_row(row) -> tuple:
        return tuple("" if v is None else str(v) for v in row)

    actual_processed = [process_row(row) for row in actual_rows]
    expected_processed = [
        process_row(tuple(row[i] for i in col_index)) for row in expected_rows
    ]

    # 使用 Counter 比较多重集：保留重复行，且为 O(n)
    return Counter(actual_processed) == Counter(expected_processed)


def _split_statements(sql: Optional[str]) -> List[str]:
    """按分号拆分多条 SQL，忽略空语句与空白。"""
    return [stmt.strip() for stmt in (sql or "").split(";") if stmt.strip()]


def _connect(host: str, port: int, timeout: int):
    """创建到判题数据库的 psycopg2 连接。"""
    return psycopg2.connect(
        host=host, port=port, database=DB_NAME,
        user=DB_USER, password=DB_PASSWORD, connect_timeout=timeout,
    )


class MultiDbPool:
    """多个 judge-db 的连接池集合：按轮询把连接分片到不同实例。

    对外提供与 psycopg2 ThreadedConnectionPool 相同的
    ``getconn`` / ``putconn(conn, close=...)`` / ``closeall`` 接口，
    因此 ``_acquire_connection`` 与各调用方无需改动即可支持多实例。
    """

    def __init__(self, pools: List[Any]):
        self._pools = list(pools)
        self._lock = threading.Lock()
        self._owner: Dict[int, Any] = {}
        self._counter = 0

    def getconn(self):
        size = len(self._pools)
        with self._lock:
            start = self._counter
            self._counter = (self._counter + 1) % size
        # 从轮询起点开始，逐个尝试；某实例繁忙则试下一个
        for offset in range(size):
            pool = self._pools[(start + offset) % size]
            try:
                conn = pool.getconn()
            except PoolError:
                continue
            with self._lock:
                self._owner[id(conn)] = pool
            return conn
        raise PoolError("所有判题库连接池均繁忙")

    def putconn(self, conn, close: bool = False) -> None:
        with self._lock:
            pool = self._owner.pop(id(conn), None)
        if pool is None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 - 未知来源连接直接关闭
                pass
            return
        pool.putconn(conn, close=close)

    def closeall(self) -> None:
        for pool in self._pools:
            pool.closeall()


class SharedConnectionProvider:
    """默认模式：从共享 judge-db 连接池取连接。"""

    def acquire(self):
        return _acquire_connection()

    def release(self, conn, close: bool = False) -> None:
        db_pool.putconn(conn, close=close)


class ContainerConnectionProvider:
    """池模式：连接任务专属容器，每个用例独立连接、用完即关。"""

    def __init__(self, container):
        self._container = container

    def acquire(self):
        return psycopg2.connect(
            connect_timeout=DB_CONNECT_TIMEOUT, **self._container.connect_kwargs()
        )

    def release(self, conn, close: bool = False) -> None:
        try:
            conn.close()
        except Exception:  # noqa: BLE001 - 关闭失败忽略
            pass


class PoolExhaustedError(RuntimeError):
    """连接池在等待超时后仍无可用连接（服务过载，可稍后重试）。"""


def _acquire_connection(timeout: int = POOL_ACQUIRE_TIMEOUT):
    """从连接池获取连接；池耗尽时有限等待空闲连接，而不是立即失败。

    ``ThreadedConnectionPool.getconn`` 在达到 maxconn 时直接抛 ``PoolError`` 而非阻塞，
    高并发下会造成大量瞬时失败。这里改为短暂轮询，把「立即失败」变成「有限等待」，
    从而提升并发承载力；等待超过 ``timeout`` 仍未获取到连接则抛 ``PoolExhaustedError``。
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            return db_pool.getconn()
        except PoolError:
            if time.monotonic() >= deadline:
                raise PoolExhaustedError(
                    f"连接池繁忙，等待 {timeout}s 仍无空闲连接"
                ) from None
            time.sleep(POLL_ACQUIRE_INTERVAL)


def _fetch_result_set(cur) -> ResultSet:
    """读取当前游标的查询结果；无结果集（如 INSERT/UPDATE）时返回空结果集。

    统一 columns/rows 结构，供用例执行与多语句执行复用。
    """
    if not cur.description:
        return {"columns": [], "rows": []}
    return {
        "columns": [desc[0] for desc in cur.description],
        "rows": cur.fetchall(),
    }


def _execute_statements(cur, statements: List[str]) -> Optional[ResultSet]:
    """顺序执行多条 SQL，返回最后一条带结果集语句的结果（无则返回 None）。"""
    last_result: Optional[ResultSet] = None
    for stmt in statements:
        cur.execute(stmt)
        if cur.description:
            last_result = _fetch_result_set(cur)
    return last_result


@contextmanager
def _interruptible_wait() -> Iterator[threading.Event]:
    """等待就绪期间临时接管中断信号，让同步阻塞的启动流程能被 Ctrl+C 立即打断。

    uvicorn 在启动前会用「仅设置退出标志」的处理函数替换 SIGINT/SIGTERM（见其
    ``Server.capture_signals``），因此 ``wait_for_db`` 既收不到 ``KeyboardInterrupt``，
    又因同步阻塞占用了事件循环而无法响应退出标志，导致 Ctrl+C 看似无效。

    这里在等待期间临时包装信号处理：信号到来时先置位本地事件（让等待循环立刻结束），
    再链式调用原处理函数（保留 uvicorn 的优雅退出语义）；等待结束后恢复原处理函数。

    信号只能在主线程注册，故仅在主线程生效，其余情况退化为「仅按超时结束」。
    """
    stop = threading.Event()
    if threading.current_thread() is not threading.main_thread():
        yield stop
        return

    signals = [signal.SIGINT]
    sigbreak = getattr(signal, "SIGBREAK", None)  # Windows 下的 Ctrl+Break
    if sigbreak is not None:
        signals.append(sigbreak)

    previous = {sig: signal.getsignal(sig) for sig in signals}

    def _handle(signum, frame):
        stop.set()  # 先置位，让等待循环立刻结束
        handler = previous.get(signum)
        if callable(handler):
            handler(signum, frame)  # 链式调用原处理函数（如 uvicorn 的 handle_exit）

    try:
        for sig in signals:
            signal.signal(sig, _handle)
        yield stop
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def wait_for_db(host: str, port: int, timeout: int = DB_READY_TIMEOUT) -> None:
    """轮询等待判题数据库可连接（容器由 docker-compose 负责创建）。

    - 每轮在剩余时间内用 ``DB_CONNECT_TIMEOUT`` 建立一次连接，成功即关闭并返回；
    - 失败按 ``POLL_INTERVAL`` 重试，休眠与连接超时都不超过剩余时间，避免总耗时超出 ``timeout``；
    - 等待期间可被 Ctrl+C 立即中断（见 ``_interruptible_wait``）；
    - 超过 ``timeout`` 仍不可用则抛出 ``TimeoutError``，并带上尝试次数与最后一次错误。
    """
    logger.info("等待判题数据库 %s:%s 就绪（最长 %ss，可按 Ctrl+C 取消）", host, port, timeout)
    deadline = time.monotonic() + timeout
    attempts = 0
    last_err: Optional[BaseException] = None

    with _interruptible_wait() as interrupted:
        while True:
            if interrupted.is_set():
                logger.warning("等待判题数据库就绪被用户中断")
                raise KeyboardInterrupt("等待判题数据库就绪时被中断")

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            attempts += 1
            # libpq 的 connect_timeout 为整数秒且最小为 1，同时不超过剩余时间
            connect_timeout = max(1, min(DB_CONNECT_TIMEOUT, int(remaining)))
            try:
                # closing 保证连接一旦建立就被关闭，避免异常路径泄漏连接
                with closing(_connect(host, port, connect_timeout)):
                    pass
            except psycopg2.Error as exc:
                last_err = exc
                logger.debug("判题数据库尚未就绪（第 %s 次尝试）：%s", attempts, exc)
                # 用 Event.wait 代替 sleep：中断事件已置位时立即返回；休眠同样不超出剩余时间
                interrupted.wait(
                    min(POLL_INTERVAL, max(0.0, deadline - time.monotonic()))
                )
            else:
                elapsed = timeout - max(0.0, deadline - time.monotonic())
                logger.info("判题数据库 %s:%s 已就绪（用时 %.1fs，尝试 %s 次）",
                            host, port, elapsed, attempts)
                return

    raise TimeoutError(
        f"判题数据库连接超时（{timeout}s，尝试 {attempts} 次）: {last_err}"
    )


def _execute_case(cur, submitted_sql: str, idx: int, tc: TestCase) -> TestCaseResult:
    """在当前连接/事务内执行单个用例并比对结果（无需 SAVEPOINT）。

    每个用例使用独立连接与独立 schema，事务结束整体回滚，天然隔离；
    - SQL 层错误（语法、超时等）只影响当前用例；
    - 连接层错误向上抛，由调用方统一返回 ERROR。
    """
    try:
        _execute_statements(cur, _split_statements(tc.test_input))
        cur.execute(submitted_sql)
        result_dict = _fetch_result_set(cur)
        passed = compare_result_sets(result_dict, parse_output_string(tc.expected_output))
        return TestCaseResult(
            test_case_id=idx,
            passed=passed,
            actual_output=format_result_set(result_dict),
            error_message=None,
        )
    except QueryCanceled:
        # QueryCanceled 是 OperationalError 的子类，需先于连接层错误捕获
        return TestCaseResult(
            test_case_id=idx, passed=False, actual_output="", error_message="SQL执行超时",
        )
    except _CONNECTION_ERRORS:
        raise  # 连接层错误：交给调用方统一返回 ERROR
    except psycopg2.Error as exc:
        logger.exception("测试用例 %s 执行失败", idx)
        return TestCaseResult(
            test_case_id=idx, passed=False, actual_output="", error_message=str(exc),
        )


class _HardCancelTimer:
    """单个用例的 wall-clock 硬超时。

    到点后调用 ``conn.cancel()`` 请求服务端中断当前查询（覆盖
    ``statement_timeout`` 未覆盖的连接/协议层卡顿）。到点取消后，
    执行线程会收到 QueryCanceled，按「SQL 执行超时」处理。
    """

    def __init__(self, conn, timeout_seconds: float):
        self._conn = conn
        self._timeout = max(1.0, float(timeout_seconds))
        self._timer: Optional[threading.Timer] = None

    def start(self) -> None:
        self._timer = threading.Timer(self._timeout, self._fire)
        self._timer.daemon = True
        self._timer.start()

    def _fire(self) -> None:
        try:
            self._conn.cancel()
        except Exception:  # noqa: BLE001 - 取消失败只记录，不抛出
            logger.warning("硬超时取消查询失败", exc_info=True)

    def cancel(self) -> None:
        if self._timer is not None:
            self._timer.cancel()


def _run_single_case(
    request: JudgeRequest, idx: int, tc: TestCase, provider
) -> Tuple[Optional[TestCaseResult], Optional[str]]:
    """在独立连接 + 独立临时 schema 中执行单个用例，结束后整体回滚清空。

    独立 schema/连接使各用例可安全并行，且回滚即清理（即使进程崩溃也不会残留数据）。
    返回 ``(result, setup_error)``：建表阶段出错时返回 ``(None, 错误信息)``。
    """
    schema = sql.Identifier(f"judge_{uuid4().hex[:12]}")
    conn = provider.acquire()
    # 硬超时兜底：wall-clock 到点即向服务端发取消，避免查询卡死占用连接
    hard_cancel = _HardCancelTimer(conn, request.timeout + CASE_HARD_GRACE)
    hard_cancel.start()
    result: Optional[TestCaseResult] = None
    setup_error: Optional[str] = None
    try:
        conn.autocommit = False
        try:
            with conn.cursor() as cur:
                # SET LOCAL 仅作用于当前事务，回滚后自动失效，不会污染连接池中复用的连接
                timeout_ms = int(request.timeout) * 1000
                cur.execute(f"SET LOCAL statement_timeout = {timeout_ms}")
                # 持锁等待与空闲事务同样受限，避免长事务拖垮复用的连接
                cur.execute(f"SET LOCAL lock_timeout = {timeout_ms}")
                cur.execute(
                    f"SET LOCAL idle_in_transaction_session_timeout = {timeout_ms}"
                )
                cur.execute(sql.SQL("CREATE SCHEMA {}").format(schema))
                # search_path 只指向本用例的 schema，未限定名称的建表/查询不会落到 public
                cur.execute(sql.SQL("SET LOCAL search_path = {}").format(schema))
                try:
                    _execute_statements(cur, _split_statements(request.create_table_sql))
                except QueryCanceled:
                    setup_error = "建表语句执行超时"
                except _CONNECTION_ERRORS:
                    raise  # 连接层错误：交给调用方统一返回 ERROR
                except psycopg2.Error as exc:
                    setup_error = f"建表语句执行失败: {exc}"
                if setup_error is None:
                    result = _execute_case(cur, request.submitted_sql, idx, tc)
        finally:
            conn.rollback()  # 撤销 CREATE SCHEMA + 建表 + 数据，连接可干净复用
    except Exception:
        # 连接/事务异常：关闭该连接换新，避免把坏连接放回池中
        try:
            hard_cancel.cancel()
            provider.release(conn, close=True)
        except Exception:
            logger.exception("关闭异常连接失败")
        raise
    else:
        hard_cancel.cancel()
        provider.release(conn)
    return result, setup_error


def _run_judge_in_schema(
    request: JudgeRequest, provider
) -> Tuple[List[TestCaseResult], Optional[str]]:
    """每个用例在独立连接 + 独立临时 schema 中执行，可按 ``CASE_CONCURRENCY`` 并行。

    返回 (details, fatal_error)：
    - 建表等导致所有用例都无法执行的 SQL 层错误，作为 fatal_error 返回；
    - 连接/进程层错误向上抛，由调用方统一返回 ERROR。
    """
    cases = list(enumerate(request.test_cases))
    workers = min(CASE_CONCURRENCY, len(cases))
    if workers > 1:
        # 用例间相互独立（各用各的 schema/连接），并行执行以降低整体响应时间
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="judge-case") as pool:
            outcomes = list(
                pool.map(lambda item: _run_single_case(request, *item, provider), cases)
            )
    else:
        outcomes = [_run_single_case(request, idx, tc, provider) for idx, tc in cases]

    # create_table_sql 对全部用例一致：若全部在建表阶段失败，视为致命错误
    if all(setup_error is not None for _, setup_error in outcomes):
        return [], outcomes[0][1]

    details: List[TestCaseResult] = []
    for (idx, _tc), (result, setup_error) in zip(cases, outcomes):
        if result is None:  # 个别用例建表失败（非全局）：按失败用例返回
            result = TestCaseResult(
                test_case_id=idx, passed=False, actual_output="", error_message=setup_error,
            )
        details.append(result)
    return details, None


def _friendly_sql_error(exc: psycopg2.Error) -> str:
    """把数据库异常转成一行可读原因（附带 SQLSTATE，便于教师排错）。"""
    code = getattr(exc, 'pgcode', None)
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else 'SQL 执行失败'
    return f"SQL 执行失败（{code}）: {message}" if code else f"SQL 执行失败: {message}"


def _judge_schema_case(
    cur,
    schema_name: str,
    submitted_sql: str,
    idx: int,
    tc: TestCase,
    strictness: str = "subset",
    compare_names: bool = False,
) -> TestCaseResult:
    """在已建好的临时 schema 中执行学生 DDL，再做结构 diff 与行为探针。"""
    if not tc.expected_schema and not tc.probes:
        return TestCaseResult(
            test_case_id=idx, passed=False, actual_output="",
            error_message="该用例未配置期望结构或探针",
        )

    try:
        _execute_statements(cur, _split_statements(submitted_sql))
    except QueryCanceled:
        return TestCaseResult(
            test_case_id=idx, passed=False, actual_output="", error_message="SQL执行超时",
        )
    except _CONNECTION_ERRORS:
        raise  # 连接层错误：交给调用方统一返回 ERROR
    except psycopg2.Error as exc:
        return TestCaseResult(
            test_case_id=idx, passed=False, actual_output="",
            error_message=_friendly_sql_error(exc),
        )

    actual = introspect_schema(cur, schema_name)
    checks: List[Dict[str, Any]] = []
    if tc.expected_schema:
        checks.extend(
            diff_schema(tc.expected_schema, actual, strictness, compare_names)
        )
    checks.extend(run_probes(cur, [probe.model_dump() for probe in tc.probes]))

    failures = [
        f"{check['name']}：{check['detail']}" if check['detail'] else check['name']
        for check in checks
        if not check['passed']
    ]
    return TestCaseResult(
        test_case_id=idx,
        passed=bool(checks) and all(check['passed'] for check in checks),
        actual_output=render_snapshot(actual),
        error_message='；'.join(failures[:5]),
        checks=checks,
    )


def _run_single_schema_case(
    request: JudgeRequest, idx: int, tc: TestCase, provider
) -> Tuple[Optional[TestCaseResult], Optional[str]]:
    """schema 模式的单用例执行：临时 schema + 前置语句 + 学生 DDL + diff/探针。"""
    schema_name = f"judge_{uuid4().hex[:12]}"
    schema = sql.Identifier(schema_name)
    conn = provider.acquire()
    hard_cancel = _HardCancelTimer(conn, request.timeout + CASE_HARD_GRACE)
    hard_cancel.start()
    result: Optional[TestCaseResult] = None
    setup_error: Optional[str] = None
    try:
        conn.autocommit = False
        try:
            with conn.cursor() as cur:
                timeout_ms = int(request.timeout) * 1000
                cur.execute(f"SET LOCAL statement_timeout = {timeout_ms}")
                cur.execute(f"SET LOCAL lock_timeout = {timeout_ms}")
                cur.execute(
                    f"SET LOCAL idle_in_transaction_session_timeout = {timeout_ms}"
                )
                cur.execute(sql.SQL("CREATE SCHEMA {}").format(schema))
                cur.execute(sql.SQL("SET LOCAL search_path = {}").format(schema))

                # test_input 在 schema 模式下作为可选前置语句（ALTER 类题目使用）
                try:
                    _execute_statements(cur, _split_statements(tc.test_input))
                except QueryCanceled:
                    setup_error = "前置语句执行超时"
                except _CONNECTION_ERRORS:
                    raise
                except psycopg2.Error as exc:
                    setup_error = _friendly_sql_error(exc)

                if setup_error is None:
                    result = _judge_schema_case(
                        cur, schema_name, request.submitted_sql, idx, tc,
                        request.strictness, request.compare_names,
                    )
        finally:
            conn.rollback()  # 撤销 CREATE SCHEMA 与全部 DDL，连接可干净复用
    except Exception:
        try:
            hard_cancel.cancel()
            provider.release(conn, close=True)
        except Exception:
            logger.exception("关闭异常连接失败")
        raise
    else:
        hard_cancel.cancel()
        provider.release(conn)
    return result, setup_error


def _run_schema_judge_in_schema(
    request: JudgeRequest, provider
) -> Tuple[List[TestCaseResult], Optional[str]]:
    """schema 模式：每个用例独立连接 + 独立临时 schema，可按并发度并行。"""
    cases = list(enumerate(request.test_cases))
    workers = min(CASE_CONCURRENCY, len(cases))
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="judge-schema") as pool:
            outcomes = list(
                pool.map(
                    lambda item: _run_single_schema_case(request, *item, provider), cases
                )
            )
    else:
        outcomes = [
            _run_single_schema_case(request, idx, tc, provider) for idx, tc in cases
        ]

    # 前置语句对全部用例都失败：视为致命错误（与 query 模式的建表失败同语义）
    if all(setup_error is not None for _, setup_error in outcomes):
        return [], outcomes[0][1]

    details: List[TestCaseResult] = []
    for (idx, _tc), (result, setup_error) in zip(cases, outcomes):
        if result is None:
            result = TestCaseResult(
                test_case_id=idx, passed=False, actual_output="", error_message=setup_error,
            )
        details.append(result)
    return details, None


def _run_judge(
    request: JudgeRequest,
) -> Tuple[List[TestCaseResult], Optional[str]]:
    """按是否启用容器池选择执行后端。

    - 未启用池：走共享 judge-db（默认，行为不变）；
    - 启用池：取一个预热容器执行，正常则清理复用，异常/超时则 kill 补建。
    """
    runner = _run_schema_judge_in_schema if request.mode == "schema" else _run_judge_in_schema
    if container_pool is None:
        return runner(request, SharedConnectionProvider())

    try:
        container = container_pool.acquire()
    except PoolUnavailableError as exc:
        # 池繁忙/不可用：按「服务繁忙」返回，与连接池耗尽同语义
        raise PoolExhaustedError(str(exc)) from None

    healthy = True
    try:
        return runner(request, ContainerConnectionProvider(container))
    except Exception:
        # 任务异常/超时：容器可能处于不确定状态，交由池 kill 并补建
        healthy = False
        raise
    finally:
        container_pool.release(container, healthy=healthy)


def format_result_set(result: ResultSet) -> str:
    """将结果集字典格式化为字符串，便于展示"""
    columns = result.get("columns", [])
    rows = result.get("rows", [])
    if not columns:
        return ""
    header = "|".join(str(c) for c in columns)
    lines = [header]
    for row in rows:
        line = "|".join(str(v) if v is not None else "" for v in row)
        lines.append(line)
    return "\n".join(lines)


def _error_response(error_message: Optional[str] = None) -> JudgeResponse:
    """构造统一的判题错误响应。"""
    return JudgeResponse(
        passed=False,
        execution_status="ERROR",
        score=0,
        details=[],
        error_message=error_message,
    )


@app.post("/judge", response_model=JudgeResponse)
def judge(request: JudgeRequest) -> JudgeResponse:
    # 同步 def：内部为阻塞式 I/O（psycopg2），由 FastAPI 放入线程池运行，避免阻塞事件循环
    try:
        details, fatal_error = _run_judge(request)
        if fatal_error:
            # 建表等 SQL 层致命错误：附带原因返回并记录日志，便于上层定位（原先该信息被丢弃）
            logger.warning("判题未能执行: %s", fatal_error)
            return _error_response(fatal_error)

        total = len(request.test_cases)
        passed_count = sum(d.passed for d in details)
        all_passed = passed_count == total

        return JudgeResponse(
            passed=all_passed,
            execution_status="ACCEPTED" if all_passed else "WRONG_ANSWER",
            score=passed_count * 100 // total,
            details=details,
        )
    except PoolExhaustedError as exc:
        # 连接池过载：返回可重试的繁忙状态，避免把瞬时高并发当作崩溃
        logger.warning("判题服务繁忙: %s", exc)
        return _error_response(str(exc))
    except Exception:
        logger.exception("判题失败")
        return _error_response()


@app.get("/pool")
def pool_status():
    """容器池状态（监控：容器复用率 / 就绪数）。未启用时返回 enabled=False。"""
    if container_pool is None:
        return {"enabled": False}
    return {"enabled": True, **container_pool.stats()}


class IntrospectRequest(BaseModel):
    sql: str = Field(..., min_length=1)
    setup_sql: Optional[str] = ""
    timeout: int = Field(default=SQL_TIMEOUT, ge=1, le=MAX_TIMEOUT)
    # 是否基于参考结构自动生成并验证行为探针（教师端出题用）
    suggest_probes: bool = False


class IntrospectResponse(BaseModel):
    # 直接返回可直接存入 TestCase.expected_schema 的快照结构
    expected_schema: Optional[Dict[str, Any]] = None
    suggested_probes: List[Dict[str, Any]] = []
    error_message: Optional[str] = None


@app.post("/introspect", response_model=IntrospectResponse)
def introspect(request: IntrospectRequest):
    """把参考 DDL 跑一遍并返回规范化结构快照（教师端生成期望结构用）。

    与判题一样在临时 schema 中执行并回滚，只读取结构、不落任何数据。
    """
    provider = SharedConnectionProvider()
    schema_name = f"judge_ref_{uuid4().hex[:8]}"
    conn = None
    healthy = True
    try:
        conn = provider.acquire()
        conn.autocommit = False
        with conn.cursor() as cur:
            timeout_ms = int(request.timeout) * 1000
            cur.execute(f"SET LOCAL statement_timeout = {timeout_ms}")
            cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name)))
            cur.execute(
                sql.SQL("SET LOCAL search_path = {}").format(sql.Identifier(schema_name))
            )
            _execute_statements(
                cur, _split_statements(request.setup_sql or "")
            )
            _execute_statements(cur, _split_statements(request.sql))
            snapshot = introspect_schema(cur, schema_name)
            probes = suggest_probes(cur, snapshot) if request.suggest_probes else []
        return IntrospectResponse(expected_schema=snapshot, suggested_probes=probes)
    except QueryCanceled:
        return IntrospectResponse(error_message="SQL执行超时")
    except _CONNECTION_ERRORS:
        healthy = False
        raise
    except psycopg2.Error as exc:
        return IntrospectResponse(error_message=_friendly_sql_error(exc))
    except PoolExhaustedError as exc:
        return IntrospectResponse(error_message=str(exc))
    finally:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001 - 连接已坏时直接丢弃
                healthy = False
            provider.release(conn, close=not healthy)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
