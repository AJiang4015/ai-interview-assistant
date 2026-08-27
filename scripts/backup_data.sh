#!/usr/bin/env bash
# data/ 目录备份脚本（FAISS 索引 + SQLite + ingest_state + 知识库）。
#
# 用法（Linux/部署机器，配合 cron 每天定时跑）：
#   0 2 * * * cd /path/to/RAGKonwLedge && scripts/backup_data.sh >> /var/log/rag-backup.log 2>&1
#
# 配置：
#   BACKUP_ROOT  备份存放目录，默认 <项目根>/backups（已在 .gitignore 忽略）
#   KEEP         保留最近 N 份备份，默认 7
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$PROJECT_DIR/data"
BACKUP_ROOT="${BACKUP_ROOT:-$PROJECT_DIR/backups}"
KEEP="${KEEP:-7}"

if [ ! -d "$DATA_DIR" ]; then
  echo "[backup] data dir missing: $DATA_DIR" >&2
  exit 1
fi

mkdir -p "$BACKUP_ROOT"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="$BACKUP_ROOT/data_${STAMP}.tar.gz"

# 打包整个 data 目录（含隐藏文件如 .gitkeep 不影响）
tar -czf "$OUT_FILE" -C "$PROJECT_DIR" data
echo "[backup] wrote $OUT_FILE"

# 清理旧备份，仅保留最近 KEEP 份
count=0
for f in $(ls -1t "$BACKUP_ROOT"/data_*.tar.gz 2>/dev/null; true); do
  count=$((count + 1))
  if [ "$count" -gt "$KEEP" ]; then
    rm -f "$f"
    echo "[backup] removed old $f"
  fi
done

echo "[backup] done"