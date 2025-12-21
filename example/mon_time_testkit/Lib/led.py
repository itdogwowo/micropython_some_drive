import time
from machine import Pin

'''
This is a library for directly controlling the WS2812 IC with Python GPIO. First of all, 
thank you for creating this library under such unfortunate circumstances. 
I hope it can solve the problems you are facing.
'''
RGT = 250  # 0.25us = 250 ns

T0H = 350  # 0.35us = 350 ns
T0L = 500  # 0.50us = 500 ns

RES = 5000   # 50us 0.000050

bit0: int = 0b11000000
bit1: int = 0b11110000

class What_wrong_with_me_neopixel:
    def __init__(self, frame_rate, pins, led_count, rgbw=False):
        self.frame_rate = frame_rate
        self.pins = [Pin(i, Pin.OUT) for i in pins]
        self.led_count = led_count
        self.rgbw = rgbw
        print(pins)
        self.buffers = [ [0 * (max(led_count) * (4 if rgbw else 3))]  for _ in pins]

    def _get_time_ns(self):
        try:
            return time.time_ns()
        except :
            return time.monotonic_ns()

        return

    def _IOtrol(self,IOvalue):
        try:
            for l in self.pins :
                l.value(IOvalue)
        except :
            for l in self.pins :
                l.value = IOvalue

        return


    def _IOsleep(self,start_time,IOvalue):
        while 1:
            if (self._get_time_ns() -  start_time) >=IOvalue:
                break


    def _pin_write_buf(self,led_buf: list  = []):
        
        if len(led_buf) == len(self.pins):
            start_time = self._get_time_ns()
            self._IOtrol(1)
            self._IOsleep(start_time,T0H)
            for n , pin in  enumerate(self.pins) :

                if led_buf[n] == 0 or led_buf[n] == '0' :
                    l.value(0)

            self._IOsleep(start_time,T0H)


    def write_byte(self):

        self._IOtrol(RES)
        
        for n in range(len(self.buffers[0])):
            all_buff = [f'{(sublist[n]&0xFF):08b}'  for sublist  in self.buffers]
            for i in range(8):
                io_bin = [sublist[i] for sublist  in all_buff]
                self._pin_write_buf(self,io_bin)

        self._IOtrol(RES)

        return 
