import time
from machine import I2C, Pin
import struct

class QMI8658:
    # I2C地址
    I2C_ADDR = 0x6B
    I2C_ADDR_ALT = 0x6A
    
    # 寄存器地址
    REG_WHO_AM_I = 0x00
    REG_REVISION_ID = 0x01
    REG_CTRL1 = 0x02
    REG_CTRL2 = 0x03
    REG_CTRL3 = 0x04
    REG_CTRL4 = 0x05
    REG_CTRL5 = 0x06
    REG_CTRL6 = 0x07
    REG_CTRL7 = 0x08
    REG_CTRL8 = 0x09
    REG_CTRL9 = 0x0A
    REG_CAL1_L = 0x0B
    REG_CAL1_H = 0x0C
    REG_CAL2_L = 0x0D
    REG_CAL2_H = 0x0E
    REG_CAL3_L = 0x0F
    REG_CAL3_H = 0x10
    REG_CAL4_L = 0x11
    REG_CAL4_H = 0x12
    REG_FIFO_WTM_TH = 0x13
    REG_FIFO_CTRL = 0x14
    REG_FIFO_SMPL_CNT = 0x15
    REG_FIFO_STATUS = 0x16
    REG_FIFO_DATA = 0x17
    REG_STATUS_INT = 0x2D
    REG_STATUS0 = 0x2E
    REG_STATUS1 = 0x2F
    REG_TIMESTAMP_LOW = 0x30
    REG_TIMESTAMP_MID = 0x31
    REG_TIMESTAMP_HIGH = 0x32
    REG_TEMP_L = 0x33
    REG_TEMP_H = 0x34
    REG_AX_L = 0x35
    REG_AX_H = 0x36
    REG_AY_L = 0x37
    REG_AY_H = 0x38
    REG_AZ_L = 0x39
    REG_AZ_H = 0x3A
    REG_GX_L = 0x3B
    REG_GX_H = 0x3C
    REG_GY_L = 0x3D
    REG_GY_H = 0x3E
    REG_GZ_L = 0x3F
    REG_GZ_H = 0x40
    REG_COD_STATUS = 0x46
    
    # 設備ID
    CHIP_ID = 0x05
    
    # 加速度計範圍設置
    ACC_RANGE_2G = 0x00
    ACC_RANGE_4G = 0x01
    ACC_RANGE_8G = 0x02
    ACC_RANGE_16G = 0x03
    
    # 陀螺儀範圍設置
    GYR_RANGE_16DPS = 0x00
    GYR_RANGE_32DPS = 0x01
    GYR_RANGE_64DPS = 0x02
    GYR_RANGE_128DPS = 0x03
    GYR_RANGE_256DPS = 0x04
    GYR_RANGE_512DPS = 0x05
    GYR_RANGE_1024DPS = 0x06
    GYR_RANGE_2048DPS = 0x07
    
    # ODR (Output Data Rate) 設置
    ODR_8000HZ = 0x00
    ODR_4000HZ = 0x01
    ODR_2000HZ = 0x02
    ODR_1000HZ = 0x03
    ODR_500HZ = 0x04
    ODR_250HZ = 0x05
    ODR_125HZ = 0x06
    ODR_62_5HZ = 0x07
    ODR_31_25HZ = 0x08
    
    def __init__(self, i2c, addr=None, int_pin=None):
        """
        初始化QMI8658
        
        Args:
            i2c: I2C對象
            addr: I2C地址，默認自動檢測
            int_pin: 中斷引腳（可選）
        """
        self.i2c = i2c
        self.int_pin = int_pin
        
        # 自動檢測I2C地址
        if addr is None:
            if self._check_device(self.I2C_ADDR):
                self.addr = self.I2C_ADDR
            elif self._check_device(self.I2C_ADDR_ALT):
                self.addr = self.I2C_ADDR_ALT
            else:
                raise RuntimeError("QMI8658 not found on I2C bus")
        else:
            self.addr = addr
            
        # 驗證設備ID
        if not self._check_device(self.addr):
            raise RuntimeError(f"Invalid device ID at address 0x{self.addr:02X}")
            
        # 設置默認配置
        self.acc_range = self.ACC_RANGE_2G
        self.gyr_range = self.GYR_RANGE_256DPS
        self.acc_scale = 2.0 / 32768.0  # g/LSB
        self.gyr_scale = 256.0 / 32768.0  # dps/LSB
        
        # 初始化傳感器
        self._init_sensor()
        
    def _check_device(self, addr):
        """檢查設備是否存在且ID正確"""
        try:
            chip_id = self._read_reg(self.REG_WHO_AM_I, addr)
            return chip_id == self.CHIP_ID
        except:
            return False
            
    def _read_reg(self, reg, addr=None):
        """讀取單個寄存器"""
        if addr is None:
            addr = self.addr
        return self.i2c.readfrom_mem(addr, reg, 1)[0]
        
    def _write_reg(self, reg, value):
        """寫入單個寄存器"""
        self.i2c.writeto_mem(self.addr, reg, bytes([value]))
        
    def _read_reg_bytes(self, reg, length):
        """讀取多個寄存器"""
        return self.i2c.readfrom_mem(self.addr, reg, length)
        
    def _init_sensor(self):
        """初始化傳感器配置"""
        # 軟復位
        self._write_reg(self.REG_CTRL1, 0x60)
        time.sleep_ms(10)
        
        # 使能加速度計和陀螺儀
        self._write_reg(self.REG_CTRL1, 0x40)  # 同步模式
        self._write_reg(self.REG_CTRL2, 0x95)  # 加速度計使能，2G範圍，1000Hz ODR
        self._write_reg(self.REG_CTRL3, 0xD5)  # 陀螺儀使能，256dps範圍，1000Hz ODR
        self._write_reg(self.REG_CTRL5, 0x11)  # 低通濾波器設置
        self._write_reg(self.REG_CTRL7, 0x03)  # 使能加速度計和陀螺儀
        
        time.sleep_ms(50)  # 等待穩定
        
    def set_acc_range(self, range_val):
        """設置加速度計量程"""
        ctrl2 = self._read_reg(self.REG_CTRL2)
        ctrl2 = (ctrl2 & 0xF0) | (range_val << 4) | (ctrl2 & 0x0F)
        self._write_reg(self.REG_CTRL2, ctrl2)
        
        self.acc_range = range_val
        if range_val == self.ACC_RANGE_2G:
            self.acc_scale = 2.0 / 32768.0
        elif range_val == self.ACC_RANGE_4G:
            self.acc_scale = 4.0 / 32768.0
        elif range_val == self.ACC_RANGE_8G:
            self.acc_scale = 8.0 / 32768.0
        elif range_val == self.ACC_RANGE_16G:
            self.acc_scale = 16.0 / 32768.0
            
    def set_gyr_range(self, range_val):
        """設置陀螺儀量程"""
        ctrl3 = self._read_reg(self.REG_CTRL3)
        ctrl3 = (ctrl3 & 0xF0) | (range_val << 4) | (ctrl3 & 0x0F)
        self._write_reg(self.REG_CTRL3, ctrl3)
        
        self.gyr_range = range_val
        ranges = [16, 32, 64, 128, 256, 512, 1024, 2048]
        self.gyr_scale = ranges[range_val] / 32768.0
        
    def set_acc_odr(self, odr):
        """設置加速度計輸出數據率"""
        ctrl2 = self._read_reg(self.REG_CTRL2)
        ctrl2 = (ctrl2 & 0xF0) | odr
        self._write_reg(self.REG_CTRL2, ctrl2)
        
    def set_gyr_odr(self, odr):
        """設置陀螺儀輸出數據率"""
        ctrl3 = self._read_reg(self.REG_CTRL3)
        ctrl3 = (ctrl3 & 0xF0) | odr
        self._write_reg(self.REG_CTRL3, ctrl3)
        
    def read_acceleration(self):
        """讀取加速度數據 (g)"""
        data = self._read_reg_bytes(self.REG_AX_L, 6)
        ax = struct.unpack('<h', data[0:2])[0] * self.acc_scale
        ay = struct.unpack('<h', data[2:4])[0] * self.acc_scale
        az = struct.unpack('<h', data[4:6])[0] * self.acc_scale
        return (ax, ay, az)
        
    def read_gyroscope(self):
        """讀取陀螺儀數據 (dps)"""
        data = self._read_reg_bytes(self.REG_GX_L, 6)
        gx = struct.unpack('<h', data[0:2])[0] * self.gyr_scale
        gy = struct.unpack('<h', data[2:4])[0] * self.gyr_scale
        gz = struct.unpack('<h', data[4:6])[0] * self.gyr_scale
        return (gx, gy, gz)
        
    def read_temperature(self):
        """讀取溫度數據 (°C)"""
        data = self._read_reg_bytes(self.REG_TEMP_L, 2)
        temp_raw = struct.unpack('<h', data)[0]
        temperature = temp_raw / 256.0  # 根據數據手冊轉換
        return temperature
        
    def read_all(self):
        """一次性讀取所有傳感器數據"""
        # 讀取溫度
        temp = self.read_temperature()
        
        # 讀取加速度計和陀螺儀數據
        data = self._read_reg_bytes(self.REG_AX_L, 12)
        
        ax = struct.unpack('<h', data[0:2])[0] * self.acc_scale
        ay = struct.unpack('<h', data[2:4])[0] * self.acc_scale
        az = struct.unpack('<h', data[4:6])[0] * self.acc_scale
        
        gx = struct.unpack('<h', data[6:8])[0] * self.gyr_scale
        gy = struct.unpack('<h', data[8:10])[0] * self.gyr_scale
        gz = struct.unpack('<h', data[10:12])[0] * self.gyr_scale
        
        return {
            'acceleration': (ax, ay, az),
            'gyroscope': (gx, gy, gz),
            'temperature': temp
        }
        
    def data_ready(self):
        """檢查數據是否就緒"""
        status = self._read_reg(self.REG_STATUS0)
        return bool(status & 0x01)  # 檢查數據就緒位
        
    def enable_interrupt(self, int_config=0x03):
        """使能中斷"""
        self._write_reg(self.REG_CTRL8, int_config)
        
    def disable_interrupt(self):
        """禁用中斷"""
        self._write_reg(self.REG_CTRL8, 0x00)
        
    def get_device_info(self):
        """獲取設備信息"""
        chip_id = self._read_reg(self.REG_WHO_AM_I)
        revision = self._read_reg(self.REG_REVISION_ID)
        return {
            'chip_id': chip_id,
            'revision': revision
        }
        
    def calibrate_gyroscope(self, samples=1000):
        """陀螺儀校準（計算零點偏移）"""
        print("Gyroscope calibration started. Keep the sensor stationary...")
        
        gx_sum = gy_sum = gz_sum = 0
        
        for i in range(samples):
            gx, gy, gz = self.read_gyroscope()
            gx_sum += gx
            gy_sum += gy
            gz_sum += gz
            time.sleep_ms(10)
            
            if i % 100 == 0:
                print(f"Progress: {i}/{samples}")
                
        self.gyr_offset_x = gx_sum / samples
        self.gyr_offset_y = gy_sum / samples
        self.gyr_offset_z = gz_sum / samples
        
        print(f"Calibration complete!")
        print(f"Gyro offsets: X={self.gyr_offset_x:.3f}, Y={self.gyr_offset_y:.3f}, Z={self.gyr_offset_z:.3f}")
        
        return (self.gyr_offset_x, self.gyr_offset_y, self.gyr_offset_z)
        
    def read_gyroscope_calibrated(self):
        """讀取校準後的陀螺儀數據"""
        gx, gy, gz = self.read_gyroscope()
        
        if hasattr(self, 'gyr_offset_x'):
            gx -= self.gyr_offset_x
            gy -= self.gyr_offset_y
            gz -= self.gyr_offset_z
            
        return (gx, gy, gz)