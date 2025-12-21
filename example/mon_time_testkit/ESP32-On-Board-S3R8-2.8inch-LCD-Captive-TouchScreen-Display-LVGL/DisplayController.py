import time,machine

from TFTController import *
from JpegBufferController import *


class CountdownTimer:
    """倒計時器 - 使用硬體定時器"""
    def __init__(self):
        self.total_time = 0
        self.current_time = 0
        self.is_running = False
        self.update_interval = 1000  # 1秒
        self.time_update_gen = []
        self.time_update_fun = []
        self.end_gen = []
        self.end_fun = []
        self.timer = None
        self.update_triggered = False
        self.end_triggered = False
    
    def set_time(self, time):
        """設定計時時間（秒）"""
        self.total_time = time
        self.current_time = time
    
    def get_current_time(self):
        """獲取當前剩餘時間（秒）"""
        return self.current_time
    
    def start(self):
        """開始計時"""
        if not self.is_running:
            self.is_running = True
            self.current_time = self.total_time
            self.timer = machine.Timer(3)
            self.timer.init(
                period=self.update_interval,
                mode=machine.Timer.PERIODIC,
                callback=self._tick
            )
    
    def stop(self):
        """停止計時"""
        if self.is_running:
            self.is_running = False
            if self.timer:
                self.timer.deinit()
                self.timer = None
    
    def on_time_update(self, gen=None, fun=None):
        """添加時間更新事件的回調"""
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
        """添加計時結束事件的回調"""
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
        """定時器中斷回調"""
        if self.is_running:
            self.current_time -= 1
            if self.current_time <= 0:
                self.current_time = 0
                self.end_triggered = True
                self.is_running = False
            else:
                self.update_triggered = True
    
    def update(self):
        """處理待處理的回調事件（應在主循環中定期呼叫）"""
        # 處理時間更新事件
        if self.update_triggered:
            self.update_triggered = False
            current_time = self.current_time
            
            # 處理生成器回調
            to_remove_gen = []
            for i, gen in enumerate(self.time_update_gen):
                try:
                    gen.send(current_time)
                except StopIteration:
                    to_remove_gen.append(i)
                except Exception as e:
                    print(f"生成器錯誤: {e}")
                    to_remove_gen.append(i)
            
            for i in sorted(to_remove_gen, reverse=True):
                del self.time_update_gen[i]
            
            # 處理函數回調
            for fun in self.time_update_fun:
                try:
                    fun(current_time)
                except Exception as e:
                    print(f"函數回調錯誤: {e}")
        
        # 處理計時結束事件
        if self.end_triggered:
            self.end_triggered = False
            current_time = self.current_time
            
            # 處理生成器回調
            to_remove_gen = []
            for i, gen in enumerate(self.end_gen):
                try:
                    gen.send(current_time)
                except StopIteration:
                    to_remove_gen.append(i)
                except Exception as e:
                    print(f"生成器錯誤: {e}")
                    to_remove_gen.append(i)
            
            for i in sorted(to_remove_gen, reverse=True):
                del self.end_gen[i]
            
            # 處理函數回調
            for fun in self.end_fun:
                try:
                    fun(current_time)
                except Exception as e:
                    print(f"函數回調錯誤: {e}")
            
            self.stop()


