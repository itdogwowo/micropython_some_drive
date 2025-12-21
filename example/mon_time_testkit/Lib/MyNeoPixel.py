from machine import Pin
from neopixel import NeoPixel

class MyNeoPixel(NeoPixel):
    def __init__(self, pin, n, bpp=3, brightness=1.0, auto_write=False):
        super().__init__(pin, n, bpp=bpp)
        self._bpp = bpp
        self._colors = [(0,) * bpp] * n  # 存储原始颜色（未应用亮度）
        self._brightness = brightness
        self.auto_write = auto_write  # 控制是否自动更新硬件

    def __repr__(self):
        return str(self._colors.copy())

    def __setitem__(self, index, value):
        # 处理切片赋值
        if isinstance(index, slice):
            start, stop, step = index.indices(len(self))
            indices = list(range(start, stop, step))
            if len(indices) != len(value):
                raise ValueError("Slice assignment length mismatch")
            for i, val in zip(indices, value):
                self._set_item(i, val)
        else:
            self._set_item(index, value)
        
        # 自动更新硬件
        if self.auto_write:
            self.write()

    def _set_item(self, index, value):
        # 解析颜色格式（支持元组/整型）
        parsed_color = self._parse_color(value)
        # 存储原始颜色
        self._colors[index] = parsed_color
        # 应用亮度并设置到硬件
        adjusted_color = self._apply_brightness(parsed_color)
        super().__setitem__(index, adjusted_color)

    def _parse_color(self, color):
        # 将颜色统一转换为元组格式
        if isinstance(color, int):
            if self._bpp == 3:
                return (
                    (color >> 16) & 0xFF,
                    (color >> 8) & 0xFF,
                    color & 0xFF
                )
            elif self._bpp == 4:
                return (
                    (color >> 24) & 0xFF,
                    (color >> 16) & 0xFF,
                    (color >> 8) & 0xFF,
                    color & 0xFF
                )
        elif isinstance(color, (tuple, list)):
            return tuple(color)
        else:
            raise ValueError("Invalid color format")

    def _apply_brightness(self, color):
        # 应用亮度并钳制数值范围
        return tuple(
            min(255, max(0, int(c * self._brightness)))
            for c in color
        )

    @property
    def brightness(self):
        return self._brightness

    @brightness.setter
    def brightness(self, value):
        if not 0.0 <= value <= 1.0:
            raise ValueError("Brightness must be 0.0~1.0")
        self._brightness = value
        # 重新应用亮度到所有LED
        for i in range(len(self._colors)):
            adjusted = self._apply_brightness(self._colors[i])
            super().__setitem__(i, adjusted)
        if self.auto_write:
            self.write()

    def fill(self, color):
        parsed_color = self._parse_color(color)
        self._colors = [parsed_color] * len(self)
        adjusted_color = self._apply_brightness(parsed_color)
        super().fill(adjusted_color)
        if self.auto_write:
            self.write()

    def write(self):
        super().write()

    def show(self):
        self.write()


from machine import Pin
from esp32 import RMT
import time

class NeoPixel1:
    # WS2812 时序参数 (单位: ns)
    T0H = 600
    T0L = 300
    T1H = 300
    T1L = 600
    RESET_US = 300
    
    # RMT 时钟频率 (80MHz / 8 = 10MHz)
    RMT_CLK_DIV = 8  # 每个时钟周期 100ns
    
    def __init__(self, pin, num_leds):
        self.num_leds = num_leds
        self.pin = pin
        self.rmt = RMT(
            0,
            pin=self.pin,
            clock_div=self.RMT_CLK_DIV,

        )
        
        # 初始化颜色数据
        self.buffer = bytearray(num_leds * 3)
        self._rmt_buf = bytearray()
        
        # 生成 RMT 时序转换表
        self._timing = {
            0: self._make_pulse(self.T0H, self.T0L),
            1: self._make_pulse(self.T1H, self.T1L)
        }
    
    def _make_pulse(self, high_ns, low_ns):
        """将纳秒时间转换为 RMT 时钟周期数"""
        high_ticks = (high_ns // 100)  # 每个时钟周期 100ns
        low_ticks = (low_ns // 100)
        return (high_ticks, low_ticks)
    
    def _encode_bits(self, data):
        """将字节数据编码为 RMT 脉冲序列"""
        for byte in data:
            for i in range(7, -1, -1):
                bit = (byte >> i) & 1
                high, low = self._timing[bit]
                self._rmt_buf.append(high | 0x80)  # 设置持续时间的最高位
                self._rmt_buf.append(low)
    
    def _create_rmt_buffer(self):
        """创建 RMT 数据缓冲区"""
        self._rmt_buf = bytearray()
        
        # 编码颜色数据
        self._encode_bits(self.buffer)
        
        # 添加复位信号
        reset_ticks = self.RESET_US * 1000 // 100  # 转换为时钟周期
        self._rmt_buf.append(0x80)  # 持续标志位
        self._rmt_buf.append(reset_ticks & 0x7F)
    
    def fill(self, color):
        """填充所有 LED 为相同颜色"""
        for i in range(self.num_leds):
            self.set_pixel(i, color)
    
    def set_pixel(self, n, color):
        """设置单个 LED 颜色"""
        r, g, b = color
        index = n * 3
        self.buffer[index] = g  # WS2812 使用 GRB 顺序
        self.buffer[index + 1] = r
        self.buffer[index + 2] = b
    
    def write(self):
        """将数据写入 LED 灯带"""
        self._create_rmt_buffer()
        self.rmt.write_pulses(tuple(self._rmt_buf), 0)
    
    def rainbow(self, wait_ms=20):
        """彩虹效果示例"""
        for j in range(256):
            for i in range(self.num_leds):
                rc_index = (i * 256 // self.num_leds) + j
                self.set_pixel(i, self.wheel(rc_index & 255))
            self.write()
            time.sleep_ms(wait_ms)
    
    @staticmethod
    def wheel(pos):
        """生成彩虹颜色"""
        if pos < 85:
            return (pos * 3, 255 - pos * 3, 0)
        elif pos < 170:
            pos -= 85
            return (255 - pos * 3, 0, pos * 3)
        else:
            pos -= 170
            return (0, pos * 3, 255 - pos * 3)