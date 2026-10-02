
---

# SQL 判题服务 API 文档

## 1. 服务概述

SQL 判题服务是一个独立的微服务，负责安全执行学生提交的 SQL 语句，与预期输出进行比对，并返回判题结果。  
服务基于 FastAPI 开发，使用 docker-compose 常驻一个 PostgreSQL 容器，判题时按请求创建独立 schema 隔离执行。  
技术栈：FastAPI + Docker Compose + PostgreSQL  
默认端口：8080  
通信协议：HTTP + JSON

---

## 2. 启动服务

### 2.1 环境要求

Python 3.10 或更高版本  
Docker Desktop（或 Docker Engine）与 Docker Compose 已安装并运行  
端口 8080 未被占用

### 2.2 安装依赖

```bash
pip install -r requirements_judge.txt
```

`requirements_judge.txt` 内容：

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
psycopg2-binary==2.9.10
pydantic==2.9.0
requests==2.32.3
python-dotenv==1.2.2
```

### 2.3 启动命令

先创建并启动判题数据库容器（复用）：

```bash
docker compose up -d
```

再启动判题服务：

```bash
python judge_service_new.py
```

或直接使用提供的批处理文件（Windows，会自动执行上述两步）：

```bash
start_judge.bat
```

启动成功输出示例：

```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080
```

### 2.4 配置说明（judge_service/.env）

判题服务的数据库等配置统一从配置文件 `judge_service/.env` 读取，由 `judge_config.py` 负责加载：

- 默认读取与脚本同目录的 `.env`，可复制 `.env.example` 得到；
- `docker compose` 也会自动读取 `judge_service/.env`，容器与判题服务共用同一套配置，无需重复填写；
- 优先级：真实环境变量 > `.env` 配置文件 > 代码内置默认值；
- 可用环境变量 `JUDGE_CONFIG_FILE` 指定其他配置文件路径。

`.env` 支持的配置项：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `JUDGE_DB_HOST` | 判题数据库主机 | `127.0.0.1` |
| `JUDGE_DB_PORT` | 判题数据库端口（与 docker-compose 映射一致） | `5433` |
| `JUDGE_DB_NAME` | 判题数据库名 | `judge_db` |
| `JUDGE_DB_USER` | 判题数据库账号 | `judge_user` |
| `JUDGE_DB_PASSWORD` | 判题数据库密码 | `judge_pass` |
| `JUDGE_DB_READY_TIMEOUT` | 启动时等待数据库可连接的秒数 | `60` |
| `JUDGE_DB_POOL_MAX` | 连接池最大连接数（并发承载上限） | `20` |
| `JUDGE_DB_POOL_MIN` | 常驻（预热）连接数，默认与最大连接数一致，避免反复建连 | `20` |
| `JUDGE_CASE_CONCURRENCY` | 单个请求内测试用例的并行度（>1 时并行执行） | `4` |
| `JUDGE_POOL_ACQUIRE_TIMEOUT` | 连接池耗尽时等待空闲连接的最长秒数 | `10` |

---

## 3. API 端点

### 3.1 健康检查

**GET** `/health`

用于检查服务是否正常运行。

**响应示例**：

```json
{
  "status": "ok"
}
```

---

### 3.2 判题接口

**POST** `/judge`

执行学生提交的 SQL，并与预期输出比对。

#### 请求头

| 参数名 | 值 |
|--------|-----|
| Content-Type | application/json |

#### 请求体 (JSON)

| 字段 | 类型 | 必填 | 描述 |
|------|------|------|------|
| `submitted_sql` | string | 是 | 学生提交的 SQL 语句（如 `SELECT name, age FROM students;`） |
| `test_cases` | array | 是 | 测试用例列表，至少包含一个用例 |
| `test_cases[].expected_output` | string | 是 | 预期输出字符串，格式见下文“输出格式说明” |
| `test_cases[].test_input` | string | 否 | 该用例的测试数据准备语句（多条语句可用分号分隔） |
| `create_table_sql` | string | 否 | 建表语句（多条语句可用分号分隔），所有测试用例共享 |
| `timeout` | integer | 否 | SQL 执行超时时间（秒），默认 30 秒 |

#### 请求示例

```json
{
  "submitted_sql": "SELECT name, age FROM students WHERE age > 18 ORDER BY age;",
  "create_table_sql": "CREATE TABLE students (id INT, name VARCHAR(50), age INT);",
  "test_cases": [
    {
      "test_input": "INSERT INTO students VALUES (1, 'Alice', 20), (2, 'Bob', 17), (3, 'Charlie', 22);",
      "expected_output": "name|age\nAlice|20\nCharlie|22"
    },
    {
      "test_input": "INSERT INTO students VALUES (1, 'David', 19), (2, 'Eve', 16);",
      "expected_output": "name|age\nDavid|19"
    }
  ],
  "timeout": 30
}
```

#### 响应体 (JSON)

| 字段 | 类型 | 描述 |
|------|------|------|
| `passed` | boolean | 所有测试用例是否全部通过 |
| `execution_status` | string | 判题状态：`ACCEPTED` / `WRONG_ANSWER` / `ERROR` |
| `score` | integer | 得分（0-100），等于通过用例数 / 总用例数 × 100 |
| `details` | array | 每个测试用例的详细结果 |
| `error_message` | string | 仅在 `execution_status` 为 `ERROR` 时可能携带错误原因（如建表语句失败），否则为 `null` |

**`details` 数组元素**：

| 字段 | 类型 | 描述 |
|------|------|------|
| `test_case_id` | integer | 测试用例序号（从 0 开始） |
| `passed` | boolean | 该用例是否通过 |
| `actual_output` | string | 学生 SQL 在该用例下的实际输出 |
| `error_message` | string | 若发生异常，返回错误信息（正常时为 `null`） |

#### 响应示例（全部通过）

```json
{
  "passed": true,
  "execution_status": "ACCEPTED",
  "score": 100,
  "details": [
    {
      "test_case_id": 0,
      "passed": true,
      "actual_output": "name|age\nAlice|20\nCharlie|22",
      "error_message": null
    },
    {
      "test_case_id": 1,
      "passed": true,
      "actual_output": "name|age\nDavid|19",
      "error_message": null
    }
  ]
}
```

#### 响应示例（部分未通过）

```json
{
  "passed": false,
  "execution_status": "WRONG_ANSWER",
  "score": 50,
  "details": [
    {
      "test_case_id": 0,
      "passed": true,
      "actual_output": "name|age\nAlice|20\nCharlie|22",
      "error_message": null
    },
    {
      "test_case_id": 1,
      "passed": false,
      "actual_output": "",
      "error_message": "syntax error at or near \"SELEC\""
    }
  ]
}
```

#### 响应示例（SQL 超时）

SQL 执行超时会作为对应测试用例的 `error_message` 返回（`passed=false`），整体状态为 `WRONG_ANSWER`：

```json
{
  "passed": false,
  "execution_status": "WRONG_ANSWER",
  "score": 0,
  "details": [
    {
      "test_case_id": 0,
      "passed": false,
      "actual_output": "",
      "error_message": "SQL执行超时"
    }
  ]
}
```

---

## 4. 输出格式说明

### 4.1 预期输出 (`expected_output`) 格式

- 第一行为**列名**，用竖线 `|` 分隔（例如 `name|age`）。
- 后续每行为**一行数据**，同样用 `|` 分隔。
- 行与行之间用换行符 `\n` 分隔。
- 示例：

```
name|age
Alice|20
Charlie|22
```

**注意**：
- 列顺序无关：判题引擎会根据列名自动对齐，你无需保证列名顺序与学生的实际输出顺序一致。

- 行顺序无关：判题引擎会将结果集视为无序集合进行比对，不会因为行排列顺序不同而判错。

- 系统会忽略每行首尾的空格，但列值内部的空格会保留。

- 重复行会被正确计数。

### 4.2 实际输出 (`actual_output`) 格式

判题服务会将学生 SQL 执行的结果集自动转换为与 `expected_output` 相同的格式，规则如下：

- 列名从数据库返回的字段名直接读取（转为字符串）。
- 每行数据按查询返回的顺序输出（未排序时顺序可能不固定，但判题不受影响）。
- 若 SQL 不返回结果集（如 `INSERT`、`UPDATE`），则 `actual_output` 为空字符串 `""`。

### 4.3 判题比对规则

判题基于结果集的内容，而非字符串形式。具体规则：

- 解析学生输出和预期输出为结构化结果集（列名列表 + 行列表）。

- 检查列名集合是否一致（顺序无关）。

- 将预期结果的行按照学生输出的列顺序重新排列。

- 将所有行的每个单元格转换为字符串（NULL 视为空字符串），然后对两边的行集合进行排序后逐行比较。

- 两边行集合完全相等（含重复行）则判为正确。



---

## 5. 错误状态说明

| `execution_status` | 含义 |
|--------------------|------|
| `ACCEPTED` | 所有测试用例通过 |
| `WRONG_ANSWER` | 至少有一个测试用例未通过（结果不匹配、执行错误或超时） |
| `ERROR` | 服务内部异常（如数据库容器未运行、网络问题等） |

---

## 6. 安全机制

1. **schema 隔离**：判题复用常驻容器，每个测试用例使用独立的临时 schema，请求结束整体回滚清空，请求/用例间互不干扰。
2. **权限收敛**：容器初始化脚本把判题账号降为非超管角色，并将 `public` schema 所有权转移，防止越权访问/删除。
3. **资源限制**：容器内存限制 `1GB`、CPU 配额（默认 2 核，见 `docker-compose.yml` 的 `cpu_quota`）、`pids_limit` 进程数限制（避免无限循环/fork 炸弹）。
4. **能力裁剪**：容器只保留必要的 Linux Capabilities，丢弃 `SYS_ADMIN`、`NET_RAW` 等高危权限。
5. **SQL 超时**：通过 PostgreSQL 的 `statement_timeout` 参数强制中断长时间运行的查询。
6. **事务回滚**：每个测试用例在独立连接与独立临时 schema 中执行，结束后整体回滚（回滚即清理），确保用例间数据隔离且不残留。

---

## 7. 注意事项

- **判题服务与判题数据库容器需在同一主机上**：先通过 `docker compose up -d` 启动容器，再启动判题服务。
- 判题服务通过固定端口（默认 `5433`）连接常驻的 PostgreSQL 容器，可用 `JUDGE_DB_PORT` 等环境变量覆盖。
- 如果业务后端与判题服务不在同一台机器，需修改 `judge.py` 中的 `JUDGE_SERVICE_URL` 为实际地址（默认 `http://localhost:8080/judge`）。
- 容器复用时并发量受连接池（`JUDGE_DB_POOL_MAX`）与数据库自身限制：连接不足时请求会等待空闲连接（最长 `JUDGE_POOL_ACQUIRE_TIMEOUT` 秒），超时返回 `ERROR`（服务繁忙）。
- 单个请求内的多个测试用例默认并行执行（`JUDGE_CASE_CONCURRENCY`），可降低多用例请求的整体响应时间；连接池与并行度需按数据库承载能力调优。
- 多条 SQL 语句用分号 `;` 分隔，但**不支持 SQL 字符串内部包含分号**（极少数情况），如有需要请将复杂语句合并为单条或使用存储过程。

