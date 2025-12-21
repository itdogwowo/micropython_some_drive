# gs4_animation_with_color_fade.py
# 動畫播放 + 實時顏色漸變控制
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
MAX_ANIMATION_FRAMES = 30  # 最大動畫幀數
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
# 主循環：動畫播放 + 實時顏色控制
# ============================================================
# 初始化狀態
gpio_state = control_gpio.value()

# 顏色漸變狀態
current_angle = math.pi/2 if gpio_state else 3*math.pi/2  # 根據GPIO初始狀態
current_speed = COLOR_SPEED[gpio_state]
is_moving = False  # 初始已到達目標

# 動畫播放狀態
animation_frame = 0
animation_counter = 0
animation_speed = ANIMATION_SPEED

# 性能監控
frames = 0
last_time = time.ticks_ms()
last_gpio_state = gpio_state

print("\n動畫播放 + 實時顏色控制 系統啟動")
print("=" * 50)
print("工作原理:")
print("  1. 不斷播放動畫幀 (000.g4 → 001.g4 → ...)")
print("  2. GPIO實時控制顏色漸變方向")
print("  3. 每幀動畫都應用當前的顏色")
print("=" * 50)
print(f"初始GPIO: {gpio_state} ({'高電位' if gpio_state else '低電位'})")
print(f"顏色速度: {current_speed:.3f}")
print(f"動畫速度: 每{animation_speed}幀切換")
print(f"最大幀數: {MAX_ANIMATION_FRAMES}")

# 載入初始動畫幀
load_animation_frame_safe(root_path,animation_frame, gs4_buf, MAX_ANIMATION_FRAMES)

# 計算初始顏色
sin_val = math.sin(current_angle)
red = int((sin_val + 1) * 127.5)
green = 255 - red
red = max(0, min(255, red))
green = max(0, min(255, green))

print(f"初始顏色: 紅={red:3d}, 綠={green:3d}")
print(f"初始動畫幀: {animation_frame}")

while True:
    # ======================================================
    # 1. 讀取GPIO狀態
    # ======================================================
    gpio_state = control_gpio.value()
    
    # 如果GPIO狀態改變
    if gpio_state != last_gpio_state:
        last_gpio_state = gpio_state
        
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
        
        # 下一幀（循環）
        next_frame = (animation_frame + 1) % MAX_ANIMATION_FRAMES
        
        # 載入新幀
        loaded_frame, success = load_animation_frame_safe(
            root_path,
            next_frame, 
            gs4_buf, 
            MAX_ANIMATION_FRAMES
        )
        
        if success:
            animation_frame = loaded_frame
            # 可選：顯示幀號（調試用）
            # print(f"切換到動畫幀: {animation_frame}")
    
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
        
        print(f"FPS: {fps:2d} | GPIO:{gpio_state} ({state_text}) | "
              f"顏色:{moving_text:4s} | 動畫幀:{animation_frame:3d} | "
              f"紅:{red:3d} 綠:{green:3d}")
        
        frames = 0
        last_time = current_time
    
    # 可選：添加小延遲
    # time.sleep_ms(10)

# ============================================================
# 使用示例和調試函數
# ============================================================
def debug_functions():
    """調試和測試函數"""
    
    # 測試載入不同幀
    for i in range(5):
        frame, success = load_animation_frame_safe(root_path,i, gs4_buf, MAX_ANIMATION_FRAMES)
        print(f"測試載入幀 {i}: {'成功' if success else '失敗'} (實際幀: {frame})")
    
    # 測試邊界情況
    print("\n測試邊界情況:")
    test_frames = [0, 99, 100, 101, 200, -1]
    for frame in test_frames:
        safe_frame = frame % MAX_ANIMATION_FRAMES
        print(f"  輸入:{frame:4d} → 安全幀:{safe_frame:3d}")
    
    # 測試顏色計算
    print("\n測試顏色計算:")
    test_angles = [0, math.pi/2, math.pi, 3*math.pi/2, 2*math.pi]
    for angle in test_angles:
        sin_val = math.sin(angle)
        red = int((sin_val + 1) * 127.5)
        green = 255 - red
        print(f"  角度:{angle:6.3f} → 紅:{red:3d} 綠:{green:3d}")
