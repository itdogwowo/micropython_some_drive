# gs4_animation_with_color_fade_dual_mode.py
# 動畫播放 + 實時顏色漸變控制 + 雙模式循環（支援開機序列）
import time
import framebuf
import math
from machine import SPI, Pin
from TFT import *

# 顯示參數
W, H = 160, 160

# ============================================================
# GPIO引腳配置
# ============================================================
CONTROL_PIN = 1  # 使用GPIO1
control_gpio = Pin(CONTROL_PIN, Pin.IN, Pin.PULL_UP)
print(f"控制引腳 GPIO{CONTROL_PIN} 配置完成")
print(f"初始狀態: {'高電位' if control_gpio.value() else '低電位'}")

# ============================================================
# 可調節參數
# ============================================================
# 顏色漸變速度
COLOR_SPEED = {
    1: 0.10,  # 高電位：綠色 → 紅色 的速度
    0: 0.03   # 低電位：紅色 → 綠色 的速度
}

# 動畫播放速度（幀延遲）
ANIMATION_SPEED = 2  # 每2幀切換一次動畫（越小越快）
MAX_ANIMATION_FRAMES = 720  # 最大動畫幀數

# 模式配置
MODE_CONFIG = {
    0: {  # 模式1 (GPIO低電位)
        'boot_start': 0,        # 開機起始幀（首次從0開始）
        'start': 115,           # mode 1 start（模式切換時跳轉位置）
        'loop_start': 361,      # mode 1 loop start
        'loop_end': 434         # mode 1 loop end
    },
    1: {  # 模式2 (GPIO高電位)
        'boot_start': None,     # 模式2沒有開機序列
        'start': 435,           # mode 2 start
        'loop_start': 495,      # mode 2 loop start
        'loop_end': 709         # mode 2 loop end
    }
}

# 驗證配置
def validate_mode_config():
    """驗證模式配置是否有效"""
    for mode, config in MODE_CONFIG.items():
        # 檢查範圍
        if config.get('boot_start') is not None:
            if not (0 <= config['boot_start'] < MAX_ANIMATION_FRAMES):
                raise ValueError(f"模式{mode}的boot_start值超出範圍: {config['boot_start']}")
        
        if not (0 <= config['start'] < MAX_ANIMATION_FRAMES):
            raise ValueError(f"模式{mode}的start值超出範圍: {config['start']}")
        if not (0 <= config['loop_start'] < MAX_ANIMATION_FRAMES):
            raise ValueError(f"模式{mode}的loop_start值超出範圍: {config['loop_start']}")
        if not (0 <= config['loop_end'] < MAX_ANIMATION_FRAMES):
            raise ValueError(f"模式{mode}的loop_end值超出範圍: {config['loop_end']}")
        
        # 檢查順序
        if config['loop_start'] >= config['loop_end']:
            raise ValueError(f"模式{mode}: loop_start({config['loop_start']}) 必須小於 loop_end({config['loop_end']})")
        
        # 檢查start是否在loop範圍內
        if config['start'] > config['loop_end']:
            print(f"警告: 模式{mode}的start({config['start']})超過loop_end({config['loop_end']})")
    
    print("模式配置驗證通過")

validate_mode_config()

root_path = 'frame'

# ============================================================
# 核心函數：生成GS4調色板
# ============================================================
def build_gs4_palette_big_endian(pal_buf, r_tint, g_tint, b_tint=0):
    """為GS4格式生成16色調色板"""
    mv = memoryview(pal_buf)
    
    for gray in range(16):
        brightness = (gray << 4) | gray
        
        r = (r_tint * brightness) >> 8
        g = (g_tint * brightness) >> 8
        b = (b_tint * brightness) >> 8
        
        color = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        
        idx = gray * 2
        mv[idx] = (color >> 8) & 0xFF
        mv[idx + 1] = color & 0xFF

