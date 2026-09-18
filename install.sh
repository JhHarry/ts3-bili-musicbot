#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# 本包集成的第三方组件：
#   TeamSpeak 3 Server 私有许可     https://www.teamspeak.com   （随包分发，使用即接受其条款）
#   TS3AudioBot        OSL-3.0      https://github.com/Splamy/TS3AudioBot
#   yt-dlp             Unlicense    https://github.com/yt-dlp/yt-dlp
#   ffmpeg             LGPL/GPL     https://ffmpeg.org
#   libssl1.1/libcrypto1.1  OpenSSL License  （.NET Core 3.1 运行依赖，随包分发）
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

# ============================================================
#  TeamSpeak 3 + B站听歌机器人  一键部署脚本（离线完整版）
#  适用：Ubuntu / Debian 全新服务器（x86_64）
#  用法：sudo bash install.sh
#
#  本包已内置（离线）：
#    · TeamSpeak 3 服务端 3.13.7
#    · TS3AudioBot（已打崩溃修复补丁的自编译版）
#    · libssl1.1 兼容层（.NET Core 3.1 依赖）
#    · B站音频代理 v4（边播边释放）
#    · yt-dlp 兜底
#  不依赖 GitHub / 外网下载即可完成部署。
# ============================================================
set -e
cd "$(dirname "$0")"
DIR="$(pwd)"

# ---------- 可调参数（可用环境变量覆盖） ----------
BOT_NAME="${BOT_NAME:-MusicBot🎵Bot}"              # 机器人昵称
SERVER_NAME="${SERVER_NAME:-My TeamSpeak Server}"  # 服务器名
SERVER_PW="${SERVER_PW:-}"                         # 服务器密码（连接时输入）；默认空 = 不需要密码
SECLEVEL="${SECLEVEL:-5}"                          # 身份安全等级（5=默认，8 会让新人连不上）
PROXY_PORT="${PROXY_PORT:-8087}"
TS3_PORT="${TS3_PORT:-9987}"
QUERY_PORT="${QUERY_PORT:-10011}"
PRIVATE_PW="${PRIVATE_PW:-}"                       # 私密房间密码；留空则不加密码
INSTALL_DIR=/opt/ts3bot
TS3_DIR=/opt/teamspeak3-server

say() { echo -e "\n\033[1;36m==> $*\033[0m"; }
die() { echo -e "\033[1;31m错误: $*\033[0m"; exit 1; }

[ "$(id -u)" = "0" ] || die "请用 root 运行：sudo bash install.sh"
[ "$(uname -m)" = "x86_64" ] || die "本脚本仅支持 x86_64（TS3 官方服务端只有 amd64 二进制）"

# ---------- 组件选择 ----------
# WITH_BOT=1 装全套（TS3 + B站点歌机器人）；WITH_BOT=0 只装 TS3 服务端。
# 也可以用环境变量直接指定，跳过提问：  sudo WITH_BOT=0 bash install.sh
WITH_BOT="${WITH_BOT:-}"
case "$WITH_BOT" in
    1|y|Y|yes|YES|true) WITH_BOT=1 ;;
    0|n|N|no|NO|false)  WITH_BOT=0 ;;
    "")
        if [ -t 0 ]; then
            echo
            echo -e "\033[1;36m==> 组件选择\033[0m"
            echo "    本脚本可以只装 TS3 语音服务器，也可以连 B站点歌机器人一起装。"
            printf "    是否安装 B站点歌机器人？[Y/n] "
            read -r _ANS || _ANS=""
            case "$_ANS" in n|N|no|No|NO) WITH_BOT=0 ;; *) WITH_BOT=1 ;; esac
        else
            WITH_BOT=1        # 非交互（脚本调用 / 管道）默认装全套
        fi
        ;;
    *) WITH_BOT=1 ;;
esac
if [ "$WITH_BOT" = "1" ]; then
    echo "    ✓ 安装内容：TeamSpeak 3 服务端 + B站点歌机器人（全套）"
else
    echo "    ✓ 安装内容：TeamSpeak 3 服务端（不含音乐机器人）"
fi

# ---------- 软件本体自检 ----------
# 仓库里【直接带着】TS3 服务端、yt-dlp、libssl1.1 兼容层（约 29 MB）。
# 音乐机器人是单个 97.5 MB 的文件（贴着 GitHub 的 100 MiB 单文件上限），
# 所以它单独放在 Release 附件里，克隆下来后由本脚本自动补齐。
VENDOR="$DIR/vendor"
mkdir -p "$VENDOR"

if   [ -d "$VENDOR/teamspeak3-server" ]; then :
elif [ -f "$VENDOR/teamspeak3-server.tar.bz2" ]; then :
else die "vendor/ 里找不到 TS3 服务端 —— 克隆不完整"; fi

if [ "$WITH_BOT" = "1" ] && [ ! -x "$VENDOR/TS3AudioBot" ]; then
    [ -f "$DIR/fetch-bot.sh" ] || die "缺少 vendor/TS3AudioBot，且找不到 fetch-bot.sh"
    say "缺少音乐机器人，自动下载（约 35~40 MB，只需一次）"
    bash "$DIR/fetch-bot.sh" || die "机器人下载失败 —— 可手动取附件解压成 vendor/TS3AudioBot"
fi

echo "    软件本体: $(du -sh "$VENDOR" 2>/dev/null | cut -f1) 已就位"

