#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ──────────────────────────────────────────────────────────────────────────
# 通过 TeamSpeak 官方 ServerQuery(文本) 协议通信：
#   TeamSpeak 3 Server 私有许可     https://www.teamspeak.com   （随包分发，使用即接受其条款）
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

"""
ts3-serverset.py —— 一次性校正 TS3 虚拟服务器的关键属性（幂等，可反复执行）

为什么需要它（都是上海部署时真实踩过的坑）：
  1) hostmessage_mode = 3 表示「弹出消息后强制断开连接」（本意是服务器关机通知）。
     一旦被设成 3，【所有客户端一进服务器就被踢】，而日志只写 reasonmsg=Leaving，
     看起来像客户端自己退出 —— 极难排查。必须校正为 1（在聊天框显示）。
  2) needed_identity_security_level = 8 会让【没刷过身份等级的新人连不上】。
     全新部署应设为 5（TS3 默认值，兼顾安全与可用性）。
  3) 服务器名里常带肉眼看不见的【尾随空格】，客户端书签/排序会出怪问题 → 统一 rstrip。
  4) virtualserver_flag_password 与 virtualserver_password 必须【成对】设置，
     只改密码不改 flag 会出现「设了空密码却仍要求输入密码」。

用法（环境变量驱动，默认值即生产值）：
    TS3_PASS=<ServerQuery密码> python3 ts3-serverset.py
"""
import os
import socket
import sys
import time

HOST = os.environ.get("TS3_HOST", "127.0.0.1")
PORT = int(os.environ.get("TS3_QUERY_PORT", "10011"))
USER = os.environ.get("TS3_USER", "serveradmin")
PASS = os.environ.get("TS3_PASS", "")

NAME = os.environ.get("SV_NAME", "")            # 留空则不改名
PW = os.environ.get("SV_PW", "")                # 服务器密码，空 = 无密码
SECLEVEL = os.environ.get("SV_SECLEVEL", "5")
HOSTMSG = os.environ.get("SV_HOSTMSG_MODE", "1")
LOGCLIENT = os.environ.get("SV_LOG_CLIENT", "1")


def esc(s):
    """TS3 ServerQuery 转义"""
    return (s.replace("\\", "\\\\").replace(" ", "\\s")
             .replace("/", "\\/").replace("|", "\\p")
             .replace("\n", "\\n").replace("\r", ""))


def unesc(s):
    return (s.replace("\\s", " ").replace("\\/", "/")
             .replace("\\p", "|").replace("\\n", "\n").replace("\\\\", "\\"))


class Q:
    def __init__(self, host, port, timeout=15):
        self.s = socket.socket()
        self.s.settimeout(timeout)
        self.s.connect((host, port))
        self._recv()

    def _recv(self, n=262144):
        time.sleep(0.25)
        try:
            return self.s.recv(n).decode("utf-8", "ignore").strip()
        except socket.timeout:
            return ""

    def cmd(self, c, wait=0.35):
        self.s.send((c + "\n").encode("utf-8"))
        time.sleep(wait)
        return self._recv()

    def close(self):
        try:
            self.cmd("quit")
        except Exception:
            pass
        try:
            self.s.close()
        except Exception:
            pass


def ok(resp):
    return isinstance(resp, str) and "error id=0" in resp


def main():
    try:
        q = Q(HOST, PORT)
    except Exception as e:
        print("    ✗ 连不上 ServerQuery %s:%s —— %s" % (HOST, PORT, e))
        return 1

    r = q.cmd("login %s %s" % (USER, PASS))
    if not ok(r):
        print("    ✗ ServerQuery 登录失败: %s" % r.splitlines()[0][:120])
        q.close()
        return 1

    q.cmd("use sid=1")

    changed, failed = [], []

    # ① 服务器名（去掉尾随空格）
    if NAME:
        q.cmd("serveredit virtualserver_name=%s" % esc(NAME.rstrip()))
        changed.append("name=%s" % NAME.rstrip())

    # ② 服务器密码 + flag 成对设置
    cur = q.cmd("serverinfo")
    already_ok = False
    if ok(cur):
        # 只有当前状态与目标不一致时才写，避免无谓改动
        want_flag = "1" if PW else "0"
        if ("virtualserver_flag_password=%s" % want_flag) in cur:
            already_ok = True
    if not already_ok:
        q.cmd("serveredit virtualserver_password=%s" % esc(PW))
        q.cmd("serveredit virtualserver_flag_password=%d" % (1 if PW else 0))
        changed.append("password=%s" % ("已设置" if PW else "已清空"))

    # ③ 身份安全等级
    r = q.cmd("serveredit virtualserver_needed_identity_security_level=%s" % SECLEVEL)
    if ok(r):
        changed.append("security_level=%s" % SECLEVEL)
    else:
        failed.append("security_level: %s" % r.splitlines()[0][:100])

    # ④ 服务器消息模式（=3 会让所有人连上就被踢）
    r = q.cmd("serveredit virtualserver_hostmessage_mode=%s" % HOSTMSG)
    if ok(r):
        changed.append("hostmessage_mode=%s" % HOSTMSG)
    else:
        failed.append("hostmessage_mode: %s" % r.splitlines()[0][:100])

    # ⑤ 客户端连接日志（默认 0，排查时什么都看不到）
    r = q.cmd("serveredit virtualserver_log_client=%s" % LOGCLIENT)
    if ok(r):
        changed.append("log_client=%s" % LOGCLIENT)

    # ── 复核 ──
    info = q.cmd("serverinfo")
    q.close()

    print("    ✓ 已校正: %s" % ("、".join(changed) if changed else "（无需改动）"))
    if failed:
        print("    ⚠ 未生效: %s" % "; ".join(failed))

    if ok(info):
        want = {
            "virtualserver_name": None,
            "virtualserver_needed_identity_security_level": SECLEVEL,
            "virtualserver_hostmessage_mode": HOSTMSG,
            "virtualserver_flag_password": ("1" if PW else "0"),
            "virtualserver_maxclients": None,
        }
        out = {}
        for kv in info.split():
            if "=" in kv:
                k, v = kv.split("=", 1)
                out[k] = v
        for k, v in want.items():
            if k not in out:
                continue
            mark = "✓" if (v is None or out[k] == v) else "✗"
            print("      %s %-48s = %s" % (mark, k, unesc(out[k])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
