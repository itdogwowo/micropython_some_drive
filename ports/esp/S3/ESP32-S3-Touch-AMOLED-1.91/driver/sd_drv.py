import machine
import os
from lib.sys_bus import bus
from lib.log_service import get_log

CONFIG = {
    "phat": "/sd",
    "LDO": {"id": 4, "mv": 3300},
    "config": {"slot": 1, "width": 1, "freq": 20000000},
    "GPIO": {"sck": 9, "cmd": 42, "data": [8]},
}

def config():
    if not CONFIG:
        bus.register_service("data_Phat", "")
        return ""

    phat = CONFIG.get("phat", "/sd")
    if _exists(phat):
        bus.register_service("data_Phat", phat)
        return phat

    try:
        from esp32 import LDO
        ldo_cfg = CONFIG.get("LDO", {})
        LDO(ldo_cfg.get("id", 4), ldo_cfg.get("mv", 3300), adjustable=True)
    except Exception as e:
        get_log().error("LDO error: {}".format(e))

    slot = CONFIG.get("config", {}).get("slot", 0)
    try:
        if slot >= 2:
            _init_sd_spi(phat)
        else:
            _init_sd_sdio(phat)
    except Exception as e:
        get_log().error("SD card init error: {}".format(e))

    bus.register_service("data_Phat", phat)
    return phat


def _init_sd_spi(phat):
    sd = machine.SDCard(
        slot=CONFIG["config"].get("slot", 2),
        sck=CONFIG["GPIO"]["sck"],
        mosi=CONFIG["GPIO"]["cmd"],
        miso=CONFIG["GPIO"]["data"][0],
        cs=CONFIG["GPIO"]["data"][3],
        freq=CONFIG["config"].get("freq", 20000000),
    )
    os.mount(sd, phat)


def _init_sd_sdio(phat):
    sd = machine.SDCard(
        slot=CONFIG["config"]["slot"],
        width=CONFIG["config"]["width"],
        sck=CONFIG["GPIO"]["sck"],
        cmd=CONFIG["GPIO"]["cmd"],
        data=CONFIG["GPIO"]["data"],
        freq=CONFIG["config"]["freq"],
    )
    os.mount(sd, phat)


def _exists(path):
    try:
        os.stat(path)
    except OSError:
        return False
    return True


def gpios():
    result = {}
    gpio = CONFIG.get("GPIO", {})
    if gpio.get("sck") is not None:
        result[gpio["sck"]] = "sd_sck"
    if gpio.get("cmd") is not None:
        result[gpio["cmd"]] = "sd_cmd"
    for i, d in enumerate(gpio.get("data", [])):
        result[d] = "sd_d{}".format(i)
    return result