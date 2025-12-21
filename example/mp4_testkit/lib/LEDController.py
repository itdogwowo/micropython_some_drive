from machine import Timer, I2C,SoftI2C, ADC, Pin, PWM,UART
import esp, gc, time, json,  neopixel, utime, array, struct  ,ubinascii ,_thread,micropython

from lib.LEDMathMethod import hsv2rgb,hsv2grb,hsv_to_grb


C_LUMN = 1.0
# KEEP_RUN = True

def get_all_rgbIO(rgbIO):
    all_led_io = []
    for i in range(rgbIO.led.n):
        all_led_io.append(rgbIO.led_location([i]))
    return all_led_io

def random_List(in_list):
    t_list =[]
    for i in range(len(in_list)):
        re_i = random.choice(range(len(in_list)))
        t_list.append(in_list.pop(re_i))
        
    return t_list

def random_pattern(F_n, l_max, run_n, gpio_all, r_end_Time ,led_n = 0, method = 'square_wave_now'):
    degreeO = 360/(len(gpio_all))+1 if led_n == 0 else 360/led_n
    r_pattern = []
    for i in range(led_n):
        GPIO_n = []
        for n in range(run_n):
            GPIO_n.append(random.choice(gpio_all))
            
        p = []        
        p_V = {'type':method, 'F':F_n ,'l_max':l_max,'l_lim':0, 'phi':degreeO*i, 'end_Time':r_end_Time}
        p.append(p_V)
            
        r =  {'type':'LED', 'GPIO':GPIO_n, 'patter':p, 'value':{}}
        r_pattern.append(r)
          
    return r_pattern



def set_servo_angle(angle):
    # Calculate the duty cycle from the angle
    # This formula needs to be calibrated for your specific servo
    # Typical range for SG90: 0.5ms (0 deg) to 2.4ms (180 deg) pulse width
    # Duty cycle in MicroPython's duty_u16 is a 16-bit value (0-65535)
    # For 50Hz (20ms period):
    # 0.5ms pulse = (0.5 / 20) * 65535 = 1638
    # 2.4ms pulse = (2.4 / 20) * 65535 = 7864
    
    min_duty = 1638  # Adjust based on your servo's minimum pulse width
    max_duty = 7864  # Adjust based on your servo's maximum pulse width
    
    duty = int(min_duty + (angle / 180) * (max_duty - min_duty))
    pwm.duty_u16(duty)


