from lib.ESP_Boot import *
from lib.LEDcommander import *
from lib.LEDController import *
from lib.ConfigManager import *



with open('startup_config.json', 'r') as openfile:
    # Reading from json file
    config = json.load(openfile)


# ============================================
# 全局變量
# ============================================
C_LUMN = config['c_lum']

KEEP_RUN = True


# 計時器配置


# 初始化配置管理器
cfg = ConfigManager(startup_file='startup_config.json')
# print('='*70)
loop_one_success = cfg.get_state('loop_one_success', default=False)
cfg.set_state('loop_one_success', False)

# cfg.set_state('loop_one_success', True)
# check_looping(True,cfg)
check_looping(loop_one_success,cfg)


        

gc.collect()

uart = init_UART(config['UART_IO'])

led_list = init_led(config['LED_IO'])

rgb_list = init_rgb(config['RGB_IO'])
i2c_led_list = init_i2c(config['i2c_IO'])
i2s = init_i2s(config['i2s_IO'])

all_led_list = led_list + i2c_led_list
ledC = LEDcommander(all_led_list,rgb_list)
ledC.init_all()

# USER_CONNECT = True