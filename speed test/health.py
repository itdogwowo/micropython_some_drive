# -*- coding: utf-8 -*-
"""ESP 系統健康檢查 — CPU/PSRAM/Flash/SD/Network 一鍵體檢

用法:
  from health import report
  report()              # 快速報告
  report(full_sd=True)  # 完整 SD 測試(事前申請統一緩衝 + VFS sweep + raw + 細檔)
"""

import time, gc, machine, ubinascii, os, micropython

def _sz(b):
    for u in ("B","KB","MB","GB"):
        if b < 1024: return "{}{}".format(b, u)
        b //= 1024
    return "{}{}".format(b, "GB")

def _sz2(s):
    if s >= 1024: return "{:.0f}KB".format(s/1024)
    return "{:.0f}B".format(s)

# ---------- 完整 SD 測試工具 ----------
_aligned_pool = []

def _aligned(n):
    """512-byte 對齊嘅 memoryview(長度 n),fatfs 先會行 multi-block"""
    b = bytearray(n + 512)
    off = (512 - (id(b) & 0x1FF)) & 0x1FF
    _aligned_pool.append(b)
    return memoryview(b)[off:off + n]

def _fill_random(buf):
    """用隨機 4KB 種子鋪滿 buffer,防卡嘅寫入壓縮"""
    try:
        import urandom
        r = urandom.getrandbits
    except:
        import random
        r = random.getrandbits
    seed = bytearray(4096)
    for i in range(0, 4096, 4):
        seed[i:i + 4] = r(32).to_bytes(4, 'little')
    n = 0
    while n < len(buf):
        buf[n:n + 4096] = seed
        n += 4096

def _KBps(t_ms, nbytes):
    return nbytes / 1024 * 1000 / t_ms if t_ms else 0

_pct_state = {}
def _pct(done, total, label):
    """進度顯示:百分比變咗先 print,避免 print 污染計時"""
    p = done * 100 // total
    if _pct_state.get(label) != p:
        _pct_state[label] = p
        print('\r  %-20s %3d%%' % (label, p), end='')

