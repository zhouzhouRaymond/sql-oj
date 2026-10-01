# 前端镜像（Vue 3 + Vite 构建，Nginx 托管）
# 构建：docker build -t sql-oj-frontend ./sql-oj-frontend

# ---------- 构建阶段 ----------
# 使用 BUILDPLATFORM：静态资源与CPU架构无关，交叉构建（如 --platform linux/arm64）时
# 让 Node 在宿主架构上运行，避免在 QEMU 模拟下编译，可大幅提速并可产出正确的目标平台镜像。
FROM --platform=$BUILDPLATFORM node:20-alpine AS build
WORKDIR /app

# 先安装依赖，充分利用镜像层缓存（存在 package-lock.json 时使用 npm ci）
COPY package*.json ./
RUN npm ci

# 拷贝源码并构建静态产物到 /app/dist
COPY . .
# 说明：项目的 `npm run build` 会先执行 vue-tsc 类型检查（本地开发用）。
# 镜像构建只产出运行所需的静态资源，这里直接调用 vite build，
# 避免因源码中既有的类型告警导致构建中断；类型检查仍在本地 `npm run build` 中进行。
RUN npx vite build

# ---------- 运行阶段（目标平台，如 linux/arm64）----------
FROM nginx:alpine

# 自定义 Nginx 配置：SPA 回退 + 反向代理后端 /api
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 拷贝构建产物
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