---

## 8. 集成到业务后端

业务后端（Django）通过 `apps/submissions/judge.py` 的 `judge_submission` 调用判题服务：

```python
from apps.submissions.judge import judge_submission

result = judge_submission(
    submitted_sql="SELECT name FROM users;",
    test_cases=[
        {"expected_output": "name\nAlice", "test_input": "INSERT INTO users ..."}
    ],
    create_table_sql="CREATE TABLE users ..."
)
```

该函数会**同步**等待判题结果并返回与上述 API 响应一致的字典（适合脚本或离线判题）。

### 8.1 异步判题（Web 请求推荐）

为避免判题阻塞 Django 请求 worker，提交接口已改为**异步**：先落库一条
`execution_status='PENDING'` 的提交记录，再交给 `apps/submissions/judging.py` 的
后台线程判题，接口立即返回 **202**，由客户端轮询提交状态直到出结果。

```python
from apps.submissions.judging import enqueue_judge, JudgeQueueFull, PENDING

submission = Submission.objects.create(..., execution_status=PENDING, score=0)
try:
    enqueue_judge(submission.id)
except JudgeQueueFull:
    ...  # 队列已满，返回 503（服务繁忙）
```

要点：

- `POST /api/submissions/submit/` 与 `POST /api/exams/{id}/submit/` 均返回 **202**，响应中提交记录状态为 `PENDING`；
- 客户端轮询 `GET /api/submissions/{id}/`，当 `execution_status` 不再是 `PENDING`（即 `ACCEPTED`/`WRONG_ANSWER`/`ERROR`/`TIMEOUT`）时为最终结果；
- 后台线程数与队列上限可用环境变量 `JUDGE_WORKERS`（默认 4）、`JUDGE_QUEUE_SIZE`（默认 200）调整；队列满时接口返回 **503**；
- 判题在进程内执行，进程重启会丢失队列中的任务；重启后可执行 `python manage.py requeue_pending` 重新入队仍为 `PENDING` 的提交；
- 考试提交的得分由后台按该题在考试中的分值换算（`ACCEPTED` 得满分，否则 0），与单题提交（0–100 分）区别处理。

