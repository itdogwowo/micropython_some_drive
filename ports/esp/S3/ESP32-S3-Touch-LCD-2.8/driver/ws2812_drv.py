import neopixel
from lib.log_service import get_log

def config(cfgs):
    if not cfgs:
        return []
    from machine import Pin
    from lib.sys_bus import bus
    from lib.LEDController import LEDController
    ws_list = []
    for cfg in cfgs:
        pin = Pin(cfg["GPIO"], Pin.OUT)
        pixel = neopixel.NeoPixel(pin, cfg["Q"])
        ws_list.append(LEDController("WS2812", {
            "led_IO": pixel,
            "Q": cfg["Q"],
            "order": cfg.get("order", "GRB"),
        }))
    bus.register_service("ws2812_list", ws_list)
    get_log().info("WS2812: {} channel(s)".format(len(ws_list)))
    return ws_list


def gpios():
    return {}
