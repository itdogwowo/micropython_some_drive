from machine import Pin, I2C
from lib.sys_bus import bus

# Waveshare ESP32-S3-AMOLED-1.91
# Touch FT3168: SCL=39, SDA=40, addr=0x38
CONFIG = [
    {
        "id": 0,
        "freq": 400000,
        "GPIO": {"scl": 39, "sda": 40},
    }
]


def config():
    i2c_list = []
    i2c_by_id = {}
    for item in CONFIG:
        gpio = item.get("GPIO", {})
        i2c = I2C(
            item["id"],
            freq=item.get("freq"),
            scl=Pin(gpio["scl"]) if gpio.get("scl") is not None else None,
            sda=Pin(gpio["sda"]) if gpio.get("sda") is not None else None,
        )
        i2c_list.append(i2c)
        i2c_by_id[item["id"]] = i2c

    bus.register_service("i2c_list", i2c_list)
    bus.register_service("i2c_by_id", i2c_by_id)
    return i2c_list


def gpios():
    result = {}
    for item in CONFIG:
        gpio = item.get("GPIO", {})
        for name in ("scl", "sda"):
            pin = gpio.get(name)
            if pin is not None:
                result[pin] = "i2c{}_{}".format(item.get("id", "?"), name)
    return result