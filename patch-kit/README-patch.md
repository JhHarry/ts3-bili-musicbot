# 补丁工具包（patch-kit）

本目录用于**自己重新编译** TS3AudioBot。只有在你想改动机器人源码时才需要。

---

## 为什么需要它

上游 TS3AudioBot **2021-04-02 之后就没再发布过版本**，而它的音频管道有个会
**直接杀掉整个进程**的 bug：

```
Unhandled exception. System.NullReferenceException
   at TSLib.Audio.PreciseTimedPipe.ReadTick()  line 90
```

根因（已定位到源码）：

```csharp
// TS3AudioBot/Audio/Player.cs
private void CleanSource(IPlayerSource? source)
{
    MergePipe.Remove(source);   // 只是标记 changed = true
    source.Dispose();           // ⚠️ 立刻释放
}

// TSLib/Audio/PassiveMergePipe.cs
// safeProducerList 快照只在下一次 Read() 里才刷新
// → 读线程可能拿到【已释放的流】调用 Read() → 空引用 → SIGABRT
```

`master` 分支只有 **6 个 commit** 领先 0.12.0，且 `PreciseTimedPipe.cs`
**两版逐字节相同** —— 上游永远不会修。

---

## 四处补丁

| 编号 | 文件 | 作用 |
|---|---|---|
| **P1** | `TSLib/Audio/PreciseTimedPipe.cs` | `ReadLoop()` 包 try/catch + 失败计数。**这是封死致命路径的关键** |
| **P2** | `TSLib/Audio/PassiveMergePipe.cs` | `Remove()` 立即刷新快照消除竞态；`Read()` 跳过故障 producer |
| **P3** | `TS3AudioBot/Audio/AudioInputRewriter.cs`（新增） | 输入判别：歌名 → `/s/…`、BV号 → `/b/…`、真实 URL 透传 |
| **P4** | `TS3AudioBot/MainCommands.cs` | `CommandPlay` 接入 P3 的重写器 |
| **P5** | `TS3AudioBot/Bot.cs` | 命令错误不再往频道输出乱码原文（只写日志） |
| **P7** | `CommandSystem/CommandManager.cs` | 放开命令/别名的命名正则，允许**中文别名**（`!点歌 稻香`）|

## P7 —— 中文别名（本包默认已启用）

上游的 `CommandManager.LoadICommand()` 有一道命名校验：

```csharp
private static readonly Regex CommandNamespaceValidator =
    new Regex(@"^[a-z\d]+( [a-z\d]+)*$", Util.DefaultRegexConfig & ~RegexOptions.IgnoreCase);
```

所以 `[commands.alias]` 里写中文会在启动时被拒绝，日志只有一行
`Command has an invalid invoke name: 点歌`，别名静默失效 —— 很难发现。

**P7 把字符类从 `[a-z\d]` 放宽到 `[\p{L}\d]`**（任意语言的字母 + 数字），
同时补回 `IgnoreCase`（英文别名 `DIAN` 也能用了）。

```
- new Regex(@"^[a-z\d]+( [a-z\d]+)*$", Util.DefaultRegexConfig & ~RegexOptions.IgnoreCase);
+ new Regex(@"^[\p{L}\d]+(\s+[\p{L}\d]+)*$", Util.DefaultRegexConfig);
```

⚠️ 两个注意点：

1. **TOML 的 key 必须加引号**。TOML 规范不允许裸 key 出现非 ASCII 字符，
   所以是 `"点歌" = "!play (!param 0)"`，不是 `点歌 = ...`（后者直接是语法错误）。
2. 这条正则也管着**所有命令名**的合法性 —— 它只放宽命名，不改变任何命令语义。

**验证方式**（可复现）：

```bash
# 造一份含中文别名的 bot.toml，用打了 P7 / 没打 P7 的两个二进制各跑一次
# 看日志里有没有 "invalid invoke name"
timeout 12 ./TS3AudioBot 2>&1 | grep -c "invalid invoke name"
#   P7 版   → 0
#   原版    → 1
```

## 代理侧补丁（`scripts/bili_proxy.py`，用 `patch-kit/patch_search.py` 施加）

| 编号 | 位置 | 作用 |
|---|---|---|
| **P6** | `scripts/bili_proxy.py` 选源逻辑 | 四层筛选：① 只在 B站**音乐区**(`tids=3`)搜索，结果 <3 条自动回退全区；② 按「**原版 > 现场 > 翻唱/改编 > 纯器乐**」分档（用户自己搜的那一类不降级）；③ 同档内探真实音频码率择优，探到「原版 + ≥160kbps」即收手；④ **时长锚点** —— 以候选时长**中位数**估计"这首歌该多长"，用 `exp(-0.06·Δt)` 打分，整活版/裁剪版自然淘汰 |

`patch_bot.py` 应用 P1~P4，`patch_p4log.py` 追加调试日志（可选）。

### 代理侧补丁怎么施

P6 是针对 `bili_proxy.py` 的**幂等补丁脚本**，从 v4 基线开始打：

