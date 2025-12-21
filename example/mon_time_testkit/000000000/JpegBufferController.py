# ========================================
# JpegBufferController.py - 高性能三重緩衝版本
# ========================================

import json
import framebuf
import jpeg
import os
import _thread
import time

class ResourceBuffer:
    """三重緩衝資源管理器 - 無鎖設計"""
    def __init__(self, name, root_path, config, decoder, strict_mode=False):
        """
        三重緩衝設計:
        - buffer_0: 顯示緩衝 (正在被LCD使用)
        - buffer_1: 準備緩衝 (解碼完成,等待交換)
        - buffer_2: 解碼緩衝 (後台正在解碼)
        
        通過原子標誌位控制,無需鎖
        """
        self.name = name
        self.root_path = root_path
        self.config = config
        self.decoder = decoder
        self.strict_mode = strict_mode
        
        # 配置參數
        self.width = config['width']
        self.height = config['height']
        self.x = config['x']
        self.y = config['y']
        self.depth = config['depth']
        
        # 預計算
        self.buffer_size = self.width * self.height * 2
        self.jpeg_max_size = self.width * self.height * 4
        
        # === 三重緩衝 ===
        self.buffer_0 = bytearray(self.buffer_size)  # 顯示
        self.buffer_1 = bytearray(self.buffer_size)  # 準備
        self.buffer_2 = bytearray(self.buffer_size)  # 解碼
        
        # 預創建 memoryview (避免重複創建)
        self.mv_0 = memoryview(self.buffer_0)
        self.mv_1 = memoryview(self.buffer_1)
        self.mv_2 = memoryview(self.buffer_2)
        
        # FrameBuffer 只在需要時創建一次
        self.fb_0 = framebuf.FrameBuffer(self.buffer_0, self.width, self.height, framebuf.RGB565)
        self.fb_1 = framebuf.FrameBuffer(self.buffer_1, self.width, self.height, framebuf.RGB565)
        self.fb_2 = framebuf.FrameBuffer(self.buffer_2, self.width, self.height, framebuf.RGB565)
        
        # JPEG 緩衝
        self.jpeg_buffer = bytearray(self.jpeg_max_size)
        self.jpeg_mv = memoryview(self.jpeg_buffer)
        
        # === 無鎖狀態控制 (使用原子標誌) ===
        # 0: buffer_0, 1: buffer_1, 2: buffer_2
        self.display_idx = 0      # 當前顯示的緩衝索引
        self.ready_idx = -1       # 解碼完成的緩衝索引 (-1表示無)
        self.decoding_idx = -1    # 正在解碼的緩衝索引 (-1表示無)
        
        self.current_frame = 0    # 當前顯示幀
        self.decoding_frame = -1  # 正在解碼的幀
        
        self.decode_thread_running = False
        
        # === 初始化 ===
        # 同步加載第一幀到 buffer_0
        self._load_frame_to_buffer(0, self.buffer_0, self.mv_0)
        self.current_frame = 0
        self.display_idx = 0
        
        # 預載第二幀到 buffer_1
        if self.depth > 1:
            self._start_background_decode(1, buffer_idx=1)
    
    def _get_file_path(self, frame_index):
        """構建文件路徑"""
        return f"{self.root_path}{self.name}/{frame_index:03d}.jpeg"
    
    def _load_frame_to_buffer(self, frame_index, target_buffer, target_mv):
        """同步加載JPEG到指定緩衝"""
        try:
            file_path = self._get_file_path(frame_index)
            
            # 讀取JPEG
            with open(file_path, "rb") as f:
                f.readinto(self.jpeg_mv)
            
            # 解碼
            decoded_data = self.decoder.decode(self.jpeg_buffer)
            
            # 快速複製 (使用 memoryview 切片)
            decoded_mv = memoryview(decoded_data)
            target_mv[:self.buffer_size] = decoded_mv[:self.buffer_size]
            
            return True
        except Exception as e:
            if self.strict_mode:
                print(f"[ERROR] Load frame {frame_index}: {e}")
            return False
    
    def _decode_worker(self, frame_index, buffer_idx):
        """後台解碼工作線程"""
        try:
            # 根據 buffer_idx 選擇目標緩衝
            if buffer_idx == 0:
                target_buffer, target_mv = self.buffer_0, self.mv_0
            elif buffer_idx == 1:
                target_buffer, target_mv = self.buffer_1, self.mv_1
            else:
                target_buffer, target_mv = self.buffer_2, self.mv_2
            
            # 執行解碼
            success = self._load_frame_to_buffer(frame_index, target_buffer, target_mv)
            
            if success:
                # 原子更新狀態 (無需鎖)
                self.ready_idx = buffer_idx
                self.decoding_frame = frame_index
            
        except Exception as e:
            print(f"[WORKER] Decode error: {e}")
        finally:
            self.decode_thread_running = False
            self.decoding_idx = -1
    
    def _start_background_decode(self, frame_index, buffer_idx):
        """啟動後台解碼到指定緩衝"""
        if frame_index >= self.depth:
            return False
        
        # 如果已經在解碼,跳過
        if self.decode_thread_running:
            return False
        
        # 標記狀態
        self.decode_thread_running = True
        self.decoding_idx = buffer_idx
        
        try:
            _thread.start_new_thread(self._decode_worker, (frame_index, buffer_idx))
            return True
        except Exception as e:
            print(f"[ERROR] Start thread failed: {e}")
            self.decode_thread_running = False
            self.decoding_idx = -1
            return False
    
    def get_current_buffer(self):
        """獲取當前顯示緩衝 (零拷貝,直接返回 FrameBuffer)"""
        if self.display_idx == 0:
            return self.fb_0
        elif self.display_idx == 1:
            return self.fb_1
        else:
            return self.fb_2
    
    def get_next_frame(self):
        """
        獲取下一幀 (非阻塞,無鎖設計)
        
        流程:
        1. 檢查是否有準備好的緩衝 (ready_idx)
        2. 如果有,切換顯示緩衝,啟動下一幀解碼
        3. 返回當前顯示緩衝
        """
        if self.depth <= 1:
            return self.get_current_buffer()
        
        # 檢查是否有準備好的幀
        if self.ready_idx != -1:
            # 找出空閒緩衝 (用於下一次解碼)
            idle_idx = ({0, 1, 2} - {self.display_idx, self.ready_idx}).pop()
            
            # 切換顯示緩衝 (原子操作)
            old_display = self.display_idx
            self.display_idx = self.ready_idx
            self.current_frame = self.decoding_frame
            self.ready_idx = -1
            
            # 立即啟動下一幀解碼到空閒緩衝
            next_frame = (self.current_frame + 1) % self.depth
            self._start_background_decode(next_frame, buffer_idx=idle_idx)
        
        # 返回當前顯示緩衝 (零拷貝)
        return self.get_current_buffer()
    
    def jump_to_frame(self, frame_index):
        """
        跳轉到指定幀
        
        策略:
        1. 等待當前解碼完成
        2. 同步加載到顯示緩衝
        3. 啟動預加載
        """
        if not (0 <= frame_index < self.depth):
            return self.get_current_buffer()
        
        # 等待解碼完成 (最多100ms)
        timeout = 0
        while self.decode_thread_running and timeout < 100:
            time.sleep_ms(1)
            timeout += 1
        
        # 同步加載到當前顯示緩衝
        if self.display_idx == 0:
            target_buffer, target_mv = self.buffer_0, self.mv_0
        elif self.display_idx == 1:
            target_buffer, target_mv = self.buffer_1, self.mv_1
        else:
            target_buffer, target_mv = self.buffer_2, self.mv_2
        
        if self._load_frame_to_buffer(frame_index, target_buffer, target_mv):
            self.current_frame = frame_index
            self.ready_idx = -1
            
            # 預載下一幀
            if self.depth > 1:
                next_frame = (frame_index + 1) % self.depth
                # 選擇非顯示緩衝
                preload_idx = 1 if self.display_idx != 1 else 2
                self._start_background_decode(next_frame, buffer_idx=preload_idx)
        
        return self.get_current_buffer()
    
    def get_digit_buffer(self, digit):
        """獲取數字圖像 (專用於 text 資源)"""
        if self.name != 'text' or not (0 <= digit < self.depth):
            return None
        
        # 等待解碼完成
        timeout = 0
        while self.decode_thread_running and timeout < 100:
            time.sleep_ms(1)
            timeout += 1
        
        # 加載到顯示緩衝
        if self.display_idx == 0:
            target_buffer, target_mv = self.buffer_0, self.mv_0
        elif self.display_idx == 1:
            target_buffer, target_mv = self.buffer_1, self.mv_1
        else:
            target_buffer, target_mv = self.buffer_2, self.mv_2
        
        if self._load_frame_to_buffer(digit, target_buffer, target_mv):
            return self.get_current_buffer()
        return None
    
    def reset(self):
        """重置到第一幀"""
        timeout = 0
        while self.decode_thread_running and timeout < 100:
            time.sleep_ms(1)
            timeout += 1
        
        self.current_frame = 0
        self.ready_idx = -1
        
        # 加載到當前顯示緩衝
        if self.display_idx == 0:
            self._load_frame_to_buffer(0, self.buffer_0, self.mv_0)
        elif self.display_idx == 1:
            self._load_frame_to_buffer(0, self.buffer_1, self.mv_1)
        else:
            self._load_frame_to_buffer(0, self.buffer_2, self.mv_2)
        
        # 預載下一幀
        if self.depth > 1:
            preload_idx = 1 if self.display_idx != 1 else 2
            self._start_background_decode(1, buffer_idx=preload_idx)
    
    def cleanup(self):
        """清理資源"""
        timeout = 0
        while self.decode_thread_running and timeout < 200:
            time.sleep_ms(5)
            timeout += 1


