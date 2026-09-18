#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# 还原对象：
#   TS3AudioBot        OSL-3.0      https://github.com/Splamy/TS3AudioBot
#   TeamSpeak 3 Server 私有许可     https://www.teamspeak.com   （随包分发，使用即接受其条款）
#   SQLite (sqlite3)   Public Domain https://sqlite.org
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

# ts3-restore.sh —— 从备份包还原 TS3 + 机器人
# 用法: ts3-restore.sh <备份包.tar.gz> [--yes]
# 不带 --yes 时先做 dry-run 预览，确认后再加 --yes 真正执行
set -euo pipefail

ARCHIVE="${1:?用法: ts3-restore.sh <备份包.tar.gz> [--yes]}"
CONFIRM="${2:-}"
TS3_DIR=/opt/teamspeak3-server
BOT_DIR=/opt/ts3bot
STAGE=$(mktemp -d /var/tmp/ts3rs.XXXXXX)
PRE=$(mktemp -d /var/tmp/ts3pre.XXXXXX)

log() { echo "[$(date '+%F %T')] $*"; }
die() { echo "[错误] $*" >&2; exit 1; }

[ -f "$ARCHIVE" ] || die "备份包不存在: $ARCHIVE"

log "=== TS3 还原 ==="
log "备份包: $ARCHIVE ($(stat -c %s "$ARCHIVE") 字节)"

# ── 解包并校验
log "[1/6] 解包 + 校验"
tar xzf "$ARCHIVE" -C "$STAGE"
[ -f "$STAGE/ts3server.sqlitedb" ] || die "备份包内没有 ts3server.sqlitedb"
INT=$(sqlite3 "$STAGE/ts3server.sqlitedb" "PRAGMA integrity_check;")
[ "$INT" = "ok" ] || die "数据库完整性检查失败: $INT"
CH=$(sqlite3 "$STAGE/ts3server.sqlitedb" "SELECT COUNT(*) FROM channels;")
log "      integrity_check=ok  频道数=$CH"

if [ -f "$STAGE/MANIFEST.txt" ]; then
  log "      ── 备份包清单 ──"
  sed 's/^/        /' "$STAGE/MANIFEST.txt"
fi

if [ "$CONFIRM" != "--yes" ]; then
  log ""
  log "*** DRY-RUN（未做任何修改）***"
  log "将执行："
  log "  1) 停 teamspeak3 / ts3audiobot / bili-proxy"
  log "  2) 现网数据先备份到 $PRE（安全网）"
  log "  3) 覆盖 $TS3_DIR 与 $BOT_DIR 的配置"
  log "  4) 重新启动服务"
  log "  5) 校验"
  log ""
  log "确认无误后重跑： $0 $ARCHIVE --yes"
  exit 0
fi

# ── ← 以下才真正改动
log "[2/6] 停服务"
for s in ts3bot-watchdog.timer ts3audiobot bili-proxy teamspeak3; do
  systemctl stop "$s" 2>/dev/null && log "      已停 $s" || true
done
sleep 2

# ── 现网快照（安全网）
log "[3/6] 现网数据快照 → $PRE"
sqlite3 "$TS3_DIR/ts3server.sqlitedb" ".backup $PRE/ts3server.sqlitedb" 2>/dev/null || true
cp -a "$TS3_DIR/ssh_host_rsa_key" "$PRE/" 2>/dev/null || true
tar czf "/var/backups/ts3/pre-restore-$(date +%Y%m%d-%H%M%S).tar.gz" -C "$PRE" . 2>/dev/null || true
log "      安全网已存到 /var/backups/ts3/"

# ── 还原 TS3
log "[4/6] 还原 TS3"
install -o ts3server -g ts3server -m 600 "$STAGE/ts3server.sqlitedb" "$TS3_DIR/ts3server.sqlitedb"
rm -f "$TS3_DIR/ts3server.sqlitedb-shm" "$TS3_DIR/ts3server.sqlitedb-wal" 2>/dev/null || true
[ -f "$STAGE/ssh_host_rsa_key" ] && install -o ts3server -g ts3server -m 600 "$STAGE/ssh_host_rsa_key" "$TS3_DIR/ssh_host_rsa_key"
[ -d "$STAGE/files" ] && cp -a "$STAGE/files/." "$TS3_DIR/files/" 2>/dev/null || true
for f in query_ip_allowlist.txt query_ip_denylist.txt; do
  [ -f "$STAGE/$f" ] && install -o ts3server -g ts3server -m 600 "$STAGE/$f" "$TS3_DIR/$f" || true
