#!/usr/bin/env python3
"""
PXLD v3 解碼器 - 簡化版
使用風格: context manager + 直觀的 API
"""

import struct
import binascii
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

# ==================== 常數 ====================
V3_HEADER_SIZE = 64
V3_FRAME_HEADER_SIZE = 32
V3_SLAVE_ENTRY_SIZE = 24
V3_BYTES_PER_LED = 4
V3_MAGIC = 'PXLD'
V3_MAJOR_VERSION = 3

# ==================== 資料結構 ====================

@dataclass
class FileHeader:
    magic: str
    major_version: int
    minor_version: int
    fps: int
    total_slaves: int
    total_frames: int
    total_pixels: int
    udp_port: int
    file_crc32: int
    
    @classmethod
    def from_bytes(cls, data: bytes):
        return cls(
            magic=data[0:4].decode('ascii'),
            major_version=data[4],
            minor_version=data[5],
            fps=data[6],
            total_slaves=struct.unpack('<H', data[7:9])[0],
            total_frames=struct.unpack('<I', data[9:13])[0],
            total_pixels=struct.unpack('<I', data[13:17])[0],
            udp_port=struct.unpack('<H', data[21:23])[0],
            file_crc32=struct.unpack('<I', data[23:27])[0]
        )

@dataclass
class LED:
    """單個 LED（固定 4 bytes: RGBW）"""
    r: int
    g: int
    b: int
    w: int
    led_type: str = 'RGB'
    
    def to_rgb_tuple(self) -> Tuple[int, int, int]:
        return (self.r, self.g, self.b)
    
    def to_rgbw_tuple(self) -> Tuple[int, int, int, int]:
        return (self.r, self.g, self.b, self.w)
    
    def __str__(self) -> str:
        if self.led_type == 'MONO':
            return f"MONO(亮度={self.w})"
        return f"RGB({self.r},{self.g},{self.b})"

# ==================== 解碼器 ====================

