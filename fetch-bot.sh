#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# 本脚本下载的第三方组件：
#   TS3AudioBot        OSL-3.0      https://github.com/Splamy/TS3AudioBot
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────
# ============================================================
#  fetch-bot.sh —— 在线获取「已打补丁的音乐机器人」二进制
#
#  为什么单独拿出来下载：
#    补丁版的 TS3AudioBot 是单个 97.5 MB 的文件，放在 git 里会把仓库撑到
#    130 MB，而且贴着 GitHub 的 100 MiB 单文件硬限制。所以它作为
#    Release 附件单独分发（xz 后约 35~40 MB），仓库本体只有 30 MB 左右。
#
#  用法（一般由 install.sh 自动调用）：
#     bash fetch-bot.sh            # 装到 vendor/TS3AudioBot
#     bash fetch-bot.sh --check    # 只检查本地是否已有
#
#  纯离线部署：把这个附件手动拷成 vendor/TS3AudioBot 即可，install.sh 会跳过下载。
# ============================================================
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# shellcheck source=repo.conf
[ -f repo.conf ] && . ./repo.conf
GITHUB_REPO="${GITHUB_REPO:-your-name/ts3-bili-musicbot}"
BOT_ASSET="${BOT_ASSET:-ts3audiobot-patched.tar.xz}"
VENDOR="$DIR/vendor"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

if [ -x "$VENDOR/TS3AudioBot" ]; then
    echo "    机器人二进制已在 vendor/TS3AudioBot（跳过下载）"
    exit 0
fi
[ "$1" = "--check" ] && { echo "    需要下载"; exit 1; }

URL="https://github.com/$GITHUB_REPO/releases/latest/download/$BOT_ASSET"
say "下载音乐机器人（约 35~40 MB，只需一次）"
echo "    $URL"

TMP=/var/tmp/ts3bot-dl.tar.xz
rm -f "$TMP"
if command -v curl >/dev/null 2>&1; then
    curl -fL --retry 3 --connect-timeout 20 -o "$TMP" "$URL" \
      || { echo "✗ 下载失败。可手动下载后放到 vendor/TS3AudioBot"; exit 1; }
else
    wget -O "$TMP" "$URL" || { echo "✗ 下载失败"; exit 1; }
fi
echo "    已下载 $(du -h "$TMP" | cut -f1)"

say "解压到 vendor/"
mkdir -p "$VENDOR"
tar -xJf "$TMP" -C "$VENDOR"
rm -f "$TMP"
chmod 755 "$VENDOR/TS3AudioBot" 2>/dev/null || true

if [ ! -x "$VENDOR/TS3AudioBot" ]; then
    echo "✗ 解压后没找到 vendor/TS3AudioBot —— 附件内容不对"
    exit 1
fi
echo "    完成: $(du -h "$VENDOR/TS3AudioBot" | cut -f1)"
