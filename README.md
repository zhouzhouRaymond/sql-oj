# SQL Online Judge 系统

## 1 系统概述

SQL Online Judge（SQL OJ）是一个面向数据库课程的在线判题平台，支持学生在线练习 SQL 题目、参加考试，教师管理题库、组织考试并查看统计分析。系统采用前后端分离架构，判题引擎基于 Docker（docker-compose）与 schema 隔离实现安全执行。

### 1.1 功能模块

| 模块 | 说明 |
|------|------|
| 用户管理 | 学生自助注册、教师账号管理（新建/编辑/停用/重置密码）、JWT 认证、个人信息管理 |
| 题目管理 | 题目 CRUD、难度分级、建表 SQL、批量导入 |
| 考试管理 | 创建考试、时间校验、考生范围控制、成绩排名 |
| 提交判题 | SQL 提交、Docker 容器执行、schema 隔离、自动评分 |
| 统计分析 | 通过率统计、学生排名、数据概览 |
| #todo 班级管理 | 待实现 |
| #todo 自定义测试用例 | 待实现 |
| #todo 逐测试用例返回结果 | 待实现 |

### 1.2 技术栈

**后端服务**

| 组件 | 版本 |
|------|------|
| Python | 3.10+ |
| Django | 6.0 |
| Django REST Framework | 3.17 |
| Simple JWT | 5.5 |
| MySQL | 8.x |
| PyMySQL | 1.2 |

**判题服务（独立微服务）**

| 组件 | 版本 |
|------|------|
| FastAPI | 0.115.0 |
| Docker Engine / Docker Compose | 20.10+ |
| PostgreSQL | 15（容器内） |
| psycopg2 | 2.9.10 |

**前端**

| 组件 | 版本 |
|------|------|
| Vue | 3.5 |
| TypeScript | 6.0 |
| Vite | 8.0 |
| Element Plus | 2.14 |
| ECharts | 6.1 |

---

## 2 环境要求

在部署之前，请确保目标机器满足以下条件：

| 软件 | 最低版本 | 用途 |
|------|----------|------|
| Python | 3.10 | 后端运行环境 |
| MySQL | 8.0 | 业务数据库 |
| Docker Desktop | 20.10 | 判题沙箱 |
| Node.js | 18.0 | 前端构建与开发 |
| Git | 2.30 | 版本控制 |

操作系统：Windows 10/11 或 Linux（本文以 Windows 为例）。

---

## 3 安装与部署

### 3.1 获取源码

```powershell
git clone <仓库地址>
cd sql_oj
```

### 3.2 后端安装

```powershell
# 创建并激活虚拟环境（推荐）
python -m venv venv
venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

依赖清单（requirements.txt）：
- Django >= 5.0
- djangorestframework >= 3.14
- djangorestframework-simplejwt >= 5.3
- django-cors-headers >= 4.3
- django-filter >= 23.0
- PyMySQL >= 1.1
- requests >= 2.31

### 3.3 数据库配置

**步骤一：创建数据库**

使用 MySQL 客户端执行：

```sql
CREATE DATABASE sql_oj_db DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

**步骤二：修改配置文件**

编辑 `sql_oj/settings.py`，修改 DATABASES 配置中的连接参数：

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'sql_oj_db',
        'USER': 'root',
        'PASSWORD': '<你的MySQL密码>',
        'HOST': 'localhost',
        'PORT': '3306',
        'OPTIONS': {'charset': 'utf8mb4'},
    }
}
```

**步骤三：执行数据库迁移**

```powershell
python manage.py migrate
```

成功后终端会输出各应用的迁移状态（均显示 OK）。

### 3.4 导入预置题目（可选）

系统内置 11 道 SQL 练习题（含完整的题目描述、建表语句、测试用例和标准答案等），可通过管理命令一键导入：

```powershell
python manage.py import_exercises --teacher-id=1
```

注意：需先注册一个教师账号（ID 为 1），或指定已有教师用户的 ID。

### 3.5 判题服务安装

```powershell
cd judge_service

# 安装依赖
pip install -r requirements_judge.txt

# 创建配置文件（数据库等参数统一从此读取；docker compose 也会自动加载）
copy .env.example .env
```

判题服务的数据库等配置统一存放于 `judge_service/.env`，各配置项含义见 `docs/judge_api_new.md` 第 2.4 节。

前置条件：Docker Desktop（含 Docker Compose）已安装并正在运行。

### 3.6 前端安装

```powershell
cd sql-oj-frontend

# 安装依赖
npm install
```

---

## 4 系统启动

系统运行需要同时启动三个服务，建议按以下顺序操作（各服务使用独立终端窗口）：

### 4.1 启动判题服务

```powershell
cd judge_service

# 用 docker compose 创建并启动判题数据库容器（复用）
docker compose up -d

# 启动判题服务
python judge_service_new.py
```

启动成功标志：
```
INFO:     Uvicorn running on http://0.0.0.0:8080
```

验证方法：
```powershell
curl http://localhost:8080/health
```
返回 `{"status":"ok"}` 表示正常。

### 4.2 启动后端服务

```powershell
cd sql_oj
python manage.py runserver
```

启动成功标志：
```
Starting development server at http://127.0.0.1:8000/
```

### 4.3 启动前端服务

```powershell
cd sql-oj-frontend
npm run dev
```

启动成功标志：
```
VITE vx.x.x  ready in xxx ms
Local: http://localhost:5173/
```

前端通过 Vite 代理将 `/api` 请求转发至后端 `http://localhost:8000`，无需额外配置跨域。

