#!/bin/bash

# ============================================================
# FastAPI UI 测试平台 - 快速重启脚本
# 适用：服务器上拉取最新代码后快速更新前后端
# 用法：./restart.sh [backend|frontend|nginx|all]
# ============================================================

cd /opt/autotest || exit 1

MODE="${1:-all}"

# 检查参数
if [[ "$MODE" != "backend" && "$MODE" != "frontend" && "$MODE" != "nginx" && "$MODE" != "all" ]]; then
    echo "用法: ./restart.sh [backend|frontend|nginx|all]"
    echo "  backend  - 只更新并重建后端容器"
    echo "  frontend - 只构建前端并重启 Nginx（服务器内存不足时可能失败）"
    echo "  nginx    - 只重启 Nginx"
    echo "  all      - 完整更新前后端（默认）"
    exit 1
fi

echo "=========================================="
echo "  模式: $MODE"
echo "  开始更新并重启服务"
echo "=========================================="

# 1. 拉取最新代码（nginx 模式可跳过）
# 部署机与远程不一致时（如 force-push），用 fetch + reset 对齐 origin/main
if [ "$MODE" != "nginx" ]; then
    echo "[1/3] 拉取最新代码..."
    git checkout -- deploy.sh restart.sh 2>/dev/null
    OLD_HEAD=$(git rev-parse HEAD 2>/dev/null || echo "")
    if ! git fetch origin main; then
        echo "[ERROR] git fetch 失败，已中止，未重启服务"
        exit 1
    fi
    if ! git reset --hard origin/main; then
        echo "[ERROR] 无法同步到 origin/main，已中止，未重启服务"
        exit 1
    fi
    NEW_HEAD=$(git rev-parse HEAD)
    echo "      当前版本: $(git rev-parse --short HEAD) $(git log -1 --format='%s')"
    if [ -n "$OLD_HEAD" ] && [ "$OLD_HEAD" != "$NEW_HEAD" ]; then
        echo "      本次更新涉及文件:"
        git diff --name-status "$OLD_HEAD" "$NEW_HEAD" | while IFS= read -r line; do
            echo "        $line"
        done
        echo "      提交说明:"
        git log --oneline "$OLD_HEAD..$NEW_HEAD" | while IFS= read -r line; do
            echo "        $line"
        done
    else
        echo "      代码已是最新，无文件变更"
    fi
    # 仓库内脚本应带可执行位；若历史提交未标记 +x，拉取后在此自愈
    chmod +x restart.sh deploy.sh 2>/dev/null
fi

# 2. 构建前端（backend / nginx 模式跳过）
if [ "$MODE" == "frontend" ] || [ "$MODE" == "all" ]; then
    echo "[2/3] 构建前端..."
    cd frontend
    npm install

    # 检查服务器内存，如果小于 2G 且没有 swap，提示可能构建失败
    memory_kb=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    swap_kb=$(grep SwapTotal /proc/meminfo | awk '{print $2}')
    if [ "$memory_kb" -lt 2097152 ] && [ "$swap_kb" -eq 0 ]; then
        echo "[WARN] 服务器内存不足 2G 且没有 swap，npm run build 可能会被系统杀死。"
        echo "       建议先在本地 Windows 构建 dist 目录后上传到服务器覆盖。"
        echo "       或者先执行以下命令增加 swap："
        echo "         dd if=/dev/zero of=/swapfile bs=1M count=2048"
        echo "         chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile"
    fi

    npm run build
    if [ $? -ne 0 ]; then
        echo "[ERROR] 前端构建失败，请检查上面的错误信息。"
        echo "        如果是 'Killed'，说明内存不足，请参考上面的建议。"
        exit 1
    fi
    cd ..
fi

# 3. 重启后端（frontend / nginx 模式跳过）
if [ "$MODE" == "backend" ] || [ "$MODE" == "all" ]; then
    echo "[3/3] 重启后端..."
    if ! docker compose up -d --build backend; then
        echo "[ERROR] 后端容器启动失败"
        exit 1
    fi
    echo "      建议执行数据库迁移: docker compose exec backend aerich upgrade"
fi

# 4. 重启 Nginx（backend 模式跳过）
if [ "$MODE" == "frontend" ] || [ "$MODE" == "nginx" ] || [ "$MODE" == "all" ]; then
    echo "[3/3] 重启 Nginx..."
    docker compose restart nginx
fi

echo ""
echo "=========================================="
echo "  重启完成"
echo "=========================================="
echo "  前端: http://$(curl -s ifconfig.me || echo '你的服务器IP')"
echo "  后端: http://$(curl -s ifconfig.me || echo '你的服务器IP'):8000"
echo "=========================================="
