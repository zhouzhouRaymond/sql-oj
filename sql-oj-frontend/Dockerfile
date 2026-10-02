# SQL Online Judge — 前端镜像（Vue 3 + Vite 构建，Nginx 托管）
# 构建：docker build -t sql-oj-frontend ./sql-oj-frontend（或 `docker compose build frontend`）

# ---------- 构建阶段 ----------
# 使用 BUILDPLATFORM：静态资源与 CPU 架构无关，交叉构建（如 --platform linux/arm64）时
# 让 Node 在宿主架构上运行，避免在 QEMU 模拟下编译，可大幅提速并可产出正确的目标平台镜像。
FROM --platform=$BUILDPLATFORM node:20-alpine AS build
WORKDIR /app

# 先安装依赖，充分利用镜像层缓存：
# 有 package-lock.json 时用 npm ci（严格按锁文件安装、结果可复现），否则退回 npm install
COPY package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# 拷贝源码并构建静态产物到 /app/dist
# 说明：这里直接调用 vite build，只产出运行所需的静态资源；
# 类型检查由本地/CI 的 `npm run build`（vue-tsc + vite build）负责，
# 这样镜像构建不会被类型问题阻塞，构建也更快。
COPY . .
RUN npx vite build

# ---------- 运行阶段（目标平台，如 linux/arm64）----------
FROM nginx:alpine

# 自定义 Nginx 配置：SPA 回退 + 反向代理后端 /api、/admin、/static
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 拷贝构建产物
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