### 4.4 服务端口汇总

| 服务 | 地址 | 说明 |
|------|------|------|
| 后端 API | http://localhost:8000 | Django 业务后端 |
| 判题服务 | http://localhost:8080 | FastAPI 判题引擎 |
| 前端页面 | http://localhost:5173 | Vite 开发服务器 |

---

## 5 系统使用说明

### 5.1 用户注册与登录

系统支持两种角色：学生（student）和教师（teacher）。账号有两个名称字段：

| 字段 | 说明 |
|------|------|
| **登录名** `username` | 全站唯一，用于登录；建议用"姓名拼音_学号/工号"格式避免重名 |
| **用户名** `display_name` | 展示名，可自定义（留空时与登录名相同），在「个人中心」或账号管理中修改 |

访问前端页面（Docker 部署为 http://localhost:8090 ，开发模式为 http://localhost:5173 ），在登录/注册页面完成账号创建：

- **自助注册仅支持学生账号**：需填写登录名（≥3 位）与密码（≥6 位）；用户名、邮箱均为**选填**（邮箱填写时会校验格式）。
- **教师账号不由自助注册创建**：请由已登录教师在「账号管理」页面新建（角色可选学生 / 教师）。仅当系统内还没有任何教师时，允许通过注册接口创建一个教师账号用于初始化。

![注册登录页面](./images/Login.png)

### 5.2 学生端操作

#### 5.2.1 题目列表与练习

登录后进入题目列表页面，可查看所有可用题目，显示题目ID、名称和难度标签。

![学生端题目列表](./images/Questions_student.png)

点击"开始答题"，可查看题目描述与样例输入输出。编写SQL并提交，系统自动判题，返回结果"ACCEPTED""WRONG ANSWER"或"ERROR"以及最终得分。

练习页的 SQL 编辑内容会**自动暂存到本机浏览器**，刷新或误关页面后重新进入该题即可**恢复上次编辑的 SQL**（清空编辑器或退出登录时清除）。

![答题1](./images/AnswerQuestion1.png)

判题机制允许学生输出的行、列顺序与标准答案不同，只要内容语义一致即判定通过，提升判题的灵活性和公平性。测试中可提交不同的正确答案，下图中输出结果与标准答案分别存在列、行顺序的不同，均判为正确。

![答题2](./images/AnswerQuestion2.png)
![答题3](./images/AnswerQuestion3.png)

#### 5.2.2 查看提交记录

在"提交记录"页面可查看历史提交，以列表形式呈现每次提交对应的题目ID、判题结果（ACCEPTED / WRONG_ANSWER / ERROR / TIMEOUT）、得分和提交时间。点击"查看详情"可查看提交的完整SQL。

![提交记录](./images/Submissions.png)

#### 5.2.3 参加考试

「我的考试」分为**当前考试**与**考试记录**两个标签（标签上带数量）：表格中每行显示考试名称（下方标注**共几题**）、考试时间（开始 / 结束 / **时长** 三行同格展示，时长 `0` 显示"不限时"）、总分与状态标签（未开始 / 进行中 / 已结束）；若有考试正在进行中，页面顶部会给出提醒。过去时段的考试显示"已结束"，未来时段的显示"未开始"，已经参加过的考试不能重复参加；显示"进行中"的考试点击"进入考试"即可作答。

![学生端考试列表](./images/Exams_student.png)

考试过程中阅读每道题目，编写SQL语句，答题完成后点击"提交试卷"，系统集中判题。右上角按**考试时长**倒计时（时长由教师在创建考试时设置，`0` 表示不限时、以考试结束时间为准），**倒计时结束会自动交卷**。作答内容会**双重暂存**：本机浏览器（刷新/误关页面可恢复，交卷成功后清除、登出时清理）+ **服务端**（每 20 秒同步一次，**换电脑/换浏览器登录也能接着答**）。若学生在到点前关掉浏览器，服务端会在教师查看排名/导出成绩、或学生再次进入/查看得分时**按最后同步的草稿自动交卷**，成绩不会漏；离开考试页时浏览器也会给出提醒。

![参加考试](./images/Exams_student2.png)

交卷后系统反馈考试结果，包括总分、正确题目数以及每道题的答题详情，可查看自己提交的SQL。

> **结果页的出口由进入方式决定**：**交卷后（含倒计时自动交卷）**进入结果页时，本页不提供任何其它页面入口，右上角只有「退出」一个出口（按钮样式与学生端其它页面一致），退出后回到登录界面；学生在该页使用浏览器「后退」返回考试页等操作同样会被拦截，并使其登录状态失效、跳转登录界面。**从「考试记录」点击「查看结果」**进入时属于回顾历史成绩，页面右上角提供「← 返回考试记录」与「退出」，返回考试记录标签页不做登出。教师访问该页不受此限制。

![考试结果](./images/ExamResult.png)

参加过的考试都会显示在"考试记录"中，「得分 / 总分」列直接给出该场考试的得分（大号彩色分数 + 得分占比进度条，口径与教师端排名一致：同一题多次提交只取最高分），点击"查看结果"可查看考试结果。

![考试记录](./images/ExamRecords.png)

#### 5.2.4 个人统计

在个人中心可查看个人信息与统计数据。可修改个人信息中的邮箱。个人数据包括提交总次数、通过率、通过题目数和最近提交记录，其中通过率=个人通过次数/个人提交次数×100%.

