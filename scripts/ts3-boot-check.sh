#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# 被检查的服务：
#   TeamSpeak 3 Server 私有许可     https://www.teamspeak.com   （随包分发，使用即接受其条款）
#   TS3AudioBot        OSL-3.0      https://github.com/Splamy/TS3AudioBot
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

# 开机后 30 秒自检：把没起来的服务拉起来
sleep 30
LOG=/var/log/ts3-boot-check.log
echo "[$(date '+%F %T')] 开机自检" >> $LOG
for s in teamspeak3 bili-proxy ts3audiobot ts3bot-watchdog.timer ts3-backup-push.timer; do
  st=$(systemctl is-active $s 2>/dev/null)
  echo "  $s = $st" >> $LOG
  if [ "$st" != "active" ]; then
    systemctl start "$s" 2>/dev/null
    sleep 3
    echo "    → 已尝试拉起，现状态: $(systemctl is-active $s)" >> $LOG
  fi
done
echo "[$(date '+%F %T')] 自检完成" >> $LOG
