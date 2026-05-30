# tft_test_tool.py — TFT 螢幕測試工具集
# 透過 TFT library 統一接口操作，驗證 lib/TFT.py 正確性
#
# 用法:
#   import tft_test_tool
#   tft_test_tool.config(240, 536)    # 手動設解析度 (選填)
#   tft_test_tool.fill_colors()
#   tft_test_tool.fps_test()

import gc, time, math, random
from lib.sys_bus import bus

# ═══ 內部狀態 ═══
_lcd = None
_w = 240
_h = 320
_manual_w = 0
_manual_h = 0

def config(width=0, height=0):
    """設定螢幕解析度。不傳參則從 bus 讀取"""
    global _manual_w, _manual_h
    _manual_w = width
    _manual_h = height

def _setup():
    global _lcd, _w, _h
    if _lcd is None:
        _lcd = bus.get_service("lcd")
        if _lcd is None:
            raise RuntimeError("LCD not on bus — did boot.py run?")
    if _manual_w and _manual_h:
        _w = _manual_w
        _h = _manual_h
    else:
        _w = int(bus.shared.get("tft_width", 240))
        _h = int(bus.shared.get("tft_height", 536))

def _color(r, g, b):
    """RGB 888 → RGB565 大端"""
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)

def _color_le(r, g, b):
    """RGB 888 → RGB565 小端"""
    c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return (c >> 8) | (c << 8)

def _hsv(h, s=100, v=100):
    """HSV → RGB565"""
    h = float(h % 360) / 60.0
    s, v = s / 100.0, v / 100.0
    i = int(h); f = h - i
    p = v * (1 - s); q = v * (1 - s * f); t = v * (1 - s * (1 - f))
    r, g, b = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i]
    return ((int(r * 31) & 0x1F) << 11) | ((int(g * 63) & 0x3F) << 5) | (int(b * 31) & 0x1F)

def _write_solid(color565):
    """全螢幕填色 — 透過 TFT._bus 層零大分配寫入"""
    chunk = bytearray(8192)
    for i in range(4096):
        chunk[i * 2] = color565 >> 8
        chunk[i * 2 + 1] = color565 & 0xFF
    total = _w * _h
    mv = memoryview(chunk)
    written = 0
    while written < total:
        n = min(total - written, 4096)
        hn = _lcd._bus.write_data_async(mv[:n * 2])
        if hn is not None: _lcd._bus.wait(hn)
        written += n
    _lcd._bus.flush()

def _clear():
    _lcd.set_window(0, 0, _w - 1, _h - 1)
    _write_solid(0x0000)

# ══════════════════════════════════════════════════════════════
#  公開測試 API
# ══════════════════════════════════════════════════════════════

def fill_colors():
    """九色全螢幕填滿 — 透過 TFT 接口"""
    _setup()
    gc.collect()
    colors = [
        ("RED",    0xF800), ("GREEN",  0x07E0), ("BLUE",   0x001F),
        ("YELLOW", 0xFFE0), ("CYAN",   0x07FF), ("MAGENTA",0xF81F),
        ("WHITE",  0xFFFF), ("GRAY",   0x8410), ("BLACK",  0x0000),
    ]
    for name, c in colors:
        print("  %s (0x%04X) ..." % (name, c))
        _lcd.set_window(0, 0, _w - 1, _h - 1)
        _write_solid(c)
        time.sleep_ms(500)
    print("fill_colors done")

def color_bars():
    """八色垂直條 — 透過 TFT 接口"""
    _setup()
    bar_h = _h // 8
    for i, c in enumerate([0xF800, 0x07E0, 0x001F, 0xFFFF,
                           0xFFE0, 0x07FF, 0xF81F, 0x0000]):
        y0, y1 = i * bar_h, (i + 1) * bar_h - 1 if i < 7 else _h - 1
        pixels = _w * (y1 - y0 + 1)
        chunk = bytearray(4096 * 2)
        for j in range(4096):
            chunk[j * 2] = c >> 8
            chunk[j * 2 + 1] = c & 0xFF
        mv = memoryview(chunk)
        _lcd.set_window(0, y0, _w - 1, y1)
        remaining = pixels
        while remaining > 0:
            n = min(remaining, 4096)
            hn = _lcd._bus.write_data_async(mv[:n * 2])
            if hn is not None: _lcd._bus.wait(hn)
            remaining -= n
        _lcd._bus.flush()
    time.sleep_ms(1500)
    print("color_bars done")

