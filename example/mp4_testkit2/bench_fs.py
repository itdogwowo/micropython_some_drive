import os
import time


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


def _list_jpegs(folder_path):
    files = [f for f in os.listdir(folder_path) if f.lower().endswith(".jpg") or f.lower().endswith(".jpeg")]
    files.sort()
    return [folder_path.rstrip("/") + "/" + f for f in files]


def _kb_s(moved_bytes, dt_us):
    if dt_us <= 0:
        return 0.0
    return (moved_bytes * 1000000.0) / (dt_us * 1024.0)


def bench_open_read_close(paths, loops=3, buf_size=0):
    if not paths:
        print("no files")
        return

    if buf_size <= 0:
        buf_size = max(int(os.stat(p)[6]) for p in paths)
    buf = bytearray(buf_size)
    mv = memoryview(buf)

    total_us = 0
    total_bytes = 0
    t_min = None
    t_max = 0

    for _ in range(loops):
        for p in paths:
            t0 = _ticks_us()
            with open(p, "rb") as f:
                n = f.readinto(mv)
            t1 = _ticks_us()
            dt = _ticks_diff(t1, t0)
            if n is None:
                n = 0
            total_us += dt
            total_bytes += n
            if t_min is None or dt < t_min:
                t_min = dt
            if dt > t_max:
                t_max = dt

    cnt = loops * len(paths)
    avg_us = total_us // cnt if cnt else 0
    print("open+read+close")
    print("  files :", len(paths), "loops:", loops, "ops:", cnt)
    print("  buf   :", _fmt_int(buf_size), "bytes")
    print("  avg_us:", _fmt_int(avg_us), "min_us:", _fmt_int(t_min or 0), "max_us:", _fmt_int(t_max))
    print("  KB/s  :", "{:.1f}".format(_kb_s(total_bytes, total_us)))


def bench_keep_open_sequential(path, loops=10, chunk=4096):
    size = int(os.stat(path)[6])
    buf = bytearray(chunk)
    mv = memoryview(buf)

    total_us = 0
    total_bytes = 0
    t_min = None
    t_max = 0

    with open(path, "rb") as f:
        for _ in range(loops):
            f.seek(0)
            t0 = _ticks_us()
            while True:
                n = f.readinto(mv)
                if not n:
                    break
                total_bytes += n
            t1 = _ticks_us()
            dt = _ticks_diff(t1, t0)
            total_us += dt
            if t_min is None or dt < t_min:
                t_min = dt
            if dt > t_max:
                t_max = dt

    avg_us = total_us // loops if loops else 0
    print("keep-open sequential read")
    print("  file  :", path)
    print("  size  :", _fmt_int(size), "bytes")
    print("  chunk :", _fmt_int(chunk), "bytes")
    print("  loops :", loops)
    print("  avg_us:", _fmt_int(avg_us), "min_us:", _fmt_int(t_min or 0), "max_us:", _fmt_int(t_max))
    print("  KB/s  :", "{:.1f}".format(_kb_s(total_bytes, total_us)))


def main(folder="/jpeg/background", loops=3):
    paths = _list_jpegs(folder)
    print("folder:", folder, "files:", len(paths))
    if not paths:
        return

    sample = paths[:min(10, len(paths))]
    print("sample:", sample[0])

    bench_open_read_close(sample, loops=loops, buf_size=0)
    bench_keep_open_sequential(sample[0], loops=max(5, loops), chunk=4096)


if __name__ == "__main__":
    main()
