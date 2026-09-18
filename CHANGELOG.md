# 更新日志

本项目采用[语义化版本](https://semver.org/lang/zh-CN/)。版本号对应 GitHub Release 的 tag。

---

## v1.0.0 — 2026-09-18

首次公开发布。在此之前经过三轮实际部署迭代（见 v0.1.0 / v0.2.0），
本版本在此基础上完成了完整的现场测试与修复。

### 新增功能

**安装流程**

* 安装时可选组件：交互询问「是否安装 B站点歌机器人」，选否则仅部署 TeamSpeak 3
  服务端（内存占用由约 250 MB 降至约 30 MB）；亦可通过 `WITH_BOT=0/1` 跳过询问。
  安装后可通过 `sudo WITH_BOT=1 bash install.sh` 补装。
* 安装完成后自动生成 `TS3-服务器信息.txt`（写入脚本所在目录与 `/root`），
  内容包括连接地址、管理员令牌、点歌指令、管理凭据与常用运维命令。
* 新增前置命令自检：安装依赖后校验全部所需命令是否就位，缺失即明确报错。

**点歌与登录**

* 内置 20 个拼音与英文简写别名（`!dian`、`!zan`、`!ting`、`!xia`、`!now` 等），
  以及 15 个中文别名（`!点歌`、`!暂停`、`!下一首` 等）。
* `scripts/qrmini.py`：纯 Python 实现的 QR 码生成器，仅依赖标准库 `zlib`，
  无需 qrencode、Pillow 或 qrcode。
* `scripts/bili_login.py`：B站扫码登录，同时输出终端字符画与 PNG 图片，
  登录成功自动清理二维码文件并修正 cookie 属主；新增 `--check` 校验登录状态。

**运维**

* `systemd/ts3-boot-check.service`：开机 30 秒后检查各服务状态，未启动的自动拉起。
* 安装时自动禁用 `kdump-tools` 与 `apt-daily` 两个开机阻塞项，缩短启动时间约 18 秒。
* `docs/COMMANDS.md`：完整指令手册，含自定义别名的必要规则说明。
* `docs/TROUBLESHOOTING.md`：按「症状 → 原因 → 处理」组织的排错手册。

### 重要修复

以下问题均在真实部署环境中复现并修复。

**导致部署失败的问题**

| 现象 | 原因 | 处理 |
|---|---|---|
| 机器人无法启动，提示缺少 `libssl.so.1.1` | 安装脚本仅处理 `private-libs.tar.gz` 与 `.deb` 两种形式，而仓库中为目录 `vendor/private-libs/`，兼容层未被安装 | 补充目录分支；缺少该文件时直接终止安装 |
| 解压机器人附件失败 | 依赖列表中缺少 `xz-utils`（`tar -xJf` 需要） | 加入依赖列表 |
| 生成异地备份密钥时中断 | 依赖列表中缺少 `openssh-client`（`ssh-keygen`） | 加入依赖列表 |
| TeamSpeak 3 安装后目录为空 | 清理旧版本的 `rm -rf` 位于解包之后，误删刚解出的文件 | 调整为先清理后安装 |
| `Failed to determine credentials for user '__RUN_USER__'` | systemd 单元的占位符仅部分回填 | 全量回填并增加残留检查 |
| 机器人无法启动，提示 `Failed to load library libopus` | 仅安装 `libopus0`，而 .NET 需要不带版本号的 `libopus.so`（仅 `libopus-dev` 提供） | 依赖列表加入 `libopus-dev` |
| 服务器属性校正被跳过 | TeamSpeak 3.13.7 起凭据仅输出至 stdout，不再写入 `logs/` 目录 | 改为同时读取日志文件与 `journalctl` |
| 抓取到上一次安装的旧密码 | `journalctl` 保留历史记录，未限定时间范围 | 查询加入 `--since` 时间窗口 |
| 部署信息中的管理员令牌缺失 | 与上一条同源 | 同上，并延长轮询至 50 秒（令牌生成晚于密码约 30 秒） |

**导致功能异常的问题**

| 现象 | 原因 | 处理 |
|---|---|---|
| 所有客户端连接后被立即断开 | `virtualserver_hostmessage_mode = 3` 的语义为「弹出消息后强制断开」 | 新增 `ts3-serverset.py`，安装时校正为 `1` 并复核 |
| 新用户无法连接 | `needed_identity_security_level = 8`，而新客户端默认为 5 | 安装时写入 5（可用 `SECLEVEL` 覆盖） |
| 设置空密码后仍需输入密码 | `virtualserver_password` 与 `flag_password` 未成对设置 | 工具中成对写入 |
| 服务器名称排序异常 | 名称末尾存在不可见空格 | 写入前执行 `rstrip()` |
| 服务器重启后机器人延迟 5 分钟恢复 | `[bot.reconnect] onshutdown = ["5m"]` | 模板改为递进重连序列 |
| 排查时日志无客户端记录 | `virtualserver_log_client` 默认为 0 | 安装时置为 1 |
| 机器人无法进入频道 | `bot.toml` 中频道号指向源环境 | 打包时重置为 `/1` |
| 还原后服务无法启动 | 备份包中的 systemd 单元带有源主机用户名 | 还原时自动重映射 `User=` / `Group=` |
| `systemctl enable` 报错且服务不自启 | 自定义 unit 缺少 `[Install]` 段 | 安装时执行单元自检 |
| 日志中 92% 为心跳噪声 | `NLog.config` 默认为 `Debug` | 模板调整为 `Info` |
| Web API 无鉴权暴露 | 上游默认绑定全部网卡 | 模板改为仅绑定 `localhost` |
| 搜索结果非原曲 | 选源逻辑仅检查标题 | 代理内置分区过滤、分档、码率探测、时长锚点与拼音排序 |
| 备份脚本无输出即退出 | 目标主机无 `ts3server.sqlitedb`，在 `set -e` 下终止 | 增加前置判断，无实例时正常退出 |

### 打包与发布

* 体积策略：代码与 `vendor/` 中的 TS3 服务端、yt-dlp、libssl1.1 兼容层纳入 git
  （约 29 MB）；机器人二进制（97.5 MiB，接近 GitHub 单文件上限）作为 Release 附件分发。
* `build-vendor.sh` 一次生成可提交的 `vendor/` 与 Release 附件。
* `fetch-bot.sh` 由 `install.sh` 自动调用；亦支持手动解压附件实现完全离线安装。
* 强制隐私检查：扫描公网 IP、域名、私钥、cookie 名与家目录路径，
  并检查凭证类文件，未通过则不产出任何产物。
* 仓库结构：`LICENSE`（MIT）、`THIRD_PARTY_NOTICES.md`、`.gitignore`、
  `.gitattributes`、`repo.conf`（发布地址统一配置）、`docs/RELEASE.md`、
  GitHub Actions 语法与回归检查。

### 验证情况

* 在全新的 Ubuntu 24.04 x86_64 实例上完成完整安装测试：
  依赖安装、二进制下载、服务启动、端口监听、备份任务均正常。
* 点歌链路实测：请求 `/s/稻香` 返回可播放的音频流。
* 二维码生成器与 `qrencode` 逐位比对，并通过 `zbarimg` 解码回归（40 组用例）。
* 全部 shell 脚本通过 `bash -n` 与 ShellCheck，Python 脚本通过 `py_compile`。

---

## v0.2.0 — 2026-09-16

* 修复跨机迁移时的问题：TeamSpeak 3 解包顺序、systemd 单元占位符回填不完整、
  缺少 `sqlite3` / `libopus-dev` / `libsodium23`、还原时单元带入源主机用户名。
* 新增 `ts3-backup-push`、`ts3-backup-prune`、`ts3-bot` 及相关 systemd 单元。
* 加入 TS3AudioBot 崩溃修复补丁 P1 至 P5，根因为 `PreciseTimedPipe` 的空引用。

---

## v0.1.0 — 2026-09-15

* 首个可用的离线部署包：TeamSpeak 3 3.13.7、自行编译的 TS3AudioBot、
  B站音频代理 v4。
* 本地热备份、一键还原、异地冷备份仓库。
* 内存守卫与重启后自动续播。
