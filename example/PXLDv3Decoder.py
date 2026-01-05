#!/usr/bin/env python3
"""
PXLD v3 格式解碼器
支持: 每個 LED 固定 4 字節 (RGBW 順序)
      WS2812B [G][R][B] -> [R,G,B,W]
      APA102C [R,G,B] -> [R,G,B,亮度]
      單色 LED -> [0,0,0,亮度]
作者: 基於 PXLD 技術文檔 [1] 及 v3 規範
"""

import struct
import binascii
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

# ==================== 常數定義 ====================
V3_HEADER_SIZE = 64
V3_FRAME_HEADER_SIZE = 32
V3_SLAVE_ENTRY_SIZE = 24
V3_BYTES_PER_LED = 4  # RGBW 固定 4 字節
V3_MAGIC = 'PXLD'
V3_MAJOR_VERSION = 3

# ==================== 資料結構 ====================

@dataclass
class FileHeader:
    """PXLD v3 檔案標頭"""
    magic: str
    major_version: int
    minor_version: int
    fps: int
    total_slaves: int
    total_frames: int
    total_pixels: int
    frame_header_size: int
    slave_entry_size: int
    udp_port: int
    file_crc32: int
    checksum_type: int
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'FileHeader':
        """解析檔案標頭 (64 bytes)"""
        if len(data) < V3_HEADER_SIZE:
            raise ValueError(f"標頭資料不足: {len(data)} bytes")
        
        magic = data[0:4].decode('ascii', errors='ignore')
        if magic != V3_MAGIC:
            raise ValueError(f"無效的 PXLD v3 檔案，magic: {magic}")
        
        major_version = data[4]
        if major_version != V3_MAJOR_VERSION:
            raise ValueError(f"版本不符，預期 v3，得到 v{major_version}")
        
        return cls(
            magic=magic,
            major_version=major_version,
            minor_version=data[5],
            fps=data[6],
            total_slaves=struct.unpack('<H', data[7:9])[0],
            total_frames=struct.unpack('<I', data[9:13])[0],
            total_pixels=struct.unpack('<I', data[13:17])[0],
            frame_header_size=struct.unpack('<H', data[17:19])[0],
            slave_entry_size=struct.unpack('<H', data[19:21])[0],
            udp_port=struct.unpack('<H', data[21:23])[0],
            file_crc32=struct.unpack('<I', data[23:27])[0],
            checksum_type=data[27]
        )
    
    def __str__(self) -> str:
        return (
            f"PXLD v{self.major_version}.{self.minor_version}\n"
            f"  FPS: {self.fps}\n"
            f"  總影格數: {self.total_frames}\n"
            f"  總 Slave 數: {self.total_slaves}\n"
            f"  總 LED 數: {self.total_pixels}\n"
            f"  總通道數: {self.total_pixels * V3_BYTES_PER_LED}\n"
            f"  UDP 埠: {self.udp_port}\n"
            f"  CRC32: 0x{self.file_crc32:08X}\n"
            f"  校驗類型: {self.checksum_type}"
        )

@dataclass
class FrameHeader:
    """影格標頭 (32 bytes)"""
    frame_id: int
    flags: int
    slave_table_size: int
    pixel_data_size: int
    timestamp_ms: float  # 計算得出
    
    @classmethod
    def from_bytes(cls, data: bytes, fps: int) -> 'FrameHeader':
        """解析影格標頭"""
        if len(data) < V3_FRAME_HEADER_SIZE:
            raise ValueError(f"影格標頭資料不足")
        
        frame_id = struct.unpack('<I', data[0:4])[0]
        flags = struct.unpack('<H', data[4:6])[0]
        slave_table_size = struct.unpack('<I', data[8:12])[0]
        pixel_data_size = struct.unpack('<I', data[12:16])[0]
        
        # 計算時間戳 (不儲存在檔案中)
        timestamp_ms = frame_id * (1000.0 / fps) if fps > 0 else 0.0
        
        return cls(
            frame_id=frame_id,
            flags=flags,
            slave_table_size=slave_table_size,
            pixel_data_size=pixel_data_size,
            timestamp_ms=timestamp_ms
        )

