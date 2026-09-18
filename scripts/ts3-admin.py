#!/usr/bin/env python3
# ──────────────────────────────────────────────────────────────────────────
# 通过 TeamSpeak 官方 ServerQuery(文本) 协议通信：
#   TeamSpeak 3 Server 私有许可     https://www.teamspeak.com   （随包分发，使用即接受其条款）
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

"""TS3 频道/服务器管理通用工具。

用法（需要 TS3_PASS 环境变量）：
  python3 ts3-admin.py list                    列出所有频道
  python3 ts3-admin.py create "DOTA2" "Apex英雄"  创建永久频道（可多个）
  python3 ts3-admin.py delete "王者荣耀" "和平精英" 删除频道（可多个）
  python3 ts3-admin.py rename "旧名" "新名"        重命名
  python3 ts3-admin.py server "新服务器名"        改服务器名
  python3 ts3-admin.py raw "serverinfo"          执行任意 ServerQuery 命令
"""
import os, socket, sys, time

HOST = os.environ.get("TS3_HOST", "127.0.0.1")
PORT = int(os.environ.get("TS3_QUERY_PORT", "10011"))
USER = os.environ.get("TS3_USER", "serveradmin")
PASS = os.environ.get("TS3_PASS", "")


def esc(s):
    return (s.replace("\\", "\\\\").replace(" ", "\\s")
             .replace("/", "\\/").replace("|", "\\p"))


def unesc(s):
    return (s.replace("\\s", " ").replace("\\/", "/")
             .replace("\\p", "|").replace("\\\\", "\\"))


class TS3:
    def __init__(self):
        self.s = socket.socket()
        self.s.settimeout(15)
        self.s.connect((HOST, PORT))
        self.s.recv(4096)
        self.cmd("login %s %s" % (USER, PASS))
        self.cmd("use 1")

    def cmd(self, c, wait=0.4):
        self.s.send((c + "\n").encode("utf-8"))
        time.sleep(wait)
        try:
            return self.s.recv(131072).decode("utf-8", "ignore").strip()
        except socket.timeout:
            return "(timeout)"

    def channels(self):
        """返回 [(cid, order, name), ...]"""
        raw = self.cmd("channellist")
        out = []
        for part in raw.split("|"):
            if "cid=" not in part:
                continue
            f = {}
            for kv in part.split():
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    f[k] = v
            out.append((int(f["cid"]), int(f.get("channel_order", 0)),
                        unesc(f.get("channel_name", ""))))
        return out

    def close(self):
        try:
            self.cmd("quit")
        finally:
            self.s.close()


def main():
    if not PASS:
        sys.exit("需要 TS3_PASS 环境变量")
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    op = sys.argv[1]
    args = sys.argv[2:]
    t = TS3()

    if op == "list":
        print("%-4s %-6s %s" % ("cid", "order", "频道名"))
        for cid, order, name in sorted(t.channels(), key=lambda x: (x[1], x[0])):
            print("%-4d %-6d %s" % (cid, order, name))

    elif op == "create":
        for name in args:
            r = t.cmd("channelcreate channel_name=%s channel_flag_permanent=1"
                      % esc(name))
            print("[建] %s -> %s" % (name, r))

    elif op == "delete":
        chans = {c[2]: c[0] for c in t.channels()}
        for name in args:
            if name not in chans:
                print("[删] %s -> 不存在，跳过" % name)
                continue
            r = t.cmd("channeldelete cid=%d force=1" % chans[name], wait=0.7)
            print("[删] %s (cid=%d) -> %s" % (name, chans[name], r))

    elif op == "rename":
        old, new = args[0], args[1]
        chans = {c[2]: c[0] for c in t.channels()}
        if old not in chans:
            print("找不到频道: %s" % old)
        else:
            print("[改名] %s -> %s : %s"
                  % (old, new, t.cmd("channeledit cid=%d channel_name=%s"
                                     % (chans[old], esc(new)))))

    elif op == "server":
        print("[服务器名] %s" % t.cmd("serveredit virtualserver_name=%s"
                                      % esc(args[0])))

    elif op == "raw":
        for c in args:
            print("=== %s ===" % c)
            print(t.cmd(c))

    else:
        sys.exit("未知操作: %s" % op)

    t.close()


if __name__ == "__main__":
    main()
