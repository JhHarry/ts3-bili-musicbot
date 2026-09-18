#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# 体检对象：
#   TeamSpeak 3 Server 私有许可     https://www.teamspeak.com   （随包分发，使用即接受其条款）
#   TS3AudioBot        OSL-3.0      https://github.com/Splamy/TS3AudioBot
#   ffmpeg             LGPL/GPL     https://ffmpeg.org
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

# TS3 服务器全面优化体检
# 用法: sudo bash audit.sh 1|2|3
SEC="${1:-1}"
H(){ echo; echo "──── $* ────"; }

if [ "$SEC" = "1" ]; then
H "A. 系统概况"
echo "  发行版   : $(. /etc/os-release; echo $PRETTY_NAME)"
echo "  内核     : $(uname -r)  架构 $(uname -m)"
echo "  虚拟化   : $(systemd-detect-virt 2>/dev/null || echo unknown)"
echo "  CPU      : $(lscpu | awk -F: '/Model name/{print $2}' | xargs)"
echo "  核数     : $(nproc)  主频 $(lscpu | awk -F: '/MHz/{print $2}' | xargs | cut -d' ' -f1) MHz"
echo "  开机     : $(uptime -s)   已运行 $(uptime -p)"
echo "  当前时间 : $(date '+%F %T %Z')"

H "B. CPU / 负载"
echo "  负载      : $(cut -d' ' -f1-3 /proc/loadavg)"
echo "  运行/阻塞 : $(awk '{print "runnable="$1" blocked="$2}' /proc/loadavg | tr ' ' '\n' | tail -2 | tr '\n' ' ')"
echo "  上下文切换: $(awk '/ctxt/{print $2}' /proc/stat) 次"
echo "  中断      : $(awk '/intr/{print $2}' /proc/stat) 次"
echo "  CPU 时间分布(%)："
grep '^cpu ' /proc/stat | awk '{t=$2+$3+$4+$5+$6+$7+$8; printf "    user %.1f  nice %.1f  sys %.1f  idle %.1f  iowait %.1f  irq %.1f  softirq %.1f  steal %.1f\n", $2/t*100,$3/t*100,$4/t*100,$5/t*100,$6/t*100,$7/t*100,$8/t*100,($9+$10)/t*100}'
echo "  --- 单核明细 ---"
grep '^cpu[0-9]' /proc/stat | awk '{t=$2+$3+$4+$5+$6+$7+$8; printf "    %s  idle %.1f%%  iowait %.1f%%  steal %.1f%%\n", $1, $5/t*100, $6/t*100, ($9+$10)/t*100}'

H "C. 内存 / 交换"
free -m | sed 's/^/  /'
echo "  --- 关键项 ---"
awk '/^(MemTotal|MemFree|MemAvailable|Cached|Buffers|Dirty|Writeback|SwapTotal|SwapFree|Shmem|Slab|SReclaimable|SUnreclaim|Committed_AS|CommitLimit):/{printf "    %-18s %8.1f MB\n",$1,$2/1024}' /proc/meminfo
echo "  --- 压力与风险 ---"
echo "    swappiness      : $(cat /proc/sys/vm/swappiness)  （默认60；小内存机建议 10~30）"
echo "    overcommit_memory: $(cat /proc/sys/vm/overcommit_memory)"
echo "    min_free_kbytes : $(cat /proc/sys/vm/min_free_kbytes)"
echo "    OOM 事件累计    : $(dmesg 2>/dev/null | grep -ci 'out of memory' || echo 0)"
echo "    swap 换入/换出  : $(awk '/pswpin/{print $2" / "$3}' /proc/vmstat)"
echo "    pgmajfault(缺页): $(awk '/pgmajfault/{print $2}' /proc/vmstat)"
echo "  --- TOP5 内存进程 ---"
ps -eo rss,pcpu,pmem,etime,comm --sort=-rss --no-headers | head -5 | awk '{printf "    %7.1fMB  CPU%-5s MEM%-5s 运行%-12s %s\n",$1/1024,$2,$3,$4,$5}'
echo "  --- zram/swap 设备 ---"
swapon --show 2>/dev/null | sed 's/^/    /' || echo "    无"
lsblk -o NAME,SIZE,ROTA,TYPE,MOUNTPOINT 2>/dev/null | sed 's/^/    /'

