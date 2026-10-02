# SQL Online Judge — 后端镜像（Django + DRF + PyMySQL）
# 构建：docker build -t sql-oj-backend .            （或根目录 `docker compose build backend`）
# 说明：数据库连接、判题服务地址等均通过环境变量注入（见根目录 docker-compose.yml）
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先安装依赖，充分利用镜像层缓存（改源码不会触发重装）
# 依赖清单统一维护在 requirements.txt（含连接 MySQL 8.4 所需的 cryptography）
COPY requirements.txt ./
RUN pip install -r requirements.txt

# 拷贝项目源码：构建上下文已由 .dockerignore 收敛（不含 venv/dist/images/docs 及其他服务源码）
COPY . .

# 兜底：Windows 下检出可能带入 CRLF。.gitattributes 已统一为 LF，这里防止「非 git 拷贝」等场景，
# 保证 /bin/sh 能正常解析 entrypoint.sh
RUN sed -i 's/\r$//' /app/entrypoint.sh

EXPOSE 8000

# 入口脚本：等待 MySQL 就绪 -> 执行数据库迁移 -> 启动服务（见 entrypoint.sh）
ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
