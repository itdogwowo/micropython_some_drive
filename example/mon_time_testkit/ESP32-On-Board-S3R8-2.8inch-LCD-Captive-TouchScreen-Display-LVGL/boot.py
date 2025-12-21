from Lib.ESP_Boot import *
from Lib.LEDcommander import *
from Lib.LEDController import * 

with open('startup_config.json', 'r') as openfile:
    # Reading from json file
    startup_config = json.load(openfile)

# Writing to sample.json
with open("running_config.json", "w+") as outfile:
    running_config = json.dumps(startup_config)
    outfile.write(running_config)

with open('running_config.json', 'r') as openfile:
    # Reading from json file
    config = json.load(openfile)



C_LUMN = config['c_lum']
KEEP_RUN = True

'''

5V   ---   ---   5
G    ---   ---   6
3.3  ---   ---   7
4    ---   ---   8
3    ---   ---   9
2    ---   ---   10
1    ---   ---   20
0    ---   ---   21

'''


init_Network(config['Network'])

gc.collect()

uart = init_UART(config['UART_IO'])
led_list = init_led(config['LED_IO'])
rgb_list = init_rgb(config['RGB_IO'])
i2c_led_list = init_i2c(config['i2c_IO'])
i2s = init_i2s(config['i2s_IO'])

all_led_list = led_list + i2c_led_list
ledC = LEDcommander(all_led_list,rgb_list)
ledC.init_all()