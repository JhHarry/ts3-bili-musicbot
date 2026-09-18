# 排错手册

按「症状 → 原因 → 处理」组织。前面几条都是**真机上踩过的**，不是理论问题。

---

## 1. 所有人都连不上服务器

### 1.1 客户端一进去就被踢出来（欢迎语闪一下就断）

**症状**：连上 → 弹出欢迎消息 → 立刻断开，反复重连都一样。
服务端日志里只有 `client disconnected ... reasonmsg=Leaving`（看起来像客户端自己退出）。

**原因**：`virtualserver_hostmessage_mode = 3`。
这个值的语义是「**弹出消息后强制断开连接**」（本意是"服务器即将关闭"的通知），
设成 3 等于把每个连进来的人都踢出去。

**处理**：
```bash
sudo TS3_PASS=$(sudo cat /opt/ts3bot/query.pw) \
     SV_NAME="$(...)" python3 /opt/ts3bot/ts3-serverset.py
# 或者直接：
#   serveredit virtualserver_hostmessage_mode=1
```
`install.sh` 部署时会自动校正成 `1`，并打印复核结果。

> 🔍 排查技巧：这一条极难查，因为日志看起来像客户端主动退出。
> 先开 `serveredit virtualserver_log_client=1`（否则日志里根本看不到连接记录），
> 再配合 `tcpdump -i any -n 'udp and not net 127.0.0.0/8'` 看双向流量。

### 1.2 新朋友连不上，但老用户正常

**原因**：`virtualserver_needed_identity_security_level = 8`。
这个值要求客户端身份等级 ≥ 8，新装的客户端默认等级是 5。

**处理**：设为 `5`（`install.sh` 默认就是 5）。

### 1.3 完全收不到 UDP 包（连超时）

**原因**：**云平台防火墙把 9987 建成了 TCP**。
常见于轻量云主机 ——「轻量应用服务器防火墙」与「CVM 安全组」是**两个独立的地方**，
改错地方会表现为"规则明明加了却没用"。

**判断**：TS3 在 `0.0.0.0:9987` 正常监听、本机 `ufw` 是 inactive、但外部一个 UDP 包都进不来
（TCP 30033 却能连）→ 就是上游把 UDP 丢了。

**处理**：控制台里加/改规则为 **协议 UDP / 端口 9987 / 来源 0.0.0.0/0**。

---

## 2. 机器人起不来

### 2.1 `Failed to load library libopus`

**原因**：只装了 `libopus0`。.NET 加载的是**不带版本号**的 `libopus.so`，
而这个软链只有 **`libopus-dev`** 提供。

**处理**：
```bash
sudo apt-get install -y libopus-dev libopus0 libsodium23
```

### 2.2 `Failed to determine credentials for user '__RUN_USER__'`

**原因**：打包时把所有 systemd 单元的 `User=` 换成了占位符，而 `install.sh` 只回填了一部分。

**处理**：`install.sh` 现在会**全量回填 + 残留检查**（有残留会直接报出来）。
手工修：
```bash
sudo grep -rl '__RUN_USER__' /etc/systemd/system/     # 看哪些没填
sudo sed -i 's|__RUN_USER__|ubuntu|g' /etc/systemd/system/ts3audiobot.service
sudo sed -i 's|__RUN_USER__|ts3server|g' /etc/systemd/system/teamspeak3.service
sudo systemctl daemon-reload
```

### 2.3 缺 `libssl.so.1.1`

.NET Core 3.1 依赖 OpenSSL 1.1，而新系统只有 OpenSSL 3。
本包在 `/opt/ts3bot/private-libs/` 里解了一份，**不污染系统**。

```bash
ls /opt/ts3bot/private-libs/usr/lib/x86_64-linux-gnu/libssl.so.1.1
# 没有就重新解压：
sudo tar xzf vendor/private-libs.tar.gz -C /opt/ts3bot
```

### 2.4 机器人要等 5 分钟才回来

**原因**：`ts3audiobot.toml` 里 `[bot.reconnect] onshutdown = ["5m"]`。

**处理**：改成
```toml
[bot.reconnect]
onshutdown = ["2s", "5s", "10s", "20s", "30s", "repeat last"]
```
本包的模板已经是修好的版本。**批量改 TS3 配置前先把机器人停掉**，否则会触发退避重连。

---

## 3. 点歌没声音 / 没反应

```bash
curl -s http://127.0.0.1:8087/health     # 代理健康检查
curl -s http://127.0.0.1:8087/status     # 解析缓存 / 下载状态
journalctl -u bili-proxy -n 30 --no-pager
```
代理**只监听 127.0.0.1**，外网访问不到是正常的。

### 3.1 `!play 歌名` 完全没反应

