from machine import Pin, SPI
from lib.sys_bus import bus

# ESP32-S3-Touch-LCD-2.8
# ST7789 via lcd_bus: data=(45,), clk=40, host=1
CONFIG = [
    {
        "id": 2,
        "baudrate": 80000000,
        "phase": 0,
        "polarity": 0,
        "GPIO": {"sck": 40},
        "data_pins": (45,),
    },
]

try:
    import lcd_bus
    _LCD_BUS = True
except ImportError:
    _LCD_BUS = False


def _make_machine_spi(item, gpio, data):
    """fallback — 用 machine.SPI 建單線 SPI bus, 先嘗試釋放舊佔用"""
    sid = item["id"]
    # soft reset 後 SPI host 可能殘留, 嘗試 deinit
    try:
        old = SPI(sid)
        old.deinit()
    except:
        pass
    sck = gpio.get("sck")
    mosi = gpio.get("mosi")
    miso = gpio.get("miso")
    return SPI(
        sid,
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
            except Exception as e:
                print("[spi_drv] SPI{} lcd_bus fail: {} → machine.SPI".format(item["id"], e))
                # 嘗試釋放 lcd_bus 可能殘留的佔用
                if 'spi' in locals():
                    try: spi.deinit()
                    except: pass
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
