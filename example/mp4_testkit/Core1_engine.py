import time

from lib.tail_codec import read_u32_le, write_u32_le


def task_loop(bus):
    io_hub = bus.get_service("io_hub")
    frame_hub = bus.get_service("frame_hub")
    decoder = bus.get_service("decoder")

    max_jpeg_bytes = int(bus.shared.get("max_jpeg_bytes", 0) or 0)
    frame_bytes = int(bus.shared.get("frame_bytes", 0) or 0)
    step_blocks = int(bus.shared.get("jpeg_step_blocks", 0) or 0)
    block = bool(bus.shared.get("jpeg_block", True))

    bus.shared["core1_ready"] = True

    while bus.shared.get("engine_run", True):
        in_view = io_hub.get_read_view()
        if in_view is None:
            time.sleep_ms(0)
            continue

        tail_off = max_jpeg_bytes
        frame_idx = read_u32_le(in_view, tail_off + 0)
        n = read_u32_le(in_view, tail_off + 4)

        if n <= 0:
            io_hub.release_read()
            time.sleep_ms(0)
            continue

        out_view = frame_hub.get_write_view()
        while out_view is None:
            time.sleep_ms(0)
            out_view = frame_hub.get_write_view()

        t0 = time.ticks_us()
        try:
            if block and step_blocks > 0:
                done = False
                while not done:
                    done = decoder.decode_into(in_view[:n], out_view[:frame_bytes], blocks=step_blocks)
            else:
                decoder.decode_into(in_view[:n], out_view[:frame_bytes])
        except Exception:
            io_hub.release_read()
            time.sleep_ms(1)
            continue
        t1 = time.ticks_us()

        hdr_off = frame_bytes
        write_u32_le(out_view, hdr_off + 0, frame_idx)
        dec_us = time.ticks_diff(t1, t0)
        write_u32_le(out_view, hdr_off + 4, dec_us)
        frame_hub.commit()
        io_hub.release_read()
