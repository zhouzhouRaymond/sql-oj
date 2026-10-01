#!/bin/sh
# 后端容器入口：等待 MySQL 就绪 -> 执行数据库迁移 -> 启动 Django 服务
# 所有连接参数均来自环境变量（默认值面向 docker-compose 网络内的服务名）
set -e

MYSQL_HOST="${MYSQL_HOST:-mysql}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-}"
MYSQL_DATABASE="${MYSQL_DATABASE:-sql_oj_db}"
MYSQL_WAIT_TIMEOUT="${MYSQL_WAIT_TIMEOUT:-60}"

export MYSQL_HOST MYSQL_PORT MYSQL_USER MYSQL_PASSWORD MYSQL_DATABASE MYSQL_WAIT_TIMEOUT

echo "[entrypoint] 等待 MySQL ${MYSQL_HOST}:${MYSQL_PORT} 就绪..."

python - <<'PY'
import os
import sys
import time

import pymysql

host = os.environ["MYSQL_HOST"]
port = int(os.environ["MYSQL_PORT"])
user = os.environ["MYSQL_USER"]
password = os.environ["MYSQL_PASSWORD"]
deadline = time.time() + int(os.environ["MYSQL_WAIT_TIMEOUT"])

while True:
    try:
        pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            connect_timeout=2,
            read_timeout=2,
            write_timeout=2,
        ).close()
        print("[entrypoint] MySQL 已就绪")
        break
    except Exception as exc:  # noqa: BLE001 - 就绪等待期间的任何异常都重试
        if time.time() >= deadline:
            print(f"[entrypoint] 等待 MySQL 超时: {exc}", file=sys.stderr)
            sys.exit(1)
        time.sleep(2)
PY

echo "[entrypoint] 执行数据库迁移..."
python manage.py migrate --noinput

echo "[entrypoint] 启动 Django 服务（0.0.0.0:8000）..."
exec python manage.py runserver 0.0.0.0:8000
