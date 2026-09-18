# 第三方组件许可与来源

本仓库包含自己写的脚本、配置模板和文档，以及放在 `vendor/` 目录里的
运行所需程序 —— 后者各自的许可证如下。

**使用即表示你接受下表各组件的许可条款**，尤其是 TeamSpeak 3 服务端。

| 组件 | 版本 | 许可证 | 来源 |
|---|---|---|---|
| **TeamSpeak 3 Server** | 3.13.7 | TeamSpeak 官方许可（私有） | https://teamspeak.com |
| **TS3AudioBot** | 0.12.0（自编译衍生版） | OSL-3.0 | https://github.com/Splamy/TS3AudioBot |
| **yt-dlp** | latest | Unlicense | https://github.com/yt-dlp/yt-dlp |
| **libssl1.1 / libcrypto1.1** | 1.1.1w | OpenSSL License（双重许可） | Debian/Ubuntu 归档 |
| **B站音频代理 / 登录器（本仓库）** | — | MIT | 本仓库 |

## ⚠️ 关于 TeamSpeak 3 服务端

TS3 服务端**不是自由软件**。它随包分发只是因为官方允许免费、非商业地运行
（最多 32 个 slot）。**下载、安装、运行即表示你接受 TeamSpeak 官方的许可条款**：

> This software is provided "as is" and any express or implied warranties,
> including, but not limited to, the implied warranties of merchantability and
> fitness for a particular purpose are disclaimed.

如果用于商业用途，请自行到 https://www.teamspeak.com 购买授权。
**TeamSpeak** 是 TeamSpeak Systems GmbH 的商标，本项目与其无任何关联。

## 关于 TS3AudioBot

上游项目已经在 **2021-04-02 停止维护**，且其音频管道存在会把整个进程打死的
空引用崩溃。本仓库附带的是**自行编译并打了 4+1 处补丁**的衍生版本，
补丁源码与一键重编译脚本都在 `patch-kit/`，完全符合 OSL-3.0 对衍生作品的要求
（标注来源 + 提供修改后的源码）。

## 关于 B站

`bili_proxy.py` 只是**本地解析公开播放地址并转码转发**，不含任何破解、
不绕过付费内容、不存储视频文件。扫码登录用的是 B站官方 Web 登录接口，
cookie 只保存在你自己的服务器上。

请遵守 B站用户协议，不要用于批量抓取或再分发内容。
