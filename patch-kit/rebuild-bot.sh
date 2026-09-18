#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# 构建依赖：
#   TS3AudioBot        OSL-3.0      https://github.com/Splamy/TS3AudioBot
#   .NET Core 3.1      MIT          https://github.com/dotnet/runtime
#   libssl1.1/libcrypto1.1  OpenSSL License  （.NET Core 3.1 运行依赖，随包分发）
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

# ============================================================
#  TS3AudioBot 补丁重编译工具
#  用途：本仓库已停更（最后 release 2021-04-02），崩溃 bug 上游不会修，
#        因此我们打补丁自行编译。此脚本一键重做。
#  用法：sudo /opt/ts3bot/rebuild-bot.sh
# ============================================================
set -e
BUILD=/var/tmp/build
D=$BUILD/src
DOTNET=$BUILD/dotnet3
LIBS=/opt/ts3bot/private-libs/usr/lib/x86_64-linux-gnu

export DOTNET_ROOT=$DOTNET
export PATH=$DOTNET:$PATH
export DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1
export LD_LIBRARY_PATH=$LIBS          # .NET Core 3.1 需要 OpenSSL 1.1（系统只有 3）
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_NOLOGO=1
export NUGET_PACKAGES=$BUILD/nuget

# ---------- 1. 准备源码（首次会自动下载） ----------
if [ ! -d "$D" ]; then
    mkdir -p "$BUILD" && cd "$BUILD"
    curl -sL -o src.tgz https://github.com/Splamy/TS3AudioBot/archive/refs/heads/master.tar.gz
    tar xzf src.tgz && mv TS3AudioBot-master src
fi
[ -x "$DOTNET/dotnet" ] || {
    mkdir -p "$BUILD" && cd "$BUILD"
    curl -sL -o sdk.tar.gz https://dotnetcli.azureedge.net/dotnet/Sdk/3.1.426/dotnet-sdk-3.1.426-linux-x64.tar.gz
    mkdir -p dotnet3 && tar xzf sdk.tar.gz -C dotnet3
}
# 移除会要求 net9/net10 工具的构建钩子（GitVersion / dotnet-script）
find "$D" -name 'dotnet-tools.json' -o -name 'global.json' | while read f; do
    [ -e "$f.disabled" ] || mv "$f" "$f.disabled"; done

# ---------- 2. 应用补丁（幂等） ----------
HERE="$(cd "$(dirname "$0")" && pwd)"
# 核心补丁（P1~P4 崩溃修复 + P7 中文别名）：必须打上，否则中止
for pf in patch_bot.py patch_p7.py; do
    SRC="$HERE/$pf"; [ -f "$SRC" ] || SRC="$BUILD/$pf"
    [ -f "$SRC" ] || { echo "✗ 找不到补丁脚本 $pf"; exit 1; }
    python3 "$SRC" "$D" || { echo "✗ 补丁 $pf 应用失败"; exit 1; }
done
# 可选补丁（调试日志 / 错误回显抑制）：失败不影响编译
for pf in patch_p4log.py patch_p5.py; do
    SRC="$HERE/$pf"; [ -f "$SRC" ] || SRC="$BUILD/$pf"
    [ -f "$SRC" ] && { python3 "$SRC" "$D" || true; }
done

# ---------- 3. 编译 ----------
cd "$D"
echo "开始编译 $(date +%T)"
dotnet publish TS3AudioBot/TS3AudioBot.csproj -c Release -r linux-x64 \
    --self-contained true -p:PublishSingleFile=true -o "$BUILD/out" || {
    echo "⚠️ 若报 NU1202（gitversion/dotnet-script），属构建钩子噪音，看是否有 'TS3AudioBot ->' 输出即可"; }

# ---------- 4. 部署 ----------
[ -f "$BUILD/out/TS3AudioBot" ] || { echo "编译产物不存在，中止"; exit 1; }
cp -p /opt/ts3bot/TS3AudioBot /opt/ts3bot/TS3AudioBot.prev 2>/dev/null || true
systemctl stop ts3audiobot
cp "$BUILD/out/TS3AudioBot" /opt/ts3bot/TS3AudioBot
cp "$BUILD/out/TS3AudioBot.pdb" /opt/ts3bot/TS3AudioBot.pdb
chmod 755 /opt/ts3bot/TS3AudioBot
systemctl start ts3audiobot
sleep 15
echo "服务状态: $(systemctl is-active ts3audiobot)"
echo "完成 $(date +%T)"
echo
echo "回滚方法："
echo "  systemctl stop ts3audiobot"
echo "  cp /opt/ts3bot/TS3AudioBot.orig-0.12.0 /opt/ts3bot/TS3AudioBot   # 上游原版"
echo "  cp /opt/ts3bot/TS3AudioBot.prev        /opt/ts3bot/TS3AudioBot   # 上一版补丁"
echo "  systemctl start ts3audiobot"
