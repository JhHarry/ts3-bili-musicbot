#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────
# 仅用标准 Unix 工具，无第三方依赖
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

# ============================================================
#  privacy-scan.sh —— 开源发布前的隐私扫描
#
#  用法：  bash privacy-scan.sh <要扫描的目录> [额外的关键词文件]
#
#  为什么单独拆出来：
#    这份包是要公开到 GitHub 的，绝对不能带上任何部署环境的痕迹
#    （服务器 IP、域名、身份密钥、cookie、频道名、用户名……）。
#    靠"我记得改过"是不可靠的，所以做成一个可以反复跑的检查。
#
#  设计要点：
#    * 用【模式】识别，而不是把某个具体 IP 写死在脚本里
#      —— 否则扫描脚本本身就是泄露源；
#    * 你自己的敏感词写在 privacy-denylist.txt 里（已 gitignore），
#      或者用第二个参数临时指定；
#    * 二进制不进文本 grep（裸字节匹配会大量误报），改用 strings 单独判。
# ============================================================
set -uo pipefail

TARGET="${1:-.}"
DENY="${2:-}"
[ -d "$TARGET" ] || { echo "用法: privacy-scan.sh <目录> [关键词文件]"; exit 2; }

# 允许出现的"技术性" IP（写死的本机/保留地址，不算泄露）
# 允许出现的"技术性" IP：
#   保留地址 / 文档示例 / 常见公共 DNS / 以及 UA 里的版本号伪 IP（Chrome/120.0.0.0）
#   另含 RFC 5737 文档专用网段（192.0.2.0/24、198.51.100.0/24、203.0.113.0/24）
IP_WHITELIST='0\.0\.0\.0|127\.0\.0\.0|127\.0\.0\.1|255\.255\.255\.255|1\.2\.3\.4|8\.8\.8\.8|114\.114\.114\.114|120\.0\.0\.0|192\.0\.2\.[0-9]+|198\.51\.100\.[0-9]+|203\.0\.113\.[0-9]+'

# 扫描脚本自身要排除（它里面写着各种待匹配的模式）
SELF='privacy-scan\.sh'

HIT=0
note() { echo "  ⚠️  $1"; HIT=1; }

# 文本文件清单（排除二进制与依赖目录）
list_text() {
    find "$TARGET" -type f \
        -not -path '*/.git/*' -not -path '*/vendor/*' \
        -not -name '*.png' -not -name '*.jpg' -not -name '*.gz' \
        -not -name '*.xz' -not -name '*.zst' -not -name '*.bz2' \
        -not -name '*.so' -not -name '*.pdb' -not -name '*.dll' \
        2>/dev/null | while read -r f; do
            # 含 NUL 字节的按二进制处理
            echo "$f" | grep -qE "$SELF" && continue
            if ! LC_ALL=C grep -qP '\x00' "$f" 2>/dev/null; then echo "$f"; fi
        done
}

echo "=== 隐私扫描: $TARGET ==="

TXTFILE=$(mktemp)
list_text > "$TXTFILE"
echo "  文本文件 $(wc -l < "$TXTFILE") 个"

# ---------- 1. 公网 IP ----------
IPS=$(xargs -r grep -hoE '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b' < "$TXTFILE" 2>/dev/null \
      | sort -u | grep -vE "^($IP_WHITELIST)$" || true)
if [ -n "$IPS" ]; then
    note "发现疑似公网 IP："
    echo "$IPS" | sed 's/^/       /'
    while read -r ip; do
        [ -n "$ip" ] || continue
        grep -rlF "$ip" $(cat "$TXTFILE") 2>/dev/null | sed "s|^|       ($ip) |"
    done <<< "$IPS"
fi

# ---------- 2. 主机名 / 域名线索 ----------
while read -r pat; do
    [ -z "$pat" ] && continue
    F=$(xargs -r grep -lE "$pat" < "$TXTFILE" 2>/dev/null || true)
    [ -n "$F" ] && note "[$pat]" && echo "$F" | sed 's/^/       /'
done <<'PATS'
(ts3\.(ren|com|me)|tsdns\.vip|\.ts3\.|noip\.|duckdns\.)
(instance-[0-9]{4,}|ip-10-|ec2-|vm-[0-9]+)
PATS

# ---------- 3. 身份密钥 / token / 私钥 ----------
while read -r pat; do
    [ -z "$pat" ] && continue
    F=$(xargs -r grep -lE "$pat" < "$TXTFILE" 2>/dev/null || true)
    [ -n "$F" ] && note "[$pat]" && echo "$F" | sed 's/^/       /'
done <<'PATS'
^\s*key\s*=\s*"[A-Za-z0-9+/]{40,}
BEGIN [A-Z ]*PRIVATE KEY
(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})
(SCKEY|SendKey|sctapi\.ftqq|SCT[0-9A-Za-z]{10,})
PATS

# ---------- 4~6. 仅提示项（本项目本来就会提到这些文件名，不算泄露） ----------
info() { echo "  ℹ️  $1"; }
F=$(xargs -r grep -lE 'SESSDATA|bili_jct|buvid3|DedeUserID|bili_cookies\.txt' < "$TXTFILE" 2>/dev/null || true)
[ -n "$F" ] && info "提到 B站 cookie 名（确认只是变量名 / 文档）:" && echo "$F" | sed 's/^/       /'
F=$(xargs -r grep -lE 'ts3server\.sqlitedb|ssh_host_rsa_key|ts3audiobot\.db' < "$TXTFILE" 2>/dev/null || true)
[ -n "$F" ] && info "提到运行期数据文件名（确认只是脚本里的路径）:" && echo "$F" | sed 's/^/       /'
F=$(xargs -r grep -lE '/home/[a-zA-Z0-9_.-]+|/Users/[a-zA-Z0-9_.-]+' < "$TXTFILE" 2>/dev/null || true)
[ -n "$F" ] && info "提到家目录路径（确认是示例而非真实用户）:" && echo "$F" | sed 's/^/       /'

# ---------- 7. 你自己的敏感词 ----------
if [ -n "$DENY" ] && [ -f "$DENY" ]; then
    echo "  载入自定义关键词: $DENY"
    while IFS= read -r kw; do
        case "$kw" in ''|\#*) continue ;; esac
        F=$(xargs -r grep -lF "$kw" < "$TXTFILE" 2>/dev/null || true)
        [ -n "$F" ] && note "[自定义] $kw" && echo "$F" | sed 's/^/       /'
    done < "$DENY"
fi

# ---------- 8. 二进制里不该有用户名 / 路径 ----------
BIN="$TARGET/vendor/TS3AudioBot"
if [ -f "$BIN" ] && command -v strings >/dev/null 2>&1; then
    for kw in "/home/[a-z]" "instance-2026" "DayDay"; do
        if strings "$BIN" 2>/dev/null | grep -qE "$kw"; then
            note "二进制 $BIN 中含 [$kw]"
        fi
    done
fi

rm -f "$TXTFILE"
echo
if [ "$HIT" = "0" ]; then
    echo "✅ 未发现隐私泄露"
    exit 0
else
    echo "❌ 有命中项，发布前必须逐条确认"
    exit 1
fi
