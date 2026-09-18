#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ──────────────────────────────────────────────────────────────────────────
# 补丁对象：
#   TS3AudioBot        OSL-3.0      https://github.com/Splamy/TS3AudioBot
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

"""
P7 补丁：放开别名的命名限制，允许中文别名（`!点歌 稻香`）。

背景：
    TS3AudioBot 的别名/命令名要过一道命名校验（CommandManager.LoadICommand）：

        private static readonly Regex CommandNamespaceValidator =
            new Regex(@"^[a-z\\d]+( [a-z\\d]+)*$", Util.DefaultRegexConfig & ~RegexOptions.IgnoreCase);

    所以 `[commands.alias]` 里写 `点歌 = "!play (!param 0)"` 会在启动时被拒绝，
    日志里只有一行 `Command has an invalid invoke name: 点歌`，然后这个别名静默失效。

处理：
    把字符类从 `[a-z\\d]` 放宽到 `[\\p{L}\\d]`（任意语言的字母 + 数字），
    同时补回 IgnoreCase（中文没有大小写，但英文别名 `DIAN` 也能用了）。

    空格分隔多词的写法 `dian ge` 依然支持 —— 把 ` ` 换成 `\\s+` 只是更宽容一点。

⚠️ 这个补丁会【改变命令解析器的行为】，属于进阶玩法：
    * 只影响「命令名 / 别名名」的合法性，不改变任何命令的语义；
    * 打完必须重新编译（patch-kit/rebuild-bot.sh 会自动调用本脚本）；
    * 中文别名里的参数转发规则和英文完全相同，仍然要写 `(!param 0)`。
"""
import sys

D = sys.argv[1] if len(sys.argv) > 1 else '/var/tmp/build/src'
P = D + '/TS3AudioBot/CommandSystem/CommandManager.cs'

OLD = (
"\t\tprivate static readonly Regex CommandNamespaceValidator =\n"
"\t\t\tnew Regex(@\"^[a-z\\d]+( [a-z\\d]+)*$\", Util.DefaultRegexConfig & ~RegexOptions.IgnoreCase);\n"
)

NEW = (
"\t\t// [PATCH P7] 放开命名限制：允许中文等非 ASCII 字母的别名/命令名。\n"
"\t\t// 原版是 ^[a-z\\d]+( [a-z\\d]+)*$ 且强制区分大小写，导致\n"
"\t\t//   [commands.alias] 点歌 = \"!play (!param 0)\"\n"
"\t\t// 会被拒绝（日志：Command has an invalid invoke name: 点歌）。\n"
"\t\tprivate static readonly Regex CommandNamespaceValidator =\n"
"\t\t\tnew Regex(@\"^[\\p{L}\\d]+(\\s+[\\p{L}\\d]+)*$\", Util.DefaultRegexConfig);\n"
)

s = open(P, encoding='utf-8').read()
if OLD not in s:
    if 'PATCH P7' in s:
        print('  [SKIP] P7 已应用')
        sys.exit(0)
    print('  [FAIL] P7 锚点未找到（源码版本可能不同，请检查 CommandManager.cs）')
    sys.exit(1)
open(P, 'w', encoding='utf-8').write(s.replace(OLD, NEW, 1))
print('  [OK] P7 已应用：别名/命令名支持中文（!点歌 稻香）')
