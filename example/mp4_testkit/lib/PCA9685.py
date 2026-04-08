import ustruct
import time

class PCA9685:
    # 寄存器地址常量
    MODE1 = 0x00
    PRESCALE = 0xFE
    LED0_ON_L = 0x06
    ALL_LED_ON_L = 0xFA
    ALL_LED_OFF_L = 0xFC
    
    def __init__(self, i2c, address=0x40):
        """初始化PCA9685控制器
        Args:
            i2c: I2C通訊物件
            address: 設備地址 (默認0x40)
        """
        self.i2c = i2c
        self.address = address
        self.buffer = [0] * 16  # 存儲各通道PWM值
        self._pwm_registers = bytearray(64)  # 存儲I2C寄存器數值
        self.reset()

    def __getitem__(self, index):
        """通過索引獲取LED控制器"""
        if 0 <= index < 16:
            return self.LED(self, index)
        raise IndexError('Index out of range (0-15)')

    def __setitem__(self, index, value):
        """設置指定通道PWM值並立即更新"""
        if 0 <= index < 16:
            self.duty(index, value)
        else:
            raise IndexError('Index out of range (0-15)')

    def __iter__(self):
        """迭代所有LED控制器"""
        return (self.LED(self, i) for i in range(16))

    class LED:
        """LED通道控制句柄"""
        def __init__(self, controller, index):
            self.controller = controller
            self.index = index

        def duty(self, value):
            """設置PWM占空比"""
            self.controller.duty(self.index, value)

    def _write(self, address, value):
        """寫入單個寄存器"""
        self.i2c.writeto_mem(self.address, address, bytearray([value]))

    def _read(self, address):
        """讀取單個寄存器"""
        return self.i2c.readfrom_mem(self.address, address, 1)[0]
    def reset(self):
        """復位設備到初始狀態"""
        try:
            self._write(self.MODE1, 0x00)  # 進入正常模式
        except BaseException as e:
            print(e)



    def freq(self, freq=None):
        """設置/獲取PWM頻率"""

        if freq is None:
            return int(25000000.0 / 4096 / (self._read(self.PRESCALE) - 0.5))
        prescale = int(25000000.0 / 4096.0 / freq + 0.5)
        old_mode = self._read(self.MODE1)
        self._write(self.MODE1, (old_mode & 0x7F) | 0x10)  # 進入休眠
        self._write(self.PRESCALE, prescale)
        self._write(self.MODE1, old_mode)
        time.sleep_us(5)
        self._write(self.MODE1, old_mode | 0xA1)  # 自動增量使能

    def pwm(self, index, on=None, off=None):
        """直接操作PWM寄存器"""
        reg = self.LED0_ON_L + 4 * index
        if on is None or off is None:
            data = self.i2c.readfrom_mem(self.address, reg, 4)
            return ustruct.unpack('<HH', data)
        self.i2c.writeto_mem(self.address, reg, ustruct.pack('<HH', on, off))

    def duty(self, index, value=None, invert=False):
        """設置PWM占空比 (0-4095)"""
        if value is None:
            # 讀取當前值
            _, off = self.pwm(index)
            return 4095 - off if invert else off
            
        if not 0 <= value <= 4095:
            raise ValueError("Duty cycle out of range (0-4095)")
            
        value = 4095 - value if invert else value
        if value == 0:
            self.pwm(index, 0, 4096)  # 全關
        elif value == 4095:
            self.pwm(index, 4096, 0)  # 全開
        else:
            self.pwm(index, 0, value)  # 正常PWM

        # 更新緩存
        self.buffer[index] = value
        self._update_pwm_register(index, value)

    def _update_pwm_register(self, index, value):
        """更新內部寄存器緩存"""
        reg_base = 4 * index
        # ON時間固定為0
        self._pwm_registers[reg_base] = 0 & 0xFF       # ON_L
        self._pwm_registers[reg_base + 1] = ( 0 >> 8) & 0x0F      # ON_H
        # 設置OFF時間
        self._pwm_registers[reg_base + 2] = value & 0xFF        # OFF_L
        self._pwm_registers[reg_base + 3] = (value >> 8) & 0x0F  # OFF_H

    def duty_all(self, value=None):
        """同時設置所有通道的PWM值"""
        if value is None:
            value = 0
        if not 0 <= value <= 4095:
            raise ValueError("Duty cycle out of range (0-4095)")

        on_l = 0 & 0xFF
        on_h = (0 >> 8) & 0x0F
        off_l = value & 0xFF
        off_h = (value >> 8) & 0x0F
            
        # 使用全通道更新寄存器
        data = ustruct.pack('<HH', 0, value)
        self.i2c.writeto_mem(self.address, self.ALL_LED_ON_L, bytearray([on_l, on_h, off_l, off_h]))

    def write_buffer(self):
        """將緩存數據批量寫入設備"""
        # 先更新所有寄存器緩存
        for i in range(16):
            self._update_pwm_register(i, self.buffer[i])
        # 批量寫入I2C
        self.i2c.writeto_mem(self.address, self.LED0_ON_L, self._pwm_registers)

    def sync_buffer(self, max_diff=5):
        """智能緩存同步 (差異超過指定數量時批量更新)"""
        diff_count = 0
        diff_indices = []
        
        # 檢測差異
        for i in range(16):
            # 從寄存器緩存讀取當前值
            off_l = self._pwm_registers[4*i + 2]
            off_h = self._pwm_registers[4*i + 3]
            cached_value = (off_h << 8) | off_l
            if cached_value != self.buffer[i]:
                diff_count += 1
                diff_indices.append(i)
                
        # 根據差異數量選擇更新策略
        if diff_count == 0:
            return
        elif diff_count > max_diff:
            self.write_buffer()
        else:
            for i in diff_indices:
                self.duty(i, self.buffer[i])
                