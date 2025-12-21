def rgb_gradient(rgb_start, rgb_end, steps):
    """
    RGB顏色漸變生成器
    
    參數:
        rgb_start: 起始RGB值,格式 (r, g, b) 或 [r, g, b],範圍0-255
        rgb_end: 結束RGB值,格式 (r, g, b) 或 [r, g, b],範圍0-255
        steps: 漸變步數
    
    返回:
        生成器,每次yield一個 (r, g, b) 元組
    
    使用示例:
        for rgb in rgb_gradient((255, 0, 0), (0, 0, 255), 10):
            print(rgb)  # (255, 0, 0) -> ... -> (0, 0, 255)
    """
    r_start, g_start, b_start = rgb_start
    r_end, g_end, b_end = rgb_end
    
    # 計算每步的增量
    r_step = (r_end - r_start) / (steps - 1) if steps > 1 else 0
    g_step = (g_end - g_start) / (steps - 1) if steps > 1 else 0
    b_step = (b_end - b_start) / (steps - 1) if steps > 1 else 0
    
    for i in range(steps):
        r = int(r_start + r_step * i)
        g = int(g_start + g_step * i)
        b = int(b_start + b_step * i)
        
        # 確保值在0-255範圍內
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        
        yield (r, g, b)


def rgb_gradient_list(rgb_start, rgb_end, steps):
    """
    RGB顏色漸變列表生成器(一次性返回所有值)
    
    參數:
        rgb_start: 起始RGB值 (r, g, b)
        rgb_end: 結束RGB值 (r, g, b)
        steps: 漸變步數
    
    返回:
        列表,包含所有漸變的RGB值
    """
    return list(rgb_gradient(rgb_start, rgb_end, steps))

              
def rgb_multi_next(palette):

    if len(palette) < 8 or len(palette) % 4 != 0:
        raise ValueError("調色板格式錯誤，必須包含至少2個顏色點，且每4個數字為一組(位置, R, G, B)")
    
    # 解析調色板
    color_points = []
    positions = []
    
    for i in range(0, len(palette), 4):
        position = palette[i]
        r = palette[i + 1]
        g = palette[i + 2]
        b = palette[i + 3]
        positions.append(position)
        color_points.append((r, g, b))
    
    if len(color_points) < 2:
        raise ValueError("至少需要兩個顏色節點")
    
    
    for i in range(len(color_points)-1):
        start_color = color_points[i]
        end_color = color_points[i + 1]
        steps = positions[i+1] - positions[i]
        
        
        # 生成當前段的漸變
        for rgb in rgb_gradient(start_color, end_color, steps):
            yield rgb
            
           
def rgb_multi_list(palette):
    """
    RGB顏色漸變列表生成器(一次性返回所有值)
    
    參數:
        rgb_start: 起始RGB值 (r, g, b)
        rgb_end: 結束RGB值 (r, g, b)
        steps: 漸變步數
    
    返回:
        列表,包含所有漸變的RGB值
    """
    return list(rgb_multi_next(palette))



class ColorPalette:
    """
    FastLED風格調色盤類
    
    支援自定義調色盤,類似FastLED的CRGBPalette
    """
    
    def __init__(self, palette_data=None):
        """
        初始化調色盤
        
        參數:
            palette_data: 調色盤數據
                格式1: (pos1, r1, g1, b1, pos2, r2, g2, b2, ...)
                格式2: [(pos1, r1, g1, b1), (pos2, r2, g2, b2), ...]
                pos範圍: 0-255,表示在調色盤中的位置
        """
        self.palette = []
        
        if palette_data:
            self.set_palette(palette_data)
    
    def set_palette(self, palette_data):
        """設置調色盤數據"""
        self.palette = []
        
        # 判斷格式並轉換
        if isinstance(palette_data, (tuple, list)):
            if len(palette_data) > 0 and isinstance(palette_data[0], (tuple, list)):
                # 格式2: [(pos, r, g, b), ...]
                for item in palette_data:
                    if len(item) == 4:
                        pos, r, g, b = item
                        self.palette.append((pos, r, g, b))
            else:
                # 格式1: (pos, r, g, b, pos, r, g, b, ...)
                if len(palette_data) % 4 != 0:
                    raise ValueError("調色盤數據長度必須是4的倍數")
                
                for i in range(0, len(palette_data), 4):
                    pos = palette_data[i]
                    r = palette_data[i + 1]
                    g = palette_data[i + 2]
                    b = palette_data[i + 3]
                    self.palette.append((pos, r, g, b))
        
        # 按位置排序
        self.palette.sort(key=lambda x: x[0])
    
    def get_color(self, position):
        """
        從調色盤獲取指定位置的顏色
        
        參數:
            position: 位置值,範圍0-255
        
        返回:
            (r, g, b) 元組
        """
        if not self.palette:
            return (0, 0, 0)
        
        # 確保position在0-255範圍內
        position = max(0, min(255, position))
        
        # 只有一個顏色節點
        if len(self.palette) == 1:
            return (self.palette[0][1], self.palette[0][2], self.palette[0][3])
        
        # 查找position所在的區間
        for i in range(len(self.palette) - 1):
            pos1, r1, g1, b1 = self.palette[i]
            pos2, r2, g2, b2 = self.palette[i + 1]
            
            if pos1 <= position <= pos2:
                # 在這個區間內,進行插值
                if pos2 == pos1:
                    ratio = 0
                else:
                    ratio = (position - pos1) / (pos2 - pos1)
                
                r = int(r1 + (r2 - r1) * ratio)
                g = int(g1 + (g2 - g1) * ratio)
                b = int(b1 + (b2 - b1) * ratio)
                
                return (r, g, b)
        
        # 超出範圍,返回最後一個顏色
        last = self.palette[-1]
        return (last[1], last[2], last[3])
    
    def get_gradient(self, num_colors):
        """
        獲取均勻分布的漸變色序列
        
        參數:
            num_colors: 要生成的顏色數量
        
        返回:
            RGB顏色列表
        """
        colors = []
        for i in range(num_colors):
            position = int(i * 255 / (num_colors - 1)) if num_colors > 1 else 0
            colors.append(self.get_color(position))
        return colors