done
log "      ts3server.sqlitedb / ssh_host_rsa_key / files/ 已还原"

# ── 还原机器人配置
log "[5/6] 还原机器人配置"
if [ -d "$STAGE/bot" ]; then
  for f in "$STAGE"/bot/*; do
    bn=$(basename "$f")
    case "$bn" in
      bots) cp -a "$f/." "$BOT_DIR/bots/" 2>/dev/null || true ;;
      *)    cp -a "$f" "$BOT_DIR/$bn" 2>/dev/null || true ;;
    esac
  done
  log "      已还原 $(ls "$STAGE/bot" | wc -l) 项"
fi
[ -d "$STAGE/bin" ] && cp -a "$STAGE/bin/." /usr/local/bin/ 2>/dev/null && chmod 755 /usr/local/bin/ts3bot-*.sh /usr/local/bin/ts3bot-*.py 2>/dev/null || true
# ── systemd 单元：还原，但【必须重映射 User/Group】──
# 备份包里的单元带着【源机】的用户名（例如上一台机器的用户名），直接铺到目标机就会变成
# "Failed to determine credentials for user '<源机用户名>'" → 服务无限重启。
# 这里按本机实际情况重新指派：teamspeak3 用专用系统用户 ts3server，其余用本机运行用户。
if [ -d "$STAGE/systemd" ]; then
  RUN_USER=""
  for cand in "$( [ -f /etc/systemd/system/ts3audiobot.service ] && grep -oP '^User=\K.*' /etc/systemd/system/ts3audiobot.service | head -1 )" ubuntu "$(id -un 1000 2>/dev/null)" ts3bot; do
    [ -n "$cand" ] && id "$cand" >/dev/null 2>&1 && { RUN_USER="$cand"; break; }
  done
  [ -n "$RUN_USER" ] || { RUN_USER=ts3bot; id ts3bot >/dev/null 2>&1 || useradd -r -m -s /bin/bash ts3bot; }
  id ts3server >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin ts3server
  log "      systemd 单元 User 重映射 → ts3server（TS3）/ $RUN_USER（机器人、代理）"

  cp -a "$STAGE/systemd/." /etc/systemd/system/ 2>/dev/null || true
  for u in /etc/systemd/system/teamspeak3.service /etc/systemd/system/ts3audiobot.service \
           /etc/systemd/system/bili-proxy.service /etc/systemd/system/ts3bot-watchdog.service; do
    [ -f "$u" ] || continue
    case "$(basename "$u")" in
      teamspeak3.service) U=ts3server ;;
      *)                  U="$RUN_USER" ;;
    esac
    sed -i -E "s|^User=.*|User=$U|; s|^Group=.*|Group=$U|" "$u"
  done
  # drop-in 里也可能写着源机用户名（例如 Group=<源机用户名>）
  for f in $(grep -rlE '^(User|Group)=' /etc/systemd/system/*.service.d/ 2>/dev/null); do
    case "$f" in
      */teamspeak3.service.d/*) U=ts3server ;;
      *)                        U="$RUN_USER" ;;
    esac
    sed -i -E "s|^(User|Group)=.*|\1=$U|" "$f"
  done
  chown -R "$RUN_USER:$RUN_USER" /opt/ts3bot 2>/dev/null || true
  systemctl daemon-reload
fi

# ── 启动 + 校验
log "[6/6] 启动服务并校验"
systemctl start teamspeak3; sleep 6
systemctl start bili-proxy ts3audiobot 2>/dev/null || true; sleep 3
systemctl start ts3bot-watchdog.timer 2>/dev/null || true

echo
log "── 还原结果 ──"
for s in teamspeak3 ts3audiobot bili-proxy ts3bot-watchdog.timer; do
  printf "  %-24s %s\n" "$s" "$(systemctl is-active "$s" 2>/dev/null)"
done
sleep 3
if systemctl is-active --quiet teamspeak3; then
  log "  ✅ TS3 已上线，频道数: $(sqlite3 "$TS3_DIR/ts3server.sqlitedb" 'SELECT COUNT(*) FROM channels;' 2>/dev/null)"
  log "  监听端口: $(ss -lun 2>/dev/null | grep -c ':9987' ) 个 UDP 9987"
else
  log "  ❌ TS3 启动失败，查: journalctl -u teamspeak3 -n 50"
fi

rm -rf "$STAGE" "$PRE"
log "=== 还原结束 ==="
