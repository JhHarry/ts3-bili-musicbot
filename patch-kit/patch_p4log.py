#!/usr/bin/env python3
# ──────────────────────────────────────────────────────────────────────────
# 补丁对象：
#   TS3AudioBot        OSL-3.0      https://github.com/Splamy/TS3AudioBot
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

import sys
D = sys.argv[1] if len(sys.argv) > 1 else '/var/tmp/build/src'
p = D + '/TS3AudioBot/Audio/AudioInputRewriter.cs'
s = open(p, encoding='utf-8').read()
old = """			if (string.IsNullOrWhiteSpace(input))
				return input;

			var t = input.Trim();"""
new = """			if (string.IsNullOrWhiteSpace(input))
			{
				Console.Error.WriteLine("[PATCH P4] blank input");
				return input;
			}

			var t = input.Trim();"""
if old in s:
    s = s.replace(old, new)
else:
    print('  [SKIP] 空值分支已存在')

old2 = """			if (string.IsNullOrWhiteSpace(input))
			{
				Console.Error.WriteLine("[PATCH P4] blank input");
				return input;
			}

			var t = input.Trim();"""
if old2 not in s:
    print('  [FAIL] 锚点缺失'); sys.exit(1)

# 在四个返回点前统一记录
s = s.replace("""			if (t.StartsWith("/", StringComparison.Ordinal) || t.StartsWith("\\\\", StringComparison.Ordinal) || t.StartsWith(".", StringComparison.Ordinal))
				return input;""",
"""			if (t.StartsWith("/", StringComparison.Ordinal) || t.StartsWith("\\\\", StringComparison.Ordinal) || t.StartsWith(".", StringComparison.Ordinal))
			{
				Console.Error.WriteLine($"[PATCH P4] local path passthrough: '{t}'");
				return input;
			}""")

s = s.replace("""				if (host == "b23.tv" || host == "bilibili.com" || host.EndsWith(".bilibili.com", StringComparison.Ordinal))
					return VideoBase + Uri.EscapeDataString(t);
				return input; // real url (direct mp3/stream) -> untouched""",
"""				if (host == "b23.tv" || host == "bilibili.com" || host.EndsWith(".bilibili.com", StringComparison.Ordinal))
				{
					var bv = VideoBase + Uri.EscapeDataString(t);
					Console.Error.WriteLine($"[PATCH P4] bilibili link: '{t}' -> '{bv}'");
					return bv;
				}
				Console.Error.WriteLine($"[PATCH P4] absolute uri passthrough: '{t}' (scheme={uri.Scheme})");
				return input; // real url (direct mp3/stream) -> untouched""")

s = s.replace("""			if (t.StartsWith("BV", StringComparison.OrdinalIgnoreCase) && t.Length >= 12)
				return VideoBase + Uri.EscapeDataString(t);""",
"""			if (t.StartsWith("BV", StringComparison.OrdinalIgnoreCase) && t.Length >= 12)
			{
				Console.Error.WriteLine($"[PATCH P4] BV id: '{t}'");
				return VideoBase + Uri.EscapeDataString(t);
			}""")

s = s.replace("""			// anything else is a search query
			return SearchBase + Uri.EscapeDataString(t);""",
"""			// anything else is a search query
			var final = SearchBase + Uri.EscapeDataString(t);
			Console.Error.WriteLine($"[PATCH P4] search: '{t}' -> '{final}'");
			return final;""")

open(p, 'w', encoding='utf-8').write(s)
print('  [OK] P4 已加入调试日志')
