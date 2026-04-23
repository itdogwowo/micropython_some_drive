import time

from lib.pack_source import PackSource


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


def main(path="/jpeg/background.jpk", loops=5):
    p = PackSource(path, loop=True)
    print("pack:", path, "count:", p.count, "max_size:", p.max_size)
    buf = bytearray(int(p.max_size))
    mv = memoryview(buf)

    total_us = 0
    total_bytes = 0
    t_min = None
    t_max = 0
    frames = 0

    for _ in range(loops):
        for _ in range(p.count):
            t0 = _ticks_us()
            idx, n, dt = p.read_next_into(mv, len(mv))
            t1 = _ticks_us()
            real_dt = _ticks_diff(t1, t0)
            if n is None:
                n = 0
            frames += 1
            total_us += dt
            total_bytes += n
            if t_min is None or dt < t_min:
                t_min = dt
            if dt > t_max:
                t_max = dt
            if real_dt > dt:
                pass

    avg_us = total_us // frames if frames else 0
    if total_us > 0:
        kb_s = (total_bytes * 1000000.0) / (total_us * 1024.0)
    else:
        kb_s = 0.0
    print("frames:", frames, "loops:", loops)
    print("avg_us:", _fmt_int(avg_us), "min_us:", _fmt_int(t_min or 0), "max_us:", _fmt_int(t_max))
    print("KB/s :", "{:.1f}".format(kb_s))


if __name__ == "__main__":
    main()
