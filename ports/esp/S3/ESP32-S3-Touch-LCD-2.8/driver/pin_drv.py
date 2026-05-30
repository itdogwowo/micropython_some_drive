"""
pin_drv.py — GPIO 腳位管理
ESP32-S3-Touch-LCD-2.8

已由其他 driver 佔用的腳位不收錄在此:
  spi_drv:  40, 45
  i2c_drv:  1, 3 (Touch), 10, 11 (Sensors)
  sd_drv:   14, 16, 17, 21
  i2s_drv:  38, 47, 48

正式使用 (控制腳):
  tft_cs=42, tft_dc=41, tft_rst=39, tft_bl=5
  touch_rst=2, touch_int=4
  pwr_in=6, pwr_ctrl=7
  bat_adc=8

餘下全部可用 GPIO 都列在下方
"""
from lib.hw_manager import init_pins

CONFIG = [
    # ── TFT 控制腳 ──
    {"GPIO": 42, "label": "tft_cs",    "mode": "OUT", "initial": 1},
    {"GPIO": 41, "label": "tft_dc",    "mode": "OUT", "initial": 0},
    {"GPIO": 39, "label": "tft_rst",   "mode": "OUT", "initial": 1},
    {"GPIO": 5,  "label": "tft_bl",    "mode": "OUT", "initial": 0},

    # ── Touch (CST328) 控制腳 ──
    {"GPIO": 2,  "label": "touch_rst", "mode": "OUT", "initial": 1},
    {"GPIO": 4,  "label": "touch_int", "mode": "IN",  "initial": 0, "pull": "UP"},

    # ── 電源鍵 ──
    {"GPIO": 6,  "label": "pwr_in",    "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 7,  "label": "pwr_ctrl",  "mode": "OUT", "initial": 0},

    # ── 電池 ADC ──
    {"GPIO": 8,  "label": "bat_adc",   "mode": "IN",  "initial": 0},

    # ── 剩餘可用 GPIO (未分配、可自由使用) ──
    {"GPIO": 0,  "label": "gp0",       "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 9,  "label": "gp9",       "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 12, "label": "gp12",      "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 13, "label": "gp13",      "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 15, "label": "gp15",      "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 18, "label": "gp18",      "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 43, "label": "gp43",      "mode": "IN",  "initial": 0, "pull": "UP"},
    {"GPIO": 44, "label": "gp44",      "mode": "IN",  "initial": 0, "pull": "UP"},
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