![学生个人中心](./images/PersonalCenter_student.png)

### 5.3 教师端操作

#### 5.3.1 题目管理

在题目列表页面显示题目ID、名称和难度标签，教师可对题目进行创建、查看、编辑、删除操作。

列表中的**「学生可见」开关**用于控制该题是否对学生公开：**公开**时学生可在题库中看到并作答；**隐藏**后该题会从学生题库中移除，学生也无法直接打开它（返回 404），教师端始终可见（已隐藏的题目标题会灰显）。隐藏**不影响已安排的考试**——考试内容由考试接口单独下发。

![教师端题目列表](./images/Questions_teacher.png)

点击"查看"，教师视图显示题目描述、样例输入输出、测试用例（含测试输入与预期输出）和参考答案；其中**样例输入、样例输出、参考答案、测试用例四块默认折叠**，点击标题才展开（避免长页面一次铺开）。

页面下方还有**「📊 数据统计」**面板：可选择统计时间段（精确到分钟，提供"最近 1 小时 / 24 小时 / 7 天 / 30 天 / 90 天 / 未来 1 小时"快捷选项，默认统计**全部历史提交**），动态展示本题的**提交次数、提交人数（去重）、通过率**，并给出**该时间段内本题的学生通过率排名**（提交数 / 通过数 / 通过率 / 是否通过）。

![教师查看题目1](./images/Questions_teacher2.png)
![教师查看题目2](./images/Questions_teacher3.png)

点击"编辑",可修改已有的题目。

![教师修改题目](./images/EditQuestion.png)

"创建题目"时需填写题目名称、题目描述、难度、建表 SQL、输入输出样例、测试用例和正确答案。其中题目描述、输入输出样例会在学生视图中展示，支持Markdown.

![教师创建题目](./images/CreateQuestion1.png)

系统支持添加多个测试用例，只有通过所有测试才会判为"ACCEPTED"，最终得分按照"通过测试数/总测试数×题目分值"计算。

![测试用例](./images/CreateQuestion2.png)

#### 5.3.2 考试管理

教师可创建考试，设定考试名称、起止时间、**考试时长**、从题库中选择题目并分配分值。考试时长以分钟为单位，**0 表示不限时**（仅受考试起止时间约束）；学生进入考试后按该时长倒计时，**倒计时结束会自动交卷**。

![教师创建考试](./images/CreateExam.png)

考试由**全体教师共享**：任何教师都能看到并编辑（含删除、导出成绩、重置考试次数）其他教师创建的考试；学生也能看到**所有教师**创建的考试（仍受「学生可见」与考试范围约束）。列表中显示考试ID、名称、**创建人**、状态、考试时间（含时长）、总分与「学生可见」开关。教师可删除考试，或进行编辑修改（编辑不会改变创建人）。

列表中的**「学生可见」开关**用于控制该考试是否对学生公开：**公开**时学生会在「我的考试」中看到并能进入；**隐藏**后该考试对学生完全不可见（列表中不再出现，直接打开详情或开始考试都返回 404），教师端始终可见（已隐藏的考试名称会灰显）。该显示逻辑与题目列表保持一致。

列表还显示**状态**（未开始 / 进行中 / 已结束）、**考试时间**（开始、结束两行，并标注考试时长）与总分。当考试**已结束**后，「操作」列中的**「导出」**变为可用，点击即可下载该场考试的**成绩单 CSV**（UTF-8 带 BOM，Excel 可直接打开）：排名、登录名、姓名、得分、考试总分、最近提交时间；同一题多次提交只计最高分。

**考试时间内每位学生只能考一次**：已提交过的学生无法再次进入或重复提交（直接访问会被拒绝）。如确有需要，教师可在「排名」弹窗中对该生点击**「重置考试次数」**（按个人重置，清除其本场考试的作答记录），重置后该生即可重新参加考试。

「操作」列还提供**「考试情况」**：点开即可查看**参加本场考试的学生**的成绩与提交情况（含"已进入但未提交"的学生；未参加考试的学生不会列出）——顶部汇总（参加考试 / 已提交 / 未提交 人数、提交记录条数、已提交者平均分），表格按**得分降序**默认排列（点击「得分」表头可切换升降序），列出**排名**、用户名、登录名、**得分**、状态（已提交 / 未提交）、**已答题目数**与最近提交时间，并可对某位学生**重置考试次数**；展开某位学生可看到其每道题的提交（题目、得分、判题状态、提交时间），点「查看详情」可看该次提交的 **SQL 与判题用例明细**。

![教师端考试列表](./images/Exams_teacher.png)

点击"编辑"，可调整考试起止时间或考题选择。

![教师修改考试](./images/EditExam.png)

#### 5.3.3 考试成绩排名

在考试管理页面点击"排名"可查看某场考试的学生成绩排名。若没有学生完成考试，则显示"暂无学生参加该考试"。

![查看考试成绩排名](./images/ExamRanking.png)

#### 5.3.4 整体统计

教师端"统计分析"页面提供：
- 题目通过率（提交次数，提交人数，通过人数，题目通过率=通过人数/提交人数×100%）
- 学生通过率排名（学生通过率=个人通过次数/个人提交次数×100%）
- 整体数据概览（题目总数，总提交次数，注册用户数，平均通过率=总通过次数/总提交次数×100%）

![统计分析](./images/Statistics.png)

#### 5.3.5 个人统计

