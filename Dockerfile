# SQL Online Judge 后端镜像（Django + DRF + PyMySQL）
# 构建：docker build -t sql-oj-backend .
# 说明：业务数据库连接、判题服务地址等均通过环境变量注入（见根目录 docker-compose.yml）
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先安装依赖，充分利用镜像层缓存
COPY requirements.txt ./
# cryptography：PyMySQL 连接 MySQL 8.4 默认的 caching_sha2_password 认证所必需
RUN pip install --no-cache-dir -r requirements.txt cryptography

# 拷贝项目源码
COPY . .

# 兜底：Windows 下检出可能带入 CRLF，转换为 LF，避免 /bin/sh 解析失败
RUN sed -i 's/\r$//' /app/entrypoint.sh

EXPOSE 8000

# 入口脚本：等待 MySQL -> 数据库迁移 -> 启动服务
ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
