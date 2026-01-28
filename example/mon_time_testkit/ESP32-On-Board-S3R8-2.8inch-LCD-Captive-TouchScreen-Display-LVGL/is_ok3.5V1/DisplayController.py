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
    def __init__(self, root_path, lcd, uart, encoder=None, encoder_button=None, touch=None, reverse=False):
        

        self.root_path = root_path
        with open(f'{root_path}/config.json', 'r') as openfile:
        # Reading from json file
            self.config = json.load(openfile)
            
        self.CPU_steps = True

        
        # 硬體物件初始化
        self.lcd = lcd
        self.uart = uart
        self.encoder = encoder
        self.encoder_button = encoder_button
        self.timer = CountdownTimer()
        self.reverse = reverse
        
        self._patter = self.config['patter']
        self._patter_range = range(self.config['patter'])
        self._root_path_template = self.config['root_path']%self._patter
        
        self._temp_buff = bytearray(self.config['lcd']['width'] * self.config['lcd']['height'] * 2)
        self.front_fb = framebuf.FrameBuffer(
            self._temp_buff,
            self.config['lcd']['width'],
            self.config['lcd']['height'],
            framebuf.RGB565
        )
        self.front_fb.fill(0XFFFF)
        
        
        # 按鈕和觸摸控制器初始化
        # +++ 只有當 encoder_button 不為 None 時才初始化按鈕處理器 +++
        if self.encoder_button is not None:
            self.button_handler = ButtonController(self.encoder_button, self._on_input_event)
        else:
            self.button_handler = None
            
        if touch is not None:
            self.touch_controller = TouchController(touch, touch_width=240, touch_height=320, rotation=3, callback=self._on_input_event)
            # 觸摸按鈕配置
            self.touch_controller.add_button(0, 0, 120, 48*2, callback=None, name="-1")
            self.touch_controller.add_button(0, 144, 120, 48*2, callback=None, name="1")

        else:
            self.touch_controller = None
            
        # 狀態變數初始化
        self.mode_count = 0
        self.last_mode_count = -1
        self.brightness_value = 0
        self.last_brightness_value = -1
        self.encoder_max = 0
        self.last_time = None
        self.frame_count = 0
        
        # 緩存最大模式數量
        self.max_mode = 3  # 默認值，將在 _initialize_display 中更新
        
        # 模式信息初始化
        self.mod_info = None
        self.brightness_info = None
        
        if self.encoder is not None:
            self.encoder.value(self.brightness_value)
        self._initialize_display(self._root_path_template)
        
    def _initialize_display(self,patter = 0):
        """初始化顯示背景和基本元素"""
        _root_path = patter%self._patter 
        root_path = f'{self.root_path}/{_root_path}/'
        self.buffer_mgr = JpegBufferController(root_path)
        
        self._root_path_template = _root_path
        
        bg_buf = self.buffer_mgr.get_background()
        if bg_buf:
            self.lcd.set_window(0, 0)
            self.lcd.write_data(bg_buf)
        self.brightness_info = self.buffer_mgr.get_resource_info('brightness')
        self.mod_info = self.buffer_mgr.get_resource_info('mod')
        self.loop_info = self.buffer_mgr.get_resource_info('loop')
        self.text_info = self.buffer_mgr.get_resource_info('text')
        self.encoder_max = self.brightness_info['depth']
        
        # 初始化最大模式數量
        if self.mod_info:
            self.max_mode = self.mod_info['depth']
        else:
            self.max_mode = 3  # 默認值
            
        if self.config['offline']:
            self.timer.set_time(self.buffer_mgr.counter_time[0])
        
        self.timer.start()
        self.last_time = self.timer.current_time
        self.time_buf = self.buffer_mgr.update_time_display(self.last_time)
        
        self._update_mode_display()
        self._update_brightness_display()
        
    def _reinitialize(self,patter = 0):
        """重新初始化顯示控制器：更新配置並重新加載資源"""
        try:
            # 重新初始化顯示
            self._initialize_display(patter)
            # 確保狀態值在新範圍內有效
            self._set_state(mode=self.mode_count, brightness=self.brightness_value, source='local')