@dataclass
class SlaveEntry:
    """從機條目 (24 bytes)"""
    slave_id: int
    flags: int
    channel_start: int  # 1-indexed
    channel_count: int
    pixel_count: int
    data_offset: int
    data_length: int
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'SlaveEntry':
        """解析從機條目"""
        if len(data) < V3_SLAVE_ENTRY_SIZE:
            raise ValueError(f"從機條目資料不足")
        
        return cls(
            slave_id=data[0],
            flags=data[1],
            channel_start=struct.unpack('<H', data[2:4])[0],
            channel_count=struct.unpack('<H', data[4:6])[0],
            pixel_count=struct.unpack('<H', data[6:8])[0],
            data_offset=struct.unpack('<I', data[8:12])[0],
            data_length=struct.unpack('<I', data[12:16])[0]
        )
    
    def __str__(self) -> str:
        return (
            f"Slave {self.slave_id}: "
            f"通道 {self.channel_start}-{self.channel_start + self.channel_count - 1}, "
            f"{self.pixel_count} 個 LED, "
            f"{self.data_length} bytes"
        )

@dataclass
class LED:
    """單個 LED 的資料 (4 bytes RGBW)"""
    r: int
    g: int
    b: int
    w: int
    led_type: str = 'UNKNOWN'
    
    def to_rgb_tuple(self) -> Tuple[int, int, int]:
        """轉換為標準 RGB 元組"""
        return (self.r, self.g, self.b)
    
    def to_rgbw_tuple(self) -> Tuple[int, int, int, int]:
        """轉換為 RGBW 元組"""
        return (self.r, self.g, self.b, self.w)
    
    def __str__(self) -> str:
        if self.led_type == 'STANDARD_LED':
            return f"單色({self.w})"
        else:
            return f"RGB({self.r},{self.g},{self.b}) W={self.w}"

# ==================== 主解碼器 ====================