---

## 9. 常见问题

**Q：判题服务启动后提示数据库连接失败？**  
A：请先执行 `docker compose up -d` 启动判题数据库容器，并确认端口 `5433` 未被占用。

**Q：判题超时如何调整？**  
A：在请求体中传递 `timeout` 字段（单位秒），或修改 `SQL_TIMEOUT` 常量后重启服务。

**Q：启动时一直停在“等待判题数据库就绪”，能取消吗？**  
A：可以。等待期间按 `Ctrl+C` 会立即中断启动并退出，无需等到 `JUDGE_DB_READY_TIMEOUT` 超时。若频繁出现，请确认已执行 `docker compose up -d` 启动判题数据库容器，并检查 `JUDGE_DB_HOST`/`JUDGE_DB_PORT` 等配置。

---

## 10. 性能压测

仓库自带压测工具 `judge_service/load_test.py`（**仅用标准库**，宿主机或任意容器内都能直接跑）：

```bash
# 并发阶梯（1→128），默认打在 http://localhost:8080/judge
python judge_service/load_test.py

# 固定并发持续压 15 秒，并把每档结果写成 JSON
python judge_service/load_test.py --mode sustained --concurrency 32 --duration 15 --json result.json

# CPU 型重负载（4 个用例 × 800 行自连接聚合）
python judge_service/load_test.py --heavy

# 容器内运行（判题服务在 compose 网络里，用容器名寻址）
docker compose exec -T backend python - --url http://judge-service:8080/judge < judge_service/load_test.py
```