教师在"个人中心"可查看基本信息和个人数据，后者包括自己创建题目和考试的数量。个人中心还支持修改**用户名（展示名）**、邮箱（选填）以及**登录密码**（「🔒 修改密码」，需校验原密码，修改成功后需用新密码重新登录）。

![教师个人中心](./images/PersonalCenter_teacher.png)

#### 5.3.6 账号管理

教师端侧边栏「账号管理」用于管理**所有类别的账号**（学生与教师）：

- **列表**：显示 ID / 登录名 / 用户名 / 邮箱 / 角色 / 状态 / 注册时间；滚动到底部自动加载下一页（与题目列表一致的无限滚动），支持**关键词搜索**（登录名、用户名、邮箱）与**角色筛选**
- **新建账号**：可创建学生或教师账号，需填写登录名与初始密码（用户名、邮箱选填）
- **编辑账号**：可修改用户名、邮箱、角色；在"重置密码"中填入新密码即可为该账号重置密码
- **停用 / 启用**：停用后该账号**无法登录**，其已签发的 Token 也会**立即失效**（建议用"停用"替代删除，保留该账号的提交与考试记录）

> 教师账号**不支持自助注册**：注册页面仅能创建学生账号；教师账号请在本页面新建。仅当系统内一个教师都没有时，注册接口才允许创建教师账号，用于初始化。

<!-- [截图：账号管理] -->

---

## 6 API 接口参考

所有接口基础地址：`http://localhost:8000`

### 6.1 认证接口

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | /api/auth/register/ | 用户注册 | 无需登录 |
| POST | /api/auth/login/ | 登录，返回 JWT Token | 无需登录 |
| POST | /api/auth/refresh/ | 刷新 Token | 无需登录 |
| POST | /api/auth/logout/ | 登出，使该账号已签发的 token 立即失效 | 登录用户 |

> **单点登录（单会话）**：默认开启（`SINGLE_SESSION_ENFORCED=True`）。同一账号只能在一个终端在线，**新登录会立即踢掉该账号此前的会话**——旧 access token 失效、旧 refresh token 进入黑名单。可通过环境变量 `SINGLE_SESSION_ENFORCED=False` 关闭。
>
> **免登录窗口（登录 Cookie）**：登录成功后，refresh token 写入 **HttpOnly Cookie**（`sql_oj_refresh`，`Path=/api/auth`，`SameSite=Lax`），有效期即**免登录窗口**——默认 **7 天**，可用环境变量 `LOGIN_REMEMBER_DAYS` 调整（最小 1 天）。关闭浏览器后重新打开，只要还在窗口内，前端会用该 Cookie **自动续期** access token（access 有效期 2 小时，用户无感）；窗口过期后 Cookie 被浏览器删除、服务端也拒绝刷新，**必须重新登录**。每次刷新都会轮换 Cookie（窗口按活跃度顺延）。HTTPS 部署建议设 `LOGIN_COOKIE_SECURE=True`（Cookie 仅走 HTTPS）。
>
> **登录限流**：登录接口按来源 IP 限流（默认 10 次/分钟），超过限制返回 429，用于缓解密码暴力破解。

### 6.2 用户管理

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | /api/users/me/ | 查看个人信息 | 登录用户 |
| PUT/PATCH | /api/users/me/ | 修改个人信息（仅用户名/邮箱/密码；登录名、角色、启用状态只读） | 登录用户 |
| POST | /api/users/change-password/ | 修改自己的密码（校验原密码，改后旧 token 立即失效） | 登录用户 |
| GET | /api/users/me/stats/ | 个人统计数据 | 登录用户 |
| GET | /api/users/ | 账号列表（分页；支持 `?search=` 关键词、`?user_type=student\|teacher` 过滤） | 教师 |
| POST | /api/users/ | 新建任意角色账号（需初始密码，邮箱选填） | 教师 |
| PATCH | /api/users/{id}/ | 编辑账号 / 重置密码（传 `password`）/ 停用启用（`is_active`） | 教师 |

### 6.3 题目管理

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | /api/questions/ | 题目列表（分页） | 登录用户 |
| POST | /api/questions/ | 创建题目 | 教师 |
| GET | /api/questions/{id}/ | 题目详情（学生只能看到 `is_visible=true` 的题目，否则 404） | 登录用户 |
| PUT | /api/questions/{id}/ | 修改题目 | 教师 |
| PATCH | /api/questions/{id}/ | 局部修改（如切换 `is_visible` 控制学生可见） | 教师 |
| DELETE | /api/questions/{id}/ | 删除题目 | 教师 |

> **学生可见（`is_visible`）**：`false` 的题目不会出现在学生的 `GET /api/questions/` 列表中，学生访问其详情返回 404；教师端不受影响（列表与详情均可查看，便于随时改回公开）。