# ============================================================
# 安全載入動畫幀
# ============================================================
def load_animation_frame_safe(frame_path, frame_number, buffer, max_frames=100):
    """
    安全載入動畫幀
    自動處理幀號邊界（循環播放）
    """
    # 確保幀號在安全範圍內（0 到 max_frames-1）
    safe_frame = frame_number % max_frames
    
    try:
        # 生成文件名，例如：/000.g4, /001.g4, /002.g4
        filename = f"/{frame_path}/{safe_frame:03d}.g4"
        
        with open(filename, "rb") as f:
            bytes_read = f.readinto(buffer)
            
            if bytes_read != len(buffer):
                print(f"警告: {filename} 只讀取到 {bytes_read} 字節")
                # 填充剩餘部分
                if bytes_read < len(buffer):
                    buffer[bytes_read:] = b'\x00' * (len(buffer) - bytes_read)
            
            return safe_frame, True
            
    except Exception as e:
        print(f"載入 {filename} 失敗: {e}")
        # 創建錯誤提示圖像
        create_error_frame(buffer, safe_frame)
        return safe_frame, False

def create_error_frame(buffer, frame_number):
    """創建錯誤提示圖像"""
    # 創建棋盤格圖案
    for i in range(len(buffer)):
        x = (i * 2) % W
        y = (i * 2) // W
        
        # 棋盤格效果
        if ((x // 8) + (y // 8)) % 2 == 0:
            gray = 0x0F  # 亮色
        else:
            gray = 0x01  # 暗色
        
        # 添加幀號標記
        if x < 16 and y < 16:
            gray = (frame_number % 16)  # 左上角顯示幀號
        
        buffer[i] = (gray << 4) | gray

# ============================================================
# 動畫狀態機（支援開機序列）
# ============================================================
class AnimationStateMachine:
    """動畫狀態機，管理不同模式的播放，支援開機序列"""
    
    def __init__(self, mode_config, initial_mode=0):
        self.mode_config = mode_config
        self.current_mode = initial_mode
        self.is_first_run = True  # 是否是首次運行（開機序列）
        
        # 開機時，如果有boot_start就使用，否則使用start
        config = mode_config[initial_mode]
        if self.is_first_run and config.get('boot_start') is not None:
            self.current_frame = config['boot_start']
            print(f"使用開機序列: 從幀 {self.current_frame} 開始")
        else:
            self.current_frame = config['start']
            print(f"使用常規起點: 從幀 {self.current_frame} 開始")
        
        self.in_loop = False  # 是否在循環播放中
        self.direction = 1  # 播放方向: 1=正向
        
        print(f"動畫狀態機初始化: 模式={self.current_mode}, 起始幀={self.current_frame}")
    
    def update_frame(self):
        """更新當前幀號，根據模式進行循環"""
        config = self.mode_config[self.current_mode]
        
        # 計算下一幀
        next_frame = self.current_frame + self.direction
        
        # 判斷是否已經在循環中
        if self.in_loop:
            # 已經在循環中，檢查是否超出loop範圍
            if next_frame > config['loop_end']:
                # 超出loop_end，回到loop_start
                next_frame = config['loop_start']
                print(f"[循環] 模式{self.current_mode}: 到達loop_end({config['loop_end']})，跳轉到loop_start({config['loop_start']})")
            
            elif next_frame < config['loop_start']:
                # 低於loop_start（理論上不會發生，因為direction=1）
                next_frame = config['loop_start']
                print(f"[循環] 模式{self.current_mode}: 低於loop_start，回到{config['loop_start']}")
        
        else:
            # 還在首次播放中（開機序列或切換後的過渡）
            if next_frame >= config['loop_start']:
                # 到達或超過loop_start，進入循環模式
                self.in_loop = True
                self.is_first_run = False  # 關閉開機標記
                
                # 如果超過loop_end，立即回到loop_start
                if next_frame > config['loop_end']:
                    next_frame = config['loop_start']
                    print(f"[進入循環] 模式{self.current_mode}: 超過loop_end，直接進入循環 {config['loop_start']}")
                else:
                    print(f"[進入循環] 模式{self.current_mode}: 到達loop_start({config['loop_start']})，開始循環播放")
                    print(f"  循環範圍: {config['loop_start']}-{config['loop_end']}")
        
        self.current_frame = next_frame
        return self.current_frame
    
    def switch_mode(self, new_mode):
        """切換到新模式"""
        if new_mode == self.current_mode:
            return False
        
        old_mode = self.current_mode
        self.current_mode = new_mode
        config = self.mode_config[new_mode]
        
        # 跳轉到新模式的start幀（不使用boot_start，那是開機專用）
        self.current_frame = config['start']
        self.in_loop = False  # 重置循環狀態
        self.is_first_run = False  # 切換模式後不算首次運行
        self.direction = 1  # 重置為正向播放
        
        print(f"\n{'='*50}")
        print(f"模式切換: {old_mode} → {new_mode}")
        print(f"  跳轉到幀: {self.current_frame}")
        print(f"  目標循環範圍: {config['loop_start']}-{config['loop_end']}")
        print(f"{'='*50}\n")
        
        return True
    
    def get_mode_info(self):
        """獲取當前模式信息"""
        config = self.mode_config[self.current_mode]
        return {
            'mode': self.current_mode,
            'frame': self.current_frame,
            'in_loop': self.in_loop,
            'is_first_run': self.is_first_run,
            'loop_range': (config['loop_start'], config['loop_end']),
            'direction': self.direction
        }

# ============================================================
# 初始化顯示器
# ============================================================
spi = SPI(1, baudrate=40_000_000, polarity=0, phase=0)
spi.init(sck=Pin(13), mosi=Pin(12))
tft = ST7789(
    spi,
    dc=Pin(10),
    cs=Pin(9),
    rst=Pin(11),
    width=240,
    height=320,
    rotation=0
)
tft.set_rotation(0)
tft.set_color_order('RGB')
tft.invert_display(False)
tft.set_window(0, 0, W - 1, H - 1)

# ============================================================
# 創建緩衝區
# ============================================================
gs4_buf = bytearray((W * H + 1) // 2)
gs4_fb = framebuf.FrameBuffer(gs4_buf, W, H, framebuf.GS4_HMSB)
rgb_buf = bytearray(W * H * 2)
rgb_fb = framebuf.FrameBuffer(rgb_buf, W, H, framebuf.RGB565)
pal_buf = bytearray(16 * 2)
pal_fb = framebuf.FrameBuffer(pal_buf, 16, 1, framebuf.RGB565)

# ============================================================
# 初始化狀態
# ============================================================
# 初始化GPIO狀態
gpio_state = control_gpio.value()
last_gpio_state = gpio_state

# 創建動畫狀態機（根據GPIO初始狀態決定起始模式）
initial_mode = gpio_state  # 0=低電位, 1=高電位
anim_sm = AnimationStateMachine(MODE_CONFIG, initial_mode=initial_mode)

# 顏色漸變狀態
current_angle = math.pi/2 if gpio_state else 3*math.pi/2  # 根據GPIO初始狀態
current_speed = COLOR_SPEED[gpio_state]
is_moving = False  # 初始已到達目標

# 動畫播放狀態
animation_counter = 0
animation_speed = ANIMATION_SPEED

# 性能監控
frames = 0
last_time = time.ticks_ms()

print("\n雙模式動畫播放系統啟動（支援開機序列）")
print("=" * 50)
print("工作原理:")
print("  1. 開機時從幀0開始播放")
print("  2. 播放到loop_start時進入循環")
print("  3. GPIO切換時跳到對應模式的start幀")
print("  4. 實時顏色漸變控制")
print("=" * 50)
print(f"初始GPIO: {gpio_state} ({'高電位' if gpio_state else '低電位'})")
print(f"初始模式: {anim_sm.current_mode}")
print(f"初始幀: {anim_sm.current_frame}")

# 顯示配置詳情
for mode_id, config in MODE_CONFIG.items():
    print(f"\n模式{mode_id}配置:")
    if config.get('boot_start') is not None:
        print(f"  開機序列: {config['boot_start']} → {config['start']} → {config['loop_start']}")
    else:
        print(f"  切換起點: {config['start']} → {config['loop_start']}")
    print(f"  循環範圍: {config['loop_start']} - {config['loop_end']}")

print(f"\n顏色速度: {current_speed:.3f}")
print(f"動畫速度: 每{animation_speed}幀切換")

# 載入初始動畫幀
load_animation_frame_safe(root_path, anim_sm.current_frame, gs4_buf, MAX_ANIMATION_FRAMES)

# 計算初始顏色
sin_val = math.sin(current_angle)
red = int((sin_val + 1) * 127.5)
green = 255 - red
red = max(0, min(255, red))
green = max(0, min(255, green))
print(f"初始顏色: 紅={red:3d}, 綠={green:3d}")

# ============================================================
# 主循環：動畫播放 + 實時顏色控制
# ============================================================
while True:
    # ======================================================
    # 1. 讀取GPIO狀態並切換模式
    # ======================================================
    gpio_state = control_gpio.value()
    
    # 如果GPIO狀態改變，切換模式
    if gpio_state != last_gpio_state:
        last_gpio_state = gpio_state
        
        # 切換模式 (0=低電位, 1=高電位)
        new_mode = gpio_state
        if anim_sm.switch_mode(new_mode):
            # 載入新模式的第一幀
            load_animation_frame_safe(
                root_path, 
                anim_sm.current_frame, 
                gs4_buf, 
                MAX_ANIMATION_FRAMES
            )
        
        # 更新顏色漸變目標和速度
        target_angle = math.pi/2 if gpio_state else 3*math.pi/2
        current_speed = COLOR_SPEED[gpio_state]
        is_moving = True  # 開始移動
        
        # 顯示切換信息
        direction = "綠色→紅色" if gpio_state else "紅色→綠色"
        print(f"[{time.ticks_ms()//1000}s] GPIO改變: {gpio_state} ({direction})")
        print(f"  顏色速度: {current_speed:.3f}")
    
    # ======================================================
    # 2. 更新顏色漸變
    # ======================================================
    if is_moving:
        target_angle = math.pi/2 if gpio_state else 3*math.pi/2
        angle_diff = target_angle - current_angle
        
        # 選擇最短路径
        if abs(angle_diff) > math.pi:
            if angle_diff > 0:
                angle_diff -= 2 * math.pi
            else:
                angle_diff += 2 * math.pi
        
        # 使用當前速度移動
        if abs(angle_diff) > current_speed:
            # 向目標移動
            current_angle += current_speed if angle_diff > 0 else -current_speed
        else:
            # 到達目標，停止
            current_angle = target_angle
            is_moving = False
            
            # 顯示到達信息
            color_name = "紅色" if gpio_state else "綠色"
            print(f"  到達目標顏色: {color_name}")
    
    # 計算當前顏色
    sin_val = math.sin(current_angle)
    red = int((sin_val + 1) * 127.5)
    green = 255 - red
    red = max(0, min(255, red))
    green = max(0, min(255, green))
    
    # ======================================================
    # 3. 更新動畫幀
    # ======================================================
    animation_counter += 1
    
    if animation_counter >= animation_speed:
        animation_counter = 0
        
        # 更新幀號（狀態機會處理循環邏輯）
        next_frame = anim_sm.update_frame()
        
        # 載入新幀
        loaded_frame, success = load_animation_frame_safe(
            root_path,
            next_frame, 
            gs4_buf, 
            MAX_ANIMATION_FRAMES
        )
    
    # ======================================================
    # 4. 渲染和顯示
    # ======================================================
    # 4.1 生成當前顏色的調色板
    build_gs4_palette_big_endian(pal_buf, red, green)
    
    # 4.2 應用調色板到當前動畫幀
    rgb_fb.blit(gs4_fb, 0, 0, -1, pal_fb)
    
    # 4.3 顯示到屏幕
    tft.write_data(rgb_buf)
    
    # ======================================================
    # 5. 性能監控
    # ======================================================
    frames += 1
    current_time = time.ticks_ms()
    
    # 每秒顯示狀態
    if time.ticks_diff(current_time, last_time) >= 1000:
        fps = frames
        state_text = "高電位" if gpio_state else "低電位"
        moving_text = "移動中" if is_moving else "已停止"
        mode_info = anim_sm.get_mode_info()
        
        loop_status = "循環中" if mode_info['in_loop'] else "過渡中"
        first_run_text = "(開機)" if mode_info['is_first_run'] else ""
        
        print(f"FPS:{fps:2d} | 模式:{mode_info['mode']} | GPIO:{gpio_state}({state_text}) | "
              f"幀:{mode_info['frame']:3d} | {loop_status}{first_run_text} | "
              f"顏色:紅{red:3d}/綠{green:3d}")
        
        frames = 0
        last_time = current_time