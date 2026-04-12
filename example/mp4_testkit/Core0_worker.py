import time

from lib.tail_codec import read_u32_le


def _yield():
    return


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
    sec_disp_us = 0
    sec_dec_us = 0
    n_disp_us = 0
    n_dec_us = 0

    def _stats_on_frame(disp_us, dec_us):
        nonlocal sec_t0, sec_frames, n_t0, n_frames, sec_disp_us, sec_dec_us, n_disp_us, n_dec_us
        if not stats_enabled:
            return
        now = time.ticks_ms()
        sec_frames += 1
        n_frames += 1
        sec_disp_us += disp_us
        sec_dec_us += dec_us
        n_disp_us += disp_us
        n_dec_us += dec_us

        # 1 秒窗口：輸出近 1 秒內的 frame 數量與實際經過毫秒
        dt_sec = time.ticks_diff(now, sec_t0)
        if dt_sec >= stats_interval_ms:
            avg_disp = sec_disp_us // sec_frames if sec_frames else 0
            avg_dec = sec_dec_us // sec_frames if sec_frames else 0
            print("1s_frames:", sec_frames, "ms:", dt_sec, "avg_disp_us:", avg_disp, "avg_dec_us:", avg_dec)
            sec_t0 = now
            sec_frames = 0
            sec_disp_us = 0
            sec_dec_us = 0

        # N 帧窗口：輸出 N 帧累積耗時（可觀察平均每帧成本）
        if n_frames >= stats_frames_n:
            dt_n = time.ticks_diff(now, n_t0)
            avg_disp = n_disp_us // n_frames if n_frames else 0
            avg_dec = n_dec_us // n_frames if n_frames else 0
            print("frames:", n_frames, "ms:", dt_n, "avg_disp_us:", avg_disp, "avg_dec_us:", avg_dec)
            n_t0 = now
            n_frames = 0
            n_disp_us = 0
            n_dec_us = 0

    io_hub = bus.get_service("io_hub")
    frame_hub = bus.get_service("frame_hub")
    max_jpeg_bytes = int(bus.shared.get("max_jpeg_bytes", 0) or 0)
    frame_bytes = int(bus.shared.get("frame_bytes", 0) or 0)

    idx = 0
    # 主迴圈：持續餵 JPEG 到 io_hub；同時從 frame_hub 取出已解碼 frame 顯示到 LCD
    while True:
        did_work = False

        r = frame_hub.get_read_view()
        if r is not None:
            dec_us = read_u32_le(r, frame_bytes + 4)
            t0 = time.ticks_us()
            try:
                lcd.write_data(r[:frame_bytes])
            finally:
                frame_hub.release_read()
            t1 = time.ticks_us()
            disp_us = time.ticks_diff(t1, t0)
            _stats_on_frame(disp_us, dec_us)
            did_work = True
        else:
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

        if not did_work:
            _yield()
