import os
import time

try:
    from lib.config_loader import load_config
    from lib.sdio_mount import mount_from_config
except Exception:
    load_config = None
    mount_from_config = None


def _ticks_us():
    if hasattr(time, "ticks_us"):
        return time.ticks_us()
    return int(time.time() * 1000000)


def _ticks_diff(a, b):
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(a, b)
    return a - b


def _fmt_int(n):
    try:
        return "{:,}".format(int(n))
    except Exception:
        return str(int(n))


def _kb_s(moved_bytes, dt_us):
    if dt_us <= 0:
        return 0.0
    return (moved_bytes * 1000000.0) / (dt_us * 1024.0)


def _mb_s(moved_bytes, dt_us):
    if dt_us <= 0:
        return 0.0
    return (moved_bytes * 1000000.0) / (dt_us * 1048576.0)


def _exists(p):
    try:
        os.stat(p)
        return True
    except Exception:
        return False


def _list_files(folder, exts=(".jpg", ".jpeg")):
    names = []
    for n in os.listdir(folder):
        ln = n.lower()
        for e in exts:
            if ln.endswith(e):
                names.append(n)
                break
    names.sort()
    return [folder.rstrip("/") + "/" + n for n in names]


def _stats_init():
    return {
        "count": 0,
        "min": None,
        "max": 0,
        "sum": 0,
        "gt_5ms": 0,
        "gt_20ms": 0,
        "gt_100ms": 0,
        "samples": [],
        "sample_cap": 1024,
    }


def _stats_add(st, v):
    st["count"] += 1
    st["sum"] += v
    if st["min"] is None or v < st["min"]:
        st["min"] = v
    if v > st["max"]:
        st["max"] = v
    if v >= 5000:
        st["gt_5ms"] += 1
    if v >= 20000:
        st["gt_20ms"] += 1
    if v >= 100000:
        st["gt_100ms"] += 1
    s = st["samples"]
    if len(s) < st["sample_cap"]:
        s.append(v)


def _stats_avg(st):
    if st["count"] <= 0:
        return 0
    return st["sum"] // st["count"]


def _percentile(sorted_vals, p):
    if not sorted_vals:
        return 0
    if p <= 0:
        return sorted_vals[0]
    if p >= 100:
        return sorted_vals[-1]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    i = int(k)
    j = i + 1
    if j >= len(sorted_vals):
        return sorted_vals[i]
    frac = k - i
    return int(sorted_vals[i] + (sorted_vals[j] - sorted_vals[i]) * frac)


def _print_stat_line(title, moved_bytes, st_us):
    avg_us = _stats_avg(st_us)
    mn = 0 if st_us["min"] is None else st_us["min"]
    mx = st_us["max"]
    print(title)
    print("  ops     :", _fmt_int(st_us["count"]))
    print("  avg_us  :", _fmt_int(avg_us), "min_us:", _fmt_int(mn), "max_us:", _fmt_int(mx))
    if st_us["count"] > 0:
        print("  >5ms    :", _fmt_int(st_us["gt_5ms"]), ">20ms:", _fmt_int(st_us["gt_20ms"]), ">100ms:", _fmt_int(st_us["gt_100ms"]))
    s = st_us.get("samples", None)
    if s:
        s2 = sorted(s)
        print("  p50_us  :", _fmt_int(_percentile(s2, 50)), "p90_us:", _fmt_int(_percentile(s2, 90)), "p99_us:", _fmt_int(_percentile(s2, 99)))
    if moved_bytes is not None:
        print("  KB/s    :", "{:.1f}".format(_kb_s(moved_bytes, st_us["sum"])))
        print("  MB/s    :", "{:.2f}".format(_mb_s(moved_bytes, st_us["sum"])))
    if avg_us > 0:
        print("  jitter  :", "{:.2f}x".format(mx / float(avg_us)))


def bench_folder_open_read_close(folder, files_n=30, loops=3, buf_size=0):
    if not _exists(folder):
        print("folder not found:", folder)
        return None

    paths = _list_files(folder)
    if not paths:
        print("no jpg/jpeg in:", folder)
        return None

    sample = paths[: min(files_n, len(paths))]
    if buf_size <= 0:
        buf_size = max(int(os.stat(p)[6]) for p in sample)
    buf = bytearray(buf_size)
    mv = memoryview(buf)

    st = _stats_init()
    moved = 0
    for _ in range(loops):
        for p in sample:
            t0 = _ticks_us()
            with open(p, "rb") as f:
                n = f.readinto(mv)
            t1 = _ticks_us()
            dt = _ticks_diff(t1, t0)
            if n is None:
                n = 0
            moved += n
            _stats_add(st, dt)

    _print_stat_line("folder open+read+close: " + folder, moved, st)
    return {"moved": moved, "us": st["sum"], "avg_us": _stats_avg(st), "min_us": st["min"], "max_us": st["max"]}


