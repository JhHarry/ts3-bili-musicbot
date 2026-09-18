#!/bin/sh
# ──────────────────────────────────────────────────────────────────────────
# 被守护对象：
#   TS3AudioBot        OSL-3.0      https://github.com/Splamy/TS3AudioBot
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

# TS3 听歌机器人守护脚本：自动恢复服务、重启后自动续播、清理幽灵连接
LOG=/var/log/ts3bot-watchdog.log
say() { echo "$(date '+%F %T') $*" >> "$LOG"; }
RESTARTED=0

# 1) 代理不健康则重启
if ! systemctl is-active --quiet bili-proxy; then
    systemctl restart bili-proxy
    say "重启 bili-proxy"
fi

# 2) 机器人服务不健康则重启
if ! systemctl is-active --quiet ts3audiobot; then
    systemctl restart ts3audiobot
    say "重启 ts3audiobot（服务非 active）"
    RESTARTED=1
fi

# 3) 检测最近的崩溃（3 分钟内出现过 Critical program failure）-> 重启并清理幽灵
LATEST=$(ls -t /opt/ts3bot/logs/*.log 2>/dev/null | head -1)
if [ -n "$LATEST" ] && find "$LATEST" -mmin -3 >/dev/null 2>&1 && \
   grep -q "Critical program failure" "$LATEST" 2>/dev/null; then
    # 用标记文件避免同一份日志反复触发
    MARK=/var/tmp/.ts3bot_last_crash
    if [ ! -f "$MARK" ] || [ "$MARK" -ot "$LATEST" ]; then
        touch "$MARK"
        systemctl restart ts3audiobot
        say "检测到崩溃，已重启机器人"
        RESTARTED=1
    fi
fi

# 4) 让日志不要无限增长
tail -n 500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG" 2>/dev/null
# 清理 3 天前的机器人日志
find /opt/ts3bot/logs -name "*.log" -mtime +3 -delete 2>/dev/null

# 缓存超 2.5GB 时清理最旧文件
SZ=$(du -sm /var/tmp/ts3music 2>/dev/null | cut -f1)
if [ "${SZ:-0}" -gt 2500 ]; then
    ls -t /var/tmp/ts3music/*.m4a /var/tmp/ts3music/*.flac 2>/dev/null | tail -n +6 | xargs -r rm -f
fi

# 机器人内存超 450MB 自动重启（防长期运行 OOM）
BOTRSS=$(ps -eo rss,cmd | awk "/TS3AudioBot/ && !/awk/ {print int(\$1/1024); exit}")
if [ -n "$BOTRSS" ] && [ "$BOTRSS" -gt 450 ]; then
    systemctl restart ts3audiobot
    say "机器人内存 ${BOTRSS}MB 超限，已重启"
    RESTARTED=1
fi

# 5) 记录点播状态；若本分钟重启过机器人，则后台自动续播
#    （脚本自身也会检测 PID 变化，覆盖崩溃/手动重启等情况）
if [ "$RESTARTED" = "1" ]; then
    nohup setsid python3 /usr/local/bin/ts3bot-autoresume.py --force \
        >/dev/null 2>&1 </dev/null &
else
    nohup setsid python3 /usr/local/bin/ts3bot-autoresume.py \
        >/dev/null 2>&1 </dev/null &
fi

exit 0
