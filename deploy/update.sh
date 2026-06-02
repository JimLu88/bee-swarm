#!/bin/sh
# H-SEMAS 群晖定时自动更新脚本
# 作用: 拉取主仓库 + 爬虫仓库最新代码 → 重建并滚动重启容器 (UI/手机端随之联动更新)。
# 用法: 群晖「控制面板 → 任务计划 → 新增 → 计划的任务 → 用户定义脚本」, 每天凌晨跑一次:
#   sh /volume1/docker/h-semas/deploy/update.sh >> /volume1/docker/h-semas/deploy/update.log 2>&1
#
# 前提: 主仓库(h-semas)、爬虫(AI 数据爬虫)、记忆中心(AI 记忆中心) 并排克隆在同一父目录下。
set -e

# 本脚本位于 <repo>/deploy/update.sh → REPO = 上一级
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PARENT_DIR="$(cd "$REPO_DIR/.." && pwd)"

echo "===== $(date '+%Y-%m-%d %H:%M:%S') 开始自动更新 ====="

# 1) 拉主仓库 + 各并排子仓库 (存在才拉; 单个失败不影响其它)
echo "[1/2] 拉取各仓库最新代码"
git -C "$REPO_DIR" pull --ff-only || echo "  (主仓库 pull 失败, 用现有代码继续)"
for sub in "AI 数据爬虫" "AI 记忆中心"; do
  if [ -d "$PARENT_DIR/$sub/.git" ]; then
    echo "  - 拉取: $sub"
    git -C "$PARENT_DIR/$sub" pull --ff-only || echo "    ($sub pull 失败, 跳过)"
  else
    echo "  - 跳过(未克隆): $sub"
  fi
done

# 2) 重建并重启 (仅重建有变化的层, --build 拉新代码进镜像)
echo "[2/2] docker compose 重建 + 重启"
cd "$REPO_DIR"
docker compose up -d --build

echo "===== $(date '+%Y-%m-%d %H:%M:%S') 更新完成 ====="
