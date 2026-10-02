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

![答题1](./images/AnswerQuestion1.png)

判题机制允许学生输出的行、列顺序与标准答案不同，只要内容语义一致即判定通过，提升判题的灵活性和公平性。测试中可提交不同的正确答案，下图中输出结果与标准答案分别存在列、行顺序的不同，均判为正确。

![答题2](./images/AnswerQuestion2.png)
![答题3](./images/AnswerQuestion3.png)

#### 5.2.2 查看提交记录

在"提交记录"页面可查看历史提交，以列表形式呈现每次提交对应的题目ID、判题结果（ACCEPTED / WRONG_ANSWER / ERROR / TIMEOUT）、得分和提交时间。点击"查看详情"可查看提交的完整SQL。

![提交记录](./images/Submissions.png)

#### 5.2.3 参加考试

在考试面板中查看考试列表，过去时段的考试显示"已结束"，未来时段的考试显示"未开始"，已经参加过的考试不能重复参加。显示"进行中"的考试当前可参加，点击"进入考试"。

![学生端考试列表](./images/Exams_student.png)

考试过程中阅读每道题目，编写SQL语句，答题完成后点击"提交试卷"，系统集中判题。右上角有考试倒计时（固定为2小时），到时间则自动交卷。

![参加考试](./images/Exams_student2.png)

交卷后系统反馈考试结果，包括总分、正确题目数以及每道题的答题详情，可查看自己提交的SQL。

![考试结果](./images/ExamResult.png)

参加过的考试都会显示在"考试记录"中，点击"查看详情"可查看考试结果。

![考试记录](./images/ExamRecords.png)

#### 5.2.4 个人统计

在个人中心可查看个人信息与统计数据。可修改个人信息中的邮箱。个人数据包括提交总次数、通过率、通过题目数和最近提交记录，其中通过率=个人通过次数/个人提交次数×100%.

![学生个人中心](./images/PersonalCenter_student.png)

### 5.3 教师端操作

#### 5.3.1 题目管理

在题目列表页面显示题目ID、名称和难度标签，教师可对题目进行创建、查看、编辑、删除操作。

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

教师可创建考试，设定考试名称、起止时间、从题库中选择题目并分配分值。

![教师创建考试](./images/CreateExam.png)

在"考试管理"页面，教师可查看自己创建的考试，但不能看到其他教师的考试。列表中显示考试ID、名称、起止时间和总分。教师可删除考试，或进行编辑修改。

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

### 6.1 认证接口（无需登录）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/auth/register/ | 用户注册 |
| POST | /api/auth/login/ | 登录，返回 JWT Token |
| POST | /api/auth/refresh/ | 刷新 Token |

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
| GET | /api/questions/{id}/ | 题目详情 | 登录用户 |
| PUT | /api/questions/{id}/ | 修改题目 | 教师 |
| DELETE | /api/questions/{id}/ | 删除题目 | 教师 |

### 6.4 考试管理

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | /api/exams/ | 考试列表 | 登录用户 |
| POST | /api/exams/ | 创建考试 | 教师 |
| GET | /api/exams/{id}/ | 考试详情 | 登录用户 |
| PUT | /api/exams/{id}/ | 修改考试 | 教师 |
| DELETE | /api/exams/{id}/ | 删除考试 | 教师 |
| POST | /api/exams/{id}/start/ | 开始考试 | 学生 |
| POST | /api/exams/{id}/submit/ | 提交试卷 | 学生 |
| GET | /api/exams/{id}/result/ | 考试排名 | 登录用户 |

### 6.5 提交判题

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | /api/submissions/submit/ | 提交 SQL 判题 | 登录用户 |
| GET | /api/submissions/ | 提交历史 | 登录用户 |
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


