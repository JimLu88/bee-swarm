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

# lxml/pandas 等部分包需要编译工具; 装完即清理, 控制镜像体积
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY backend/ /app
# 把前端静态产物放进后端托管目录 (main.py 挂 StaticFiles(static_ui) 于 /)
COPY --from=ui /ui/out /app/app/static_ui

EXPOSE 8100

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
