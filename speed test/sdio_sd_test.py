# -*- coding: utf-8 -*-
"""SDIO SD 卡 I/O 測試 v3 — 統一緩衝 + size sweep + raw 對照

v3 改進:
  1. 統一緩衝: 一次過申請,之後所有 size 測試都用同一個緩衝嘅 view,唔會重複 malloc
     - 優先 heap_caps CAP_DMA(內部 RAM,冇 bounce)→ 由 64KB 開始,失敗逐級減半
     - 冇 heap_caps 或者全部失敗 → GC bytearray
  2. 大檔測試: 同一緩衝,分別用 64K/32K/16K/8K/4K 嘅 view 測寫/讀速度
     - 注意: fatfs 每個 disk op 最多一個 cluster(8KB),chunk 大過 cluster 都會被斬開,
       所以「chunk 越大越快」喺 VFS 層唔一定成立——呢個測試就係要睇真
  3. raw 對照: sd_raw 服務嘅 readblocks/writeblocks 16KB
     ——冇 cluster 斬件、冇 fatfs 開銷嘅實際上限
  4. 印出 cluster size,方便理解斬件行為
  5. 保留 v2 嘅進度顯示(每步知做緊乜)
"""

from machine import Pin, SDCard
import os, time, urandom, gc

# ================= 硬件設定(按你的板改) =================
#
# sd = SDCard(slot=0, width=4,
#             sck=43, cmd=44,
#             data=(39, 40, 41, 42),
#             freq=40_000_000)
#
#     "config": { "slot": 4, "width": 4, "freq": 20000000 },
#     "GPIO": {
#         "_comment": "sck=CLK/SCK, cmd=CMD/MOSI, [D0/MISO, D1/IRQ, D2/NC, D3/CS]",
#         "sck": 14,
#         "cmd": 17,
#         "data": [16, 18, 15, 21]
#         }
#     }
#
# sd = SDCard(slot=2, width=4,
#             sck=14, cmd=17,
#             data=(16, 18, 15, 21),
#             freq=10_000_000)
#
# sd = SDCard(slot=2, width=1,  sck=14, miso=16, mosi=17, cs=21,  freq=20000000)
#
# sd = SDCard(slot=0, width=4,
#             sck=7, cmd=6,
#             data=(15, 16, 4, 5),
#             freq=40_000_000)
#
# os.mount(sd, '/sd')

ROOT = '/sd'
print('mount ok:', ROOT)

# ================= 測試參數 =================
FILE_MB  = 4          # 大檔大小 (MB)
SIZES_KB = (64, 32, 16, 8, 4)   # 用統一緩衝嘅 view 逐個 size 測
SMALL_N  = 1000       # 細檔數量
SMALL_KB = 4          # 細檔大小 (KB)

# ---------- 工具 ----------
_pool = []
def aligned(n):
    """512-byte 對齊嘅 memoryview(長度 n)。"""
    b = bytearray(n + 512)
    off = (512 - (id(b) & 0x1FF)) & 0x1FF
    _pool.append(b)
    return memoryview(b)[off:off + n]

def fill_random(buf):
    """用隨機 4KB 種子鋪滿 buffer(防卡嘅寫入壓縮,快過逐 4 byte)"""
    seed = bytearray(4096)
    for i in range(0, 4096, 4):
        seed[i:i + 4] = urandom.getrandbits(32).to_bytes(4, 'little')
    n = 0
    while n < len(buf):
        buf[n:n + 4096] = seed
        n += 4096

def KBps(t_ms, nbytes):
    return nbytes / 1024 * 1000 / t_ms if t_ms else 0

_pct_state = {}
def pct(done, total, label):
    """進度顯示:百分比變咗先 print,避免每次 iteration 嘅 print 污染計時"""
    p = done * 100 // total
    if _pct_state.get(label) != p:
        _pct_state[label] = p
        print('\r  %-20s %3d%%' % (label, p), end='')

