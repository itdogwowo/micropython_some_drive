import time,machine

from TFTController import *
from JpegBufferController import *


class CountdownTimer:
    def __init__(self):
        self.total_time = 0  # 單位：秒
        self.current_time = 0
        self.is_running = False
        self.update_interval = 1000  # 單位：毫秒，預設1秒
        self.time_update_gen = []  # 生成器對象列表
        self.time_update_fun = []  # 函數對象列表
        self.end_gen = []          # 生成器對象列表
        self.end_fun = []          # 函數對象列表
        self.timer = None
        self.update_triggered = False
        self.end_triggered = False
        
        self.start_time = 0
        self.temp_time = 0

    def set_time(self, time):
        """設定計時時間（秒）"""
        self.total_time = time
        self.current_time = time  # 重置當前時間

    def get_current_time(self):
        """獲取當前剩餘時間（秒）"""
        return self.current_time

    def start(self):
        """開始計時"""
        if not self.is_running:
#             self.start_time = time.ticks_ms()
            self.is_running = True
            self.current_time = self.total_time  # 確保從設定時間開始
            # 初始化硬體定時器，使用虛擬定時器（-1）以節省硬體資源
            self.timer = machine.Timer(3)
            self.timer.init(period=self.update_interval, mode=machine.Timer.PERIODIC, callback=self._tick)

    def stop(self):
        """停止計時"""
        if self.is_running:
            self.is_running = False
            if self.timer:
                self.timer.deinit()
                self.timer = None

    def on_time_update(self, gen=None, fun=None):
        """添加時間更新事件的回調。參數為生成器列表或函數列表。"""
        if gen is not None:
            if isinstance(gen, list):
                self.time_update_gen.extend(gen)
            else:
                self.time_update_gen.append(gen)
        if fun is not None:
            if isinstance(fun, list):
                self.time_update_fun.extend(fun)
            else:
                self.time_update_fun.append(fun)

    def on_countdown_end(self, gen=None, fun=None):
        """添加計時結束事件的回調。參數為生成器列表或函數列表。"""
        if gen is not None:
            if isinstance(gen, list):
                self.end_gen.extend(gen)
            else:
                self.end_gen.append(gen)
        if fun is not None:
            if isinstance(fun, list):
                self.end_fun.extend(fun)
            else:
                self.end_fun.append(fun)

    def _tick(self, timer):
        """定時器中斷回調（每間隔呼叫一次）。保持簡潔以符合中斷要求。"""
        if self.is_running:
            self.current_time -= 1  # 減少當前時間（假設間隔為1秒）
            if self.current_time <= 0:
                self.current_time = 0
                self.end_triggered = True  # 標記計時結束
                self.is_running = False    # 停止計時
            else:
                self.update_triggered = True  # 標記時間更新

    def update(self):
        """處理待處理的回調事件。應在主循環中定期呼叫。"""
        # 處理時間更新事件
        