class DisplayController:
    """主控制器類，管理LCD顯示和各種硬體交互 - 高性能優化版"""
    def __init__(self, root_path, lcd, uart, encoder=None, encoder_button=None, touch=None, reverse=False):
        """
        初始化顯示控制器
        
        Args:
            root_path: 資源根目錄
            lcd: LCD 顯示對象
            uart: UART 通訊對象
            encoder: 編碼器對象 (可選)
            encoder_button: 編碼器按鈕 (可選)
            touch: 觸摸控制器 (可選)
            reverse: 是否反轉寬高
        """
        self.root_path = root_path
        self.CPU_steps = True
        
        # 載入配置文件
        with open(f'{root_path}/config.json', 'r') as openfile:
            self.config = json.load(openfile)
        
        # 硬體物件初始化
        self.lcd = lcd
        self.uart = uart
        self.encoder = encoder
        self.encoder_button = encoder_button
        self.timer = CountdownTimer()
        self.reverse = reverse
        
        # 配置參數
        self._patter = self.config['patter']
        self._patter_range = range(self._patter)
        self._root_path_template = self.config['root_path'] % self._patter
        
        # 創建臨時緩衝區 (用於清屏等操作)
        self._temp_buff = bytearray(
            self.config['lcd']['width'] * self.config['lcd']['height'] * 2
        )
        self.front_fb = framebuf.FrameBuffer(
            self._temp_buff,
            self.config['lcd']['width'],
            self.config['lcd']['height'],
            framebuf.RGB565
        )
        self.front_fb.fill(0xFFFF)
        
        # 按鈕和觸摸控制器初始化
        if self.encoder_button is not None:
            self.button_handler = ButtonController(
                self.encoder_button,
                self._on_input_event
            )
        else:
            self.button_handler = None
        
        if touch is not None:
            self.touch_controller = TouchController(
                touch,
                touch_width=240,
                touch_height=320,
                rotation=3,
                callback=self._on_input_event
            )
            # 觸摸按鈕配置
            self.touch_controller.add_button(0, 0, 120, 48, callback=None, name="0")
            self.touch_controller.add_button(0, 48, 120, 48, callback=None, name="1")
            self.touch_controller.add_button(0, 96, 120, 48, callback=None, name="2")
            self.touch_controller.add_button(0, 144, 120, 48, callback=None, name="3")
            self.touch_controller.add_button(0, 192, 120, 48, callback=None, name="4")
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
        self.max_mode = 3
        
        # 模式信息初始化
        self.mod_info = None
        self.brightness_info = None
        self.loop_info = None
        self.text_info = None
        
        # 設置編碼器初始值
        if self.encoder is not None:
            self.encoder.value(self.brightness_value)
        
        # 初始化顯示
        self._initialize_display(self._root_path_template)
    
    def _initialize_display(self, patter=0):
        """初始化顯示背景和基本元素"""
        _root_path = patter % self._patter
        root_path = f'{self.root_path}/{_root_path}/'
        
        # 初始化緩衝管理器
        self.buffer_mgr = JpegBufferController(root_path)
        self._root_path_template = _root_path
        
        # 顯示背景
        bg_fb = self.buffer_mgr.get_background()
        if bg_fb:
            self.lcd.set_window(0, 0)
            self.lcd.write_data(bytes(bg_fb))
        
        # 獲取資源信息
        self.brightness_info = self.buffer_mgr.get_resource_info('brightness')
        self.mod_info = self.buffer_mgr.get_resource_info('mod')
        self.loop_info = self.buffer_mgr.get_resource_info('loop')
        self.text_info = self.buffer_mgr.get_resource_info('text')
        
        # 設置編碼器最大值
        if self.brightness_info:
            self.encoder_max = self.brightness_info['depth'] - 1
        
        # 初始化最大模式數量
        if self.mod_info:
            self.max_mode = self.mod_info['depth']
        else:
            self.max_mode = 3
        
        # 初始化計時器
        if self.config['offline']:
            self.timer.set_time(self.buffer_mgr.counter_time[0])
        self.timer.start()
        self.last_time = self.timer.current_time
        
        # 更新初始顯示
        self.time_buf = self.buffer_mgr.update_time_display(self.last_time)
        self._update_mode_display()
        self._update_brightness_display()
    
    def _reinitialize(self, patter=0):
        """重新初始化顯示控制器：更新配置並重新加載資源"""
        try:
            # 重新初始化顯示
            self._initialize_display(patter)
            
            # 確保狀態值在新範圍內有效
            self._set_state(
                mode=self.mode_count,
                brightness=self.brightness_value,
                source='local'
            )
            
            print("✓ Reinitialization completed")
        except Exception as e:
            print(f"✗ Reinitialization error: {e}")
    
    def _on_input_event(self, event_type, event_value=None):
        """
        整合的輸入事件處理器
        
        Args:
            event_type: 事件類型
                - 'click': 按鈕單擊
                - 'double_click': 按鈕雙擊
                - 'long_press': 按鈕長按
                - 'touche': 觸摸模式切換
                - 'brightness': 觸摸亮度調整
                - 'change_pattern': 切換圖案
                - 'wifi': Wi-Fi 功能
            event_value: 事件值
        """
        if event_type in ['click', 'touche']:
            # 處理模式切換
            if event_type == 'click':
                new_mode = self.mode_count + 1
            else:
                new_mode = event_value
            
            self._set_state(mode=new_mode, source='local')
            print(f'{event_type} event - mode: {new_mode}')
        
        elif event_type == 'brightness':
            # 處理亮度調整
            new_brightness = self.brightness_value + event_value
            self._set_state(brightness=new_brightness, source='local')
            print(f'brightness event - value: {event_value}')
        
        elif event_type == 'double_click':
            print("Double click detected")
            # 可添加其他功能
        
        elif event_type == 'long_press':
            print("Long press detected")
            # 可添加其他功能
        
        elif event_type == 'change_pattern':
            current_pattern = self._root_path_template
            result = current_pattern + event_value
            
            # 清屏
            self.lcd.set_window(0, 0)
            self.lcd.write_data(self._temp_buff)
            
            # 重新初始化
            self._reinitialize(result)
            print("change_pattern event")
        
        elif event_type == 'wifi':
            self._set_state(mode=0x47, source='local')
            print("wifi event")
    
    def _set_state(self, mode=None, brightness=None, time=None, source='local'):
        """
        統一設置狀態：模式、亮度、時間
        
        優化:
        - 只在狀態真正改變時才觸發更新
        - 使用非阻塞 jump_to_frame
        - 立即啟動解碼,避免延遲
        """
        old_mode = self.mode_count
        old_brightness = self.brightness_value
        state_changed = False
        
        # 處理模式改變
        if mode is not None:
            new_mode = mode % self.max_mode
            if new_mode != old_mode:
                self.mode_count = new_mode
                state_changed = True
                
                # 離線模式下設置計時器
                if self.config['offline']:
                    self.last_time = self.buffer_mgr.counter_time[self.mode_count]
                    self.timer.set_time(self.last_time)
                    self.timer.start()
                
                # 立即啟動解碼 (非阻塞)
                self.buffer_mgr.jump_to_frame('mod', self.mode_count)
        
        # 處理亮度改變
        if brightness is not None:
            # 限制亮度範圍
            brightness = max(0, min(brightness, self.encoder_max))
            if brightness != old_brightness:
                self.brightness_value = brightness
                state_changed = True
                
                # 更新編碼器硬體值
                if self.encoder is not None:
                    self.encoder.value(brightness)
                
                # 立即啟動解碼 (非阻塞)
                self.buffer_mgr.jump_to_frame('brightness', self.brightness_value)
        
        # 處理時間改變
        if time is not None:
            self.last_time = time
            self.timer.set_time(self.last_time)
            self.timer.start()
        
        # 發送 UART 更新
        if state_changed and source == 'local':
            self._send_uart_update()
    
    def _handle_encoder(self, in_data=None):
        """處理編碼器輸入"""
        if self.encoder is None:
            return
        
        if in_data is not None:
            # 增量模式
            current_value = self.encoder.value()
            new_brightness = current_value + in_data
            self._set_state(brightness=new_brightness, source='local')
        else:
            # 輪詢模式
            current_value = self.encoder.value()
            self._set_state(brightness=current_value, source='local')
    
    def _process_uart_command(self, mode, brightness, time_remaining):
        """處理 UART 命令"""
        # 處理常規模式
        if 0 <= mode <= 10:
            self._set_state(mode=mode, source='uart')
        elif mode == 0x77:
            print("Program error mode activated")
        elif mode == 0x47:
            print("Wi-Fi mode activated")
        
        # 更新亮度和時間
        self._set_state(
            time=time_remaining,
            brightness=brightness,
            source='uart'
        )
    
    def _update_mode_display(self):
        """
        更新模式顯示 (非阻塞版本)
        
        特性:
        - 重複調用同一模式不會重複解碼
        - 立即返回當前可用畫面
        - 後台自動完成解碼
        """
        # 非阻塞跳轉 (可能返回上一幀,但不會卡住)
        mod_fb = self.buffer_mgr.jump_to_frame('mod', self.mode_count)
        
        if mod_fb:
            x, y = self.mod_info['x'], self.mod_info['y']
            
            if self.reverse:
                w, h = self.mod_info['height'], self.mod_info['width']
            else:
                w, h = self.mod_info['width'], self.mod_info['height']
            
            # 直接寫入 LCD (零拷貝)
            self.lcd.set_window(x, y, x + w - 1, y + h - 1)
            self.lcd.write_data(bytes(mod_fb))
    
    def _update_brightness_display(self):
        """更新亮度顯示 (非阻塞,去重)"""
        brightness_fb = self.buffer_mgr.jump_to_frame(
            'brightness',
            self.brightness_value
        )
        
        if brightness_fb:
            x, y = self.brightness_info['x'], self.brightness_info['y']
            
            if self.reverse:
                w, h = self.brightness_info['height'], self.brightness_info['width']
            else:
                w, h = self.brightness_info['width'], self.brightness_info['height']
            
            self.lcd.set_window(x, y, x + w - 1, y + h - 1)
            self.lcd.write_data(bytes(brightness_fb))
    
    def _update_time_display(self):
        """更新時間顯示"""
        new_time = self.timer.current_time
        
        # 離線模式下時間為0時自動切換模式
        if self.config['offline'] and new_time == 0:
            new_mode = self.mode_count + 1
            self._set_state(mode=new_mode, source='local')
            self.timer.start()
        
        # 只在時間改變時更新
        if self.last_time != new_time:
            self.last_time = new_time
            self.time_buf = self.buffer_mgr.update_time_display(new_time)
    
    def _update_loop_animation(self, time_buf):
        """
        更新循環動畫 (優化版本)
        
        優化:
        - 零拷貝獲取幀緩衝
        - 使用 blit 合成時間顯示
        - 直接寫入 LCD
        """
        # 獲取下一幀動畫 (零拷貝)
        if self.CPU_steps:
            self.loop_fb = self.buffer_mgr.get_next_frame('loop')
        
        else:
        
            if self.loop_fb:
                # 如果有時間顯示,使用 blit 合成
                if time_buf:
                    text_x, text_y = self.text_info['x'], self.text_info['y']
                    loop_fb.blit(time_buf, text_x, text_y,0)
                
                # 計算顯示區域
                x, y = self.loop_info['x'], self.loop_info['y']
                
                if self.reverse:
                    w, h = self.loop_info['height'], self.loop_info['width']
                else:
                    w, h = self.loop_info['width'], self.loop_info['height']
                
                # 直接寫入 LCD (零拷貝)
                self.lcd.set_window(x, y, x + w - 1, y + h - 1)
                self.lcd.write_data(self.loop_fb)
    
    def _send_uart_update(self):
        """發送 UART 更新信號"""
        if self.uart:
            _data = bytearray([
                0xB4,
                self.mode_count,
                self.brightness_value,
                self.last_time,
                0xFF
            ])
            try:
                self.uart.write(_data)
            except Exception as e:
                print(f"UART send error: {e}")
    
    def _handle_uart_receive(self):
        """處理 UART 接收的數據"""
        if self.uart and self.uart.any():
            try:
                data = self.uart.read()
                print(data)
                
                # 查找有效數據幀
                start_idx = -1
                for i in range(len(data)):
                    if (data[i] == 0xB4 and 
                        i + 4 < len(data) and 
                        data[i+4] == 0xFF):
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
        """
        主更新函數 (高性能優化版)
        
        優化:
        - 只在狀態改變時才調用 _update_xxx_display
        - 使用非阻塞 jump_to_frame
        - 最小化重複操作
        
        Args:
            debug: 是否顯示調試信息
        
        Returns:
            運行時間 (ms)
        """
        start_time = time.ticks_ms()
        
        # 更新輸入設備
        if self.button_handler is not None:
            self.button_handler.update()
            self.button_handler.check_single_click()
        
        if self.touch_controller:
            self.touch_controller.update()
        
        # 處理編碼器和 UART
        self._handle_encoder()
        self._handle_uart_receive()
        
        # 更新計時器
        self.timer.update()
        self._update_time_display()
        
        # 更新循環動畫 (每幀都更新)
        self._update_loop_animation(self.time_buf)
        
        # === 只在狀態改變時更新顯示 ===
        # 注意: _set_state 中已經調用了 jump_to_frame
        # 這裡只需要檢查是否需要重繪
        
        if self.last_mode_count != self.mode_count:
            self.last_mode_count = self.mode_count
            self._update_mode_display()
        
        if self.last_brightness_value != self.brightness_value:
            self.last_brightness_value = self.brightness_value
            self._update_brightness_display()
        
        # 調試輸出
        if debug:
            run_time = time.ticks_diff(time.ticks_ms(), start_time)
            
            # 顯示詳細狀態
            mod_res = self.buffer_mgr.resources.get('mod')
            if mod_res:
                print(f'run_time: {run_time}ms | '
                      f'mode: {self.mode_count} | '
                      f'brightness: {self.brightness_value} | '
                      f'current_frame: {mod_res.current_frame} | '
                      f'decoding: {mod_res.decode_thread_running}')
            else:
                print(f'run_time: {run_time}ms')
            
            return run_time
        else:
            return 0