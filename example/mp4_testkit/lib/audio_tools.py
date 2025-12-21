import machine
import time
from machine import I2S, Pin
import gc
import math


class AudioBuffer:
    def __init__(self, i2s_device, buffer_size=512, history_size=15, beat_threshold=1.5, debug=False):
        """
        初始化节拍检测器
        
        参数:
        i2s_device: 配置好的I2S设备对象
        buffer_size: 音频缓冲区大小(样本数) - 建议512-1024
        history_size: 能量历史记录大小
        beat_threshold: 节拍检测灵敏度阈值(乘数)
        debug: 是否启用调试输出
        """
        self.i2s = i2s_device
        self.buffer_size = buffer_size
        self.history_size = history_size
        self.beat_threshold = beat_threshold
        self.debug = debug
        self.active = True
        
        # 音频缓冲区 (双缓冲)
        self.buffer1 = bytearray(buffer_size * 4)  # 立体声: 4字节/样本
        self.buffer2 = bytearray(buffer_size * 4)
        self.current_buffer = self.buffer1
        self.processing_buffer = None
        
        # 节拍检测状态
        self.energy_history = []
        self.beat_detected = False
        self.last_beat_time = 0
        self.bpm = 0
        self.beat_count = 0
        self.start_time = time.ticks_ms()
        self.last_update_time = 0
        self.energy = 0
        self.energy_1 = 0.0
        self.avg_energy = 0
        self.threshold = 0
        self.callback_count = 0
        self.process_count = 0
        
        # 回调状态
        self.new_data_available = False
        self.processing_complete = True
        self.read_in_progress = False
        
        # 设置IRQ回调
        self.i2s.irq(self.i2s_callback)
        
        # 启动第一个读取
        self.start_reading()
        
        if self.debug:
            print("[初始化] 节拍检测器已创建")
            print(f"  缓冲区大小: {buffer_size} 样本 ({len(self.buffer1)} 字节)")
#             print(f"  采样率: {self.i2s.rate} Hz")
#             print(f"  位深度: {self.i2s.bits} 位")
#             print(f"  声道: {'立体声' if self.i2s.format == I2S.STEREO else '单声道'}")

    def start_reading(self):
        """启动非阻塞读取"""
        if not self.read_in_progress and self.processing_complete:
            try:
                self.read_in_progress = True
                self.i2s.readinto(self.current_buffer)
                if self.debug:
                    print(f"[读取启动] 缓冲区: {'1' if self.current_buffer is self.buffer1 else '2'}")
            except Exception as e:
                self.read_in_progress = False
                if self.debug:
                    print(f"[错误] 读取启动失败: {e}")
    
    def i2s_callback(self, arg):
        """I2S中断回调函数"""
        if not self.active:
            return
            
        self.callback_count += 1
        self.read_in_progress = False
        
        # 标记有新数据可用
        self.new_data_available = True
        
        # 切换缓冲区
        if self.current_buffer is self.buffer1:
            self.processing_buffer = self.buffer1
            self.current_buffer = self.buffer2
        else:
            self.processing_buffer = self.buffer2
            self.current_buffer = self.buffer1
        
        if self.debug:
            print(f"[回调] #{self.callback_count} 新数据可用, 缓冲区: {'1' if self.processing_buffer is self.buffer1 else '2'}")
        
        # 启动下一个读取
        self.start_reading()
    
    def convert_stereo_to_mono(self, data):
        """将立体声数据转换为单声道（取平均值）"""
        # 优化版本 - 减少内存分配
        mono_samples = [0] * (len(data) // 4)
        
        for i in range(0, len(data), 4):
            # 左声道（小端序）
            left_sample = (data[i+1] << 8) | data[i]
            if left_sample >= 0x8000:
                left_sample -= 0x10000
            
            # 右声道（小端序）
            right_sample = (data[i+3] << 8) | data[i+2]
            if right_sample >= 0x8000:
                right_sample -= 0x10000
            
            # 计算平均值作为单声道样本
            mono_samples[i//4] = (left_sample + right_sample) // 2
        
        return mono_samples
    
    def calculate_energy(self, samples):
        """计算音频样本的能量"""
        energy = 0
        for sample in samples:
            energy += abs(sample)
        return energy
    
    def detect_beat(self):
        """检测节拍并更新状态"""
        if not self.new_data_available or not self.active:
            return False
            
        if self.debug:
            start_time = time.ticks_ms()
        
        try:
            # 处理新数据
            mono_samples = self.convert_stereo_to_mono(self.processing_buffer)
            self.energy = self.calculate_energy(mono_samples)
            self.energy_1 = max(0.0, min(1.0,  self.energy/3355340))

            self.new_data_available = False
            
            # 更新能量历史
            self.energy_history.append(self.energy)
            if len(self.energy_history) > self.history_size:
                self.energy_history.pop(0)
            
            # 计算移动平均
            if self.energy_history:
                self.avg_energy = sum(self.energy_history) / len(self.energy_history)
            else:
                self.avg_energy = 0
            
            # 计算动态阈值
            self.threshold = self.avg_energy * self.beat_threshold if self.avg_energy > 0 else 1000
            
            # 检测节拍
            current_time = time.ticks_ms()
            self.beat_detected = False
            
            if self.energy > self.threshold:
                # 防抖动 - 最小节拍间隔100ms
                if time.ticks_diff(current_time, self.last_beat_time) > 100:  
                    self.beat_detected = True
                    self.last_beat_time = current_time
                    self.beat_count += 1
                    
                    # 每10个节拍计算一次BPM
                    if self.beat_count >= 10:
                        elapsed_time = time.ticks_diff(current_time, self.start_time) / 1000.0  # 转为秒
                        if elapsed_time > 0:
                            self.bpm = int((self.beat_count / elapsed_time) * 60)
                        self.beat_count = 0
                        self.start_time = current_time
            
            # 标记处理完成
            self.processing_complete = True
            self.last_update_time = current_time
            self.process_count += 1
            
            if self.debug:
                process_time = time.ticks_diff(time.ticks_ms(), start_time)
                print(f"[处理] #{self.process_count} 完成, 耗时: {process_time} ms")
                print(f"  能量: {self.energy}, 平均: {self.avg_energy:.1f}, 阈值: {self.threshold:.1f}")
                print(f"  节拍: {'是' if self.beat_detected else '否'}, BPM: {self.bpm}")
            
            return True
        except Exception as e:
            if self.debug:
                print(f"[错误] 处理失败: {e}")
            return False
    
    def get_beat_info(self):
        """获取节拍信息"""
        return {
            "timestamp": self.last_update_time,
            "energy": self.energy,
            "energy_1": self.energy_1,
            "avg_energy": self.avg_energy,
            "threshold": self.threshold,
            "beat_detected": self.beat_detected,
            "bpm": self.bpm,
            "callback_count": self.callback_count,
            "process_count": self.process_count
        }
    
    def get_beat_status(self):
        """获取简化的节拍状态"""
        return self.beat_detected
    
    def get_bpm(self):
        """获取当前BPM"""
        return self.bpm
    
    def deinit(self):
        """释放资源"""
        self.active = False
        self.i2s.irq(None)  # 移除回调
        time.sleep_ms(100)   # 等待可能的回调完成
        self.i2s.deinit()
        if self.debug:
            print("[关闭] 节拍检测器已释放资源")