#         if self.is_running:
#             self.temp_time += time.ticks_diff( time.ticks_ms(),self.start_time)
#             self.start_time = time.ticks_ms()
#                 
#             if self.temp_time >= 1000:
#                 self.current_time -= 1
#                 self.temp_time -= 1000
#                 if self.current_time <= 0:
#                     self.current_time = 0
#                     self.end_triggered = True  # 標記計時結束
#                     self.is_running = False    # 停止計時
#                 else:
#                     self.update_triggered = True  # 標記時間更新

        if self.update_triggered:
            self.update_triggered = False
            current_time = self.current_time  # 獲取當前時間
            
            # 處理生成器回調：呼叫 send() 並傳遞當前時間
            to_remove_gen = []
            for i, gen in enumerate(self.time_update_gen):
                try:
                    gen.send(current_time)  # 傳遞當前時間給生成器
                except StopIteration:
                    to_remove_gen.append(i)  # 標記完成生成器
                except Exception as e:
                    print("生成器錯誤:", e)
                    to_remove_gen.append(i)  # 錯誤時移除生成器
            
            # 從後往前移除生成器，避免索引偏移
            for i in sorted(to_remove_gen, reverse=True):
                del self.time_update_gen[i]
            
            # 處理函數回調，傳遞當前時間
            for fun in self.time_update_fun:
                try:
                    fun(current_time)  # 呼叫函數並傳遞當前時間
                except Exception as e:
                    print("函數回調錯誤:", e)

        # 處理計時結束事件
        if self.end_triggered:
            self.end_triggered = False
            current_time = self.current_time  # 這裡應該是0
            
            # 處理生成器回調
            to_remove_gen = []
            for i, gen in enumerate(self.end_gen):
                try:
                    gen.send(current_time)  # 傳遞當前時間給生成器
                except StopIteration:
                    to_remove_gen.append(i)
                except Exception as e:
                    print("生成器錯誤:", e)
                    to_remove_gen.append(i)
            
            for i in sorted(to_remove_gen, reverse=True):
                del self.end_gen[i]
            
            # 處理函數回調，傳遞當前時間（0）
            for fun in self.end_fun:
                try:
                    fun(current_time)
                except Exception as e:
                    print("函數回調錯誤:", e)
            
            # 停止定時器
            self.stop()



class DisplayController:
    """主控制器類，管理LCD顯示和各種硬體交互"""
    def __init__(self, config, lcd, uart, encoder, encoder_button, buffer_mgr, timer,touch = None,reverse = False):
        # 硬體物件
        self.config = config
        self.lcd = lcd
        self.uart = uart
        self.encoder = encoder
        self.buffer_mgr = buffer_mgr
        self.timer = timer
        self.reverse = reverse
        # 按鈕處理器
        self.button_handler = ButtonController(encoder_button, self._on_button_event)
        if touch :
            self.touch_controller = TouchController(touch,touch_width=240, touch_height=320, rotation=3, callback=self._on_touche_event)
            self.touch_controller.add_button( 0, 0, 120, 48, callback=None, name="0")
            self.touch_controller.add_button( 0, 48, 120, 48, callback=None, name="1")
            self.touch_controller.add_button( 0, 96, 120, 48, callback=None, name="2")
            self.touch_controller.add_button( 0, 144, 120, 48, callback=None, name="3")
            self.touch_controller.add_button( 0, 192, 120, 48, callback=None, name="4")
        else:
            self.touch_controller = None
        # 狀態變數
        self.mode_count = 0
        self.last_mode_count = -1
        self.brightness_value = 1
        self.last_brightness_value = -1
        self.encoder_max = 0
        self.last_time = None
        self.frame_count = 0
        # 模式信息
        self.mod_info = None
        self.brightness_info = None
        # 初始化編碼器
        self.encoder.value(self.brightness_value)
        # 初始化顯示
        self._initialize_display()
        
        
    def _initialize_display(self):
        """初始化顯示背景和基本元素"""
        # 顯示背景
        bg_buf = self.buffer_mgr.get_background()
        if bg_buf:
            self.lcd.set_window(0, 0)
            self.lcd.write_data(bg_buf)
            
        self.brightness_info = self.buffer_mgr.get_resource_info('brightness')
        self.mod_info = self.buffer_mgr.get_resource_info('mod')
        self.loop_info = self.buffer_mgr.get_resource_info('loop')
        self.text_info = self.buffer_mgr.get_resource_info('text')
        
        self.encoder_max = self.brightness_info['depth']-1
        
        # 初始化時間顯示
        self.timer.start()
        self.last_time = self.timer.current_time
        self.time_buf = self.buffer_mgr.update_time_display(self.last_time)
        # 初始化模式顯示
        self._update_mode_display()
        # 初始化亮度顯示
        self._update_brightness_display()
    def _on_button_event(self, event_type):
        """處理按鈕事件"""
        if event_type == 'click':
            self._switch_mode()
            self._send_uart_update()
            print('click')
        elif event_type == 'double_click':