# ============ 預定義調色盤 (FastLED風格) ============

# 彩虹調色盤
RAINBOW_PALETTE = (
    0, 255, 0, 0,      # 紅
    42, 255, 165, 0,   # 橙
    85, 255, 255, 0,   # 黃
    128, 0, 255, 0,    # 綠
    170, 0, 0, 255,    # 藍
    213, 75, 0, 130,   # 靛
    255, 238, 130, 238 # 紫
)

# 火焰調色盤
FIRE_PALETTE = (
    0, 0, 0, 0,        # 黑
    64, 128, 0, 0,     # 深紅
    128, 255, 0, 0,    # 紅
    192, 255, 128, 0,  # 橙
    255, 255, 255, 0   # 黃白
)

# 海洋調色盤
OCEAN_PALETTE = (
    0, 0, 0, 128,      # 深藍
    85, 0, 128, 255,   # 藍
    170, 0, 255, 255,  # 青
    255, 200, 255, 255 # 淺青
)

# 森林調色盤
FOREST_PALETTE = (
    0, 0, 64, 0,       # 深綠
    128, 0, 128, 0,    # 綠
    200, 128, 255, 0,  # 黃綠
    255, 200, 255, 100 # 淺黃綠
)

# 日落調色盤
SUNSET_PALETTE = (
    0, 25, 25, 112,    # 深藍
    64, 255, 140, 0,   # 深橙
    128, 255, 69, 0,   # 橙紅
    192, 255, 215, 0,  # 金色
    255, 255, 255, 224 # 淺黃
)

# 霓虹調色盤
NEON_PALETTE = (
    0, 255, 0, 255,    # 品紅
    64, 0, 255, 255,   # 青
    128, 0, 255, 0,    # 綠
    192, 255, 255, 0,  # 黃
    255, 255, 0, 255   # 品紅
)


def create_palette_effect(led_no=8, palette=RAINBOW_PALETTE, speed=1, 
                         reverse=False, scroll_speed=2):
    """
    調色盤滾動效果
    
    參數:
        led_no: LED數量
        palette: 調色盤數據
        speed: 幀速度
        reverse: 是否反向
        scroll_speed: 調色盤滾動速度
    
    返回:
        生成器,yield RGB值列表
    """
    pal = ColorPalette(palette)
    offset = 0
    
    while True:
        rgb_buffer = []
        
        for i in range(led_no):
            # 計算當前LED在調色盤中的位置
            position = (offset + i * (256 // led_no)) % 256
            rgb = pal.get_color(position)
            rgb_buffer.append(rgb)
        
        # 滾動調色盤
        offset = (offset + scroll_speed) % 256
        
        # 輸出
        for _ in range(speed):
            if reverse:
                yield rgb_buffer[::-1]
            else:
                yield rgb_buffer.copy()


# ============ HSV轉RGB工具 ============

def hsv_to_rgb(h, s, v):
    """
    HSV轉RGB
    
    參數:
        h: 色相 (0-360)
        s: 飽和度 (0-100)
        v: 明度 (0-100)
    
    返回:
        (r, g, b) 元組,範圍0-255
    """
    h = h % 360
    s = max(0, min(100, s)) / 100.0
    v = max(0, min(100, v)) / 100.0
    
    c = v * s
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = v - c
    
    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    
    r = int((r + m) * 255)
    g = int((g + m) * 255)
    b = int((b + m) * 255)
    
    return (r, g, b)


def rgb_to_hsv(r, g, b):
    """
    RGB轉HSV
    
    參數:
        r, g, b: RGB值,範圍0-255
    
    返回:
        (h, s, v) 元組
        h: 色相 0-360
        s: 飽和度 0-100
        v: 明度 0-100
    """
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    
    max_val = max(r, g, b)
    min_val = min(r, g, b)
    diff = max_val - min_val
    
    # 計算色相
    if diff == 0:
        h = 0
    elif max_val == r:
        h = 60 * (((g - b) / diff) % 6)
    elif max_val == g:
        h = 60 * (((b - r) / diff) + 2)
    else:
        h = 60 * (((r - g) / diff) + 4)
    
    # 計算飽和度
    s = 0 if max_val == 0 else (diff / max_val) * 100
    
    # 計算明度
    v = max_val * 100
    
    return (h, s, v)


