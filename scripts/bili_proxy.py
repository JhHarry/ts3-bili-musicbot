#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ──────────────────────────────────────────────────────────────────────────
# B站音频代理所用到的第三方组件：
#   B站 Web 接口       公开接口      https://api.bilibili.com   （本仓库只调用，不修改其内容）
#   pypinyin           MIT          https://github.com/mozillazg/python-pinyin   （可选）
#   requests           Apache-2.0   https://github.com/psf/requests              （可选）
#   yt-dlp             Unlicense    https://github.com/yt-dlp/yt-dlp
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

"""
B站音频代理 v6  ——  边播边释放（纯透传，不在本地留缓存）
监听 127.0.0.1:8087（仅本地）

运行模式（环境变量 BILI_PROXY_MODE）：
  stream  默认。解析出直链后直接把字节流转发出去，读到什么发什么，
          不写磁盘；上游断流时按当前偏移自动续传。
          优点：零磁盘占用、零残留、无 ffmpeg、无等待。
  cache   可选。边下边播并落盘，完整缓存后下次毫秒级命中（占磁盘）。

路由：
  /b/<BV号|av号|B站链接>   点播指定视频的音频
  /s/<关键词>              搜索并播放
  /health                  健康检查
  /status                  运行状态

v3 相对 v2 的关键改进：
  1. 【边下边播】不再等 ffmpeg 全量下载完才响应。首字节 ~1s 内返回，
     后台同步落盘；下满后自动"转正"为完整缓存，下次毫秒级命中。
  2. 【零转码】B站 DASH 音轨本身就是 moov 前置的可 seek MP4（或 FLAC），
     直接透传原始字节 —— 省掉 ffmpeg 的 CPU 与全部等待。
  3. 【真 Range】完整缓存走本地磁盘；未下到的区间直接向B站 CDN 转发 Range，
     seek 秒级响应。
  4. 【解析缓存 + TLS 复用】requests.Session 复用连接；
     bvid→cid 永久缓存、关键词→bvid 10 分钟、直链 15 分钟。
"""
import hashlib
import http.server
import json
import os
import re
import shutil
import socketserver
import subprocess
import threading
import time
import urllib.parse
import urllib.request

try:
    import requests
    HAVE_REQ = True
except ImportError:
    HAVE_REQ = False

PORT = 8087
YTDLP = "/usr/local/bin/yt-dlp"
FFMPEG = "/usr/bin/ffmpeg"
COOKIES = "/opt/ts3bot/bili_cookies.txt"
CACHE_DIR = "/var/tmp/ts3music"
CACHE_MAX_MB = 3000
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
REFERER = "https://www.bilibili.com/"
HEADERS = {"User-Agent": UA, "Referer": REFERER}
API_HEADERS = dict(HEADERS, **{"Accept": "application/json, text/plain, */*"})

CHUNK = 262144

