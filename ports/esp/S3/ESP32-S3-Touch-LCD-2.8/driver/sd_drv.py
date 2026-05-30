import machine
import os
from lib.sys_bus import bus
from lib.log_service import get_log

# ESP32-S3-Touch-LCD-2.8
# SDMMC 1-bit mode: CLK=14, CMD=17, D0=16
# D1/D2/D3 are NC (-1 in ESP-IDF config)
CONFIG = {
    "phat": "/sd",
    "LDO": {"id": 4, "mv": 3300},
    "config": {"slot": 1, "width": 1, "freq": 20000000},
    "GPIO": {"sck": 14, "cmd": 17, "data": [16]},
}

def config():
    if not CONFIG:
        bus.register_service("data_Phat", "")
        return ""

    phat = CONFIG.get("phat", "/sd")

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
        get_log().info("SD card mounted on {}".format(phat))
    except Exception as e:
        get_log().error("SD card init error: {}".format(e))
        if not _exists(phat):
            os.mkdir(phat)
        open(phat + "/local", "w").close()

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
        if d is not None and d >= 0:
            result[d] = "sd_d{}".format(i)
    return result
