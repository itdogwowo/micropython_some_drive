import jpeg
from machine import Pin, SPI

from lib.buffer_hub import AtomicStreamHub
from lib.config_loader import load_config
from lib.media_source import compute_max_file_size, compute_max_frame_size, list_jpegs
from lib.storage_sd import init_sd
from lib.sys_bus import SysBus


def build_bus():
    cfg = load_config()
    sd_dev, sd_path, sd_err = init_sd(cfg)

    assets_root = (cfg.get("assets_root", "/jpeg") or "/jpeg").rstrip("/")
    tft_cfg = cfg.get("tft", {}) or {}
    jpeg_cfg = cfg.get("jpeg", {}) or {}
    player_cfg = cfg.get("player", {}) or {}
    layout = (cfg.get("display_Layout") or [{}])[0] or {}

    width = int(tft_cfg.get("width", layout.get("width", 240)))
    height = int(tft_cfg.get("height", layout.get("height", 240)))
    folder = layout.get("type", "background")
    folder_path = assets_root + "/" + folder
    depth_val = layout.get("depth", -1)
    depth = -1 if depth_val is None else int(depth_val)

    pixel_format = jpeg_cfg.get("pixel_format", "RGB565_BE")
    rotation = int(jpeg_cfg.get("rotation", 0))
    block = bool(jpeg_cfg.get("block", True))
    return_bytes = bool(jpeg_cfg.get("return_bytes", False))
    step_blocks = int(jpeg_cfg.get("step_blocks", 0) or 0)
    max_jpeg_bytes = int(jpeg_cfg.get("max_jpeg_bytes", 0) or 0)

    pace_ms = int(player_cfg.get("pace_ms", 0) or 0)
    loop_play = bool(player_cfg.get("loop", True))
    pipeline_cfg = player_cfg.get("pipeline", {}) or {}
    pipeline_io_buffers = pipeline_cfg.get("io_buffers", None)
    pipeline_frame_buffers = pipeline_cfg.get("frame_buffers", None)
    io_buffers = None if pipeline_io_buffers is None else int(pipeline_io_buffers)
    frame_buffers = None if pipeline_frame_buffers is None else int(pipeline_frame_buffers)
    stats_cfg = player_cfg.get("stats", {}) or {}
    stats_enabled = bool(stats_cfg.get("enabled", False))
    stats_interval_ms = int(stats_cfg.get("interval_ms", 1000) or 1000)
    stats_frames_n = int(stats_cfg.get("frames_n", 60) or 60)

    if pixel_format != "RGB565_BE":
        raise ValueError("Only RGB565_BE is supported in New for now")

    decoder = jpeg.Decoder(
        pixel_format=pixel_format,
        rotation=rotation,
        block=block,
        return_bytes=return_bytes,
    )

    paths = list_jpegs(folder_path)
    if not paths:
        raise OSError("No JPEG files in: " + folder_path)
    if depth > 0 and depth < len(paths):
        paths = paths[:depth]

    if max_jpeg_bytes <= 0:
        max_jpeg_bytes = compute_max_file_size(paths)

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
    disp_rotation = int(tft_cfg.get("rotation", 0))
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
        rotation=disp_rotation,
        color_order=color_order,
        invert=invert,
    )
    lcd.set_window(0, 0)

    bus = SysBus()
    bus.shared["config"] = cfg
    bus.shared["sd_path"] = sd_path
    bus.shared["sd_error"] = sd_err
    bus.shared["data_Phat"] = sd_path
    bus.shared["width"] = width
    bus.shared["height"] = height
    bus.shared["frame_bytes"] = compute_max_frame_size(paths, default_bytes=width * height * 2)
    bus.shared["max_jpeg_bytes"] = max_jpeg_bytes
    bus.shared["jpeg_block"] = block
    bus.shared["jpeg_step_blocks"] = step_blocks
    bus.shared["pace_ms"] = pace_ms
    bus.shared["loop_play"] = loop_play
    bus.shared["pipeline_io_buffers"] = io_buffers
    bus.shared["pipeline_frame_buffers"] = frame_buffers
    bus.shared["stats_enabled"] = stats_enabled
    bus.shared["stats_interval_ms"] = stats_interval_ms
    bus.shared["stats_frames_n"] = stats_frames_n
    bus.shared["engine_run"] = True
    bus.shared["core1_ready"] = False

    if sd_dev is not None:
        bus.set_service("sdcard", sd_dev)
    if sd_path:
        bus.set_service("data_Phat", sd_path)
    bus.set_service("lcd", lcd)
    bus.set_service("decoder", decoder)
    bus.set_service("paths", paths)

    frame_tail = 16
    io_tail = 16
    bus.shared["frame_tail"] = frame_tail
    bus.shared["io_tail"] = io_tail

    frame_hub_buffers = 3 if frame_buffers is None else frame_buffers
    io_hub_buffers = (2 if frame_hub_buffers > 2 else frame_hub_buffers) if io_buffers is None else io_buffers

    frame_hub = AtomicStreamHub(bus.shared["frame_bytes"] + frame_tail, num_buffers=frame_hub_buffers)
    io_hub = AtomicStreamHub(max_jpeg_bytes + io_tail, num_buffers=io_hub_buffers)

    bus.set_service("frame_hub", frame_hub)
    bus.set_service("io_hub", io_hub)

    return bus