class PXLDv3Decoder:
    """PXLD v3 解碼器"""
    
    def __init__(self, filepath: str, config_path: Optional[str] = None):
        self.filepath = filepath
        self.config_path = config_path
        self.file = None
        self.file_header = None
        self.frame_offsets = []
        self.slave_configs = {}
        
        self._open_file()
        if config_path:
            self._load_config()
    
    def _open_file(self):
        """開啟並解析檔案"""
        self.file = open(self.filepath, 'rb')
        
        # 讀取標頭
        header_data = self.file.read(V3_HEADER_SIZE)
        self.file_header = FileHeader.from_bytes(header_data)
        
        if self.file_header.magic != V3_MAGIC:
            raise ValueError("不是有效的 PXLD v3 檔案")
        
        # 建立影格索引
        self._build_frame_index()
        
        print(f"✅ 檔案載入成功")
        print(f"   FPS: {self.file_header.fps}")
        print(f"   影格數: {self.file_header.total_frames}")
        print(f"   Slave 數: {self.file_header.total_slaves}")
        print(f"   LED 總數: {self.file_header.total_pixels}")
    
    def _load_config(self):
        """載入配置檔案"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            for slave in config_data.get('slaves', []):
                slave_id = slave.get('slave_id')
                if slave_id is not None:
                    self.slave_configs[slave_id] = slave
            
            print(f"✅ 配置載入成功: {len(self.slave_configs)} 個 Slave")
        except Exception as e:
            print(f"⚠️  配置載入失敗: {e}")
    
    def _build_frame_index(self):
        """建立影格索引"""
        self.frame_offsets = []
        current_offset = V3_HEADER_SIZE
        
        for _ in range(self.file_header.total_frames):
            self.frame_offsets.append(current_offset)
            
            self.file.seek(current_offset)
            frame_header = self.file.read(V3_FRAME_HEADER_SIZE)
            
            slave_table_size = struct.unpack('<I', frame_header[8:12])[0]
            pixel_data_size = struct.unpack('<I', frame_header[12:16])[0]
            
            current_offset += V3_FRAME_HEADER_SIZE + slave_table_size + pixel_data_size
    
    def read_frame(self, frame_id: int) -> Dict:
        """讀取指定影格"""
        if frame_id >= len(self.frame_offsets):
            raise ValueError(f"影格 {frame_id} 超出範圍")
        
        self.file.seek(self.frame_offsets[frame_id])
        
        # 讀取標頭
        frame_header = self.file.read(V3_FRAME_HEADER_SIZE)
        slave_table_size = struct.unpack('<I', frame_header[8:12])[0]
        pixel_data_size = struct.unpack('<I', frame_header[12:16])[0]
        
        # 讀取 Slave 表
        slave_table = self.file.read(slave_table_size)
        slaves = []
        for i in range(self.file_header.total_slaves):
            offset = i * V3_SLAVE_ENTRY_SIZE
            entry = slave_table[offset:offset + V3_SLAVE_ENTRY_SIZE]
            slaves.append({
                'slave_id': entry[0],
                'pixel_count': struct.unpack('<H', entry[6:8])[0],
                'data_offset': struct.unpack('<I', entry[8:12])[0],
                'data_length': struct.unpack('<I', entry[12:16])[0]
            })
        
        # 讀取像素資料
        pixel_data = self.file.read(pixel_data_size)
        
        return {
            'frame_id': struct.unpack('<I', frame_header[0:4])[0],
            'timestamp_ms': struct.unpack('<I', frame_header[0:4])[0] * (1000 / self.file_header.fps),
            'slaves': slaves,
            'pixel_data': pixel_data
        }
    
    def get_slave_leds(self, frame_data: Dict, slave_id: int) -> List[LED]:
        """提取指定 Slave 的 LED 資料"""
        slave = next((s for s in frame_data['slaves'] if s['slave_id'] == slave_id), None)
        if not slave:
            raise ValueError(f"找不到 Slave {slave_id}")
        
        # 提取該 Slave 的資料
        pixel_data = frame_data['pixel_data']
        start = slave['data_offset']
        end = start + slave['data_length']
        slave_data = pixel_data[start:end]
        
        leds = []
        config = self.slave_configs.get(slave_id)
        
        # 解析 LED（每個 4 bytes）
        if config and 'outputs' in config:
            # 使用配置
            led_index = 0
            for output in config['outputs']:
                led_type = output.get('type', 'RGB')
                count = output.get('count', 0)
                
                for _ in range(count):
                    offset = led_index * V3_BYTES_PER_LED
                    if offset + V3_BYTES_PER_LED <= len(slave_data):
                        led = LED(
                            r=slave_data[offset],
                            g=slave_data[offset + 1],
                            b=slave_data[offset + 2],
                            w=slave_data[offset + 3],
                            led_type=led_type
                        )
                        leds.append(led)
                        led_index += 1
        else:
            # 無配置，全部視為 RGB
            for i in range(0, len(slave_data), V3_BYTES_PER_LED):
                if i + V3_BYTES_PER_LED <= len(slave_data):
                    led = LED(
                        r=slave_data[i],
                        g=slave_data[i + 1],
                        b=slave_data[i + 2],
                        w=slave_data[i + 3]
                    )
                    leds.append(led)
        
        return leds
    
    def get_all_leds(self, frame_data: Dict) -> Dict[int, List[LED]]:
        """提取所有 Slave 的 LED"""
        all_leds = {}
        for slave in frame_data['slaves']:
            leds = self.get_slave_leds(frame_data, slave['slave_id'])
            all_leds[slave['slave_id']] = leds
        return all_leds
    
    def close(self):
        """關閉檔案"""
        if self.file:
            self.file.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

# ==================== 使用範例 ====================

def main():
    """主程式範例"""
    # 可選：載入配置檔案以區分 LED 類型
    with PXLDv3Decoder('/Users/tungkinlee/Downloads/demo_packet_slave0v3.pxld', 
                       config_path='/Users/tungkinlee/Downloads/slave_config.json') as decoder:
        
        # 讀取第 100 個影格
        frame_data = decoder.read_frame(100)
        
        print(f"\n影格 {frame_data['frame_id']}")
        print(f"時間: {frame_data['timestamp_ms']:.2f} ms\n")
        
        # 提取 Slave 0 的 LED 資料
        leds = decoder.get_slave_leds(frame_data, slave_id=0)
        
        print(f"Slave 0 共有 {len(leds)} 個 LED\n")
        
        # 處理每個 LED
        for i, led in enumerate(leds[:10]):  # 只顯示前 10 個
            if led.led_type == 'MONO':
                print(f"LED {i}: 單色 LED 亮度 = {led.w}")
                
            else:
                print(f"LED {i}: RGB({led.r}, {led.g}, {led.b})")

                # 處理每個 LED
        for i, led in enumerate(leds):  # 只顯示前 10 個
            if led.led_type == 'MONO':
                print(f"LED {i}: 單色 LED 亮度 = {led.w}")
                print(f"LED {i}: 單色 LED 亮度 = {led}")
            else:
                print(f"LED {i}: RGB({led.r}, {led.g}, {led.b})")
                print(f"LED {i}: RGB({led})")
        
        # 提取所有 Slave 的資料
        print("\n所有 Slave LED 統計:")
        all_leds = decoder.get_all_leds(frame_data)
        for slave_id, leds in all_leds.items():
            print(f"  Slave {slave_id}: {len(leds)} 個 LED")

if __name__ == "__main__":
    main()