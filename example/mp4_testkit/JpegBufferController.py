import json
import framebuf
import jpeg
import os
import _thread
import time

class ResourceBuffer:
    """雙重緩衝資源管理器 - 性能優化版"""
    
    def __init__(self, name, root_path, config, decoder, strict_mode=False):
        """
        初始化資源緩衝
        Args:
            name: 資源名稱
            root_path: 根路徑
            config: 資源配置
            decoder: JPEG解碼器
            strict_mode: 嚴格模式,啟用文件檢查(調試用)
        """
        self.name = name
        self.root_path = root_path
        self.config = config
        self.decoder = decoder
        self.strict_mode = strict_mode
        
        # 提取配置
        self.width = config['width']
        self.height = config['height']
        self.x = config['x']
        self.y = config['y']
        self.depth = config['depth']
        
        # 預計算固定值
        self.buffer_size = self.width * self.height * 2  # RGB565
        self.jpeg_max_size = self.width * self.height * 4
        
        # 當前幀索引
        self.current_frame = 0
        self.next_frame_index = 0
        
        # === 雙重緩衝設計 ===
        self.front_buffer = bytearray(self.buffer_size)
        self.back_buffer = bytearray(self.buffer_size)
        
        # 預創建memoryview(避免重複創建)
        self.front_mv = memoryview(self.front_buffer)
        self.back_mv = memoryview(self.back_buffer)
        
        self.front_fb = framebuf.FrameBuffer(
            self.front_buffer,
            self.width,
            self.height,
            framebuf.RGB565
        )
        
        self.back_fb = framebuf.FrameBuffer(
            self.back_buffer,
            self.width,
            self.height,
            framebuf.RGB565
        )
        
        # JPEG讀取緩衝
        self.jpeg_buffer = bytearray(self.jpeg_max_size)
        self.jpeg_mv = memoryview(self.jpeg_buffer)
        
        # === 多核同步機制 ===
        self.decode_lock = _thread.allocate_lock()
        self.swap_lock = _thread.allocate_lock()
        self.decode_ready = False
        self.decode_thread_running = False
        
        # 初始化第一幀到前台
        self._load_frame_sync(0, self.front_buffer, self.front_mv)
        
        # 預載第二幀到後台(如果有多幀)
        if self.depth > 1:
            self._start_background_decode(1)
    
    def _get_file_path(self, frame_index):
        """構建文件路徑"""
        return f"{self.root_path}{self.name}/{frame_index:03d}.jpg"
    
    def _calculate_next_index(self, current_idx):
        """計算下一幀索引"""
        return (current_idx + 1) % self.depth
    
    def _load_frame_sync(self, frame_index, target_buffer, target_mv):
        """同步載入指定幀到目標緩衝區"""
        try:
            file_path = self._get_file_path(frame_index)
            
            # 讀取JPEG數據
            with open(file_path, "rb") as f:
                f.readinto(self.jpeg_mv)
            
            # 解碼
            decoded_data = self.decoder.decode(self.jpeg_buffer)
            
            # 使用預創建的memoryview快速拷貝
            decoded_mv = memoryview(decoded_data)
            target_mv[:self.buffer_size] = decoded_mv[:self.buffer_size]
            
            return True
            
        except OSError as e:
            print(f"[ERROR] Failed to load {file_path}: {e}")
            if self.strict_mode:
                raise
            return False
            
        except Exception as e:
            print(f"[ERROR] Decode error for frame {frame_index}: {e}")
            return False
    
    def _decode_worker(self, frame_index):
        """後台解碼工作線程"""
        try:
            success = self._load_frame_sync(
                frame_index, 
                self.back_buffer, 
                self.back_mv
            )
            
            with self.decode_lock:
                if success:
                    self.decode_ready = True
                    self.next_frame_index = frame_index
                else:
                    self.decode_ready = False
                
        except Exception as e:
            print(f"[WORKER] Decode error: {e}")
            with self.decode_lock:
                self.decode_ready = False
        
        finally:
            self.decode_thread_running = False
    
    def _start_background_decode(self, frame_index):
        """啟動後台解碼"""
        if frame_index >= self.depth:
            return False
        
        # 等待上一次解碼完成
        timeout = 0
        while self.decode_thread_running and timeout < 100:
            time.sleep_ms(1)
            timeout += 1
        
        if self.decode_thread_running:
            print(f"[WARN] Previous decode still running for {self.name}")
            return False
        
        # 重置狀態
        with self.decode_lock:
            self.decode_ready = False
            self.decode_thread_running = True
        
        # 啟動新線程
        try:
            _thread.start_new_thread(self._decode_worker, (frame_index,))
            return True
        except Exception as e:
            print(f"[ERROR] Failed to start decode thread: {e}")
            self.decode_thread_running = False
            return False
    
    def _swap_buffers(self):
        """交換前後台緩衝"""
        with self.swap_lock:
            # 交換buffer引用
            self.front_buffer, self.back_buffer = self.back_buffer, self.front_buffer
            
            # 交換memoryview
            self.front_mv, self.back_mv =  self.back_mv, self.front_mv
            
            # 交換framebuffer
            self.front_fb = framebuf.FrameBuffer(
                self.front_buffer,
                self.width,
                self.height,
                framebuf.RGB565
            )
            self.back_fb = framebuf.FrameBuffer(
                self.back_buffer,
                self.width,
                self.height,
                framebuf.RGB565
            )
    
    def get_current_buffer(self):
        """獲取當前幀緩衝"""
        return self.front_fb
    
    def get_next_frame(self):
        """獲取下一幀(非阻塞)"""
        if self.depth <= 1:
            return self.front_fb
        
        # 檢查後台解碼是否完成
        is_ready = False
        with self.decode_lock:
            is_ready = self.decode_ready
        
        if is_ready:
            # 執行交換
            self._swap_buffers()
            
            with self.decode_lock:
                self.current_frame = self.next_frame_index
                self.decode_ready = False
            
            # 立即啟動下一幀解碼
            next_idx = self._calculate_next_index(self.current_frame)
            self._start_background_decode(next_idx)
        
        return self.front_fb
    
    def jump_to_frame(self, frame_index):
        """跳轉到指定幀"""
        if not (0 <= frame_index < self.depth):
            print(f"[WARN] Invalid frame {frame_index}, range: 0-{self.depth-1}")
            return self.front_fb
        
        # 等待當前解碼完成
        timeout = 0
        while self.decode_thread_running and timeout < 100:
            time.sleep_ms(1)
            timeout += 1
        
        # 同步載入到前台
        if self._load_frame_sync(frame_index, self.front_buffer, self.front_mv):
            self.current_frame = frame_index
            
            # 重建framebuffer
            self.front_fb = framebuf.FrameBuffer(
                self.front_buffer,
                self.width,
                self.height,
                framebuf.RGB565
            )
            
            # 預載下一幀
            if self.depth > 1:
                next_idx = self._calculate_next_index(frame_index)
                self._start_background_decode(next_idx)
        
        return self.front_fb
    
    def get_digit_buffer(self, digit):
        """獲取數字圖像(專門為text資源)"""
        if self.name != 'text':
            return None
        
        if not (0 <= digit <= self.depth):
            print(f"[WARN] Invalid digit {digit}")
            return None
        
        # 等待解碼線程完成
        timeout = 0
        while self.decode_thread_running and timeout < 100:
            time.sleep_ms(1)
            timeout += 1
        
        # 載入數字到前台
        if self._load_frame_sync(digit, self.front_buffer, self.front_mv):
            self.front_fb = framebuf.FrameBuffer(
                self.front_buffer,
                self.width,
                self.height,
                framebuf.RGB565
            )
            return self.front_fb
        
        return None
    
    def reset(self):
        """重置到第一幀"""
        timeout = 0
        while self.decode_thread_running and timeout < 100:
            time.sleep_ms(1)
            timeout += 1
        
        self.current_frame = 0
        self._load_frame_sync(0, self.front_buffer, self.front_mv)
        
        # 重建framebuffer
        self.front_fb = framebuf.FrameBuffer(
            self.front_buffer,
            self.width,
            self.height,
            framebuf.RGB565
        )
        
        # 預載下一幀
        if self.depth > 1:
            self._start_background_decode(1)
    
    def cleanup(self):
        """清理資源"""
        timeout = 0
        while self.decode_thread_running and timeout < 200:
            time.sleep_ms(5)
            timeout += 1


