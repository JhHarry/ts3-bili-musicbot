#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ──────────────────────────────────────────────────────────────────────────
# 补丁对象与构建依赖：
#   TS3AudioBot        OSL-3.0      https://github.com/Splamy/TS3AudioBot
#   .NET Core 3.1      MIT          https://github.com/dotnet/runtime
#   libssl1.1/libcrypto1.1  OpenSSL License  （.NET Core 3.1 运行依赖，随包分发）
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

"""
TS3AudioBot 本地补丁（0.12.0 / master 通用）
  P1. TSLib/Audio/PreciseTimedPipe.cs   —— tick 线程 try/catch，杜绝未捕获异常杀进程
  P2. TSLib/Audio/PassiveMergePipe.cs   —— 消除 Remove 与 Dispose 之间的竞态
  P3. TS3AudioBot/Audio/AudioInputRewriter.cs (新增) —— !play 直接吃歌名
  P4. TS3AudioBot/MainCommands.cs       —— CommandPlay 调用重写器
"""
import os, sys, re

D = sys.argv[1] if len(sys.argv) > 1 else '/var/tmp/build/src'
def rd(p):
    with open(p, encoding='utf-8') as f: return f.read()
def wr(p, s):
    with open(p, 'w', encoding='utf-8') as f: f.write(s)

def must_replace(text, old, new, tag):
    if old not in text and new in text:
        print(f'  [SKIP] {tag}: 已应用'); return text
    if old not in text:
        print(f'  [FAIL] {tag}: 未找到锚点'); sys.exit(1)
    if text.count(old) != 1:
        print(f'  [FAIL] {tag}: 锚点不唯一 ({text.count(old)})'); sys.exit(1)
    return text.replace(old, new)

# ---------------------------------------------------------------- P1
p = os.path.join(D, 'TSLib/Audio/PreciseTimedPipe.cs')
s = rd(p)
old = """		private void ReadLoop()
		{
			while (running)
			{
				if (!Paused)
					ReadTick();
				Thread.Sleep(SendCheckInterval);
			}
		}"""
new = """		private int tickFailures;

		private void ReadLoop()
		{
			while (running)
			{
				try
				{
					if (!Paused)
						ReadTick();
					tickFailures = 0;
				}
				catch (Exception ex)
				{
					// [PATCH P1] Upstream lets any transient exception from the audio
					// producer chain (typically a song switch racing with Dispose)
					// tear down the whole process. Swallow it and keep the pipe alive.
					tickFailures++;
					if (tickFailures <= 3)
						Console.Error.WriteLine($"[PATCH P1] audio tick failed ({tickFailures}x): {ex}");
					try { AudioTimer.ResetRemoteBuffer(); } catch { }
					if (tickFailures >= 50)
					{
						tickFailures = 0;
						Thread.Sleep(TimeSpan.FromMilliseconds(500));
					}
				}
				Thread.Sleep(SendCheckInterval);
			}
		}"""
s = must_replace(s, old, new, 'P1')
wr(p, s); print('  [OK] P1 PreciseTimedPipe.ReadLoop 已加固')

# ---------------------------------------------------------------- P2
p = os.path.join(D, 'TSLib/Audio/PassiveMergePipe.cs')
s = rd(p)
old = """				lock (listLock)
				{
					var removed = producerList.Remove(removeProducer);
					changed |= removed;
					return removed;
				}"""
new = """				lock (listLock)
				{
					var removed = producerList.Remove(removeProducer);
					if (removed)
					{
						// [PATCH P2] refresh the snapshot immediately: the caller
						// disposes the producer right after Remove() returns, so a
						// stale snapshot would hand out a disposed stream to Read().
						safeProducerList = producerList.ToArray();
						changed = false;
					}
					return removed;
				}"""
s = must_replace(s, old, new, 'P2a')
old = """			if (safeProducerList.Length == 1)
				return safeProducerList[0].Read(buffer, offset, length, out meta);"""
new = """			if (safeProducerList.Length == 1)
			{
				try
				{
					return safeProducerList[0].Read(buffer, offset, length, out meta);
				}
				catch (Exception ex)
				{
					// [PATCH P2] never let a dying producer take the process down
					Console.Error.WriteLine($"[PATCH P2] producer read failed, skipping: {ex.GetType().Name}");
					return 0;
				}
			}"""
s = must_replace(s, old, new, 'P2b')
old = """			foreach (var producer in safeProducerList)
			{
				int ppread = producer.Read(buffer, offset, maxReadLength, out meta);
				if (ppread == 0)
					continue;"""