#             print("Reinitialization completed successfully")
        except Exception as e:
            print(f"Error during reinitialization: {e}")

    def _on_input_event(self, event_type, event_value=None):
        """整合的輸入事件處理器
        處理所有輸入事件（按鈕和觸摸）
        
        Args:
            event_type: 事件類型
                - 'click': 按鈕單擊
                - 'double_click': 按鈕雙擊  
                - 'long_press': 按鈕長按
                - 'touche': 觸摸模式切換
                - 'brightness': 觸摸亮度調整
                - 'wifi': 觸摸Wi-Fi功能
            event_value: 事件值（對於觸摸事件）
        """
        if event_type in ['click', 'touche']:
            # 處理模式切換
            if event_type == 'click':
                # 按鈕單擊：切換到下一個模式
                new_mode = self.mode_count + 1
            else:  # touche
                # 觸摸事件：直接切換到指定模式
                new_mode = self.mode_count + event_value
#                 new_mode = event_value
            
            self._set_state(mode=new_mode, source='local')
#             print(f'{event_type} event - mode: {new_mode}')
            
        elif event_type == 'brightness':
            # 處理亮度調整
            current_brightness = self.brightness_value
            new_brightness = current_brightness + event_value
            self._set_state(brightness=new_brightness, source='local')
#             print(f'brightness event - value: {event_value}')
            
        elif event_type == 'double_click':
            # 雙擊事件處理
            pass
#             print("Double click detected")
            # 可添加其他功能，如重置設定
            
        elif event_type == 'long_press':
            # 長按事件處理
            pass
#             print("Long press detected")
            # 可添加其他功能，如進入設定模式
        elif event_type == 'change_pattern':
            
            current_pattern = self._root_path_template
            result = current_pattern + event_value
            
            
            self.lcd.set_window(0, 0)
            self.lcd.write_data(self._temp_buff)
                        
            self._reinitialize(result)
#             print("change_pattern event")
            # 可添加 Wi-Fi 相關功能
            
        elif event_type == 'wifi':
            self._set_state(mode=0x47, source='local')
#             print("wifi event")
            # 可添加 Wi-Fi 相關功能

    def _set_state(self, mode=None, brightness=None, time=None, source='local'):
        """統一設置狀態：模式、亮度、時間"""
        old_mode = self.mode_count
        old_brightness = self.brightness_value
        
        # 使用緩存的 max_mode 而不是每次計算
        max_mode = self.max_mode
        
        # 處理模式改變
        if mode is not None:
            new_mode = mode % max_mode  # 使用緩存的 max_mode
            if new_mode != old_mode:
                self.mode_count = new_mode
                # 如果離線模式，設置計時器時間
                if self.config['offline']:
                    self.last_time = self.buffer_mgr.counter_time[self.mode_count]
                    self.timer.set_time(self.last_time)
                    self.timer.start()
        
        # 處理亮度改變
        if brightness is not None:
            # 限制亮度範圍
            if brightness > self.encoder_max:
                brightness = self.encoder_max
            elif brightness < 0:
                brightness = 0
            if brightness != old_brightness:
                self.brightness_value = brightness
                # +++ 只有當 encoder 不為 None 時才更新編碼器硬件值 +++
                if self.encoder is not None:
                    self.encoder.value(brightness)
        
        # 處理時間改變
        if time is not None:
            self.last_time = time
            self.timer.set_time(self.last_time)
            self.timer.start()
        
        # 如果狀態改變且來源為本地，發送 UART 更新
        state_changed = (mode is not None and self.mode_count != old_mode) or (brightness is not None and self.brightness_value != old_brightness)
        if state_changed and source == 'local':
            self._send_uart_update()

    

    def _handle_encoder(self, in_data=None):
        """處理編碼器輸入 - 使用 _set_state"""
        # +++ 只有當 encoder 不為 None 時才處理編碼器輸入 +++
        if self.encoder is None:
            return
            
        if in_data is not None:
            # in_data 為增量，計算新亮度值
            current_value = self.encoder.value()
            new_brightness = current_value + in_data
            self._set_state(brightness=new_brightness, source='local')
        else:
            # 輪詢當前編碼器值
            current_value = self.encoder.value()
            self._set_state(brightness=current_value, source='local')

    def _process_uart_command(self, mode, brightness, time_remaining):
        """處理 UART 命令 - 使用 _set_state"""
        # 處理常規模式
        if 0 <= mode <= 10:  # 常規模式範圍
            self._set_state(mode=mode, source='uart')
        elif mode == 0x77:   # 程式錯誤模式
            pass
#             print("Program error mode activated")
            # 可設置錯誤狀態
        elif mode == 0x47:   # Wi-Fi 模式
            pass
#             print("Wi-Fi mode activated")
            # 可設置 Wi-Fi 狀態
        
        # 更新亮度和時間
        self._set_state(time=time_remaining,brightness=brightness, source='uart')