### 6.4 考试管理

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | /api/exams/ | 考试列表 | 登录用户 |
| POST | /api/exams/ | 创建考试 | 教师 |
| GET | /api/exams/{id}/ | 考试详情（学生只能看到 `is_visible=true` 的考试，否则 404） | 登录用户 |
| PUT | /api/exams/{id}/ | 修改考试 | 教师 |
| PATCH | /api/exams/{id}/ | 局部修改（如切换 `is_visible` 控制学生可见） | 教师 |
| DELETE | /api/exams/{id}/ | 删除考试 | 教师 |
| POST | /api/exams/{id}/start/ | 开始考试（隐藏对学生 404；已考过返回 400；返回 `remaining_seconds` 倒计时与已同步的 `draft` 草稿） | 学生 |
| POST | /api/exams/{id}/draft/ | 同步作答草稿（`{"answers": {"题目id": "SQL"}}`；换设备恢复作答、到点兜底交卷的依据） | 学生 |
| POST | /api/exams/{id}/submit/ | 提交试卷（已提交过返回 400；成功后清除服务端草稿） | 学生 |
| GET | /api/exams/{id}/result/ | 考试排名 | 登录用户 |
| GET | /api/exams/my-scores/ | 当前学生每场考试的得分（`{scores: {考试id: 得分}}`，同一题只取最高分后求和） | 登录用户 |
| GET | /api/exams/{id}/export/ | 导出成绩单（CSV，UTF-8 带 BOM；仅教师，且考试结束后才可用，否则 400） | 教师 |
| POST | /api/exams/{id}/reset-attempt/ | 重置某位学生在本场考试的作答记录（传 `student_id`，按个人重置考试次数） | 教师 |

> **学生可见（`is_visible`）**：`false` 的考试不会出现在学生的 `GET /api/exams/` 列表中，学生打开详情、调用 `start` / `submit` 均返回 404；教师端不受影响（列表与详情均可查看，便于随时改回公开）。
>
> **考试共享与创建人**：考试不归属于个人——教师调用 `GET /api/exams/` 会看到**全部**考试（含其他教师创建的、已隐藏的），并可对它们执行修改 / 删除 / 导出 / 重置考试次数；学生仍只看到 `is_visible=true` 且在自己范围内的考试。列表每行附带创建人信息：`teacher`（id）、`teacher_name`（展示名，为空时回退登录名）、`teacher_username`（登录名）；由谁编辑都不会改变创建人。
>
> **成绩导出**：`GET /api/exams/{id}/export/` 仅教师可调用，且必须 `now > end_time`（考试已结束），否则返回 400。导出为 CSV，列为：排名、登录名、姓名、得分、考试总分、最近提交时间；得分按「每题最高分」求和（同一题多次提交不累加）。
>
> **只能考一次**：考试时间内每位学生只能考一次——存在作答记录后再调用 `start` / `submit` 都会返回 400。教师可用 `reset-attempt` 按个人清除该生的作答记录，使其可重新参加考试。
>
> **考试时长与倒计时**：考试的 `duration_minutes`（分钟，`0` = 不限时）决定学生进入后的作答倒计时，且不晚于考试结束时间；`start` 返回 `remaining_seconds`。截止时间会持久化（刷新页面不会重置计时），到期后 `start` 返回 400「本场考试作答时间已结束」，需教师在排名弹窗中重置该生考试次数。排名弹窗同时列出「已进入但未提交」的考生（标记为未提交），便于重置。
>
> **作答草稿与兜底交卷**：`POST /api/exams/{id}/draft/` 把 `{题目 id: SQL}` 暂存到服务端（仅本人在作答会话有效期内、未交卷时可写）；`start` 会一并返回该草稿，供换设备恢复作答。若考生到点仍未交卷但服务端存有草稿，`start` / `result` / `export` / `my-scores` 会先**懒执行兜底交卷**（按最后草稿生成提交并判题；`start` 同时返回 `auto_submitted: true` 与「已自动交卷」提示）；也可手动执行 `python manage.py finalize_expired_exams [--exam <id>]`。从未作答（无草稿）的考生保持「未提交」，提示仍为「本场考试作答时间已结束，请联系教师重置考试次数」。

### 6.5 提交判题

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | /api/submissions/submit/ | 提交 SQL 判题 | 登录用户 |
| GET | /api/submissions/ | 提交历史（可按 `?question_id=`、`?student_id=`、`?exam=`、`start`/`end` 时间窗过滤；`student_id` 仅教师生效，学生始终只能看到自己的提交） | 登录用户 |
| GET | /api/submissions/{id}/ | 提交详情 | 登录用户 |

### 6.6 统计分析

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | /api/stats/overview/ | 整体数据概览 | 登录用户 |
| GET | /api/stats/questions/ | 题目通过率 | 教师 |
| GET | /api/stats/students/ | 学生排名 | 教师 |
| GET | /api/stats/question/ | 单题统计（`?question_id=`，可选 `start`/`end` 时间窗、精确到分钟；返回提交数/去重提交数/通过率/学生通过率排名） | 教师 |

---

## 7 功能验证测试

本节提供各功能模块的验证步骤，供测试人员参照执行。

### 7.1 用户注册与登录

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 注册学生账号（不填邮箱） | 返回 201，`email` 为空，`name` 回退为登录名 |
| 2 | 注册学生账号（填合法邮箱） | 返回 201，`email` 正确回显 |
| 3 | 注册学生账号（填非法邮箱） | 返回 400，提示邮箱格式 |
| 4 | 注册教师账号（系统内已有教师） | 返回 400，提示教师账号不可自助注册 |
| 5 | 使用正确密码登录 | 返回 access 和 refresh Token |
| 6 | 使用错误密码登录 | 返回 401 |
| 7 | 学生 PATCH /api/users/me/ 传 `user_type=teacher` | 返回 200，但 `user_type` 仍为 student（角色字段只读，无法自行提权） |
| 8 | 同一账号在第二台设备登录（单点登录） | 返回 200；第一台设备的旧 Token 立即失效（旧 access 请求返回 401，旧 refresh 刷新返回 401） |
| 9 | 登录后调用 POST /api/auth/logout/ | 返回 200，原 access token 立即失效 |
| 10 | 一分钟内连续尝试登录超过 10 次 | 超出部分返回 429（登录限流） |
| 11 | 登录成功后关闭浏览器，在免登录窗口（默认 7 天）内重新打开 | 免登录进入系统（access 过期自动续期）；超出窗口后需重新登录 |