new = """			foreach (var producer in safeProducerList)
			{
				int ppread;
				try
				{
					ppread = producer.Read(buffer, offset, maxReadLength, out meta);
				}
				catch (Exception ex)
				{
					// [PATCH P2] skip broken producers instead of crashing
					Console.Error.WriteLine($"[PATCH P2] producer read failed, skipping: {ex.GetType().Name}");
					continue;
				}
				if (ppread == 0)
					continue;"""
s = must_replace(s, old, new, 'P2c')
wr(p, s); print('  [OK] P2 PassiveMergePipe 竞态与容错已修')

# ---------------------------------------------------------------- P3
rewriter = '''// [PATCH P3] Typed-by-hand play targets.
// Lets people write  !play <song name>  instead of a full proxy url.
using System;
using System.Linq;

namespace TS3AudioBot.Audio
{
	public static class AudioInputRewriter
	{
		private const string SearchBase = "http://127.0.0.1:8087/s/";
		private const string VideoBase = "http://127.0.0.1:8087/b/";

		public static string Rewrite(string input, ref string[] attributes)
		{
			var attrs = attributes ?? Array.Empty<string>();

			// PlayManager.ParseAttributes only understands "@<offset>".
			// Anything else the user typed after the name belongs to the song title.
			if (attrs.Length > 0)
			{
				var extra = attrs.Where(a => !string.IsNullOrEmpty(a) && !a.StartsWith("@", StringComparison.Ordinal)).ToArray();
				if (extra.Length > 0)
				{
					input = (input ?? string.Empty) + " " + string.Join(" ", extra);
					attributes = attrs.Where(a => !string.IsNullOrEmpty(a) && a.StartsWith("@", StringComparison.Ordinal)).ToArray();
				}
			}

			if (string.IsNullOrWhiteSpace(input))
				return input;

			var t = input.Trim();

			// local paths stay local
			if (t.StartsWith("/", StringComparison.Ordinal) || t.StartsWith("\\\\", StringComparison.Ordinal) || t.StartsWith(".", StringComparison.Ordinal))
				return input;

			if (Uri.TryCreate(t, UriKind.Absolute, out var uri) && !string.IsNullOrEmpty(uri.Scheme) && uri.Scheme.Length > 1)
			{
				var host = (uri.Host ?? string.Empty).ToLowerInvariant();
				if (host == "b23.tv" || host == "bilibili.com" || host.EndsWith(".bilibili.com", StringComparison.Ordinal))
					return VideoBase + Uri.EscapeDataString(t);
				return input; // real url (direct mp3/stream) -> untouched
			}

			// bilibili id shorthand
			if (t.StartsWith("BV", StringComparison.OrdinalIgnoreCase) && t.Length >= 12)
				return VideoBase + Uri.EscapeDataString(t);
			if (t.StartsWith("av", StringComparison.OrdinalIgnoreCase) && t.Length > 2 && long.TryParse(t.Substring(2), out _))
				return VideoBase + Uri.EscapeDataString(t);

			// anything else is a search query
			return SearchBase + Uri.EscapeDataString(t);
		}
	}
}
'''
os.makedirs(os.path.join(D, 'TS3AudioBot/Audio'), exist_ok=True)
wr(os.path.join(D, 'TS3AudioBot/Audio/AudioInputRewriter.cs'), rewriter)
print('  [OK] P3 AudioInputRewriter.cs 已新增')

# ---------------------------------------------------------------- P4
p = os.path.join(D, 'TS3AudioBot/MainCommands.cs')
s = rd(p)
old = """		[Command("play")]
		public static async Task CommandPlay(PlayManager playManager, InvokerData invoker, string url, params string[] attributes)
			=> await playManager.Play(invoker, url, meta: PlayManager.ParseAttributes(attributes));"""
new = """		[Command("play")]
		public static async Task CommandPlay(PlayManager playManager, InvokerData invoker, string url, params string[] attributes)
		{
			// [PATCH P4] accept a plain song name / BV id / bilibili link, not just a url
			var target = AudioInputRewriter.Rewrite(url, ref attributes);
			await playManager.Play(invoker, target, meta: PlayManager.ParseAttributes(attributes));
		}"""
s = must_replace(s, old, new, 'P4')
wr(p, s); print('  [OK] P4 CommandPlay 已接入重写器')

print('全部补丁应用完成')