say "0/9 环境预检"
AVAIL_MB=$(df -Pm / | awk 'NR==2{print $4}')
MEM_MB=$(free -m | awk '/^Mem:/{print $2}')
echo "    磁盘可用: ${AVAIL_MB}MB   内存: ${MEM_MB}MB   架构: $(uname -m)"
[ "$AVAIL_MB" -ge 2000 ] || die "磁盘空间不足（需 ≥2GB，当前 ${AVAIL_MB}MB）"
if [ "$MEM_MB" -lt 900 ] && ! swapon --show 2>/dev/null | grep -q .; then
    echo "    ⚠️  内存偏低（<900MB）且无 swap，创建 2GB swapfile"
    fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
    chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

say "1/9 安装系统依赖"
export DEBIAN_FRONTEND=noninteractive
# 国内服务器如果 apt 很慢，可以取消下面这行注释换阿里云镜像源：
# sed -i 's|archive.ubuntu.com|mirrors.aliyun.com|g; s|security.ubuntu.com|mirrors.aliyun.com|g' /etc/apt/sources.list* 2>/dev/null || true
apt-get update -qq || die "apt 源更新失败 —— 检查网络，或换个镜像源（见本文件上方注释）"

# ── 依赖说明（都是踩过坑才加上的，别删）──
#   sqlite3        ts3-backup.sh 用 .backup 做在线热备份，缺了备份直接失败
#   libopus-dev    【注意不是 libopus0】.NET 加载的是不带版本号的 libopus.so，
#                  只有 -dev 包才提供那个软链；只装 libopus0 会导致
#                  "Failed to load library libopus" 然后机器人无限重启
#   libsodium23    .NET 运行时的加密依赖
#   xz-utils       fetch-bot.sh 用 tar -xJf 解 .tar.xz 附件，没它解不开
#   openssh-client 生成异地备份密钥（ssh-keygen）+ 推送（scp）；精简镜像可能没带
#   ca-certificates https 访问 GitHub / B站 接口要用
#   iproute2       ts3-restore.sh 用 ss 查端口
#   procps         ts3-bot.sh 用 pgrep，audit.sh 用 free/uptime
#   bc             audit.sh 算内存百分比（没装也不影响主流程，会降级成 0）
DEPS="curl wget tar bzip2 xz-utils ca-certificates python3 sqlite3 \
      openssh-client iproute2 procps bc"
[ "$WITH_BOT" = "1" ] && DEPS="$DEPS ffmpeg libopus0 libopus-dev libsodium23"

if ! apt-get install -y -qq $DEPS >/dev/null 2>&1; then
    # 很多镜像源的报错会被 -qq 吞掉，所以失败时再来一次并显示详情
    echo "    ⚠ 批量安装失败，重试并显示详情…"
    apt-get install -y $DEPS || die "依赖安装失败（上面有 apt 的报错原文）"
fi
echo "    系统依赖 ✓ ($DEPS)"

# pypinyin —— B站代理的「拼音/英文搜索」排序需要（可选；装不上只会让拼音查询
# 降级为精确匹配，其它功能不受影响，所以这里【不 die】）
if [ "$WITH_BOT" = "1" ] && ! python3 -c "import pypinyin" >/dev/null 2>&1; then
    apt-get install -y -qq python3-pypinyin >/dev/null 2>&1 || true
    if ! python3 -c "import pypinyin" >/dev/null 2>&1 && command -v pip3 >/dev/null 2>&1; then
        pip3 install -q --break-system-packages \
             -i https://pypi.tuna.tsinghua.edu.cn/simple pypinyin >/dev/null 2>&1 || true
    fi
    python3 -c "import pypinyin" >/dev/null 2>&1 \
      || echo "    ○ pypinyin 未装上（拼音搜歌会降级，其余功能不受影响）"
fi
if [ "$WITH_BOT" = "1" ]; then
    python3 -c "import pypinyin" >/dev/null 2>&1 && echo "    pypinyin ✓（拼音/英文搜歌可用）"
fi

# ── 前置命令自检：缺任何一个都立刻报出来，不让你装到一半才发现 ──
NEED_CMDS="curl wget tar xz bzip2 python3 sqlite3 ssh-keygen scp ss awk sed grep find"
[ "$WITH_BOT" = "1" ] && NEED_CMDS="$NEED_CMDS ffmpeg"
MISSING=""
for c in $NEED_CMDS; do
    command -v "$c" >/dev/null 2>&1 || MISSING="$MISSING $c"
done
if [ -n "$MISSING" ]; then
    echo
    echo "    ✗ 以下必要命令没有装上:$MISSING"
    echo "      请先手动安装再重跑本脚本，例如："
    echo "        apt-get update && apt-get install -y xz-utils openssh-client"
    die "前置软件不齐"
fi
echo "    前置命令自检 ✓（$NEED_CMDS 均已就位）"

# ---------- 运行用户 ----------
RUN_USER="${RUN_USER:-}"
if [ -z "$RUN_USER" ]; then
    if [ -n "$SUDO_USER" ] && [ "$SUDO_USER" != "root" ]; then RUN_USER="$SUDO_USER"
    elif id ubuntu >/dev/null 2>&1; then RUN_USER=ubuntu
    else RUN_USER=ts3bot; id ts3bot >/dev/null 2>&1 || useradd -r -m -s /bin/bash ts3bot; fi
fi
echo "    运行用户: $RUN_USER"

# ---------- 2. 探测公网 IP ----------
say "2/9 探测公网 IP"
PUBIP="${PUBIP:-$(curl -s --max-time 10 https://api.ipify.org || curl -s --max-time 10 ifconfig.me || true)}"
[ -n "$PUBIP" ] || die "无法获取公网 IP，请用 PUBIP=x.x.x.x 环境变量指定后重试"
echo "    公网 IP: $PUBIP"

