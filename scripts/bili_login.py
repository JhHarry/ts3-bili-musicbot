#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ──────────────────────────────────────────────────────────────────────────
# 二维码由本仓库的 qrmini.py 生成；登录走 B站官方接口：
#   B站 Web 接口       公开接口      https://api.bilibili.com   （本仓库只调用，不修改其内容）
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

"""
bili_login.py —— B站扫码登录（二维码全用 Python 现画，零外部依赖）

做三件事：
    1) 向 passport.bilibili.com 申请一个 qrcode_key 和对应的登录 URL
    2) 把这个 URL 画成二维码 —— 同时给两种形态：
         · PNG 图片文件（默认 /var/tmp/bili_qr.png）→ 传到手机/电脑打开就能扫
         · 终端字符画（手机对着屏幕也能扫）
    3) 轮询登录结果，成功后把 cookie 写成 Netscape 格式
       （yt-dlp / 本项目的 bili_proxy.py 都用这个格式）保存到 /opt/ts3bot/bili_cookies.txt

用法：
    python3 bili_login.py                  # 扫码登录
    python3 bili_login.py --check          # 只检查现有 cookie 是否还有效
    python3 bili_login.py --png /tmp/q.png # 指定二维码图片路径
    python3 bili_login.py --no-terminal    # 只在终端画图不方便时关掉字符画
    python3 bili_login.py --json           # 机器可读输出（供脚本调用）

不想联网装库：二维码由同目录的 qrmini.py 纯 Python 生成（只用 zlib 标准库）。

说明：
    * 登录**不是必须的** —— 不登录也能点歌，只是音源档位可能偏低。
    * cookie 有效期通常数月；失效后重跑本脚本即可。
"""

import argparse
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import qrmini
except ImportError:
    qrmini = None

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
REFERER = "https://www.bilibili.com/"

DEFAULT_OUT = os.environ.get("BILI_COOKIE_FILE", "/opt/ts3bot/bili_cookies.txt")
DEFAULT_PNG = os.environ.get("BILI_QR_PNG", "/var/tmp/bili_qr.png")
STATUS_FILE = os.environ.get("BILI_LOGIN_STATUS", "/var/tmp/bili_login_status.txt")

API_GEN = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
API_POLL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
API_NAV = "https://api.bilibili.com/x/web-interface/nav"

CODE_OK, CODE_EXPIRED, CODE_SCANNED = 0, 86038, 86090

STATUS_TEXT = {
    "WAITING": "等待扫码",
    "SCANNED": "已扫码，请在手机上点「确认登录」",
    "OK": "登录成功",
    "EXPIRED": "二维码已过期",
    "ERROR": "出错",
}


def log(msg=""):
    print(msg, flush=True)


def set_status(state, extra=""):
    try:
        with open(STATUS_FILE, "w") as f:
            f.write(state + ((" " + extra) if extra else ""))
    except OSError:
        pass


def req(url):
    return urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": REFERER,
        "Accept": "application/json, text/plain, */*",
    })


