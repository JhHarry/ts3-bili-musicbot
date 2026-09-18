#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# 备份内容来自：
#   TS3AudioBot        OSL-3.0      https://github.com/Splamy/TS3AudioBot
#   TeamSpeak 3 Server 私有许可     https://www.teamspeak.com   （随包分发，使用即接受其条款）
#   SQLite (sqlite3)   Public Domain https://sqlite.org
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

# ts3-backup.sh —— TS3 + 机器人 全量热备份（不停服）
# 用法: ts3-backup.sh [标签]   标签默认 local
# 产物: /var/backups/ts3/<标签>-<时间戳>.tar.gz
set -euo pipefail

LABEL="${1:-local}"
TS3_DIR=/opt/teamspeak3-server
BOT_DIR=/opt/ts3bot
DEST=/var/backups/ts3
STAGE=$(mktemp -d /var/tmp/ts3bk.XXXXXX)
KEEP=7
MAX_GB="${MAX_GB:-10}"          # 总大小上限（GB）—— 超过就从最旧的开始删
TS="$(date +%Y%m%d-%H%M%S)"

log() { echo "[$(date '+%F %T')] $*"; }
cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

# 没有 TS3 实例就直接退出（例如 GCP 已转为纯冷备仓库、本机不再跑 TS3）
if [ ! -f "$TS3_DIR/ts3server.sqlitedb" ]; then
  log "=== 跳过：找不到 $TS3_DIR/ts3server.sqlitedb ==="
  log "    本机没有 TS3 实例可备份（纯冷备仓库模式）"
  exit 0
fi

mkdir -p "$DEST"
log "=== 开始备份 (标签=$LABEL) ==="

# ── 1. TS3 数据库：在线安全备份（WAL 模式下必须用 .backup，不能 cp）
log "[1/6] sqlite3 .backup 数据库（在线）"
sqlite3 "$TS3_DIR/ts3server.sqlitedb" ".backup $STAGE/ts3server.sqlitedb"
INT=$(sqlite3 "$STAGE/ts3server.sqlitedb" "PRAGMA integrity_check;")
[ "$INT" = "ok" ] || { log "✗ 数据库完整性检查失败: $INT"; exit 1; }
log "      integrity_check = ok ($(stat -c %s "$STAGE/ts3server.sqlitedb") 字节)"
# 清掉校验过程中 sqlite 生成的 WAL 脚手架 —— .backup 产物本身已是自洽独立库，
# 留着 -wal/-shm 反而可能在还原时引入不一致
sqlite3 "$STAGE/ts3server.sqlitedb" "PRAGMA wal_checkpoint(TRUNCATE);" >/dev/null 2>&1
rm -f "$STAGE/ts3server.sqlitedb-shm" "$STAGE/ts3server.sqlitedb-wal"

# ── 2. 服务器身份密钥（缺了客户端书签会报"身份变更"）
log "[2/6] ssh_host_rsa_key"
cp -a "$TS3_DIR/ssh_host_rsa_key" "$STAGE/" 2>/dev/null || log "      (无，跳过)"

# ── 3. 频道上传文件
log "[3/6] files/ 上传文件"
cp -a "$TS3_DIR/files" "$STAGE/files" 2>/dev/null || mkdir -p "$STAGE/files"

# ── 4. 查询访问控制
for f in query_ip_allowlist.txt query_ip_denylist.txt; do
  [ -f "$TS3_DIR/$f" ] && cp -a "$TS3_DIR/$f" "$STAGE/" || true
done

# ── 5. 机器人配置（只收配置，不收 300MB 的二进制）
log "[4/6] 机器人配置 + 脚本"
mkdir -p "$STAGE/bot"
for f in ts3audiobot.toml rights.toml NLog.config bili_proxy.py \
         bili_cookies.txt query.pw relay.env play_relay.py ts3-admin.py rebuild-layout.py; do
  [ -f "$BOT_DIR/$f" ] && cp -a "$BOT_DIR/$f" "$STAGE/bot/" || true
done
[ -d "$BOT_DIR/bots" ] && cp -a "$BOT_DIR/bots" "$STAGE/bot/" 2>/dev/null || true
mkdir -p "$STAGE/bin"
for f in /usr/local/bin/ts3bot-watchdog.sh /usr/local/bin/ts3bot-autoresume.py /usr/local/bin/audit.sh; do
  [ -f "$f" ] && cp -a "$f" "$STAGE/bin/" || true
done

