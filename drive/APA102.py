# apa102.py  MicroPython 官方驱动（精简版，已兼容 APA102C）
class APA102:
    ORDER = (0, 1, 2, 3)          # RGB 顺序；APA102C 要改成 (0,2,1,3)
    def __init__(self, clk, data, n, *, brightness=31):
        from machine import SPI, Pin
        self.n = n
        self.buf = bytearray(n * 4 + 8)   # 4 帧头 + 4*n 数据 + 4 帧尾
        # 硬件 SPI 初始化
        self.spi = SPI(1, baudrate=4_000_000,
                       polarity=0, phase=1,
                       sck=clk, mosi=data)
        # 帧头 0x00 *4
        for i in range(4):
            self.buf[i] = 0
        # 帧尾 0xFF *4
        for i in range(4):
            self.buf[4 * n + 4 + i] = 0xFF
        self._brightness = brightness & 0x1F

    def __setitem__(self, i, color):
        r, g, b, brightness = color
        if len(color) == 3:
            brightness = self._brightness
        else:
            brightness &= 0x1F
        order = self.ORDER
        self.buf[4 + 4 * i + order[0]] = r
        self.buf[4 + 4 * i + order[1]] = g
        self.buf[4 + 4 * i + order[2]] = b
        self.buf[4 + 4 * i + 3] = 0xE0 | brightness

    def write(self):
        self.spi.write(self.buf)