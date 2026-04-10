import time


def _pace(target_ms, start_ms):
    if target_ms <= 0:
        time.sleep_ms(0)
        return

    dt = time.ticks_diff(time.ticks_ms(), start_ms)
    if dt < target_ms:
        time.sleep_ms(target_ms - dt)


def task_loop(bus):
    lcd = bus.get_service("lcd")
    paths = bus.get_service("paths")

    pace_ms = int(bus.shared.get("pace_ms", 0) or 0)
    loop_play = bool(bus.shared.get("loop_play", True))
    stats_enabled = bool(bus.shared.get("stats_enabled", False))
    stats_interval_ms = int(bus.shared.get("stats_interval_ms", 1000) or 1000)
    stats_frames_n = int(bus.shared.get("stats_frames_n", 60) or 60)

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

        dt_sec = time.ticks_diff(now, sec_t0)
        if dt_sec >= stats_interval_ms:
            print("1s_frames:", sec_frames, "ms:", dt_sec)
            sec_t0 = now
            sec_frames = 0

        if n_frames >= stats_frames_n:
            dt_n = time.ticks_diff(now, n_t0)
            print("frames:", n_frames, "ms:", dt_n)
            n_t0 = now
            n_frames = 0

    if not bool(bus.shared.get("pipeline_enabled", True)):
        decoder = bus.get_service("decoder")
        frame_bytes = int(bus.shared.get("frame_bytes", 0) or 0)
        max_jpeg_bytes = int(bus.shared.get("max_jpeg_bytes", 0) or 0)
        block = bool(bus.shared.get("jpeg_block", True))
        step_blocks = int(bus.shared.get("jpeg_step_blocks", 0) or 0)

        frame_buf = bytearray(frame_bytes)
        frame_mv = memoryview(frame_buf)
        jpeg_buf = bytearray(max_jpeg_bytes)
        jpeg_mv = memoryview(jpeg_buf)

        idx = 0
        while True:
            st = time.ticks_ms()
            p = paths[idx]
            with open(p, "rb") as f:
                n = f.readinto(jpeg_mv)

            if n:
                if block and step_blocks > 0:
                    done = False
                    while not done:
                        done = decoder.decode_into(jpeg_mv[:n], frame_mv, blocks=step_blocks)
                else:
                    decoder.decode_into(jpeg_mv[:n], frame_mv)
                lcd.write_data(frame_mv)
                _stats_on_frame()

            idx += 1
            if idx >= len(paths):
                if loop_play:
                    idx = 0
                else:
                    idx = len(paths) - 1

            _pace(pace_ms, st)

    io_hub = bus.get_service("io_hub")
    frame_hub = bus.get_service("frame_hub")
    max_jpeg_bytes = int(bus.shared.get("max_jpeg_bytes", 0) or 0)
    frame_bytes = int(bus.shared.get("frame_bytes", 0) or 0)

    idx = 0
    target = frame_hub.num_buffers
    while frame_hub.get_fill_level() < target:
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
        else:
            time.sleep_ms(0)

    while True:
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

        r = frame_hub.get_read_view()
        if r is not None:
            st = time.ticks_ms()
            lcd.write_data(r[:frame_bytes])
            frame_hub.release_read()
            _stats_on_frame()
            _pace(pace_ms, st)

        if pace_ms <= 0:
            time.sleep_ms(0)
