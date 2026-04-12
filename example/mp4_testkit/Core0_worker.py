import time


_SLEEP_US = getattr(time, "sleep_us", None)


def _yield():
    if _SLEEP_US is not None:
        _SLEEP_US(50)
    else:
        time.sleep_ms(1)


# Core0 主要工作迴圈：
# - 讀取 JPEG 檔案序列（paths）並寫入 io_hub
# - 從 frame_hub 取出已解碼 frame 顯示到 LCD
# - 可選擇性統計 FPS/耗時
# - 依 pace_ms 控制每帧節奏
def task_loop(bus):
    # 依賴的服務（由 bus 注入）
    lcd = bus.get_service("lcd")
    paths = bus.get_service("paths")

    # 執行參數（由 shared 設定）
    pace_ms = int(bus.shared.get("pace_ms", 0) or 0)
    loop_play = bool(bus.shared.get("loop_play", True))
    stats_enabled = bool(bus.shared.get("stats_enabled", False))
    stats_interval_ms = int(bus.shared.get("stats_interval_ms", 1000) or 1000)
    stats_frames_n = int(bus.shared.get("stats_frames_n", 60) or 60)

    # 統計用計數器：以 1 秒窗口與 N 帧窗口各自計算一次
    sec_t0 = time.ticks_ms()
    sec_frames = 0
    n_t0 = time.ticks_ms()
    n_frames = 0

    def _stats_on_frame():
        nonlocal sec_t0, sec_frames, n_t0, n_frames
        if not stats_enabled:
            return
        now = time.ticks_ms()
        sec_frames += 1
        n_frames += 1

        # 1 秒窗口：輸出近 1 秒內的 frame 數量與實際經過毫秒
        dt_sec = time.ticks_diff(now, sec_t0)
        if dt_sec >= stats_interval_ms:
            print("1s_frames:", sec_frames, "ms:", dt_sec)
            sec_t0 = now
            sec_frames = 0

        # N 帧窗口：輸出 N 帧累積耗時（可觀察平均每帧成本）
        if n_frames >= stats_frames_n:
            dt_n = time.ticks_diff(now, n_t0)
            print("frames:", n_frames, "ms:", dt_n)
            n_t0 = now
            n_frames = 0

    io_hub = bus.get_service("io_hub")
    frame_hub = bus.get_service("frame_hub")
    max_jpeg_bytes = int(bus.shared.get("max_jpeg_bytes", 0) or 0)
    frame_bytes = int(bus.shared.get("frame_bytes", 0) or 0)

    idx = 0
    target = frame_hub.num_buffers
    # B1. 預熱：先把 io_hub 填到足夠讓下游解碼/產生 frame（直到 frame_hub 滿到 target）
    while frame_hub.get_fill_level() < target:
        w = io_hub.get_write_view()
        if w is not None:
            p = paths[idx]
            with open(p, "rb") as f:
                n = f.readinto(w[:max_jpeg_bytes])

            # 尾端 metadata：在 max_jpeg_bytes 之後，附上 idx 與實際讀入 bytes (n)，供下游辨識
            tail_off = max_jpeg_bytes
            w[tail_off + 0] = idx & 255
            w[tail_off + 1] = (idx >> 8) & 255
            w[tail_off + 2] = (idx >> 16) & 255
            w[tail_off + 3] = (idx >> 24) & 255
            w[tail_off + 4] = (n if n else 0) & 255
            w[tail_off + 5] = ((n if n else 0) >> 8) & 255
            w[tail_off + 6] = ((n if n else 0) >> 16) & 255
            w[tail_off + 7] = ((n if n else 0) >> 24) & 255
            io_hub.commit()

            idx += 1
            if idx >= len(paths):
                if loop_play:
                    idx = 0
                else:
                    idx = len(paths) - 1
        else:
            _yield()

    # B2. 主迴圈：持續餵 JPEG 到 io_hub；同時從 frame_hub 取出已解碼 frame 顯示到 LCD
    next_due = time.ticks_ms()
    while True:
        did_work = False

        # (供給者) 盡可能把下一張 JPEG 送進 io_hub
        w = io_hub.get_write_view()
        if w is not None:
            p = paths[idx]
            with open(p, "rb") as f:
                n = f.readinto(w[:max_jpeg_bytes])

            tail_off = max_jpeg_bytes
            w[tail_off + 0] = idx & 255
            w[tail_off + 1] = (idx >> 8) & 255
            w[tail_off + 2] = (idx >> 16) & 255
            w[tail_off + 3] = (idx >> 24) & 255
            w[tail_off + 4] = (n if n else 0) & 255
            w[tail_off + 5] = ((n if n else 0) >> 8) & 255
            w[tail_off + 6] = ((n if n else 0) >> 16) & 255
            w[tail_off + 7] = ((n if n else 0) >> 24) & 255
            io_hub.commit()

            idx += 1
            if idx >= len(paths):
                if loop_play:
                    idx = 0
                else:
                    idx = len(paths) - 1
            did_work = True

        now = time.ticks_ms()
        if pace_ms <= 0 or time.ticks_diff(now, next_due) >= 0:
            r = frame_hub.get_read_view()
            if r is not None:
                lcd.write_data(r[:frame_bytes])
                frame_hub.release_read()
                _stats_on_frame()
                did_work = True
                if pace_ms > 0:
                    next_due = time.ticks_add(now, pace_ms)

        if not did_work:
            _yield()
