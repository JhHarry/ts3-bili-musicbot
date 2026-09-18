#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ──────────────────────────────────────────────────────────────────────────
# 通过 TeamSpeak 官方 ServerQuery(文本) 协议通信：
#   TeamSpeak 3 Server 私有许可     https://www.teamspeak.com   （随包分发，使用即接受其条款）
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

"""setdesc.py —— 给服务器里每个频道写上「点歌说明」和频道主题。

用法: TS3_PASS='<ServerQuery密码>' python3 setdesc.py
"""
import os
import socket
import time

HOST = os.environ.get("TS3_HOST", "127.0.0.1")
PORT = int(os.environ.get("TS3_QUERY_PORT", "10011"))
USER = os.environ.get("TS3_USER", "serveradmin")
PASS = os.environ.get("TS3_PASS", "")

DESC = (
    "🎵 点歌（直接发，中文拼音都好使）\n"
    "  !play 稻香              完整写法\n"
    "  !dian 稻香  /  !bo 稻香  拼音简写（少打字）\n"
    "  !play BV1G88y6xEQV      B站视频号\n"
    "  !play https://b23.tv/xx 直接粘链接\n"
    "\n"
    "▶ 播放控制\n"
    "  !zan 暂停/继续   !ting 停止   !xia 下一首   !shang 上一首\n"
    "  !yin 50 音量     !tiao 90 跳到 90 秒\n"
    "  !now 当前曲目    !lb 看队列\n"
    "  !danqu 单曲循环  !quanbu 列表循环  !sui 随机  !shun 顺序\n"
    "\n"
    "  !bz 查看全部命令"
)
TOPIC = "点歌：!play 歌名（或 !dian 稻香 · !bo 稻香）"


def esc(s):
    return (s.replace("\\", "\\\\").replace(" ", "\\s")
             .replace("/", "\\/").replace("|", "\\p").replace("\n", "\\n"))


def main():
    s = socket.socket()
    s.settimeout(15)
    s.connect((HOST, PORT))
    s.recv(4096)

    def cmd(c, w=0.4):
        s.send((c + "\n").encode("utf-8"))
        time.sleep(w)
        return s.recv(131072).decode("utf-8", "ignore").strip()

    cmd("login %s %s" % (USER, PASS))
    cmd("use 1")
    n = 0
    for part in cmd("channellist").split("|"):
        if "cid=" not in part:
            continue
        f = dict(kv.split("=", 1) for kv in part.split() if "=" in kv)
        if "cid" not in f:
            continue
        cmd("channeledit cid=%s channel_description=%s" % (f["cid"], esc(DESC)))
        cmd("channeledit cid=%s channel_topic=%s" % (f["cid"], esc(TOPIC)))
        n += 1
    print("    已写入 %d 个频道的点歌说明" % n)
    try:
        cmd("quit")
    except Exception:
        pass
    s.close()


main()
