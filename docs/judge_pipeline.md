# 异步判题链路：硬性约束落地与压测指标清单

本文对应当前实现的「异步判题 + 缓存 + 限流 + 熔断 + 异步批量回写」改造，
逐条说明硬性约束落在哪个文件、如何验证，并给出上线压测必须上报的指标项。

---

## 1. 异步判题链路

```
用户提交 SQL
  → Django 校验（apps/submissions/views.py::submit）
  → 落库一条 PENDING 提交（只写一条）
  → 入进程内判题队列（apps/submissions/judging.py）
  → 判题 Worker 消费，调用 judge-service（db 容器内执行用例）
  → 结果交给异步批量写线程（apps/submissions/result_writer.py）
  → 前端轮询 GET /api/submissions/{id}/ 直到状态非 PENDING
```

- 提交接口立即返回 **202 + submission_id**，绝不等待容器执行完毕。
- 状态机：`PENDING` → `ACCEPTED` / `WRONG_ANSWER` / `ERROR` / `TIMEOUT`。
- 进程重启会丢失队列中的任务（提交停留在 `PENDING`），可用
  `python manage.py requeue_pending` 重新入队。

## 2. 硬性约束对照表

| 硬性约束 | 落地位置 | 说明 |
|---|---|---|
| 新接口必须异步轮询 | `apps/submissions/views.py`、`apps/exams/views.py` | 提交接口 202 + `submission_id`，前端轮询详情；无同步等待容器的接口 |
| SQL 执行路径硬超时 | `judge_service/judge_service_new.py`、`apps/submissions/judge.py` | `statement_timeout` + `lock_timeout` + `idle_in_transaction_session_timeout` + wall-clock `_HardCancelTimer`；HTTP 侧 `JUDGE_HTTP_TIMEOUT` 兜底 |
| cgroup 资源上限（CPU/内存/IO/执行时间） | `docker-compose.yml` | `judge-db`：mem 1g / cpu 2 核 / pids 64 / tmpfs（IO 与容量上限）；`judge-service`：mem 512m / cpu 1 核 / pids 256；执行时间见上一行 |
| 缓存键含题目 ID + SQL 规范化 + 用例 | `apps/submissions/normalization.py`、`judge_cache.py` | 键 = hash(题目 ID || `normalize_sql(sql)` || 用例指纹 || 环境指纹) |
| 写库异步批量、统计延迟聚合 | `apps/submissions/result_writer.py` | 判题结果进内存缓冲，后台线程按间隔/批量 `bulk_update`；主流程不等待 UPDATE |
| 容器无状态、不持久化、每用例临时数据 | `docker-compose.yml`、`judge_service/container_pool.py`、`judge_service_new.py` | 池容器数据目录挂 tmpfs 不落盘；每个用例独立临时 schema，事务结束整体回滚清理；容器按任务拉起/回收（见第 6 节） |

### 2.1 SQL 规范化

`normalize_sql()` 只做**语义等价**改写：去注释、压缩多余空白、关键字大写；
字符串字面量原样保留（注释删除后不会把相邻 token 粘连）。因此
`SELECT a FROM t` 与 `select   a   from t` 命中同一缓存键，而
`SELECT 'a b'` 与 `SELECT 'a  b'` 仍是不同的键。

### 2.2 结果缓存

- 只缓存确定性结果（`ACCEPTED` / `WRONG_ANSWER`）；判题侧的瞬时 `ERROR`
  （连接池耗尽、DB 抖动）不缓存，避免相同提交在 TTL 内持续拿到旧错误。
- 默认有效期 `JUDGE_RESULT_CACHE_TTL=3600` 秒，<=0 关闭。
- 缓存后端默认进程内 LocMem；配置 `REDIS_URL` 后切换到 Redis，跨 worker 共享。
- 命中率由 `apps/submissions/judge_cache.py` 的 `cache_stats()` 给出
  （`hit_rate = hits / (hits + misses)`，计数器按进程统计；`reset_cache_stats()`
  可重置统计窗口）。测试见 `apps/submissions/test_cache_hit_rate.py`：
  10 次相同提交只真正判题 1 次、命中率 0.9；5 条 SQL 各重复 20 次的混合负载命中率 0.95。