class JpegBufferController:
    """JPEG 圖像緩衝管理器 - 高性能版本"""
    def __init__(self, root_path, config_file='dp_config.json', strict_mode=False):
        self.root_path = root_path.rstrip('/') + '/'
        self.config_file = config_file
        self.strict_mode = strict_mode
        self.config = {}
        self.resources = {}
        
        # 共享解碼器
        self.decoder = jpeg.Decoder(rotation=0, pixel_format="RGB565_BE")
        
        self._load_config(config_file)
        self._init_resources()
    
    def _load_config(self, config_file):
        """載入配置文件"""
        config_path = self.root_path + config_file
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        print(f"✓ Config loaded")
    
    def _init_resources(self):
        """初始化所有資源"""
        for i in self.config['display_Layout']:
            name = i["type"]
            self.resources[name] = ResourceBuffer(
                name=name,
                root_path=self.root_path,
                config=i,
                decoder=self.decoder,
                strict_mode=self.strict_mode
            )
            print(f"✓ {name}: {i['depth']} frames")
            
            if name == 'text':
                self._init_text(i)
        
        self.counter_time = self.config['counter_time']
    
    def _init_text(self, text_cfg):
        """初始化時間顯示 - 優化版本"""
        self.seconds = -1
        
        # === 預載數字緩存 (0-9 + 冒號) ===
        self._digit_cache = {}
        text_resource = self.resources['text']
        
        for digit in range(11):
            digit_fb = text_resource.get_digit_buffer(digit)
            if digit_fb:
                # 創建獨立緩存 (使用 blit 複製)
                buffer_size = text_cfg['width'] * text_cfg['height'] * 2
                cached_data = bytearray(buffer_size)
                cached_fb = framebuf.FrameBuffer(
                    cached_data,
                    text_cfg['width'],
                    text_cfg['height'],
                    framebuf.RGB565
                )
                cached_fb.blit(digit_fb, 0, 0)  # 使用 blit 複製
                
                self._digit_cache[digit] = cached_fb
        
        # === 5個位置的緩存 (避免重複創建) ===
        self._position_cache = []
        for i in range(5):
            buffer_data = bytearray(text_cfg['width'] * text_cfg['height'] * 2)
            fb = framebuf.FrameBuffer(
                buffer_data,
                text_cfg['width'],
                text_cfg['height'],
                framebuf.RGB565
            )
            self._position_cache.append({
                'fb': fb,
                'data': buffer_data,
                'digit': -1  # 當前顯示的數字
            })
        
        # === 最終時間顯示緩衝 ===
        total_width = text_cfg['width'] * 5
        total_size = total_width * text_cfg['height'] * 2
        self.time_buffer_data = bytearray(total_size)
        self.time_buffer = framebuf.FrameBuffer(
            self.time_buffer_data,
            total_width,
            text_cfg['height'],
            framebuf.RGB565
        )
        
        print(f"✓ Time display: {total_width}x{text_cfg['height']}")
    
    def get_background(self):
        """獲取背景 (零拷貝)"""
        if 'background' in self.resources:
            return self.resources['background'].get_current_buffer()
        return None
    
    def get_next_frame(self, resource_name):
        """獲取下一幀 (零拷貝)"""
        if resource_name in self.resources:
            return self.resources[resource_name].get_next_frame()
        return None
    
    def jump_to_frame(self, resource_name, frame_index):
        """跳轉到指定幀 (零拷貝)"""
        if resource_name in self.resources:
            return self.resources[resource_name].jump_to_frame(frame_index)
        return None
    
    def update_time_display(self, seconds):
        """
        更新時間顯示 - 最小化操作版本
        
        優化策略:
        1. 只更新變化的位置
        2. 使用 blit 而不是 memoryview 複製
        3. 緩存位置信息
        """
        if not self.time_buffer or 'text' not in self.resources:
            return None
        
        if self.seconds == seconds:
            return self.time_buffer
        
        self.seconds = seconds
        mins, secs = divmod(seconds, 60)
        
        # 計算5個位置的數字
        digits = [
            mins // 10,
            mins % 10,
            10,  # 冒號
            secs // 10,
            secs % 10
        ]
        
        text_cfg = self.resources['text'].config
        digit_width = text_cfg['width']
        
        # 只更新變化的位置
        for i, digit in enumerate(digits):
            cache = self._position_cache[i]
            
            if cache['digit'] != digit:
                # 從預載緩存複製 (使用 blit)
                if digit in self._digit_cache:
                    cache['fb'].blit(self._digit_cache[digit], 0, 0)
                    cache['digit'] = digit
            
            # 繪製到最終緩衝 (使用 blit)
            self.time_buffer.blit(cache['fb'], i * digit_width, 0)
        
        return self.time_buffer
    
    def get_resource_info(self, resource_name):
        """獲取資源配置"""
        if resource_name in self.resources:
            return self.resources[resource_name].config.copy()
        return None
    
    def get_all_resources(self):
        """獲取所有資源名稱"""
        return list(self.resources.keys())
    
    def reset_resource(self, resource_name):
        """重置資源"""
        if resource_name in self.resources:
            self.resources[resource_name].reset()
    
    def cleanup(self):
        """清理所有資源"""
        for resource in self.resources.values():
            resource.cleanup()
        self.resources = {}