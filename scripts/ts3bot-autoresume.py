#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ──────────────────────────────────────────────────────────────────────────
# 被守护对象：
#   TS3AudioBot        OSL-3.0      https://github.com/Splamy/TS3AudioBot
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

"""TS3AudioBot 重启后自动续播上一首曲子。

由 ts3bot-watchdog.sh 每分钟调用一次：
  1) 记录机器人日志里最近一次 !play 的内容（用户输入原样保存，可直接重放）
  2) 察觉机器人 PID 变化（内存守卫重启 / 崩溃）后，等它重新入频道再自动续播

保护规则（避免误伤）：
  - 用户执行过 !stop / !pause -> 清空续播记录，重启后不再放
  - 频道里**至少要有一个真人**才续播（防止深夜无人时空放、白耗流量）
  - 机器人已经在播放（ffmpeg 在跑）-> 不打扰
"""
import json
import os
import re
import socket
import sys
import time

QUERY = ("127.0.0.1", 10011)
PW_FILE = "/opt/ts3bot/query.pw"
LOG_DIR = "/opt/ts3bot/logs"
STATE = "/var/tmp/.ts3bot_resume_state"
LOG = "/var/log/ts3bot-autoresume.log"
CID = 22                     # Lobby 频道
BOT_MARKS = ("bot", "机器人")  # 用来把机器人自己从"真人"里排除
WAIT_ROUNDS = 20             # 最多等 20 轮 × 3 秒 = 60 秒
# 仅用于测试：置 1 时忽略"必须有真人"的限制（出问题时不会被误用）
IGNORE_HUMAN = os.environ.get("TS3_RESUME_IGNORE_HUMAN") == "1"


def say(msg):
    try:
        with open(LOG, "a") as f:
            f.write("%s %s\n" % (time.strftime("%F %T"), msg))
    except Exception:
        pass


def esc(s):
    """TeamSpeak ServerQuery 参数转义"""
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == "/":
            out.append("\\/")
        elif ch == " ":
            out.append("\\s")
        elif ch == "|":
            out.append("\\p")
        elif ch in "\n\r":
            out.append("\\n")
        else:
            out.append(ch)
    return "".join(out)


def password():
    try:
        return open(PW_FILE).read().strip().split()[0]
    except Exception:
        return ""


def newest_log():
    try:
        fs = [os.path.join(LOG_DIR, f) for f in os.listdir(LOG_DIR)
              if f.endswith(".log")]
        return max(fs, key=os.path.getmtime) if fs else None
    except Exception:
        return None


def proc_pids(name):
    pids = []
    try:
        for d in os.listdir("/proc"):
            if not d.isdigit():
                continue
            try:
                with open("/proc/%s/comm" % d) as f:
                    if f.read().strip() == name:
                        pids.append(d)
            except Exception:
                pass
    except Exception:
        pass
    return pids


def playing():
    """机器人是否正在放歌（它靠 ffmpeg 解码）"""
    return bool(proc_pids("ffmpeg"))


def qcmd(s, c, wait=0.4):
    s.send((c + "\n").encode())
    time.sleep(wait)
    s.settimeout(2.0)
    data = b""
    while True:
        try:
            chunk = s.recv(65536)
        except socket.timeout:
            break
        if not chunk:
            break
        data += chunk
        if b"error id=" in data:
            break
    return data.decode("utf-8", "ignore")


def connect():
    s = socket.create_connection(QUERY, timeout=10)
    s.recv(4096)                       # banner
    qcmd(s, "login serveradmin " + password())
    qcmd(s, "use 1")
    return s


def clients(s):
    """返回 [(昵称, 是否机器人, cid)]"""
    data = qcmd(s, "clientlist")
    out = []
    for part in data.split("|"):
        if "client_type=0" not in part:
            continue          # 只算真实语音客户端，排除 query
        m = re.search(r"client_nickname=(\S+)", part)
        nick = m.group(1) if m else "?"
        c = re.search(r"\bcid=(\d+)", part)
        nick_l = nick.lower()
        is_bot = any(k in nick_l for k in BOT_MARKS)
        out.append((nick, is_bot, c.group(1) if c else "?"))
    return out


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def save_state(st):
    try:
        with open(STATE, "w") as f:
            json.dump(st, f)
    except Exception:
        pass


def do_resume(cmd):
    for _ in range(WAIT_ROUNDS):
        time.sleep(3)
        if playing():
            say("机器人已在播放，跳过续播")
            return
        try:
            s = connect()
            cl = clients(s)
            s.close()
        except Exception:
            continue
        if not cl:
            continue
        bots = [c for c in cl if c[1]]
        humans = [c for c in cl if not c[1]]
        if not bots:
            continue                       # 机器人还没入频道
        if not humans and not IGNORE_HUMAN:
            continue                       # 没有真人在，先不放
        try:
            s = connect()
            r = qcmd(s, "sendtextmessage targetmode=2 target=%d msg=%s"
                     % (CID, esc(cmd)))
            s.close()
        except Exception as e:
            say("发送续播命令失败: %s" % str(e)[:60])
            return
        if "error id=0" in r:
            say("✅ 已续播: %s  (真人在线: %s)"
                % (cmd, ", ".join(h[0] for h in humans)))
        else:
            say("续播命令返回异常: %s" % r.strip()[:90])
        return
    say("等待 60 秒仍不满足条件（机器人未上线 / 无真人在线），放弃续播")


def main():
    force = "--force" in sys.argv
    st = load_state()
    last = st.get("last_play", "")

    # ---- 1) 从机器人日志里更新"最近一次点播" ----
    lg = newest_log()
    if lg:
        try:
            txt = open(lg, encoding="utf-8", errors="ignore").read()
            cmds = re.findall(r"requested: (!\S+.*)", txt)
        except Exception:
            cmds = []
        if cmds:
            c = cmds[-1].strip()
            if c.startswith(("!stop", "!pause")):
                if last:
                    say("用户执行 %s，清空续播记录" % c.split()[0])
                last = ""
            elif c.startswith("!play "):
                if c != last:
                    say("记录点播: %s" % c)
                last = c
    st["last_play"] = last

    # ---- 2) 检测重启（PID 变化）----
    pids = proc_pids("TS3AudioBot")
    pid = pids[0] if pids else ""
    old = st.get("pid", "")
    restarted = force or bool(old and pid and old != pid)
    st["pid"] = pid
    save_state(st)

    if not restarted:
        return
    if not last:
        say("检测到机器人重启（pid %s -> %s），但没有可续播的曲目"
            % (old or "?", pid or "?"))
        return
    say("检测到机器人重启（pid %s -> %s），准备续播: %s"
        % (old or "?", pid or "?", last))
    do_resume(last)


if __name__ == "__main__":
    main()
