#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ──────────────────────────────────────────────────────────────────────────
# 补丁对象：
#   TS3AudioBot        OSL-3.0      https://github.com/Splamy/TS3AudioBot
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

"""
P5 补丁：不要把命令错误原文发到频道里。

现象（用户截图）：
    机器人往频道里回一段【未解析的标记 + 内部错误原文】，例如：

      <BOT>  [COLOR=red]Error: Could not load. (media: Unknown request error.)

原因：
    Bot.cs 的 TryCatchCommand 把内部异常原文发到频道：
        info.Write(TextMod.Format(config.Commands.Color,
            strings.error_call_error.Mod().Color(Color.Red).Bold(), ex.Message))
    TextMod 生成的 [B][COLOR=red] 标记 TS3 客户端不解析 → 原样显示，
    而且 "media: Unknown request error." 对用户毫无意义。

处理：错误只写日志，频道里不再输出。
      想改成简短提示的话，把 DISABLED 行的注释按说明替换即可。
"""
import sys

D = sys.argv[1] if len(sys.argv) > 1 else '/var/tmp/build/src'
P = D + '/TS3AudioBot/Bot.cs'

OLD = (
"\t\t\tcatch (AudioBotException ex)\n"
"\t\t\t{\n"
"\t\t\t\tNLog.LogLevel commandErrorLevel = answer ? NLog.LogLevel.Debug : NLog.LogLevel.Warn;\n"
"\t\t\t\tLog.Log(commandErrorLevel, ex, \"Command Error ({0})\", ex.Message);\n"
"\t\t\t\tif (answer)\n"
"\t\t\t\t{\n"
"\t\t\t\t\tawait info.Write(TextMod.Format(config.Commands.Color, strings.error_call_error.Mod().Color(Color.Red).Bold(), ex.Message))\n"
"\t\t\t\t\t\t.CatchToLog(Log);\n"
"\t\t\t\t}\n"
"\t\t\t}\n"
"\t\t\tcatch (Exception ex)\n"
"\t\t\t{\n"
"\t\t\t\tLog.Error(ex, \"Unexpected command error: {0}\", ex.Message);\n"
"\t\t\t\tif (answer)\n"
"\t\t\t\t{\n"
"\t\t\t\t\tawait info.Write(TextMod.Format(config.Commands.Color, strings.error_call_unexpected_error.Mod().Color(Color.Red).Bold(), ex.Message))\n"
"\t\t\t\t\t\t.CatchToLog(Log);\n"
"\t\t\t\t}\n"
"\t\t\t}\n"
)

NEW = (
"\t\t\tcatch (AudioBotException ex)\n"
"\t\t\t{\n"
"\t\t\t\tNLog.LogLevel commandErrorLevel = answer ? NLog.LogLevel.Debug : NLog.LogLevel.Warn;\n"
"\t\t\t\tLog.Log(commandErrorLevel, ex, \"Command Error ({0})\", ex.Message);\n"
"\t\t\t\t// [PATCH P5] 频道里不再回显内部错误原文。\n"
"\t\t\t\t// 原因：TextMod 生成的 [B][COLOR=red] 标记 TS3 客户端不解析，会原样显示；\n"
"\t\t\t\t// 且 \"media: Unknown request error.\" 之类对用户毫无意义。细节只写日志。\n"
"\t\t\t\t// 若想给用户一句简短提示，取消下面一行注释即可：\n"
"\t\t\t\t// if (answer) await info.Write(\"❌ 这首歌加载失败，换个版本试试\").CatchToLog(Log);\n"
"\t\t\t}\n"
"\t\t\tcatch (Exception ex)\n"
"\t\t\t{\n"
"\t\t\t\tLog.Error(ex, \"Unexpected command error: {0}\", ex.Message);\n"
"\t\t\t\t// [PATCH P5] 同上，不再向频道输出内部异常\n"
"\t\t\t}\n"
)

s = open(P, encoding='utf-8').read()
if OLD not in s:
    if 'PATCH P5' in s:
        print('  [SKIP] P5 已应用')
        sys.exit(0)
    print('  [FAIL] P5 锚点未找到')
    sys.exit(1)
open(P, 'w', encoding='utf-8').write(s.replace(OLD, NEW, 1))
print('  [OK] P5 已应用：命令错误不再输出到频道')
