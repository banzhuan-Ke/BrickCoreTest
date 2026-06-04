#!/bin/bash
# ============================================================
# MySQL 备份脚本（Docker Compose 部署）
# 用法:
#   ./scripts/backup-mysql.sh
#   ./scripts/backup-mysql.sh --keep 14
#   MYSQL_ROOT_PASSWORD=xxx ./scripts/backup-mysql.sh
# 建议: chmod +x scripts/backup-mysql.sh
#       crontab: 0 3 * * * /opt/autotest/scripts/backup-mysql.sh --keep 14 >> /root/backups/backup.log 2>&1
# ============================================================

set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/autotest}"
BACKUP_DIR="${BACKUP_DIR:-/root/backups}"
DB_NAME="${DB_NAME:-fastapi}"
KEEP_DAYS="${KEEP_DAYS:-0}"

# 与 docker-compose.yml 默认一致；生产环境可 export MYSQL_ROOT_PASSWORD=...
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-Secur3Root!2026#Hz}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

usage() {
    cat <<'EOF'
用法: backup-mysql.sh [选项]

选项:
  --keep N    保留最近 N 天备份，删除更早的 fastapi_*.sql（默认 0=不删）
  -h, --help  显示帮助

环境变量:
  PROJECT_DIR          项目目录（默认 /opt/autotest）
  BACKUP_DIR           备份输出目录（默认 /root/backups）
  MYSQL_ROOT_PASSWORD  MySQL root 密码
  DB_NAME              数据库名（默认 fastapi）
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --keep)
            KEEP_DAYS="${2:-0}"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log_error "未知参数: $1"
            usage
            exit 1
            ;;
    esac
done

if [[ ! -f "$PROJECT_DIR/docker-compose.yml" ]]; then
    log_error "未找到 $PROJECT_DIR/docker-compose.yml，请设置 PROJECT_DIR"
    exit 1
fi

if ! docker compose -f "$PROJECT_DIR/docker-compose.yml" ps --status running mysql 2>/dev/null | grep -q mysql; then
    log_error "MySQL 容器未运行，请先: cd $PROJECT_DIR && docker compose up -d mysql"
    exit 1
fi

mkdir -p "$BACKUP_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="$BACKUP_DIR/fastapi_${TS}.sql"

log_info "开始备份 $DB_NAME -> $OUT_FILE"

docker compose -f "$PROJECT_DIR/docker-compose.yml" exec -T mysql \
    mysqldump -uroot -p"${MYSQL_ROOT_PASSWORD}" \
    --single-transaction --routines --triggers "$DB_NAME" \
    > "$OUT_FILE"

if [[ ! -s "$OUT_FILE" ]]; then
    rm -f "$OUT_FILE"
    log_error "备份失败：输出文件为空，请检查 root 密码与 MySQL 状态"
    exit 1
fi

SIZE="$(du -h "$OUT_FILE" | awk '{print $1}')"
log_info "备份成功: $OUT_FILE ($SIZE)"

if [[ "$KEEP_DAYS" =~ ^[0-9]+$ ]] && [[ "$KEEP_DAYS" -gt 0 ]]; then
    DELETED="$(find "$BACKUP_DIR" -maxdepth 1 -name 'fastapi_*.sql' -type f -mtime +"$KEEP_DAYS" -print -delete | wc -l)"
    if [[ "$DELETED" -gt 0 ]]; then
        log_info "已删除 ${KEEP_DAYS} 天前的备份 ${DELETED} 个"
    fi
fi

log_info "最近备份:"
ls -lh "$BACKUP_DIR"/fastapi_*.sql 2>/dev/null | tail -3 || true
