import time, json

class TouchButton:
    """觸控按鈕類"""
    def __init__(self, x, y, width, height, callback=None, name=""):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.callback = callback
        self.name = name
        self.is_pressed = False
        
        # 按鈕狀態回調
        self.on_press = None
        self.on_release = None
        self.on_long_press = None
    
    def is_point_inside(self, x, y):
        """檢查點是否在按鈕內"""
        return (self.x <= x <= self.x + self.width and 
                self.y <= y <= self.y + self.height)
    
    def handle_touch(self, x, y):
        point_inside = self.is_point_inside(x, y)
        if point_inside and self.callback:
            self.callback(self)
        
        return point_inside, self.name
    
    

class TouchController:
    
    def __init__(self, touch_driver, touch_width=240, touch_height=320, 
                 rotation=0, callback=None):
        
        self.touch_driver = touch_driver
        
        # 觸控驅動的原始尺寸
        self.touch_width = touch_width
        self.touch_height = touch_height
        
        self.rotation = rotation % 4  # 確保rotation在0-3之間
        self.callback = callback
        self.buttons = []
        
        self.last_state = False
        
        self.touch_X = 0
        self.touch_Y = 0
        
        self.last_X = 0
        self.last_Y = 0
        
        self.offset_X = 0
        self.offset_Y = 0
        
        self.temp_finger_number = 0
    
    def transform_touch_point(self, raw_x, raw_y):
        """
        將觸控驅動的原始座標轉換為顯示座標
        rotation = 0: 0°   (原始)
        rotation = 1: 90°  (順時針)
        rotation = 2: 180° 
        rotation = 3: 270° (逆時針90°)
        """
        if self.rotation == 0:
            # 0° - 無旋轉
            return raw_x, raw_y
            
        elif self.rotation == 1:
            # 90° 順時針
            # 觸控 (0,0) 在左上 -> 顯示 (0,0) 在右上
            # 觸控點 (x,y) -> 顯示點 (touch_height-y, x)
            return self.touch_height - raw_y, raw_x
            
        elif self.rotation == 2:
            # 180°
            # 觸控 (0,0) 在左上 -> 顯示 (0,0) 在右下
            return self.touch_width - raw_x, self.touch_height - raw_y
            
        elif self.rotation == 3:
            # 270° 順時針 (90° 逆時針)
            # 觸控 (0,0) 在左上 -> 顯示 (0,0) 在左下
            return raw_y, self.touch_width - raw_x
        
        return raw_x, raw_y
    
    def add_button(self, x, y, width, height, callback=None, name=""):
        """
        添加按鈕 - 直接使用顯示屏的邏輯座標
        x, y, width, height 都是基於當前旋轉方向的顯示座標
        """
        button = TouchButton(x, y, width, height, callback, name)
        self.buttons.append(button)
        return button
    
    def update(self):
        if self.touch_driver.is_touched():
            finger_number, points = self.touch_driver.read_touch()
            
            if finger_number-1 == self.temp_finger_number :
                self.temp_finger_number = finger_number

            if self.temp_finger_number == 4:
                self.temp_finger_number = 0
                if self.callback:
                    self.callback('wifi', 47)
                    
            raw_x, raw_y = points['x'], points['y']
            display_x, display_y = self.transform_touch_point(raw_x, raw_y)
            # 更新當前觸控點(顯示座標)
            self.touch_X = display_x
            self.touch_Y = display_y
                
            if not self.last_state:
                
                
                self.last_X, self.last_Y = display_x , display_y       
                
                self.last_state = True
            else:
                
                if display_x != self.last_X and finger_number == 2 :
                    self.offset_X =  display_x -self.last_X 
                    if self.callback:
                        self.callback('brightness', self.offset_X // 15)
                    self.last_X = display_x
                    
                if display_y != self.last_Y:
                    self.offset_Y = self.last_Y - display_y
                    self.last_Y = display_y
             
        else:
            if self.last_state:
                finger_number, points = self.touch_driver.read_touch()
                
                raw_x, raw_y = points['x'], points['y']
                display_x, display_y = self.transform_touch_point(raw_x, raw_y)
                
                if self.temp_finger_number == 3:
                    
                    self.offset_X =  display_x -self.last_X
                    
                    if self.callback and self.offset_X != 0 :
                        
                        output_value =  1 if self.offset_X >0 else -1
                        self.callback('change_pattern', output_value)
                    
                
#                 raw_x, raw_y = points['x'], points['y']
#                 display_x, display_y = self.transform_touch_point(raw_x, raw_y)
#                 self.last_X, self.last_Y = display_x , display_y
                
                
                for button in self.buttons:
                    is_hit, name = button.handle_touch(self.touch_X, self.touch_Y)
#                     if is_hit and finger_number == 1 :
                    if is_hit and self.temp_finger_number == 1 :
                        self.callback( 'touche', int(name))
#                         print(f"Button pressed: {name}")
                self.temp_finger_number = 0
                self.last_state = False
            
        return self.last_state


class ButtonController:
    """處理按鈕的點擊、雙擊、長按事件"""
    
    def __init__(self, pin, callback=None):
        self.pin = pin
        self.callback = callback
        
        # 按鈕狀態
        self.last_state = 1
        self.press_start_time = 0
        self.last_release_time = 0
        self.is_pressed = False
        self.long_press_triggered = False
        
        # 時間閾值（毫秒）
        self.DEBOUNCE_TIME = 20
        self.DOUBLE_CLICK_TIME = 300
        self.LONG_PRESS_TIME = 1000
        
    def update(self):
        """更新按鈕狀態，檢測各種點擊事件"""
        current_time = time.ticks_ms()
        current_state = self.pin.value()
        
        # 防抖動處理
        if current_state != self.last_state:
            if current_state == 0 and self.last_state == 1:  # 按下
                self.press_start_time = current_time
                self.is_pressed = True
                self.long_press_triggered = False
                
            elif current_state == 1 and self.last_state == 0:  # 釋放
                if self.is_pressed and not self.long_press_triggered:
                    press_duration = time.ticks_diff(current_time, self.press_start_time)
                    
                    if press_duration < self.LONG_PRESS_TIME:
                        # 檢查是否為雙擊
                        if time.ticks_diff(current_time, self.last_release_time) < self.DOUBLE_CLICK_TIME:
                            self._trigger_event('double_click')
                        else:
                            # 延遲檢查單擊（等待可能的雙擊）
                            self.last_release_time = current_time
                            self._schedule_single_click_check()
                
                self.is_pressed = False
                
            self.last_state = current_state
        
        # 檢查長按
        if self.is_pressed and not self.long_press_triggered:
            if time.ticks_diff(current_time, self.press_start_time) >= self.LONG_PRESS_TIME:
                self.long_press_triggered = True
                self._trigger_event('long_press')
    
    def _schedule_single_click_check(self):
        """延遲檢查單擊事件"""
        # 這裡可以使用定時器或在主循環中檢查
        pass
    
    def check_single_click(self):
        """檢查是否應該觸發單擊事件"""
        current_time = time.ticks_ms()
        if (self.last_release_time > 0 and 
            time.ticks_diff(current_time, self.last_release_time) >= self.DOUBLE_CLICK_TIME):
            self.last_release_time = 0
            self._trigger_event('click')
    
    def _trigger_event(self, event_type):
        """觸發事件回調"""
        self.last_release_time = 0
        if self.callback:
            self.callback(event_type)