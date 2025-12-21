from lib.TFT import *
from machine import SDCard
import machine , time , os,vfs,framebuf , jpeg
from machine import Timer, I2C,SoftI2C, ADC, Pin, PWM,UART,I2S,SPI,I2CTarget
import json
import framebuf
import jpeg
import os

from JpegBufferController import *
from TFTController import *


from DisplayController import *

time.sleep_ms(1000)


def irq_handler(i2c_target):
    """I2C Target 中断处理 - 直接操作共享内存"""
    flags = i2c_target.irq().flags()
    addr = i2c_target.memaddr
    
    if flags & I2CTarget.IRQ_END_READ:
        # Controller 读取:从 mem 发送数据
#         i2c_target.write(mem)
        print(f"📖 Read from addr {addr}: {mem}")
        
    elif flags & I2CTarget.IRQ_END_WRITE:
        # Controller 写入:直接更新 mem
#         i2c_target.readinto(mem)
        print(f"✍️  Write to addr {addr}: {mem}")
        
        
mem = bytearray(8)
i2c = I2CTarget(addr=0x43, mem=mem,scl=45, sda=46)


def main():
    # 初始化硬體
    from lib.TFT import ST7789
    from machine import SDCard, SPI, Pin, Encoder, UART
    import os
    import time
        
    
    # LCD和SD卡初始化
    tft_spi = machine.SPI(1, baudrate=80_000_000, sck=Pin(1), mosi=Pin(2))
    lcd = GC9D01(
        spi=tft_spi,
        dc=Pin(4, Pin.OUT),
        cs=Pin(5, Pin.OUT),
        rst=Pin(7, Pin.OUT),
        width= 160,
        height=160,
        invert=True
    )
#     lcd.set_rotation(90)
#     lcd._update_inversion()
    
    lcd.toggle_inversion()
#     all_led_list[0][0].duty(4095)
    
    # 編碼器和按鈕初始化    
    with open('/sd1/config.json', 'r') as openfile:
    # Reading from json file
        sd_config = json.load(openfile)
        
    _root_path = sd_config['root_path']%sd_config['patter']
    root_path = f'/sd1/{_root_path}/'

    lcd.set_window(0, 0)
#     buf = bytearray(160 * 160 * 2)

#     lcd.write_data(buf)
    
#     # 創建緩衝管理器和計時器 
    buffer_mgr = JpegBufferController(root_path)
    loop_buf =  buffer_mgr.get_next_frame('loop')
    lcd.write_data(loop_buf)
    time.sleep_ms(10)
    all_led_list[0][0].duty(4095)


    frame_state = False
    try:
        while True:
#             print(mem)
            st = time.ticks_ms()
#             loop_buf =  buffer_mgr.get_next_frame('loop')
#             lcd.write_data(loop_buf)
            if frame_state:
                loop_buf =  buffer_mgr.get_next_frame('loop')
            else:
                lcd.write_data(loop_buf)
                
            frame_state = not frame_state
                
            run_time = time.ticks_diff( time.ticks_ms(),st)
#             print('run_time : ',run_time)
            if run_time <= 20 :
                time.sleep_ms(20-run_time)
                
    except KeyboardInterrupt:
        timer.stop()
        print("Program stopped")

if __name__ == "__main__":
    main()
    
    
    
    
        