def gradient():
    """RGB 水平漸變 — 透過 TFT 接口"""
    _setup()
    gc.collect()
    row = bytearray(_w * 2)
    for x in range(_w):
        r = int(x * 255 / _w)
        g = int((1 - abs(x - _w / 2) / (_w / 2)) * 255)
        b = int((_w - x) * 255 / _w)
        c = _color(r, g, b)
        row[x * 2] = c >> 8
        row[x * 2 + 1] = c & 0xFF

    BATCH = 40
    for y in range(0, _h, BATCH):
        h = min(BATCH, _h - y)
        buf = bytearray(_w * h * 2)
        for i in range(h):
            off = i * _w * 2
            buf[off:off + len(row)] = row
        _lcd.set_window(0, y, _w - 1, y + h - 1)
        hn = _lcd._bus.write_data_async(buf)
        if hn is not None: _lcd._bus.wait(hn)
        _lcd._bus.flush()
    time.sleep_ms(2000)
    print("gradient done")

def checkerboard():
    """棋盤格 (40x40) — 透過 TFT 接口"""
    _setup()
    sq = 40
    row_buf = bytearray(_w * sq * 2)
    for row_y in range(0, _h, sq):
        for py in range(sq):
            for bx in range(0, _w, sq):
                is_w = ((bx // sq) + (row_y // sq)) % 2 == 0
                c = 0xFFFF if is_w else 0x0000
                for px in range(sq):
                    idx = ((py * _w) + bx + px) * 2
                    row_buf[idx] = c >> 8
                    row_buf[idx + 1] = c & 0xFF
        _lcd.set_window(0, row_y, _w - 1, row_y + sq - 1)
        hn = _lcd._bus.write_data_async(row_buf)
        if hn is not None: _lcd._bus.wait(hn)
        _lcd._bus.flush()
    time.sleep_ms(2000)
    print("checkerboard done")

def color_loop():
    """HSV 色輪循環動畫 (Ctrl-C 停止) — 透過 TFT 接口"""
    _setup()
    print("color_loop running... (Ctrl-C to stop)")
    hue = 0
    try:
        while True:
            for y in range(0, _h, 2):
                c = _hsv((hue + y) % 360)
                buf = bytearray(_w * 2 * 2)
                for x in range(_w):
                    buf[x * 2] = c >> 8
                    buf[x * 2 + 1] = c & 0xFF
                    buf[_w * 2 + x * 2] = c >> 8
                    buf[_w * 2 + x * 2 + 1] = c & 0xFF
                _lcd.set_window(0, y, _w - 1, y + 1)
                hn = _lcd._bus.write_data_async(buf)
                if hn is not None: _lcd._bus.wait(hn)
                _lcd._bus.flush()
            hue = (hue + 3) % 360
    except KeyboardInterrupt:
        _clear()

def shapes():
    """同心圓 + 放射線 (framebuf) — 透過 TFT 接口"""
    _setup()
    import framebuf
    h_buf = min(_h, 400)
    buf = bytearray(_w * h_buf * 2)
    fbuf = framebuf.FrameBuffer(buf, _w, h_buf, framebuf.RGB565)

    def _pixel(x, y, c):
        if 0 <= x < _w and 0 <= y < h_buf: fbuf.pixel(x, y, c)

    fbuf.fill(0)
    cx, cy = _w // 2, h_buf // 2
    for r in range(20, min(_w, h_buf)//2 - 10, 15):
        c = _color(255, 255 - r, r)
        x, y, err = r, 0, 0
        while x >= y:
            for dx, dy in ((x,y),(y,x),(-x,y),(-y,x),(-x,-y),(-y,-x),(x,-y),(y,-x)):
                _pixel(cx+dx, cy+dy, c)
            y += 1; err += 1 + 2*y
            if 2*(err-x)+1 > 0: x -= 1; err += 1-2*x
    _lcd.show(buf, 0, (_h - h_buf)//2, _w, h_buf)
    time.sleep_ms(2000)

    fbuf.fill(0)
    for _ in range(40):
        a = random.uniform(0, 2 * math.pi)
        rl = random.randint(30, min(_w, h_buf)//2 - 10)
        ex = int(cx + math.cos(a) * rl)
        ey = int(cy + math.sin(a) * rl)
        c = _color(random.randint(0,255), random.randint(0,255), random.randint(0,255))
        x0, y0 = cx, cy
        dx, dy = abs(ex-x0), -abs(ey-y0)
        sx = 1 if x0 < ex else -1
        sy = 1 if y0 < ey else -1
        err = dx + dy
        while True:
            _pixel(x0, y0, c)
            if x0 == ex and y0 == ey: break
            e2 = 2*err
            if e2 >= dy: err += dy; x0 += sx
            if e2 <= dx: err += dx; y0 += sy
    _lcd.show(buf, 0, (_h - h_buf)//2, _w, h_buf)
    time.sleep_ms(2000)
    _clear()
    print("shapes done")

def animate():
    """彈跳球 + 星空 + 跑馬燈 — 透過 TFT 接口"""
    _setup()
    import framebuf
    buf = bytearray(_w * _h * 2)
    fbuf = framebuf.FrameBuffer(buf, _w, _h, framebuf.RGB565)

    print("animate: bouncing ball")
    bx, by = _w//2, _h//2
    bdx, bdy = 5, 4
    fbuf.fill(0)
    for _ in range(150):
        fbuf.fill_rect(max(0, bx-17), max(0, by-17), 34, 34, 0)
        bx += bdx; by += bdy
        if bx <= 0 or bx >= _w-1: bdx = -bdx
        if by <= 0 or by >= _h-1: bdy = -bdy
        fbuf.ellipse(bx, by, 15, 15, _color(255,255,0), True)
        _lcd.show(buf)
        time.sleep_ms(8)

    print("animate: starfield")
    stars = [(random.randint(0,_w-1), random.randint(0,_h-1),
              random.randint(1,3)) for _ in range(60)]
    fbuf.fill(0)
    for _ in range(150):
        for i, (sx, sy, spd) in enumerate(stars):
            fbuf.pixel(sx, sy, 0)
            sx = (sx + spd) % _w
            stars[i] = (sx, sy, spd)
            fbuf.pixel(sx, sy, _color(spd*80, spd*80, spd*80+60))
        _lcd.show(buf)
        time.sleep_ms(15)

    print("animate: text ticker")
    texts = ["ESP32-S3", "RM67162", "QSPI 80MHz", "AMOLED 240x536"]
    tx = _w; ti = 0
    fbuf.fill(0)
    for _ in range(300):
        fbuf.fill_rect(0, _h//2 - 8, _w, 16, 0)
        ct = texts[ti]
        tw = len(ct) * 8
        fbuf.text(ct, tx, _h//2 - 4, _color(255,255,0))
        tx -= 3
        if tx < -tw: tx = _w; ti = (ti + 1) % len(texts)
        _lcd.show(buf)
        time.sleep_ms(10)
    _clear()
    print("animate done")

def fps_test(frames=100):
    """黑白交替 FPS 測試 (直通 _bus，純頻寬基準)"""
    _setup()
    gc.collect()
    chunk_w = memoryview(bytearray(b'\xff\xff' * 16384))
    chunk_b = memoryview(bytearray(32768))
    total = _w * _h * 2
    _lcd.set_window(0, 0, _w - 1, _h - 1)
    spi = _lcd._bus._spi
    cs = _lcd._bus._cs
    t0 = time.ticks_us()
    for n in range(frames):
        cs.value(0)
        spi.write(b'', cmd=0x32, addr=0x002C00, multiline=False)
        chunk = chunk_w if n & 1 else chunk_b
        remaining = total
        while remaining > 0:
            nbytes = min(remaining, 32768)
            tid = spi.write(chunk[:nbytes])
            spi.wait(tid)
            remaining -= nbytes
        cs.value(1)
    elapsed = time.ticks_diff(time.ticks_us(), t0) / 1_000_000
    fps = frames / elapsed
    mbps = total * frames / elapsed / (1024 * 1024)
    print(f"FPS: {fps:.0f}  ({elapsed/frames*1000:.1f} ms/frame, {mbps:.1f} MB/s)")


def fps_test_tft(frames=100):
    """黑白交替 FPS — 透過 TFT.show_frame() 全幀 library 開銷"""
    _setup()
    gc.collect()
    total = _w * _h * 2
    full_w = memoryview(bytearray(b'\xff\xff' * (total // 2))[:total])
    full_b = memoryview(bytearray(total))
    _lcd.set_window(0, 0, _w - 1, _h - 1)
    t0 = time.ticks_us()
    for n in range(frames):
        _lcd.show_frame(full_w if n & 1 else full_b)
    elapsed = time.ticks_diff(time.ticks_us(), t0) / 1_000_000
    fps = frames / elapsed
    mbps = total * frames / elapsed / (1024 * 1024)
    print(f"FPS(TFT): {fps:.0f}  ({elapsed/frames*1000:.1f} ms/frame, {mbps:.1f} MB/s)")




def fps_test_tft888(frames=100):
    """TFT 層 RGB888 FPS — 透過 show_frame() 24bpp 全幀"""
    _setup()
    gc.collect()
    total = _w * _h * 3
    full_w = memoryview(bytearray(b'\xff\xff\xff' * (total // 3))[:total])
    full_b = memoryview(bytearray(total))
    _set_rgb888()
    _lcd.set_window(0, 0, _w - 1, _h - 1)
    t0 = time.ticks_us()
    for n in range(frames):
        _lcd.show_frame(full_w if n & 1 else full_b)
    elapsed = time.ticks_diff(time.ticks_us(), t0) / 1_000_000
    fps = frames / elapsed
    mbps = total * frames / elapsed / (1024 * 1024)
    print(f"FPS(TFT888): {fps:.0f}  ({elapsed/frames*1000:.1f} ms/frame, {mbps:.1f} MB/s)")
    _set_rgb565()

# ══════════════════════════════════════════════════════════════
#  RGB888 (24bpp) 測試
# ══════════════════════════════════════════════════════════════

def _colmod(cmd_val):
    """切換 COLMOD — 透過 TFT 統一接口 write_cmd_data()"""
    _lcd.write_cmd_data(0x3A, bytes([cmd_val]))

def _set_rgb888():
    _colmod(0x76)
    _lcd.bytes_per_pixel = 3

def _set_rgb565():
    _colmod(0x55)
    _lcd.bytes_per_pixel = 2

def _write_solid888(r, g, b):
    """全螢幕 RGB888 填色 (3 bytes/pixel) — 透過 TFT 接口"""
    chunk = bytearray(4096 * 3)
    for i in range(4096):
        off = i * 3
        chunk[off] = r
        chunk[off + 1] = g
        chunk[off + 2] = b
    _lcd.set_window(0, 0, _w - 1, _h - 1)
    total = _w * _h
    mv = memoryview(chunk)
    written = 0
    while written < total:
        n = min(total - written, 4096)
        hn = _lcd._bus.write_data_async(mv[:n * 3])
        if hn is not None: _lcd._bus.wait(hn)
        written += n
    _lcd._bus.flush()

def fill_colors888():
    """九色全螢幕填滿 (RGB888) — 自動切換 COLMOD"""
    _setup()
    gc.collect()
    colors = [
        ("RED",     255, 0,   0),
        ("GREEN",   0,   255, 0),
        ("BLUE",    0,   0,   255),
        ("YELLOW",  255, 255, 0),
        ("CYAN",    0,   255, 255),
        ("MAGENTA", 255, 0,   255),
        ("WHITE",   255, 255, 255),
        ("GRAY",    128, 128, 128),
        ("BLACK",   0,   0,   0),
    ]
    _set_rgb888()
    for name, r, g, b in colors:
        print("  %s (%d,%d,%d) ..." % (name, r, g, b))
        _lcd.set_window(0, 0, _w - 1, _h - 1)
        _write_solid888(r, g, b)
        time.sleep_ms(500)
    _set_rgb565()
    print("fill_colors888 done")

def fps_test888(frames=100):
    """RGB888 黑白交替 FPS — 24bpp 匯流排吞吐量"""
    _setup()
    gc.collect()
    px3 = _w * _h * 3
    chunk_w = memoryview(bytearray(b'\xff\xff\xff' * 8192))
    chunk_b = memoryview(bytearray(24576))
    _set_rgb888()
    _lcd.set_window(0, 0, _w - 1, _h - 1)
    spi = _lcd._bus._spi
    cs = _lcd._bus._cs
    CHUNK = len(chunk_w)
    t0 = time.ticks_us()
    for n in range(frames):
        cs.value(0)
        spi.write(b'', cmd=0x32, addr=0x002C00, multiline=False)
        chunk = chunk_w if n & 1 else chunk_b
        remaining = px3
        while remaining > 0:
            nbytes = min(remaining, CHUNK)
            tid = spi.write(chunk[:nbytes])
            spi.wait(tid)
            remaining -= nbytes
        cs.value(1)
    elapsed = time.ticks_diff(time.ticks_us(), t0) / 1_000_000
    fps = frames / elapsed
    mbps = px3 * frames / elapsed / (1024 * 1024)
    print(f"FPS(888): {fps:.0f}  ({elapsed/frames*1000:.1f} ms/frame, {mbps:.1f} MB/s)")
    _set_rgb565()





def all():
    """全部依序執行：FPS (565/888) + 圖形驗證"""
    fps_test(50)
    _clear(); time.sleep_ms(300)
    fps_test888(50)
    _clear(); time.sleep_ms(300)
    fps_test_tft(50)
    _clear(); time.sleep_ms(300)
    fps_test_tft888(50)
    _clear(); time.sleep_ms(300)
    fill_colors()
    _clear(); time.sleep_ms(300)
    fill_colors888()
    _clear(); time.sleep_ms(300)
    color_bars()
    _clear(); time.sleep_ms(300)
    gradient()
    _clear(); time.sleep_ms(300)
    checkerboard()
    _clear(); time.sleep_ms(300)
    shapes()
    _clear()
    print("=== all tests done ===")

# ══════════════════════════════════════════════════════════════
#  官方 examples 移植 — 不在 all() 中，手動呼叫
# ══════════════════════════════════════════════════════════════

def color_sweep():
    """HSV 色條由上而下刷動（源自 color_loop.py）"""
    _setup()
    gc.collect()
    SPEED = 5
    _sw_chunk = bytearray(8192)

    def _hsv_rgb(hue, sat=255, val=100):
        h = float(hue % 360) / 60.0
        s, v = sat / 255.0, val / 100.0
        i = int(h); f = h - i
        p = v * (1 - s); q = v * (1 - s * f); t = v * (1 - s * (1 - f))
        r, g, b = [(v,t,p),(q,v,p),(p,v,t),(p,q,v),(t,p,v),(v,p,q)][i]
        return int(r*255), int(g*255), int(b*255)

    hue = 0
    print("color_sweep running... (Ctrl-C to stop)")
    try:
        while True:
            r, g, b = _hsv_rgb(hue)
            c = _color(r, g, b)
            for i in range(4096):
                _sw_chunk[i * 2] = c >> 8
                _sw_chunk[i * 2 + 1] = c & 0xFF
            mv = memoryview(_sw_chunk)
            for j in range(0, _h, SPEED):
                _lcd.set_window(0, j, _w - 1, min(j + SPEED, _h) - 1)
                pixels = _w * min(SPEED, _h - j)
                remaining = pixels
                while remaining > 0:
                    n = min(remaining, 4096)
                    hn = _lcd._bus.write_data_async(mv[:n * 2])
                    if hn is not None: _lcd._bus.wait(hn)
                    remaining -= n
                _lcd._bus.flush()
            hue = (hue + 5) % 360
    except KeyboardInterrupt:
        _clear()
        print("color_sweep stopped")

def scroll_text():
    """平滑捲動字元表（源自 scroll.py） — 透過 TFT 接口"""
    _setup()
    import framebuf
    gc.collect()

    font_h = 8
    buf = bytearray(_w * font_h * 2)
    fbuf = framebuf.FrameBuffer(buf, _w, font_h, framebuf.RGB565)

    colors = [0xF800, 0x07E0, 0x001F, 0xFFE0, 0x07FF, 0xF81F]
    ci = 0
    fg = colors[ci]
    bg = 0x0000

    fbuf.fill(bg)
    for i in range(0, _h, font_h):
        _lcd.show(buf, 0, i, _w, font_h)

    last_line = _h - font_h
    scroll = 0
    ch = 0x20

    print("scroll_text running... (Ctrl-C to stop)")
    try:
        while True:
            if scroll % font_h == 0:
                line = (scroll + last_line) % _h
                fbuf.fill(bg)
                s = '0x%02x %c' % (ch, ch) if 0x20 <= ch <= 0x7E else '0x%02x' % ch
                fbuf.text(s, 16, 0, fg)
                _lcd.show(buf, 0, line, _w, font_h)
                ci = (ci + 1) % len(colors)
                fg = colors[ci]
                ch += 1
                if ch > 0x7F:
                    ch = 0x20
            scroll = (scroll + 1) % _h
            time.sleep_ms(30)
    except KeyboardInterrupt:
        _clear()
        print("scroll_text stopped")

def feathers_anim():
    """羽毛波形動畫（源自 feathers.py — 簡化版）"""
    _setup()
    import framebuf
    gc.collect()

    buf = bytearray(_w * 2)
    fbuf = framebuf.FrameBuffer(buf, _w, 1, framebuf.RGB565)

    def _between(a, b, t):
        return int(a * (1 - t) + b * t)

    def _color_wheel(pos):
        pos = (255 - pos) % 255
        if pos < 85:       return _color(255 - pos * 3, 0, pos * 3)
        elif pos < 170:
            pos -= 85;     return _color(0, pos * 3, 255 - pos * 3)
        else:
            pos -= 170;    return _color(pos * 3, 255 - pos * 3, 0)

    half = (_h >> 1) - 1
    interval = 10
    increment = 1.0 / interval
    counter = 1
    cy, ly = 0, 0
    wheel = 0

    print("feathers running... (Ctrl-C to stop)")
    try:
        while True:
            if counter > interval:
                ly, cy = cy, random.randint(0, half)
                counter = 0
                interval = random.randint(10, 100)
                increment = 1.0 / interval if interval else 0

            tween = _between(ly, cy, counter * increment)

            for x in range(_w):
                fbuf.pixel(x, 0, 0)

            for i, xo in enumerate([x * (_w // 8) - 1 for x in range(2, 9)]):
                c = _color_wheel(wheel + (i << 2))
                fbuf.pixel(xo % _w, 0, c)

            _lcd.show(buf, 0, half + tween, _w, 1)
            _lcd.show(buf, 0, half - tween, _w, 1)

            wheel = (wheel + 1) % 256
            counter += 1
    except KeyboardInterrupt:
        _clear()
        print("feathers stopped")

def framebuf_rgb():
    """Framebuf 紅綠藍循環（源自 use_framebuf.py） — 透過 TFT 接口"""
    _setup()
    import framebuf
    gc.collect()

    buf = bytearray(_w * 10 * 2)
    fbuf = framebuf.FrameBuffer(buf, _w, 10, framebuf.RGB565)

    print("framebuf_rgb running... (Ctrl-C to stop)")
    try:
        while True:
            fbuf.fill(_color(255, 0, 0))
            for i in range(0, _h, 10):
                _lcd.show(buf, 0, i, _w, 10)
            time.sleep_ms(500)

            fbuf.fill(_color(0, 255, 0))
            for i in range(0, _h, 10):
                _lcd.show(buf, 0, i, _w, 10)
            time.sleep_ms(500)

            fbuf.fill(_color(0, 0, 255))
            for i in range(0, _h, 10):
                _lcd.show(buf, 0, i, _w, 10)
            time.sleep_ms(500)
    except KeyboardInterrupt:
        _clear()
        print("framebuf_rgb stopped")

def img_logo():
    """顯示 logo 點陣圖 — 透過 TFT 接口"""
    _setup()
    import framebuf
    gc.collect()

    buf = bytearray(_w * _h * 2)
    fbuf = framebuf.FrameBuffer(buf, _w, _h, framebuf.RGB565)
    fbuf.fill(0)

    for i in range(min(_w, _h)):
        fbuf.pixel(i, i, _color(255, 0, 0))
        fbuf.pixel(_w - 1 - i, i, _color(0, 255, 0))

    fbuf.rect(0, 0, _w, _h, _color(255, 255, 255))
    fbuf.rect(4, 4, _w - 8, _h - 8, _color(0, 0, 255))

    cx, cy = _w // 2, _h // 2
    for r in range(20, min(_w, _h)//2, 20):
        fbuf.ellipse(cx, cy, r, r, _color(r*5 & 0xFF, 255 - r*5, r*3 & 0xFF))

    _lcd.show(buf)
    time.sleep_ms(3000)
    _clear()
    print("img_logo done")


if __name__ == "__main__":
    all()
