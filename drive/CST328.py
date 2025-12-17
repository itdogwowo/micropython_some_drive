from machine import Pin, Timer
import time

class CST328:
    """
    CST328 電容觸摸芯片驅動 - 專注於硬件通信
    """
    # CST328 寄存器地址
    REG_TOUCH_DATA = 0x00
    REG_TOUCH_NUM = 0x05
    
    REG_TOUCH_MISC = 0x03
    REG_CHIP_ID = 0xA7
    REG_FW_VERSION = 0xA6
    REG_SLEEP_MODE = 0xE5
    REG_IRQ_ENABLE = 0xFA
    REG_SOFT_RESET = 0xEE
    
    def __init__(self, i2c, address=0x1A, int_pin=None, rst_pin=None):
        """
        初始化CST328驅動
        """
        self.i2c = i2c
        self.address = address

        self.touch_count = 0
        self.first_buf = bytearray(6)
        
        # 初始化引腳
        self.int_pin = Pin(int_pin, Pin.IN, Pin.PULL_UP) if int_pin else None
        self.rst_pin = Pin(rst_pin, Pin.OUT) if rst_pin else None
        
        # 初始化硬件
        if self.rst_pin:
            self._reset()
        self._init()
        
    def _reset(self):
        """硬件復位芯片"""
        if self.rst_pin:
            print("執行硬件復位...")
            self.rst_pin.value(0)
            time.sleep_ms(20)
            self.rst_pin.value(1)
            time.sleep_ms(100)
            
    def _init(self):
        """初始化芯片配置"""
        try:
            # 軟件復位
            for _ in range(3):
                self._write(self.REG_SOFT_RESET, 0x01)
                time.sleep_ms(20)
                
            # 檢查芯片
            chip_id = self._read(self.REG_CHIP_ID)
            print(f"CST328 Chip ID: 0x{chip_id:02X}")
            
            fw_version = self._read(self.REG_FW_VERSION)
            print(f"Firmware Version: 0x{fw_version:02X}")
            
            # 清空緩存
            for _ in range(5):
                self._read(self.REG_TOUCH_DATA, 72)
                time.sleep_ms(10)
                
            print("CST328 初始化完成")
        except Exception as e:
            print(f"CST328 初始化警告: {e}")
            
    def _write(self, address, data):
        """寫入寄存器"""
        try:
            if isinstance(data, int):
                data = bytes([data])
            self.i2c.writeto_mem(self.address, address, data)
            return True
        except:
            return False
            
    def _read(self, address, length=1):
        """讀取寄存器"""
        try:
            data = self.i2c.readfrom_mem(self.address, address, length)
            return data[0] if length == 1 else data
        except:
            return 0 if length == 1 else b'\x00' * length
            
    def read_touch(self):
        """
        讀取觸摸數據
        返回: (touch_count, touch_points)
        """
        
        self.touch_count = self.first_buf[5] & 0x0F
        
        if self.touch_count == 0:
            return 0, []
            
        # 讀取觸摸數據
        raw_data = self.first_buf
        
        touch_id = raw_data[0]& 0xF0
        pressure = raw_data[4]
        
        x_high = raw_data[1]       # 寄存器 0x01: X 坐標高八位
        y_high = raw_data[2]       # 寄存器 0x02: Y 坐標高八位
        xy_low = raw_data[3]       # 寄存器 0x03: 低四位為 X 低四位，高四位為 Y 低四位
        
        x = (x_high << 4) | (xy_low & 0x0F)   # X: 高8位左移4位，或上低4位
        y = (y_high << 4) | (xy_low >> 4)     # Y: 高8位左移4位，或上低4位（從xy_low高4位右移）
        
        points = {
                    'x': x,
                    'y': y,
                    'pressure': pressure,
                    'touch_id': touch_id,
                    'touch_count': self.touch_count
                    }
        
        return self.touch_count , points
#         return points
        
    def is_touched(self):
        """檢查是否有觸摸"""
        if not self.int_pin :
            return self.int_pin.value() == 0
        else:
            self.i2c.readfrom_mem_into(0x1A,0x00,self.first_buf)
            return self.first_buf[0] & 0x0F == 0x06