#!/bin/bash

# ============================================================
# BrickCore - 快速重启脚本
# 适用：服务器上拉取最新代码后快速更新前后端
# 用法：./restart.sh [backend|frontend|nginx|all]
#
# 环境变量：
#   GIT_BRANCH=main          覆盖自动检测的远程分支
#   AUTO_AERICH=1            后端启动后自动执行 aerich upgrade
#   SKIP_GIT=1               不拉代码，只重建/重启（本地调试）
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

MODE="${1:-all}"
AUTO_AERICH="${AUTO_AERICH:-0}"
SKIP_GIT="${SKIP_GIT:-0}"
TM_HOST_DIR="$SCRIPT_DIR/backend/ext_packages"
TM_BACKUP_DIR="$SCRIPT_DIR/.runtime/brickcore_tm_backup"

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
    echo "环境变量: AUTO_AERICH=1 GIT_BRANCH=... SKIP_GIT=1"
    exit 1
fi

log_info() { echo "      $*"; }
log_warn() { echo "[WARN] $*"; }
log_error() { echo "[ERROR] $*"; }

# 备份容器内「手装」brickcore_tm（site-packages），避免 force-recreate 丢失。
# Pro 内置包在镜像 /app/brickcore_tm，重建后仍在；CE 手装进 site-packages 的会被抹掉。
backup_installed_tm() {
    mkdir -p "$TM_BACKUP_DIR" "$TM_HOST_DIR"
    if ! docker compose ps --status running --services 2>/dev/null | grep -qx backend; then
        return 0
    fi
    log_info "检查是否需备份手装 brickcore_tm..."
    # 若已挂载到持久目录则无需备份
    if docker compose exec -T backend sh -c 'test -f /app/ext_packages/brickcore_tm/__init__.py' 2>/dev/null; then
        log_info "已存在 /app/ext_packages/brickcore_tm，跳过备份"
        return 0
    fi
    # 探测 site-packages 中的手装包（排除 /app/brickcore_tm 内置路径）
    local found
    found=$(docker compose exec -T backend python - <<'PY' 2>/dev/null || true
import brickcore_tm, pathlib
p = pathlib.Path(brickcore_tm.__file__).resolve().parent
# 内置：/app/brickcore_tm；手装常见：.../site-packages/brickcore_tm
s = str(p)
if s.startswith("/app/brickcore_tm") or "/ext_packages/" in s.replace("\\", "/"):
    raise SystemExit(0)
print(s)
PY
)
    if [ -z "${found:-}" ]; then
        return 0
    fi
    log_warn "检测到手装 brickcore_tm: $found"
    log_warn "将备份到 $TM_BACKUP_DIR 并同步到 backend/ext_packages（重建后保留）"
    rm -rf "$TM_BACKUP_DIR/brickcore_tm"
    if docker compose cp "backend:$found" "$TM_BACKUP_DIR/brickcore_tm" 2>/dev/null; then
        rm -rf "$TM_HOST_DIR/brickcore_tm"
        mkdir -p "$TM_HOST_DIR"
        cp -a "$TM_BACKUP_DIR/brickcore_tm" "$TM_HOST_DIR/brickcore_tm"
        log_info "已写入 $TM_HOST_DIR/brickcore_tm"
    else
        log_warn "docker compose cp 失败，请手动: docker cp <容器>:$found ./backend/ext_packages/"
    fi
}

check_tm_premium() {
    log_info "检查测试管理扩展包状态..."
    local i
    for i in 1 2 3 4 5 6 7 8 9 10; do
        if docker compose exec -T backend python - <<'PY' 2>/dev/null
from app.modules.test_management.premium_gateway import clear_tm_premium_cache, get_tm_premium_info
clear_tm_premium_cache()
info = get_tm_premium_info()
inst = bool(info.get("installed"))
compat = bool(info.get("compatible"))
ver = info.get("version") or "?"
plat = info.get("platform_version") or "?"
msg = info.get("message") or ""
print(f"installed={inst} compatible={compat} tm={ver} platform={plat}")
print(msg)
raise SystemExit(0 if (inst and compat) else 2)
PY
        then
            log_info "测试管理扩展包：已安装且与平台版本兼容"
            return 0
        fi
        status=$?
        if [ "$status" = "2" ]; then
            log_warn "测试管理扩展包未就绪或与平台版本不兼容（见上）。"
            log_warn "说明：多数情况下不是「被删掉」，而是平台升到 1.8.x 后旧包声明的兼容区间不含 1.8。"
            log_warn "Pro：拉最新代码重建 backend（内置 brickcore_tm 会随镜像更新）。"
            log_warn "CE：把 .bcpack 装到持久目录 /app/ext_packages 后重启，例如："
            log_warn "  docker cp brickcore_tm-*.bcpack \$(docker compose ps -q backend):/tmp/tm.bcpack"
            log_warn "  docker compose exec backend python tools/install_brickcore_tm.py /tmp/tm.bcpack"
            return 0
        fi
        sleep 2
    done
    log_warn "未能探测 premium-status（backend 可能仍在启动），可稍后访问 /test-management/premium-status"
}

echo "=========================================="
echo "  模式: $MODE"
echo "  开始更新并重启服务"
echo "=========================================="

# 1. 拉取最新代码（nginx 模式可跳过）
if [ "$MODE" != "nginx" ] && [ "$SKIP_GIT" != "1" ]; then
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
elif [ "$SKIP_GIT" = "1" ]; then
    log_info "[1] SKIP_GIT=1，跳过拉取代码"
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
    backup_installed_tm

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

    check_tm_premium
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
