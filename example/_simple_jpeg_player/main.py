class JpegPlayer:
    def __init__(
        self,
        lcd,
        decoder,
        folder_path,
        files,
        jpeg_mv,
        frame_mv,
        width,
        height,
        bytes_per_pixel,
        block,
        step_blocks,
        fps_ms,
        uart,
        stats_cfg,
        pixel_format,
    ):
        self.lcd = lcd
        self.decoder = decoder
        self.folder_path = folder_path
        self.files = files
        self.jpeg_mv = jpeg_mv
        self.frame_mv = frame_mv
        self.width = width
        self.height = height
        self.bytes_per_pixel = bytes_per_pixel
        self.block = block
        self.step_blocks = step_blocks
        self.fps_ms = fps_ms
        self.uart = uart
        self.pixel_format = pixel_format
        self.pipeline_enabled = False

        self.index = 0
        self.paused = False
        self.stopped = False
        self._goto_mode = False
        self._num = ""

        self._stats_enabled = bool((stats_cfg or {}).get("enabled", False))
        self._stats_cfg = stats_cfg or {}
        self._stats_on_screen = bool((stats_cfg or {}).get("on_screen", True))
        self._stats_print = bool((stats_cfg or {}).get("print", False))
        self._stats_interval_ms = int((stats_cfg or {}).get("interval_ms", 500))
        self._stats_x = int((stats_cfg or {}).get("x", 0))
        self._stats_y = int((stats_cfg or {}).get("y", 0))
        self._stats_w = int((stats_cfg or {}).get("w", self.width))
        self._stats_h = int((stats_cfg or {}).get("h", 16))
        self._stats_fg = int((stats_cfg or {}).get("fg_rgb565", 65535))
        self._stats_bg = int((stats_cfg or {}).get("bg_rgb565", 0))

        self._avg_dec_us = 0
        self._avg_wr_us = 0
        self._avg_read_us = 0
        self._avg_total_us = 0
        self._prod_loop_us = 0
        self._prod_dec_us = 0
        self._cons_loop_us = 0
        self._stat_last_ms = 0
        self._bench_last_ms = 0
        self._stats_text_display = None
        self._stats_text_print = None
        self._stats_inited = False
        self._stats_buf = None
        self._stats_mv = None

    def pause(self):
        self.paused = True

    def resume(self):
        self.stopped = False
        self.paused = False
        self.render()

    def toggle_pause(self):
        if self.paused and not self.stopped:
            self.paused = False
        else:
            self.paused = True

    def stop(self):
        self.stopped = True
        self.paused = True
        self._write_black()

    def goto(self, frame_index):
        if not self.files:
            return
        self.index = int(frame_index) % len(self.files)
        if not self.stopped:
            self.render()

    def next(self):
        self.goto(self.index + 1)

    def prev(self):
        self.goto(self.index - 1)

    def _write_black(self):
        total = self.width * self.height * self.bytes_per_pixel
        chunk = bytes(1024)
        self.lcd.set_window(0, 0)
        remaining = total
        while remaining > 0:
            n = 1024 if remaining >= 1024 else remaining
            self.lcd.write_data(chunk[:n])
            remaining -= n

    def _stats_pack16(self, v):
        if self.pixel_format.endswith("_LE"):
            return bytes([v & 255, (v >> 8) & 255])
        return bytes([(v >> 8) & 255, v & 255])

    def _stats_init(self):
        if self._stats_inited:
            return
        if not self._stats_enabled:
            self._stats_on_screen = False
            self._stats_print = False
            self._stats_inited = True
            return
        if self.bytes_per_pixel != 2:
            self._stats_on_screen = False
        w = self._stats_w
        h = self._stats_h
        if w <= 0:
            w = self.width
        if h <= 0:
            h = 16
        if w > self.width:
            w = self.width
        if h > self.height:
            h = self.height
        self._stats_w = w
        self._stats_h = h
        if self._stats_on_screen:
            mode = self._stats_cfg.get("mode", "overlay")
            if mode == "blit":
                self._stats_buf = bytearray(w * h * 2)
                self._stats_mv = memoryview(self._stats_buf)
        self._stats_inited = True

    def _fmt_ms10_from_us(self, us):
        if us <= 0:
            return "0.0"
        ms10 = int(us) // 100
        return str(ms10 // 10) + "." + str(ms10 % 10)

    def _bench_text(self):
        c0 = self._fmt_ms10_from_us(self._cons_loop_us)
        c1 = self._fmt_ms10_from_us(self._prod_loop_us)
        return "c0:" + c0 + " c1:" + c1

    def _bench_should_print(self):
        if not self._stats_print:
            return False
        import time

        now = time.ticks_ms()
        if self._bench_last_ms == 0:
            self._bench_last_ms = now
            return True
        if time.ticks_diff(now, self._bench_last_ms) >= self._stats_interval_ms:
            self._bench_last_ms = now
            return True
        return False

    def _bench_print(self):
        if not self._bench_should_print():
            return
        print(
            "lcd_write_ms=" + str(self._avg_wr_us / 1000) +
            " consumer_loop_ms=" + str(self._cons_loop_us / 1000) +
            " producer_loop_ms=" + str(self._prod_loop_us / 1000) +
            " decode_ms=" + str(self._prod_dec_us / 1000)
        )

    def _stats_update_avg(self, dec_us, wr_us):
        if self._avg_dec_us == 0:
            self._avg_dec_us = dec_us
        else:
            self._avg_dec_us = (self._avg_dec_us * 7 + dec_us * 3) // 10
        if self._avg_wr_us == 0:
            self._avg_wr_us = wr_us
        else:
            self._avg_wr_us = (self._avg_wr_us * 7 + wr_us * 3) // 10

    def _stats_update_avg_extra(self, read_us, total_us):
        if self._avg_read_us == 0:
            self._avg_read_us = read_us
        else:
            self._avg_read_us = (self._avg_read_us * 7 + read_us * 3) // 10
        if self._avg_total_us == 0:
            self._avg_total_us = total_us
        else:
            self._avg_total_us = (self._avg_total_us * 7 + total_us * 3) // 10

    def _stats_fps10(self, avg_us):
        if avg_us <= 0:
            return 0
        return (10_000_000 // avg_us)

    def _stats_fmt_fps10(self, fps10):
        a = fps10 // 10
        b = fps10 % 10
        return str(a) + "." + str(b)

    def _stats_font(self):
        return {
            " ": [0, 0, 0, 0, 0, 0, 0],
            "0": [14, 17, 19, 21, 25, 17, 14],
            "1": [4, 12, 4, 4, 4, 4, 14],
            "2": [14, 17, 1, 2, 4, 8, 31],
            "3": [14, 17, 1, 6, 1, 17, 14],
            "4": [2, 6, 10, 18, 31, 2, 2],
            "5": [31, 16, 30, 1, 1, 17, 14],
            "6": [6, 8, 16, 30, 17, 17, 14],
            "7": [31, 1, 2, 4, 8, 8, 8],
            "8": [14, 17, 17, 14, 17, 17, 14],
            "9": [14, 17, 17, 15, 1, 2, 12],
            ".": [0, 0, 0, 0, 0, 12, 12],
            ":": [0, 12, 12, 0, 12, 12, 0],
            "D": [30, 17, 17, 17, 17, 17, 30],
            "W": [17, 17, 17, 21, 21, 21, 10],
        }

    def _stats_draw_text_into(self, mv, w, h, text):
        fg = self._stats_fg & 65535
        bg = self._stats_bg & 65535
        fg2 = self._stats_pack16(fg)
        bg2 = self._stats_pack16(bg)

        for i in range(0, len(mv), 2):
            mv[i] = bg2[0]
            mv[i + 1] = bg2[1]

        font = self._stats_font()
        x = 0
        scale = 2 if h >= 14 else 1
        cell_w = 6 * scale
        cell_h = 7 * scale
        if cell_h > h:
            scale = 1
            cell_w = 6
            cell_h = 7
        y0 = (h - cell_h) // 2
        flip_x = bool(self._stats_cfg.get("flip_x", False))

        for ch in text:
            if x + cell_w > w:
                break
            rows = font.get(ch, font[" "])
            for ry in range(7):
                bits = rows[ry]
                for rx in range(5):
                    if bits & (1 << (rx if flip_x else (4 - rx))):
                        for sy in range(scale):
                            yy = y0 + ry * scale + sy
                            if yy >= h:
                                continue
                            for sx in range(scale):
                                xx = x + rx * scale + sx
                                if xx >= w:
                                    continue
                                idx = (yy * w + xx) * 2
                                mv[idx] = fg2[0]
                                mv[idx + 1] = fg2[1]
            x += cell_w

    def _stats_overlay(self, text):
        if not self._stats_on_screen:
            return
        if self.bytes_per_pixel != 2:
            return
        x0 = self._stats_x
        y0 = self._stats_y
        w = self._stats_w
        h = self._stats_h
        if x0 < 0:
            x0 = 0
        if y0 < 0:
            y0 = 0
        if x0 >= self.width or y0 >= self.height:
            return
        if x0 + w > self.width:
            w = self.width - x0
        if y0 + h > self.height:
            h = self.height - y0
        if w <= 0 or h <= 0:
            return

        fg = self._stats_fg & 65535
        bg = self._stats_bg & 65535
        fg2 = self._stats_pack16(fg)
        bg2 = self._stats_pack16(bg)
        font = self._stats_font()

        fb = self.frame_mv
        for yy in range(h):
            base = ((y0 + yy) * self.width + x0) * 2
            for xx in range(w):
                i = base + xx * 2
                fb[i] = bg2[0]
                fb[i + 1] = bg2[1]

        scale = 2 if h >= 14 else 1
        cell_w = 6 * scale
        cell_h = 7 * scale
        if cell_h > h:
            scale = 1
            cell_w = 6
            cell_h = 7
        ytxt0 = y0 + (h - cell_h) // 2
        flip_x = bool(self._stats_cfg.get("flip_x", False))

        x = x0
        for ch in text:
            if x + cell_w > x0 + w:
                break
            rows = font.get(ch, font[" "])
            for ry in range(7):
                bits = rows[ry]
                for rx in range(5):
                    if bits & (1 << (rx if flip_x else (4 - rx))):
                        for sy in range(scale):
                            yy = ytxt0 + ry * scale + sy
                            if yy >= y0 + h:
                                continue
                            for sx in range(scale):
                                xx = x + rx * scale + sx
                                if xx >= x0 + w:
                                    continue
                                i = (yy * self.width + xx) * 2
                                fb[i] = fg2[0]
                                fb[i + 1] = fg2[1]
            x += cell_w

    def _stats_blit(self, text):
        if not self._stats_on_screen:
            return
        if self._stats_mv is None:
            return
        self._stats_draw_text_into(self._stats_mv, self._stats_w, self._stats_h, text)
        x = self._stats_x
        y = self._stats_y
        w0 = self._stats_w
        h0 = self._stats_h
        self.lcd.set_window(x, y, x + w0 - 1, y + h0 - 1)
        self.lcd.write_data(self._stats_mv)
        self.lcd.set_window(0, 0)

    def _stats_prepare_text(self):
        return None

    def _handle_uart(self):
        if self.uart is None:
            return
        n = self.uart.any()
        if not n:
            return
        data = self.uart.read()
        if not data:
            return
        for b in data:
            self._handle_key(b)

    def _handle_key(self, b):
        ch = chr(b)
        if ch in "Uu":
            self.prev()
            return
        if ch in "Rr":
            self.next()
            return
        if ch in "Pp":
            self.toggle_pause()
            return
        if ch in "Ss":
            self.stop()
            return
        if ch in "Aa":
            self.resume()
            return
        if ch in "Gg":
            self._goto_mode = True
            self._num = ""
            return
        if "0" <= ch <= "9":
            if not self._goto_mode:
                self._goto_mode = True
                self._num = ""
            self._num += ch
            return
        if ch in "\r\n":
            if self._goto_mode and self._num:
                self.goto(int(self._num))
            self._goto_mode = False
            self._num = ""

    def render(self):
        import time

        self._stats_init()
        if not self.files:
            return
        path = self._paths[self.index]
        t_read0 = time.ticks_us()
        with open(path, "rb") as fp:
            n = fp.readinto(self.jpeg_mv)
        t_read1 = time.ticks_us()
        if n <= 0:
            return

        t0 = time.ticks_us()
        if self.block and self.step_blocks > 0:
            done = False
            while not done:
                self._handle_uart()
                if self.stopped:
                    return
                done = self.decoder.decode_into(self.jpeg_mv[:n], self.frame_mv, blocks=self.step_blocks)
        else:
            self.decoder.decode_into(self.jpeg_mv[:n], self.frame_mv)
        t1 = time.ticks_us()

        if not self.stopped:
            self.lcd.set_window(0, 0)
            t2 = time.ticks_us()
            self.lcd.write_data(self.frame_mv)
            t3 = time.ticks_us()
            dec_us = time.ticks_diff(t1, t0)
            wr_us = time.ticks_diff(t3, t2)
            read_us = time.ticks_diff(t_read1, t_read0)
            total_us = time.ticks_diff(t3, t_read0)
            self._stats_update_avg(dec_us, wr_us)
            self._stats_update_avg_extra(read_us, total_us)
            self._prod_dec_us = self._avg_dec_us
            self._prod_loop_us = self._avg_dec_us
            self._cons_loop_us = total_us
            self._bench_print()

    def run(self, autoplay=True):
        import time

        if autoplay and not self.stopped:
            self.render()

        if self.fps_ms <= 0:
            while True:
                self._handle_uart()

                if self.stopped:
                    time.sleep_ms(10)
                    continue

                if self.paused:
                    time.sleep_ms(10)
                    continue

                self.next()
                time.sleep_ms(0)
            return

        next_tick = time.ticks_ms()
        while True:
            self._handle_uart()

            if self.stopped:
                time.sleep_ms(10)
                continue

            if self.paused:
                time.sleep_ms(10)
                continue

            now = time.ticks_ms()
            if time.ticks_diff(now, next_tick) >= 0:
                self.next()
                next_tick = time.ticks_add(next_tick, self.fps_ms)
            else:
                time.sleep_ms(1)


class BufferedJpegPlayer(JpegPlayer):
    def __init__(
        self,
        lcd,
        decoder,
        folder_path,
        files,
        jpeg_mv,
        frame_mv,
        width,
        height,
        bytes_per_pixel,
        block,
        step_blocks,
        fps_ms,
        uart,
        stats_cfg,
        pixel_format,
        hub,
        state,
        lock,
        decode_stats,
    ):
        super().__init__(
            lcd=lcd,
            decoder=decoder,
            folder_path=folder_path,
            files=files,
            jpeg_mv=jpeg_mv,
            frame_mv=frame_mv,
            width=width,
            height=height,
            bytes_per_pixel=bytes_per_pixel,
            block=block,
            step_blocks=step_blocks,
            fps_ms=fps_ms,
            uart=uart,
            stats_cfg=stats_cfg,
            pixel_format=pixel_format,
        )
        self._hub = hub
        self._state = state
        self._lock = lock
        self._decode_stats = decode_stats
        self.pipeline_enabled = True

        self._disp_last_us = 0
        self._avg_disp_us = 0
        self._avg_cons_wait_frame_us = 0
        self._cons_last_loop_us = 0
        self._avg_cons_loop_us = 0
        self._cons_frames = 0
        self._cons_poll_wait_us = 0
        self._cons_poll_wait_polls = 0

    def pause(self):
        with self._lock:
            self._state["paused"] = True
        super().pause()

    def resume(self):
        with self._lock:
            self._state["stopped"] = False
            self._state["paused"] = False
        self.stopped = False
        self.paused = False

    def toggle_pause(self):
        with self._lock:
            paused = bool(self._state.get("paused", False))
            stopped = bool(self._state.get("stopped", False))
            if paused and not stopped:
                self._state["paused"] = False
            else:
                self._state["paused"] = True
        super().toggle_pause()

    def stop(self):
        with self._lock:
            self._state["stopped"] = True
            self._state["paused"] = True
            self._state["dirty"] = False
        self.stopped = True
        self.paused = True
        self._hub.flush()
        self.frame_mv = None
        self._write_black()

    def goto(self, frame_index):
        if not self.files:
            return
        idx = int(frame_index) % len(self.files)
        with self._lock:
            self._state["request_index"] = idx
            self._state["dirty"] = True
            self._state["direction"] = 1
            self._state["stopped"] = False
            self._state["paused"] = False
        self.stopped = False
        self.paused = False
        self.index = idx
        self._hub.flush()

    def next(self):
        self.goto(self.index + 1)

    def prev(self):
        self.goto(self.index - 1)

    def _update_disp_avg(self, dt_us):
        if self._avg_disp_us == 0:
            self._avg_disp_us = dt_us
        else:
            self._avg_disp_us = (self._avg_disp_us * 7 + dt_us * 3) // 10

    def _update_cons_loop_avg(self, dt_us):
        if self._avg_cons_loop_us == 0:
            self._avg_cons_loop_us = dt_us
        else:
            self._avg_cons_loop_us = (self._avg_cons_loop_us * 7 + dt_us * 3) // 10

    def _update_cons_wait_avg(self, dt_us):
        if self._avg_cons_wait_frame_us == 0:
            self._avg_cons_wait_frame_us = dt_us
        else:
            self._avg_cons_wait_frame_us = (self._avg_cons_wait_frame_us * 7 + dt_us * 3) // 10

    def render(self):
        import time

        self._stats_init()

        t_loop0 = time.ticks_us()
        mv = self._hub.get_read_view()
        if mv is not None:
            self.frame_mv = mv

        poll_wait_us = self._cons_poll_wait_us
        poll_wait_polls = self._cons_poll_wait_polls
        self._cons_poll_wait_us = 0
        self._cons_poll_wait_polls = 0

        if self.frame_mv is None:
            t_loop1 = time.ticks_us()
            self._update_cons_wait_avg(time.ticks_diff(t_loop1, t_loop0))
            return False

        with self._lock:
            produced = self._state.get("produced_index", None)
        if produced is not None:
            self.index = int(produced)

        with self._lock:
            self._avg_dec_us = int(self._decode_stats.get("avg_dec_us", self._avg_dec_us))
            self._avg_read_us = int(self._decode_stats.get("avg_read_us", self._avg_read_us))
            prod_loop_us = int(self._decode_stats.get("avg_loop_us", 0))
            prod_wait_us = int(self._decode_stats.get("avg_wait_view_us", 0))
            prod_wait_polls = int(self._decode_stats.get("avg_wait_polls", 0))
            prod_commit_us = int(self._decode_stats.get("avg_commit_us", 0))
            prod_frames = int(self._decode_stats.get("frames", 0))

        t2 = time.ticks_us()
        self.lcd.set_window(0, 0)
        self.lcd.write_data(self.frame_mv)
        t3 = time.ticks_us()

        wr_us = time.ticks_diff(t3, t2)
        self._stats_update_avg(self._avg_dec_us, wr_us)
        self._prod_dec_us = self._avg_dec_us
        self._prod_loop_us = prod_loop_us

        if self._disp_last_us:
            self._update_disp_avg(time.ticks_diff(t3, self._disp_last_us))
            self._avg_total_us = self._avg_disp_us
        self._disp_last_us = t3
        self._cons_frames += 1

        t_loop1 = time.ticks_us()
        self._update_cons_loop_avg(time.ticks_diff(t_loop1, t_loop0))
        self._cons_loop_us = self._avg_cons_loop_us

        if self._stats_on_screen:
            self._stats_overlay(self._bench_text())
        self._bench_print()

        return True


    def run(self, autoplay=True):
        import time

        if autoplay and not self.stopped:
            self.render()

        if self.fps_ms <= 0:
            while True:
                self._handle_uart()
                with self._lock:
                    if self._state.get("stopped", False) or self._state.get("paused", False):
                        time.sleep_ms(10)
                        continue
                    self._state["request_index"] = (int(self._state.get("request_index", self.index)) + 1) % len(self.files)
                    self._state["dirty"] = True
                t0 = time.ticks_us()
                ok = self.render()
                t1 = time.ticks_us()
                if not ok:
                    self._cons_poll_wait_polls += 1
                    self._cons_poll_wait_us += time.ticks_diff(t1, t0)
                time.sleep_ms(0)
            return

        next_tick = time.ticks_ms()
        while True:
            self._handle_uart()

            with self._lock:
                if self._state.get("stopped", False):
                    time.sleep_ms(10)
                    continue
                if self._state.get("paused", False):
                    time.sleep_ms(10)
                    continue

            now = time.ticks_ms()
            if time.ticks_diff(now, next_tick) >= 0:
                with self._lock:
                    self._state["request_index"] = (int(self._state.get("request_index", self.index)) + 1) % len(self.files)
                    self._state["dirty"] = True
                next_tick = time.ticks_add(next_tick, self.fps_ms)
            t0 = time.ticks_us()
            ok = self.render()
            t1 = time.ticks_us()
            if not ok:
                self._cons_poll_wait_polls += 1
                self._cons_poll_wait_us += time.ticks_diff(t1, t0)
            time.sleep_ms(0)


PLAYER = None


def _init_uart(cfg):
    uart_cfg = (cfg.get("control") or {}).get("uart") if cfg else None
    if not uart_cfg:
        return None
    if not bool(uart_cfg.get("enabled", False)):
        return None
    from machine import UART, Pin

    uart_id = int(uart_cfg.get("id", 0))
    baudrate = int(uart_cfg.get("baudrate", 115200))
    rx = uart_cfg.get("rx", None)
    tx = uart_cfg.get("tx", None)

    try:
        if rx is None and tx is None:
            return UART(uart_id, baudrate=baudrate)
        kwargs = {"baudrate": baudrate}
        if rx is not None:
            kwargs["rx"] = Pin(int(rx))
        if tx is not None:
            kwargs["tx"] = Pin(int(tx))
        return UART(uart_id, **kwargs)
    except Exception:
        try:
            return UART(uart_id, baudrate=baudrate)
        except Exception:
            return None


def main():
    from machine import SPI, Pin
    import json
    import jpeg
    import os
    import time

    time.sleep_ms(500)

    cfg_path = "/jpeg/dp_config.json"
    try:
        with open(cfg_path, "r") as f:
            cfg = json.load(f)
    except OSError:
        cfg_path = "/jepg/dp_config.json"
        with open(cfg_path, "r") as f:
            cfg = json.load(f)

    assets_root = cfg.get("assets_root", "/jpeg").rstrip("/")
    tft_cfg = cfg.get("tft", {}) or {}
    jpeg_cfg = cfg.get("jpeg", {})
    player_cfg = cfg.get("player", {}) or {}
    layout = (cfg.get("display_Layout") or [{}])[0]

    width = int(tft_cfg.get("width", layout.get("width", 240)))
    height = int(tft_cfg.get("height", layout.get("height", 240)))
    folder = layout.get("type", "background")
    folder_path = assets_root + "/" + folder

    pixel_format = jpeg_cfg.get("pixel_format", "RGB565_LE")
    rotation = int(jpeg_cfg.get("rotation", 0))
    block = bool(jpeg_cfg.get("block", True))
    return_bytes = bool(jpeg_cfg.get("return_bytes", False))
    step_blocks = int(jpeg_cfg.get("step_blocks", 0))
    fps_ms = int(player_cfg.get("fps_ms", 33))
    autoplay = bool(player_cfg.get("autoplay", True))
    pipeline_cfg = player_cfg.get("pipeline", {}) or {}
    pipeline_enabled = bool(pipeline_cfg.get("enabled", False))
    pipeline_num_buffers = int(pipeline_cfg.get("num_buffers", 3))

    decoder = jpeg.Decoder(
        pixel_format=pixel_format,
        rotation=rotation,
        block=block,
        return_bytes=return_bytes,
    )

    bytes_per_pixel = 3 if pixel_format == "RGB888" else 2
    frame_buf = bytearray(width * height * bytes_per_pixel)
    frame_mv = memoryview(frame_buf)

    files = [
        f
        for f in os.listdir(folder_path)
        if f.lower().endswith(".jpeg") or f.lower().endswith(".jpg")
    ]
    files.sort()
    if not files:
        raise OSError("No JPEG files in: " + folder_path)
    paths = [folder_path + "/" + f for f in files]

    max_jpeg_bytes = int(jpeg_cfg.get("max_jpeg_bytes", 0))
    if max_jpeg_bytes <= 0:
        for f in files:
            sz = os.stat(folder_path + "/" + f)[6]
            if sz > max_jpeg_bytes:
                max_jpeg_bytes = sz
        if max_jpeg_bytes <= 0:
            max_jpeg_bytes = 64 * 1024

    jpeg_buf = bytearray(max_jpeg_bytes)
    jpeg_mv = memoryview(jpeg_buf)

    spi_cfg = tft_cfg.get("spi", {}) or {}
    pins_cfg = tft_cfg.get("pins", {}) or {}

    spi_id = int(spi_cfg.get("id", 1))
    spi_baudrate = int(spi_cfg.get("baudrate", 80_000_000))
    spi_sck = int(spi_cfg.get("sck", 8))
    spi_mosi = int(spi_cfg.get("mosi", 7))

    dc_pin = int(pins_cfg.get("dc", 13))
    cs_pin = int(pins_cfg.get("cs", 10))
    rst_pin = int(pins_cfg.get("rst", 14))

    tft_spi = SPI(spi_id, baudrate=spi_baudrate, sck=Pin(spi_sck), mosi=Pin(spi_mosi))

    driver_name = tft_cfg.get("driver", "GC9A01")
    rotation = int(tft_cfg.get("rotation", 0))
    color_order = tft_cfg.get("color_order", "RGB")
    invert = bool(tft_cfg.get("invert", True))

    tft_mod = __import__("lib.TFT", None, None, ["*"])
    driver_cls = getattr(tft_mod, driver_name)

    lcd = driver_cls(
        spi=tft_spi,
        dc=Pin(dc_pin, Pin.OUT),
        cs=Pin(cs_pin, Pin.OUT),
        rst=Pin(rst_pin, Pin.OUT),
        width=width,
        height=height,
        rotation=rotation,
        color_order=color_order,
        invert=invert,
    )
    lcd.set_window(0, 0)

    uart = _init_uart(cfg)

    global PLAYER
    stats_cfg = (player_cfg.get("stats") or {})

    if pipeline_enabled:
        try:
            import _thread
            from lib.buffer_hub import AtomicStreamHub
        except Exception:
            pipeline_enabled = False

    if pipeline_enabled:
        frame_size = width * height * bytes_per_pixel
        hub = AtomicStreamHub(frame_size, num_buffers=pipeline_num_buffers)
        lock = _thread.allocate_lock()
        state = {
            "paused": False,
            "stopped": False,
            "request_index": 0,
            "dirty": True,
            "produced_index": None,
            "next_index": 0,
            "direction": 1,
        }
        decode_stats = {"avg_read_us": 0, "avg_dec_us": 0}

        max_jpeg_bytes2 = max_jpeg_bytes
        if max_jpeg_bytes2 <= 0:
            max_jpeg_bytes2 = 64 * 1024
        jpeg_buf2 = bytearray(max_jpeg_bytes2)
        jpeg_mv2 = memoryview(jpeg_buf2)

        def _avg(old, new):
            if old == 0:
                return new
            return (old * 7 + new * 3) // 10

        def _decode_worker():
            import time
            last_idx = -1
            while True:
                t_loop0 = time.ticks_us()
                with lock:
                    if state.get("stopped", False) or state.get("paused", False):
                        time.sleep_ms(10)
                        continue
                    dirty = bool(state.get("dirty", False))
                    idx = int(state.get("request_index", 0)) % len(files)

                if not dirty or idx == last_idx:
                    time.sleep_ms(0)
                    continue

                t_wait0 = time.ticks_us()
                wait_polls = 0
                view = hub.get_write_view()
                while view is None:
                    wait_polls += 1
                    time.sleep_ms(0)
                    view = hub.get_write_view()
                t_wait1 = time.ticks_us()

                path = paths[idx]

                t_read0 = time.ticks_us()
                try:
                    with open(path, "rb") as fp:
                        n = fp.readinto(jpeg_mv2)
                except Exception:
                    time.sleep_ms(1)
                    continue
                t_read1 = time.ticks_us()
                if n <= 0:
                    time.sleep_ms(0)
                    continue

                t_dec0 = time.ticks_us()
                try:
                    if block and step_blocks > 0:
                        done = False
                        while not done:
                            with lock:
                                if state.get("stopped", False) or state.get("paused", False):
                                    break
                            done = decoder.decode_into(jpeg_mv2[:n], view, blocks=step_blocks)
                        if not done:
                            time.sleep_ms(0)
                            continue
                    else:
                        decoder.decode_into(jpeg_mv2[:n], view)
                except Exception:
                    time.sleep_ms(1)
                    continue
                t_dec1 = time.ticks_us()

                t_commit0 = time.ticks_us()
                hub.commit()
                t_commit1 = time.ticks_us()

                read_us = time.ticks_diff(t_read1, t_read0)
                dec_us = time.ticks_diff(t_dec1, t_dec0)
                wait_us = time.ticks_diff(t_wait1, t_wait0)
                commit_us = time.ticks_diff(t_commit1, t_commit0)
                loop_us = time.ticks_diff(t_commit1, t_loop0)
                with lock:
                    decode_stats["avg_read_us"] = _avg(int(decode_stats.get("avg_read_us", 0)), int(read_us))
                    decode_stats["avg_dec_us"] = _avg(int(decode_stats.get("avg_dec_us", 0)), int(dec_us))
                    decode_stats["avg_wait_view_us"] = _avg(int(decode_stats.get("avg_wait_view_us", 0)), int(wait_us))
                    decode_stats["avg_wait_polls"] = _avg(int(decode_stats.get("avg_wait_polls", 0)), int(wait_polls))
                    decode_stats["avg_commit_us"] = _avg(int(decode_stats.get("avg_commit_us", 0)), int(commit_us))
                    decode_stats["avg_loop_us"] = _avg(int(decode_stats.get("avg_loop_us", 0)), int(loop_us))
                    decode_stats["frames"] = int(decode_stats.get("frames", 0)) + 1
                    state["produced_index"] = idx
                    if int(state.get("request_index", idx)) == idx:
                        state["dirty"] = False
                last_idx = idx

                time.sleep_ms(0)

        _thread.start_new_thread(_decode_worker, ())

        player = BufferedJpegPlayer(
            lcd=lcd,
            decoder=decoder,
            folder_path=folder_path,
            files=files,
            jpeg_mv=jpeg_mv,
            frame_mv=frame_mv,
            width=width,
            height=height,
            bytes_per_pixel=bytes_per_pixel,
            block=block,
            step_blocks=step_blocks,
            fps_ms=fps_ms,
            uart=uart,
            stats_cfg=stats_cfg,
            pixel_format=pixel_format,
            hub=hub,
            state=state,
            lock=lock,
            decode_stats=decode_stats,
        )
        player._paths = paths
    else:
        player = JpegPlayer(
            lcd=lcd,
            decoder=decoder,
            folder_path=folder_path,
            files=files,
            jpeg_mv=jpeg_mv,
            frame_mv=frame_mv,
            width=width,
            height=height,
            bytes_per_pixel=bytes_per_pixel,
            block=block,
            step_blocks=step_blocks,
            fps_ms=fps_ms,
            uart=uart,
            stats_cfg=stats_cfg,
            pixel_format=pixel_format,
        )
        player._paths = paths
    PLAYER = player
    player.run(autoplay=autoplay)


if __name__ == "__main__":
    main()
