# H-SEMAS 单容器: 先用 node 构建前端静态站(Next output:export), 再由后端(8100)统一托管 UI + API.
# 构建上下文 = 仓库根目录 (docker-compose: context: .). 这样一次 git pull + 重建即可同步 Web/手机端.

# ---- stage 1: 构建前端静态站 → out/ ----
FROM node:20-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
# Next 15 output:"export" → 静态文件输出到 /ui/out

# ---- stage 2: python 后端, 内嵌静态 UI ----
FROM python:3.11-slim
WORKDIR /app

# lxml/pandas 等部分包需要编译工具; 另装 Node (stdio 类 MCP: Airbnb/Google Maps 用 node 子进程)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# v13 #1: 预装 stdio MCP 服务包 (运行时不再联网下载 → 调用不卡). 失败不阻断构建 (运行时 npx -y 兜底).
RUN npm install -g @openbnb/mcp-server-airbnb || true

COPY backend/requirements.txt /app/requirements.txt
# 国内 NAS 直连 files.pythonhosted.org 慢/易超时 → 走阿里云 PyPI 镜像 + 重试/超时加长
RUN pip install --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --retries 5 --timeout 180 \
    -r /app/requirements.txt

COPY backend/ /app
# 把前端静态产物放进后端托管目录 (main.py 挂 StaticFiles(static_ui) 于 /)
COPY --from=ui /ui/out /app/app/static_ui

EXPOSE 8100

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
