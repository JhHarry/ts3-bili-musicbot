#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ──────────────────────────────────────────────────────────────────────────
# 算法依据 ISO/IEC 18004；实现参考了公开参考实现所采用的标准参数表：
#   Nayuki QR Code     MIT          https://www.nayuki.io/page/qr-code-generator-library
#   完整清单与许可证全文见仓库根目录 THIRD_PARTY_NOTICES.md
# ──────────────────────────────────────────────────────────────────────────

"""
qrmini —— 极简 QR 码生成器（零依赖，纯标准库）

为什么自己写：
    扫码登录要的是「把一段 URL 变成能扫的图」。系统里有 qrencode 当然好，
    但很多精简容器 / 干净服务器上并没有，而为了一个二维码去装一堆图像库
    很划不来。本模块用纯 Python + zlib 直接吐出 PNG，也顺手能画终端字符版。

支持：
    * 字节模式（UTF-8 自动编码），版本 1~40 自动选择
    * 纠错等级 L / M / Q / H
    * 自动掩膜（8 种按标准罚分择优）
    * 输出 PNG（灰度高对比，任意倍数缩放 + 静默边）
    * 输出终端 UTF-8 / ANSI 字符画

算法依据 ISO/IEC 18004:2015（QR Code Model 2），实现参考了 Nayuki 的
公开参考实现（MIT License）所采用的标准参数表与流程。
"""

import zlib

# ---------------------------------------------------------------- 标准参数表

