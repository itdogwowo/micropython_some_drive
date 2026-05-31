# -*- coding: utf-8 -*-
"""ESP 系統健康檢查 — CPU/PSRAM/Flash/SD/Network 一鍵體檢

用法:
  from tests.health import report
  report()          # 完整報告
"""

import time, gc, machine, ubinascii, os, micropython

def _sz(b):
    for u in ("B","KB","MB","GB"):
        if b < 1024: return "{}{}".format(b, u)
        b //= 1024
    return "{}{}".format(b, "GB")

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

def _sd(sd):
    print("── SD 卡效能 ──")
    ss = sd.info()[1]
    cap = sd.info()[0]
    print("  容量: {} ({:.1f} GB)  sector: {}B".format(_sz(cap), cap/1073741824, ss))
    try:
        s = os.statvfs("/sd")
        print("  Cluster: {}  free: {} / {}".format(_sz(s[0]), _sz(s[3]*s[1]), _sz(s[2]*s[1])))
    except: pass
    gc.collect()
    b4k = bytearray(4096); b16k = bytearray(16384)
    for i in range(16384): b16k[i] = i & 0xFF
    try: import urandom; r = urandom.getrandbits
    except: import random; r = random.getrandbits
    max_sec = cap // ss

    try:
        import heap_caps
        d4k = heap_caps.malloc(4096, heap_caps.CAP_DMA)
        d16k = heap_caps.malloc(16384, heap_caps.CAP_DMA)
    except: d4k = d16k = None

    rows = []
    def _ms(fn, blk, buf, n):
        t0 = time.ticks_ms()
        for _ in range(n): fn(blk, buf); blk += len(buf) // ss
        return time.ticks_diff(time.ticks_ms(), t0)

    rows.append(("HEAP", "rd", "4KB",  _ms(sd.readblocks, 500000, b4k, 256),  1*1024*1024))
    rows.append(("HEAP", "rd", "16KB", _ms(sd.readblocks, 520000, b16k, 64),  1*1024*1024))
    if d4k:  rows.append(("DMA",  "rd", "4KB",  _ms(sd.readblocks, 540000, d4k, 256),  1*1024*1024))
    else:    rows.append(("DMA",  "—",  "4KB",   0, 0))
    if d16k: rows.append(("DMA",  "rd", "16KB", _ms(sd.readblocks, 560000, d16k, 64),  1*1024*1024))
    else:    rows.append(("DMA",  "—",  "16KB",  0, 0))
    rows.append(("HEAP", "wr", "16KB", _ms(sd.writeblocks, 600000, b16k, 64),  1*1024*1024))
    if d16k:
        for i in range(16384): d16k[i] = i & 0xFF
        rows.append(("DMA", "wr", "16KB", _ms(sd.writeblocks, 620000, d16k, 64), 1*1024*1024))
    t0 = time.ticks_ms()
    for _ in range(1000): sd.readblocks(r(28) % max_sec, b4k)
    rows.append(("HEAP", "rnd", "4KB", time.ticks_diff(time.ticks_ms(), t0), 4*1000*1000))
    if d4k:
        t0 = time.ticks_ms()
        for _ in range(1000): sd.readblocks(r(28) % max_sec, d4k)
        rows.append(("DMA", "rnd", "4KB", time.ticks_diff(time.ticks_ms(), t0), 4*1000*1000))

    # VFS 讀取 (從已 mount 的 /sd)
    try:
        tf="/sd/.hltst"; vsz=262144; nv=vsz//16384; vb=bytearray(16384)
        with open(tf,"wb") as f:
            for _ in range(nv): f.write(vb); f.flush()
        t0=time.ticks_ms()
        with open(tf,"rb") as f:
            for _ in range(nv): f.read(16384)
        rows.append(("VFS", "rd", "16KB", time.ticks_diff(time.ticks_ms(),t0), vsz))
        os.remove(tf)
    except: pass

    # 表格輸出
    print("  {:>4s} {:>3s} {:>5s}  {:>8s}  {:>8s}  {:>8s}".format("buf", "op", "chunk", "時間", "速度", "vs VFS"))
    print("  " + "─" * 46)
    best = 0; vfs_baseline = 0
    for mem, op, bsz, ms, total in rows:
        spd = total / 1048576 / (ms / 1000) if ms else 0
        if spd > best: best = spd
        # vs VFS 對比: 用最後一個 VFS 讀取的速度當基準
        if mem == "VFS": vfs_baseline = spd
    for mem, op, bsz, ms, total in rows:
        if ms == 0:
            print("  {:>4s} {:>3s} {:>5s}  {:>8s}  {:>8s}  {:>8s}".format(mem, op, bsz, "—", "—", "—"))
            continue
        spd = total / 1048576 / (ms / 1000) if ms else 0
        vs = ""
        if mem != "VFS" and vfs_baseline and vfs_baseline > 0:
            vs = "{:.1f}x".format(spd / vfs_baseline)
        print("  {:>4s} {:>3s} {:>5s}  {:>6.1f} ms  {:>7.2f} MB/s  {:>8s}".format(mem, op, bsz, ms, spd, vs))

    # 釋放 DMA buffer
    try:
        import heap_caps
        if d4k: heap_caps.free(d4k)
        if d16k: heap_caps.free(d16k)
    except: pass

    print("  " + "─" * 46)
    if best > 0:
        print("  peak: {:.1f} MB/s".format(best))
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

def report():
    gc.collect()
    print("\n" + "╔" + "═"*54 + "╗")
    print("║" + "  ESP 系統健康檢查報告".center(50) + "║")
    print("╚" + "═"*54 + "╝\n")
    _sys(); _mem()
    gc.collect()
    try:
        from lib.sys_bus import bus
        sd = bus.get_service("sd_raw")
        if sd: _sd(sd)
    except: pass
    # VFS 測試已合併到 _sd() 表格中
    _net()
    print("─"*56 + "\n  ✅ 完成\n")