<!-- [截图：注册成功] -->

<!-- [截图：登录成功] -->

### 7.2 题目管理（教师）

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 教师创建题目（含建表SQL、答案、测试用例） | 返回 201，题目创建成功 |
| 2 | 查看题目列表 | 返回分页数据，每页 20 条 |
| 3 | 学生查看题目详情 | 不显示正确答案和建表 SQL |
| 4 | 教师修改题目 | 返回 200，内容更新 |
| 5 | 教师删除题目 | 返回 204，级联删除答案和测试用例 |

<!-- [截图：创建题目成功] -->

### 7.3 SQL 提交与判题

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 学生提交正确 SQL | 返回 ACCEPTED |
| 2 | 学生提交错误 SQL | 返回 WRONG_ANSWER |
| 3 | 提交超时 SQL | 返回 TIMEOUT |
| 4 | 查看提交记录 | 包含 submission_time、question_title、execution_status |

<!-- [截图：提交正确SQL] -->

<!-- [截图：提交错误SQL] -->

### 7.4 考试流程

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 教师创建考试（设定时间、题目、分值） | 返回 201 |
| 2 | 学生在考试时间内开始考试 | 返回题目列表 |
| 3 | 学生提交试卷（POST /api/exams/{id}/submit/） | 返回各题得分和总分 |
| 4 | 考试时间外提交 | 返回 400 错误 |
| 5 | 查看考试排名 | 按总分降序排列 |

<!-- [截图：考试中作答] -->

<!-- [截图：提交试卷结果] -->

### 7.5 统计分析（教师）

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 查看整体概览 | 返回题目数、提交数、用户数、平均通过率 |
| 2 | 查看题目通过率 | 每题显示尝试人数、通过人数、通过率 |
| 3 | 查看学生排名 | 仅显示有提交记录的学生，含通过题目数 |

<!-- [截图：统计概览] -->

<!-- [截图：题目通过率图表] -->

<!-- [截图：学生排名表格] -->

### 7.6 权限控制

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 未登录访问 API | 返回 401 |
| 2 | 学生尝试创建题目 | 返回 403 |
| 3 | 学生尝试创建考试 | 返回 403 |
| 4 | 学生查看他人提交记录 | 仅返回自己的记录 |

<!-- [截图：权限拦截] -->

### 7.7 教师端查看学生提交记录（按题目下钻）

| 步骤 | 操作 | 预期结果 |
|------|------|----------|
| 1 | 教师打开「题目详情」→「数据统计」 | 显示提交次数 / 提交人数 / 通过率，以及本题学生通过率排名 |
| 2 | 切换时间段后点击「查询」 | 统计与排名按该时间段刷新，「实际统计」文案同步更新 |
| 3 | 点击排名表中的学生姓名 | 弹窗列出该学生**该时间段内本题**的提交（提交ID / 状态 / 得分 / 来源 / 提交时间） |
| 4 | 展开弹窗中某一行 | 显示该次提交的 SQL 与判题明细（失败用例、运行结果均表格化展示） |
| 5 | 学生账号请求 `GET /api/submissions/?student_id=<他人ID>&question_id=<题目ID>` | 仅返回本人提交，拿不到他人数据 |
| 6 | 请求 `GET /api/submissions/?question_id=abc` | 返回 400（非法参数不会变成 500） |

<!-- [截图：学生提交记录下钻弹窗] -->

---

## 8 项目目录结构

```
sql_oj/
├── manage.py                       # Django 管理入口
├── requirements.txt                # 后端依赖
├── images/                         # 系统页面截图
├── sql_oj/                         # 项目配置
│   ├── settings.py                 # 数据库、JWT、CORS 等配置
│   ├── urls.py                     # 根路由
│   └── wsgi.py                     # WSGI 入口
├── apps/                           # 业务模块
│   ├── users/                      # 用户管理
│   │   ├── models.py               # 用户模型（含 user_type 角色字段）
│   │   ├── serializers.py          # 注册/用户信息序列化器
│   │   ├── views.py                # 注册、个人信息、统计
│   │   ├── permissions.py          # 自定义权限类
│   │   ├── urls.py                 # 用户路由
│   │   └── urls_auth.py            # 认证路由
│   ├── questions/                  # 题目管理
│   │   ├── models.py               # 题目、答案、测试用例模型
│   │   ├── serializers.py          # 嵌套序列化器
│   │   ├── views.py                # 题目 CRUD
│   │   ├── urls.py                 # 题目路由
│   │   └── management/commands/    # 管理命令
│   │       └── import_exercises.py # 批量导入题目
│   ├── exams/                      # 考试管理
│   │   ├── models.py               # 考试模型、考试题目关联
│   │   ├── serializers.py          # 考试序列化器
│   │   ├── views.py                # 考试 CRUD、开始考试、提交试卷、排名
│   │   └── urls.py                 # 考试路由
│   └── submissions/                # 提交判题
│       ├── models.py               # 提交记录模型
│       ├── serializers.py          # 提交记录序列化器
│       ├── views.py                # 提交与统计分析
│       ├── judge.py                # 判题服务调用（同步）
│       ├── judging.py              # 后台异步判题队列（不阻塞请求 worker）
│       ├── urls.py                 # 提交路由
│       └── urls_stats.py           # 统计路由
├── judge_service/                  # 判题引擎（独立微服务）
│   ├── judge_service_new.py        # FastAPI 主程序（端口 8080）
│   ├── judge_config.py             # 配置加载（从 .env 读取数据库等配置）
│   ├── .env / .env.example         # 配置文件 / 示例（.env 本地创建，不提交）
│   ├── docker-compose.yml          # 判题数据库容器（复用）
│   ├── initdb/                     # 容器初始化脚本（权限收敛、public 隔离）
│   ├── requirements_judge.txt      # 判题服务依赖
│   ├── load_test.py                # 并发压测工具（纯标准库，见 docs/judge_api_new.md 第 10 节）
│   └── start_judge.bat             # Windows 启动脚本
├── docs/                           # 文档
│   └── judge_api_new.md                # 判题服务 API 文档
└── sql-oj-frontend/                # 前端（Vue 3）
    ├── package.json                # 前端依赖
    ├── vite.config.ts              # Vite 配置（含 API 代理）
    └── src/
        ├── api/                    # API 调用封装
        ├── router/                 # 路由与权限守卫
        ├── stores/                 # Pinia 状态管理
        └── views/                  # 页面组件
            ├── student/            # 学生端页面
            └── teacher/            # 教师端页面
```

