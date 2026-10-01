# SQL 判题服务镜像（FastAPI + psycopg2）
# 构建：docker build -t sql-oj-judge-service ./judge_service
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先安装依赖，充分利用镜像层缓存
COPY requirements_judge.txt ./
RUN pip install --no-cache-dir -r requirements_judge.txt

# 拷贝源码（.env 由 .dockerignore 排除，配置通过 compose 的环境变量注入）
COPY . .

EXPOSE 8080

# judge_service_new.py 内部以 0.0.0.0:8080 启动 uvicorn
CMD ["python", "judge_service_new.py"]
