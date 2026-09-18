# TS3 + B站点歌机器人 · 懒人一键包

[![Release](https://img.shields.io/github/v/release/JhHarry/ts3-bili-musicbot?display_name=tag&sort=semver&color=2ea44f)](https://github.com/JhHarry/ts3-bili-musicbot/releases/latest)
[![Stars](https://img.shields.io/github/stars/JhHarry/ts3-bili-musicbot?style=flat&color=f9c513)](https://github.com/JhHarry/ts3-bili-musicbot/stargazers)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Ubuntu%20%7C%20Debian%20%C2%B7%20x86__64-important)](#-系统与配置要求)
[![Shell](https://img.shields.io/badge/shell-bash-4EAA25?logo=gnubash&logoColor=white)](#)
[![Python](https://img.shields.io/badge/python-3.8%2B-3776AB?logo=python&logoColor=white)](#)

**克隆下来 → 跑一条命令 → 完事。**

在频道里发 `!点歌 稻香` 或 `!play 稻香` 就出声，约 2 秒。

---

## ⚡ 开箱即用（3 条命令）

```bash
git clone https://github.com/JhHarry/ts3-bili-musicbot.git
cd ts3-bili-musicbot
sudo bash install.sh
```

就这三条。仓库里已经带着 TS3 服务端、yt-dlp、libssl1.1 兼容层（约 29 MB），
音乐机器人（35~40 MB）由 `install.sh` **自动下载一次** —— 之后的部署都是纯本地。

它会把剩下的全做完：

```
✓ 装系统依赖（ffmpeg / sqlite3 / libopus-dev / libsodium23 …）
✓ 自动补齐音乐机器人（只在第一次，约 35~40 MB）
✓ 部署 TS3 服务端 + 音乐机器人 + B站音频代理
✓ 建频道结构、写点歌说明、配好 36 条别名
✓ 注册开机自启 + 每分钟守护 + 每天自动备份
✓ 打印连接地址和管理令牌
```

**纯内网 / 无法访问 GitHub 的机器**：把机器人压缩包（`ts3audiobot-patched.tar.xz`）
手动解压成 `vendor/TS3AudioBot`，`install.sh` 会检测到并跳过下载 —— 全程离线。

安装时会先问你一句：

```
==> 组件选择
    本脚本可以只装 TS3 语音服务器，也可以连 B站点歌机器人一起装。
    是否安装 B站点歌机器人？[Y/n]
```

* **回车 / y** → 装全套（TS3 + 点歌机器人）
* **n** → 只装 TS3 语音服务器（不下载机器人、不装代理、不占内存）

非交互场景（脚本调用、管道）**默认装全套**；也可以用环境变量直接指定，跳过提问：

```bash
sudo WITH_BOT=0 bash install.sh     # 只要 TS3 语音服务器
sudo WITH_BOT=1 bash install.sh     # 全套（默认）
```

其它可调参数：

| 变量 | 默认 | 说明 |
|---|---|---|
| `WITH_BOT` | 提问（非交互时 `1`）| `0` = 只装 TS3；`1` = 装全套 |
| `BOT_NAME` | `MusicBot🎵Bot` | 机器人昵称（仅装机器人时有效）|
| `SERVER_NAME` | `My TeamSpeak Server` | 服务器名 |
| `SERVER_PW` | 空 | 服务器密码；留空 = 不需要密码 |
| `SECLEVEL` | `5` | 身份安全等级（**别设 8**，新人会连不上）|
| `BILI_LOGIN` | `0` | 设 `1` 时部署完自动弹扫码登录 |
| `BACKUP_TARGET` | 空 | 异地冷备仓库地址 |
| `PRIVATE_PW` | 空 | 私密房间密码 |

> 装完之后随时可以补装机器人：`sudo WITH_BOT=1 bash install.sh`（已装的部分会跳过）。

---

## 📋 系统与配置要求

### 系统

| 项目 | 要求 |
|---|---|
| **操作系统** | Ubuntu 20.04 / 22.04 / 24.04 / 26.04 LTS，Debian 11 / 12 / 13 |
| **架构** | **x86_64 / amd64 仅**。ARM（aarch64）**不支持** —— TS3 官方服务端只发布 amd64 二进制 |
| **权限** | root / sudo 免密 |
| **网络** | 需要能访问 **apt 源**；**首次安装**还要能访问 GitHub（下载机器人 35~40 MB，之后不再需要）|
| **实测环境** | Ubuntu 26.04 LTS · 内核 7.0 · 2 核 / 1962 MB · 腾讯云轻量 |

> 脚本会自己检查：架构不对 / 磁盘不够会**直接报错退出**，不会装到一半。

### 机器配置

| 档位 | CPU | 内存 | 磁盘 | 适用 |
|---|---|---|---|---|
| **最低** | 1 核 | 1 GB | 3 GB | 自己和小伙伴听歌（≤10 人）|
| **推荐** | 2 核 | 2 GB | 10 GB | 满员 32 人 |

**实测占用**（上海服务器正在跑的实例）：

| 组件 | 内存 | 磁盘 |
|---|---|---|
| TeamSpeak 3 服务端 | ~30 MB | 24 MB |
| 音乐机器人 TS3AudioBot | ~110 MB（涨到 450 MB 会被守护自动重启）| 104 MB |
| B站音频代理 | ~95 MB | — |
| **合计** | **常态 ~250 MB，峰值 ~600 MB** | **~130 MB + 备份** |

* 内存不足 900 MB 且没有 swap 时，脚本会**自动创建 2 GB swapfile**（不用你管）
* 备份每次约 76 KB，每天 2 次，自动只保留最近 10 GB
* 带宽：每个听歌的人约 **12 KB/s**（Opus 98 kbps）→ 10 人约 120 KB/s，满员 32 人约 390 KB/s

### 端口

| 端口 | 协议 | 必须开？ |
|---|---|---|
| `9987` | **UDP** | ✅ **必须**（语音）|
| `30033` | TCP | ✅ 建议（文件传输 / 频道头像）|
| `10011` | TCP | ❌ **不要开**（ServerQuery 管理口，会被爆破）|

---

## ⚠️ 装完必做的一步：开防火墙

在云平台控制台放行：

```
UDP  9987      ← 语音。【协议一定要选 UDP】，选成 TCP 会完全连不上
TCP  30033     ← 文件传输
```

⚠️ 轻量云主机常见坑：**「轻量应用服务器防火墙」和「CVM 安全组」是两个独立的地方**，
改错地方会表现为"规则明明加了却连不上"。

需要远程管理 ServerQuery 时，走 SSH 隧道（不要开公网）：

```bash
ssh -L 10011:127.0.0.1:10011 <用户>@<服务器>
```

---

## 🎵 怎么用

在**任意频道直接发消息**，不用 @机器人：

```
!点歌 稻香   ·  !play 稻香  ·  !dian 稻香  ·  !bo 稻香     ← 点歌（四种写法都行）
!play BV1G88y6xEQV  ·  !play https://b23.tv/xxxx          ← 视频号 / 链接
!play 周杰伦 稻香                                          ← 多个词自动合并搜索

!暂停/继续   !停止   !下一首   !上一首                      ← 中文
!zan !ting !xia !shang                                    ← 拼音
!当前  !队列  !音量 50  !跳转 90  !单曲  !循环  !随机  !顺序  !帮助
```

完整指令表 → [docs/COMMANDS.md](docs/COMMANDS.md)

### 扫码登录 B站（可选）

不登录也能点歌，登录后音源档位更好：

```bash
sudo -u <运行用户> python3 /opt/ts3bot/bili_login.py
```

二维码会**同时**给你两种：

```
（终端里直接画出二维码，手机对着屏幕扫）
📱 二维码图片：/var/tmp/bili_qr.png     ← 传到手机打开再扫，更稳
```

不需要装任何二维码库 —— 纯 Python 现画。

---

## 🔧 运维常用命令

```bash
sudo ts3-backup.sh                 # 立刻备份一次（不停服，76 KB）
sudo ts3-restore.sh <包>            # 还原（默认 dry-run，加 --yes 才动手）
sudo ts3-bot.sh status             # 机器人状态
sudo ts3-bot.sh stop / start       # 开关机器人
sudo bash /usr/local/bin/audit.sh 1 # 体检

journalctl -u teamspeak3 -n 50     # 看 TS3 日志
journalctl -u ts3audiobot -n 50    # 看机器人日志
```

每天 `00:00 / 12:00` 自动热备份 + 推送到异地（需在 `install.sh` 里给 `BACKUP_TARGET`）。

---

## 🆘 出问题了

先看 **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** —— 11 类常见故障的"症状 → 原因 → 处理"都在里面，全部来自真机踩坑。

最常见的三个：

| 症状 | 一句话解决 |
|---|---|
| 客户端一连上就被踢 | `hostmessage_mode` 被设成了 3，本包会自动校正为 1 |
| 新人连不上，老用户正常 | 身份安全等级被设成 8，本包默认写 5 |
| 完全连不上、UDP 没反应 | 云防火墙把 9987 建成了 TCP，改成 UDP |

---

## 📁 目录结构

```
ts3-bili-musicbot/
├── install.sh              一键部署（跑它就行）
├── vendor/                 软件本体（约 29 MB，已内置）
│   ├── teamspeak3-server/  TS3 服务端（已剔除数据库/密钥/日志）
│   ├── private-libs/       libssl1.1 兼容层
│   ├── yt-dlp              兜底音源解析
│   └── TS3AudioBot         ← 不在这里，首次安装时自动下载（97.5 MB，单独走 Release）
├── fetch-bot.sh            下载音乐机器人（install.sh 会调用）
├── build-vendor.sh         维护用：重新生成 vendor/ 与 Release 附件
├── config/                 配置模板（含 36 条点歌别名）
├── scripts/                代理 / 登录 / 备份 / 守护 / 体检 等 17 个脚本
├── systemd/                开机自启与守护服务
├── patch-kit/              进阶：自己改机器人源码重编译（普通用户用不到）
├── docs/                   指令手册 + 排错手册
├── LICENSE                 MIT（只覆盖自写代码）
└── THIRD_PARTY_NOTICES.md  第三方组件出处与许可证
```

---

## 🚀 想自己开源一份？

见 **[docs/RELEASE.md](docs/RELEASE.md)** —— 发布清单（改 `repo.conf` → 生成 vendor/ 与附件
→ 提交 → 建 Release 传附件 → 实测），含自动隐私检查项和常见发布事故。

**为什么机器人不直接放进 git？** 它是单个 **97.5 MiB** 的文件，GitHub 硬性拦截 100 MiB
以上的文件 —— 放进去能过但没余量，且每次重编译都会让仓库永久膨胀约 100 MB。

---

## 📄 许可与出处

本仓库自写的代码是 **MIT**。

随包分发的组件：TeamSpeak 3 服务端（**私有许可，使用即表示接受其条款**）、
TS3AudioBot（OSL-3.0）、yt-dlp（Unlicense）、libssl1.1（OpenSSL）、
pypinyin（MIT）、requests（Apache-2.0）、SQLite（Public Domain）。

**完整出处与许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)**，
每个脚本头部也标了自己用到哪些组件。

TeamSpeak 是 TeamSpeak Systems GmbH 的商标，本项目与其无任何关联。
