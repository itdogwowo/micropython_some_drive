from machine import Pin, Timer
import time

class CST816D:
    """
    CST816D 电容触摸芯片驱动 - 专注于硬件通信
    单点触摸控制器，支持手势识别
    """
    
    # CST816D 寄存器地址定义
    REG_GESTURE_ID = 0x01      # 手势ID
    REG_FINGER_NUM = 0x02      # 触摸点数
    REG_XPOS_H = 0x03          # X坐标高4位
    REG_XPOS_L = 0x04          # X坐标低8位
    REG_YPOS_H = 0x05          # Y坐标高4位
    REG_YPOS_L = 0x06          # Y坐标低8位
    REG_CHIP_ID = 0xA7         # 芯片ID (0xB4)
    REG_PROJ_ID = 0xA8         # 项目ID
    REG_FW_VERSION = 0xA9      # 固件版本
    REG_MOTION_MASK = 0xEC     # 手势功能使能
    REG_IRQ_PULSE_WIDTH = 0xED # 中断脉冲宽度
    REG_NOR_SCAN_PER = 0xEE    # 正常扫描周期
    REG_MOTION_SL_ANGLE = 0xEF # 滑动角度控制
    REG_LP_AUTO_WAKEUP = 0xF4  # 自动唤醒时间
    REG_LP_SCAN_TH = 0xF5      # 低功耗扫描阈值
    REG_AUTO_SLEEP_TIME = 0xF9 # 自动休眠时间
    REG_IRQ_CTL = 0xFA         # 中断控制
    REG_AUTO_RESET = 0xFB      # 自动复位
    REG_LONG_PRESS_TICK = 0xFC # 长按时间设置
    REG_IOCTL = 0xFD           # IO控制
    REG_DIS_AUTO_SLEEP = 0xFE  # 禁用自动休眠
    
    # 手势ID定义
    GESTURE_NONE = 0x00
    GESTURE_SWIPE_UP = 0x01
    GESTURE_SWIPE_DOWN = 0x02
    GESTURE_SWIPE_LEFT = 0x03
    GESTURE_SWIPE_RIGHT = 0x04
    GESTURE_SINGLE_CLICK = 0x05
    GESTURE_DOUBLE_CLICK = 0x0B
    GESTURE_LONG_PRESS = 0x0C
    
    # 手势名称映射
    GESTURE_NAMES = {
        0x00: 'NONE',
        0x01: 'SWIPE_UP',
        0x02: 'SWIPE_DOWN',
        0x03: 'SWIPE_LEFT',
        0x04: 'SWIPE_RIGHT',
        0x05: 'SINGLE_CLICK',
        0x0B: 'DOUBLE_CLICK',
        0x0C: 'LONG_PRESS',
    }
    
    def __init__(self, i2c, address=0x15, int_pin=None, rst_pin=None):
        """
        初始化CST816D驱动
        
        :param i2c: I2C对象
        :param address: I2C地址，默认0x15
        :param int_pin: 中断引脚号
        :param rst_pin: 复位引脚号
        """
        self.i2c = i2c
        self.address = address
        self.touch_count = 0
        self.touch_buffer = bytearray(6)  # 用于读取触摸数据的缓冲区
        
        # 初始化引脚
        self.int_pin = Pin(int_pin, Pin.IN, Pin.PULL_UP) if int_pin is not None else None
        self.rst_pin = Pin(rst_pin, Pin.OUT) if rst_pin is not None else None
        
        # 初始化硬件
        if self.rst_pin:
            self._reset()
        
        self._init()
    
    def _reset(self):
        """硬件复位芯片"""
        if self.rst_pin:
            print("执行硬件复位...")
            self.rst_pin.value(0)
            time.sleep_ms(10)
            self.rst_pin.value(1)
            time.sleep_ms(50)
    
    def _init(self):
        """初始化芯片配置"""
        try:
            # 等待芯片稳定
            time.sleep_ms(50)
            
            # 读取芯片信息
            chip_id = self._read(self.REG_CHIP_ID)
            print(f"CST816D Chip ID: 0x{chip_id:02X}")
            
            if chip_id != 0xB4:
                print(f"警告: 芯片ID不匹配 (期望:0xB4, 实际:0x{chip_id:02X})")
            
            fw_version = self._read(self.REG_FW_VERSION)
            print(f"Firmware Version: 0x{fw_version:02X}")
            
            proj_id = self._read(self.REG_PROJ_ID)
            print(f"Project ID: 0x{proj_id:02X}")
            
            # 配置芯片参数
            self._write(self.REG_IRQ_CTL, 0x41)  # 使能中断，触摸时产生低脉冲
            self._write(self.REG_NOR_SCAN_PER, 0x01)  # 设置扫描周期
            self._write(self.REG_MOTION_MASK, 0xFF)   # 使能所有手势
            self._write(self.REG_IRQ_PULSE_WIDTH, 0x01)  # 中断脉冲宽度1ms
            
            # 清空缓存
            for _ in range(3):
                self._read(self.REG_GESTURE_ID, 6)
                time.sleep_ms(10)
            
            print("CST816D 初始化完成")
            
        except Exception as e:
            print(f"CST816D 初始化错误: {e}")
    
    def _write(self, address, data):
        """
        写入寄存器
        
        :param address: 寄存器地址
        :param data: 数据(int或bytes)
        :return: 是否成功
        """
        try:
            if isinstance(data, int):
                data = bytes([data])
            self.i2c.writeto_mem(self.address, address, data)
            return True
        except Exception as e:
            print(f"写入错误 0x{address:02X}: {e}")
            return False
    
    def _read(self, address, length=1):
        """
        读取寄存器
        
        :param address: 寄存器地址
        :param length: 读取长度
        :return: 读取的数据
        """
        try:
            data = self.i2c.readfrom_mem(self.address, address, length)
            return data[0] if length == 1 else data
        except Exception as e:
            print(f"读取错误 0x{address:02X}: {e}")
            return 0 if length == 1 else b'\x00' * length
    
    def read_touch(self):
        """
        读取触摸数据
        
        :return: (touch_count, touch_data_dict) 或 (0, None)
        """
        try:
            # 读取6字节数据: GESTURE_ID, FINGER_NUM, XPOS_H, XPOS_L, YPOS_H, YPOS_L
            self.i2c.readfrom_mem_into(self.address, self.REG_GESTURE_ID, self.touch_buffer)
            
            gesture_id = self.touch_buffer[0]
            finger_num = self.touch_buffer[1]
            
            # 如果没有触摸点
            if finger_num == 0:
                self.touch_count = 0
                return 0, None
            
            # 解析坐标 (12位分辨率)
            x = ((self.touch_buffer[2] & 0x0F) << 8) | self.touch_buffer[3]
            y = ((self.touch_buffer[4] & 0x0F) << 8) | self.touch_buffer[5]
            
            # 触摸事件类型 (高4位)
            event = (self.touch_buffer[2] & 0xC0) >> 6
            
            self.touch_count = finger_num
            
            # 组装触摸数据
            touch_data = {
                'x': x,
                'y': y,
                'gesture': self.GESTURE_NAMES.get(gesture_id, 'UNKNOWN'),
                'gesture_id': gesture_id,
                'event': event,  # 0:按下 1:抬起 2:接触
                'touch_count': finger_num
            }
            
            return finger_num, touch_data
            
        except Exception as e:
            print(f"读取触摸数据错误: {e}")
            return 0, None
    
    def is_touched(self):
        """
        检查是否有触摸
        
        :return: True表示有触摸，False表示无触摸
        """
        # 优先使用中断引脚判断
        if self.int_pin is not None:
            return self.int_pin.value() == 0
        
        # 备用方案：读取触摸点数量
        try:
            finger_num = self._read(self.REG_FINGER_NUM)
            return finger_num > 0
        except:
            return False
    
    def get_gesture(self):
        """
        单独读取手势ID
        
        :return: (gesture_id, gesture_name)
        """
        gesture_id = self._read(self.REG_GESTURE_ID)
        gesture_name = self.GESTURE_NAMES.get(gesture_id, 'UNKNOWN')
        return gesture_id, gesture_name
    
    def enable_auto_sleep(self, enable=True):
        """
        启用/禁用自动休眠
        
        :param enable: True启用，False禁用
        """
        self._write(self.REG_DIS_AUTO_SLEEP, 0x00 if enable else 0x01)
    
    def set_auto_sleep_time(self, seconds):
        """
        设置自动休眠时间
        
        :param seconds: 休眠时间(秒)，范围1-255
        """
        if 1 <= seconds <= 255:
            self._write(self.REG_AUTO_SLEEP_TIME, seconds)
    
    def set_long_press_time(self, ms):
        """
        设置长按触发时间
        
        :param ms: 长按时间(毫秒)，范围100-2550，步进10ms
        """
        ticks = min(255, max(10, ms // 10))
        self._write(self.REG_LONG_PRESS_TICK, ticks)
    
    def enter_sleep(self):
        """进入休眠模式"""
        self._write(self.REG_DIS_AUTO_SLEEP, 0x03)
    
    def get_chip_info(self):
        """
        获取芯片完整信息
        
        :return: 芯片信息字典
        """
        return {
            'chip_id': f"0x{self._read(self.REG_CHIP_ID):02X}",
            'fw_version': f"0x{self._read(self.REG_FW_VERSION):02X}",
            'proj_id': f"0x{self._read(self.REG_PROJ_ID):02X}",
        }


# ==================== 使用示例 ====================
if __name__ == '__main__':
    from machine import I2C, Pin
    
    # 初始化I2C (根据您的硬件修改引脚)
    i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
    
    # 创建CST816D对象
    touch = CST816D(
        i2c=i2c,
        address=0x15,
        int_pin=26,  # 中断引脚
        rst_pin=25   # 复位引脚
    )
    
    # 配置参数
    touch.set_long_press_time(500)  # 长按500ms触发
    touch.set_auto_sleep_time(10)   # 10秒无操作自动休眠
    
    # 获取芯片信息
    info = touch.get_chip_info()
    print("芯片信息:", info)
    
    print("\n开始检测触摸...")
    
    # 方式1: 使用中断引脚检测
    while True:
        if touch.is_touched():
            count, data = touch.read_touch()
            if data:
                print(f"触摸点数: {count}")
                print(f"坐标: ({data['x']}, {data['y']})")
                print(f"手势: {data['gesture']}")
                print(f"事件: {data['event']}")
                print("-" * 40)
        time.sleep_ms(50)
    
    # 方式2: 轮询读取
    # while True:
    #     count, data = touch.read_touch()
    #     if count > 0:
    #         print(f"X:{data['x']:4d} Y:{data['y']:4d} 手势:{data['gesture']}")
    #     time.sleep_ms(100)