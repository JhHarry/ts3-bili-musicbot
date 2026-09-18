# 更新日志

版本号对应 GitHub Release 的 tag。

---

## v13 — 2026-09-18

这一版是拿**上海真机部署**踩到的坑反推回来改的。

### ✨ 新增

* **可选组件**：安装时先问「是否安装 B站点歌机器人？[Y/n]」——
  选 `n` 就只装 TS3 语音服务器（不下载机器人、不装代理、内存占用降到 ~30 MB）；
  也可用 `WITH_BOT=0/1` 跳过提问。装完随时能 `sudo WITH_BOT=1 bash install.sh` 补装
* **真正开箱即用**：`git clone` 后只需 `sudo bash install.sh` 一条命令。
  仓库自带 TS3 服务端 / yt-dlp / libssl1.1 兼容层（约 29 MB）；
  音乐机器人（97.5 MB，贴着 GitHub 100 MiB 单文件上限）作为 **Release 附件**
  由 `install.sh` 自动下载一次，也可手动解压成 `vendor/TS3AudioBot` 走纯离线
* **README 重写为懒人包**：突出「系统与机器配置要求」「防火墙」「三条命令开箱」，
  原理说明全部挪到 `docs/` 与 `patch-kit/`，主流程不再夹带解释
* 依赖表精简：二维码改成纯 Python 生成后，不再需要 `qrencode`

* **点歌指令大扩容**
  * 内置 20 个拼音/英文简写别名：`!dian`、`!bo`、`!zan`、`!ting`、`!xia`、`!now`……
  * 频道说明（description / topic）重写，把常用指令直接贴在频道里
  * 新增 `docs/COMMANDS.md`：完整指令手册 + 自定义别名的两个必知规则
* **B站扫码登录自动化**
  * `scripts/qrmini.py`：**纯 Python 的 QR 码生成器**，只用标准库 `zlib`，
    零外部依赖（不需要 qrencode / Pillow / qrcode）
  * `scripts/bili_login.py` 重写：终端字符画 + **PNG 图片**双形态输出，
    登录成功后自动删掉 PNG（里面是登录票据）、自动把 cookie 的属主改成机器人用户
  * 新增 `--check`（校验现有 cookie 还有没有效）、`--json`、`--no-terminal`、`--png`
* **可开源的仓库结构**：`LICENSE`(MIT)、`THIRD_PARTY_NOTICES.md`、`.gitignore`、
  `.gitattributes`、`repo.conf`（发布地址只改这一处）、
  `build-vendor.sh`（生成 `vendor/` + Release 附件）、`fetch-bot.sh`、
  `docs/RELEASE.md`、GitHub Actions 语法检查
* `systemd/ts3-boot-check.service`：开机 30 秒后兜底检查各服务
* `install.sh`：自动 `disable` `kdump-tools` / `apt-daily`，**开机快约 18 秒**

### 🐛 修复（按"部署时会不会炸"排序）

| 现象 | 根因 | 修法 |
|---|---|---|
| **机器人起不来**：`libssl.so.1.1` 找不到 | `install.sh` 只处理 `private-libs.tar.gz` / `.deb` 两种形态，而仓库里是**目录** `vendor/private-libs/` → 兼容层根本没装上，且只打一行警告就继续 | 补上目录分支；找不到 `libssl.so.1.1` 时**直接 die**，不再带着隐患往下跑 |
| `fetch-bot.sh` 解不开 `ts3audio...tar.xz` | 依赖表里没有 **`xz-utils`**（`tar -xJf` 需要它），精简镜像上会直接失败 | 加入依赖表 |
| 生成异地备份密钥时脚本中断 | 依赖表里没有 **`openssh-client`**，`ssh-keygen` 在精简镜像上不存在 | 加入依赖表 |
| `ts3-restore.sh` 的端口检查报错 | 缺 `iproute2`（`ss`）| 加入依赖表 |
| `ts3-bot.sh` 状态显示异常 | 缺 `procps`（`pgrep`）| 加入依赖表 |
| apt 源更新失败时报错难懂 | `apt-get update` 没有错误处理 | 加明确提示；依赖安装失败时**重试一次并显示 apt 原文** |
| 装到一半才发现缺命令 | 没有前置校验 | 新增**前置命令自检**：`curl/tar/xz/sqlite3/python3/ssh-keygen/scp/ss/ffmpeg…` 缺任何一个立即报出来 |