class PXLDv3Decoder:
    """PXLD v3 格式解碼器"""
    
    def __init__(self, filepath: str, config_path: Optional[str] = None):
        """
        初始化解碼器
        
        Args:
            filepath: PXLD v3 檔案路徑
            config_path: Slave 配置 JSON 檔案路徑 (可選)
        """
        self.filepath = filepath
        self.file = None
        self.file_header: Optional[FileHeader] = None
        self.frame_offsets: List[int] = []
        self.slave_configs: Dict[int, Dict] = {}
        
        # 載入配置檔案
        if config_path:
            self.load_slave_configs(config_path)
        
        # 開啟檔案並解析標頭
        self.open()
    
    def load_slave_configs(self, config_path: str):
        """載入 Slave 配置 JSON [1]"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            if isinstance(config_data, list):
                for slave in config_data:
                    if 'slave_id' in slave:
                        self.slave_configs[slave['slave_id']] = slave
            elif 'slaves' in config_data:
                for slave in config_data['slaves']:
                    if 'slave_id' in slave:
                        self.slave_configs[slave['slave_id']] = slave
            
            print(f"✅ 已載入 {len(self.slave_configs)} 個 Slave 配置")
        except Exception as e:
            print(f"⚠️  無法載入配置檔案: {e}")
    
    def open(self):
        """開啟檔案並解析標頭"""
        self.file = open(self.filepath, 'rb')
        
        # 解析檔案標頭
        header_data = self.file.read(V3_HEADER_SIZE)
        self.file_header = FileHeader.from_bytes(header_data)
        
        # 驗證結構大小
        if self.file_header.frame_header_size != V3_FRAME_HEADER_SIZE:
            raise ValueError(f"不支援的影格標頭大小: {self.file_header.frame_header_size}")
        if self.file_header.slave_entry_size != V3_SLAVE_ENTRY_SIZE:
            raise ValueError(f"不支援的從機條目大小: {self.file_header.slave_entry_size}")
        
        # 驗證 CRC32
        if self.file_header.checksum_type == 1:
            self.verify_crc32()
        
        # 建立影格索引
        self.build_frame_index()
        
        print(f"✅ 檔案開啟成功:")
        print(self.file_header)
    
    def verify_crc32(self):
        """驗證檔案 CRC32"""
        self.file.seek(27)
        file_data = self.file.read()
        calculated_crc32 = binascii.crc32(file_data) & 0xFFFFFFFF
        
        if calculated_crc32 != self.file_header.file_crc32:
            raise ValueError(
                f"CRC32 校驗失敗! "
                f"宣告: 0x{self.file_header.file_crc32:08X}, "
                f"計算: 0x{calculated_crc32:08X}"
            )
        print(f"✅ CRC32 校驗通過: 0x{calculated_crc32:08X}")
    
    def build_frame_index(self):
        """建立影格偏移索引，支援快速隨機存取"""
        print(f"建立影格索引 (總數: {self.file_header.total_frames})...")
        
        self.frame_offsets = []
        current_offset = V3_HEADER_SIZE
        
        for frame_id in range(self.file_header.total_frames):
            self.frame_offsets.append(current_offset)
            
            # 讀取影格標頭以獲取大小資訊
            self.file.seek(current_offset)
            frame_header_data = self.file.read(V3_FRAME_HEADER_SIZE)
            
            if len(frame_header_data) < V3_FRAME_HEADER_SIZE:
                print(f"⚠️  影格 {frame_id} 資料不完整")
                break
            
            slave_table_size = struct.unpack('<I', frame_header_data[8:12])[0]
            pixel_data_size = struct.unpack('<I', frame_header_data[12:16])[0]
            
            # 計算下一個影格的偏移
            frame_size = V3_FRAME_HEADER_SIZE + slave_table_size + pixel_data_size
            current_offset += frame_size
            
            if (frame_id + 1) % 1000 == 0:
                print(f"  索引進度: {frame_id + 1}/{self.file_header.total_frames}")
        
        print(f"✅ 索引完成，共 {len(self.frame_offsets)} 個影格")
    
    def read_frame(self, frame_id: int) -> Dict:
        """
        讀取指定影格的完整資料
        
        Args:
            frame_id: 影格 ID (0-based)
            
        Returns:
            包含標頭、從機表和像素資料的字典
        """
        if frame_id < 0 or frame_id >= len(self.frame_offsets):
            raise ValueError(f"影格 ID {frame_id} 超出範圍 (0-{len(self.frame_offsets)-1})")
        
        # 定位到影格起始位置
        self.file.seek(self.frame_offsets[frame_id])
        
        # 1. 讀取影格標頭
        frame_header_data = self.file.read(V3_FRAME_HEADER_SIZE)
        frame_header = FrameHeader.from_bytes(frame_header_data, self.file_header.fps)
        
        # 2. 讀取從機表
        slave_table_data = self.file.read(frame_header.slave_table_size)
        slave_entries = []
        
        for i in range(self.file_header.total_slaves):
            entry_offset = i * V3_SLAVE_ENTRY_SIZE
            entry_data = slave_table_data[entry_offset:entry_offset + V3_SLAVE_ENTRY_SIZE]
            slave_entry = SlaveEntry.from_bytes(entry_data)
            slave_entries.append(slave_entry)
        
        # 3. 讀取像素資料
        pixel_data = self.file.read(frame_header.pixel_data_size)
        
        return {
            'header': frame_header,
            'slaves': slave_entries,
            'pixel_data': pixel_data
        }
    
    def get_slave_leds(self, frame_data: Dict, slave_id: int) -> List[LED]:
        """
        提取指定 Slave 的 LED 資料
        
        Args:
            frame_data: read_frame() 返回的影格資料
            slave_id: Slave ID
            
        Returns:
            LED 物件列表
        """
        # 找到對應的從機條目
        slave_entry = None
        for entry in frame_data['slaves']:
            if entry.slave_id == slave_id:
                slave_entry = entry
                break
        
        if not slave_entry:
            raise ValueError(f"找不到 Slave {slave_id}")
        
        # 提取該 Slave 的原始資料
        pixel_data = frame_data['pixel_data']
        start = slave_entry.data_offset
        end = start + slave_entry.data_length
        slave_data = pixel_data[start:end]
        
        # 解析每個 LED (每個 LED 固定 4 字節 RGBW)
        leds = []
        config = self.slave_configs.get(slave_id)
        
        if config and 'outputs' in config:
            # 使用配置解析
            led_index = 0
            for output in config['outputs']:
                output_type = output.get('type', 'UNKNOWN')
                count = output.get('count', 0)
                
                for _ in range(count):
                    offset = led_index * V3_BYTES_PER_LED
                    if offset + V3_BYTES_PER_LED > len(slave_data):
                        break
                    
                    r = slave_data[offset]
                    g = slave_data[offset + 1]
                    b = slave_data[offset + 2]
                    w = slave_data[offset + 3]
                    
                    led = LED(r=r, g=g, b=b, w=w, led_type=output_type)
                    leds.append(led)
                    led_index += 1
        else:
            # 通用解析（無配置）
            for i in range(0, len(slave_data), V3_BYTES_PER_LED):
                if i + V3_BYTES_PER_LED > len(slave_data):
                    break
                
                r = slave_data[i]
                g = slave_data[i + 1]
                b = slave_data[i + 2]
                w = slave_data[i + 3]
                
                led = LED(r=r, g=g, b=b, w=w)
                leds.append(led)
        
        return leds
    
    def get_all_leds(self, frame_data: Dict) -> Dict[int, List[LED]]:
        """
        提取影格中所有 Slave 的 LED 資料
        
        Args:
            frame_data: read_frame() 返回的影格資料
            
        Returns:
            字典，key 為 slave_id，value 為 LED 列表
        """
        all_leds = {}
        for slave_entry in frame_data['slaves']:
            leds = self.get_slave_leds(frame_data, slave_entry.slave_id)
            all_leds[slave_entry.slave_id] = leds
        return all_leds
    
    def analyze_slave(self, slave_id: int):
        """分析並顯示 Slave 的詳細資訊"""
        print(f"\n{'='*60}")
        print(f"Slave {slave_id} 分析")
        print(f"{'='*60}")
        
        # 讀取第一個影格以獲取結構資訊
        frame_data = self.read_frame(0)
        leds = self.get_slave_leds(frame_data, slave_id)
        
        # 取得配置
        config = self.slave_configs.get(slave_id)
        
        if config:
            print(f"名稱: {config.get('name', 'N/A')}")
            print(f"描述: {config.get('description', 'N/A')}")
            print(f"\nOutput 配置:")
            
            led_index = 0
            for output in config.get('outputs', []):
                print(f"\n  {output.get('label', 'unknown')}:")
                print(f"    類型: {output.get('type', 'UNKNOWN')}")
                print(f"    數量: {output.get('count', 0)}")
                print(f"    描述: {output.get('description', 'N/A')}")
                
                # 顯示前3個LED的樣本資料
                count = output.get('count', 0)
                print(f"    前 3 個 LED 樣本:")
                for i in range(min(3, count)):
                    if led_index < len(leds):
                        print(f"      LED {i}: {leds[led_index]}")
                        led_index += 1
        else:
            print("⚠️  沒有配置檔案，顯示通用資訊")
            print(f"總 LED 數: {len(leds)}")
            print(f"前 5 個 LED 樣本:")
            for i in range(min(5, len(leds))):
                print(f"  LED {i}: {leds[i]}")
    
    def close(self):
        """關閉檔案"""
        if self.file:
            self.file.close()
            self.file = None
            print("✅ 檔案已關閉")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

# ==================== 使用範例 ====================

def main():
    """主程式範例"""
    with PXLDv3Decoder('/Users/tungkinlee/Downloads/demo_packet_slave0v3.pxld') as decoder:
        # 讀取第 100 個影格
        frame_data = decoder.read_frame(100)
        
        # 提取 Slave 0 的 LED 資料
        leds = decoder.get_slave_leds(frame_data, slave_id=0)
        
        # 處理每個 LED
        for led in leds:
            if led.led_type == 'STANDARD_LED':
                # 單色 LED，使用 W 通道
                print(f"單色 LED 亮度: {led.w}")
                print(f"單色 LED 亮度: {led}")
            else:
                # RGB LED
                r, g, b = led.to_rgb_tuple()
                print(f"RGB: ({r}, {g}, {b}), 亮度: {led.w}")
        
        # 提取所有 Slave 的資料
        all_leds = decoder.get_all_leds(frame_data)
        for slave_id, leds in all_leds.items():
            print(f"Slave {slave_id}: {len(leds)} 個 LED")

if __name__ == "__main__":
    import sys
    sys.exit(main())