---

## 9 常见问题

**Q: 执行 migrate 报错 "Access denied for user"**

A: settings.py 中的 MySQL 密码配置不正确。请确认 PASSWORD 字段与本地 MySQL root 密码一致。

**Q: 执行 migrate 报错 "Unknown database 'sql_oj_db'"**

A: 尚未创建数据库。先在 MySQL 中执行 `CREATE DATABASE sql_oj_db DEFAULT CHARACTER SET utf8mb4;`。

**Q: 提交 SQL 后返回 ERROR 或无响应**

A: 检查判题服务是否正在运行（http://localhost:8080/health），以及 Docker Desktop 是否已启动。

**Q: 前端页面无法调用后端接口**

A: 确认后端服务运行在 8000 端口，且前端 Vite 开发服务器已启动。开发环境下 API 代理已配置，无需手动处理跨域。

**Q: pip install 报错**

A: 确认 Python 版本 >= 3.10，尝试 `pip install --upgrade pip` 后重试。Windows 下 PyMySQL 一般无需编译，如遇问题可单独安装：`pip install PyMySQL`。

**Q：前端调用 API 报 CORS 错误？**
A：开发阶段 `CORS_ALLOW_ALL_ORIGINS = True` 已经配好了。如果还报错，检查前端请求 URL 是否正确。

**Q：在哪里查看 API 文档？**
A：启动后端后，浏览器访问 `http://127.0.0.1:8000/api/`，DRF 自带的浏览界面可以直接测试所有接口。

---

## 10 注意事项

1. `settings.py` 包含数据库密码，各成员需自行配置，不提交至版本库。
2. 后端和判题服务需同时运行，否则 SQL 提交功能不可用。
3. 判题服务依赖 Docker，首次运行 docker compose up -d 时会拉取 PostgreSQL 镜像，请确保网络畅通。
4. 数据模型变更后需执行 `python manage.py makemigrations` 和 `python manage.py migrate`。
5. 判题服务的数据库等配置统一从 `judge_service/.env` 读取（可复制 `.env.example` 得到），`docker compose` 也会自动加载该文件，从而保证容器与判题服务配置一致。

---

## 11 Docker 容器化部署（一键启动）

除本地手动部署（第 3~4 节）外，本项目提供完整的 Docker 化方案，可用一条命令启动全部服务（MySQL、判题数据库 PostgreSQL、判题服务、后端、前端）。

### 11.1 前置条件

- 已安装 Docker Desktop（含 Docker Compose），且 Docker 服务正在运行。
- 首次构建与启动需要联网拉取基础镜像（python:3.12-slim、node:20-alpine、nginx:alpine、mysql:8.4、postgres:15-alpine）。

### 11.2 快速开始

```powershell
# 在项目根目录执行
docker compose up -d --build
```

启动完成后访问：

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端页面 | http://localhost:8090 | Nginx 托管前端构建产物 |
| 后端 API | http://localhost:8000/api/ | Django + DRF（可直接浏览测试） |
| 判题服务 | http://localhost:8080/health | FastAPI 判题引擎健康检查 |

### 11.3 各服务说明

| 容器 | 镜像/构建 | 端口映射 | 说明 |
|------|-----------|----------|------|
| sql-oj-frontend | 由 `sql-oj-frontend/Dockerfile` 构建 | 8090 → 80 | Node 构建产物 + Nginx，反代 `/api`、`/admin` 到后端 |
| sql-oj-backend | 由根目录 `Dockerfile` 构建 | 8000 → 8000 | 入口脚本等待 MySQL、执行迁移后启动 Django |
| sql-oj-judge-service | 由 `judge_service/Dockerfile` 构建 | 8080 → 8080 | FastAPI 判题服务 |
| sql-oj-judge-db | postgres:15-alpine | 仅容器网络 | 判题数据库（tmpfs，容器重建即重置） |
| sql-oj-mysql | mysql:8.4 | 仅容器网络 | 业务数据库（数据持久化在 mysql-data 卷；Django 6.x 要求 MySQL ≥ 8.4） |

