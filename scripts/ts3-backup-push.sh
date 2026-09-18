#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# 备份内容来自：
#   TS3AudioBot        OSL-3.0      https://github.com/Splamy/TS3AudioBot
#   SQLite (sqlite3)   Public Domain https://sqlite.org
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

# ts3-backup-push.sh —— 本地热备份 + 推送到异地（冷备份仓库）
# 用法: ts3-backup-push.sh
# 配置: /etc/ts3-backup.conf
set -uo pipefail

CONF=/etc/ts3-backup.conf
BACKUP_BIN=/usr/local/bin/ts3-backup.sh
LOG=/var/log/ts3-backup-push.log

# ── 读取配置
PUSH_TARGET=""
PUSH_LABEL="$(hostname -s)"
KEEP_LOCAL=3
PUSH_SSH_KEY=""
[ -f "$CONF" ] && . "$CONF"

# 组装 scp 参数（可选指定私钥，不指定则走默认 ssh 配置/agent）
SCP_OPTS="-o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new"
[ -n "$PUSH_SSH_KEY" ] && SCP_OPTS="-i $PUSH_SSH_KEY $SCP_OPTS"

mask() { sed -E 's#(ssh://)?([^@/]*@)?([^:/]*).*#\3#g' <<<"$1"; }

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

[ -x "$BACKUP_BIN" ] || { log "✗ 找不到 $BACKUP_BIN"; exit 1; }

# ── 1. 本地热备份
log "=== 开始：本地备份 (标签=$PUSH_LABEL) ==="
if ! "$BACKUP_BIN" "$PUSH_LABEL" >>"$LOG" 2>&1; then
  log "✗ 本地备份失败，终止"; exit 1
fi
ARCHIVE="/var/backups/ts3/latest-${PUSH_LABEL}.tar.gz"
[ -e "$ARCHIVE" ] || { log "✗ 备份产物不存在: $ARCHIVE"; exit 1; }
REAL=$(readlink -f "$ARCHIVE")
log "✓ 本地备份完成: $(basename "$REAL") ($(stat -c %s "$REAL") 字节)"

# ── 2. 推送到异地
if [ -z "$PUSH_TARGET" ]; then
  log "○ 未配置 PUSH_TARGET，跳过推送（纯本地备份模式）"
else
  HOST=$(mask "$PUSH_TARGET")
  log "→ 推送到 $HOST …"
  for i in 1 2 3; do
    if scp $SCP_OPTS "$REAL" "$PUSH_TARGET" >>"$LOG" 2>&1; then
      log "✓ 推送成功 ($(basename "$REAL"))"
      PUSHED=1; break
    fi
    log "  第 $i 次失败，5 秒后重试…"; sleep 5
  done
  [ "${PUSHED:-0}" = "1" ] || log "✗ 推送失败（本地备份仍在，下次会重试）"
fi

# ── 3. 本地保留策略（异地那份由对端自己管）
cd /var/backups/ts3 || { log "✗ 无法进入 /var/backups/ts3"; exit 1; }
ls -1t *.tar.gz 2>/dev/null | grep -v '^latest-' | tail -n +$((KEEP_LOCAL+1)) | while read -r old; do
  rm -f "$old"; log "  清理本地旧备份: $old"
done

log "=== 结束 ==="
