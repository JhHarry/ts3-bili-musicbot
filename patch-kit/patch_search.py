#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ──────────────────────────────────────────────────────────────────────────
# 补丁对象（本仓库自研的选源逻辑，与上游无关）
#   yt-dlp             Unlicense    https://github.com/yt-dlp/yt-dlp
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

"""优化 bili_proxy.py 的选源逻辑：
   1) 按「原版 > 现场 > 翻唱/改编 > 纯器乐」分档，原版优先
   2) 同档内按音频码率择优（不再盲选第一个）
   3) 搜索接口 412 限流自动退避重试
用法: python3 patch_search.py /opt/ts3bot/bili_proxy.py
"""
import sys, os, re, shutil, time

path = sys.argv[1] if len(sys.argv) > 1 else "/opt/ts3bot/bili_proxy.py"
src = open(path, encoding="utf-8").read()
orig = src

# ============ 1. 词表：分档用的关键词 ============
OLD_WORDS = '''LONG_WORDS = ["演唱会", "现场", "专辑", "全场", "音乐会", "纯享",
              "live", "concert", "album", "巡演", "大电影"]'''

NEW_WORDS = '''LONG_WORDS = ["演唱会", "现场", "专辑", "全场", "音乐会", "纯享",
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
                    "教学", "教程", "教你", "谱子", "零基础", "翻弹"]
ALTER_WORDS = ["remix", "混音", "电音", "dj版", "加速", "慢速", "变速", "二创",
               "调教", "音mad", "0.8x", "1.25x", "1.5x", "0.9x", "2.0x",
               "8d", "环绕", "reaction", "反应", "解析", "讲解", "测评",
               "盘点", "倒数第一", "mashup", "缝合", "搞笑", "沙雕",
               "恶搞", "玩梗"]
LIVE_WORDS = ["现场", "演唱会", "全场", "音乐会", "live", "concert",
              "巡演", "不插电", "unplugged", "现场版"]
ORIGINAL_HINTS = ["原版", "原声", "官方", "official", "mv",
                  "高清", "无损", "hi-res", "hires", "flac", "完整版",
                  "正版", "专辑版", "经典", "首发", "正式版", "高质量"]

# 码率择优：同档次内最多多试几个候选；够好就收手（避免拖慢点歌）
PROBE_N = 4
BW_GOOD = 160000        # 已是原版且达到这个码率，就不再比了

# 搜索范围：优先在 B站【音乐区】里找，避开鬼畜/剪辑/访谈等非音乐内容
MUSIC_TID = 3           # 3 = 音乐区（含 原创音乐28/翻唱31/演奏59/MV193/现场29 等子分区）
MIN_MUSIC_HITS = 3      # 音乐区结果少于这个数就回退全区搜索'''

assert OLD_WORDS in src, "词表锚点未找到"
src = src.replace(OLD_WORDS, NEW_WORDS, 1)

# ============ 2. 新增：分档函数 + 码率探测 ============
ANCHOR2 = "_SEARCH_TTL = 10 * 60\n"
NEW_FUNCS = ANCHOR2 + r'''

# ---------- 选源：分档 + 码率 ----------
_bw_cache = {}      # bvid -> 最大音频码率(bps)，同一视频码率不会变


def _title_tier(title, keyword=""):
    """判断候选属于哪个档次。0=原版 1=现场 2=翻唱/改编 3=纯器乐/伴奏/教学。
    如果【用户自己搜的就是这一类】（例如自己找伴奏版），该类不再降级。"""
    t = (title or "").lower()
    kw = (keyword or "").lower()

    def hit(words):
        for w in words:
            if w in t and w not in kw:
                return True
        return False

    if hit(INSTRUMENT_WORDS):
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
'''
assert ANCHOR2 in src, "_SEARCH_TTL 锚点未找到"
src = src.replace(ANCHOR2, NEW_FUNCS, 1)

# ============ 3. 重写 search_bili_api ============
NEW_SEARCH = r'''def search_bili_api(keyword, limit=6):
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
        if dur and dur < 25:
            continue          # 太短的片段
        valid.append((it, title, dur))

    # ---- 时长锚点：候选时长中位数 ≈ 这首歌的真实长度 ----
    durs = sorted(d for _, _, d in valid if d)
    anchor = durs[len(durs) // 2] if durs else 0

    # ---- 第二遍：分档 + 打分 ----
    def key(v):
        _it, title, dur = v
        tier = _title_tier(title, keyword)
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
                s += 2                     # 原版/官方/Hi-Res 这类线索加分
                break
        s += _fuzzy(ct, keyword) * 6       # 模糊相似度
        if anchor and dur:
            s += 12 * math.exp(-0.06 * abs(dur - anchor))   # 时长锚点
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
'''

p1 = src.index("def search_bili_api(keyword, limit=6):")
p2 = src.index("    return ordered[:limit]\n", p1) + len("    return ordered[:limit]\n")
src = src[:p1] + NEW_SEARCH + src[p2:]

# ============ 4. 重写候选选取：先分档，再比码率 ============
NEW_PICK = '''        last = None
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
'''

s1 = src.index("        last = None\n        for i, (bv, ctitle) in enumerate(cands):")
END_MARK = '            raise RuntimeError("候选视频都不可用: %r" % last)\n'
s2 = src.index(END_MARK, s1) + len(END_MARK)
src = src[:s1] + NEW_PICK + src[s2:]

# ============ 5. api_get 增加 412 退避重试 ============
NEW_APIGET = '''def api_get(url, _retry=0):
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
'''

a1 = src.index("def api_get(url):")
a2 = src.index("timeout=15))\n", a1) + len("timeout=15))\n")
src = src[:a1] + NEW_APIGET + src[a2:]

# ============ 写回 ============
if src == orig:
    print("!! 没有任何改动")
    sys.exit(1)

bak = path + ".bak-search"
if not os.path.exists(bak):
    shutil.copy2(path, bak)
    print("  备份 -> %s" % bak)

open(path, "w", encoding="utf-8").write(src)
print("  已写入 %s（%d -> %d 字节）" % (path, len(orig), len(src)))

# 自检
import py_compile
py_compile.compile(path, doraise=True)
print("  ✅ 语法检查通过")
for name in ("_title_tier", "_probe_audio_bw", "BW_GOOD", "PROBE_N",
             "COVER_WORDS", "INSTRUMENT_WORDS"):
    assert name in src, "缺少 %s" % name
print("  ✅ 新增符号齐全")
# 版本标识 v4 -> v5
with open(path, encoding="utf-8") as f:
    _t = f.read()
if "B站音频代理 v4" in _t:
    open(path, "w", encoding="utf-8").write(_t.replace("B站音频代理 v4", "B站音频代理 v6"))
    print("  ✅ 版本标识 → v5")
