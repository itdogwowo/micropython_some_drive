from machine import Pin, PWM
from lib.sys_bus import bus
from lib.log_service import get_log

CONFIG = []


def config():
    pwm_list = []
    for item in CONFIG:
        gpio = item.get("GPIO")
        if gpio is None:
            continue
        pwm = PWM(Pin(gpio), freq=1000, duty=0)
        pwm_list.append(pwm)

    bus.register_service("pwm_list", pwm_list)
    get_log().info("PWM: {} channel(s)".format(len(pwm_list)))
    return pwm_list


def gpios():
    result = {}
    for i, item in enumerate(CONFIG):
        gpio = item.get("GPIO")
        if gpio is not None:
            result[gpio] = "pwm_{}".format(i)
    return result
