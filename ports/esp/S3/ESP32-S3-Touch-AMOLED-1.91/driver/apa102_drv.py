from lib.log_service import get_log
from lib.apa102 import APA102

def config(cfgs):
    if not cfgs:
        return []
    from lib.sys_bus import bus
    from lib.LEDController import LEDController
    spi_by_id = bus.get_service("spi_by_id") or {}
    apa_list = []
    for cfg in cfgs:
        spi = spi_by_id.get(cfg["spi_id"])
        if spi is None:
            get_log().error("APA102: SPI id {} not found".format(cfg["spi_id"]))
            continue
        apa = APA102(spi, num_leds=cfg["Q"])
        apa_list.append(LEDController("APA102", {
            "led_IO": apa,
            "Q": cfg["Q"],
            "order": cfg.get("order", "BGRW"),
        }))
    bus.register_service("apa1022_list", apa_list)
    get_log().info("APA102: {} channel(s)".format(len(apa_list)))
    return apa_list


def gpios():
    # APA102 走 SPI，無獨立 GPIO
    return {}