#         self._set_state(brightness=brightness, source='uart')
#         if time_remaining >= 0:
#             self._set_state(time=time_remaining, source='uart')

    # 以下顯示更新方法保持不變
    def _update_mode_display(self):
        """更新模式顯示"""
        mod_buf = self.buffer_mgr.jump_to_frame('mod', self.mode_count)
        if mod_buf:
            x, y = self.mod_info['x'], self.mod_info['y']
            if self.reverse:
                w, h = self.mod_info['height'], self.mod_info['width']
            else:
                w, h = self.mod_info['width'], self.mod_info['height']
            self.lcd.set_window(x, y, x + w - 1, y + h - 1)
            self.lcd.write_data(mod_buf)

    def _update_brightness_display(self):
        """更新亮度顯示"""
        brightness_buf = self.buffer_mgr.jump_to_frame('brightness', self.brightness_value)
        if brightness_buf:
            x, y = self.brightness_info['x'], self.brightness_info['y']
            if self.reverse:
                w, h = self.brightness_info['height'], self.brightness_info['width']
            else:
                w, h = self.brightness_info['width'], self.brightness_info['height']
            self.lcd.set_window(x, y, x + w - 1, y + h - 1)
            self.lcd.write_data(brightness_buf)

    def _update_time_display(self):
        """更新時間顯示"""
        new_time = self.timer.current_time
        if self.config['offline'] and new_time == 0:
            # 離線模式下時間為0時自動切換模式
            new_mode = self.mode_count + 1
            self._set_state(mode=new_mode, source='local')
            self.timer.start()
        if self.last_time != new_time:
            self.last_time = new_time
            self.time_buf = self.buffer_mgr.update_time_display(new_time)
        return None

    def _update_loop_animation(self, time_buf):
        """更新循環動畫"""
        if self.CPU_steps:
            self.loop_fb = self.buffer_mgr.get_next_frame('loop')
        else:
            if self.loop_fb:
                if time_buf:
                    text_x, text_y = self.text_info['x'], self.text_info['y']
                    self.loop_fb.blit(time_buf, text_x, text_y, 0)
                x, y = self.loop_info['x'], self.loop_info['y']
                if self.reverse:
                    w, h = self.loop_info['height'], self.loop_info['width']
                else:
                    w, h = self.loop_info['width'], self.loop_info['height']
                self.lcd.set_window(x, y, x + w - 1, y + h - 1)
                self.lcd.write_data(self.loop_fb)

    def _send_uart_update(self):
        """發送 UART 更新信號"""
        if self.uart:
            _data = bytearray([0xB4, self.mode_count, self.brightness_value, self.last_time, 0xFF])
            try:
                self.uart.write(_data)
            except Exception as e:
                print(f"UART send error: {e}")

    def _handle_uart_receive(self):
        """處理 UART 接收的數據"""
        if self.uart and self.uart.any():
            try:
                data = self.uart.read()
#                 print(data)
                start_idx = -1
                for i in range(len(data)):
                    if data[i] == 0xB4 and i + 4 < len(data) and data[i+4] == 0xFF:
                        start_idx = i
                        break
                if start_idx != -1:
                    mode = data[start_idx + 1]
                    brightness = data[start_idx + 2]
                    time_remaining = data[start_idx + 3]
                    self._process_uart_command(mode, brightness, time_remaining)
            except Exception as e:
                print(f"UART receive error: {e}")
                

    def update(self, debug=False):
        """主更新函數"""
        start_time = time.ticks_ms()
        
        # +++ 只有當 button_handler 不為 None 時才更新按鈕狀態 +++
        if self.button_handler is not None:
            self.button_handler.update()
            self.button_handler.check_single_click()
            
        if self.touch_controller:
            self.touch_controller.update()
        
        # 處理編碼器和 UART
        self._handle_encoder()
        self._handle_uart_receive()
        
        # 更新計時器和顯示
        self.timer.update()
        self._update_time_display()
        self._update_loop_animation(self.time_buf)
        
        # 檢查狀態改變並更新顯示
        if self.last_mode_count != self.mode_count:
            self.last_mode_count = self.mode_count
            self._update_mode_display()
        if self.last_brightness_value != self.brightness_value:
            self.last_brightness_value = self.brightness_value
            self._update_brightness_display()
            
        if self.CPU_steps:
            self.CPU_steps = not self.CPU_steps
        else:
            self.CPU_steps = not self.CPU_steps
            
        if debug:
            run_time = time.ticks_diff(time.ticks_ms(), start_time)
            print('run_time:', run_time)
            if run_time <= 20:
                time.sleep_ms(20 - run_time)
            return run_time
        else:
            return 0