#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# 本仓库/本脚本涉及的第三方组件：
#   TeamSpeak 3 Server 私有许可     https://www.teamspeak.com   （随包分发，使用即接受其条款）
#   TS3AudioBot        OSL-3.0      https://github.com/Splamy/TS3AudioBot
#   yt-dlp             Unlicense    https://github.com/yt-dlp/yt-dlp
#   libssl1.1/libcrypto1.1  OpenSSL License  （.NET Core 3.1 运行依赖，随包分发）
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────
# ============================================================
#  build-vendor.sh —— 准备发布用的二进制内容
#
#  本仓库的体积策略：
#     · git 里【直接放】TS3 服务端、yt-dlp、libssl1.1 兼容层  → vendor/ 约 29 MB
#     · 机器人（单个 97.5 MB，贴着 GitHub 100 MiB 红线）→ 单独打成一个
#       Release 附件 ts3audiobot-patched.tar.xz（约 35~40 MB）
#
#  本脚本在一台【已经部署好】的机器上运行，一次产出上面两样东西。
#
#  用法（在仓库根目录）：
#     sudo bash build-vendor.sh
#
#  冷备机器上先解归档再指定来源：
#     sudo mkdir -p /var/tmp/coldx
#     sudo tar -xf xxx/ts3bot.tar.zst     --zstd -C /var/tmp/coldx opt/ts3bot
#     sudo tar -xf xxx/ts3server.tar.zst  --zstd -C /var/tmp/coldx opt/teamspeak3-server
#     sudo OPT_ROOT=/var/tmp/coldx bash build-vendor.sh
# ============================================================
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

[ -f repo.conf ] && . ./repo.conf
BOT_ASSET="${BOT_ASSET:-ts3audiobot-patched.tar.xz}"

OPT_ROOT="${OPT_ROOT:-}"
SRC_BOT="${OPT_ROOT:-}/opt/ts3bot"
SRC_TS3="${OPT_ROOT:-}/opt/teamspeak3-server"
V="$DIR/vendor"

[ "$(id -u)" = "0" ] || { echo "请用 sudo 运行"; exit 1; }

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
need() { [ -e "$1" ] || { echo "✗ 缺少素材: $1"; exit 1; }; }

need "$SRC_BOT/TS3AudioBot"
need "$SRC_TS3/ts3server"
need /usr/local/bin/yt-dlp

say "1/5 机器人二进制 → Release 附件（不进 git）"
TMPB=$(mktemp -d /var/tmp/botpack.XXXXXX)
install -m 755 "$SRC_BOT/TS3AudioBot"     "$TMPB/TS3AudioBot"
install -m 644 "$SRC_BOT/TS3AudioBot.pdb" "$TMPB/TS3AudioBot.pdb" 2>/dev/null || true
echo "    正在压缩（97.5 MB，xz -9 多线程，要几分钟）…"
# 用管道而不是 tar -J，这样可以交给 xz -T0 多线程压缩（快很多）
tar -c -C "$TMPB" . | xz -9 -T0 > "$DIR/$BOT_ASSET"
rm -rf "$TMPB"
ls -l "$DIR/$BOT_ASSET" | awk '{printf "    产物: %s  (%.1f MB)\n", $9, $5/1048576}'

say "2/5 仓库内二进制：yt-dlp + libssl1.1 兼容层"
rm -rf "$V"
mkdir -p "$V"
install -m 755 /usr/local/bin/yt-dlp "$V/yt-dlp"
cp -a "$SRC_BOT/private-libs" "$V/private-libs"
echo "    yt-dlp / private-libs ✓"

say "3/5 仓库内二进制：TS3 服务端（剔除全部运行数据）"
# 这些【绝不能】进仓库：数据库、身份密钥、日志、频道上传文件、query 访问控制、许可标记
mkdir -p "$V/teamspeak3-server"
(cd "$SRC_TS3" && tar cf - \
    --exclude='ts3server.sqlitedb*' \
    --exclude='ssh_host_rsa_key' \
    --exclude='logs' \
    --exclude='files' \
    --exclude='.ts3server_license_accepted' \
    --exclude='query_ip_allowlist.txt' \
    --exclude='query_ip_denylist.txt' \
    --exclude='ts3server.ini' \
    --exclude='*.key' --exclude='*.log' --exclude='*.sqlitedb*' \
    .) | (cd "$V/teamspeak3-server" && tar xf -)
echo "    $(find "$V/teamspeak3-server" -type f | wc -l) 个文件"

say "4/5 隐私扫描 + 凭证文件检查"
DENY="$DIR/privacy-denylist.txt"
bash scripts/privacy-scan.sh "$DIR" "$DENY" || {
    echo "❌ 隐私扫描未通过，修好再提交"; exit 1; }

for f in bili_cookies.txt query.pw relay.env ts3server.sqlitedb ssh_host_rsa_key \
         ts3audiobot.db id_ed25519 id_ed25519_push; do
    FOUND=$(find "$DIR" -name "$f" -not -path '*/.git/*' 2>/dev/null || true)
    [ -n "$FOUND" ] && { echo "❌ 仓库里不该出现: $FOUND"; exit 1; }
done
echo "    ✅ 未发现凭证类文件"

say "5/5 体积汇总"
echo "── 要提交进 git 的 vendor/ ──"
du -sh "$V"/* | sed 's|^|    |'
echo "    仓库合计: $(du -sh "$V" | cut -f1) + 代码约 300 KB"
echo
echo "── 要传成 Release 附件的 ──"
echo "    $BOT_ASSET  ($(du -h "$DIR/$BOT_ASSET" | cut -f1))"
echo
echo "接下来："
echo "  1) git add -A && git commit -m 'v13' && git push"
echo "  2) 建 Release，把 $BOT_ASSET 作为附件上传"
echo "     gh release create v13 $BOT_ASSET --title v13 --notes-file CHANGELOG.md"
