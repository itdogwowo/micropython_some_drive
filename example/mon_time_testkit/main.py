from Lib.TFT import *
from machine import SDCard
import machine , time , os,vfs,framebuf , jpeg
from machine import Timer, I2C,SoftI2C, ADC, Pin, PWM,UART,I2S,SPI
import json
import framebuf
import jpeg
import os

from DisplayController import *
from JpegBufferController import *
from TFTController import *

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
#     lcd.set_rotation(90)
#     
#     lcd.toggle_inversion()
#     all_led_list[0][0].duty(2046)
    
    # 編碼器和按鈕初始化
    counter = Encoder(0, Pin(7, Pin.IN), Pin(8, Pin.IN))
    encoder_button = Pin(9, Pin.IN, Pin.PULL_UP)
    
    sd = SDCard(slot=1, width=4, sck=1, cmd=44, data=(43, 4, 3, 2))
    os.mount(sd, "/sd")
    
    with open('/sd/config.json', 'r') as openfile:
    # Reading from json file
        sd_config = json.load(openfile)
        
        
    _root_path = sd_config['root_path']%sd_config['patter']
    root_path = f'/sd/{_root_path}/'
    
    # 顯示背景
    decoder = jpeg.Decoder(rotation=0, pixel_format="RGB565_BE")
    jpeg_data = open(root_path+"background/000.jpeg", "rb").read()
    decoded_image = decoder.decode(jpeg_data)
    lcd.set_window(0, 0)
    lcd.write_data(decoded_image)
    
    # 創建緩衝管理器和計時器 
    buffer_mgr = JpegBufferController(root_path)
    timer = CountdownTimer()
    timer.set_time(0)  # 10秒倒計時
    
    
    # 創建主控制器
    controller = DisplayController(config = sd_config, lcd = lcd , uart = uart , encoder = counter ,
                                   encoder_button = encoder_button, buffer_mgr = buffer_mgr, timer = timer,
                                   touch = None,reverse = True)
    
    try:
        while True:
            st = time.ticks_ms()
            controller.update(debug = False )
            
            run_time = time.ticks_diff( time.ticks_ms(),st)
#             print('run_time : ',run_time)
            if run_time <= 20 :
                time.sleep_ms(20-run_time)
                
    except KeyboardInterrupt:
        timer.stop()
        print("Program stopped")

if __name__ == "__main__":
    main()
    
    
    
    
        