### 2.3 幂等 / 限流 / 熔断

- **幂等**（`apps/submissions/idempotency.py`）：以「学生 + 题目 + 考试 +
  SQL 规范化」为维度，窗口 `JUDGE_IDEMPOTENCY_TTL`（默认 30s）内复用既有提交，
  相同提交不重复创建判题任务。
- **限流**（`apps/users/throttles.py` + `sql_oj/settings.py`）：提交走三级限流，
  速率可调 —— `THROTTLE_SUBMIT_USER`（默认 20/min）、
  `THROTTLE_SUBMIT_QUESTION`（默认 60/min）、`THROTTLE_SUBMIT_GLOBAL`
  （默认 600/min）。
- **背压**：判题队列上限 `JUDGE_QUEUE_SIZE`（默认 200），满时返回 503。
- **熔断**（`apps/submissions/circuit_breaker.py`）：判题服务连续失败
  `JUDGE_BREAKER_THRESHOLD`（默认 5）次后 OPEN `JUDGE_BREAKER_COOLDOWN`
  （默认 10s），期间新任务快速失败，冷却后放行探测。

## 3. 压测指标项清单（变更必附）

上线压测时**必须**同时上报下列指标；使用 `judge_service/load_test.py` 产出
QPS / 延迟 / 失败率，容器复用率与资源水位由 `docker stats` / compose 采集。

| 指标 | 口径 | 采集方式 |
|---|---|---|
| 提交 QPS | 稳态吞吐（req/s），并标注并发档位 | `load_test.py --mode sustained --concurrency N --duration 15` 的 `req/s` |
| P99 判题耗时 | 提交经异步链路到结果可见的端到端耗时（含排队） | 轮询 `GET /api/submissions/{id}/` 计时统计 p50/p95/p99；或 `load_test.py` 的 p99（判题服务侧） |
| 队列堆积量 | 待判题队列长度峰值 / 稳态 | `apps.submissions.judging.queue_depth()`（可打点到监控） |
| 容器复用率 | 复用执行次数 / (复用 + 新建)；启用容器池后由池统计给出 | `GET http://<judge-service>/pool` 的 `reuse_rate` / `reused` / `created` |
| 失败率 | 非判题结果响应占比（HTTP 错误 / `ERROR` / 客户端失败） | `load_test.py` 输出的 `non-judge responses` 与状态分布 |
| 缓存命中率 | 命中结果缓存的提交数 / 总提交数 | `apps.submissions.judge_cache.cache_stats()` 的 `hits` / `misses` / `hit_rate` |
| 数据库写入延迟 | 结果从产生到落库的批量刷写延迟 | `JUDGE_RESULT_FLUSH_INTERVAL` 与写线程耗时 |
| 单节点 CPU/内存/IO | 判题库与判题服务容器水位 | `docker stats`，对照 cgroup 上限 |

### 3.1 复现命令

```bash
# 判题服务侧吞吐 / 延迟 / 失败率（ramp 阶梯）
python judge_service/load_test.py

# 固定并发持续压 15 秒并导出 JSON
python judge_service/load_test.py --mode sustained --concurrency 32 --duration 15 --json result.json

# CPU 型重负载
python judge_service/load_test.py --heavy

# 容器水位（另开终端）
docker stats sql-oj-judge-db sql-oj-judge-service
```

> 判题服务在 compose 网络内时，从容器内压测可避免宿主机端口转发的客户端瓶颈：
> `docker compose exec -T backend python - --url http://judge-service:8080/judge < judge_service/load_test.py`

## 4. PR 代码审查检查清单