# ── 6. systemd 单元 + 结构快照 + 清单
log "[5/6] systemd 单元 + 结构快照"
mkdir -p "$STAGE/systemd"
cp -a /etc/systemd/system/teamspeak3.service       "$STAGE/systemd/" 2>/dev/null || true
cp -a /etc/systemd/system/ts3audiobot.service      "$STAGE/systemd/" 2>/dev/null || true
cp -a /etc/systemd/system/ts3audiobot.service.d    "$STAGE/systemd/" 2>/dev/null || true
cp -a /etc/systemd/system/bili-proxy.service       "$STAGE/systemd/" 2>/dev/null || true
cp -a /etc/systemd/system/ts3bot-watchdog.service  "$STAGE/systemd/" 2>/dev/null || true
cp -a /etc/systemd/system/ts3bot-watchdog.timer    "$STAGE/systemd/" 2>/dev/null || true

cat > "$STAGE/MANIFEST.txt" <<EOF
备份标签    : $LABEL
备份时间    : $(date '+%F %T %Z')
主机名      : $(hostname)
TS3 二进制  : $(sha256sum "$TS3_DIR/ts3server" 2>/dev/null | cut -c1-16) / $(stat -c %s "$TS3_DIR/ts3server") 字节
TS3 状态    : $(systemctl is-active teamspeak3)
机器人状态  : $(systemctl is-active ts3audiobot)
数据库大小  : $(stat -c %s "$STAGE/ts3server.sqlitedb") 字节
频道数      : $(sqlite3 "$STAGE/ts3server.sqlitedb" "SELECT COUNT(*) FROM channels;" 2>/dev/null)
注册客户端  : $(sqlite3 "$STAGE/ts3server.sqlitedb" "SELECT COUNT(*) FROM clients;" 2>/dev/null)
服务器组    : $(sqlite3 "$STAGE/ts3server.sqlitedb" "SELECT COUNT(*) FROM groups_server;" 2>/dev/null)
频道组      : $(sqlite3 "$STAGE/ts3server.sqlitedb" "SELECT COUNT(*) FROM groups_channel;" 2>/dev/null)
特权密钥    : $(sqlite3 "$STAGE/ts3server.sqlitedb" "SELECT COUNT(*) FROM tokens;" 2>/dev/null)
封禁条目    : $(sqlite3 "$STAGE/ts3server.sqlitedb" "SELECT COUNT(*) FROM bans;" 2>/dev/null)
EOF

log "      systemd 单元: $(ls "$STAGE/systemd" 2>/dev/null | wc -l) 个"

# ── 6.5 采集流量/资源数据（异地推送通知要用；没有该脚本就跳过）──
if [ -x /usr/local/bin/ts3-stats.sh ]; then
  /usr/local/bin/ts3-stats.sh > /dev/null 2>&1 || true
  if [ -f /var/tmp/ts3-stats.json ]; then
    cp /var/tmp/ts3-stats.json "$STAGE/STATS.json"
    log "      已采集 STATS.json（流量/内存/磁盘）"
  fi
fi

# 打包
log "[6/6] 打包"
OUT="$DEST/${LABEL}-${TS}.tar.gz"
tar czf "$OUT" -C "$STAGE" .
log "      产物: $OUT  ($(stat -c %s "$OUT") 字节)"

# 保留策略①：份数上限（排除 latest-* 符号链接，只对真实归档计数）
cd "$DEST"
ls -1t *.tar.gz 2>/dev/null | grep -v '^latest-' | tail -n +$((KEEP+1)) | while read -r old; do
  rm -f "$old"; log "      清理旧备份: $old"
done

# 保留策略②：总大小上限 MAX_GB（从最旧的开始删，但至少留 3 份）
total_now() { ls -1 *.tar.gz 2>/dev/null | grep -v '^latest-' | xargs -r stat -c %s 2>/dev/null | awk '{s+=$1} END{printf "%.0f", s+0}'; }
LIMIT=$(awk -v g="$MAX_GB" 'BEGIN{printf "%.0f", g*1024*1024*1024}')
TOTAL=$(total_now || true); TOTAL=${TOTAL:-0}
if [ "$TOTAL" -gt "$LIMIT" ]; then
  log "      总大小 $((TOTAL/1048576))MB 超上限 ${MAX_GB}GB → 继续清理"
  ls -1t *.tar.gz 2>/dev/null | grep -v '^latest-' | tail -n +4 | while read -r old; do
    rm -f "$old"; log "        清理(超容量): $old"
    T=$(total_now || true)
    [ "${T:-0}" -le "$LIMIT" ] && break
  done
else
  log "      总大小 $((TOTAL/1048576))MB，未超 ${MAX_GB}GB 上限"
fi

# 写最新指针
ln -sf "$(basename "$OUT")" "$DEST/latest-${LABEL}.tar.gz"

log "=== 完成，当前保留 $(ls -1 "$DEST"/*.tar.gz 2>/dev/null | grep -vc '/latest-') 份 ==="
