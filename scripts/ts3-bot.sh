#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# 被管理的服务：
#   TS3AudioBot        OSL-3.0      https://github.com/Splamy/TS3AudioBot
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

# ts3-bot.sh —— 音乐机器人（TS3AudioBot + B站代理）控制
# 用法: ts3-bot.sh <start|stop|restart|status|freeze|thaw>
#
#   start   启动整套（含开机自启）
#   stop    停止（保留开机自启设置）
#   freeze  冷冻：停止 + 关闭开机自启  ← "冷备"用这个
#   thaw    解冻：恢复开机自启 + 启动
#   status  查看状态
set -uo pipefail

SVCS_HOT="bili-proxy ts3audiobot"
TIMER="ts3bot-watchdog.timer"
SVC_ALL="$SVCS_HOT $TIMER"

c_reset='\033[0m'; c_ok='\033[32m'; c_warn='\033[33m'; c_err='\033[31m'; c_dim='\033[2m'
ok()   { printf "  ${c_ok}✓${c_reset} %s\n" "$*"; }
warn() { printf "  ${c_warn}!${c_reset} %s\n" "$*"; }
err()  { printf "  ${c_err}✗${c_reset} %s\n" "$*"; }

need_root() { [ "$(id -u)" = "0" ] || { err "需要 root：sudo $0 $*"; exit 1; }; }

do_status() {
  echo "── 服务状态 ──"
  for s in $SVC_ALL teamspeak3; do
    st=$(systemctl is-active "$s" 2>/dev/null)
    en=$(systemctl is-enabled "$s" 2>/dev/null)
    [ "$st" = "active" ] && printf "  %-24s ${c_ok}%-10s${c_reset} 自启=%s\n" "$s" "$st" "$en" \
                         || printf "  %-24s ${c_dim}%-10s${c_reset} 自启=%s\n" "$s" "$st" "$en"
  done
  echo "── 进程 ──"
  P=$(pgrep -x TS3AudioBot | head -1)
  if [ -n "$P" ]; then
    rss=$(ps -o rss= -p "$P" | tr -d ' ')
    up=$(ps -o etime= -p "$P" | xargs)
    printf "  机器人 PID=%-8s 运行=%-12s 内存=%.0fMB\n" "$P" "$up" "$(awk -v r="$rss" 'BEGIN{print r/1024}')"
  else
    echo "  机器人未运行"
  fi
  echo "── 播放 ──"
  if pgrep -x ffmpeg >/dev/null; then ok "正在播放"; else echo "  未在播放"; fi
  echo "── 剩余内存 ──"
  free -m | awk '/Mem:/{printf "  可用 %.0fMB / 共 %.0fMB\n",$7,$2}'
}

case "${1:-status}" in
  start)
    need_root "$@"
    echo "启动音乐机器人…"
    systemctl start bili-proxy && ok "bili-proxy" || err "bili-proxy"
    sleep 1
    systemctl start ts3audiobot && ok "ts3audiobot" || err "ts3audiobot"
    systemctl start "$TIMER" 2>/dev/null && ok "watchdog.timer" || warn "watchdog.timer"
    sleep 3; echo; do_status ;;
  stop)
    need_root "$@"
    echo "停止音乐机器人（保留自启设置）…"
    systemctl stop "$TIMER" 2>/dev/null && ok "watchdog.timer" || true
    systemctl stop ts3audiobot 2>/dev/null && ok "ts3audiobot" || true
    systemctl stop bili-proxy  2>/dev/null && ok "bili-proxy" || true
    echo; do_status ;;
  freeze)
    need_root "$@"
    echo "冷冻音乐机器人（停 + 关自启）…"
    systemctl stop "$TIMER" 2>/dev/null; systemctl disable "$TIMER" 2>/dev/null && ok "watchdog.timer 已停用"
    systemctl stop ts3audiobot 2>/dev/null; systemctl disable ts3audiobot 2>/dev/null && ok "ts3audiobot 已停用"
    systemctl stop bili-proxy  2>/dev/null; systemctl disable bili-proxy  2>/dev/null && ok "bili-proxy 已停用"
    echo
    warn "机器人已冷冻：重启机器后不会自动拉起。需要时执行：sudo $0 thaw"
    echo; do_status ;;
  thaw)
    need_root "$@"
    echo "解冻音乐机器人（恢复自启 + 启动）…"
    systemctl enable bili-proxy ts3audiobot "$TIMER" >/dev/null 2>&1 && ok "自启已恢复"
    systemctl start bili-proxy; sleep 1
    systemctl start ts3audiobot
    systemctl start "$TIMER" 2>/dev/null
    sleep 3; echo; do_status ;;
  restart)
    need_root "$@"
    systemctl restart bili-proxy; sleep 1; systemctl restart ts3audiobot; sleep 3
    do_status ;;
  status|*)
    do_status ;;
esac
