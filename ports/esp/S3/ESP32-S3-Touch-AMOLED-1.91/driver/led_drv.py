from lib.sys_bus import bus
from lib.log_service import get_log
from lib.LEDController import LEDStreamer


def config(_cfg=None):
    apa_list = bus.get_service("apa1022_list") or []
    ws_list = bus.get_service("ws2812_list") or []
    pca_list = bus.get_service("pca9685_list") or []

    led_list = apa_list + ws_list + pca_list
    bus.register_service("led_list", led_list)

    try:
        st = LEDStreamer(led_list)
        st.show_all()
        bus.register_service("st_LED", st)
    except Exception as e:
        get_log().error("st_LED init error: {}".format(e))

    return led_list


def gpios():
    # LED 本身不佔 GPIO
    return {}