class LEDcontroller:
    '''
    led_IO = {'led_IO':io,'Q':0,'i2c_Object':i2c_Object}
    '''
    def __init__(self, led_Type, led_IO):
        self.led_Type = led_Type
        self.led_IO = led_IO
        self.up_lock = False
        self.lum_max = 4095
        self.brightness = 4095
        self.setup()
        self.reset()

    @micropython.native
    def __len__(self):
        """支援 len() 操作，返回 LED 總數"""
        return self.led_IO['Q']

    @micropython.native
    def __getitem__(self, index):

        if isinstance(index, slice):
            return [self.LED(self, i) for i in range(self.led_IO['Q'])[index]]
        elif isinstance(index, int):
            if -self.led_IO['Q'] <= index < self.led_IO['Q']:
                actual_index = index if index >= 0 else self.led_IO['Q'] + index
                return self.LED(self, actual_index)
            else:
                raise IndexError('Index out of range')
        else:
            raise TypeError("Invalid index type")

    @micropython.native
    def __setitem__(self, index, value):
        if 0 <= index < self.led_IO['Q']:
            self.LED_Buffer[index] = value
        else:
            raise IndexError('Index out of range')

    @micropython.native
    def __iter__(self):
        return (self.LED(self, i) for i in range(self.led_IO['Q']))

    @micropython.native
    def __add__(self, other):
        if isinstance(other, LEDcontroller):
            return list(_ for _ in self) + list(_ for _ in other)

        elif isinstance(other, list):
            return list(_ for _ in self) + list(other)
        else:
            raise TypeError("Unsupported operand type for +")

    class LED:

        def __init__(self, controller, index):
            self.controller = controller
            self.index = index

        @micropython.native
        def __getitem__(self, index):
            if 0 <= index < 3:
                return self.LED_buf(self, index)
            else:
                raise IndexError('Index out of range')

        @micropython.native
        def __setitem__(self, index, value):
            if -3 <= index < 3:
                actual_index = index if index >= 0 else 3 + index
                if actual_index == 0:
                    self.set_led_H_buf(value)
                elif actual_index == 1:
                    self.set_led_S_buf(value)
                elif actual_index == 2:
                    self.set_led_V_buf(value)
                else:
                    self.set_buf(value)
            else:
                raise IndexError('Index out of range')

        @micropython.native
        def duty(self, lum,ledQ=[]):

            if self.controller.led_Type=='esp_LED':
                io_lum = lum << 4
            elif self.controller.led_Type=='i2c_LED':
                io_lum = lum
            elif self.controller.led_Type=='RGB':
                io_lum = lum >> 4
            else:
                io_lum = lum 

            self.controller.duty(io_lum,ledQ+[self.index])

        @micropython.viper
        def led_H(self):
            return self.LED_buf(self, 0)

        @micropython.viper
        def led_S(self):
            return self.LED_buf(self, 1)

        @micropython.viper
        def led_V(self):
            return self.LED_buf(self, 2)


        @micropython.viper
        def set_led_H_buf(self, lum:int):
            if self.controller.led_Type=='esp_LED':
                self.set_buf(lum)
            elif self.controller.led_Type=='i2c_LED':
                self.set_buf(lum)
            elif self.controller.led_Type=='RGB':
                self.controller.led_H[self.index] = 360 if  int(lum) >= 360 else int(lum)
            else:
                self.set_buf(lum)


        @micropython.viper
        def set_led_S_buf(self, lum:int):
            if self.controller.led_Type=='esp_LED':
                self.set_buf(lum)
            elif self.controller.led_Type=='i2c_LED':
                self.set_buf(lum)
            elif self.controller.led_Type=='RGB':
                self.controller.led_S[self.index] = int(lum) >> 4
            else:
                self.set_buf(lum)

        @micropython.viper
        def set_led_V_buf(self, lum:int):
            self.set_buf(lum)
            
        @micropython.viper
        def set_buf(self, lum:int):

            if self.controller.led_Type=='esp_LED':
                io_lum = int(lum) << 4
            elif self.controller.led_Type=='i2c_LED':
                io_lum = int(lum)
            elif self.controller.led_Type=='RGB':
                io_lum = int(lum) >> 4       
            else:
                io_lum = int(lum)

            self.controller.LED_Buffer[self.index] = io_lum


        @micropython.viper
        def set_rgb(self, rgb: ptr8):
            r_high = rgb[0] & 0x03  # 红色分量的低2位
            g_high = rgb[1] & 0x03  # 绿色分量的低2位  
            b_high = rgb[2] & 0x03  # 蓝色分量的低2位
            
            io_lum = (r_high << 10) | (g_high << 8) | (b_high << 6) | (r_high << 4) | (g_high << 2) | b_high

            if self.controller.led_Type=='esp_LED':
                io_lum = io_lum
                self.controller.LED_Buffer[self.index] = io_lum
            elif self.controller.led_Type=='i2c_LED':
                io_lum = io_lum >> 4
                self.controller.LED_Buffer[self.index] = io_lum
            elif self.controller.led_Type=='RGB':
                _index= int(self.index )*3
                self.controller.led.buf[_index] = rgb[1]
                self.controller.led.buf[_index+1] = rgb[0]
                self.controller.led.buf[_index+2] = rgb[2]
            else:
                io_lum = int(lum)
            
            

        class LED_buf:
            def __init__(self, LED, index):
                self.LED = LED
                self.index = index

            @micropython.native
            def set_buf(self, lum:int):

                if self.index == 0 :
                   self.LED.set_led_H_buf(lum)
                elif self.index == 1:
                    self.LED.set_led_S_buf(lum)
                elif self.index == 2 :
                    self.LED.set_buf(lum)
                else:
                    self.LED.set_buf(lum)




    def setup(self):
        """初始化硬體設定"""
        if self.led_Type == 'esp_LED':
            self.led = [PWM(Pin(pin_number['GPIO']), freq=50, duty_u16=pin_number['dArc']) for pin_number in self.led_IO['led_IO']]

            
        elif self.led_Type == 'i2c_LED':
            self.led = self.led_IO['led_IO']
            
        elif self.led_Type == 'RGB':
            self.led = neopixel.NeoPixel(Pin(self.led_IO['led_IO'], Pin.OUT), self.led_IO['Q'])




    def reset(self):
        """重置所有LED狀態"""
        self.LED_Buffer = array.array('H',[0] * self.led_IO['Q'])
        if self.led_Type=='esp_LED':
            
            for idx, led in enumerate(self.led):
                self.LED_Buffer[idx] = self.led_IO['led_IO'][idx]['dArc']
                led.duty_u16(self.LED_Buffer[idx])
                
                
        if self.led_Type=='i2c_LED':
            self.led.buffer = self.LED_Buffer
            self.led.sync_buffer()

        if self.led_Type=='RGB':
            self.led_H = array.array('H',[0] * self.led_IO['Q'])
            self.led_S = array.array('B',[0] * self.led_IO['Q'])            
            self.led.fill((0,0,0))
            self.led.write()

    
    def duty(self, lum, ledQ=[]):
        try:
            value = int(lum * self.brightness / 4095)  # 添加亮度系数
            if self.led_Type in ('esp_LED', 'i2c_LED'):
                if len(ledQ) == 0:  # 全設
                    self.LED_Buffer = [value] * self.led_IO['Q']
                else:
                    for i in ledQ:
                        self.LED_Buffer[i] = value

            if self.led_Type=='RGB':
                if len(ledQ) == 0:  # 全設
                    self.LED_Buffer = [value] * self.led_IO['Q']
                    for i in range(self.led_IO['Q']):
                        self._hsv2grb_buf_index(self.led_H[i] ,self.led_S[i] ,value, i , self.led.buf) 
                else:
                    for i in ledQ:
                        self.LED_Buffer[i] = value
                        self._hsv2grb_buf_index(self.led_H[i] ,self.led_S[i] ,value, i , self.led.buf) 


            self.show()

        except BaseException as e:
            print(e)

    @micropython.viper
    def _hsv2grb_buf_index(self,h: int, s: int, v: int,index: int, buf: ptr8):
        """
        Convert HSV to RGB and return as an integer packed with RGB components.
        
        Arguments:
        h -- Hue value (0 to 360)
        s -- Saturation value (0 to 255)
        v -- Value/brightness (0 to 255)
        
        Returns:
        An integer where the most significant byte is red, the next byte is green, and the least significant byte is blue.
        """
        
        buf_index = index *3
        if s == 0:
            r = g = b = v
            buf[buf_index] = 255 if g > 255 else int(g)
            buf[buf_index+1] = 255 if r > 255 else int(r)
            buf[buf_index+2] = 255 if b > 255 else int(b)
            return 

        h = h % 360
        region = h // 60
        remainder = (h - (region * 60)) * 255 // 60

        p = (v * (255 - s)) // 255
        q = (v * (255 - ((s * remainder) // 255))) // 255
        t = (v * (255 - ((s * (255 - remainder)) // 255))) // 255

        if region == 0:
            r, g, b = v, t, p
        elif region == 1:
            r, g, b = q, v, p
        elif region == 2:
            r, g, b = p, v, t
        elif region == 3:
            r, g, b = p, q, v
        elif region == 4:
            r, g, b = t, p, v
        else:
            r, g, b = v, p, q
        
        buf[buf_index] = 255 if g > 255 else int(g)
        buf[buf_index+1] = 255 if r > 255 else int(r)
        buf[buf_index+2] = 255 if b > 255 else int(b)
        
        return 


    def set_be_light(self):
        try:
            if self.led_Type=='RGB':
                for i in range(self.led_IO['Q']):
                    self._hsv2grb_buf_index(self.led_H[i],self.led_S[i], self.LED_Buffer[i] ,i, self.led.buf)          
        except BaseException as e:
            print(e)


    def show(self):
        try:

            if self.led_Type=='esp_LED':
                for i in range(self.led_IO['Q']):
                    self.led[i].duty_u16(self.LED_Buffer[i])

            if self.led_Type=='i2c_LED':
                self.led.buffer = self.LED_Buffer
                self.led.sync_buffer()

            if self.led_Type=='RGB':
                self.led.write()
            
        except BaseException as e:
            print(e)