def bench_file_keep_open(path, loops=10, chunk=4096):
    if not _exists(path):
        print("file not found:", path)
        return None

    size = int(os.stat(path)[6])
    buf = bytearray(chunk)
    mv = memoryview(buf)

    st = _stats_init()
    moved = 0
    with open(path, "rb") as f:
        for _ in range(loops):
            f.seek(0)
            t0 = _ticks_us()
            while True:
                n = f.readinto(mv)
                if not n:
                    break
                moved += n
            t1 = _ticks_us()
            _stats_add(st, _ticks_diff(t1, t0))

    _print_stat_line("file keep-open sequential: " + path + " size=" + _fmt_int(size), moved, st)
    return {"moved": moved, "us": st["sum"], "avg_us": _stats_avg(st), "min_us": st["min"], "max_us": st["max"]}


def bench_pack(pack_path, loops=3):
    if not _exists(pack_path):
        print("pack not found:", pack_path)
        return None

    try:
        from lib.pack_source import PackSource
    except Exception as e:
        print("import lib.pack_source failed:", e)
        return None

    p = PackSource(pack_path, loop=True)
    buf = bytearray(int(p.max_size))
    mv = memoryview(buf)

    st = _stats_init()
    moved = 0
    frames = 0
    for _ in range(loops):
        for _ in range(int(p.count) or 0):
            idx, n, dt = p.read_next_into(mv, len(mv))
            if n is None:
                n = 0
            frames += 1
            moved += n
            _stats_add(st, dt)

    _print_stat_line("pack sequential: " + pack_path + " frames=" + _fmt_int(frames) + " max=" + _fmt_int(p.max_size), moved, st)
    return {"moved": moved, "us": st["sum"], "avg_us": _stats_avg(st), "min_us": st["min"], "max_us": st["max"]}


def bench_memcpy(total_bytes=8 * 1024 * 1024, chunk=32 * 1024, loops=10):
    try:
        import heap_caps
    except Exception:
        return None

    caps_list = []
    for name in ("CAP_INTERNAL", "CAP_DMA", "CAP_SPIRAM"):
        if hasattr(heap_caps, name):
            caps_list.append((name, getattr(heap_caps, name)))
    if not caps_list:
        return None

    iters = total_bytes // chunk
    if iters <= 0:
        iters = 1

    print("memcpy matrix total={}B chunk={}B loops={}".format(_fmt_int(total_bytes), _fmt_int(chunk), loops))

    for src_name, src_caps in caps_list:
        for dst_name, dst_caps in caps_list:
            src = heap_caps.malloc(chunk, src_caps)
            dst = heap_caps.malloc(chunk, dst_caps)
            if src is None or dst is None:
                if src is not None:
                    heap_caps.free(src)
                if dst is not None:
                    heap_caps.free(dst)
                print("  {} -> {} : OOM".format(src_name, dst_name))
                continue

            try:
                mv_src = memoryview(src)
                mv_dst = memoryview(dst)
                for i in range(chunk):
                    mv_src[i] = (i * 131 + 7) & 255

                t0 = _ticks_us()
                for _ in range(loops):
                    for _ in range(iters):
                        mv_dst[:] = mv_src
                dt = _ticks_diff(_ticks_us(), t0)
                moved = iters * chunk * loops
                print("  {} -> {} : {:.1f} KB/s ({:.2f} MB/s)".format(src_name, dst_name, _kb_s(moved, dt), _mb_s(moved, dt)))
            finally:
                heap_caps.free(dst)
                heap_caps.free(src)

    return True


def run():
    if load_config is not None and mount_from_config is not None:
        try:
            cfg = load_config()
            mp = mount_from_config(cfg)
            if mp:
                print("sd mounted:", mp)
        except Exception as e:
            print("sd mount skipped:", e)

    mounts = []
    for p in ("/sd", "/sdcard", "/SD", "/SDCARD"):
        if _exists(p):
            mounts.append(p)

    print("mounts:", mounts)
    print()

    bench_folder_open_read_close("/jpeg/background", files_n=30, loops=3)
    if _exists("/jpeg/background.jpk"):
        bench_pack("/jpeg/background.jpk", loops=3)

    for m in mounts:
        bench_folder_open_read_close(m + "/background", files_n=30, loops=3)
        if _exists(m + "/background.jpk"):
            bench_pack(m + "/background.jpk", loops=3)

    print()
    bench_memcpy()


if __name__ == "__main__":
    run()