输出每档并发的吞吐（req/s）、成功率、p50/p95/p99/max 延迟与**响应状态分布**；出现非判题响应
（HTTP 错误 / 客户端失败）时退出码为 1，便于 CI 里做回归判定。

### 10.1 实测（12 vCPU 宿主机，light 负载 = 1 用例 / 200 行；同一工具与客户端做 A/B）

| 并发 | 2 核配额（当前） | 0.5 核配额（旧值） | 倍率 |
|------|------------------|--------------------|------|
| 4 | 69.9 req/s* | 74.2 req/s* | — |
| 8 | 130.8 | 66.6 | 2.0× |
| 16 | **214.7** | 48.3 | 4.4× |
| 32 | 201.9 | 64.9 | 3.1× |
| 64 | 210.0 | 67.4 | 3.1× |
| 128 | 196.5 | 62.1 | 3.2× |
| 长窗 C=16（15 秒） | **230.0**（p50 65 ms，3461/3461 全部 ACCEPTED） | 71.8（p50 204 ms） | **3.2×** |

\* 并发 ≤4 时吞吐受**压测客户端**限制：在宿主机上经 Docker Desktop 端口转发访问，单连接基线约 50 ms
（≈20 req/s/连接），因此低并发档位反映的是客户端上限而非服务端上限。要测准低并发基线，请在容器网络内运行：

```bash
docker compose exec -T backend python - --url http://judge-service:8080/judge < judge_service/load_test.py
```

### 10.2 结论与调优

- **吞吐上限由判题库容器的 CPU 配额决定**：2 核下长窗约 **230 req/s**，0.5 核下约 **72 req/s**（同负载同客户端）；
  判题服务自身只用了约 1.3 核（宿主 12 核），连接池与线程池都不是瓶颈。
- 提高配额后**伸缩性恢复正常**：吞吐随并发上升到 C≈16 进入平台期（~200-230 req/s），
  而不是像 0.5 核时那样「并发越高吞吐越低、延迟线性增长」。
- 除配额外，压测还暴露并修掉了两个坑：
  1. **判题库数据 tmpfs 必须给足**：PostgreSQL 默认 `max_wal_size=1GB`，而判题每个请求都要建表/回滚，
     产生大量 WAL。数据目录只有 256MB 时，持续高并发会写满 tmpfs
     （`FATAL: could not write to file "pg_wal/xlogtemp.694": No space left on device`）→ 数据库崩溃重启 →
     复用连接被污染 → 判题批量 `ERROR`。现放宽到 1GB（见 `docker-compose.yml` 注释）。
  2. 压测工具早期版本漏写 `INSERT ... VALUES` 的 `VALUES` 关键字，会让用例恒为 `WRONG_ANSWER`，
     并在高并发下放大成 `ERROR`；现工具已修正，并会把服务端 `error_message` 一并打印，便于一眼定位失败原因。
- 需要更大容量时：按「单请求 DB CPU ÷ 配额」估算继续放宽 `cpu_quota`（单请求 DB CPU ≈ 3.6 ms/1 用例）；
  若必须维持低配额，建议加**准入控制**（限制在途请求数、超出快速返回「服务繁忙」），而不是让延迟堆到 10 秒级。

