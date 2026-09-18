#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# 构建依赖：
#   TS3AudioBot        OSL-3.0      https://github.com/Splamy/TS3AudioBot
#   .NET Core 3.1      MIT          https://github.com/dotnet/runtime
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

export DOTNET_ROOT=/var/tmp/build/dotnet3
export PATH=/var/tmp/build/dotnet3:$PATH
export DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1
export LD_LIBRARY_PATH=/opt/ts3bot/private-libs/usr/lib/x86_64-linux-gnu
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1
export NUGET_PACKAGES=/var/tmp/build/nuget
cd /var/tmp/build/src || { echo "✗ /var/tmp/build/src 不存在"; exit 1; }
echo "START $(date +%T)"
dotnet publish TS3AudioBot/TS3AudioBot.csproj -c Release -r linux-x64 --self-contained true -p:PublishSingleFile=true -o /var/tmp/build/out
echo "EXIT=$? $(date +%T)"