#             self._switch_mode()
#             self._send_uart_update('mode', self.mode_count)
  
#             _root_path = self.config['root_path']%self.config['patter']
#             root_path = f'/sd/{_root_path}/'
#             self.buffer_mgr.reinitialize(root_path)
            # 雙擊事件處理
            print("Double click detected")
            # 可以添加其他功能，比如重置設定等
        elif event_type == 'long_press':
            # 長按事件處理
            print("Long press detected")
            # 可以添加其他功能，比如進入設定模式等
    def _on_touche_event(self, ev_type, ev_value):
        """處理按鈕事件"""
        if ev_type == 'touche':
            self._switch_mode(ev_value)
            self._send_uart_update()
#             print('click')
        elif ev_type == 'brightness':
            self._handle_encoder(ev_value)
  
#             print("brightness",ev_value)
            # 可以添加其他功能，比如重置設定等
        elif ev_type == 'wifi':
            # 長按事件處理
            print("wifi")
            # 可以添加其他功能，比如進入設定模式等
    def _switch_mode(self,mode=None):
        """切換模式"""
        print('mode',mode)
        if mode != None:
            self.mode_count = mode % self.mod_info['depth']
              
        else:
            if self.mod_info:
                self.mode_count = (self.mode_count + 1) % self.mod_info['depth']
            else:
                self.mode_count = (self.mode_count + 1) % 3  # 默認3個模式
        if self.config['offline']:
            self.timer.set_time(self.buffer_mgr.counter_time[self.mode_count])
#         print(f"Mode switched to: {self.mode_count}")
    def _update_mode_display(self):
        """更新模式顯示"""
        mod_buf = self.buffer_mgr.jump_to_frame('mod', self.mode_count)
        if mod_buf:
            
            x, y = self.mod_info['x'], self.mod_info['y']
            if self.reverse :
                w, h =  self.mod_info['height'] , self.mod_info['width']
            else:
                w, h = self.mod_info['width'], self.mod_info['height']
            self.lcd.set_window(x, y, x + w - 1, y + h - 1)
            self.lcd.write_data(mod_buf)
    def _update_brightness_display(self):
        """更新亮度顯示"""
        brightness_buf = self.buffer_mgr.jump_to_frame('brightness', self.brightness_value)
        if brightness_buf:
            x, y = self.brightness_info['x'], self.brightness_info['y']
            if self.reverse :
                w, h =  self.brightness_info['height'] , self.brightness_info['width']
            else:
                w, h = self.brightness_info['width'], self.brightness_info['height']
            self.lcd.set_window(x, y, x + w - 1, y + h - 1)
            self.lcd.write_data(brightness_buf)
    def _update_time_display(self):
        """更新時間顯示"""
        new_time = self.timer.current_time
#         print(new_time)
        if self.config['offline'] and new_time == 0:
            self._switch_mode()
            self.timer.start()
        if self.last_time != new_time:
