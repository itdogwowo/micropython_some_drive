from Lib.TFT import *
from machine import SDCard
import machine , time , os,vfs,framebuf , jpeg
from machine import Timer, I2C,SoftI2C, ADC, Pin, PWM,UART,I2S,SPI
import json
import framebuf
import jpeg
import os
from machine import WDT

from JpegBufferController import *
from TFTController import *
from CST328 import *

from DisplayController import *

time.sleep_ms(1000)


def main():
    # 初始化硬體
    from Lib.TFT import ST7789
    from machine import SDCard, SPI, Pin, Encoder, UART
    import os
    import time
        
    
    # LCD和SD卡初始化
    tft_spi = machine.SPI(1, baudrate=80_000_000, sck=Pin(40), mosi=Pin(45))
    lcd = ST7789(
        spi=tft_spi,
        dc=Pin(41, Pin.OUT),
        cs=Pin(42, Pin.OUT),
        rst=Pin(39, Pin.OUT),
        width= 240,
        height=320
    )
    lcd.set_rotation(90)
    
    lcd.toggle_inversion()
    all_led_list[0][0].duty(2046)
    
    # 編碼器和按鈕初始化
    counter = Encoder(0, Pin(7, Pin.IN), Pin(8, Pin.IN))
    encoder_button = Pin(9, Pin.IN, Pin.PULL_UP)
    
    i2c = I2C(0, scl=Pin(3), sda=Pin(1), freq=400000)
    
    _touch = CST328(i2c,int_pin=4, rst_pin=2)
    
#     # UART初始化
#     uart = UART(1, baudrate=115200, tx=Pin(15), rx=Pin(18))
    
    # SD卡和文件系統
    sd = SDCard(slot=2, width=1, sck=14, miso=16, mosi=17,cs=21)
    os.mount(sd, "/sd")

    # 顯示背景
    decoder = jpeg.Decoder(rotation=0, pixel_format="RGB565_BE")
    
    jpeg_data = open('sd/0/'+"background/000.jpeg", "rb").read()
    decoded_image = decoder.decode(jpeg_data)

    _temp_buff = bytearray(320 * 240 * 2)
    front_fb = framebuf.FrameBuffer(
            _temp_buff,
            240,
            320,
            framebuf.RGB565
        )
    front_fb.fill(0XF22F)
        
        
    lcd.set_window(0, 0)
    lcd.write_data(_temp_buff)


    
    # 創建主控制器
    controller = DisplayController(root_path = '/sd', lcd = lcd , uart = uart ,
                                   encoder = counter ,encoder_button = encoder_button,
                                   touch = _touch,
                                   reverse = True)
    
#     controller.timer.set_time(0)# 10秒倒計時
    controller._set_state(mode=4, source='local')
    
#     controller._reinitialize(1)

    
    
    try:
        h = 240
        w = 320
        
#         h = 172
#         w = 320
        
        
        _temp_buff = bytearray(h * w * 2)
        front_fb = framebuf.FrameBuffer(
                _temp_buff,
                h,
                w,
                framebuf.RGB565
            )
    
    
        lcd.set_window(0, 0,h,w)
#         lcd.set_window(0, 0,172,320)
        x =0
        while True:
            
            
            front_fb.fill(x)
            
            st = time.ticks_ms()
            lcd.write_data(front_fb)
#             decoded_image = decoder.decode(jpeg_data)
            run_time = time.ticks_diff( time.ticks_ms(),st)
            print(run_time)
            
            x = (x+1)% 0xffff
            if run_time <= 20 :
                time.sleep_ms(20-run_time)

                
    except KeyboardInterrupt:
        timer.stop()
        print("Program stopped")

if __name__ == "__main__":
    
    
#     h = 240
#     w = 320
# 
#     _temp_buff = bytearray(h * w * 2)
#     front_fb = framebuf.FrameBuffer(
#             _temp_buff,
#             h,
#             w,
#             framebuf.RGB565
#         )
# 
# 
#     lcd.set_window(0, 0,h,w)
        
        
    main()
    
    
    
    
        


