#!/bin/bash

# ============================================================
# BrickCore - 快速重启脚本
# 适用：服务器上拉取最新代码后快速更新前后端
# 用法：./restart.sh [backend|frontend|nginx|all]
#
# 环境变量：
#   GIT_BRANCH=main          覆盖自动检测的远程分支
#   AUTO_AERICH=1            后端启动后自动执行 aerich upgrade
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

MODE="${1:-all}"
AUTO_AERICH="${AUTO_AERICH:-0}"

OLD_HEAD=""
NEW_HEAD=""

# 检查参数
if [[ "$MODE" != "backend" && "$MODE" != "frontend" && "$MODE" != "nginx" && "$MODE" != "all" ]]; then
    echo "用法: ./restart.sh [backend|frontend|nginx|all]"
    echo "  backend  - 只更新并重建后端容器"
    echo "  frontend - 只构建前端并重启 Nginx（服务器内存不足时可能失败）"
    echo "  nginx    - 重建 Nginx（force-recreate，可应用新 volume）"
    echo "  all      - 完整更新前后端（默认）"
    echo ""
    echo "环境变量: AUTO_AERICH=1 GIT_BRANCH=..."
    exit 1
fi

log_info() { echo "      $*"; }
log_warn() { echo "[WARN] $*"; }
log_error() { echo "[ERROR] $*"; }

echo "=========================================="
echo "  模式: $MODE"
echo "  开始更新并重启服务"
echo "=========================================="

# 1. 拉取最新代码（nginx 模式可跳过）
if [ "$MODE" != "nginx" ]; then
    echo "[1] 拉取最新代码..."
    git checkout -- deploy.sh restart.sh 2>/dev/null || true
    OLD_HEAD=$(git rev-parse HEAD 2>/dev/null || echo "")

    GIT_BRANCH="${GIT_BRANCH:-}"
    if [ -z "$GIT_BRANCH" ]; then
        GIT_BRANCH=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')
    fi
    if [ -z "$GIT_BRANCH" ]; then
        if git ls-remote --exit-code --heads origin master >/dev/null 2>&1; then
            GIT_BRANCH=master
        elif git ls-remote --exit-code --heads origin main >/dev/null 2>&1; then
            GIT_BRANCH=main
        else
            GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
        fi
    fi
    log_info "远程分支: $GIT_BRANCH"

    if ! git fetch origin "$GIT_BRANCH"; then
        log_error "git fetch origin $GIT_BRANCH 失败，已中止，未重启服务"
        exit 1
    fi
    if ! git reset --hard "origin/$GIT_BRANCH"; then
        log_error "无法同步到 origin/$GIT_BRANCH，已中止，未重启服务"
        exit 1
    fi
    NEW_HEAD=$(git rev-parse HEAD)
    log_info "当前版本: $(git rev-parse --short HEAD) $(git log -1 --format='%s')"
    if [ -n "$OLD_HEAD" ] && [ "$OLD_HEAD" != "$NEW_HEAD" ]; then
        echo "      本次更新涉及文件:"
        git diff --name-status "$OLD_HEAD" "$NEW_HEAD" | while IFS= read -r line; do
            echo "        $line"
        done
    else
        log_info "代码已是最新，无文件变更"
    fi
    chmod +x restart.sh deploy.sh 2>/dev/null || true
fi

# 2. 构建前端
if [ "$MODE" == "frontend" ] || [ "$MODE" == "all" ]; then
    echo "[2] 构建前端..."
    cd frontend
    npm install

    memory_kb=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    swap_kb=$(grep SwapTotal /proc/meminfo | awk '{print $2}')
    if [ "$memory_kb" -lt 2097152 ] && [ "$swap_kb" -eq 0 ]; then
        log_warn "服务器内存不足 2G 且没有 swap，npm run build 可能会被系统杀死。"
        log_warn "建议本地构建 dist 后上传，或增加 swap。"
    fi

    npm run build
    cd ..
fi

# 3. 重启后端
if [ "$MODE" == "backend" ] || [ "$MODE" == "all" ]; then
    echo "[3] 重建并重启后端..."
    BUILD_NO_CACHE=""
    if [ -n "$OLD_HEAD" ] && [ -n "$NEW_HEAD" ] && [ "$OLD_HEAD" != "$NEW_HEAD" ]; then
        if git diff --name-only "$OLD_HEAD" "$NEW_HEAD" | grep -qE '^backend/requirements.txt$|^backend/Dockerfile$|^backend/docker_install_deps.sh$'; then
            log_info "检测到依赖/Dockerfile 变更，使用 --no-cache 重建（仅此情况全量重建）"
            BUILD_NO_CACHE="--no-cache"
        else
            log_info "仅代码变更，使用缓存增量构建（省时间）"
        fi
    fi

    if ! docker compose build $BUILD_NO_CACHE backend; then
        log_error "后端镜像构建失败"
        exit 1
    fi
    if ! docker compose up -d --force-recreate backend; then
        log_error "后端容器启动失败"
        exit 1
    fi

    if [ "$AUTO_AERICH" = "1" ]; then
        echo "      执行数据库迁移..."
        docker compose exec -T backend aerich upgrade || log_warn "aerich upgrade 失败，请手动检查"
    else
        log_info "如需迁移: AUTO_AERICH=1 ./restart.sh backend  或 docker compose exec backend aerich upgrade"
    fi
fi

# 4. 重建 Nginx（需 recreate：仅 restart 不会应用新 volume/端口等 compose 变更）
if [ "$MODE" == "frontend" ] || [ "$MODE" == "nginx" ] || [ "$MODE" == "all" ]; then
    echo "[4] 重建 Nginx..."
    if ! docker compose up -d --force-recreate nginx; then
        log_error "Nginx 重建失败"
        exit 1
    fi
fi

echo ""
echo "=========================================="
echo "  重启完成"
echo "=========================================="
echo "  前端: http://$(curl -s --max-time 3 ifconfig.me 2>/dev/null || echo '你的服务器IP')"
echo "  后端: http://$(curl -s --max-time 3 ifconfig.me 2>/dev/null || echo '你的服务器IP'):8000"
echo "=========================================="