#             print('new_time:', new_time)
            self.last_time = new_time
            self.time_buf = self.buffer_mgr.update_time_display(new_time)
            return None
        return None
    def _update_loop_animation(self, time_buf):
        """更新循環動畫"""
        loop_buf = self.buffer_mgr.get_next_frame('loop')
        if loop_buf:
            
            if time_buf:
                text_x, text_y = self.text_info['x'], self.text_info['y']
                loop_buf.blit(time_buf, text_x, text_y,0)
            x, y = self.loop_info['x'], self.loop_info['y']
            if self.reverse :
                w, h =  self.loop_info['height'] , self.loop_info['width']
            else:
                w, h = self.loop_info['width'], self.loop_info['height']
            self.lcd.set_window(x, y, x + w - 1, y + h - 1)
            self.lcd.write_data(loop_buf)
    def _handle_encoder(self,in_data=None):
        """處理編碼器輸入"""
        encoder_value = self.encoder.value()
        if in_data !=None:
            encoder_value = encoder_value + in_data
            self.encoder.value(encoder_value)
  
        # 限制編碼器範圍
        if encoder_value > self.encoder_max:
            encoder_value = self.encoder_max
            self.encoder.value(self.encoder_max)
        elif encoder_value < 0:
            encoder_value = 0
            self.encoder.value(0)
        # 檢查亮度是否改變
        if self.brightness_value != encoder_value:
            self.brightness_value = encoder_value
            self._send_uart_update()
    def _send_uart_update(self):
        """發送UART更新信號"""
        if self.uart:
            _data = bytearray([0xB4,self.mode_count,self.brightness_value,self.last_time,0xFF])
            try:
                self.uart.write(_data)
            except Exception as e:
                print(f"UART send error: {e}")
    def _handle_uart_receive(self):
        """處理UART接收的數據 - 使用二進制格式"""
        if self.uart and self.uart.any():
            try:
                # 讀取所有可用字節
                data = self.uart.read()
                print(data)
                # 查找有效的數據包 (起始標誌0xB4，結束標誌0xFF)
                start_idx = -1
                for i in range(len(data)):
                    if data[i]==0xB4 and i + 4 < len(data) and data[i+4]==0xFF:
                        start_idx = i
                        break
  
                if start_idx != -1:
                    # 提取數據包內容
                    mode = data[start_idx + 1]
                    brightness = data[start_idx + 2]
                    time_remaining = data[start_idx + 3]
  
                    self._process_uart_command(mode, brightness, time_remaining)
            except Exception as e:
                print(f"UART receive error: {e}")
  
    def _process_uart_command(self, mode, brightness, time_remaining):
        """處理UART命令 - 直接使用二進制值"""
        # 更新模式
        if 0 <= mode <= 10:  # 常規模式
            self.mode_count = mode
            print(f"Mode changed to: {mode}")
        elif mode == 0x77:   # 程式錯誤模式
            print("Program error mode activated")
            # 處理錯誤模式的邏輯
        elif mode == 0x47:   # Wi-Fi模式
            print("Wi-Fi mode activated")
            # 處理Wi-Fi模式的邏輯
        # 更新亮度
        self.encoder.value(brightness)
        self.brightness_value = brightness
        # 更新剩餘時間
        if time_remaining >= 0:
#             self.timer.current_time = time_remaining
            self.timer.stop()
            self.timer.set_time(time_remaining)
            self.timer.start()
            print(f"Time remaining updated to: {time_remaining} seconds")
  
    def update(self,debug = False ):
        """主更新函數，在主循環中調用"""
        start_time = time.ticks_ms()
        # 更新按鈕狀態
        self.button_handler.update()
        self.button_handler.check_single_click()
        if self.touch_controller:
            self.touch_controller.update()
        # 處理編碼器
        self._handle_encoder()
        # 處理UART接收
        self._handle_uart_receive()
        # 更新計時器
        self.timer.update()
        # 更新時間顯示
        self._update_time_display()
#         self.time_buf = self._update_time_display()
        # 更新循環動畫
        self._update_loop_animation(self.time_buf)
        # 更新模式顯示（如果改變）
        if self.last_mode_count != self.mode_count:
            self.last_mode_count = self.mode_count
            self._update_mode_display()
        # 更新亮度顯示（如果改變）
        if self.last_brightness_value != self.brightness_value:
            self.last_brightness_value = self.brightness_value
            self._update_brightness_display()
#         self.frame_count += 1
        if debug :
            # 計算運行時間並控制幀率
            run_time = time.ticks_diff(time.ticks_ms(), start_time)
            print('run_time:', run_time)
            if run_time <= 20:
                time.sleep_ms(20 - run_time)
            return run_time
        else:
            return 0