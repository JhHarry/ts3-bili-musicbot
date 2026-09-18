#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# 仅做文件轮转，无第三方依赖
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

# ts3-backup-prune.sh —— 冷备份仓库保留策略（在 GCP 上跑）
# 用法: ts3-backup-prune.sh [目录] [保留份数]
set -uo pipefail

DIR="${1:-/var/backups/ts3-from-sh}"
KEEP="${2:-7}"
LOG=/var/log/ts3-backup-prune.log

log() { echo "[$(date '+%F %T')] $*" ; }

mkdir -p "$DIR"
cd "$DIR" || exit 1

TOTAL=$(ls -1 *.tar.gz 2>/dev/null | wc -l)
log "仓库: $DIR  现有 $TOTAL 份  保留策略: $KEEP 份"

if [ "$TOTAL" -gt "$KEEP" ]; then
  ls -1t *.tar.gz 2>/dev/null | tail -n +$((KEEP+1)) | while read -r old; do
    sz=$(stat -c %s "$old" 2>/dev/null || echo 0)
    rm -f "$old"
    log "  已清理: $old ($sz 字节)"
  done
fi

# 汇总
echo
echo "── 冷备份仓库现状 ──"
if [ -z "$(ls -A "$DIR" 2>/dev/null)" ]; then
  echo "  (空)"
else
  ls -1t *.tar.gz 2>/dev/null | while read -r f; do
    printf "  %-40s %8s 字节  %s\n" "$f" "$(stat -c %s "$f")" "$(stat -c %y "$f" | cut -d. -f1)"
  done
  echo "  ────────────────────────────────"
  echo "  合计: $(ls -1 *.tar.gz 2>/dev/null | wc -l) 份, $(du -sh "$DIR" | cut -f1)"
fi
