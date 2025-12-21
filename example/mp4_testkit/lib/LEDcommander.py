from lib.LEDMathMethod import *
import _thread


class LEDcommander:
    def __init__(self, led_list, rgb_list,_uart = None,buf_table = []):
        self.mt =  LEDMathMethod()
        self.led_list = led_list
        self.rgb_list = rgb_list
        self._uart = _uart
        self.buf_table = buf_table

        self.channel = 3


        self.run_Sorting = 0
        self.address = 0
        self.keep_run = True
        self.buffer_Time = 0

        self._Channel_0_buffer_Time = 0
        self._Channel_1_buffer_Time = 0

        self.running_lock = False
        self.encoder = None  # 添加encoder属性
        self.debug = False  # 添加debug属性
    
    def init_all(self):

        for i in self.led_list:
            i.reset()

        for i in self.rgb_list:
            i.reset()

        return 
    
    def dual_Channel(self,run_time,gap_Time ,encoder,debug):
        
        while self.running_lock :
            start_time = time.ticks_ms()
            bright = encoder if self.encoder is None else self.encoder.position
            for i in self.led_list:
                i.show()
            for i in self.rgb_list:
                i.set_be_light()
                i.show()

            self._calculate_timing(1, start_time, gap_time,debug)            
        print('cpu2 END' )

    @micropython.native
    def show_all(self,channel,bright = 4095):

        if  0 <= channel <= 1 :
            for i in self.led_list[channel::2]:
                i.brightness = bright
                i.show()
            for i in self.rgb_list[channel::2]:
                i.brightness = bright
                i.set_be_light()
                i.show()
                # i.up_lock = False

        elif channel == 3:
            for i in self.led_list:
                i.brightness = bright
                i.show()

            for i in self.rgb_list:
                i.brightness = bright
                i.set_be_light()
                i.show()

        elif channel == 4:
            for i in self.led_list:
                i.brightness = bright
                i.show()

            for i in self.rgb_list:
                i.brightness = bright
                # i.set_be_light()
                i.show()
        
            

        return



    def buffer_gen(self,input_path,buf_Fun,in_data):
       
        run_time = in_data.get('run_time', 1)
        led_n = in_data.get('led_n', 1)
        _add = in_data.get('_add', 2)
        _read = in_data.get('_read', 0)  # 修复：使用正确的键名'_read'
        _seek = 0

        for i in range(run_time):
            re_buf = buf_Fun(input_path=input_path, now=i, led_n=led_n, buf_seek=_seek, buf_read=_read)
            _seek = _seek + _add
            yield re_buf

    def buffer_next(self,input_path ,buf_seek = None ):
        folder_Name = input_path.split('/')[-1].split('.')[0]
        read_function = folder_Name.split('_')
        run_time = read_function[-1]
        led_n = read_function[-2]
        buffer_type= read_function[-3]
        
        _read = 3 * int(led_n)
        _add = 0
        _seek = 0 if buf_seek == None else  buf_seek

        in_data = {
            'run_time' :int(run_time),
            'led_n' :int(led_n),
            'buffer_type' :buffer_type,
            '_read' :int(_read),
            '_add' :int(_add),
            '_seek' :int(_seek),
        }

        if buffer_type == 'grbBuf':
            in_data['_add'] =_read
            _buffer = self.buffer_gen(input_path, read_rgb_buffer , in_data)

        elif buffer_type == 'LED':
            in_data['_add'] =2
            _buffer = self.buffer_gen(input_path, read_led_buffer, in_data)

        elif buffer_type == 'esp_LED':
            in_data['_add'] =2
            _buffer = self.buffer_gen(input_path, read_led_buffer, in_data)

        elif buffer_type == 'i2c_LED':
            in_data['_add'] =2
            _buffer = self.buffer_gen(input_path, read_led_buffer, in_data)

        else:
            pass

        return _buffer

    @micropython.native
    def _handle_basic_led(self, led: dict, frame: int) -> None:
        """处理基础类型 LED (单色)"""
        try:
            value = next(led['_generators'])
            if isinstance(value, int):
                for io in led['GPIO']:
                    if type(io) == list:
                        for _led in led_list:
                            _led.set_buf(value)
                    else:
                        io.set_buf(value)
            elif isinstance(value, tuple) or isinstance(value, list):
                for idx, io in enumerate(led['GPIO']):
                    _value = value[idx % len(value)]
                    if type(io) == list:
                        for _led in io:
                            _led.set_buf(_value)
                    else:
                        io.set_buf(_value)
                    
        except StopIteration:
            print(f"LED {led['type']} generator exhausted")

    @micropython.native
    def _handle_rgb_led(self, led: dict, frame: int) -> None:
        """处理 RGB LED"""
        try:
            rgb_values = next(led['_generators'])
            for io in led['GPIO']:
                buf_length = len(io.led.buf)
                io.up_lock = Turn
                io.led.buf[:] = rgb_values[:buf_length]
        except StopIteration:
            print(f"RGB LED generator exhausted")


    @micropython.native
    def _calculate_timing(self,channel, start_time, gap_time,debug):
        """計算剩餘時間並管理緩衝區"""
        end_time = time.ticks_ms()
        elapsed = time.ticks_diff(end_time, start_time)
        remaining = gap_time - elapsed

        if remaining > 0:
            time.sleep_ms(remaining)
            if channel == 0:
                self._Channel_0_buffer_Time = max(-1000, self._Channel_0_buffer_Time + remaining)
            elif remaining == 1:
                self._Channel_1_buffer_Time = max(-1000, self._Channel_1_buffer_Time + remaining)
            else:
                self.buffer_Time = max(-1000, self.buffer_Time + remaining)
                
        elif remaining == 0:
            pass
        else:
            if channel == 0:
                self._Channel_0_buffer_Time = max(-1000, self._Channel_0_buffer_Time + remaining)
            elif remaining == 1:
                self._Channel_1_buffer_Time = max(-1000, self._Channel_1_buffer_Time + remaining)
            else:
                self.buffer_Time += elapsed - gap_time
                
            if debug:
                print(f'CPU{channel}: 每帧用時間: {elapsed}ms')

    @micropython.native
    def _check_headers(self, headers: List[Callable]) -> bool:
        """檢查所有 header 條件"""
        return all(header() for header in headers)

    @micropython.native
    def _update_led_state(self, led: dict, frame: int):
        """更新單個 LED 的狀態"""
        if led['type'] in {'esp_LED', 'i2c_LED', 'LED'}:
            self._handle_basic_led(led, frame)  # 修复：传递frame而不是未定义的re_value
        elif led['type'] == 'RGB':
            self._handle_rgb_led(led, frame)  # 修复：传递frame而不是未定义的re_value

    def run_Pattern(self, led_init , gap_Time = 20, run_time = 0,
                    encoder = 4095, headers = [], set_buffer=[],
                    ex_fun=[],ex_gen=[], debug=False ):

        self.buffer_Time = 0
        self.running_lock = True
        start_run_time = time.ticks_ms()

        for i in led_init:
            p = i.get('pattern' ,None)
            if p :
                i['_generators'] = self.mt.is_math_pattern_next(p)
                t__time = i['pattern'][-1]['end_Time']
                run_time = t__time if t__time  > run_time else run_time


        # _thread.start_new_thread(self.dual_Channel, (run_time,gap_Time ,encoder,debug))            
        for frame in range(run_time):
            # 检查是否应该继续运行
            for header in headers:
                if header(self,frame):
                    print("執行暫停")
                    break

            if not self.keep_run:
                print("執行中止")
                break

            # 記錄開始時間
            start_time = time.ticks_ms()


            # 更新所有 LED 狀態
            for led in led_init:
                self._update_led_state(led, frame)

            # 執行緩衝區回調
            for callback in set_buffer:
                callback(self,frame)

            for callback in ex_gen:
                next(callback)


            # 應用亮度並顯示
            # self.show_all(0,encoder if self.encoder is None else self.encoder.position)
            # self.show_all(1,encoder if self.encoder is None else self.encoder.position)
            
            self.show_all(self.channel ,encoder if self.encoder is None else self.encoder.position)

            # 時間管理
            self._calculate_timing(0,start_time, gap_Time ,debug )


        self.keep_run = True
        end_run_time = time.ticks_ms()
        elapsed = time.ticks_diff(end_run_time, start_run_time)

        print(f'run_pg_time: {elapsed}',f'buffer_Time: {self.buffer_Time}')




