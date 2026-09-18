# TeamSpeak 3 + B站音乐机器人 部署包

[![Release](https://img.shields.io/github/v/release/JhHarry/ts3-bili-musicbot?display_name=tag&sort=semver&color=2ea44f)](https://github.com/JhHarry/ts3-bili-musicbot/releases/latest)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Ubuntu%20%7C%20Debian%20%C2%B7%20x86__64-important)](#一环境要求)
[![Shell](https://img.shields.io/badge/shell-bash-4EAA25?logo=gnubash&logoColor=white)](#)
[![Python](https://img.shields.io/badge/python-3.8%2B-3776AB?logo=python&logoColor=white)](#)

在全新的 Ubuntu / Debian x86_64 服务器上一键部署 TeamSpeak 3 语音服务器与 B站点歌机器人。
安装完成后，在频道内发送 `!play 歌名` 即可播放。

---

## 一、环境要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Ubuntu 20.04 / 22.04 / 24.04 / 26.04 LTS，Debian 11 / 12 / 13 |
| 架构 | **x86_64（amd64）**；不支持 ARM |
| 权限 | root 或可免密 sudo |
| 磁盘 | 可用空间 ≥ 2 GB |
| 内存 | ≥ 1 GB（不足 900 MB 时脚本会自动创建 2 GB swap） |
| 网络 | 可访问 apt 源（首次需下载约 150 MB 依赖）；需可访问 GitHub（下载机器人约 26 MB，仅一次） |

安装脚本会自动安装所需系统依赖，无需预先准备。

---

## 二、安装

```bash
git clone https://github.com/JhHarry/ts3-bili-musicbot.git
cd ts3-bili-musicbot
sudo bash install.sh
```

安装脚本全程自动执行，**全新机器约需 15 分钟**（其中约 10 分钟用于下载系统依赖，
`ffmpeg` 及其依赖约 150 MB）。下载期间无明显输出属正常现象，请耐心等待。

过程中会询问是否安装 B站点歌机器人：

```
是否安装 B站点歌机器人？[Y/n]
```

* 直接回车或输入 `y`：安装 TeamSpeak 3 服务端 + 音乐机器人
* 输入 `n`：仅安装 TeamSpeak 3 服务端（内存占用约 30 MB）

非交互环境（脚本调用、管道）默认安装完整组件。

### 2.1 部署信息文档

安装完成后，脚本会自动生成一份 **`TS3-服务器信息.txt`**，同时保存在两个位置：

| 路径 | 说明 |
|---|---|
| `./TS3-服务器信息.txt` | 执行 `install.sh` 的目录（即仓库根目录）|
| `/root/TS3-服务器信息.txt` | root 家目录，作为保底位置 |

文档包含以下内容：

| 章节 | 内容 |
|---|---|
| 一、连接地址 | 公网地址、语音端口、服务器名称与密码（发给朋友用）|
| **二、管理员令牌** | 用于把自己的身份设为管理员，**最重要** |
| 三、点歌指令 | 全部可用指令与别名 |
| 四、管理凭据 | ServerQuery 密码与端口 |
| 五、常用运维命令 | 备份、还原、查看日志 |
| 六、防火墙提醒 | 需要放行的端口 |

**取回本地：**

```bash
scp <用户>@<服务器>:~/ts3-bili-musicbot/TS3-服务器信息.txt ./
```

**如何使用管理员令牌：**

1. 使用文档中的「连接地址」连入服务器（TS3 客户端）
2. 打开客户端菜单 → **权限** → **使用激活密钥**（Use Privilege Key）
3. 粘贴文档第二节中的令牌字符串，确认
4. 当前身份即获得服务器管理员权限

> ⚠️ 文档中包含管理凭据，请勿随意外发。取回本地后建议删除服务器上的副本：
>
> ```bash
> sudo rm -f /root/TS3-服务器信息.txt ./TS3-服务器信息.txt
> ```
>
> 后续要查阅指令，直接看 [docs/COMMANDS.md](docs/COMMANDS.md) 即可。

### 2.2 可配置项

通过环境变量覆盖默认值，可跳过交互询问：

```bash
sudo WITH_BOT=0 bash install.sh                 # 仅安装 TeamSpeak 3
sudo SERVER_NAME="我的服务器" bash install.sh    # 自定义服务器名
```

| 变量 | 默认值 | 说明 |
|---|---|---|
| `WITH_BOT` | 交互询问（非交互时为 1） | `0` 仅安装 TS3；`1` 安装完整组件 |
| `SERVER_NAME` | `My TeamSpeak Server` | 服务器名称 |
| `SERVER_PW` | 空 | 服务器密码；留空表示无需密码 |
| `SECLEVEL` | `5` | 身份安全等级；不建议设为 8 |
| `BOT_NAME` | `MusicBot🎵Bot` | 机器人昵称（仅在安装机器人时生效） |
| `PRIVATE_PW` | 空 | 私密频道密码；留空则不加密 |
| `BILI_LOGIN` | `0` | 设为 `1` 时，安装结束自动进入 B站扫码登录 |
| `BACKUP_TARGET` | 空 | 异地备份仓库地址，形如 `用户@主机:/var/backups/ts3-from-sh/` |

### 2.3 离线安装

无法访问 GitHub 时，从 Release 下载附件 `ts3audiobot-patched.tar.xz`，
解压至 `vendor/TS3AudioBot` 后再执行 `install.sh`，安装过程不再联网。

---

## 三、防火墙配置

必须放行以下端口：

| 端口 | 协议 | 用途 |
|---|---|---|
| `9987` | **UDP** | 语音。协议必须选择 UDP，选择 TCP 将无法连接 |
| `30033` | TCP | 文件传输（头像、频道文件） |

ServerQuery 管理端口 `10011` **不应对外开放**。需要远程管理时使用 SSH 隧道：

```bash
ssh -L 10011:127.0.0.1:10011 <用户>@<服务器>
```

> 部分云平台（如轻量应用服务器）的「防火墙」与「安全组」是两处独立配置，
> 需在正确的页面添加规则。

---

## 四、使用

在任意频道内直接发送消息，无需 @机器人。

> 首次使用请先按 [2.1 部署信息文档](#21-部署信息文档) 的说明，
> 用管理员令牌把自己的身份设为管理员，否则部分管理操作无权限。

### 4.1 点歌

| 指令 | 说明 |
|---|---|
| `!play 稻香` | 按歌名搜索 |
| `!dian 稻香` / `!bo 稻香` | 拼音简写 |
| `!点歌 稻香` | 中文别名 |
| `!play 周杰伦 稻香` | 多个词自动合并为搜索词 |
| `!play BV1G88y6xEQV` | 按 B站视频号播放 |
| `!play https://b23.tv/xxxxx` | 粘贴链接播放 |

### 4.2 播放控制

| 指令 | 拼音简写 | 作用 |
|---|---|---|
| `!pause` | `!zan` | 暂停 / 继续 |
| `!stop` | `!ting` | 停止并清空队列 |
| `!next` | `!xia` | 下一首 |
| `!previous` | `!shang` | 上一首 |
| `!song` | `!now` | 显示当前曲目 |
| `!list show` | `!lb` | 显示队列 |
| `!volume 50` | `!yin 50` | 音量 |
| `!seek 90` | `!tiao 90` | 跳转至第 90 秒 |

### 4.3 播放模式

| 指令 | 拼音简写 | 作用 |
|---|---|---|
| `!repeat one` | `!danqu` | 单曲循环 |
| `!repeat all` | `!quanbu` | 列表循环 |
| `!random on` | `!sui` | 随机播放 |
| `!random off` | `!shun` | 顺序播放 |

`!help`（简写 `!bz`）可列出全部命令。完整说明见 [docs/COMMANDS.md](docs/COMMANDS.md)。

### 4.4 扫码登录 B站（可选）

未登录也可正常点歌，登录后可获得更高音源档位。

```bash
sudo -u <运行用户> python3 /opt/ts3bot/bili_login.py
```

程序会在终端直接绘制二维码，同时生成图片 `/var/tmp/bili_qr.png`，
扫码并在手机端确认后即完成登录。二维码由纯 Python 生成，无额外依赖。

校验登录状态：

```bash
python3 /opt/ts3bot/bili_login.py --check
```

---

## 五、运维

```bash
sudo ts3-backup.sh                    # 立即备份（在线进行，无需停服）
sudo ts3-restore.sh <备份包>           # 还原（默认 dry-run，加 --yes 执行）
sudo ts3-bot.sh status                # 机器人状态
sudo ts3-bot.sh stop / start          # 启停机器人
sudo bash /usr/local/bin/audit.sh 1   # 系统体检

journalctl -u teamspeak3 -n 50        # TS3 日志
journalctl -u ts3audiobot -n 50       # 机器人日志
```

系统已配置以下定时任务：

| 任务 | 时间 | 说明 |
|---|---|---|
| 热备份 | 每天 00:00 / 12:00 | 备份至 `/var/backups/ts3/`，保留最近 10 GB |
| 机器人守护 | 每分钟 | 异常自动重启；内存超限时重启并自动续播 |
| 开机自检 | 开机后 30 秒 | 检查各服务状态，未启动的自动拉起 |

---

## 六、常见问题

**Q1. 客户端连接后被立即断开**

服务端属性 `virtualserver_hostmessage_mode` 被设为 `3`，该值的语义是
「弹出消息后强制断开连接」，会导致所有客户端无法停留。

安装脚本会自动校正为 `1`。若已安装完成仍出现此问题，手动校正：

```bash
sudo TS3_PASS=$(sudo cat /opt/ts3bot/query.pw) python3 /opt/ts3bot/ts3-serverset.py
```

**Q2. 新用户无法连接，老用户正常**

身份安全等级 `needed_identity_security_level` 被设为 8，而新客户端默认等级为 5。
安装脚本默认写入 5。手动校正方式同上。

**Q3. 客户端提示连接超时，服务器端抓不到任何 UDP 数据包**

云平台防火墙将 `9987` 配置成了 TCP。请修改为 **UDP**。

**Q4. 机器人启动失败，提示 `Failed to load library libopus`**

缺少 `libopus-dev`。该软件包提供不带版本号的 `libopus.so` 软链接，仅安装
`libopus0` 无法满足 .NET 的加载需求。

```bash
sudo apt-get install -y libopus-dev libopus0 libsodium23
```

**Q5. 机器人启动失败，提示缺少 `libssl.so.1.1`**

```bash
sudo cp -a /path/to/repo/vendor/private-libs /opt/ts3bot/private-libs
sudo systemctl restart ts3audiobot
```

安装脚本在缺少该文件时会直接终止并报错，不会留下不可用的部署。

**Q6. 点歌没有声音**

依次检查：

```bash
curl -s http://127.0.0.1:8087/health          # 代理健康检查
curl -s http://127.0.0.1:8087/status          # 解析与缓存状态
journalctl -u bili-proxy -n 30 --no-pager
```

代理仅监听 `127.0.0.1`，外网无法访问属于正常现象。

**Q7. 自定义别名无效**

需注意两点：

1. 别名值必须以 `!` 开头，否则会被解析为普通字符串而非命令；
2. 转发参数必须使用 `(!param 0)`，直接写 `"!play"` 会丢弃用户输入。

```
dian = "!play (!param 0)"    # 正确
dian = "!play"               # 错误，参数被丢弃
```

此外，别名内部调用的命令（如 `!param`）也需在 `config/rights.toml` 中授权。
详见 [docs/COMMANDS.md](docs/COMMANDS.md)。

**Q8. 机器人内存持续增长**

TS3AudioBot 上游遗留的内存泄漏（播放时约 4 MB/分钟，空闲约 1.3 MB/分钟）。
守护进程会在内存超过 450 MB 时自动重启，并在约 5 秒后自动续播，无需人工干预。

**Q9. 搜索结果不是原曲**

代理内置选源逻辑会优先选择原版、高码率音源，并排除翻唱、现场、伴奏与
MV 音轨。若结果仍不符合预期，建议直接提供 BV 号或链接。

**Q10. 安装停在「1/9 安装系统依赖」很久不动**

属正常现象。全新机器没有 apt 缓存，需要下载 `ffmpeg` 及其依赖约 150 MB。
可另开一个终端确认进度：

```bash
ps -eo pid,etime,cmd | grep apt-get        # 看 apt 是否在跑
ls -l /var/cache/apt/archives/partial/     # 看正在下载的包
```

**Q11. 安装失败，提示缺少某条命令**

安装脚本在安装依赖后会执行前置命令自检，缺少的命令会明确列出。按提示补齐即可：

```bash
sudo apt-get update && sudo apt-get install -y <包名>
```

**Q12. 安装完成，但提示「未取到 ServerQuery 密码，跳过服务器属性校正」**

表示 TeamSpeak 启动异常缓慢，凭据自动抓取未成功。可与下方命令手动校正：

```bash
sudo TS3_PASS=$(sudo cat /opt/ts3bot/query.pw) python3 /opt/ts3bot/ts3-serverset.py
```

若 `/opt/ts3bot/query.pw` 不存在，密码可从 `sudo journalctl -u teamspeak3 | grep 'password='` 获取。

更多故障处理见 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)。

---

## 七、目录结构

```
ts3-bili-musicbot/
├── install.sh              一键部署脚本
├── fetch-bot.sh            下载机器人二进制（由 install.sh 调用）
├── build-vendor.sh         维护用：重新生成 vendor/ 与 Release 附件
├── config/                 配置模板
├── scripts/                代理、登录、备份、守护、体检等脚本
├── systemd/                服务单元
├── vendor/                 TS3 服务端、yt-dlp、libssl1.1 兼容层
├── patch-kit/              自编译工具与补丁（进阶）
└── docs/                   指令手册、排错手册、发布清单
```

---

## 八、许可与第三方组件

本仓库自行编写的代码采用 MIT 许可，详见 [LICENSE](LICENSE)。

随包分发的第三方组件各自适用其原始许可，完整清单见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。其中：

* **TeamSpeak 3 服务端**为私有许可软件，使用即表示接受其许可条款；
* TS3AudioBot 采用 OSL-3.0，本包附带的是自行编译并打补丁的衍生版本，
  补丁源码见 `patch-kit/`；
* yt-dlp（Unlicense）、libssl1.1（OpenSSL License）、pypinyin（MIT）、
  requests（Apache-2.0）。

TeamSpeak 是 TeamSpeak Systems GmbH 的商标，本项目与其无任何关联。
