from machine import Pin, I2S
from lib.sys_bus import bus
from lib.log_service import get_log

CONFIG = []


def config():
    i2s_list = []
    for item in CONFIG:
        gpio = item.get("GPIO", {})
        cfg = item.get("config", {})
        audio_i2s = I2S(
            0,
            sck=Pin(gpio["sck"]),
            ws=Pin(gpio["ws"]),
            sd=Pin(gpio["sd"]),
            mode=I2S.RX,
            bits=cfg.get("bits", 16),
            format=I2S.STEREO,
            rate=cfg.get("rate", 16000),
            ibuf=cfg.get("rate", 16000) * 4 * 2,
        )
        i2s_list.append(audio_i2s)

    bus.register_service("i2s_list", i2s_list)
    get_log().info("I2S: {} device(s)".format(len(i2s_list)))
    return i2s_list


def gpios():
    result = {}
    for item in CONFIG:
        gpio = item.get("GPIO", {})
        for name in ("sck", "ws", "sd"):
            pin = gpio.get(name)
            if pin is not None:
                result[pin] = "i2s_{}".format(name)
    return result
