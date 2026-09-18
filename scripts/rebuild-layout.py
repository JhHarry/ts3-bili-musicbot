#!/usr/bin/env python3
# ──────────────────────────────────────────────────────────────────────────
# 通过 TeamSpeak 官方 ServerQuery(文本) 协议通信：
#   TeamSpeak 3 Server 私有许可     https://www.teamspeak.com   （随包分发，使用即接受其条款）
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

"""重建频道布局（迁移/初始化时用）：游戏频道 + 私密房间 + 加密 + 编解码器。

在新服务器上一次性建好完整频道结构，避免迁移后只剩一个默认频道。
用法: TS3_PASS='查询密码' [PRIVATE_PW='房间密码'] python3 rebuild-layout.py
      PRIVATE_PW 留空则私密房间不设密码。
"""
import os
import socket
import time

HOST = os.environ.get("TS3_HOST", "127.0.0.1")
PORT = int(os.environ.get("TS3_QUERY_PORT", "10011"))
USER = os.environ.get("TS3_USER", "serveradmin")
PASS = os.environ.get("TS3_PASS", "")

GAMES = ["League of Legends", "Counter-Strike 2", "VALORANT", "PUBG",
         "Naraka: Bladepoint", "Delta Force", "Minecraft"]
PRIVATE = "Private Room"
# 空字符串 = 房间不加密码（不要在此硬编码任何密码）
PRIVATE_PW = os.environ.get("PRIVATE_PW", "")


def esc(s):
    s = s.replace("\\", "\\\\").replace("\n", "\\n")
    return s.replace(" ", "\\s").replace("/", "\\/").replace("|", "\\p")


def desc():
    return ("🎵 点歌（直接发，中文拼音都好使）\n"
            "  !play 稻香  ·  !dian 稻香  ·  !bo 稻香\n"
            "  !play BV1G88y6xEQV  ·  !play https://b23.tv/xx\n"
            "▶ !zan 暂停 !ting 停止 !xia 下一首 !shang 上一首\n"
            "  !now 当前曲目 !lb 队列 !yin 50 音量 !tiao 90 跳转\n"
            "  !danqu 单曲循环 !quanbu 列表循环 !sui 随机 !shun 顺序\n"
            "  !bz 查看全部命令")


def main():
    s = socket.socket()
    s.settimeout(15)
    s.connect((HOST, PORT))
    s.recv(4096)

    def cmd(c, w=0.45):
        s.send((c + "\n").encode("utf-8"))
        time.sleep(w)
        return s.recv(131072).decode("utf-8", "ignore").strip()

    cmd("login %s %s" % (USER, PASS))
    cmd("use 1")

    # 1) 找到默认频道，改名为 Lobby
    cid0 = None
    for part in cmd("channellist").split("|"):
        if "cid=" in part:
            f = dict(kv.split("=", 1) for kv in part.split() if "=" in kv)
            cid0 = int(f["cid"])
            break
    if not cid0:
        raise SystemExit("找不到默认频道")
    box = "🎵 " + desc()
    print("默认频道 cid=%d 改名为 Lobby" % cid0)
    cmd("channeledit cid=%d channel_name=Lobby" % cid0)
    cmd("channeledit cid=%d channel_codec=5 channel_codec_quality=5" % cid0)
    cmd("channeledit cid=%d channel_codec_is_unencrypted=0" % cid0)

    # 2) 逐个建游戏频道（继承服务器默认编解码器）
    for g in GAMES:
        r = cmd("channelcreate channel_name=%s channel_flag_permanent=1" % esc(g))
        print("  建频道 %s -> %s" % (g, r[:40]))

    # 3) 私密房间（可选密码 + 加密）
    if PRIVATE_PW:
        r = cmd("channelcreate channel_name=%s channel_flag_permanent=1 "
                "channel_password=%s" % (esc(PRIVATE), esc(PRIVATE_PW)))
    else:
        r = cmd("channelcreate channel_name=%s channel_flag_permanent=1" % esc(PRIVATE))
    print("  建私密房间 -> %s" % r[:40])

    # 4) 统一：加密 + 备注 + 主题
    for part in cmd("channellist").split("|"):
        if "cid=" not in part:
            continue
        f = dict(kv.split("=", 1) for kv in part.split() if "=" in kv)
        cid = int(f["cid"])
        cmd("channeledit cid=%d channel_codec_is_unencrypted=0" % cid)
        cmd("channeledit cid=%d channel_description=%s" % (cid, esc(box)))
        cmd("channeledit cid=%d channel_topic=%s" % (
            cid, esc("点歌：!play 歌名 / BV号 / B站链接")))

    print("\n=== 最终频道 ===")
    for part in cmd("channellist").split("|"):
        if "cid=" in part:
            f = dict(kv.split("=", 1) for kv in part.split() if "=" in kv)
            print("  %s" % f.get("channel_name", "").replace("\\s", " "))
    cmd("quit")
    s.close()


if __name__ == "__main__":
    main()