先确认机器人在频道里、且不是"暂停"状态。
再看 `journalctl -u ts3audiobot -n 50` —— 如果是 `Missing rights`，
说明该用户没有 `cmd.play` 权限（见 `config/rights.toml`）。

### 3.2 自定义别名点了没反应

99% 是这两个原因（见 [COMMANDS.md](COMMANDS.md#五自定义别名不用改配置文件)）：

* 别名值没以 `!` 开头；
* 忘了写 `(!param 0)`，参数被丢掉。

另外别名里面用到的内部命令（例如 `!param`）也要在 `rights.toml` 里给普通用户授权，
否则会报 `Missing rights for cmd.param`。

### 3.3 首次点播正常，15 分钟后再点同一首必炸

老版本的搜索缓存存的是 2 元组、读取端按 3 元组取下标。
本包已经修掉，回归测试见 `patch-kit/test_cache.py`。

---

## 4. 扫码登录相关

### 4.1 终端里的二维码扫不出来

1. 把二维码**调大**：终端字号调小 / 全屏；
2. 手机离屏幕 15~25 cm，**不要贴太近**；
3. 用 `--no-terminal` 只生成 PNG，把图片传到手机上打开再扫：
   ```bash
   python3 /opt/ts3bot/bili_login.py --no-terminal
   scp 用户@服务器:/var/tmp/bili_qr.png ./
   ```
4. 终端背景是**白色主题**时，字符画可能反相导致扫不出 —— 换成 PNG 方式。

> 二维码是**纯 Python** 现画的（`scripts/qrmini.py`，只用标准库 zlib），
> 所以不需要装 qrencode 之类的系统包，任何 Python 3.8+ 都能跑。

### 4.2 提示"二维码已过期"

B站的二维码只有几分钟有效期。重跑一次即可。

### 4.3 登录成功了但还是低音源

```bash
python3 /opt/ts3bot/bili_login.py --check
# ✅ cookie 有效 —— 已登录为：xxx
```
如果显示有效但音源仍低，那多半是**这条视频本身**只有低码率，
或者需要大会员（脚本不绕付费内容）。

---

## 5. 备份 / 还原

### 5.1 备份脚本跑一半就退出

**原因**：`ts3server.sqlitedb` 不存在（例如这台机器只是"冷备仓库"，本来就没跑 TS3），
`set -euo pipefail` 下第一条 sqlite 命令失败就整个退出。

**处理**：新版脚本开头加了兜底，检测不到数据库就打印说明并**正常退出 0**。

### 5.2 还原之后服务起不来

**原因**：备份包里带着源机的 systemd 单元，`User=` 是源机用户名（如 源机的用户名），
目标机上没有这个用户。

**处理**：新版 `ts3-restore.sh` 会**自动重映射** `User=` / `Group=`
（teamspeak3 → `ts3server`，其余 → 本机运行用户），drop-in 也一并处理。

### 5.3 为什么不能直接 `cp` 数据库

`ts3server.sqlitedb` 是 **WAL 模式**（同目录有 `-wal` / `-shm`），
直接复制主库会**丢掉 WAL 里还没回写的改动**，还原后可能少频道、少权限。

正确做法：`sqlite3 <db> ".backup <目标>"` —— 在线、安全、**不需要停服**，实测 184ms。

---

## 6. 磁盘 / 内存

### 6.1 机器人内存一直涨

TS3AudioBot 上游遗留泄漏：**播放时 ≈4.0 MB/分，空闲 ≈1.3 MB/分**。
`ts3bot-watchdog.timer` 每分钟巡检，超过 450MB 自动重启，重启后**自动续播**上一首
（约 5 秒接上），所以体感只是"顿一下"。

### 6.2 `/tmp` 被撑爆

很多机器 `/tmp` 是几百 MB 的 tmpfs。
本包所有构建/临时文件**一律用 `/var/tmp`**（重编译 SDK 解压就要 118MB）。

---

## 7. 抓日志的正确姿势

```bash
journalctl -u teamspeak3 -n 100 --no-pager
journalctl -u ts3audiobot -n 100 --no-pager
journalctl -u bili-proxy -n 100 --no-pager
tail -f /var/log/ts3bot-watchdog.log
tail -f /var/log/ts3bot-autoresume.log
tail -f /var/log/ts3-backup-push.log
```
`NLog.config` 默认已经调到 `Info` —— 上游默认的 `Debug` 里 **92% 是 RTT 心跳噪声**，
真出问题时反而什么都看不见。要深挖再临时改回 `Debug` 并重启机器人。

体检脚本：
```bash
sudo bash /usr/local/bin/audit.sh 1   # 系统 / CPU / 内存 / 磁盘
sudo bash /usr/local/bin/audit.sh 2   # 网络 / 服务
sudo bash /usr/local/bin/audit.sh 3   # 安全 / 更新 / 崩溃统计
```
