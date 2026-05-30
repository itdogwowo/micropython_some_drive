"""
TFT 顯示驅動配置層 — 支援 SPI / QSPI / I80 / RGB / I2C

兩種呼叫方式:
  config(spi=..., dc=..., cs=..., rst=..., driver="...", ...)   ← 工廠式，明確傳參
  boot_config(cfg)                                                ← boot 模式，接受 dict
"""

def config(spi, dc, cs, rst, driver="ST7789", width=240, height=320,
           rotation=0, color_order="RGB", invert=False,
           pixel_format="RGB565_BE", bytes_per_pixel=2, adapter=None):
    """工廠函式 — 明確傳入 SPI / pin 物件"""
    from lib.TFT import ST7789, ST7735, GC9A01, GC9D01, ILI9341, NV3030B

    driver_map = {
        "ST7789":  ST7789,
        "ST7735":  ST7735,
        "GC9A01":  GC9A01,
        "GC9D01":  GC9D01,
        "ILI9341": ILI9341,
        "NV3030B": NV3030B,
    }

    for lazy_drv in ("RM67162", "SH8601"):
        if driver == lazy_drv:
            try:
                mod = __import__("lib.TFT", None, None, [lazy_drv])
                driver_map[lazy_drv] = getattr(mod, lazy_drv)
            except (ImportError, AttributeError):
                raise ValueError("{} not available — update lib/TFT.py on device".format(lazy_drv))

    driver_cls = driver_map.get(driver)
    if driver_cls is None:
        raise ValueError("Unsupported TFT driver: {}".format(driver))

    lcd = driver_cls(
        spi=spi,
        dc=dc,
        cs=cs,
        rst=rst,
        width=width,
        height=height,
        rotation=rotation,
        color_order=color_order,
        invert=invert,
        pixel_format=pixel_format,
        bytes_per_pixel=bytes_per_pixel,
    )

    if adapter is not None:
        lcd._bus = adapter

    return lcd


def boot_config(cfg):
    """boot 模式 — 接受 cfg dict，從 bus service 解析 SPI / pin"""
    cfg = dict(cfg)  # 複製，避免 pop 影響 boot.py 原始 dict
    from lib.sys_bus import bus
    from lib.bus_adapter import SpiBusAdapter

    spi_by_id = bus.get_service("spi_by_id") or {}
    pin_by_label = bus.get_service("pin_by_label") or {}

    pins = cfg.pop("pins", {})
    dc  = pin_by_label.get(pins.get("dc", ""))
    cs  = pin_by_label.get(pins["cs"])
    rst = pin_by_label.get(pins["rst"])

    missing = []
    if cs  is None: missing.append("cs={}".format(pins["cs"]))
    if rst is None: missing.append("rst={}".format(pins["rst"]))
    if missing:
        raise ValueError("TFT pins not found: {}".format(", ".join(missing)))

    # ⚠️ 必須先開電源，RM67162 才能接收 init 命令
    bl = pin_by_label.get(pins.get("bl", ""))
    if bl is not None:
        bl.value(1)
        print("[tft_drv] power ON (GPIO={})".format(pins.get("bl", "")))
    else:
        print("[tft_drv] no power pin — display may not be powered")

    spi_id = cfg.pop("spi_id", 1)
    spi = spi_by_id.get(spi_id) or (list(spi_by_id.values())[0] if spi_by_id else None)
    if spi is None:
        print("[tft_drv] no SPI bus available, skipping")
        return None

    fmt = cfg.get("pixel_format", "RGB565_BE")
    bpp = 3 if fmt.startswith("RGB888") else 2

    adapter = SpiBusAdapter(spi, dc, cs, rst)
    lcd = config(spi=spi, dc=dc, cs=cs, rst=rst,
                 bytes_per_pixel=bpp, adapter=adapter, **cfg)

    bus.register_service("lcd", lcd)
    bus.shared["tft_width"] = cfg["width"]
    bus.shared["tft_height"] = cfg["height"]
    bus.shared["tft_driver"] = cfg["driver"]

    # 全黑畫面
    w, h = cfg["width"], cfg["height"]
    row_bytes = w * bpp
    for y in range(0, h, 20):
        rows = min(20, h - y)
        lcd.set_window(0, y, w - 1, y + rows - 1)
        lcd.write_data(bytearray(row_bytes * rows))
    lcd.set_window(0, 0)

    return lcd


def gpios():
    """TFT 不直接擁有 GPIO（SPI 由 spi_drv、控制腳由 pin_drv 註冊）"""
    return {}