def _alloc_unified():
    """統一緩衝 ×2: DMA(內部 RAM,64KB 起)+ PSRAM(1MB 起,失敗逐級減)。

    次序: import → heap_caps.reset() + gc.collect() → 顯示 free → 先至 malloc
    (reset 會 free 晒追蹤中 buffer,一定要喺 malloc 之前)
    喺效能測試之前申請,之後所有測試都用佢哋嘅 view。

    回傳 (dma_base, dma_n, dma_desc, ps_base, ps_n, ps_desc)。"""
    hc = None
    try:
        import heap_caps
        hc = heap_caps
    except:
        pass
    print("  清除緩存 ...")
    if hc:
        hc.reset()              # 釋放追蹤中嘅 buffer(包括之前 session 漏 free 嘅)
    gc.collect()
    print("  清除完成, free:")
    print("    GC              : %6d KB" % (gc.mem_free() // 1024))
    if hc:
        print("    DMA             : %6d KB" % (hc.get_free_size(hc.CAP_DMA) // 1024))
        print("    SPIRAM          : %6d KB" % (hc.get_free_size(hc.CAP_SPIRAM) // 1024))
        print("    最大連續 DMA block : %6d KB" % (hc.get_largest_free_block(hc.CAP_DMA) // 1024))
        print("    最大連續 PSRAM block: %6d KB" % (hc.get_largest_free_block(hc.CAP_SPIRAM) // 1024))
    else:
        print("    (冇 heap_caps 模組 → 只做 gc.collect,唔做 reset/DMA 報告)")

    # ── DMA 緩衝: 內部 RAM,64KB 起逐級減 ──
    dma = None
    dma_n = 0
    dma_desc = ""
    if hc:
        for kb in (64, 32, 16, 8, 4):
            d = hc.malloc(kb * 1024, hc.CAP_DMA)
            if d:
                dma, dma_n, dma_desc = d, kb * 1024, "heap_caps(DMA)"
                print("  統一緩衝 DMA  : heap_caps CAP_DMA %d KB (內部 RAM, 無 bounce)" % kb)
                break
            print("  heap_caps DMA %dKB 失敗, 試細一級 ..." % kb)

    # ── PSRAM 緩衝: 1MB 起逐級減,冇 heap_caps 就 GC bytearray ──
    ps = None
    ps_n = 0
    ps_desc = ""
    if hc:
        for kb in (1024, 512, 256, 128, 64, 32, 16):
            d = hc.malloc(kb * 1024, hc.CAP_SPIRAM)
            if d:
                ps, ps_n, ps_desc = d, kb * 1024, "heap_caps(SPIRAM)"
                print("  統一緩衝 PSRAM: heap_caps CAP_SPIRAM %d KB" % kb)
                break
            print("  heap_caps SPIRAM %dKB 失敗, 試細一級 ..." % kb)
    if ps is None:
        try:
            b = bytearray(1024 * 1024)
            _aligned_pool.append(b)
            ps = memoryview(b)
            ps_n = 1024 * 1024
            ps_desc = "GC(PSRAM)"
            print("  統一緩衝 PSRAM: GC bytearray 1024 KB")
        except MemoryError:
            pass
    return dma, dma_n, dma_desc, ps, ps_n, ps_desc

def _sys():
    print("── 系統資訊 ──")
    try:
        mac = ubinascii.hexlify(machine.unique_id()).decode().upper()
        print("  MAC:   {}:{}:{}:{}:{}:{}".format(mac[0:2],mac[2:4],mac[4:6],mac[6:8],mac[8:10],mac[10:12]))
    except: pass
    try:
        print("  CPU:   {} MHz".format(machine.freq() // 1000000))
    except: pass
    try:
        import esp
        fs = esp.flash_size(); print("  Flash: {} MB ({} bytes)".format(fs//1048576, fs))
    except: pass
    gc.collect()
    print("  GC:    {} KB total, {} KB free".format((gc.mem_alloc()+gc.mem_free())//1024, gc.mem_free()//1024))
    try:
        import heap_caps
        def _ml(label, caps):
            t = heap_caps.get_total_size(caps); f = heap_caps.get_free_size(caps)
            if t == 0: return
            u = t - f; p = u * 100 // t
            print("  {:8s}: {:>7s} total, {:>7s} free, {:>7s} used  ({}%)".format(
                label, _sz(t), _sz(f), _sz(u), p))
        _ml("DRAM", heap_caps.CAP_8BIT | heap_caps.CAP_INTERNAL)
        _ml("DMA", heap_caps.CAP_DMA)
        _ml("PSRAM", heap_caps.CAP_8BIT | heap_caps.CAP_SPIRAM)
        _ml("EXEC", heap_caps.CAP_EXEC)
    except: pass
    from lib.sys_bus import bus
    print("  Slave: {}".format(getattr(bus, "slave_id", "N/A")))
    print()

def _mem():
    print("── 記憶體頻寬 ──")
    sz = 16384
    a = bytearray(sz); b = bytearray(sz)
    for i in range(sz): a[i] = i & 0xFF
    gc.collect(); t0=time.ticks_us(); b[:]=a
    t=time.ticks_diff(time.ticks_us(),t0)
    print("  PSRAM↔PSRAM: {:>5.1f} MB/s".format(sz/1024/(t/1000)))
    try:
        import heap_caps
        d = heap_caps.malloc(sz, heap_caps.CAP_DMA)
        if d:
            for i in range(sz): d[i] = i & 0xFF
            gc.collect(); t0=time.ticks_us(); b[:]=d
            t=time.ticks_diff(time.ticks_us(),t0)
            print("  DRAM→PSRAM:  {:>5.1f} MB/s".format(sz/1024/(t/1000)))
            c = heap_caps.malloc(sz, heap_caps.CAP_DMA)
            if c:
                gc.collect(); t0=time.ticks_us(); c[:]=d
                t=time.ticks_diff(time.ticks_us(),t0)
                print("  DRAM↔DRAM:   {:>5.1f} MB/s".format(sz/1024/(t/1000)))
            if c: heap_caps.free(c)
            heap_caps.free(d)
    except: pass
    print()

def _sd(sd, dma=None, dma_n=0, dma_desc="", ps=None, ps_n=0, ps_desc=""):
    """SD 卡效能(一體化): 統一緩衝(DMA + PSRAM)+ raw HEAP/DMA 表 + VFS sweep + raw 對照 + 細檔

    dma/ps: 事前申請好嘅統一緩衝;全部 None 就係快速模式(內部臨時申請)。
    VFS 基準 = 最大 buffer 嘅 VFS 讀取速度。"""
    print("── SD 卡效能 ──")
    ss = sd.info()[1]
    cap = sd.info()[0]
    print("  容量: {} ({:.1f} GB)  sector: {}B".format(_sz(cap), cap/1073741824, ss))
    try:
        s = os.statvfs("/sd")
        print("  Cluster: {}  free: {} / {}".format(_sz(s[0]), _sz(s[3]*s[1]), _sz(s[2]*s[1])))
    except: pass
    gc.collect()

    full = dma is not None or ps is not None
    if full:
        if dma:
            print("  統一緩衝 DMA  : {} {} KB (內部 RAM, 無 bounce)".format(dma_desc, dma_n // 1024))
        if ps:
            print("  統一緩衝 PSRAM: {} {} KB".format(ps_desc, ps_n // 1024))
        try:
            st = os.statvfs("/sd")
            print("  cluster = {} B (fatfs 每個 disk op 最多一個 cluster)".format(st[0]))
        except: pass

    sizes = [4096, 8192, 16384, 32768, 65536]
    hbuf = ps if ps is not None else _aligned(65536)   # HEAP 行: PSRAM 統一緩衝
    dbuf = dma                                         # DMA 行: 內部統一緩衝
    if dbuf is None:
        try:
            import heap_caps
            dbuf = heap_caps.malloc(65536, heap_caps.CAP_DMA)
        except:
            dbuf = None

    try:
        import urandom
        r = urandom.getrandbits
    except:
        import random
        r = random.getrandbits
    max_sec = cap // ss

    rows = []
    def _bm(fn, blk, buf, n):
        t0 = time.ticks_ms()
        for _ in range(n):
            fn(blk, buf)
            blk += len(buf) // ss
        return time.ticks_diff(time.ticks_ms(), t0)

    sec = 400000
    for s in sizes:
        n = max(1048576 // s, 4)
        rows.append(("HEAP","rd",_sz2(s), _bm(sd.readblocks, sec, hbuf[:s], n), n*s))
        if dbuf:
            rows.append(("DMA","rd",_sz2(s), _bm(sd.readblocks, sec+len(sizes), dbuf[:s], n), n*s))
        sec += 200

    sec = 600000
    for s in sizes:
        n = max(524288 // s, 2)
        for j in range(s): hbuf[j] = j & 0xFF
        rows.append(("HEAP","wr",_sz2(s), _bm(sd.writeblocks, sec, hbuf[:s], n), n*s))
        if dbuf:
            for j in range(s): dbuf[j] = j & 0xFF
            rows.append(("DMA","wr",_sz2(s), _bm(sd.writeblocks, sec+len(sizes), dbuf[:s], n), n*s))
        sec += 200

    t0 = time.ticks_ms()
    for _ in range(1000): sd.readblocks(r(28) % max_sec, hbuf[:4096])
    rows.append(("HEAP","rnd","4KB", time.ticks_diff(time.ticks_ms(), t0), 4*1000*1000))
    if dbuf:
        t0 = time.ticks_ms()
        for _ in range(1000): sd.readblocks(r(28) % max_sec, dbuf[:4096])
        rows.append(("DMA","rnd","4KB", time.ticks_diff(time.ticks_ms(), t0), 4*1000*1000))

    # VFS sweep: DMA + PSRAM 兩個統一緩衝都 sweep,由各自最大開始
    vfs_baseline = 0
    vfs_rows = []
    path = "/sd/bench.dat"
    vsize = 4 * 1024 * 1024
    if full:
        print("  ── VFS chunk sweep (統一緩衝, 由最大開始) ──")
        def _sweep(buf, buf_n, label):
            mv = memoryview(buf)
            kb_list = []
            k = buf_n // 1024
            while k >= 4:
                kb_list.append(k)
                k //= 2
            out = []
            for kb in kb_list:
                view = mv[:kb * 1024]
                nchunk = vsize // len(view)
                _fill_random(view)
                print("  寫入 [%s %dKB] ..." % (label, kb))
                t0 = time.ticks_ms()
                with open(path, "wb") as f:
                    for i in range(nchunk):
                        f.write(view)
                        _pct(i + 1, nchunk, "write %s %dK" % (label, kb))
                t_w = time.ticks_diff(time.ticks_ms(), t0)
                print()
                os.sync()
                print("  讀出 [%s %dKB] ..." % (label, kb))
                t0 = time.ticks_ms()
                with open(path, "rb") as f:
                    for i in range(nchunk):
                        f.readinto(view)
                        _pct(i + 1, nchunk, "read %s %dK" % (label, kb))
                t_r = time.ticks_diff(time.ticks_ms(), t0)
                print()
                out.append((label, kb, _KBps(t_w, vsize), _KBps(t_r, vsize)))
                print("  [%s %3dKB] write %7.1f KB/s  read %7.1f KB/s" % (label, kb, out[-1][2], out[-1][3]))
            return out
        if dma:
            vfs_rows.extend(_sweep(dma, dma_n, "DMA"))
        if ps:
            vfs_rows.extend(_sweep(ps, ps_n, "PSRAM"))
        try: os.remove(path)
        except: pass
        # 基準 = 最大 chunk 嘅 VFS 讀
        if vfs_rows:
            best_row = max(vfs_rows, key=lambda r: r[1])
            vfs_baseline = best_row[3]
    else:
        try:
            tf = "/sd/.hltst"; vsz = 262144; nv = vsz // 16384
            vb = _aligned(16384)
            with open(tf, "wb") as f:
                for _ in range(nv): f.write(vb)
            os.sync()
            t0 = time.ticks_ms()
            with open(tf, "rb") as f:
                for _ in range(nv): f.readinto(vb)
            vfs_baseline = _KBps(time.ticks_diff(time.ticks_ms(), t0), vsz)
            os.remove(tf)
        except: pass

    # raw 對照 + 細檔 (完整模式)
    rw = rr = 0
    tw = tr = 0
    if full:
        print("  ── raw 對照 (readblocks/writeblocks 16KB) ──")
        buf = bytearray(16384)
        _fill_random(buf)
        t0 = time.ticks_ms()
        for _ in range(16):
            sd.writeblocks(600000, buf)
        rw = _KBps(time.ticks_diff(time.ticks_ms(), t0), 16 * 16384)
        print("  raw write 16KB @600000: %.1f KB/s" % rw)
        t0 = time.ticks_ms()
        for _ in range(64):
            sd.readblocks(400000, buf)
        rr = _KBps(time.ticks_diff(time.ticks_ms(), t0), 64 * 16384)
        print("  raw read  16KB @400000: %.1f KB/s" % rr)

        print("  ── 細檔測試: 1000 × 4KB ──")
        d = "/sd/small_test"
        try: os.mkdir(d)
        except: pass
        sp = d + "/%04d.log"
        bf = bytearray(4096)
        _fill_random(bf)
        try:
            print("  寫入細檔 ...")
            t0 = time.ticks_ms()
            for n in range(1000):
                with open(sp % n, "wb") as f:
                    f.write(bf)
                _pct(n + 1, 1000, "small write")
            tw = time.ticks_diff(time.ticks_ms(), t0)
            print()
            os.sync()
            print("  讀出細檔 ...")
            t0 = time.ticks_ms()
            for n in range(1000):
                with open(sp % n, "rb") as f:
                    f.readinto(bf)
                _pct(n + 1, 1000, "small read")
            tr = time.ticks_diff(time.ticks_ms(), t0)
            print()
        finally:
            for n in range(1000):
                try: os.remove(sp % n)
                except: pass
            try: os.rmdir(d)
            except: pass

    # raw 表輸出
    print("  {:>4s} {:>3s} {:>5s}  {:>8s}  {:>8s}  {:>8s}".format("buf", "op", "chunk", "時間", "速度", "vs VFS"))
    print("  " + "─" * 46)
    best = 0
    for mem, op, bsz, ms, total in rows:
        spd = total / 1048576 / (ms / 1000) if ms else 0
        if spd > best: best = spd
    for mem, op, bsz, ms, total in rows:
        if ms == 0:
            print("  {:>4s} {:>3s} {:>5s}  {:>8s}  {:>8s}  {:>8s}".format(mem, op, bsz, "—", "—", "—"))
            continue
        spd = total / 1048576 / (ms / 1000) if ms else 0
        vs = ""
        if vfs_baseline and vfs_baseline > 0:
            # vfs_baseline 係 KB/s,spd 係 MB/s → 除 1024 先比較
            vs = "{:.1f}x".format(spd / (vfs_baseline / 1024))
        print("  {:>4s} {:>3s} {:>5s}  {:>6.1f} ms  {:>7.2f} MB/s  {:>8s}".format(mem, op, bsz, ms, spd, vs))
    print("  " + "─" * 46)

    # 完整模式: 總結表
    if full:
        print("  ── 總結 ──")
        print("  %-6s %-8s %12s %12s" % ("buffer", "chunk", "寫 KB/s", "讀 KB/s"))
        for label, kb, w, r_ in vfs_rows:
            print("  %-6s %-8s %12.1f %12.1f" % (label, "%dK" % kb, w, r_))
        print("  %-6s %-8s %12.1f %12.1f" % ("raw", "16K", rw, rr))
        sw = _KBps(tw, 1000 * 4096) if tw else 0
        sr = _KBps(tr, 1000 * 4096) if tr else 0
        print("  %-6s %-8s %12.1f %12.1f" % ("細檔", "4K", sw, sr))
        if vfs_rows:
            print("  VFS 基準 (最大 buffer %s %dK 讀): %.1f KB/s" % (best_row[0], best_row[1], vfs_baseline))
    if best > 0:
        print("  peak: {:.1f} MB/s".format(best))

    # 釋放臨時 DMA buffer (快速模式先需要)
    if base is None and dbuf is not None:
        try:
            import heap_caps
            heap_caps.free(dbuf)
        except: pass
    print()

def _vfs(path):
    print("── VFS 檔案讀寫 ({}) ──".format(path))
    tf = path.rstrip("/") + "/.hltst"
    sz = 262144; n = sz // 16384; buf = bytearray(16384)
    try:
        t0 = time.ticks_ms()
        with open(tf, "wb") as f:
            for _ in range(n): f.write(buf)
            f.flush()
        t = time.ticks_diff(time.ticks_ms(), t0)
        print("  VFS 寫: {:>7.2f} MB/s".format(sz/1048576/(t/1000) if t else 0))
        t0 = time.ticks_ms()
        with open(tf, "rb") as f:
            for _ in range(n): f.read(16384)
        t = time.ticks_diff(time.ticks_ms(), t0)
        print("  VFS 讀: {:>7.2f} MB/s".format(sz/1048576/(t/1000) if t else 0))
        os.remove(tf)
    except Exception as e: print("  (skip: {})".format(e))
    print()

def _net():
    print("── 網路 ──")
    try:
        import network
        w = network.WLAN(network.STA_IF)
        if w.active():
            print("  WiFi: 已連線  SSID: {}  IP: {}".format(w.config("ssid"), w.ifconfig()[0]))
        else:
            print("  WiFi: 未連線")
    except: print("  WiFi: N/A")
    print()

def report(full_sd=False):
    gc.collect()
    print("\n" + "╔" + "═"*54 + "╗")
    print("║" +"ESP 系統健康檢查報告".center(64) + "║")
    print("╚" + "═"*54 + "╝\n")
    _sys(); _mem()
    gc.collect()
    try:
        from lib.sys_bus import bus
        sd = bus.get_service("sd_raw")
        if sd:
            if full_sd:
                # 統一緩衝 ×2 (DMA + PSRAM): 事前申請,之後所有 SD 測試都用佢哋
                dma, dma_n, dma_desc, ps, ps_n, ps_desc = _alloc_unified()
                _sd(sd, dma, dma_n, dma_desc, ps, ps_n, ps_desc)
            else:
                _sd(sd)
    except: pass
    _net()
    print("─"*56 + "\n  ✅ 完成\n")
