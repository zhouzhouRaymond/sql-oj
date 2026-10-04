"""SQL 判题容器预热池。

真正的「按任务拉起 / 复用 / 回收」容器池：

- 启动时预拉起 ``JUDGE_POOL_SIZE`` 个空闲 Postgres 容器作为预热池；
- 每个判题任务从池中取一个容器执行，执行完清理环境后放回复用；
- 超时、异常、危险操作直接把容器 kill 掉并补建，不等待自然结束；
- 数据目录挂 tmpfs（不持久化），CPU / 内存 / IO / 进程数由 Docker cgroup 限制。

通过环境变量开启（``JUDGE_POOL_SIZE > 0``）；未开启时判题服务沿用共享
``judge-db`` 容器，行为与之前一致。

实现说明：通过 Docker Python SDK（``docker`` 包）访问 Docker，而不是调用
``docker`` 命令行——判题服务镜像基于 python:3.12-slim，没有 docker CLI；
SDK 只需挂载 ``/var/run/docker.sock`` 即可。

若判题服务本身运行在容器里，需要在 compose 里挂载宿主机的 Docker socket
（见 docker-compose.pool.yml），并设置 ``JUDGE_POOL_HOST``/``JUDGE_POOL_BIND``
让容器能连到池容器发布的端口。
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Optional

import psycopg2
from psycopg2 import sql

logger = logging.getLogger("judge_service.pool")


def _env_str(key: str, default: str) -> str:
    value = os.environ.get(key)
    return default if value is None or value == "" else value


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


POOL_SIZE = _env_int("JUDGE_POOL_SIZE", 0)          # 0 = 关闭容器池（沿用共享库）
POOL_MAX = max(POOL_SIZE, _env_int("JUDGE_POOL_MAX", POOL_SIZE))
POOL_IMAGE = _env_str("JUDGE_POOL_IMAGE", "postgres:15-alpine")
POOL_DB = _env_str("JUDGE_POOL_DB", "judge_db")
POOL_USER = _env_str("JUDGE_POOL_USER", "judge_user")
POOL_PASSWORD = _env_str("JUDGE_POOL_PASSWORD", "judge_pass")
POOL_MEMORY = _env_str("JUDGE_POOL_MEMORY", "512m")
POOL_CPUS = _env_str("JUDGE_POOL_CPUS", "1.0")
POOL_PIDS = _env_str("JUDGE_POOL_PIDS", "128")
POOL_TMPFS_SIZE = _env_str("JUDGE_POOL_TMPFS_SIZE", "256m")
POOL_BIND = _env_str("JUDGE_POOL_BIND", "127.0.0.1")   # 容器端口发布到哪个宿主地址
POOL_HOST = _env_str("JUDGE_POOL_HOST", "127.0.0.1")   # 连池容器时用的宿主名
POOL_ACQUIRE_TIMEOUT = _env_int("JUDGE_POOL_ACQUIRE_TIMEOUT", 10)
POOL_READY_TIMEOUT = _env_int("JUDGE_POOL_READY_TIMEOUT", 60)
CONTAINER_PREFIX = _env_str("JUDGE_POOL_PREFIX", "sql-oj-judge-pool")


class PoolUnavailableError(RuntimeError):
    """容器池不可用（Docker 不可达 / 启动失败 / 池繁忙超时）。"""


@dataclass
class PooledContainer:
    name: str
    container_id: str
    host: str
    port: int
    reused: int = 0

    def connect_kwargs(self) -> Dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "dbname": POOL_DB,
            "user": POOL_USER,
            "password": POOL_PASSWORD,
        }


_client = None
_client_lock = threading.Lock()


def _docker_client():
    """懒加载 Docker SDK 客户端（连接宿主机 Docker socket）。"""
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        try:
            import docker
        except ImportError as exc:
            raise PoolUnavailableError(
                "容器池需要 Docker Python SDK（pip install docker）"
            ) from exc
        try:
            client = docker.from_env()
            client.ping()
        except Exception as exc:  # noqa: BLE001 - 连接失败统一报池不可用
            raise PoolUnavailableError(f"无法连接 Docker：{exc}") from exc
        _client = client
        return _client


class ContainerPool:
    """Postgres 容器预热池：acquire -> 执行 -> release(清理/复用)。"""

    def __init__(
        self,
        size: int = POOL_SIZE,
        max_size: int = POOL_MAX,
        acquire_timeout: int = POOL_ACQUIRE_TIMEOUT,
    ):
        self._size = max(0, size)
        self._max_size = max(self._size, max_size)
        self._acquire_timeout = acquire_timeout
        self._ready: Deque[PooledContainer] = deque()
        self._all: List[PooledContainer] = []
        self._creating = 0
        self._created = 0
        self._reused = 0
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---- 生命周期 ----------------------------------------------------
    def start(self) -> None:
        if self._size <= 0:
            return
        logger.info("启动判题容器池：预热 %s 个（上限 %s，镜像 %s）",
                    self._size, self._max_size, POOL_IMAGE)
        self._thread = threading.Thread(
            target=self._replenish_loop, name="judge-pool-replenish", daemon=True
        )
        self._thread.start()
        with self._cond:
            self._cond.wait_for(
                lambda: len(self._ready) >= self._size or self._stop.is_set(),
                timeout=POOL_READY_TIMEOUT + 10,
            )
        logger.info("判题容器池就绪：ready=%s", len(self._ready))

    def stop(self) -> None:
        self._stop.set()
        with self._cond:
            containers = list(self._all)
            self._all.clear()
            self._ready.clear()
            self._cond.notify_all()
        for container in containers:
            self._destroy(container.name)
        if self._thread is not None:
            self._thread.join(timeout=5)

    # ---- 取用 / 归还 -------------------------------------------------
    def acquire(self, timeout: Optional[float] = None) -> PooledContainer:
        """取一个空闲容器；池满时等待，超时抛 :class:`PoolUnavailableError`。"""
        deadline = time.monotonic() + (self._acquire_timeout if timeout is None else timeout)
        with self._cond:
            while True:
                if self._ready:
                    return self._ready.popleft()
                if len(self._all) + self._creating < self._max_size:
                    self._creating += 1
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PoolUnavailableError("判题容器池繁忙，稍后重试")
                self._cond.wait(remaining)

        # 锁外创建，避免阻塞其它 acquire
        try:
            container = self._create()
        except Exception:
            with self._cond:
                self._creating -= 1
                self._cond.notify()
            raise
        else:
            with self._cond:
                self._creating -= 1
                self._all.append(container)
                self._cond.notify_all()
            return container

    def release(self, container: PooledContainer, healthy: bool = True) -> None:
        """归还容器：健康则清理复用，不健康则 kill 并补建。"""
        if self._stop.is_set():
            self._destroy(container.name)
            return
        if not healthy:
            self._replace(container)
            return
        try:
            self._reset(container)
        except Exception:
            logger.warning("容器 %s 清理失败，销毁重建", container.name, exc_info=True)
            self._replace(container)
            return
        container.reused += 1
        with self._cond:
            self._reused += 1
            self._ready.append(container)
            self._cond.notify_all()

    def stats(self) -> Dict[str, Any]:
        """池指标（监控：容器复用率）。"""
        with self._cond:
            created, reused = self._created, self._reused
            ready, total = len(self._ready), len(self._all)
        denominator = created + reused
        return {
            "created": created,
            "reused": reused,
            "ready": ready,
            "total": total,
            "reuse_rate": round(reused / denominator, 3) if denominator else 0.0,
        }

    # ---- 内部实现 ----------------------------------------------------
    def _replace(self, container: PooledContainer) -> None:
        with self._cond:
            if container in self._all:
                self._all.remove(container)
            if container in self._ready:
                self._ready.remove(container)
            self._cond.notify_all()
        self._destroy(container.name)

    def _replenish_loop(self) -> None:
        while not self._stop.is_set():
            with self._cond:
                deficit = self._size - len(self._all) - self._creating
            if deficit > 0:
                self._create_and_add()
            self._stop.wait(1.0)

    def _create_and_add(self) -> Optional[PooledContainer]:
        with self._cond:
            self._creating += 1
        try:
            container = self._create()
        except Exception:
            logger.exception("补建判题容器失败")
            return None
        finally:
            with self._cond:
                self._creating -= 1
        with self._cond:
            self._all.append(container)
            self._ready.append(container)
            self._cond.notify_all()
        return container

    def _create(self) -> PooledContainer:
        client = _docker_client()
        name = f"{CONTAINER_PREFIX}-{uuid.uuid4().hex[:8]}"
        try:
            docker_container = client.containers.run(
                POOL_IMAGE,
                detach=True,
                name=name,
                # 数据目录 tmpfs：不持久化，容器重建即清空
                tmpfs={
                    "/var/lib/postgresql/data": f"rw,noexec,nosuid,size={POOL_TMPFS_SIZE}",
                    "/var/run/postgresql": "rw,noexec,nosuid,size=16m",
                    "/tmp": "rw,noexec,nosuid,size=64m",
                    "/dev/shm": "rw,noexec,nosuid,size=64m",
                },
                # cgroup 资源上限：内存 / CPU / 进程数
                mem_limit=POOL_MEMORY,
                nano_cpus=int(float(POOL_CPUS) * 1_000_000_000),
                pids_limit=int(POOL_PIDS),
                cap_drop=["SYS_ADMIN", "NET_RAW", "SYS_MODULE"],
                security_opt=["no-new-privileges"],
                environment={
                    "POSTGRES_DB": POOL_DB,
                    "POSTGRES_USER": POOL_USER,
                    "POSTGRES_PASSWORD": POOL_PASSWORD,
                },
                # 发布到 POOL_BIND 的随机端口（容器内用 host.docker.internal 访问）
                ports={"5432/tcp": (POOL_BIND, None)},
            )
        except Exception as exc:  # noqa: BLE001 - 统一转成池不可用
            raise PoolUnavailableError(f"启动判题容器失败：{exc}") from exc

        self._created += 1
        try:
            port = self._wait_ready(docker_container)
        except Exception:
            self._destroy(name)
            raise
        logger.info("判题容器就绪：%s (%s:%s)", name, POOL_HOST, port)
        return PooledContainer(
            name=name, container_id=docker_container.id[:12], host=POOL_HOST, port=port,
        )

    def _wait_ready(self, docker_container) -> int:
        deadline = time.monotonic() + POOL_READY_TIMEOUT
        while True:
            port = self._host_port(docker_container)
            # 注意：官方 postgres 镜像初始化期间会临时启动再重启，单靠
            # pg_isready 可能在重启窗口误判就绪；这里以真实连接为准。
            if port is not None and self._can_connect(port):
                return port
            if time.monotonic() >= deadline:
                raise PoolUnavailableError(
                    f"判题容器 {docker_container.name} 就绪超时"
                )
            time.sleep(0.5)

    @staticmethod
    def _host_port(docker_container) -> Optional[int]:
        """读取容器 5432 映射到的宿主机端口。"""
        try:
            docker_container.reload()
            bindings = (
                docker_container.attrs["NetworkSettings"]["Ports"].get("5432/tcp")
                or []
            )
        except Exception:  # noqa: BLE001
            return None
        for binding in bindings:
            host_port = str(binding.get("HostPort") or "")
            if host_port.isdigit():
                return int(host_port)
        return None

    @staticmethod
    def _can_connect(port: int) -> bool:
        """用真实客户端连接确认容器可服务（避开 init 的重启窗口）。"""
        try:
            conn = psycopg2.connect(
                host=POOL_HOST, port=port, dbname=POOL_DB,
                user=POOL_USER, password=POOL_PASSWORD, connect_timeout=3,
            )
        except Exception:  # noqa: BLE001 - 未就绪时任何异常都视为不可用
            return False
        conn.close()
        return True

    @staticmethod
    def _reset(container: PooledContainer) -> None:
        """清理容器环境：断开残留连接、删除残留临时 schema（正常已随事务回滚）。"""
        conn = psycopg2.connect(connect_timeout=5, **container.connect_kwargs())
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    [POOL_DB],
                )
                cur.execute(
                    "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'judge\\_%'"
                )
                for (namespace,) in cur.fetchall():
                    cur.execute(
                        sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                            sql.Identifier(namespace)
                        )
                    )
        finally:
            conn.close()

    @staticmethod
    def _destroy(name: str) -> None:
        try:
            import docker
        except ImportError:
            return
        try:
            _docker_client().containers.get(name).remove(force=True)
        except docker.errors.NotFound:
            return
        except Exception:  # noqa: BLE001 - 清理失败只记录
            logger.warning("销毁判题容器 %s 失败", name, exc_info=True)


# 进程内单例：仅当 JUDGE_POOL_SIZE>0 时启用
container_pool: Optional[ContainerPool] = (
    ContainerPool() if POOL_SIZE > 0 else None
)
