from lib.log_service import get_log
from lib.pca9685 import PCA9685

def config(cfgs):
    if not cfgs:
        return []
    from lib.sys_bus import bus
    from lib.LEDController import LEDController
    i2c_by_id = bus.get_service("i2c_by_id") or {}
    pca_list = []
    for cfg in cfgs:
        i2c = i2c_by_id.get(cfg["i2c_id"])
        if i2c is None:
            get_log().error("PCA9685: I2C id {} not found".format(cfg["i2c_id"]))
            continue
        addrs = cfg.get("address", [])
        if not addrs:
            try:
                addrs = [a for a in i2c.scan() if a != 112]
                get_log().info("I2C Scan: {}".format([hex(a) for a in addrs]))
            except Exception as e:
                get_log().error("PCA9685 scan error: {}".format(e))
                continue
        for addr in addrs:
            try:
                pca = PCA9685(i2c, address=addr)
                pca.freq(1000)
                pca_list.append(LEDController("i2c_LED", {
                    "led_IO": pca,
                    "Q": 16,
                    "order": "W",
                }))
            except Exception as e:
                get_log().error("PCA9685@{} error: {}".format(hex(addr), e))
    bus.register_service("pca9685_list", pca_list)
    get_log().info("PCA9685: {} device(s)".format(len(pca_list)))
    return pca_list


def gpios():
    # PCA9685 走 I2C，無獨立 GPIO
    return {}