容器间通过服务名互相访问：前端 Nginx → `backend:8000`，后端 → `judge-service:8080`，判题服务 → `judge-db:5432`，后端 → `mysql:3306`。

### 11.4 配置项

镜像中不含任何账号密码，全部通过环境变量注入，可在项目根目录创建 `.env` 覆盖默认值：

```powershell
copy .env.example .env
```

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MYSQL_DATABASE` | `sql_oj_db` | 业务数据库名 |
| `MYSQL_ROOT_PASSWORD` | `sql_oj` | MySQL root 密码（后端同样使用） |
| `JUDGE_DB_NAME` / `JUDGE_DB_USER` / `JUDGE_DB_PASSWORD` | `judge_db` / `judge_user` / `judge_pass` | 判题数据库 |
| `DJANGO_SECRET_KEY` | 内置开发密钥 | 生产环境请替换 |
| `DJANGO_DEBUG` | `True` | 生产环境建议设为 `False` |
| `DJANGO_ALLOWED_HOSTS` | `*` | 逗号分隔 |

后端支持的连接类环境变量（容器内已自动配置）：`MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`JUDGE_SERVICE_URL`。

### 11.5 常用命令

```powershell
docker compose ps                 # 查看容器状态
docker compose logs -f backend    # 查看后端日志
docker compose down               # 停止并移除容器（保留数据卷）
docker compose down -v            # 停止并删除数据卷（清空 MySQL 数据）
docker compose up -d --build      # 重新构建并启动
```

### 11.6 导入预置题目（可选）

容器启动后即可导入（需要一名教师账号作为题目作者，默认取 ID=1；命令是幂等的，已存在的同名题目会自动跳过）：

```powershell
docker compose exec backend python manage.py import_exercises --teacher-id=1
```

> 若系统内还没有教师账号：可先注册一个教师账号（仅初始化阶段允许自助注册），或在教师端「账号管理」中新建一个教师账号，再把 `--teacher-id` 换成该账号的 ID。

### 11.7 构建产物说明

| 文件 | 作用 |
|------|------|
| `docker-compose.yml`（根目录） | 五个服务的编排定义 |
| `Dockerfile`（根目录） | 后端镜像（Django），含入口脚本 |
| `entrypoint.sh`（根目录） | 后端容器启动脚本：等待 MySQL → migrate → runserver |
| `judge_service/Dockerfile` | 判题服务镜像（FastAPI） |
| `sql-oj-frontend/Dockerfile` | 前端镜像（Node 构建 + Nginx） |
| `sql-oj-frontend/nginx.conf` | 前端 Nginx 配置（SPA 回退 + API 反代） |
| `.env.example`（根目录） | compose 环境变量示例 |
| `.dockerignore`（各处） | 缩小构建上下文 |

---

## 12 ARM64（aarch64）镜像打包与部署

默认构建出的镜像是宿主架构（通常 amd64）。若要部署到 **ARM64 的 Linux 机器**，可用 buildx 交叉构建并导出为离线镜像包。

> 注意：`docker-compose.yml` 中 `judge-service` 已固定 `platform: linux/amd64`（原因是判题镜像曾出现"在 amd64 主机上运行 arm64 镜像、靠 QEMU 模拟导致判题变慢"的情况）。若在 ARM64 机器上使用本仓库的 compose 部署，请先删除或修改该 `platform:` 行，否则判题服务会以模拟方式运行。

### 12.1 构建并导出 ARM64 镜像

```powershell
# 交叉构建三个应用镜像（--platform 指定目标架构，前端会自动用宿主架构跑 Node 构建）
docker buildx build --platform linux/arm64 --load -t sql-oj-backend .
docker buildx build --platform linux/arm64 --load -t sql-oj-judge-service ./judge_service
docker buildx build --platform linux/arm64 --load -t sql-oj-frontend ./sql-oj-frontend

# 导出运行所需镜像（含基础镜像，便于离线重建）
docker save --platform linux/arm64 -o sql-oj-images-arm64.tar `
  sql-oj-backend sql-oj-judge-service sql-oj-frontend `
  mysql:8.4 postgres:15-alpine python:3.12-slim nginx:alpine
```

> 说明：前端 `Dockerfile` 的构建阶段使用 `FROM --platform=$BUILDPLATFORM node:20-alpine`，
> 静态资源与 CPU 架构无关，交叉构建时 Node 仍在宿主架构上运行，避免 QEMU 模拟导致构建缓慢。

### 12.2 在 ARM64 机器上部署

```bash
docker load -i sql-oj-images-arm64.tar
docker compose up -d        # 镜像已就绪，不会重新构建
```

验证：

```bash
docker image inspect sql-oj-backend --format '{{.Os}}/{{.Architecture}}'   # 应输出 linux/arm64
curl http://localhost:8080/health
```

### 12.3 说明

- 导出的 tar 中已核对所有镜像的 `architecture` 为 `arm64`（`variant: v8`）。
- 若目标机器已有外网，也可直接在该机器上执行 `docker compose up -d --build` 自行构建，无需离线包。
- 离线**重建**镜像还需 `node:20-alpine` 的 arm64 版本（仅构建阶段使用，运行不需要）。
- 注意：交叉构建会把本机 `sql-oj-backend` 等 tag 指向 arm64 镜像。若要在本机继续以 amd64 运行，
  执行 `docker compose build` 重新构建一次即可恢复；运行中的容器不受影响。