def open_json(opener, url, timeout=15):
    with opener.open(req(url), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


# ---------------------------------------------------------------- 画二维码

def draw_qr(url, png_path=None, terminal=True):
    """用纯 Python 画二维码。返回 (png路径 或 None, 是否画了终端)"""
    if qrmini is None:
        log("⚠ 找不到 qrmini.py（应与本脚本同目录），无法生成二维码")
        log("  请手动把下面的链接转成二维码：")
        log("  %s" % url)
        return None, False

    matrix, ver = qrmini.make_matrix(url, level="M")

    out_png = None
    if png_path:
        try:
            os.makedirs(os.path.dirname(png_path) or ".", exist_ok=True)
            qrmini.write_png(matrix, png_path, scale=8, border=4)
            os.chmod(png_path, 0o644)
            out_png = png_path
        except OSError as e:
            log("⚠ 写二维码图片失败：%s" % e)

    if terminal:
        log(qrmini.to_terminal(matrix, mode="ANSIUTF8", border=2))
        log()

    return out_png, terminal


# ---------------------------------------------------------------- 登录流程

def do_login(opts):
    cj = http.cookiejar.MozillaCookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    set_status("WAITING")
    try:
        gen = open_json(opener, API_GEN)
    except Exception as e:
        set_status("ERROR", str(e))
        log("✗ 申请二维码失败：%s" % e)
        log("  （检查服务器能否访问 passport.bilibili.com）")
        return 2

    if gen.get("code") != 0:
        set_status("ERROR", "generate")
        log("✗ 接口返回异常：%s" % gen)
        return 2

    data = gen.get("data") or {}
    key, url = data.get("qrcode_key"), data.get("url")
    if not key or not url:
        set_status("ERROR", "bad-response")
        log("✗ 接口返回缺少 qrcode_key / url")
        return 2

    png, _ = draw_qr(url, opts.png, terminal=not opts.no_terminal)

    if png:
        log("  📱 二维码图片：%s" % png)
        log("     传到手机打开即可扫码（在电脑上直接打开这个文件也行）")
        log("     例如：scp %s@<服务器>:%s ./" % (_ssh_user_hint(), png))
    log("  🔗 二维码内容：%s" % url)
    log()
    log("  用【手机 B站 App】扫上面任意一个二维码，然后在手机上点「确认登录」")
    log()

    deadline = time.time() + opts.timeout
    last = None
    spin = "|/-\\"
    i = 0
    while time.time() < deadline:
        try:
            r = open_json(opener, API_POLL + "?qrcode_key=" + key, timeout=10)
        except Exception:
            i += 1
            sys.stdout.write("\r  %s 等待扫码（网络抖动，重试中…）" % spin[i % 4])
            sys.stdout.flush()
            time.sleep(3)
            continue

        code = (r.get("data") or {}).get("code")

        if code == CODE_OK:
            _save_cookies(cj, opts.out, opts)
            set_status("OK")
            sys.stdout.write("\r" + " " * 56 + "\r")
            log("✅ 登录成功，cookie 已写入 %s" % opts.out)
            _maybe_cleanup_png(png)
            return 0

        if code == CODE_EXPIRED:
            set_status("EXPIRED")
            sys.stdout.write("\r" + " " * 56 + "\r")
            log("✗ 二维码已过期，请重新运行本脚本")
            return 3

        state = "SCANNED" if code == CODE_SCANNED else "WAITING"
        if state != last:
            set_status(state)
            sys.stdout.write("\r" + " " * 56 + "\r")
            log("  → %s" % STATUS_TEXT[state])
            last = state
            i = 0
        else:
            i += 1
            sys.stdout.write("\r  %s %s" % (spin[i % 4], STATUS_TEXT[state]))
            sys.stdout.flush()
        time.sleep(2)

    set_status("EXPIRED")
    sys.stdout.write("\r" + " " * 56 + "\r")
    log("✗ 等待超时（%d 秒）" % opts.timeout)
    return 3


def _ssh_user_hint():
    try:
        return os.environ.get("SUDO_USER") or os.environ.get("USER") or "root"
    except Exception:
        return "root"


def _maybe_cleanup_png(png):
    """登录成功后二维码就没用了，顺手删掉（里面是登录票据）"""
    if png and os.path.exists(png):
        try:
            os.remove(png)
        except OSError:
            pass


def _save_cookies(cj, out_path, opts):
    d = os.path.dirname(out_path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = out_path + ".tmp"
    cj.save(tmp, ignore_discard=True, ignore_expires=True)
    os.replace(tmp, out_path)          # 原子替换，代理不会读到半截文件
    os.chmod(out_path, 0o600)

    if os.geteuid() == 0:
        user = opts.owner or _guess_bot_user()
        if user:
            try:
                import pwd
                pw = pwd.getpwnam(user)
                os.chown(out_path, pw.pw_uid, pw.pw_gid)
            except Exception:
                pass


def _guess_bot_user():
    try:
        import pwd
        st = os.stat("/opt/ts3bot")
        return pwd.getpwuid(st.st_uid).pw_name
    except Exception:
        return None


# ---------------------------------------------------------------- 校验

def cookie_header_from_file(path):
    parts = []
    try:
        for line in open(path):
            line = line.replace("#HttpOnly_", "")
            if line.startswith("#") or not line.strip():
                continue
            f = line.rstrip("\n").split("\t")
            if len(f) >= 7:
                parts.append("%s=%s" % (f[5], f[6]))
    except OSError:
        return None
    return "; ".join(parts) if parts else None


def do_check(opts):
    path = opts.out
    if not os.path.exists(path):
        log("✗ cookie 文件不存在：%s" % path)
        return 1
    header = cookie_header_from_file(path)
    if not header:
        log("✗ cookie 文件为空或格式不对：%s" % path)
        return 1
    rq = urllib.request.Request(API_NAV, headers={
        "User-Agent": UA, "Referer": REFERER, "Cookie": header})
    try:
        with urllib.request.urlopen(rq, timeout=15) as r:
            j = json.loads(r.read().decode("utf-8", "ignore"))
    except Exception as e:
        log("✗ 请求失败：%s" % e)
        return 2
    d = j.get("data") or {}
    if d.get("isLogin"):
        log("✅ cookie 有效 —— 已登录为：%s (uid=%s，大会员=%s)"
            % (d.get("uname"), d.get("mid"),
               "是" if d.get("vipStatus") == 1 else "否"))
        return 0
    log("✗ cookie 已失效（或未登录），请重新运行：python3 %s"
        % os.path.basename(__file__))
    return 1


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description="B站扫码登录（纯 Python 生成二维码）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="cookie 输出路径（默认 %(default)s）")
    ap.add_argument("--png", default=DEFAULT_PNG,
                    help="二维码 PNG 输出路径（默认 %(default)s，登录成功后自动删除）")
    ap.add_argument("--no-terminal", action="store_true",
                    help="不在终端画二维码字符画")
    ap.add_argument("--no-png", action="store_true", help="不生成 PNG 文件")
    ap.add_argument("--check", action="store_true", help="只检查现有 cookie 是否有效")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    ap.add_argument("--timeout", type=int, default=300, help="等待扫码秒数")
    ap.add_argument("--owner", default="", help="cookie 文件属主（默认自动推断）")
    opts = ap.parse_args()
    if opts.no_png:
        opts.png = None

    rc = do_check(opts) if opts.check else do_login(opts)

    if opts.json:
        state = "OK" if rc == 0 else ("EXPIRED" if rc == 3 else "ERROR")
        log(json.dumps({"ok": rc == 0, "rc": rc, "state": state,
                        "cookie_file": opts.out}, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    sys.exit(main())
