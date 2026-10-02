# SQL Online Judge — 判题服务镜像（FastAPI + psycopg2）
# 构建：docker build -t sql-oj-judge-service ./judge_service（或 `docker compose build judge-service`）
# 说明：判题库连接信息通过环境变量注入（见 docker-compose.yml）；本目录 .env 由 .dockerignore 排除
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先安装依赖，充分利用镜像层缓存
COPY requirements_judge.txt ./
RUN pip install -r requirements_judge.txt

# 拷贝源码（.dockerignore 已排除 .env 与本地开发/压测脚本）
COPY . .

EXPOSE 8080

# 健康检查：探测 /health，供 docker-compose 的 depends_on: service_healthy 判断「判题服务已可接单」
# （python:3.12-slim 没有 curl，用标准库发请求即可）
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2).status == 200 else 1)"

# judge_service_new.py 内部以 0.0.0.0:8080 启动 uvicorn
CMD ["python", "judge_service_new.py"]