```bash
cp /opt/ts3bot/bili_proxy.py.bak-search /tmp/bili_proxy.py   # v4 基线
python3 patch-kit/patch_search.py /tmp/bili_proxy.py
sudo install -m 755 /tmp/bili_proxy.py /opt/ts3bot/bili_proxy.py
sudo systemctl restart bili-proxy
```

脚本自带备份（`.bak-search`）、语法自检、版本号升级。**可重复执行**，不会叠加。

#### P6 的设计要点（踩过的坑）

- **`原唱：XXX` 的冒号写法是翻唱者标注原唱的格式** —— 早期把「原唱」当原版正面词，
  导致 `前苏联小调完整版《星晴》- 原唱：周杰伦（气突苏）` 被误判为原版。现已移出正面词表，
  并把 `原唱：/原唱:/原曲：/翻自/改编自/苏联/气突苏/整活` 加入反面词表。
- **音乐区里仍然有翻唱和演奏**（`tids=31`/`tids=59` 就在音乐区），所以分区过滤
  **不能替代**分档逻辑，两者互补。
- **B站搜索接口限流狠**（连发 4 次会挂 3 次，HTTP 412）→ `api_get` 已加退避重试。

---

## 用法

```bash
sudo bash rebuild-bot.sh
```

脚本会自动：

1. 下载 .NET Core 3.1 SDK 与源码（首次约 5 分钟；之后**增量编译仅 75 秒**）
2. 应用补丁
3. 编译并部署，自动重启服务
4. 打印回滚方法

---

## 已知坑（都已在脚本里处理）

| 坑 | 说明 |
|---|---|
| **不要用 `/tmp`** | 很多机器 `/tmp` 是 477MB 的 tmpfs，118MB 的 SDK 解压会撑爆 → 脚本一律用 `/var/tmp` |
| **OpenSSL 版本** | .NET Core 3.1 需要 `libssl1.1`，新系统只有 OpenSSL 3 → 需要 `LD_LIBRARY_PATH=/opt/ts3bot/private-libs/usr/lib/x86_64-linux-gnu`（注意是 `/usr/lib/...` 子目录） |
| **NU1202 报错可忽略** | 构建目标会尝试 `dotnet tool install gitversion.tool / dotnet-script`，它们只支持 net8/9/10。该目标带 `IgnoreExitCode=true`，**只看有没有 `TS3AudioBot ->` 输出即可** |
| **工具清单要禁用** | 把仓库里的 `dotnet-tools.json` / `global.json` 改名，否则每次构建都报错 |

---

## 回滚

```bash
systemctl stop ts3audiobot
cp /opt/ts3bot/TS3AudioBot.orig-0.12.0 /opt/ts3bot/TS3AudioBot   # 上游原版
cp /opt/ts3bot/TS3AudioBot.prev        /opt/ts3bot/TS3AudioBot   # 上一版补丁
systemctl start ts3audiobot
```

---

## 验证

`test_cache.py` 是代理的缓存路径回归测试：

```bash
python3 patch-kit/test_cache.py
```

它覆盖 5 条缓存路径。**其中一条曾经会 500**：搜索缓存存的是 2 元组，
读取端却按 3 元组取下标 —— 症状是「首次点播正常，15 分钟后再点同一首必炸」。


---

## 第三方组件与出处

本目录（以及整个仓库）用到的开源组件，全部在此列明。
许可证全文见仓库根目录 [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md)。

| 组件 | 许可证 | 出处 | 用在哪 |
|---|---|---|---|
| **TS3AudioBot** 0.12.0 | OSL-3.0 | https://github.com/Splamy/TS3AudioBot | 本目录所有补丁的作用对象；`rebuild-bot.sh` 的可选下载源 |
| **.NET Core 3.1 SDK** | MIT | https://github.com/dotnet/runtime | `rebuild-bot.sh` 编译用（首次自动下载） |
| **libssl1.1 / libcrypto1.1** | OpenSSL License | Debian/Ubuntu 归档 | .NET Core 3.1 运行依赖（系统只有 OpenSSL 3） |
| **yt-dlp** | Unlicense | https://github.com/yt-dlp/yt-dlp | 兜底音源解析（`bili_proxy.py` 调用） |
| **pypinyin** | MIT | https://github.com/mozillazg/python-pinyin | `bili_proxy.py` 的拼音排序（可选） |
| **requests** | Apache-2.0 | https://github.com/psf/requests | `bili_proxy.py` 的连接复用（可选） |
| **Nayuki QR Code generator** | MIT | https://www.nayuki.io/page/qr-code-generator-library | `qrmini.py` 的标准参数表与流程参考 |
| **TeamSpeak 3 Server** | 私有许可 | https://www.teamspeak.com | 被部署的服务端本体 |
| **SQLite** | Public Domain | https://sqlite.org | `ts3-backup.sh` / `ts3-restore.sh` 的在线备份 |

> 说明：`patch_search.py`（P6，选源逻辑）和 `patch_p7.py`（P7，中文别名）都是
> **本仓库自己写的**，不是上游或第三方的代码。