# 各纠错等级下、每个分组的纠错码字数（索引 0 占位，版本 1~40）
ECC_CODEWORDS_PER_BLOCK = (
    # L
    (-1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28,
     28, 28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    # M
    (-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26,
     26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28),
    # Q
    (-1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26,
     30, 28, 30, 30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    # H
    (-1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26,
     28, 30, 24, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
)

# 各纠错等级下的分组数
NUM_ERROR_CORRECTION_BLOCKS = (
    # L
    (-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7,
     8, 8, 9, 9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25),
    # M
    (-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14,
     16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49),
    # Q
    (-1, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8, 8, 10, 12, 16, 12, 17, 16, 18, 21,
     20, 23, 23, 25, 27, 29, 34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68),
    # H
    (-1, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25,
     25, 25, 34, 30, 32, 35, 37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 74, 77, 81),
)

LEVELS = {"L": 0, "M": 1, "Q": 2, "H": 3}
# 格式信息里用的纠错等级编码
LEVEL_FORMAT_BITS = {0: 1, 1: 0, 2: 3, 3: 2}


def raw_data_modules(ver):
    """该版本可用的原始数据模块数（bit）"""
    result = (16 * ver + 128) * ver + 64
    if ver >= 2:
        numalign = ver // 7 + 2
        result -= (25 * numalign - 10) * numalign - 55
        if ver >= 7:
            result -= 36
    return result


def data_codewords(ver, lvl):
    """该版本 + 纠错等级下的数据码字数（byte）"""
    return (raw_data_modules(ver) // 8
            - ECC_CODEWORDS_PER_BLOCK[lvl][ver] * NUM_ERROR_CORRECTION_BLOCKS[lvl][ver])


# ---------------------------------------------------------------- GF(256) 运算

def _gf_mul(x, y):
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z & 0xFF


def _rs_divisor(degree):
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 0x02)
    return result


def _rs_remainder(data, divisor):
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _gf_mul(coef, factor)
    return result


# ---------------------------------------------------------------- 编码

def _append_bits(bb, val, length):
    for i in range(length - 1, -1, -1):
        bb.append((val >> i) & 1)


def encode_to_codewords(payload, lvl):
    """返回 (version, 全部码字列表)"""
    data = payload.encode("utf-8")

    ver = 1
    while True:
        cap = data_codewords(ver, lvl) * 8
        cci = 8 if ver <= 9 else 16
        if 4 + cci + 8 * len(data) <= cap:
            break
        ver += 1
        if ver > 40:
            raise ValueError("内容太长，超出 QR 版本 40 的容量")

    bb = []
    _append_bits(bb, 0b0100, 4)                    # 字节模式
    _append_bits(bb, len(data), 8 if ver <= 9 else 16)
    for b in data:
        _append_bits(bb, b, 8)

    cap = data_codewords(ver, lvl) * 8
    _append_bits(bb, 0, min(4, cap - len(bb)))     # 终止符
    _append_bits(bb, 0, (-len(bb)) % 8)            # 补齐到字节边界
    pad = 0
    while len(bb) < cap:
        _append_bits(bb, 0xEC if pad % 2 == 0 else 0x11, 8)
        pad += 1

    datacw = [int("".join(str(b) for b in bb[i:i + 8]), 2) for i in range(0, len(bb), 8)]

    # ── 分块 + 纠错
    numblocks = NUM_ERROR_CORRECTION_BLOCKS[lvl][ver]
    blockecclen = ECC_CODEWORDS_PER_BLOCK[lvl][ver]
    rawcw = raw_data_modules(ver) // 8
    numshort = numblocks - rawcw % numblocks
    shortlen = rawcw // numblocks

    blocks = []
    k = 0
    for i in range(numblocks):
        datlen = shortlen - blockecclen + (0 if i < numshort else 1)
        d = datacw[k:k + datlen]
        k += datlen
        ecc = _rs_remainder(d, _rs_divisor(blockecclen))
        if i < numshort:
            d = d + [0]
        blocks.append(d + ecc)

    # ── 交织
    result = []
    for i in range(len(blocks[0])):
        for j, blk in enumerate(blocks):
            if i != shortlen - blockecclen or j >= numshort:
                result.append(blk[i])
    return ver, result


# ---------------------------------------------------------------- 画模块

class _Grid:
    def __init__(self, ver, lvl):
        self.ver = ver
        self.lvl = lvl
        self.size = ver * 4 + 17
        self.m = [[False] * self.size for _ in range(self.size)]
        self.fn = [[False] * self.size for _ in range(self.size)]

    def set_fn(self, x, y, dark):
        self.m[y][x] = dark
        self.fn[y][x] = True

    def draw_finder(self, cx, cy):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < self.size and 0 <= y < self.size:
                    dist = max(abs(dx), abs(dy))
                    self.set_fn(x, y, dist != 2 and dist != 4)

    def draw_alignment(self, cx, cy):
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                self.set_fn(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)

    def alignment_positions(self):
        if self.ver == 1:
            return []
        n = self.ver // 7 + 2
        step = 26 if self.ver == 32 else (self.ver * 4 + n * 2 + 1) // (n * 2 - 2) * 2
        res = [6]
        pos = self.size - 7
        for _ in range(n - 1):
            res.insert(1, pos)
            pos -= step
        return res

    def draw_function_patterns(self):
        for i in range(self.size):
            self.set_fn(6, i, i % 2 == 0)
            self.set_fn(i, 6, i % 2 == 0)
        self.draw_finder(3, 3)
        self.draw_finder(self.size - 4, 3)
        self.draw_finder(3, self.size - 4)

        pos = self.alignment_positions()
        for i, x in enumerate(pos):
            for j, y in enumerate(pos):
                if (i == 0 and j == 0) or (i == 0 and j == len(pos) - 1) \
                        or (i == len(pos) - 1 and j == 0):
                    continue
                self.draw_alignment(x, y)

        self.reserve_format()
        self.draw_version_bits()

    def reserve_format(self):
        """先把格式信息区占位为浅色。

        掩膜选择时要按标准算罚分，而格式信息本身是【掩膜之后】才写入的，
        所以评估阶段这些模块按浅色处理（libqrencode / zxing 均如此，
        这样本实现与 qrencode 的输出可以逐位对齐）。
        """
        for i in range(6):
            self.set_fn(8, i, False)
        self.set_fn(8, 7, False)
        self.set_fn(8, 8, False)
        self.set_fn(7, 8, False)
        for i in range(9, 15):
            self.set_fn(14 - i, 8, False)
        for i in range(8):
            self.set_fn(self.size - 1 - i, 8, False)
        for i in range(8, 15):
            self.set_fn(8, self.size - 15 + i, False)
        self.set_fn(8, self.size - 8, False)

    def draw_format_bits(self, mask):
        data = LEVEL_FORMAT_BITS[self.lvl] << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412

        def bit(i):
            return ((bits >> i) & 1) != 0

        for i in range(6):
            self.set_fn(8, i, bit(i))
        self.set_fn(8, 7, bit(6))
        self.set_fn(8, 8, bit(7))
        self.set_fn(7, 8, bit(8))
        for i in range(9, 15):
            self.set_fn(14 - i, 8, bit(i))

        for i in range(8):
            self.set_fn(self.size - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.set_fn(8, self.size - 15 + i, bit(i))
        self.set_fn(8, self.size - 8, True)

    def draw_version_bits(self):
        if self.ver < 7:
            return
        rem = self.ver
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = self.ver << 12 | rem
        for i in range(18):
            b = ((bits >> i) & 1) != 0
            a = self.size - 11 + i % 3
            bb = i // 3
            self.set_fn(a, bb, b)
            self.set_fn(bb, a, b)

    def draw_codewords(self, cw):
        i = 0
        right = self.size - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(self.size):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = (self.size - 1 - vert) if upward else vert
                    if not self.fn[y][x] and i < len(cw) * 8:
                        self.m[y][x] = ((cw[i >> 3] >> (7 - (i & 7))) & 1) != 0
                        i += 1
            right -= 2

    def apply_mask(self, mask):
        for y in range(self.size):
            for x in range(self.size):
                if self.fn[y][x]:
                    continue
                invert = False
                if mask == 0:
                    invert = (x + y) % 2 == 0
                elif mask == 1:
                    invert = y % 2 == 0
                elif mask == 2:
                    invert = x % 3 == 0
                elif mask == 3:
                    invert = (x + y) % 3 == 0
                elif mask == 4:
                    invert = (x // 3 + y // 2) % 2 == 0
                elif mask == 5:
                    invert = x * y % 2 + x * y % 3 == 0
                elif mask == 6:
                    invert = (x * y % 2 + x * y % 3) % 2 == 0
                elif mask == 7:
                    invert = ((x + y) % 2 + x * y % 3) % 2 == 0
                if invert:
                    self.m[y][x] = not self.m[y][x]

    # ── 罚分（标准 4 条规则）
    def _add_history(self, run, hist):
        if hist[0] == 0:
            run += self.size
        hist.insert(0, run)
        hist.pop()

    def _count_patterns(self, hist):
        n = hist[1]
        core = (n > 0 and hist[2] == hist[4] == hist[5] == n and hist[3] == n * 3)
        return ((1 if (core and hist[0] >= n * 4 and hist[6] >= n) else 0)
                + (1 if (core and hist[6] >= n * 4 and hist[0] >= n) else 0))

    def _terminate(self, color, run, hist):
        if color:
            self._add_history(run, hist)
            run = 0
        run += self.size
        self._add_history(run, hist)
        return self._count_patterns(hist)

    def penalty(self):
        size, m = self.size, self.m
        result = 0
        for y in range(size):
            color, run, hist = False, 0, [0] * 7
            for x in range(size):
                if m[y][x] == color:
                    run += 1
                    if run == 5:
                        result += 3
                    elif run > 5:
                        result += 1
                else:
                    self._add_history(run, hist)
                    if not color:
                        result += self._count_patterns(hist) * 40
                    color, run = m[y][x], 1
            result += self._terminate(color, run, hist) * 40
        for x in range(size):
            color, run, hist = False, 0, [0] * 7
            for y in range(size):
                if m[y][x] == color:
                    run += 1
                    if run == 5:
                        result += 3
                    elif run > 5:
                        result += 1
                else:
                    self._add_history(run, hist)
                    if not color:
                        result += self._count_patterns(hist) * 40
                    color, run = m[y][x], 1
            result += self._terminate(color, run, hist) * 40
        for y in range(size - 1):
            for x in range(size - 1):
                c = m[y][x]
                if c == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    result += 3
        dark = sum(row.count(True) for row in m)
        total = size * size
        k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
        result += k * 10
        return result


def make_matrix(payload, level="M"):
    """生成 QR 模块矩阵：True = 黑。返回 (矩阵, 版本号)"""
    lvl = LEVELS[level.upper()]
    ver, cw = encode_to_codewords(payload, lvl)

    best = None
    for mask in range(8):
        g = _Grid(ver, lvl)
        g.draw_function_patterns()
        g.draw_codewords(cw)
        g.apply_mask(mask)
        g.draw_format_bits(mask)
        p = g.penalty()                # 按标准：评估时包含格式信息
        if best is None or p < best[0]:
            best = (p, g, mask)
    return best[1].m, ver


# ---------------------------------------------------------------- 输出

def write_png(matrix, path, scale=8, border=4):
    """把矩阵写成灰度 PNG（黑模块=0，白=255）。纯 zlib，无第三方库。"""
    n = len(matrix)
    dim = (n + border * 2) * scale
    rows = bytearray()
    for py in range(dim):
        rows.append(0)                       # 每行 filter type = 0
        my = py // scale - border
        for px in range(dim):
            mx = px // scale - border
            dark = (0 <= mx < n and 0 <= my < n and matrix[my][mx])
            rows.append(0 if dark else 255)

    def chunk(tag, data):
        out = len(data).to_bytes(4, "big") + tag + data
        return out + (zlib.crc32(tag + data) & 0xFFFFFFFF).to_bytes(4, "big")

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", dim.to_bytes(4, "big") + dim.to_bytes(4, "big")
                 + bytes([8, 0, 0, 0, 0]))    # 8bit 灰度 / 无压缩 / 无隔行
    png += chunk(b"IDAT", zlib.compress(bytes(rows), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    return path


def to_terminal(matrix, mode="ANSIUTF8", border=2):
    """把矩阵画成终端字符（每个字符代表上下两个模块）。

    qrencode 的经验：终端背景多为深色，所以【浅色模块画成亮块】。
    ANSIUTF8 会显式设置前景/背景色，因此在明暗主题下都不会反相。
    """
    n = len(matrix)
    pad = [[False] * (n + border * 2) for _ in range(border)]
    grid = pad + [[False] * border + row + [False] * border for row in matrix] + pad
    if len(grid) % 2:
        grid.append([False] * len(grid[0]))

    lines = []
    for y in range(0, len(grid), 2):
        top, bot = grid[y], grid[y + 1]
        chars = []
        for x in range(len(top)):
            t = 1 if top[x] else 0          # 1=黑
            b = 1 if bot[x] else 0
            # 反相显示：黑模块用空格，白模块用亮块
            if t and b:
                chars.append(" ")
            elif t and not b:
                chars.append("\u2584")      # 下半亮
            elif not t and b:
                chars.append("\u2580")      # 上半亮
            else:
                chars.append("\u2588")      # 全亮
        line = "".join(chars)
        lines.append("\x1b[40;37;1m" + line + "\x1b[0m" if mode == "ANSIUTF8" else line)
    return "\n".join(lines)


def to_ascii(matrix, border=2):
    """最朴素的 ██ / 空格 版本（任何终端都能显示）"""
    n = len(matrix)
    out = []
    for _ in range(border):
        out.append("  " * (n + border * 2))
    for row in matrix:
        out.append("  " * border + "".join("  " if c else "\u2588\u2588" for c in row)
                   + "  " * border)
    for _ in range(border):
        out.append("  " * (n + border * 2))
    return "\n".join(out)
