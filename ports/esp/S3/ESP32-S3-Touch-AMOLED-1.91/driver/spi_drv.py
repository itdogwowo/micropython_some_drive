from machine import Pin, SPI
from lib.sys_bus import bus

CONFIG = [
    {
        "id": 1,
        "baudrate": 80000000,
        "phase": 0,
        "polarity": 0,
        "GPIO": {"sck": 47},
        "data_pins": (18, 7, 48, 5),
    },
]

try:
    import lcd_bus
    _LCD_BUS = True
except ImportError:
    _LCD_BUS = False


def _make_machine_spi(item, gpio, data):
    """fallback — 用 machine.SPI 建單線 SPI bus"""
    sck = gpio.get("sck")
    mosi = gpio.get("mosi") if gpio.get("mosi") is not None else (
        data[0] if data else None)
    miso = gpio.get("miso")
    return SPI(
        item["id"],
        baudrate=item.get("baudrate", 80000000),
        polarity=item.get("polarity", 0),
        phase=item.get("phase", 0),
        sck=Pin(sck) if sck is not None else None,
        mosi=Pin(mosi) if mosi is not None else None,
        miso=Pin(miso) if miso is not None else None,
    )


def config():
    spi_list = []
    spi_by_id = {}
    for item in CONFIG:
        gpio = item.get("GPIO", {})
        data = item.get("data_pins")

        if _LCD_BUS:
            if data is not None:
                d = data
            else:
                mosi = gpio.get("mosi")
                d = (mosi,) if mosi is not None else None
            try:
                spi = lcd_bus.SPIBus(
                    data=d, clk=gpio["sck"],
                    freq=item.get("baudrate", 80000000),
                    host=item["id"],
                )
            except RuntimeError as e:
                print("[spi_drv] SPI{} lcd_bus fail: {} → machine.SPI".format(item["id"], e))
                spi = _make_machine_spi(item, gpio, data)
        else:
            spi = _make_machine_spi(item, gpio, data)

        spi_list.append(spi)
        spi_by_id[item["id"]] = spi

    bus.register_service("spi_list", spi_list)
    bus.register_service("spi_by_id", spi_by_id)
    return spi_list, spi_by_id


def gpios():
    result = {}
    for item in CONFIG:
        gpio = item.get("GPIO", {})
        for name in ("sck", "mosi", "miso"):
            pin = gpio.get(name)
            if pin is not None:
                result[pin] = "spi{}_{}".format(item.get("id", "?"), name)
        data = item.get("data_pins")
        if data:
            for i, d in enumerate(data):
                result[d] = "spi{}_d{}".format(item.get("id", "?"), i)
    return result
