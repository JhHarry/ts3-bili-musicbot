# 发布清单（开源到 GitHub 时照着做一遍）

## 体积策略（先说清楚为什么）

| 内容 | 放哪 | 大小 |
|---|---|---|
| 代码、配置、脚本、文档 | **git 仓库** | 约 300 KB |
| TS3 服务端 / yt-dlp / libssl1.1 兼容层 | **git 仓库** `vendor/` | 约 29 MB |
| **音乐机器人 TS3AudioBot** | **Release 附件** | 压缩后约 35~40 MB（裸文件 97.5 MiB）|

机器人不放进 git 的原因：它是单个 **97.5 MiB** 的文件，GitHub 硬性拦截 100 MiB 以上的文件
（能过但没余量），而且**每次重编译都会让仓库永久膨胀约 100 MB**。
放成 Release 附件后：仓库克隆只要 29 MB，机器人随时可以重传，两不相干。

---

## 第 1 步：改一处配置

```bash
vim repo.conf
```

```ini
GITHUB_REPO="你的用户名/ts3-bili-musicbot"     # ← 只改这一行
```

`install.sh` / `fetch-bot.sh` / `build-vendor.sh` 都从这一个文件读，不用到处改。

> 没改的话 `fetch-bot.sh` 会返回 404，用户那边会看到明确的「下载失败」提示。

---

## 第 2 步：在一台已装好的机器上生成产物

```bash
git clone <你的仓库> /tmp/pack && cd /tmp/pack
sudo bash build-vendor.sh
```

一次产出两样东西：

```
vendor/                      约 29 MB  → 提交进 git
ts3audiobot-patched.tar.xz   约 35~40 MB  → 传成 Release 附件
```

脚本包含这些**强制的**检查，任何一项不过都不出产物：

```
✓ 隐私扫描（公网 IP / 域名 / 私钥 / cookie / 家目录路径 + 你的自定义词表）
✓ 凭证文件硬性排除（cookie、query.pw、数据库、SSH 密钥、relay.env…）
✓ TS3 服务端剔除数据库 / 身份密钥 / 日志 / 上传文件 / query 白名单
```

> 冷备机器上先解归档再指定来源：
> ```bash
> sudo mkdir -p /var/tmp/coldx
> sudo tar -xf xx/ts3bot.tar.zst    --zstd -C /var/tmp/coldx opt/ts3bot
> sudo tar -xf xx/ts3server.tar.zst --zstd -C /var/tmp/coldx opt/teamspeak3-server
> sudo OPT_ROOT=/var/tmp/coldx bash build-vendor.sh
> ```

---

## 第 3 步：提交代码

```bash
git add -A
git commit -m "v13: 懒人一键包"
git push
```

---

## 第 4 步：建 Release，把机器人作为附件上传

```bash
gh release create v13 ts3audiobot-patched.tar.xz \
   --title "v13" --notes-file CHANGELOG.md
```

或者网页操作：**Releases → Draft a new release → Tag 填 `v13` →
把 `ts3audiobot-patched.tar.xz` 拖进附件区 → Publish。**

⚠️ **附件名必须是 `ts3audiobot-patched.tar.xz`**（`fetch-bot.sh` 按这个名字找；
要改就同时改 `repo.conf` 里的 `BOT_ASSET`）。

---

## 第 5 步：验证「克隆即可用」

找一台**干净的** x86_64 机器实测：

```bash
apt-get install -y git
git clone <你的仓库> /tmp/t && cd /tmp/t
du -sh .                       # 应该是 29 MB 左右，不是 130 MB
sudo bash install.sh
```

要确认：

- [ ] 打印 `缺少音乐机器人，自动下载（约 35~40 MB，只需一次）`
- [ ] 下载完成后打印 `软件本体: 3x M 已就位`
- [ ] 结尾打印出 ServerQuery 密码与管理员令牌
- [ ] `systemctl is-active teamspeak3 ts3audiobot bili-proxy` 都是 `active`
- [ ] 客户端能连上，发 `!点歌 稻香` 有声音

**再验一次离线路径**：把 `ts3audiobot-patched.tar.xz` 解压成 `vendor/TS3AudioBot`
后重跑 `install.sh`，应该**不再联网**、直接跳过下载。

---

## 附：CI 会检查什么

`.github/workflows/checks.yml`：

| 检查 | 说明 |
|---|---|
| Shell 语法 | 所有 `*.sh` 过 `bash -n` |
| Python 语法 | 所有 `*.py` 过 `py_compile` |
| 二维码回归 | 生成 QR → `zbarimg` 解码 → 与原文比对（4 个纠错等级 × 7 组用例）|
| 敏感文件扫描 | 确认 git 里没有 cookie / pw / 数据库 / 密钥 / 打包产物 |

---

## 常见发布事故

| 事故 | 原因 |
|---|---|
| 用户那边报「下载失败」 | `repo.conf` 里的 `GITHUB_REPO` 没改，或者没建 Release / 附件名不对 |
| 仓库有 130 MB，克隆很慢 | 机器人二进制被 `git add` 进去了（应该是 gitignore 状态）|
| `git push` 被拒：file is too large | 同上，`vendor/TS3AudioBot` 超过 100 MiB |
| 包里带出了服务器 IP | 生成 vendor 时没跑 `privacy-scan.sh`，或跳过了检查 |
| 仓库里有数据库 / 身份密钥 | 手工 `cp -a /opt/teamspeak3-server`，没走 `build-vendor.sh` |
| 别人的机器装完机器人起不来 | 大概率是 `libopus-dev` 没装（只有 `-dev` 包提供不带版本号的 `libopus.so`）|