| 现象 | 根因 | 修法 |
|---|---|---|
| TS3 目录空的、服务无限重启 | `rm -rf $TS3_DIR` 写在**解包之后**，把刚解出来的删了 | 改为先清后解到临时目录，兼容两种 tar 结构并校验二进制 |
| `Failed to determine credentials for user '__RUN_USER__'` | 占位符只回填了部分单元，漏了 `teamspeak3.service` 和 drop-in | 全量回填 + **残留检查** |
| `Failed to load library libopus` | 只装了 `libopus0`，而 .NET 找的是不带版本号的 `libopus.so`（只有 `-dev` 包提供该软链）| 依赖表加 `libopus-dev`；另补 `sqlite3`（备份必需）与 `libsodium23` |
| **所有人一连上就被踢**，日志只写 `reasonmsg=Leaving` | `virtualserver_hostmessage_mode=3` 的语义是"弹消息后强制断开" | 新增 `ts3-serverset.py`，部署时强制校正为 `1` 并复核 |
| 新人连不上 | `needed_identity_security_level=8` | 部署时写入 5（可在 `SECLEVEL` 覆盖）|
| 设了空密码却仍要输密码 | `virtualserver_password` 与 `flag_password` 没成对设置 | `ts3-serverset.py` 成对写入 |
| 服务器名排序怪异 | 名字末尾有看不见的空格 | 写入前 `rstrip()` |
| 服务器重启后机器人干等 5 分钟 | `[bot.reconnect] onshutdown = ["5m"]` | 模板改为 `["2s","5s","10s","20s","30s","repeat last"]` |
| 排查时日志里什么都看不到 | `virtualserver_log_client` 默认 0 | 部署时置 1 |
| 机器人进不去频道 | `bot.toml` 的 `channel` 指向源机的具体频道号 | 打包时重置为 `/1` |
| 备份脚本空转失败 | 冷备机器上没有 `ts3server.sqlitedb`，`set -e` 直接退出 | 开头兜底：没有实例就打印说明并正常退出 |
| 还原后服务起不来 | 备份包里的 systemd 单元带着**源机用户名** | 还原时自动重映射 `User=`/`Group=`，drop-in 一并处理 |
| `systemctl enable` 报 "instance name specified" | 自定义 unit 漏写 `[Install] WantedBy=` | `install.sh` 增加单元自检 |
| 机器人日志 92% 是心跳噪声 | `NLog.config` 默认 `Debug` | 模板改 `Info` |
| Web API 无密码暴露 | 上游默认 `hosts = ["*"]` | 模板改 `["localhost"]`，外部走 SSH 隧道 |
| 点歌选到翻唱 / 演奏 / MV 抠音轨 | 选源只看标题 | 代理内置 P6 四层筛选 + tag 识别 + 时长锚点 + 拼音排序 |

### 🔧 工程化

* 打包流程改为 **`build-vendor.sh` 一次产出「可提交的 `vendor/`」+「Release 附件」** ——
  文本文件以仓库为唯一真源，构建机只提供二进制，避免"改了模板却只改了一台机器"
* 新增 `OPT_ROOT`，冷备机器上可以先把归档解到临时目录再打包，不污染 `/opt`
* 隐私扫描关键词扩充（IP 段、`/home/<user>`、身份密钥、cookie 名……），
  并强制重置 `bot.toml` 的频道号、清空身份私钥

### ✅ 验证方式

* 二维码生成器：与 `qrencode` 逐位对比 + `zbarimg` 解码回归（40 组用例全通过）
* `ts3-serverset.py`：在真实 TS3 服务器上执行，复核输出全部 `✓` 且幂等
* 全部 shell / python 脚本通过 `bash -n` 与 `py_compile`

---

## v12 — 2026-09-16

* 修掉 v11 迁移包里 4 个会在新机器上炸的问题：
  TS3 解包顺序、`__RUN_USER__` 漏回填、缺 `sqlite3`/`libopus-dev`/`libsodium23`、
  还原时 systemd 单元带着源机用户名
* 新增 `ts3-backup-push` / `ts3-backup-prune` / `ts3-bot` 与对应 systemd 单元
* 机器人崩溃修复补丁 P1~P5（`PreciseTimedPipe` 空引用是真凶）

---

## v11 — 2026-09-15

* 首个可用的离线迁移包：TS3 3.13.7 + 自编译 TS3AudioBot + B站音频代理 v4
* 本地热备份 / 一键还原 / 异地冷备仓库
* 内存守卫 + 重启后自动续播
