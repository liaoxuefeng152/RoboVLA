# RoboVLA V2.0 Vue3 前端构建 + Nginx 部署
FROM node:18-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci --registry=https://registry.npmmirror.com

COPY . .
RUN npm run build

# --- 生产 Nginx 镜像 ---
FROM nginx:alpine

# 时区设置
RUN apk add --no-cache tzdata && \
    cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && \
    echo "Asia/Shanghai" > /etc/timezone

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD curl -f http://localhost:80/ || exit 1

EXPOSE 80 443
CMD ["nginx", "-g", "daemon off;"]