H "D. 磁盘 / I-O"
df -hT | grep -vE 'tmpfs|^Filesystem' | sed 's/^/  /'
echo "  --- inode ---"
df -i | grep -vE 'tmpfs|^Filesystem' | sed 's/^/  /'
echo "  --- 最大目录 TOP8 ---"
du -shx /* 2>/dev/null | sort -rh | head -8 | sed 's/^/  /'
echo "  --- I/O 统计 (iostat 替代) ---"
awk 'NR>2 && $1!="loop"{printf "    %-8s 读%8.1fMB 写%8.1fMB  在途%4d  利用率%5.1f%%\n",$3,$6/2048,$10/2048,$9,$NF}' /proc/diskstats 2>/dev/null | head -4
cat /proc/pressure/io 2>/dev/null | sed 's/^/    PSI-io: /'
cat /proc/pressure/cpu 2>/dev/null | sed 's/^/    PSI-cpu: /'
cat /proc/pressure/memory 2>/dev/null | sed 's/^/    PSI-mem: /'
echo "  --- fstab ---"
grep -v '^#' /etc/fstab | grep -v '^$' | sed 's/^/    /'
fi

if [ "$SEC" = "2" ]; then
H "E. 网络"
echo "  --- 接口流量（自开机） ---"
for i in $(ls /sys/class/net | grep -v lo); do
  awk -v I="$i" '$0 ~ I":" {printf "    %-8s RX %.2f GB  TX %.2f GB\n", I, $2/1073741824, $10/1073741824}' /proc/net/dev
done
echo "  --- TCP 调优参数 ---"
for k in net.ipv4.tcp_congestion_control net.core.default_qdisc net.ipv4.tcp_rmem net.ipv4.tcp_wmem \
         net.core.rmem_max net.core.wmem_max net.ipv4.tcp_fastopen net.ipv4.tcp_slow_start_after_idle \
         net.ipv4.tcp_mtu_probing net.ipv4.tcp_notsent_lowat net.core.somaxconn net.ipv4.tcp_max_syn_backlog; do
  printf "    %-42s %s\n" "$k" "$(sysctl -n $k 2>/dev/null)"
done
echo "  --- 可用拥塞算法 ---"
echo "    $(sysctl -n net.ipv4.tcp_available_congestion_control 2>/dev/null)"
echo "    BBR 是否可加载: $(modprobe tcp_bbr 2>&1 && echo 可加载 || echo 不可用)"
echo "  --- TCP 连接与重传 ---"
echo "    已建立: $(ss -tan state established | wc -l)   TIME_WAIT: $(ss -tan state time-wait | wc -l)"
awk '/^Tcp:/{printf "    重传 %s 段  无效 %s  丢失 %s\n",$10,$11,$3}' /proc/net/snmp | tail -1
echo "  --- 监听端口（对外） ---"
ss -tulnp | grep -vE '127\.0\.0\.|\[::1\]|%lo' | tail -n +2 | awk '{printf "    %-6s %-22s %s\n",$1,$5,$7}' | sed 's/users:((//;s/))//'

H "F. 服务健康"
echo "  失败单元: $(systemctl --failed --no-legend 2>/dev/null | wc -l)"
systemctl --failed --no-legend 2>/dev/null | sed 's/^/    ⚠️ /'
echo "  --- 关键服务 ---"
for s in teamspeak3 ts3audiobot bili-proxy ts3bot-watchdog.timer vnstat sshd; do
  st=$(systemctl is-active $s); en=$(systemctl is-enabled $s 2>/dev/null)
  mem=$(systemctl show $s -p MemoryCurrent --value 2>/dev/null)
  [ "$mem" = "[not set]" ] && mem=0
  rst=$(systemctl show $s -p NRestarts --value 2>/dev/null)
  printf "    %-22s %-8s %-9s 内存%7.1fMB  重启%s次\n" "$s" "$st" "$en" "$(echo "$mem/1048576" | bc -l 2>/dev/null || echo 0)" "$rst"
done
echo "  --- 全部运行中的单元 ---"
systemctl list-units --type=service --state=running --no-legend 2>/dev/null | awk '{printf "    %-34s %s\n",$1,$4}'
echo "  --- 定时器 ---"
systemctl list-timers --no-legend 2>/dev/null | head -8 | sed 's/^/    /'
fi

if [ "$SEC" = "3" ]; then
H "G. 安全与更新"
echo "  待更新包 : $(apt list --upgradable 2>/dev/null | tail -n +2 | wc -l)"
echo "  安全更新 : $(apt-get -s upgrade 2>/dev/null | grep -ci '^Inst.*security')"
echo "  自动更新 : $(systemctl is-active unattended-upgrades 2>&1) / $(systemctl is-enabled unattended-upgrades 2>&1)"
echo "  --- SSH 配置 ---"
sshd -T 2>/dev/null | grep -E 'permitrootlogin|passwordauthentication|pubkeyauthentication|port |maxauthtries|logingracetime' | sed 's/^/    /'
echo "  --- 失败登录尝试 ---"
journalctl -u ssh --since '-7 days' --no-pager 2>/dev/null | grep -ci 'failed password' | sed 's/^/    失败密码次数: /'
journalctl -u ssh --since '-7 days' --no-pager 2>/dev/null | grep -ci 'invalid user' | sed 's/^/    无效用户次数: /'
echo "  --- sudo 用户 ---"
getent group sudo google-sudoers 2>/dev/null | sed 's/^/    /'
echo "  --- 定时任务 ---"
crontab -l 2>/dev/null | grep -v '^#' | sed 's/^/    /' || echo "    无用户 crontab"
ls /etc/cron.d/ 2>/dev/null | sed 's/^/    /'

H "H. 日志与崩溃（关键）"
echo "  journal 大小: $(journalctl --disk-usage | grep -oE '[0-9.]+[MG]')"
echo "  --- TS3AudioBot 近 6 小时崩溃计数 ---"
for p in '3 hours ago' '6 hours ago' '12 hours ago' '24 hours ago'; do
  n=$(journalctl -u ts3audiobot --since "$p" --no-pager 2>/dev/null | grep -cE 'NullReference|FATAL|Critical')
  r=$(journalctl -u ts3audiobot --since "$p" --no-pager 2>/dev/null | grep -c 'Started TS3AudioBot')
  printf "    自 %-14s : 崩溃关键词 %-3s 次 | 重启 %s 次\n" "$p" "$n" "$r"
done
echo "  --- 当前机器人运行时长 ---"
echo "    进程启动: $(ps -o lstart= -C TS3AudioBot 2>/dev/null | xargs)"
echo "  --- 各服务近 24h 错误行数 ---"
for s in teamspeak3 ts3audiobot bili-proxy; do
  n=$(journalctl -u $s --since '-24 hours' -p err --no-pager 2>/dev/null | grep -v '^-- ' | wc -l)
  printf "    %-16s %s 条\n" "$s" "$n"
done
echo "  --- dmesg 异常 ---"
dmesg --level=err,warn 2>/dev/null | tail -8 | sed 's/^/    /'

H "I. 内核参数建议核对"
chk(){ printf "    %-44s 当前=%-12s %s\n" "$1" "$(sysctl -n $1 2>/dev/null)" "$2"; }
chk vm.swappiness          "小内存机可设 10（减少无谓换出）"
chk vm.dirty_ratio         "默认20；小盘可降到10减少卡顿"
chk vm.vfs_cache_pressure  "默认100"
chk net.core.somaxconn     "默认4096，够用"
chk net.ipv4.tcp_congestion_control "★ 跨洋链路上 BBR 通常显著优于 cubic"
chk net.core.default_qdisc "★ BBR 需配 fq"
chk net.core.rmem_max      "TS3 UDP 语音可适当加大"
chk fs.file-max            "默认够用"
chk vm.max_map_count       ".NET 程序可适当加大"
echo "  --- ulimit（当前 shell） ---"
ulimit -a | sed 's/^/    /'
echo "  --- systemd 全局限制 ---"
systemctl show -p DefaultLimitNOFILE -p DefaultTasksMax 2>/dev/null | sed 's/^/    /'
fi