# ---------- 3. 安装 TS3 服务端 ----------
say "3/9 安装 TeamSpeak 3 服务端"
TS3VER="${TS3VER:-3.13.7}"
if [ ! -x "$TS3_DIR/ts3server" ]; then
    # 先清掉可能的旧版本，再装到临时目录后整体搬过去（避免污染 /opt）
    rm -rf "$TS3_DIR"
    if [ -d "$DIR/vendor/teamspeak3-server" ]; then
        # ① 目录形态（本仓库的默认形态）：直接拷
        TMPX=$(mktemp -d /opt/.ts3x.XXXXXX)
        cp -a "$DIR/vendor/teamspeak3-server/." "$TMPX/"
        mv "$TMPX" "$TS3_DIR"
    else
        # ② tar.bz2 形态：优先用包内的，否则在线下载
        if [ -f "$DIR/vendor/teamspeak3-server.tar.bz2" ]; then
            cp "$DIR/vendor/teamspeak3-server.tar.bz2" /tmp/ts3.tar.bz2
        else
            curl -sL -o /tmp/ts3.tar.bz2 \
              "https://files.teamspeak-services.com/releases/server/${TS3VER}/teamspeak3-server_linux_amd64-${TS3VER}.tar.bz2"
        fi
        TMPX=$(mktemp -d /opt/.ts3x.XXXXXX)
        tar xjf /tmp/ts3.tar.bz2 -C "$TMPX"
        # 兼容两种包结构：带一层目录（teamspeak3-server/ 或 *_linux_amd64/）或直接铺开
        if   [ -d "$TMPX/teamspeak3-server" ]; then SRC="$TMPX/teamspeak3-server"
        elif [ -d "$TMPX/teamspeak3-server_linux_amd64" ]; then SRC="$TMPX/teamspeak3-server_linux_amd64"
        else SRC="$TMPX"; fi
        mv "$SRC" "$TS3_DIR"
        rm -rf "$TMPX" /tmp/ts3.tar.bz2
    fi
    [ -x "$TS3_DIR/ts3server" ] || { echo "    ✗ TS3 安装失败：$TS3_DIR/ts3server 不存在"; exit 1; }
    echo "    TS3 已就位: $(ls "$TS3_DIR" | wc -l) 个条目"
fi
id ts3server >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin ts3server
touch "$TS3_DIR/.ts3server_license_accepted"
chown -R ts3server:ts3server "$TS3_DIR"

install -m 644 "$DIR/systemd/teamspeak3.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable teamspeak3 >/dev/null 2>&1
systemctl restart teamspeak3
sleep 12

# 抓取首次生成的 ServerQuery 密码与管理员令牌
# ⚠ TS3 3.13.7 起这两个【不再写进 logs/ 文件】，而是打到 stdout（systemd 收进 journald）。
#   所以必须两处都读，只读日志文件会一个都抓不到 —— 那会导致下面的服务器属性校正被整段跳过。
read_ts3_output() {
    { for f in "$TS3_DIR"/logs/ts3server_*.log; do [ -f "$f" ] && cat "$f"; done
      journalctl -u teamspeak3 --no-pager -n 800 2>/dev/null
    } 2>/dev/null
}

QUERY_PASS=""; ADMIN_TOKEN=""
for _ in $(seq 1 10); do
    OUT=$(read_ts3_output)
    [ -n "$QUERY_PASS" ] || QUERY_PASS=$(printf '%s\n' "$OUT" | grep -oP 'password\s*=\s*"\K[^"]+' | tail -1)
    [ -n "$ADMIN_TOKEN" ] || ADMIN_TOKEN=$(printf '%s\n' "$OUT" | grep -oP 'token=\K\S+' | tail -1)
    # 令牌是虚拟服务器建好之后才生成的，比密码晚约 20~30 秒
    if [ -n "$QUERY_PASS" ] && [ -n "$ADMIN_TOKEN" ]; then break; fi
    sleep 5
done

# 重装场景：数据库里已经有密码了，不会再打印一次 → 沿用上次保存的
if [ -z "$QUERY_PASS" ] && [ -f "$INSTALL_DIR/query.pw" ]; then
    QUERY_PASS=$(cat "$INSTALL_DIR/query.pw")
    echo "    （沿用已保存的 ServerQuery 密码）"
fi

# 持久化保存：文档和排错手册都假设能 cat 到它
if [ -n "$QUERY_PASS" ]; then
    mkdir -p "$INSTALL_DIR"
    ( umask 077; printf '%s' "$QUERY_PASS" > "$INSTALL_DIR/query.pw" )
    chown "$RUN_USER:$RUN_USER" "$INSTALL_DIR/query.pw" 2>/dev/null || true
fi
if [ -n "$QUERY_PASS" ] || [ -n "$ADMIN_TOKEN" ]; then
    ( umask 077; {
        echo "TeamSpeak 3 凭据  ($(date '+%F %T'))"
        echo "  连接地址       : ${PUBIP:-?}"
        echo "  ServerQuery 密码: ${QUERY_PASS:-（未抓到）}"
        echo "  管理员令牌      : ${ADMIN_TOKEN:-（未抓到）}"
        echo
        echo "管理员令牌用法：TS3 客户端 → 权限 → 使用激活密钥，粘进去即可获得管理员组"
      } > /root/ts3-credentials.txt )
    SAVED="/root/ts3-credentials.txt"
    [ -f "$INSTALL_DIR/query.pw" ] && SAVED="$SAVED 与 $INSTALL_DIR/query.pw"
    echo "    凭据已保存: $SAVED"
fi

echo "    ServerQuery 密码: ${QUERY_PASS:-（未抓到，请查看 $TS3_DIR/logs）}"

if [ "$WITH_BOT" = "1" ]; then

