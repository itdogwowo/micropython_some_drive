"""
pin_drv.py — GPIO 腳位管理
Waveshare ESP32-S3-AMOLED-1.91

已由其他 driver 佔用的腳位不收錄在此:
  spi_drv: 5, 7, 18, 47, 48
  sd_drv:  8, 9, 42
  i2c_drv: 39, 40 (touch FT3168)

正式使用: 6(tft_cs), 17(tft_rst), 38(tft_bl)
餘下全部可用 GPIO 都列在下方
"""
from lib.hw_manager import init_pins

CONFIG = [
    # ── 正式使用 ──
    {"GPIO": 6,  "label": "tft_cs",    "mode": "OUT", "initial": 1},
    {"GPIO": 17, "label": "tft_rst",   "mode": "OUT", "initial": 1},
    {"GPIO": 38, "label": "tft_bl",    "mode": "OUT", "initial": 0},

    # ── 馬達 ──
    {"GPIO": 10, "label": "m1",        "mode": "OUT", "initial": 0},
    {"GPIO": 11, "label": "m2",        "mode": "OUT", "initial": 0},
    {"GPIO": 12, "label": "m_en",      "mode": "OUT", "initial": 0},

    # ── 剩餘可用 GPIO (未分配、可自由使用) ──
    {"GPIO": 0,  "label": "gp0",       "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 1,  "label": "gp1",       "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 2,  "label": "gp2",       "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 3,  "label": "gp3",       "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 4,  "label": "gp4",       "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 13, "label": "gp13",      "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 14, "label": "gp14",      "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 15, "label": "gp15",      "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 16, "label": "gp16",      "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 21, "label": "gp21",      "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 41, "label": "gp41",      "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 43, "label": "gp43",      "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 44, "label": "gp44",      "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 45, "label": "gp45",      "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 46, "label": "gp46",      "mode": "IN",  "initial": 0, "pull": "UP"},
]


def config():
    return init_pins(CONFIG)


def gpios():
    result = {}
    for item in CONFIG:
        gpio = item.get("GPIO")
        if gpio is not None:
            result[gpio] = item.get("label", "pin_{}".format(gpio))
    return result