- [ ] 新接口是否返回 `submission_id` 并走异步链路（202 + 轮询）？
- [ ] SQL 执行路径是否设置了硬超时和资源上限？
- [ ] 缓存键是否包含所有必要维度（题目 ID、SQL 规范化、用例版本、DB/环境指纹）？
- [ ] 数据库写入是否异步化 / 批量？
- [ ] 是否有幂等校验防止重复提交？
- [ ] 容器是否无状态设计（tmpfs + 临时 schema + 事务回滚清理）？
- [ ] 是否有限流 / 熔断保护？
- [ ] 是否附带本节压测指标数据（QPS / P99 / 队列堆积 / 容器复用率 / 失败率）？

## 5. 关键配置项速查

| 环境变量 | 默认 | 作用 |
|---|---|---|
| `REDIS_URL` | 空 | 配置后结果缓存 / 熔断 / 限流跨进程共享 |
| `JUDGE_RESULT_CACHE_TTL` | 3600 | 结果缓存有效期（秒），<=0 关闭 |
| `JUDGE_IDEMPOTENCY_TTL` | 30 | 提交幂等去重窗口（秒） |
| `JUDGE_RESULT_FLUSH_INTERVAL` | 0.2 | 结果批量回写间隔（秒） |
| `JUDGE_RESULT_FLUSH_BATCH` | 100 | 结果批量回写批量阈值（条） |
| `JUDGE_WORKERS` / `JUDGE_QUEUE_SIZE` | 4 / 200 | 判题工作线程数 / 队列上限 |
| `JUDGE_BREAKER_THRESHOLD` / `JUDGE_BREAKER_COOLDOWN` | 5 / 10 | 熔断阈值（连续失败）/ 冷却秒数 |
| `THROTTLE_SUBMIT_USER` / `THROTTLE_SUBMIT_QUESTION` / `THROTTLE_SUBMIT_GLOBAL` | 20/min / 60/min / 600/min | 三级提交限流速率 |
| `JUDGE_HTTP_TIMEOUT` / `JUDGE_MAX_SQL_TIMEOUT` | 35 / 60 | 判题 HTTP 硬超时 / 单条 SQL 上限（秒） |
| `JUDGE_CASE_HARD_GRACE` | 5 | 单用例 wall-clock 硬超时宽限（秒） |
| `JUDGE_QUEUE_BACKEND` | auto | 判题队列后端：`auto`（有 Redis URL 用 redis，否则 local）/ `local` / `redis` |
| `JUDGE_QUEUE_REDIS_URL` / `REDIS_URL` | 空 | Redis 连接串（外部队列 + 跨进程缓存） |
| `JUDGE_QUEUE_VISIBILITY_TIMEOUT` | 120 | inflight 任务可见性超时（秒），超时自动回收重入队 |
| `JUDGE_QUESTION_CACHE_TTL` | 300 | 题目判题元数据（用例/建表语句）缓存有效期（秒） |
| `JUDGE_POOL_SIZE` | 0 | 判题容器预热池大小，0=关闭（沿用共享 judge-db） |
| `JUDGE_POOL_MAX` | =SIZE | 池容器上限 |
| `JUDGE_POOL_MEMORY` / `JUDGE_POOL_CPUS` / `JUDGE_POOL_PIDS` | 512m / 1.0 / 128 | 池容器 cgroup 资源上限 |
| `JUDGE_POOL_HOST` / `JUDGE_POOL_BIND` | 127.0.0.1 / 127.0.0.1 | 连接池容器的宿主名 / 端口发布绑定地址 |
| `JUDGE_DB_TARGETS` | 空（回退单个 `JUDGE_DB_HOST:JUDGE_DB_PORT`） | 多 judge-db 实例列表（逗号分隔 `host:port`），judge-service 按连接分片 |
| `JUDGE_UVICORN_WORKERS` | 4 | judge-service 的 uvicorn 进程数（每进程独立 GIL/线程池）；容器池模式下必须为 1 |
| `JUDGE_DB_POOL_MAX` / `JUDGE_DB_POOL_MIN` | 20 / 20 | **每个 worker、每个判题库实例**的连接池大小（多 worker/多实例时需相应调小） |

---

## 6. 容器池 / 消息队列 / 题目缓存（增强）