# ---------- 4. 安装 TS3AudioBot（已打补丁版） ----------
say "4/9 安装 TS3AudioBot 音乐机器人"
mkdir -p "$INSTALL_DIR"
if [ -f "$DIR/vendor/TS3AudioBot" ]; then
    install -m 755 "$DIR/vendor/TS3AudioBot" "$INSTALL_DIR/TS3AudioBot"
    [ -f "$DIR/vendor/TS3AudioBot.pdb" ] && install -m 644 "$DIR/vendor/TS3AudioBot.pdb" "$INSTALL_DIR/"
    echo "    使用内置【已修复崩溃】的自编译版"
else
    die "vendor/TS3AudioBot 不存在 —— 请先跑 bash fetch-bot.sh，或手动解压附件到此路径"
fi

# .NET Core 3.1 需要 libssl1.1（系统只有 OpenSSL 3），单独解压不污染系统
# 三种形态都支持：目录（本仓库的默认形态）/ tar.gz / .deb
if [ ! -d "$INSTALL_DIR/private-libs" ]; then
    if   [ -d "$DIR/vendor/private-libs" ]; then
        cp -a "$DIR/vendor/private-libs" "$INSTALL_DIR/private-libs"
    elif [ -f "$DIR/vendor/private-libs.tar.gz" ]; then
        tar xzf "$DIR/vendor/private-libs.tar.gz" -C "$INSTALL_DIR"
    elif [ -f "$DIR/vendor/libssl1.1.deb" ]; then
        mkdir -p "$INSTALL_DIR/private-libs"
        dpkg-deb -x "$DIR/vendor/libssl1.1.deb" "$INSTALL_DIR/private-libs"
    fi
fi
LIBDIR="$INSTALL_DIR/private-libs/usr/lib/x86_64-linux-gnu"
if [ -e "$LIBDIR/libssl.so.1.1" ]; then
    echo "    libssl1.1 兼容层 ✓ ($(ls "$LIBDIR" | tr '\n' ' '))"
else
    echo "    ✗ 未找到 libssl.so.1.1 —— 机器人起不来（vendor/private-libs 缺失？）"
    die "缺少 libssl1.1 兼容层"
fi

# ---------- 5. 部署代理与守护 ----------
say "5/9 部署 B站代理与守护脚本"
install -m 644 "$DIR/scripts/bili_proxy.py"      "$INSTALL_DIR/bili_proxy.py"
install -m 755 "$DIR/scripts/ts3bot-watchdog.sh" /usr/local/bin/ts3bot-watchdog.sh
install -m 755 "$DIR/scripts/ts3bot-autoresume.py" /usr/local/bin/ts3bot-autoresume.py 2>/dev/null || true
install -m 755 "$DIR/scripts/ts3-boot-check.sh"    /usr/local/bin/ts3-boot-check.sh    2>/dev/null || true
install -m 755 "$DIR/scripts/ts3-serverset.py"     "$INSTALL_DIR/ts3-serverset.py"     2>/dev/null || true
install -m 644 "$DIR/scripts/bili_login.py"        "$INSTALL_DIR/bili_login.py"
install -m 644 "$DIR/scripts/qrmini.py"            "$INSTALL_DIR/qrmini.py"
# 备份 / 还原 / 异地推送 / 机器人控制
for s in ts3-backup.sh ts3-restore.sh ts3-backup-push.sh ts3-backup-prune.sh ts3-bot.sh; do
    [ -f "$DIR/scripts/$s" ] && install -m 755 "$DIR/scripts/$s" "/usr/local/bin/$s"
done
install -m 644 "$DIR/scripts/rebuild-layout.py"  "$INSTALL_DIR/rebuild-layout.py"
[ -f "$DIR/scripts/ts3-admin.py" ] && install -m 644 "$DIR/scripts/ts3-admin.py" "$INSTALL_DIR/ts3-admin.py"
[ -f "$DIR/scripts/audit.sh" ] && install -m 755 "$DIR/scripts/audit.sh" /usr/local/bin/audit.sh
mkdir -p /var/tmp/ts3music /var/tmp/ytdlp

# yt-dlp（兜底用；zipapp 版需 Python 3.9+）
if [ ! -x /usr/local/bin/yt-dlp ]; then
    PYOK=$(python3 -c "import sys;print(1 if sys.version_info>=(3,9) else 0)" 2>/dev/null || echo 0)
    if [ -f "$DIR/vendor/yt-dlp" ] && [ "$PYOK" = "1" ]; then
        install -m 755 "$DIR/vendor/yt-dlp" /usr/local/bin/yt-dlp
        echo "    yt-dlp: 内置精简版"
    else
        curl -sL -o /usr/local/bin/yt-dlp \
          "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux"
        chmod +x /usr/local/bin/yt-dlp
        echo "    yt-dlp: 独立二进制版"
    fi
fi

# ---------- 6. 生成配置 ----------
say "6/9 生成配置"
cp "$DIR/config/ts3audiobot.toml" "$INSTALL_DIR/ts3audiobot.toml"
cp "$DIR/config/rights.toml"      "$INSTALL_DIR/rights.toml"
cp "$DIR/config/NLog.config"      "$INSTALL_DIR/NLog.config" 2>/dev/null || true
sed -i "s|^youtube-dl = .*|youtube-dl = { path = \"/usr/local/bin/yt-dlp\" }|" "$INSTALL_DIR/ts3audiobot.toml" 2>/dev/null || true
# 降低崩溃触发面的两个开关
sed -i 's|^generate_status_avatar = true|generate_status_avatar = false|' "$INSTALL_DIR/ts3audiobot.toml" 2>/dev/null || true
sed -i 's|^set_status_description = true|set_status_description = false|' "$INSTALL_DIR/ts3audiobot.toml" 2>/dev/null || true

