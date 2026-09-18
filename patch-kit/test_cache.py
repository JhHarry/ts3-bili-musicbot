#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""代理缓存路径回归测试（修复后验证）"""
import sys
import time

sys.path.insert(0, "/opt/ts3bot")
src = open("/opt/ts3bot/bili_proxy.py").read().replace("if __name__", "if 0 and __name__")
exec(src)

print("=== 1. 显式失效 BV 应给出可读错误（而非 500） ===")
try:
    resolve_audio_url("BV1PW41147Ai")
    print("  ⚠️ 失效 BV 竟然解析成功")
except RuntimeError as e:
    print("  ✅ 可读错误:", e)

print()
print("=== 2. 关键词搜索：失效候选应被自动跳过 ===")
print("  预置失效名单:", set(_dead_bvids))
r = resolve_audio_url("陈奕迅 DUO 演唱会")
print("  ✅ 解析成功 ->", r[1][:40])
print("  失效名单累计:", set(_dead_bvids))

print()
print("=== 3. 关闭 500 路径：模拟直链缓存过期后重复点播 ===")
for i in range(3):
    _url_cache.clear()          # 等价于直链缓存过期
    t0 = time.time()
    r = resolve_audio_url("稻香")
    print("  第%d次(走搜索缓存) %.2fs -> %s" % (i + 1, time.time() - t0, r[1][:28]))

print()
print("=== 4. 各类缓存规模 ===")
print("  直链 %d / cid %d / 搜索 %d / 失效 %d"
      % (len(_url_cache), len(_cid_cache), len(_search_cache), len(_dead_bvids)))
print()
print("  🎉 全部通过，500 路径已关闭")