### 6.1 容器预热池（`judge_service/container_pool.py`）

- 通过 `JUDGE_POOL_SIZE > 0` 启用：judge-service 启动时预拉起该数量的空闲
  Postgres 容器，任务到来即取即用；
- 任务执行完清理环境（断开残留连接 + 删除残留 `judge_*` schema）后放回复用；
- 超时 / 异常直接把容器 `docker rm -f` 并后台补建，不等自然结束；
- 数据目录挂 tmpfs（不持久化），CPU / 内存 / 进程数由 Docker cgroup 限制；
- 池状态（就绪数、新建数、复用数、复用率）通过 `GET /pool` 暴露。

compose 启用方式：

```bash
docker compose -f docker-compose.yml -f docker-compose.pool.yml up -d --build
```

> ⚠️ 覆盖文件会挂载 `/var/run/docker.sock`（近似宿主机 root 权限），仅在可信环境启用。
> 宿主机直接运行 judge-service（`start_judge.bat`）时无需挂载 socket。

### 6.2 外部消息队列 + 多 Worker 水平扩展（`apps/submissions/job_queue.py`）

- `JUDGE_QUEUE_BACKEND=redis`（或 `auto` + 配置 Redis URL）时，Web 进程只把
  `submission_id` 写入 Redis 队列，由独立 Worker 进程消费；
- 可靠队列：`BRPOPLPUSH` 原子移入 inflight，成功 `ack`；失败（或 Worker 崩溃）
  由 `requeue` / `requeue_stale` 重新入队，不丢单；
- 多开 Worker 即水平扩展：`docker compose up -d --scale judge-worker=4`，
  或宿主机 `python manage.py judge_worker --workers 8`；
- 未配置 Redis 时回退进程内队列（`local`），行为与之前一致。

### 6.3 题目元数据 / 用例缓存（`apps/questions/cache.py`）

- 判题所需的 `create_table_sql` + 有序用例打包缓存，避免每次判题回查数据库；
- `Question` / `TestCase` 变更通过信号立即失效；另有 `JUDGE_QUESTION_CACHE_TTL`
  兜底（多进程 LocMem 下最长滞后一个 TTL；Redis 缓存下立即一致）。

### 6.4 多 judge-db 连接分片（`JUDGE_DB_TARGETS`）

- compose 里 `judge-db` / `judge-db-2` 复用同一份配置锚点，各限 CPU 2 核；
  judge-service 通过 `JUDGE_DB_TARGETS=judge-db:5432,judge-db-2:5432` 在每个实例上
  各建一个 **预热连接池**，并按轮询把「每个用例的连接」分片到不同实例；
- 与「每任务一个容器」（6.1 容器池）不同：连接池常驻、无每请求建连开销，
  因此多实例是提升判题吞吐的低开销方式；
- 需要更多实例时：复制 `judge-db-2` 段（改 `container_name`）并追加进 `JUDGE_DB_TARGETS`。

> 实测结论（本机 12 核，light 用例，C≈48）：
>
> | 配置 | 峰值吞吐 | 饱和/瓶颈 |
> |---|---|---|
> | 1×judge-db(2核) + judge-service 1核单进程 | ~145 req/s | judge-service 1 核打满（101%） |
> | +judge-db-2（service 仍 1 核） | ~137 req/s | 无提升，仍卡在 judge-service |
> | +judge-db-2 + judge-service 4 核单进程 | ~212 req/s | 单进程 GIL/线程池 |
> | +judge-db-2 + judge-service **4 进程** | **~399 req/s** | C=128 时三者近似饱和 |
>
> 即：**只加 judge-db 没有用，必须先解除 judge-service 的单进程/单核瓶颈**；
> 到 ~400 req/s 后 judge-service(378%) 与两个 judge-db(~180%/188%) 都接近配额，
> 继续扩容要同时加 judge-service（worker 数或副本）与 judge-db（实例数）。
> 注意 uvicorn 多进程时每个 worker 各建一份连接池，务必按 `JUDGE_DB_POOL_MAX` 收缩。