mkdir -p "$INSTALL_DIR/bots/default"
# 机器人与 TS3 在同一台机器 → 用 127.0.0.1，这样公网 IP 变了也不用改配置
BOT_ADDR="${BOT_ADDR:-127.0.0.1:${TS3_PORT}}"
sed -e "s|__ADDRESS__|${BOT_ADDR}|g" \
    -e "s|__BOTNAME__|${BOT_NAME}|g" \
    "$DIR/config/bot.toml" > "$INSTALL_DIR/bots/default/bot.toml"

fi   # ← 机器人相关步骤结束

# ---------- 7. 注册服务 + 内核调优 ----------
say "7/9 注册系统服务并应用内核调优"
if [ "$WITH_BOT" = "1" ]; then
    cp "$DIR/systemd/ts3audiobot.service"      /etc/systemd/system/
    cp "$DIR/systemd/bili-proxy.service"       /etc/systemd/system/
    cp "$DIR/systemd/ts3bot-watchdog.service"  /etc/systemd/system/
    cp "$DIR/systemd/ts3bot-watchdog.timer"    /etc/systemd/system/
fi
[ -f "$DIR/systemd/ts3-boot-check.service" ] && cp "$DIR/systemd/ts3-boot-check.service" /etc/systemd/system/
for d in teamspeak3 ts3audiobot bili-proxy; do
    [ "$WITH_BOT" = "0" ] && [ "$d" != "teamspeak3" ] && continue
    mkdir -p /etc/systemd/system/$d.service.d
    for f in "$DIR"/systemd/dropins/$d.service.d/*.conf; do
        [ -f "$f" ] && cp "$f" /etc/systemd/system/$d.service.d/
    done
done

# ── 占位符回填（重要！打包时脱敏把 User=/Group= 换成了 __RUN_USER__）──
# teamspeak3 用专用系统用户 ts3server；机器人/代理用普通用户
sed -i "s|^User=__RUN_USER__|User=ts3server|; s|^Group=__RUN_USER__|Group=ts3server|" \
    /etc/systemd/system/teamspeak3.service
if [ "$WITH_BOT" = "1" ]; then
    sed -i "s|^User=__RUN_USER__|User=$RUN_USER|; s|^Group=__RUN_USER__|Group=$RUN_USER|" \
        /etc/systemd/system/ts3audiobot.service /etc/systemd/system/bili-proxy.service
fi
for d in teamspeak3 ts3audiobot bili-proxy; do
    [ "$WITH_BOT" = "0" ] && [ "$d" != "teamspeak3" ] && continue
    U="$RUN_USER"; [ "$d" = "teamspeak3" ] && U=ts3server
    for f in $(grep -rl '__RUN_USER__' "/etc/systemd/system/$d.service.d/" 2>/dev/null); do
        sed -i "s|__RUN_USER__|$U|g" "$f"
    done
done
# 兜底：任何残留都必须报出来，不能让系统带着占位符上线
LEFT=$(grep -rl '__RUN_USER__' /etc/systemd/system/ 2>/dev/null | wc -l)
if [ "$LEFT" != "0" ]; then
    echo "    ✗ 警告：还有 $LEFT 个单元残留 __RUN_USER__ 占位符！"
    grep -rl '__RUN_USER__' /etc/systemd/system/ 2>/dev/null | sed 's/^/      /'
else
    if [ "$WITH_BOT" = "1" ]; then
        echo "    服务运行用户: ts3server（TS3）/ $RUN_USER（机器人、代理）"
    else
        echo "    服务运行用户: ts3server（TS3）"
    fi
fi

# ── 单元自检：自定义 unit 必须带 [Install] WantedBy，否则 systemctl enable 会失败
#   （踩坑记录：漏了 [Install] 时 enable 报 "instance name specified"，
#    状态停在 static，重启后服务不会自启 —— 很难发现）
BAD=0
UNIT_LIST="/etc/systemd/system/teamspeak3.service /etc/systemd/system/ts3-boot-check.service"
[ "$WITH_BOT" = "1" ] && UNIT_LIST="$UNIT_LIST /etc/systemd/system/ts3audiobot.service \
         /etc/systemd/system/bili-proxy.service /etc/systemd/system/ts3bot-watchdog.timer"
for u in $UNIT_LIST; do
    [ -f "$u" ] || continue
    grep -q '^\[Install\]' "$u" || { echo "    ✗ $(basename "$u") 缺少 [Install] 段"; BAD=1; }
done
[ "$BAD" = "0" ] && echo "    单元自检 ✓（[Install] 段齐全）"

if [ "$WITH_BOT" = "1" ]; then
    chown -R "$RUN_USER:$RUN_USER" "$INSTALL_DIR" /var/tmp/ts3music /var/tmp/ytdlp
fi

# 内核/网络调优（BBR、swappiness 等）
if [ -f "$DIR/sysctl/99-ts3-tuning.conf" ]; then
    cp "$DIR/sysctl/99-ts3-tuning.conf" /etc/sysctl.d/
    [ -f "$DIR/modules-load/99-bbr.conf" ] && cp "$DIR/modules-load/99-bbr.conf" /etc/modules-load.d/
    modprobe tcp_bbr 2>/dev/null || true
    sysctl --system >/dev/null 2>&1 || true
    echo "    已应用: BBR=$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null) swappiness=$(sysctl -n vm.swappiness)"
fi

systemctl daemon-reload
if [ "$WITH_BOT" = "1" ]; then
    systemctl enable ts3audiobot bili-proxy ts3bot-watchdog.timer >/dev/null 2>&1
fi
[ -f /etc/systemd/system/ts3-boot-check.service ] && \
    systemctl enable ts3-boot-check.service >/dev/null 2>&1 && echo "    已启用 ts3-boot-check.service（开机 30 秒兜底自检）"

# ── 开机提速：关掉 VPS 上没用的阻塞项（不影响正常功能）──
#   kdump-tools   内核崩溃转储，VPS 上没用，开机要等 ~9 秒
#   apt-daily     开机即跑 apt 更新，会卡 ~10 秒；apt-daily.timer 仍保留，更新照常
for s in kdump-tools.service apt-daily.service; do
    systemctl is-enabled "$s" >/dev/null 2>&1 && {
        systemctl disable "$s" >/dev/null 2>&1 && echo "    已禁用开机阻塞项 $s"
    }
done

if [ "$WITH_BOT" = "1" ]; then
    systemctl restart bili-proxy ts3audiobot
    systemctl start ts3bot-watchdog.timer
fi
sleep 30

# ---------- 7.2 校正服务器属性（重要！）----------
# 一次搞定 4 个「上海部署时踩过的坑」，详见 scripts/ts3-serverset.py 头部注释：
#   ① virtualserver_hostmessage_mode=3 → 所有客户端一进就被踢（日志只写 Leaving，极难查）
#   ② needed_identity_security_level=8 → 没刷过等级的新人连不上
#   ③ 服务器名尾随空格 → 客户端书签/排序出怪问题
#   ④ 服务器密码与 flag_password 不成对设置 → 设了空密码却仍要输密码
QPW=$(grep -oP 'password\s*=\s*"\K[^"]+' "$TS3_DIR"/logs/ts3server_*.log 2>/dev/null | head -1)
if [ -n "$QPW" ] && [ -f "$INSTALL_DIR/ts3-serverset.py" ]; then
    TS3_HOST=127.0.0.1 TS3_PASS="$QPW" \
    SV_NAME="$SERVER_NAME" SV_PW="$SERVER_PW" SV_SECLEVEL="$SECLEVEL" \
      python3 "$INSTALL_DIR/ts3-serverset.py" || echo "    ⚠ 服务器属性校正失败（可稍后手动执行 ts3-serverset.py）"
else
    echo "    ○ 未取到 ServerQuery 密码，跳过服务器属性校正"
fi


# ---------- 7.5 本地热备份 + 异地冷备份 ----------
say "7.5/9 配置备份体系（本地热备份 + 推送异地冷备仓库）"
mkdir -p /var/backups/ts3
install -m 644 "$DIR/systemd/ts3-backup-push.service" /etc/systemd/system/ 2>/dev/null || true
install -m 644 "$DIR/systemd/ts3-backup-push.timer"   /etc/systemd/system/ 2>/dev/null || true

# 推送专用密钥（本机生成，公钥需加到备份仓库那台机器的 authorized_keys）
if [ ! -f /root/.ssh/id_ed25519_push ]; then
    mkdir -p /root/.ssh && chmod 700 /root/.ssh
    ssh-keygen -t ed25519 -N '' -f /root/.ssh/id_ed25519_push -C 'ts3-backup-push' >/dev/null 2>&1
fi

# 配置：BACKUP_TARGET 环境变量可指定仓库地址（形如 user@host:/path/）
BK_TARGET="${BACKUP_TARGET:-}"
if [ ! -f /etc/ts3-backup.conf ]; then
    cat > /etc/ts3-backup.conf <<CONF
# ts3-backup-push.sh 配置
# PUSH_TARGET 留空 = 只做本地备份；填入则额外推送到异地冷备份仓库
PUSH_TARGET="$BK_TARGET"
PUSH_LABEL="sh"
KEEP_LOCAL=3
PUSH_SSH_KEY="/root/.ssh/id_ed25519_push"
CONF
fi

systemctl daemon-reload
systemctl enable --now ts3-backup-push.timer >/dev/null 2>&1

# 立刻跑一次，验证整条链路
if /usr/local/bin/ts3-backup-push.sh >>/var/log/ts3-backup-push.log 2>&1; then
    echo "    备份已执行: $(ls -1 /var/backups/ts3/*.tar.gz 2>/dev/null | wc -l) 份在 /var/backups/ts3/"
else
    echo "    ⚠ 备份脚本返回非零，详见 /var/log/ts3-backup-push.log"
fi
[ -z "$BK_TARGET" ] && echo "    ○ 未指定异地仓库（BACKUP_TARGET 为空），当前为纯本地备份模式"

# ---------- 8. 频道布局 + 点歌说明 ----------
say "8/9 重建频道布局并写入点歌说明"
install -m 644 "$DIR/scripts/setdesc.py" "$INSTALL_DIR/setdesc.py"
chmod 644 "$INSTALL_DIR/setdesc.py"

if [ -f "$INSTALL_DIR/rebuild-layout.py" ]; then
    PRIVATE_PW="$PRIVATE_PW" TS3_PASS="$QUERY_PASS" \
      python3 "$INSTALL_DIR/rebuild-layout.py" 2>/dev/null && echo "    频道布局已重建" || \
      echo "    （可稍后手动执行 rebuild-layout.py）"
fi
if [ "$WITH_BOT" = "1" ]; then
    TS3_PASS="$QUERY_PASS" python3 "$INSTALL_DIR/setdesc.py" 2>/dev/null || \
      echo "    （点歌说明可稍后手动执行 setdesc.py 写入）"
fi

# ---------- 8.5 可选：扫码登录 B站（自动出二维码）----------
if [ "$WITH_BOT" = "0" ]; then
    : # 没装机器人，跳过
elif [ "${BILI_LOGIN:-0}" = "1" ]; then
    say "8.5/9 B站扫码登录"
    echo "    二维码会直接画在终端里，同时生成一张 PNG 图片（方便传到手机上扫）"
    echo
    python3 "$INSTALL_DIR/bili_login.py" --out "$INSTALL_DIR/bili_cookies.txt" || \
        echo "    ⚠ 登录未完成（不影响部署，随时可以重跑：python3 $INSTALL_DIR/bili_login.py）"
    chown "$RUN_USER:$RUN_USER" "$INSTALL_DIR/bili_cookies.txt" 2>/dev/null || true
else
    echo "    ○ 未登录 B站（不登录也能点歌，只是音源档位可能偏低）"
    echo "      想登录就跑：sudo -u $RUN_USER python3 $INSTALL_DIR/bili_login.py"
fi

# ---------- 8.8 输出「部署信息」文档 ----------
# 装完之后手边要有一份能直接照着用的说明：连接地址 / 管理员令牌 / 点歌指令。
# 同时写到两处：脚本所在目录（你执行 install.sh 的地方）+ /root/（保底能找到）。
write_info_txt() {
    OUT="$1"
    {
        echo "╔══════════════════════════════════════════════════════════╗"
        echo "║        TeamSpeak 3 服务器 · 部署信息                      ║"
        echo "╚══════════════════════════════════════════════════════════╝"
        echo
        echo "生成时间：$(date '+%F %T %Z')"
        echo "主机名称：$(hostname)"
        echo
        echo "━━━ 一、连接地址（把这个发给朋友）━━━━━━━━━━━━━━━━━━━━━━━━"
        echo
        echo "    地址　　　：$PUBIP"
        echo "    语音端口　：$TS3_PORT  (UDP，客户端默认就是它，不用手填)"
        echo "    服务器名称：$SERVER_NAME"
        if [ -n "$SERVER_PW" ]; then
            echo "    服务器密码：$SERVER_PW"
        else
            echo "    服务器密码：无（任何人可直接连接）"
        fi
        echo
        if [ "$WITH_BOT" = "1" ]; then
            echo "    机器人昵称：$BOT_NAME"
        fi
        echo
        echo "━━━ 二、管理员令牌 ★ 最重要 ★ ━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo
        if [ -n "$ADMIN_TOKEN" ]; then
            echo "    $ADMIN_TOKEN"
        else
            echo "    （自动抓取失败，手动找： sudo journalctl -u teamspeak3 | grep token= ）"
        fi
        echo
        echo "    用法："
        echo "      1) 用上面的地址连进服务器"
        echo "      2) 菜单 → 权限 → 使用激活密钥（Use Privilege Key）"
        echo "      3) 把上面那串令牌粘进去 → 确定"
        echo "      4) 你的身份就变成管理员了"
        echo
        if [ "$WITH_BOT" = "1" ]; then
            echo "━━━ 三、点歌指令（在任意频道直接发消息）━━━━━━━━━━━━━━━━━"
            echo
            echo "  ▸ 点歌"
            echo "      !play 稻香              完整写法"
            echo "      !点歌 稻香              中文别名"
            echo "      !dian 稻香  !bo 稻香    拼音简写"
            echo "      !play 周杰伦 稻香       多个词自动合并成搜索词"
            echo "      !play BV1G88y6xEQV      按 B站视频号"
            echo "      !play https://b23.tv/xx 直接粘链接"
            echo
            echo "  ▸ 播放控制"
            echo "      !暂停/继续 !zan      !停止   !ting"
            echo "      !下一首    !xia      !上一首 !shang"
            echo "      !当前      !now      !队列   !lb"
            echo "      !音量 50   !yin 50   !跳转 90 !tiao 90"
            echo
            echo "  ▸ 播放模式"
            echo "      !单曲 !danqu   单曲循环     !循环 !quanbu  列表循环"
            echo "      !随机 !sui     随机播放     !顺序 !shun    顺序播放"
            echo
            echo "  ▸ !bz   查看全部命令（!help 的简写）"
            echo
        else
            echo "━━━ 三、点歌机器人：本次未安装 ━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo
            echo "    想补装（已装的部分会自动跳过）："
            echo "      cd $(pwd) && sudo WITH_BOT=1 bash install.sh"
            echo
        fi
        echo "━━━ 四、管理凭据（保密，别外发）━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo
        echo "    ServerQuery 密码 : ${QUERY_PASS:-（未抓到）}"
        echo "    ServerQuery 端口 : $QUERY_PORT  (TCP，只建议走 SSH 隧道访问)"
        echo "    隧道示例         : ssh -L $QUERY_PORT:127.0.0.1:$QUERY_PORT <用户>@$PUBIP"
        echo
        echo "━━━ 五、常用运维命令 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo
        echo "    sudo ts3-backup.sh                 立刻备份一次（不停服）"
        echo "    sudo ts3-restore.sh <备份包>        还原（默认 dry-run）"
        echo "    sudo ts3-bot.sh status             机器人状态"
        echo "    sudo bash /usr/local/bin/audit.sh 1 体检"
        echo "    journalctl -u teamspeak3 -n 50     看 TS3 日志"
        if [ "$WITH_BOT" = "1" ]; then
            echo "    journalctl -u ts3audiobot -n 50    看机器人日志"
        fi
        echo
        echo "━━━ 六、别忘了开防火墙 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo
        echo "    UDP  $TS3_PORT    ← 语音。协议一定要选 UDP！选成 TCP 会完全连不上"
        echo "    TCP  30033      ← 文件传输（头像 / 频道文件）"
        echo "    ✗ 不要开放 TCP $QUERY_PORT（会被爆破）"
        echo
        echo "──────────────────────────────────────────────────────────"
        echo "  文档位置：$OUT"
        echo "  取回本地：scp <用户>@$PUBIP:$OUT ./"
        echo "──────────────────────────────────────────────────────────"
    } > "$OUT" 2>/dev/null || return 1
    chmod 644 "$OUT" 2>/dev/null || true
    return 0
}

INFO_BASE="TS3-服务器信息.txt"
INFO_DIR_TXT="$DIR/$INFO_BASE"
INFO_ROOT_TXT="/root/$INFO_BASE"
WROTE=""
write_info_txt "$INFO_DIR_TXT" && WROTE="$INFO_DIR_TXT"
write_info_txt "$INFO_ROOT_TXT" && WROTE="${WROTE:+$WROTE 与 }$INFO_ROOT_TXT"
echo
if [ -n "$WROTE" ]; then
    echo "    📄 部署信息已写好：$WROTE"
    echo "       内容：连接地址 / 管理员令牌 / 点歌指令 / 管理凭据 / 运维命令"
fi

# ---------- 9. 完成 ----------
say "9/9 部署完成 🎉"
cat <<EOF

  ┌──────────────── 服务器信息 ────────────────
  │  连接地址（发给朋友）: $PUBIP
  │  语音端口: $TS3_PORT (UDP，客户端默认)
  │  服务器名称: $SERVER_NAME
  │  服务器密码: $([ -n "$SERVER_PW" ] && echo "已设置（注意保密）" || echo "无（任何人可直接连接）")
  │  身份安全等级: $SECLEVEL   (8 会让没刷过等级的新人连不上)
  │  安装内容: $([ "$WITH_BOT" = "1" ] && echo "TS3 服务端 + 点歌机器人" || echo "仅 TS3 服务端")
  ├──────────────── 管理凭证（务必保存） ─────
  │  ServerQuery 密码: ${QUERY_PASS:-见 $TS3_DIR/logs}
  │  管理员特权令牌: ${ADMIN_TOKEN:-见 $TS3_DIR/logs}
  ├──────────────── 服务 ────────────────────
$(if [ "$WITH_BOT" = "1" ]; then cat <<'EOS'
  │  teamspeak3 / ts3audiobot / bili-proxy
  │  守护: ts3bot-watchdog.timer（每分钟巡检 + 重启后自动续播）
EOS
else cat <<'EOS'
  │  teamspeak3（只装了语音服务端）
EOS
fi)  ├──────────────── 备份 / 运维工具 ──────────
  │  本地热备份 : ts3-backup.sh   （在线备份，不需停机，76KB）
  │  定时任务   : ts3-backup-push.timer（每天 00:00 / 12:00）
  │  一键还原   : ts3-restore.sh <包>         先 dry-run，加 --yes 才动手
$(if [ "$WITH_BOT" = "1" ]; then echo "  │  机器人开关 : ts3-bot.sh start|stop|freeze|thaw|status"; fi)\
  │  备份位置   : /var/backups/ts3/
  ├──────────────── 下一步 ──────────────────
  │  1) 云平台防火墙放行【只有这两个需要开放】：
  │       UDP $TS3_PORT   ← 语音，必须！协议一定要选 UDP（选成 TCP 会连不上）
  │       TCP 30033     ← 文件传输（头像/文件）
  │     ⚠ 不要开放 TCP $QUERY_PORT（ServerQuery 管理端口，会被爆破）
  │       需要远程管理时用 SSH 隧道：
  │         ssh -L $QUERY_PORT:127.0.0.1:$QUERY_PORT <用户>@<服务器>
  │  2) 在 TS3 客户端用上面的令牌给自己管理员权限
  │  $( [ "$WITH_BOT" = "1" ] || echo "3) 以后想加点歌机器人？把 vendor/TS3AudioBot 放回去重跑 install.sh 即可" )
  │  3) （可选）登录 B站以启用最佳音源 —— 会自动生成二维码：
  │       python3 $INSTALL_DIR/bili_login.py
  │     · 二维码会直接画在终端里（手机对着屏幕扫）
  │     · 同时生成 PNG 图片，可传到手机打开再扫
  │  4) 点歌用法（在频道里直接发）：
  │       !play 稻香          ← 完整写法
  │       !dian 稻香  !bo 稻香 ← 拼音简写
  │       !play BV1G88y6xEQV  !play https://b23.tv/xxxx
  │       !zan 暂停 !ting 停止 !xia 下一首 !shang 上一首
  │       !now 当前曲目 !lb 队列 !yin 50 音量 !tiao 90 跳转
  │       !bz 查看全部命令
  └───────────────────────────────────────────

  想自己改机器人源码？见 patch-kit/README-patch.md
  （重编译工具 + 7 处补丁，含 75 秒增量编译脚本）
EOF

if [ "$WITH_BOT" = "0" ]; then
    echo
    echo "  （本次只装了 TS3 语音服务端，没有安装点歌机器人）"
    echo "   想补装：  sudo WITH_BOT=1 bash install.sh"
fi

# ---------- 异地冷备份：打印推送公钥 ----------
if [ -f /root/.ssh/id_ed25519_push.pub ]; then
cat <<EOF

  ┌──────── 异地冷备份仓库（可选，推荐）────────
  │  已生成推送专用密钥。把它加到备份仓库那台机器的
  │  ~/.ssh/authorized_keys，然后设置仓库地址：
  │
  │    echo '$(cat /root/.ssh/id_ed25519_push.pub)' \\
  │      >> ~/.ssh/authorized_keys        # 在仓库那台机器上执行
  │
  │    sudo sed -i 's|^PUSH_TARGET=.*|PUSH_TARGET="用户@仓库IP:/var/backups/ts3-from-sh/"|' /etc/ts3-backup.conf
  │    sudo /usr/local/bin/ts3-backup-push.sh    # 立刻试跑
  │
  │  配置好后，每天 00:00 / 12:00 自动备份并推送。
  └─────────────────────────────────────────────
EOF
fi