os.environ.setdefault("TMPDIR", "/var/tmp/ytdlp")
os.makedirs(os.environ["TMPDIR"], exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

COLLECTION_WORDS = ["合集", "合辑", "精选", "串烧", "连播", "歌单", "专辑",
                    "playlist", "循环", "小时", "车载", "助眠", "全集",
                    "无损音乐库", "歌单合集"]
LONG_WORDS = ["演唱会", "现场", "专辑", "全场", "音乐会", "纯享",
              "live", "concert", "album", "巡演", "大电影"]

# ---------- 选源分档（数字越小越接近"原版"）----------
# 0=原版  1=现场/演唱会  2=翻唱或改编  3=纯器乐/伴奏/教学
COVER_WORDS = ["翻唱", "cover", "covered", "女声版", "男声版", "女生版", "男生版",
               "童声", "合唱版", "群星", "翻版", "模仿", "ai翻唱", "ai孙",
               "ai cover", "ai版", "中文版", "英文版", "粤语版", "日语版",
               "填词", "改编", "烟嗓", "民谣版", "抖音版", "网红版", "鬼畜",
               "原唱：", "原唱:", "原曲：", "原曲:", "翻自", "改编自",
               "苏联", "气突苏", "魔改", "整活"]
INSTRUMENT_WORDS = ["伴奏", "instrumental", "off vocal", "offvocal", "卡拉ok",
                    "karaoke", "无人声", "无vocal", "纯音乐", "纯音", "消音",
                    "钢琴", "吉他", "ukulele", "尤克里里", "架子鼓", "鼓谱",
                    "鼓行家", "电子琴", "小提琴", "古筝", "二胡", "指弹",
                    "演奏", "弦乐", "八音盒", "音乐盒", "口琴", "手风琴",
                    "萨克斯", "长笛", "双排键", "midi", "简谱", "五线谱",
                    "教学", "教程", "教你", "谱子", "零基础", "翻弹",
                    # ===== 补漏（2026-09-16）：实测真实 B站 伴奏标题的漏网词 =====
                    "inst.", "(inst", "[inst", "【inst", "inst版", "inst】",
                    "mr版", "mr伴奏", "music record",
                    "伴唱", "去人声", "无人声版", "no vocal", "novocal",
                    "no-vocal", "off-vocal", "off_vocal",
                    "カラオケ", "伴奏版", "纯伴奏", "原版伴奏", "无人声伴奏",
                    "器乐版", "纯器乐", "演奏版", "交响乐", "无伴奏清唱", "人声消除"]
INSTR_BOUND_WORDS = ["inst", "inst.", "instr"]
# ---------- 标签专用强信号词（tag 字段比标题更硬）----------
# 这里只放「出现即基本可确定」的词，避免像"钢琴/吉他"这种
# 在原版歌曲标签里也会出现的词造成误伤。
TAG_INSTR_WORDS = ["伴奏", "纯音乐", "消音", "无人声", "无vocal",
                   "instrumental", "karaoke", "卡拉ok", "カラオケ",
                   "翻弹", "指弹", "演奏", "交响乐", "钢琴曲", "八音盒",
                   "口琴", "古筝", "二胡", "小提琴", "架子鼓", "midi",
                   "简谱", "五线谱", "教学", "教程", "off vocal", "offvocal"]
TAG_COVER_WORDS = ["翻唱", "cover", "鬼畜", "音mad", "remix", "混音",
                   "电音", "dj版", "加速", "变速", "ai翻唱", "恶搞",
                   "搞笑", "整活", "二创", "填词", "改编"]
TAG_LIVE_WORDS  = ["现场", "演唱会", "音乐会", "live", "concert", "巡演"]

ALTER_WORDS = ["remix", "混音", "电音", "dj版", "加速", "慢速", "变速", "二创",
               "调教", "音mad", "0.8x", "1.25x", "1.5x", "0.9x", "2.0x",
               "8d", "环绕", "reaction", "反应", "解析", "讲解", "测评",
               "盘点", "倒数第一", "mashup", "缝合", "搞笑", "沙雕",
               "恶搞", "玩梗", "迫真", "确信"]
# ---------- 音视频区分（2026-09-16）----------
# 找歌时：这些是"视频抠出来的音轨"的特征 → 扣分
VIDEO_RIP_WORDS = ["mv", "4k", "8k", "hdr", "修复", "视频", "剪辑", "截图",
                   "60帧", "120帧", "帧版", "杜比", "全景声", "蓝光", "重制",
                   "搬运", "录屏", "饭拍", "直拍", "片头", "片尾", "花絮",
                   "官方mv", "高清修复", "视觉"]
# 找歌时：这些是"纯音频投稿"的特征 → 加分
PURE_AUDIO_WORDS = ["纯音频", "音源", "无损音质", "高音质", "官方音源",
                    "专辑版", "录音室", "studio", " audio", "试听",
                    "完整音源", "原档", "母带", "音轨"]
# 演唱会/演出意图（此时视频才是对的）
PERF_WORDS = ["演唱会", "现场", "音乐会", "音乐节", "巡演", "演出",
              "live", "concert", "tour", "live版"]

LIVE_WORDS = ["现场", "演唱会", "全场", "音乐会", "live", "concert",
              "巡演", "不插电", "unplugged", "现场版"]
ORIGINAL_HINTS = ["原版", "原声", "官方", "official", "无损", "hi-res", "hires", "flac", "完整版", "正版", "专辑版", "经典", "首发", "正式版", "高质量"]

# 码率择优：同档次内最多多试几个候选；够好就收手（避免拖慢点歌）
PROBE_N = 4
BW_GOOD = 160000        # 已是原版且达到这个码率，就不再比了

# 搜索范围：优先在 B站【音乐区】里找，避开鬼畜/剪辑/访谈等非音乐内容
MUSIC_TID = 3           # 3 = 音乐区（含 原创音乐28/翻唱31/演奏59/MV193/现场29 等子分区）
MIN_MUSIC_HITS = 3      # 音乐区结果少于这个数就回退全区搜索

# 运行模式：stream=边播边释放（默认） | cache=边下边播并落盘
MODE = os.environ.get("BILI_PROXY_MODE", "stream").strip().lower()
if MODE not in ("stream", "cache"):
    MODE = "stream"
PURGE_ON_START = MODE == "stream"     # stream 模式下清掉历史缓存

_stat_start = time.time()
_stat_req = 0
_stat_stream = 0


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


# ---------- Python 侧小工具 ----------
_tls = threading.local()


def sess():
    """每线程一个 requests.Session，复用 TLS 握手（省掉每次 ~0.3s）"""
    s = getattr(_tls, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update(API_HEADERS)
        _tls.s = s
    return s


_cookie_cache = {"mtime": 0, "value": None}


def cookie_header():
    try:
        mt = os.path.getmtime(COOKIES)
    except OSError:
        return None
    if _cookie_cache["mtime"] == mt:
        return _cookie_cache["value"]
    parts = []
    try:
        for line in open(COOKIES):
            line = line.replace("#HttpOnly_", "")
            if line.startswith("#") or not line.strip():
                continue
            f = line.rstrip("\n").split("\t")
            if len(f) >= 7:
                parts.append("%s=%s" % (f[5], f[6]))
    except Exception:
        return None
    val = "; ".join(parts) if parts else None
    _cookie_cache["mtime"] = mt
    _cookie_cache["value"] = val
    return val


def api_get(url, _retry=0):
    h = dict(API_HEADERS)
    ck = cookie_header()
    if ck:
        h["Cookie"] = ck
    try:
        if HAVE_REQ:
            r = sess().get(url, headers=h, timeout=15)
            r.raise_for_status()
            return r.json()
        return json.load(urllib.request.urlopen(
            urllib.request.Request(url, headers=h), timeout=15))
    except Exception as e:
        # B站反爬限流会给 HTTP 412，等一下重试（最多 2 次）
        code = getattr(e, "code", None)
        resp = getattr(e, "response", None)
        if code is None and resp is not None:
            code = getattr(resp, "status_code", None)
        if code == 412 and _retry < 2:
            time.sleep(1.2 * (_retry + 1))
            log("搜索接口 412 限流，第 %d 次重试" % (_retry + 1))
            return api_get(url, _retry + 1)
        raise


# ---------- 解析缓存 ----------
_clock = threading.Lock()
_cid_cache = {}      # bvid -> (cid, title)          cid 永不变化
_search_cache = {}   # keyword -> (candidates, ts)
_url_cache = {}      # ident -> (url, title, bvid, codec, bw, ts)
_dead_bvids = set()  # view 接口报错的 bvid（已删除/私密/区域限制），后续跳过
_URL_TTL = 15 * 60
_SEARCH_TTL = 10 * 60


# ---------- 拼音匹配（2026-09-16）----------
# 用户可能输入拼音（"zhoujielun daoxiang"）或英文，需要能命中中文标题
try:
    from pypinyin import lazy_pinyin as _lazy_pinyin
    _HAS_PINYIN = True
except Exception:
    _HAS_PINYIN = False

_PY_CACHE = {}

def _to_pinyin(text):
    """中文 → 拼音连写（小写、无声调），带缓存"""
    if not _HAS_PINYIN or not text:
        return ''
    if text in _PY_CACHE:
        return _PY_CACHE[text]
    try:
        r = ''.join(_lazy_pinyin(text)).lower()
    except Exception:
        r = ''
    if len(_PY_CACHE) < 4000:
        _PY_CACHE[text] = r
    return r

def _is_latin_query(q):
    """查询里全是拉丁字母/数字、且不含中文 → 可能是拼音或英文"""
    q = q or ''
    has_latin = bool(re.search(r'[a-zA-Z]', q))
    has_cjk = bool(re.search(r'[\u4e00-\u9fff]', q))
    return has_latin and not has_cjk


# ---------- 选源：分档 + 码率 ----------
_bw_cache = {}      # bvid -> 最大音频码率(bps)，同一视频码率不会变


def _title_tier(title, keyword="", tag=""):
    """判断候选属于哪个档次。0=原版 1=现场 2=翻唱/改编 3=纯器乐/伴奏/教学。
    如果【用户自己搜的就是这一类】（例如自己找伴奏版），该类不再降级。"""
    t = (title or "").lower()
    kw = (keyword or "").lower()
    tg = (tag or "").lower()

    # ---- 标签优先：tag 里的「伴奏/纯音乐/翻弹/翻唱」是硬证据 ----
    # 典型漏网案例：标题「（完整版）维也纳金色大厅《XXX》（迫真）」
    # 标题毫无器乐词，但 tag 里有「演奏 | 交响乐」——只扫标题就会误判成原版。
    if tg:
        for w in TAG_INSTR_WORDS:
            if w in tg and w not in kw:
                return 3
        for w in TAG_COVER_WORDS:
            if w in tg and w not in kw:
                return 2
        for w in TAG_LIVE_WORDS:
            if w in tg and w not in kw:
                return 1


    def hit(words):
        """类别级意图判断：如果【用户搜索词里本来就含这一类词】（例如自己搜"稻香 伴奏"），
        整个类别都不降档 —— 避免把用户真正想要的伴奏版当成"低质结果"排掉。"""
        for x in words:
            if x in kw:
                return False
            if len(kw) >= 4 and kw in x:      # kw="inst" 也要能匹配到词表里的 "inst."
                return False
        for w in words:
            if w in t:
                return True
        return False

    def hitb(words):
        """短英文缩写（inst / mr / off）必须按【词边界】匹配，
        否则会把 instant / install / mirror 之类误判成伴奏。"""
        for x in words:
            if x in kw:
                return False
        for w in words:
            if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", t):
                return True
        return False

    if hit(INSTRUMENT_WORDS) or hitb(INSTR_BOUND_WORDS):
        return 3
    if hit(COVER_WORDS) or hit(ALTER_WORDS):
        return 2
    if hit(LIVE_WORDS):
        return 1
    return 0


def _probe_audio_bw(bvid, cid):
    """探到这个视频的最大音频码率（bps）。0 表示拿不到/无独立音轨。"""
    with _clock:
        v = _bw_cache.get(bvid)
    if v is not None:
        return v
    try:
        pu = api_get("https://api.bilibili.com/x/player/playurl"
                     "?bvid=%s&cid=%s&fnval=16&fnver=0&fourk=1" % (bvid, cid))
        if pu.get("code") != 0:
            return 0
        au = ((pu["data"].get("dash") or {}).get("audio")) or []
        bw = max((a.get("bandwidth") or 0) for a in au) if au else 0
    except Exception:
        return 0
    with _clock:
        _bw_cache[bvid] = bw
    return bw

# ---------- 标题归一化 & 模糊匹配 ----------
# 借鉴：youtube_title_parse 的 clean_common_fluff、StackOverflow #79489705 的循环剥离正则
import math
import difflib

_DECOR_RE = re.compile(
    r"[\s\-—–|｜/]*[\(\[【（]\s*[^\)\]】）]{0,44}?"
    r"(?:official|video|audio|lyrics?|remaster(?:ed)?|hi-?res|hires|flac|无损|高清|"
    r"4k|8k|hd|hq|mv|m/?v|live|现场|完整版|试听|音质|修复|纯享|官方|mv版)"
    r"[^\)\]】）]{0,44}?\s*[\)\]】）]", re.I)

_TAIL_RE = re.compile(
    r"(?:\s*[-–—|｜/]\s*|\s*[\(\[【（]\s*)"
    r"(?:official|video|audio|lyrics?|remaster(?:ed)?|hd|hq|full|4k|8k|mv|m/?v|"
    r"version|完整版|高清|无损|\d{4})\s*[\)\]】）]?\s*$", re.I)

_MARK_RE = re.compile(r"[「」『』“”\"'·・║♪♫♬☆★｜|]+")


def _clean_title(t):
    """归一化标题：循环剥掉【4K60帧】/（Official Video）/- HD 这类装饰包装后，
    再拿干净标题去做匹配打分。装饰越多的标题越难误判成原版。"""
    t = t or ""
    prev = None
    while prev != t:
        prev = t
        t = _DECOR_RE.sub(" ", t)
        t = _TAIL_RE.sub("", t)
    t = _MARK_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _fuzzy(a, b):
    """模糊相似度 0~1（等价于 spotdl 用的 fuzz.ratio，但无第三方依赖）"""
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _dur_seconds(d):
    d = str(d or "0").split(".")[0]
    parts = [int(x) for x in re.findall(r"\d+", d)] or [0]
    s = 0
    for p in parts:
        s = s * 60 + p
    return s


def search_bili_api(keyword, limit=6):
    """搜索，返回按「原版优先 → 综合匹配度」排序的候选 [(bvid, title), ...]

    只在 B站【音乐区】(tids=3) 里搜，避开鬼畜/影视剪辑/访谈等非音乐内容；
    音乐区结果过少时自动回退全区搜索。

    打分借鉴 spotdl 的匹配管线：
      1) 硬过滤：合集/超长/超短
      2) 分档 tier：原版 > 现场 > 翻唱·改编 > 纯器乐   （用户自己找那一类时不降级）
      3) 标题分：token 命中 + 原版线索词 + 模糊相似度(fuzz.ratio 等价物)
      4) 时长锚点：以候选时长中位数为"这首歌该有多长"，用 exp(-k·Δt) 打分
         —— 整活版/裁剪版时长明显偏离，会被自然淘汰（spotdl 的 calc_time_match 思路）
    """
    q = urllib.parse.quote(keyword)
    base = ("https://api.bilibili.com/x/web-interface/search/type"
            "?search_type=video&page=1&keyword=" + q)

    def grab(resp):
        return [it for it in ((resp.get("data") or {}).get("result") or [])
                if it.get("type") == "video"]

    zone = "音乐区"
    r = api_get(base + "&tids=%d" % MUSIC_TID)
    if r.get("code") != 0:            # 分区参数不被接受时退回全区
        zone = "全区"
        r = api_get(base)
        if r.get("code") != 0:
            raise RuntimeError("搜索接口返回 %s" % r.get("message"))
    items = grab(r)
    if zone == "音乐区" and len(items) < MIN_MUSIC_HITS:
        log("音乐区仅 %d 条结果，回退全区搜索" % len(items))
        r = api_get(base)
        zone = "全区"
        if r.get("code") != 0:
            raise RuntimeError("搜索接口返回 %s" % r.get("message"))
        items = grab(r)

    tokens = [t for t in re.split(r"\s+", keyword.strip()) if t]
    long_ok = any(w in keyword.lower() for w in LONG_WORDS)

    def clean(t):
        return re.sub(r"<[^>]+>", "", t or "")

    # ---- 第一遍：硬过滤 ----
    valid = []
    for it in items:
        bv = it.get("bvid")
        if not bv:
            continue
        title = clean(it.get("title"))
        if not title:
            continue
        if not long_ok and any(w in title for w in COLLECTION_WORDS):
            continue          # 合集/串烧/歌单
        dur = _dur_seconds(it.get("duration", "0"))
        if dur > (4 * 3600 if long_ok else 15 * 60):
            continue          # 超长
        # 英文/拼音查询：中文标题必须能对上拼音，否则直接淘汰（治"搜出印尼语评论"那种垃圾）
        if _HAS_PINYIN and _is_latin_query(keyword):
            _kp0 = re.sub(r'[^a-z0-9]', '', keyword.lower())
            _tp0 = re.sub(r'[^a-z0-9]', '', _to_pinyin(title))
            _en0 = re.sub(r'[^a-z0-9]', '', title.lower())
            _ws0 = [w for w in re.split(r'\s+', keyword.lower()) if len(w) >= 2]
            _hit0 = sum(1 for w in _ws0 if re.sub(r'[^a-z0-9]', '', w) in _tp0 or re.sub(r'[^a-z0-9]', '', w) in _en0)
            if _ws0 and _hit0 == 0 and _kp0 not in _tp0 and _kp0 not in _en0:
                continue
        if dur and dur < 25:
            continue          # 太短的片段
        valid.append((it, title, dur))

    # ================= AUTO-RELAX (2026-09-16) =================
    # 问题：用户搜「soul power」这类【专辑/演唱会名】时，关键词里没有
    #       "演唱会/专辑"字样 → long_ok=False → 超过 15 分钟的视频全被砍掉
    #       → 整场演出（常 100+ 分钟）被排除，只剩零碎单曲片段。
    # 对策：如果过滤后【候选太少】或【全都很短】，说明很可能被时长限制误杀，
    #       自动放宽一次（允许 4 小时内的完整演出/专辑）。
    if not long_ok:
        _d = [d for _, _, d in valid if d]
        # 新增判据：原始结果里有【被时长上限砍掉的演出类视频】→ 说明很可能有整场演出
        _LIVE_HINT = ("演唱会", "现场", "音乐会", "音乐节", "巡演",
                      "live", "concert", "tour", "演出")
        _cut_live = 0
        for _it in items:
            _du = _dur_seconds(_it.get("duration", "0"))
            if _du > 15 * 60:
                _t = clean(_it.get("title")).lower()
                if any(w in _t for w in _LIVE_HINT):
                    _cut_live += 1
        # 阈值修正：正常歌曲 180~300 秒，原来的 300 秒判据会把【每首歌】都误判为"偏短"
        # → 改成：候选少于 5 个，或【最长候选都不到 150 秒】（说明只有片段）
        if len(valid) < 5 or (_d and max(_d) < 150) or _cut_live > 0:
            if _cut_live > 0:
                log("发现 %d 个被时长上限砍掉的演出类视频 → 自动放宽" % _cut_live)
            log("候选偏少(%d 个)或偏短(最长 %d 秒) → 自动放宽时长限制，允许完整演出/专辑"
                % (len(valid), max(_d) if _d else 0))
            long_ok = True
            valid = []
            skipped_collection = 0
            for it in items:
                bv = it.get("bvid")
                if not bv:
                    continue
                title = clean(it.get("title"))
                if not title:
                    continue
                dur = _dur_seconds(it.get("duration", "0"))
                if dur > 4 * 3600:
                    continue
                if dur and dur < 25:
                    continue
                # 放宽后仍过滤掉纯合集/歌单，但保留演出/专辑
                if any(w in title for w in ("歌单", "循环", "助眠", "车载", "无损音乐库")):
                    skipped_collection += 1
                    continue
                valid.append((it, title, dur))
            log("放宽后候选: %d 个（跳过合集 %d）" % (len(valid), skipped_collection))

    # ===========================================================

    # ---- 时长锚点：候选时长中位数 ≈ 这首歌的真实长度 ----
    durs = sorted(d for _, _, d in valid if d)
    anchor = durs[len(durs) // 2] if durs else 0

    # ---- 第二遍：分档 + 打分 ----
    def key(v):
        _it, title, dur = v
        tier = _title_tier(title, keyword, _it.get("tag") or "")
        if long_ok and tier == 1:
            tier = 0                      # 用户明确在找现场/演唱会
        ct = _clean_title(title)           # 归一化后再匹配
        low = ct.lower()
        s = 0.0
        for t in tokens:
            if t in ct:
                s += 3
        for w in ORIGINAL_HINTS:
            if w in low:
                s += 2                     # 原版/官方/无损 这类线索加分
                break
        # ---- 拼音匹配：输入全英文/拼音时，把中文标题转拼音再比 ----
        if _HAS_PINYIN and _is_latin_query(keyword):
            _kp = re.sub(r'[^a-z0-9]', '', keyword.lower())
            _tp = re.sub(r'[^a-z0-9]', '', _to_pinyin(ct))
            if _kp and _tp:
                # 拼音查询时：标题含中文的优先
                # （用户输入拼音，显然想听中文原版，而不是标题字面写着拼音的杂项）
                if re.search(r"[\u4e00-\u9fff]", ct):
                    s += 6.0                       # cjk_bonus
                if _kp and _kp in _tp:
                    s += 10.0                      # 整串命中（最理想）
                else:
                    _ws = [w for w in re.split(r'\s+', keyword.lower()) if len(w) >= 2]
                    _hit = sum(1 for w in _ws if re.sub(r'[^a-z0-9]', '', w) in _tp)
                    s += 4.0 * _hit                # 逐词命中
                    if _ws and _hit == 0:
                        s -= 6.0                   # 一个词都没命中 → 明显不相关，重罚
        # ---- 音视频区分：只有【找歌】意图才区分，找演唱会时不区分 ----
        _perf = any(w in keyword.lower() for w in PERF_WORDS)
        if not _perf:
            for w in VIDEO_RIP_WORDS:
                if w in low:
                    s -= 3.5               # 视频抠音轨 → 扣分
                    break
            for w in PURE_AUDIO_WORDS:
                if w in low:
                    s += 3.5               # 纯音频投稿 → 加分
                    break
        s += _fuzzy(ct, keyword) * 6       # 模糊相似度
        if anchor and dur:
            s += 12 * math.exp(-0.06 * abs(dur - anchor))   # 时长锚点
        if long_ok and dur >= 900:
            s += min(6.0, dur / 1800.0)      # 放宽模式下：整场演出(≥15分钟)额外加分
        else:
            s += max(0, 2 - int(dur // 300))
        return (tier, -s)

    scored = [(key(v), v) for v in valid]
    scored.sort(key=lambda x: x[0])        # 档次优先，其次综合分

    out, seen = [], set()
    for _, (_it, _title, _dur) in scored:
        bv = _it["bvid"]
        if bv in seen:
            continue
        seen.add(bv)
        out.append((bv, _title))

    with _clock:
        dead = set(_dead_bvids)

    # 优先未失效的候选
    alive = [c for c in out if c[0] not in dead]
    dead_ones = [c for c in out if c[0] in dead]
    ordered = alive + dead_ones

    if not ordered:
        for it in items:
            if it.get("bvid"):
                log("无合适单曲，退回原始结果")
                ordered = [(it["bvid"], clean(it.get("title")))]
                break

    if not ordered:
        raise RuntimeError("没有搜到结果")

    if out:
        t0 = _title_tier(out[0][1], keyword)
        tag = {0: "原版", 1: "现场", 2: "翻唱/改编", 3: "纯器乐"}.get(t0, "?")
        log("搜索 %r [%s] → %d 个候选(时长锚点%ds)，最佳档次=%d(%s)  首选 %s"
            % (keyword, zone, len(out), anchor, t0, tag, out[0][0]))
    return ordered[:limit]


def parse_ident(ident):
    ident = ident.strip()
    if ident.startswith("http"):
        m = re.search(r"(BV[0-9A-Za-z]{10})", ident)
        if m:
            return "bvid", m.group(1)
        m = re.search(r"av(\d+)", ident, re.I)
        if m:
            return "aid", m.group(1)
        raise RuntimeError("不支持的链接")
    if re.match(r"^BV[0-9A-Za-z]{10}$", ident):
        return "bvid", ident
    if re.match(r"^av\d+$", ident, re.I):
        return "aid", ident[2:]
    if ident.isdigit():
        return "aid", ident
    return "keyword", ident


def _lookup_cid(kind, value):
    """bvid/aid -> (cid, title, bvid)；失败时把该 bvid 记入失效名单"""
    key = value.lower()
    with _clock:
        hit = _cid_cache.get(key)
    if hit:
        return hit
    q = ("bvid=" + value) if kind == "bvid" else ("aid=" + value)
    view = api_get("https://api.bilibili.com/x/web-interface/view?" + q)
    if view.get("code") != 0:
        if kind == "bvid":
            with _clock:
                _dead_bvids.add(value)
        raise RuntimeError("视频不可用: %s" % view.get("message"))
    d = view["data"]
    res = (d["cid"], d.get("title", ""), d.get("bvid", value))
    with _clock:
        _cid_cache[key] = res
        _dead_bvids.discard(value)
    return res


def _resolve_uncached(ident):
    kind, value = parse_ident(ident)
    title = ""

    if kind == "keyword":
        kw = value
        # 注意：_search_cache 存的是 (候选列表, 时间戳) —— 2 元组。
        # 早先误按 3 元组取 sc[2]，导致缓存命中时抛 IndexError（首次点播正常，
        # 15 分钟直链缓存过期后必炸）。加防御，避免同类问题再 500。
        cands = None
        try:
            with _clock:
                sc = _search_cache.get(kw)
            if sc and time.time() - sc[1] < _SEARCH_TTL:
                cands = sc[0]
        except (IndexError, TypeError, KeyError):
            cands = None
        if not cands:
            cands = search_bili_api(kw)
            with _clock:
                _search_cache[kw] = (cands, time.time())

        last = None
        probed = []          # (档次, 码率, bvid, 标题, cid)
        best_t = None
        for bv, ctitle in cands:
            with _clock:
                if bv in _dead_bvids:
                    continue          # 已知失效，省一次 API 调用
            t = _title_tier(ctitle, kw)
            if best_t is not None and t > best_t:
                break                 # 后面档次更差，不用再试
            try:
                cid, real_title, bvid = _lookup_cid("bvid", bv)
            except Exception as e:
                last = e
                continue
            rt = real_title or ctitle
            tt = min(t, _title_tier(rt, kw))
            bw = _probe_audio_bw(bvid, cid)
            if not bw:
                last = RuntimeError("%s 无独立音轨" % bvid)
                continue
            probed.append((tt, bw, bvid, rt, cid))
            best_t = tt if best_t is None else min(best_t, tt)
            if tt == 0 and bw >= BW_GOOD:
                break                 # 已是原版且码率够好，收手
            if len(probed) >= PROBE_N:
                break

        if not probed:
            with _clock:
                _search_cache.pop(kw, None)
            raise RuntimeError("候选视频都不可用: %r" % last)

        probed.sort(key=lambda x: (x[0], -x[1]))   # 档次优先，其次码率
        _tier, _bw, bvid, title, cid = probed[0]
        value, kind = bvid, "bvid"
        log("选用 %s [档次%d %dkbps] %s"
            % (bvid, _tier, _bw // 1000, title[:40]))
        if len(probed) > 1:
            log("  对比过 %d 个候选: %s" % (len(probed),
                " / ".join("%s(%dk)" % (p[2], p[1] // 1000) for p in probed)))
        # 把命中的候选提到最前，下次直接命中
        with _clock:
            _search_cache[kw] = ([(bvid, title)] + [c for c in cands if c[0] != bvid],
                                 time.time())

    else:
        cid, title, bvid = _lookup_cid(kind, value)
        value = bvid

    pu = api_get("https://api.bilibili.com/x/player/playurl"
                 "?bvid=%s&cid=%s&fnval=16&fnver=0&fourk=1" % (value, cid))
    if pu.get("code") != 0:
        raise RuntimeError("取播放地址失败: %s" % pu.get("message"))
    audios = ((pu["data"].get("dash") or {}).get("audio")) or []
    if not audios:
        raise RuntimeError("该视频没有独立音轨")

    def rank(a):
        codec = (a.get("codecs") or "").lower()
        bw = a.get("bandwidth") or 0
        if "flac" in codec:
            return (2, bw)
        if a.get("id") == 30250:
            return (1, bw)
        return (0, bw)

    audios.sort(key=rank)
    pick = audios[-1]
    return ((pick.get("baseUrl") or pick.get("base_url")), title, value,
            (pick.get("codecs") or ""), (pick.get("bandwidth") or 0))


def resolve_audio_url(ident):
    """返回 (直链, 标题, bvid, codec, bandwidth)，带 15 分钟缓存"""
    try:
        with _clock:
            hit = _url_cache.get(ident)
        if hit and time.time() - hit[5] < _URL_TTL:
            return tuple(hit[:5])
    except (IndexError, TypeError):
        hit = None
    res = _resolve_uncached(ident)
    with _clock:
        _url_cache[ident] = tuple(res) + (time.time(),)
    return res


def find_cached(key):
    for ext in (".flac", ".m4a"):
        p = os.path.join(CACHE_DIR, key + ext)
        try:
            if os.path.getsize(p) > 20000:
                return p
        except OSError:
            pass
    return None


def cleanup_cache():
    """淘汰旧缓存；正在下载的 .part 不参与"""
    try:
        with _dl_lock:
            busy = set(d.part for d in _dls.values())
        files = []
        for f in os.listdir(CACHE_DIR):
            if not f.endswith((".m4a", ".flac", ".part")):
                continue
            p = os.path.join(CACHE_DIR, f)
            if p in busy:
                continue
            files.append((os.path.getmtime(p), p))
        total = sum(os.path.getsize(p) for _, p in files) / 1048576.0
        if total <= CACHE_MAX_MB:
            return
        files.sort()
        for _, p in files:
            try:
                os.remove(p)
            except OSError:
                pass
            total -= os.path.getsize(p) / 1048576.0
            if total <= CACHE_MAX_MB * 0.8:
                break
    except Exception as e:
        log("清理缓存出错: %r" % e)


def ensure_mp3(ident, url, title, codec):
    """降级路径：直传不可用时用 ffmpeg 全量下载转封装（v2 老流程）"""
    key = hashlib.md5(ident.encode("utf-8")).hexdigest()[:16]
    if "flac" in (codec or "").lower():
        ext, args = ".flac", ["-c:a", "copy", "-f", "flac"]
    else:
        ext, args = ".m4a", ["-c:a", "copy", "-f", "mp4", "-movflags", "+faststart"]
    out = os.path.join(CACHE_DIR, key + ext)
    meta = os.path.join(CACHE_DIR, key + ".txt")
    tmp = out + ".part"
    cmd = [FFMPEG, "-y", "-loglevel", "error",
           "-user_agent", UA, "-headers", "Referer: %s\r\n" % REFERER,
           "-i", url, "-vn"] + args + [tmp]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if r.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) < 20000:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise RuntimeError("转码失败: %s" % (r.stderr or "")[-150:])
    os.replace(tmp, out)
    open(meta, "w").write(title)
    log("已缓存(ffmpeg降级): %s (%d KB)" % (title, os.path.getsize(out) // 1024))
    cleanup_cache()
    return out, title


# ---------- 渐进式下载 ----------
_dl_lock = threading.Lock()
_dls = {}    # key -> Download
MAX_CONCURRENT = 3   # 同时最多几个后台下载；超出的让路给正在播放的那条


def _evict_readerless(keep):
    """活跃下载过多时，取消最久无人读取的，保证正在播放的那条不被抢带宽"""
    with _dl_lock:
        active = [d for d in _dls.values()
                  if not d.done and d is not keep and not d.cancel]
    if len(active) < MAX_CONCURRENT:
        return
    active.sort(key=lambda d: d.last_read)
    for d in active[:len(active) - MAX_CONCURRENT + 1]:
        if time.time() - d.last_read > 15:
            d.cancel = True
            log("让路：取消无人读取的后台下载 %s (%.1f/%.1f MB)"
                % (d.key, d.ready / 1048576.0,
                   (d.total or 0) / 1048576.0))


class Download:
    """后台拉流写入 .part；读取端通过 cond 边下边读。下满后转正为完整缓存。"""

    MAX_TRY = 5

    def __init__(self, key, url, ext):
        self.key = key
        self.url = url
        self.part = os.path.join(CACHE_DIR, key + ext + ".part")
        self.final = os.path.join(CACHE_DIR, key + ext)
        self.meta = os.path.join(CACHE_DIR, key + ".txt")
        self.cond = threading.Condition()
        # 断点续传：复用上次残留的 .part
        try:
            self.ready = os.path.getsize(self.part)
        except OSError:
            self.ready = 0
        self.total = None
        self.done = False
        self.error = None
        self.cancel = False
        self.last_read = time.time()
        self.t0 = time.time()
        self.thread = threading.Thread(target=self._run, name="dl-" + key, daemon=True)
        self.thread.start()

    def _run(self):
        for attempt in range(1, self.MAX_TRY + 1):
            try:
                h = dict(HEADERS)
                if self.ready > 0:
                    h["Range"] = "bytes=%d-" % self.ready
                with urllib.request.urlopen(
                        urllib.request.Request(self.url, headers=h), timeout=30) as r:
                    status = getattr(r, "status", 200) or 200
                    cl = r.headers.get("Content-Length")
                    cr = r.headers.get("Content-Range")
                    if status == 200 and self.ready > 0:
                        # 上游忽略了 Range → 只能从头下
                        log("上游忽略 Range，从头下载 %s" % self.key)
                        with self.cond:
                            self.ready = 0
                            self.cond.notify_all()
                    new_total = None
                    if cr and "/" in cr:
                        new_total = int(cr.split("/")[-1])
                    elif cl:
                        new_total = self.ready + int(cl)
                    with self.cond:
                        if self.total is None:
                            self.total = new_total
                        self.cond.notify_all()
                    mode = "ab" if self.ready > 0 else "wb"
                    with open(self.part, mode) as f:
                        while True:
                            if self.cancel:
                                raise IOError("已被取消（让路给播放）")
                            chunk = r.read(CHUNK)
                            if not chunk:
                                break
                            f.write(chunk)
                            with self.cond:
                                self.ready += len(chunk)
                                self.cond.notify_all()
                if self.total is not None and self.ready < self.total:
                    raise IOError("上游提前结束 %d/%d 字节" % (self.ready, self.total))
                os.replace(self.part, self.final)
                with self.cond:
                    self.done = True
                    self.cond.notify_all()
                log("下载完成: %s (%.1f MB, %.1fs, 第 %d 次尝试)" % (
                    self.key, self.ready / 1048576.0, time.time() - self.t0, attempt))
                cleanup_cache()
                return
            except Exception as e:
                if self.cancel:
                    with self.cond:
                        self.done = True
                        self.error = e
                        self.cond.notify_all()
                    return
                if attempt < self.MAX_TRY:
                    log("下载中断(%s): %r —— %d 秒后从 %.1f MB 处续传"
                        % (self.key, e, 2 * attempt, self.ready / 1048576.0))
                    time.sleep(2 * attempt)
                    continue
                with self.cond:
                    self.error = e
                    self.done = True
                    self.cond.notify_all()
                log("下载最终失败: %s -> %r（已保留 %.1f MB 供续传/播放）"
                    % (self.key, e, self.ready / 1048576.0))
                return


def get_download(key, url, ext):
    with _dl_lock:
        d = _dls.get(key)
        if d is not None and (d.done or d.error is not None):
            # 已结束的任务：仅当成品文件仍在时才可复用；
            # 否则（下载失败 / 缓存已被淘汰）必须重开，否则会发出 0 字节。
            if d.error is not None or not os.path.exists(d.final):
                d = None
        if d is None:
            d = Download(key, url, ext)
            _dls[key] = d
            _evict_readerless(d)
        return d


# ---------- HTTP ----------
class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    # 透传模式下的上游重试次数


    def log_message(self, fmt, *a):
        try:
            log("[proxy] " + (fmt % a))
        except Exception:
            pass

    # -- 工具 --
    def _json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except Exception:
                pass

    def fail(self, msg, code=500):
        body = msg.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    @staticmethod
    def _parse_range(header, total):
        if not header:
            return (0, total - 1, False)
        m = re.match(r"bytes=(\d*)-(\d*)", header.strip())
        if not m:
            return (0, total - 1, False)
        a, b = m.group(1), m.group(2)
        if a:
            start = int(a)
            end = int(b) if b else total - 1
        elif b:
            start = max(0, total - int(b))
            end = total - 1
        else:
            return (0, total - 1, False)
        return (start, min(end, total - 1), True)

    def _serve_file(self, fp, head_only):
        """完整缓存：直接走磁盘（毫秒级）"""
        size = os.path.getsize(fp)
        start, end, partial = self._parse_range(self.headers.get("Range"), size)
        if start >= size:
            self.send_response(416)
            self.send_header("Content-Range", "bytes */%d" % size)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        length = end - start + 1
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type",
                         "audio/flac" if fp.endswith(".flac") else "audio/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if partial:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        if head_only:
            return
        try:
            with open(fp, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(CHUNK, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    MAX_UPSTREAM_TRY = 4

    def _stream_through(self, url, ext, head_only):
        """边播边释放：把上游字节流直接转发给客户端，不落盘。
        上游中途断流时，按已发偏移发 Range 续传，尽量让音乐不断。"""
        client_range = self.headers.get("Range")
        ctype = "audio/flac" if ext == ".flac" else "audio/mp4"
        body_sent = 0
        started = False
        expect = None          # 本次会话应有的总字节数（用于判断是否被截断）
        t0 = time.time()

        for attempt in range(1, self.MAX_UPSTREAM_TRY + 1):
            h = dict(HEADERS)
            if body_sent > 0:
                h["Range"] = "bytes=%d-" % body_sent
            elif client_range:
                h["Range"] = client_range
            try:
                r = urllib.request.urlopen(
                    urllib.request.Request(url, headers=h), timeout=30)
            except Exception as e:
                if not started:
                    return self.fail("上游取流失败: %r" % e)
                log("上游重连失败(%d/%d): %r" % (attempt, self.MAX_UPSTREAM_TRY, e))
                time.sleep(min(2 * attempt, 6))
                continue

            clean = False
            try:
                if not started:
                    status = getattr(r, "status", 200) or 200
                    cl = r.headers.get("Content-Length")
                    cr = r.headers.get("Content-Range")
                    # 注意：expect 必须是"上游本次会发多少字节"，
                    # 而不是 Content-Range 里的总长度 —— 否则客户端请求
                    # 有界区间(如 bytes=0-65535)时会被误判成"被截断"。
                    if cr and "/" in cr:
                        try:
                            a, b = cr.replace("bytes", "").strip().split("/")[0].split("-")
                            expect = int(b) + 1
                        except (ValueError, IndexError):
                            expect = None
                    elif cl:
                        try:
                            expect = body_sent + int(cl)
                        except ValueError:
                            expect = None
                    self.send_response(status)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Accept-Ranges", "bytes")
                    if cr:
                        self.send_header("Content-Range", cr)
                    if cl:
                        self.send_header("Content-Length", cl)
                    self.end_headers()
                    started = True
                    if head_only:
                        return
                while True:
                    chunk = r.read(CHUNK)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    body_sent += len(chunk)
                clean = True
            except (BrokenPipeError, ConnectionResetError):
                log("客户端断开（透传结束，已发 %.1f MB）" % (body_sent / 1048576.0))
                return
            except Exception as e:
                log("上游读取中断(%d/%d, 已发 %.1f MB): %r"
                    % (attempt, self.MAX_UPSTREAM_TRY, body_sent / 1048576.0, e))
            finally:
                try:
                    r.close()
                except Exception:
                    pass

            if clean and (expect is None or body_sent >= expect):
                el = time.time() - t0
                if body_sent:
                    log("透传完成: %.1f MB / %.2fs (%.0f KB/s)"
                        % (body_sent / 1048576.0, el, body_sent / 1024.0 / max(el, 0.001)))
                return
            if expect is not None and body_sent >= expect:
                return
            if attempt < self.MAX_UPSTREAM_TRY:
                log("上游截断，从 %.1f MB 处续传…" % (body_sent / 1048576.0))
                time.sleep(min(attempt, 3))

        log("透传最终失败（已发 %.1f MB）" % (body_sent / 1048576.0))

    def _copy_upstream(self, url, start, end):
        """（响应头已发）把 [start,end] 区间从上游拷到客户端"""
        h = dict(HEADERS)
        h["Range"] = "bytes=%d-%d" % (start, end)
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30)
        except Exception as e:
            log("上游转发失败: %r" % e)
            return
        left = end - start + 1
        try:
            while left > 0:
                chunk = r.read(min(CHUNK, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            r.close()

    def _proxy_range(self, url, start, end, total, ext, head_only):
        """本地还没下到该区间 → 直接向B站 CDN 转发 Range（seek 秒级）"""
        self.send_response(206)
        self.send_header("Content-Type",
                         "audio/flac" if ext == ".flac" else "audio/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, total))
        self.end_headers()
        if head_only:
            return
        self._copy_upstream(url, start, end)

    def _stream_progressive(self, dl, start, end, total, partial, ext, head_only):
        """核心：边下边播 —— 数据还在落盘，这里同步往下发"""
        length = end - start + 1
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type",
                         "audio/flac" if ext == ".flac" else "audio/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if partial:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, total))
        self.end_headers()
        if head_only:
            return

        pos, f, sent, t0 = start, None, 0, time.time()
        try:
            while pos <= end:
                with dl.cond:
                    while dl.ready <= pos and not dl.done and dl.error is None:
                        dl.cond.wait(0.5)
                    avail, err = dl.ready, dl.error
                if pos >= avail:
                    if err is not None and pos <= end:
                        log("上游中断，余下 %.1f MB 改走 CDN 转发"
                            % ((end - pos + 1) / 1048576.0))
                        self._copy_upstream(dl.url, pos, end)
                        sent += max(0, end - pos + 1)
                    break
                if f is None:
                    for cand in (dl.part, dl.final):
                        try:
                            f = open(cand, "rb")
                            break
                        except OSError:
                            continue
                    if f is None:
                        break
                f.seek(pos)
                chunk = f.read(min(end - pos + 1, avail - pos, CHUNK))
                if not chunk:
                    time.sleep(0.02)
                    continue
                dl.last_read = time.time()
                self.wfile.write(chunk)
                pos += len(chunk)
                sent += len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            log("客户端提前断开（后台继续缓存到磁盘）")
        except Exception as e:
            log("发送出错: %r" % e)
        finally:
            if f is not None:
                try:
                    f.close()
                except Exception:
                    pass
        el = time.time() - t0
        if sent and el > 0.05:
            log("流式发送: %.1f MB / %.2fs (%.0f KB/s)"
                % (sent / 1048576.0, el, sent / 1024.0 / el))

    def _stream_unknown(self, dl, head_only):
        """罕见：上游无 Content-Length 时退化为 close 分隔"""
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "audio/mp4")
        self.send_header("Connection", "close")
        self.end_headers()
        if head_only:
            return
        pos = 0
        while True:
            with dl.cond:
                while dl.ready <= pos and not dl.done and dl.error is None:
                    dl.cond.wait(0.5)
                avail = dl.ready
            if pos >= avail:
                break
            try:
                with open(dl.part, "rb") as f:
                    f.seek(pos)
                    chunk = f.read(avail - pos)
                self.wfile.write(chunk)
                pos += len(chunk)
            except (BrokenPipeError, ConnectionResetError, OSError):
                break

    # -- 路由 --
    def do_HEAD(self):
        self._serve(head_only=True)

    def do_GET(self):
        self._serve(head_only=False)

    def _serve(self, head_only):
        global _stat_req, _stat_stream
        _stat_req += 1
        path = urllib.parse.unquote(self.path.split("?", 1)[0].lstrip("/"))

        if path in ("health", "healthz"):
            with _dl_lock:
                active = sum(1 for d in _dls.values() if not d.done)
            return self._json({"ok": True, "uptime": int(time.time() - _stat_start),
                               "requests": _stat_req, "active_downloads": active})

        if path == "status":
            with _dl_lock:
                dls = [{"key": d.key, "ready_mb": round(d.ready / 1048576.0, 1),
                        "total_mb": round(d.total / 1048576.0, 1) if d.total else None,
                        "done": d.done, "err": str(d.error) if d.error else None}
                       for d in _dls.values()]
            return self._json({"uptime": int(time.time() - _stat_start),
                               "requests": _stat_req, "streams": _stat_stream,
                               "resolve_cache": {"url": len(_url_cache), "cid": len(_cid_cache)},
                               "downloads": dls})

        if path.startswith("b/") or path.startswith("s/"):
            ident = path[2:]
        else:
            return self.fail("用法: /b/<BV号|av号|链接> 或 /s/<关键词>", 404)
        if not ident.strip():
            return self.fail("缺少参数", 400)

        key = hashlib.md5(ident.encode("utf-8")).hexdigest()[:16]

        # ① 完整缓存命中（仅落盘模式）
        if MODE == "cache":
            fp = find_cached(key)
            if fp:
                return self._serve_file(fp, head_only)

        # ② 解析直链
        try:
            url, title, bvid, codec, bw = resolve_audio_url(ident)
        except Exception as e:
            log("解析失败: %r" % e)
            return self.fail(str(e))

        log("音源: %s | %.0f kbps | %s" % (title, bw / 1000.0, codec))
        ext = ".flac" if "flac" in (codec or "").lower() else ".m4a"

        # ② 边播边释放：纯透传，不落盘（默认）
        if MODE != "cache":
            _stat_stream += 1
            return self._stream_through(url, ext, head_only)

        dl = get_download(key, url, ext)
        _stat_stream += 1

        # ③ 等上游给出总长度（通常 <1s）—— 才能发精确 Content-Length 并支持 Range
        t0 = time.time()
        with dl.cond:
            while (dl.total is None and dl.error is None and not dl.done
                   and time.time() - t0 < 20):
                dl.cond.wait(0.5)
            total, err = dl.total, dl.error

        # 直传早期失败 → 退回 ffmpeg 全量下载（老流程，保证能播）
        if err is not None and dl.ready < 20000:
            log("直传失败，降级 ffmpeg: %r" % err)
            with _dl_lock:
                _dls.pop(key, None)
            try:
                fp, title = ensure_mp3(ident, url, title, codec)
            except Exception as e2:
                return self.fail(str(e2))
            return self._serve_file(fp, head_only)

        if total is None:
            return self._stream_unknown(dl, head_only)

        start, end, partial = self._parse_range(self.headers.get("Range"), total)
        if start > end:
            self.send_response(416)
            self.send_header("Content-Range", "bytes */%d" % total)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        # ④ 远距离 seek 且本地没下到 → 向 CDN 转发 Range
        if partial and start > dl.ready + CHUNK and dl.ready < total:
            log("转发 Range %d-%d（本地仅 %d）" % (start, end, dl.ready))
            return self._proxy_range(url, start, end, total, ext, head_only)

        return self._stream_progressive(dl, start, end, total, partial, ext, head_only)


class S(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 32

    def handle_error(self, request, client_address):
        import sys as _sys
        if isinstance(_sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


if __name__ == "__main__":
    if PURGE_ON_START:
        freed = 0
        try:
            for f in os.listdir(CACHE_DIR):
                if f.endswith((".m4a", ".flac", ".part", ".txt")):
                    p = os.path.join(CACHE_DIR, f)
                    try:
                        freed += os.path.getsize(p)
                        os.remove(p)
                    except OSError:
                        pass
        except OSError:
            pass
        if freed:
            log("已清理历史缓存 %.1f MB（stream 模式不在本地留文件）" % (freed / 1048576.0))
    log("B站音频代理 v6 启动，模式=%s，端口 %d，requests=%s，缓存目录=%s"
        % (MODE, PORT, HAVE_REQ, CACHE_DIR))
    S(("127.0.0.1", PORT), H).serve_forever()