class JpegBufferController:
    """JPEG圖像緩衝管理器 - 處理所有圖像資源的讀取和緩衝"""
    
    def __init__(self, root_path, config_file='dp_config.json', strict_mode=False):
        """
        初始化緩衝管理器
        Args:
            root_path: 資源根目錄路徑
            config_file: 配置文件名
            strict_mode: 嚴格模式(調試用)
        """
        self.root_path = root_path.rstrip('/') + '/'
        self.config_file = config_file
        self.strict_mode = strict_mode
        self.config = {}
        self.resources = {}
        
        # 創建共享的JPEG解碼器
        self.decoder = jpeg.Decoder(rotation=0, pixel_format="RGB565_BE")
        
        # 讀取配置文件
        self._load_config(config_file)
        
        # 初始化所有資源
        self._init_resources()
    
    def _load_config(self, config_file):
        """載入配置文件"""
        config_path = self.root_path + config_file
        try:
            with open(config_path, 'r') as f:
                self.config = json.load(f)
            print(f"✓ Config loaded from {config_path}")
        except Exception as e:
            print(f"✗ Failed to load config: {e}")
            raise
    
    def _init_resources(self):
        """初始化所有資源"""
        
#         for name, cfg in self.config.items():
            
        for i in self.config['display_Layout']:
            name = i["type"]
            self.resources[name] = ResourceBuffer(
                    name=name,
                    root_path=self.root_path,
                    config=i,
                    decoder=self.decoder,
                    strict_mode=self.strict_mode
                )
            print(f"✓ Initialized resource: {name} ({i['depth']} frames)")
            
            if name == 'text':
                self._init_text(i)
            
        self.counter_time = self.config['counter_time']
        
    
    def _init_text(self, text_cfg):
        """初始化時間顯示緩衝 - 預載所有數字圖像"""
        self.seconds = -1
        
        # === 預載數字圖像緩存 (0-9 + 冒號) ===
        self._digit_cache = {}
        text_resource = self.resources['text']
        
        # 預載 0-9 和冒號(索引10)
        for digit in range(11):  # 0-9 + 冒號
            # 從 ResourceBuffer 獲取數字圖像
            digit_fb = text_resource.get_digit_buffer(digit)
            
            if digit_fb:
                # 創建獨立的緩存副本
                buffer_size = text_cfg['width'] * text_cfg['height'] * 2
                cached_data = bytearray(buffer_size)
                cached_fb = framebuf.FrameBuffer(
                    cached_data,
                    text_cfg['width'],
                    text_cfg['height'],
                    framebuf.RGB565
                )

                # 從 ResourceBuffer 複製圖像數據

                cached_fb.blit(digit_fb, 0, 0)
                
                self._digit_cache[digit] = {
                    'buff': cached_fb,
                    'data': cached_data
                }
                
                digit_text = digit if digit < 10 else ':'
                print(f"  ✓ Cached digit: {digit_text}")
            else:
                print(f"  ✗ Failed to cache digit: {digit}")
        
        # === 創建5個位置的顯示緩衝區 ===
        self._time_buffer = {}
        for i in range(5):
            buffer_size = text_cfg['width'] * text_cfg['height'] * 2
            buffer_data = bytearray(buffer_size)
            _buffer = framebuf.FrameBuffer(
                buffer_data,
                text_cfg['width'],
                text_cfg['height'],
                framebuf.RGB565
            )
            self._time_buffer[str(i)] = {
                'buff': _buffer,
                'data': buffer_data,
                'status': 255  # 初始狀態設為無效值
            }
        
        # === 創建完整時間顯示緩衝 ===
        total_size = text_cfg['width'] * 5 * text_cfg['height'] * 2
        self.time_buffer_data = bytearray(total_size)
        self.time_buffer = framebuf.FrameBuffer(
            self.time_buffer_data,
            text_cfg['width'] * 5,
            text_cfg['height'],
            framebuf.RGB565
        )
        
        print(f"✓ Time display initialized: {text_cfg['width']*5}x{text_cfg['height']}")
        print(f"✓ Digit cache: {len(self._digit_cache)} images loaded")
                

    
    def reinitialize(self, new_root_path, config_file=None):
        """
        重新初始化資源管理器
        Args:
            new_root_path: 新的資源根目錄路徑
            config_file: 可選的新配置文件名
        """
        # 正規化新路徑
        new_root_path = new_root_path.rstrip('/') + '/'
        
        # 保存舊值以便恢復
        old_root_path = self.root_path
        old_config_file = self.config_file
        
        # 更新實例變量
        self.root_path = new_root_path
        if config_file is not None:
            self.config_file = config_file
        
        try:
            # 嘗試加載新配置
            self._load_config(self.config_file)
        except Exception as e:
            # 加載失敗,恢復舊值
            self.root_path = old_root_path
            self.config_file = old_config_file
            print(f"✗ Reinitialization failed: {e}")
            raise
        
        # 清理舊資源
        for resource in self.resources.values():
            resource.cleanup()
        
        self.resources = {}
        
        # 清理文本緩衝區
        if hasattr(self, 'time_buffer'):
            del self.time_buffer
        if hasattr(self, '_time_buffer'):
            del self._time_buffer
        if hasattr(self, 'seconds'):
            del self.seconds
        
        # 重新初始化資源
        self._init_resources()
        print("✓ Reinitialization completed successfully")
    
    def get_background(self):
        """獲取背景圖像緩衝"""
        if 'background' in self.resources:
            return self.resources['background'].get_current_buffer()
        return None
    
    def get_next_frame(self, resource_name):
        """
        獲取指定資源的下一幀
        Args:
            resource_name: 資源名稱
        Returns:
            framebuf對象或None
        """
        if resource_name in self.resources:
            return self.resources[resource_name].get_next_frame()
        return None
    
    def jump_to_frame(self, resource_name, frame_index):
        """
        跳轉到指定資源的特定幀
        Args:
            resource_name: 資源名稱
            frame_index: 幀索引
        Returns:
            framebuf對象或None
        """
        if resource_name in self.resources:
            return self.resources[resource_name].jump_to_frame(frame_index)
        return None


    def update_time_display(self, seconds):
        """
        更新時間顯示緩衝區 - 使用預載緩存
        Args:
            seconds: 秒數
        Returns:
            包含完整時間顯示的framebuf
        """
        if not self.time_buffer or 'text' not in self.resources:
            return None
        
        if self.seconds == seconds:
            return self.time_buffer  # 時間未變化,直接返回
        
        self.seconds = seconds
        mins, secs = divmod(seconds, 60)
        
        text_cfg = self.resources['text'].config
        digit_width = text_cfg['width']
        
        # 預計算字符映射
        digits = [
            mins // 10,        # 十位分鐘
            mins % 10,         # 個位分鐘
            10,                # 冒號
            secs // 10,        # 十位秒
            secs % 10          # 個位秒
        ]
        
        # 繪製每個字符
        for i, digit_value in enumerate(digits):
            cache = self._time_buffer[str(i)]
            
            # 只在數字改變時更新緩衝
            if cache['status'] != digit_value:
                # 從預載緩存中獲取數字圖像
                if digit_value in self._digit_cache:
                    cached_digit = self._digit_cache[digit_value]
                    
                    # 複製到位置緩衝
                    cache['buff'].blit(cached_digit['buff'], 0, 0)
                    cache['status'] = digit_value
                else:
                    print(f"[WARN] Digit {digit_value} not in cache!")
            
            # 繪製到時間緩衝區
            self.time_buffer.blit(cache['buff'], i * digit_width, 0)
        
        return self.time_buffer
     
    
    def get_resource_info(self, resource_name):
        """
        獲取資源的配置信息
        Args:
            resource_name: 資源名稱
        Returns:
            配置字典或None
        """
        if resource_name in self.resources:
            return self.resources[resource_name].config.copy()
        return None
    
    def get_all_resources(self):
        """獲取所有資源名稱列表"""
        return list(self.resources.keys())
    
    def reset_resource(self, resource_name):
        """重置資源到第一幀"""
        if resource_name in self.resources:
            self.resources[resource_name].reset()
            print(f"✓ Reset resource: {resource_name}")
    
    def cleanup(self):
        """清理所有資源"""
        for name, resource in self.resources.items():
            resource.cleanup()
            print(f"✓ Cleaned up: {name}")
        
        self.resources = {}
        print("✓ All resources cleaned up")