# ---------- 統一緩衝 ----------
def alloc_unified():
    """申請一個統一緩衝: heap_caps CAP_DMA 由 64KB 起,失敗逐級減半。

    流程:
      1. import heap_caps(冇就用 GC fallback)
      2. 清除兩個模組嘅緩存: heap_caps.reset()(釋放追蹤中 buffer)
         + gc.collect()(清 GC heap)
      3. 清除完成後顯示而家 free 幾多(GC / DMA / SPIRAM / 最大連續 DMA block)
      4. 先至申請統一緩衝(reset 要喺 malloc 之前,否則連自己都會被 free)

    回傳 (base_buffer, 實際可用 size(bytes), 說明字串)。"""
    heap_caps = None
    try:
        import heap_caps
    except Exception:
        pass

    # ── 1. 清除兩個模組嘅緩存 ──
    print('  清除緩存 ...')
    if heap_caps:
        heap_caps.reset()          # 釋放追蹤中嘅 buffer(包括之前 session 漏 free 嘅)
    gc.collect()                   # 清 GC heap

    # ── 2. 清除完成後顯示 free ──
    print('  清除完成, free:')
    print('    GC              : %6d KB' % (gc.mem_free() // 1024))
    if heap_caps:
        print('    DMA             : %6d KB' % (heap_caps.get_free_size(heap_caps.CAP_DMA) // 1024))
        print('    SPIRAM          : %6d KB' % (heap_caps.get_free_size(heap_caps.CAP_SPIRAM) // 1024))
        print('    最大連續 DMA block: %6d KB' % (heap_caps.get_largest_free_block(heap_caps.CAP_DMA) // 1024))
    else:
        print('    (冇 heap_caps 模組 → 只做 gc.collect,唔做 reset/DMA 報告)')

    # ── 3. 先至申請統一緩衝 ──
    base = None
    base_n = 0
    desc = ''
    if heap_caps:
        for kb in (64, 32, 16, 8, 4):
            d = heap_caps.malloc(kb * 1024, heap_caps.CAP_DMA)
            if d:
                base, base_n, desc = d, kb * 1024, 'heap_caps(DMA)'
                print('  統一緩衝: heap_caps CAP_DMA %d KB (內部 RAM, 無 bounce)' % kb)
                break
            print('  heap_caps %dKB 失敗, 試細一級 ...' % kb)
    if base is None:
        # fallback: GC heap(PSRAM),512 對齊 view
        n = 64 * 1024
        base = aligned(n)
        base_n = n
        desc = 'GC(PSRAM)'
        print('  統一緩衝: GC bytearray 64 KB (PSRAM, 行 bounce)')
    return base, base_n, desc

# ---------- 大檔測試(size sweep) ----------
def bench_big(base, base_n, desc):
    print()
    print('== 大檔測試: %d MB, 統一緩衝 = %s ==' % (FILE_MB, desc))
    try:
        st = os.statvfs(ROOT)
        print('  cluster size = %d B  (fatfs 每個 disk op 最多一個 cluster)'
              % st[0])
    except Exception:
        pass
    path = ROOT + '/bench.dat'
    size = FILE_MB * 1024 * 1024
    mv = memoryview(base)          # 統一緩衝嘅 view 基礎
    results = {}

    for kb in SIZES_KB:
        if kb * 1024 > base_n:
            continue               # 統一緩衝唔夠大就跳過
        view = mv[:kb * 1024]      # 唔使再 malloc,直接用同一緩衝嘅頭一段
        nchunk = size // len(view)
        fill_random(view)

        # ---- 寫 ----
        print('  寫入 [chunk %dKB] ...' % kb)
        t0 = time.ticks_ms()
        with open(path, 'wb') as f:
            for i in range(nchunk):
                f.write(view)
                pct(i + 1, nchunk, 'write %dK' % kb)
        t_w = time.ticks_diff(time.ticks_ms(), t0)
        print()
        os.sync()

        # ---- 讀 ----
        print('  讀出 [chunk %dKB] ...' % kb)
        t0 = time.ticks_ms()
        with open(path, 'rb') as f:
            for i in range(nchunk):
                f.readinto(view)
                pct(i + 1, nchunk, 'read %dK' % kb)
        t_r = time.ticks_diff(time.ticks_ms(), t0)
        print()

        results[kb] = (KBps(t_w, size), KBps(t_r, size))
        print('  [%3dKB] write %7.1f KB/s  read %7.1f KB/s'
              % (kb, results[kb][0], results[kb][1]))
    try:
        os.remove(path)
    except OSError:
        pass
    return results

# ---------- raw 對照 ----------
def bench_raw():
    print()
    print('== raw 對照 (sd_raw readblocks/writeblocks 16KB, 冇 fatfs 斬件) ==')
    try:
        from lib.sys_bus import bus
        sd = bus.get_service('sd_raw')
    except Exception:
        print('  冇 sd_raw 服務,跳過')
        return None
    buf = bytearray(16384)
    fill_random(buf)
    res = {}

    t0 = time.ticks_ms()
    for _ in range(16):
        sd.writeblocks(600000, buf)
    t = time.ticks_diff(time.ticks_ms(), t0)
    res['write'] = KBps(t, 16 * 16384)
    print('  raw write 16KB @600000: %.1f KB/s' % res['write'])

    t0 = time.ticks_ms()
    for _ in range(64):
        sd.readblocks(400000, buf)
    t = time.ticks_diff(time.ticks_ms(), t0)
    res['read'] = KBps(t, 64 * 16384)
    print('  raw read  16KB @400000: %.1f KB/s' % res['read'])
    return res

# ---------- 細檔測試 ----------
def bench_small():
    print()
    print('== 細檔測試: %d × %d KB ==' % (SMALL_N, SMALL_KB))
    d = ROOT + '/small_test'
    try:
        os.mkdir(d)
    except OSError:
        pass
    path = d + '/%04d.log'
    size = SMALL_N * SMALL_KB * 1024
    bf = bytearray(SMALL_KB * 1024)
    fill_random(bf)

    try:
        print('  寫入細檔 ...')
        t0 = time.ticks_ms()
        for n in range(SMALL_N):
            with open(path % n, 'wb') as f:
                f.write(bf)
            pct(n + 1, SMALL_N, 'small write')
        t_w = time.ticks_diff(time.ticks_ms(), t0)
        print()
        os.sync()

        print('  讀出細檔 ...')
        t0 = time.ticks_ms()
        for n in range(SMALL_N):
            with open(path % n, 'rb') as f:
                f.readinto(bf)
            pct(n + 1, SMALL_N, 'small read')
        t_r = time.ticks_diff(time.ticks_ms(), t0)
        print()
    finally:
        for n in range(SMALL_N):
            try:
                os.remove(path % n)
            except OSError:
                pass
        try:
            os.rmdir(d)
        except OSError:
            pass

    return (KBps(t_w, size), KBps(t_r, size))

# ---------- 主流程 ----------
def main():
    print('╔' + '═' * 42 + '╗')
    print(' SDIO SD 測試 v3')
    print(' 測試計劃:')
    print('  1. 清除緩存(heap_caps.reset + gc.collect)+ 顯示 free')
    print('  2. 大檔 %d MB × chunk %s' % (FILE_MB, '/'.join('%dK' % k for k in SIZES_KB)))
    print('  3. raw 對照 (readblocks/writeblocks 16KB)')
    print('  4. 細檔 %d × %d KB' % (SMALL_N, SMALL_KB))
    print('╚' + '═' * 42 + '╝')

    base, base_n, desc = alloc_unified()
    big = bench_big(base, base_n, desc)
    raw = bench_raw()
    small = bench_small()

    print()
    print('── 總結 ──')
    print('  %-12s %12s %12s' % ('chunk', '寫 KB/s', '讀 KB/s'))
    for kb in SIZES_KB:
        if kb in big:
            print('  %-12s %12.1f %12.1f' % (('%dK' % kb), big[kb][0], big[kb][1]))
    if raw:
        print('  %-12s %12.1f %12.1f' % ('raw 16K', raw['write'], raw['read']))
    print('  %-12s %12.1f %12.1f' % ('細檔 4K', small[0], small[1]))
    print()
    print('✅ 完成')

main()
