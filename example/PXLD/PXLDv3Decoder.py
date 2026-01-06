#!/usr/bin/env python3
"""
PXLD v3 解碼器 - 極簡版
功能: Frame → Slave → LED 三層精準訪問
不依賴配置文件,純粹基於二進制格式解析 [1]
"""
import struct
from typing import Dict, List, Tuple
from dataclasses import dataclass

# ==================== 常數 ====================
V3_HEADER_SIZE = 64
V3_FRAME_HEADER_SIZE = 32
V3_SLAVE_ENTRY_SIZE = 24
V3_BYTES_PER_LED = 4  # 固定 RGBW 4 bytes [1]

# ==================== 資料結構 ====================
@dataclass
class LED:
    """單個 LED (固定 4 bytes: RGBW) [1]"""
    r: int
    g: int
    b: int
    w: int
    
    def __repr__(self) -> str:
        return f"LED(r={self.r}, g={self.g}, b={self.b}, w={self.w})"
    
    def to_tuple(self) -> Tuple[int, int, int, int]:
        """返回 (R, G, B, W) 元組"""
        return (self.r, self.g, self.b, self.w)

# ==================== 解碼器 ====================
class PXLDv3Decoder:
    """PXLD v3 解碼器 - 三層訪問架構"""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.file = None
        self.fps = 0
        self.total_frames = 0
        self.total_slaves = 0
        self.total_pixels = 0
        self.frame_offsets = []
        
        self._open_and_index()
    
    def _open_and_index(self):
        """開啟檔案並建立索引 [1]"""
        self.file = open(self.filepath, 'rb')
        
        # 讀取 FileHeader (64 bytes)
        header = self.file.read(V3_HEADER_SIZE)
        
        # 驗證 Magic
        magic = header[0:4].decode('ascii')
        if magic != 'PXLD':
            raise ValueError("不是有效的 PXLD v3 檔案")
        
        # 解析 Header [1]
        major_version = header[4]
        if major_version != 3:
            raise ValueError(f"不支援版本 {major_version},僅支援 v3")
        
        self.fps = header[6]
        self.total_slaves = struct.unpack('<H', header[7:9])[0]
        self.total_frames = struct.unpack('<I', header[9:13])[0]
        self.total_pixels = struct.unpack('<I', header[13:17])[0]
        
        # 建立影格索引
        self._build_frame_index()
        
        print(f"✅ 檔案載入成功")
        print(f"   FPS: {self.fps}")
        print(f"   總影格: {self.total_frames}")
        print(f"   總 Slave: {self.total_slaves}")
        print(f"   總 LED: {self.total_pixels}")
    
    def _build_frame_index(self):
        """建立所有影格的偏移索引 [1]"""
        self.frame_offsets = []
        current_offset = V3_HEADER_SIZE
        
        for _ in range(self.total_frames):
            self.frame_offsets.append(current_offset)
            
            # 讀取 FrameHeader 計算下一個影格位置
            self.file.seek(current_offset)
            frame_header = self.file.read(V3_FRAME_HEADER_SIZE)
            
            slave_table_size = struct.unpack('<I', frame_header[8:12])[0]
            pixel_data_size = struct.unpack('<I', frame_header[12:16])[0]
            
            current_offset += V3_FRAME_HEADER_SIZE + slave_table_size + pixel_data_size
    
    # ==================== 層級 1: Frame 訪問 ====================
    
    def get_frame(self, frame_id: int) -> Dict:
        """
        獲取完整影格資料
        
        返回:
            {
                'frame_id': int,
                'timestamp_ms': float,
                'slaves': List[Dict],  # 所有 Slave 元資料
                'pixel_data': bytes    # 原始像素資料
            }
        """
        if frame_id >= len(self.frame_offsets):
            raise ValueError(f"影格 {frame_id} 超出範圍 (總共 {len(self.frame_offsets)} 個)")
        
        self.file.seek(self.frame_offsets[frame_id])
        
        # 讀取 FrameHeader [1]
        frame_header = self.file.read(V3_FRAME_HEADER_SIZE)
        actual_frame_id = struct.unpack('<I', frame_header[0:4])[0]
        slave_table_size = struct.unpack('<I', frame_header[8:12])[0]
        pixel_data_size = struct.unpack('<I', frame_header[12:16])[0]
        
        # 讀取 SlaveTable [1]
        slave_table_data = self.file.read(slave_table_size)
        slaves = []
        for i in range(self.total_slaves):
            offset = i * V3_SLAVE_ENTRY_SIZE
            entry = slave_table_data[offset:offset + V3_SLAVE_ENTRY_SIZE]
            
            slaves.append({
                'slave_id': entry[0],
                'channel_start': struct.unpack('<H', entry[2:4])[0],
                'channel_count': struct.unpack('<H', entry[4:6])[0],
                'pixel_count': struct.unpack('<H', entry[6:8])[0],
                'data_offset': struct.unpack('<I', entry[8:12])[0],
                'data_length': struct.unpack('<I', entry[12:16])[0]
            })
        
        # 讀取 PixelData [1]
        pixel_data = self.file.read(pixel_data_size)
        
        return {
            'frame_id': actual_frame_id,
            'timestamp_ms': (actual_frame_id * 1000) / self.fps if self.fps > 0 else 0,
            'slaves': slaves,
            'pixel_data': pixel_data
        }
    
    # ==================== 層級 2: Slave 訪問 ====================
    
    def get_slave_data(self, frame_data: Dict, slave_id: int) -> bytes:
        """
        從影格中提取指定 Slave 的原始資料
        
        返回: bytes (該 Slave 的所有像素資料)
        """
        slave = next((s for s in frame_data['slaves'] if s['slave_id'] == slave_id), None)
        if not slave:
            raise ValueError(f"找不到 Slave {slave_id}")
        
        start = slave['data_offset']
        end = start + slave['data_length']
        return frame_data['pixel_data'][start:end]
    
    def get_slave_leds(self, frame_data: Dict, slave_id: int) -> List[LED]:
        """
        從影格中提取指定 Slave 的所有 LED
        
        返回: List[LED]
        """
        slave_data = self.get_slave_data(frame_data, slave_id)
        
        leds = []
        for i in range(0, len(slave_data), V3_BYTES_PER_LED):
            if i + V3_BYTES_PER_LED <= len(slave_data):
                leds.append(LED(
                    r=slave_data[i],
                    g=slave_data[i + 1],
                    b=slave_data[i + 2],
                    w=slave_data[i + 3]
                ))
        
        return leds
    
    # ==================== 層級 3: LED 訪問 ====================
    
    def get_led(self, frame_data: Dict, slave_id: int, led_index: int) -> LED:
        """
        從影格中提取指定 Slave 的特定 LED
        
        參數:
            frame_data: 影格資料
            slave_id: Slave ID
            led_index: LED 索引 (0-based)
        
        返回: LED 物件
        """
        slave_data = self.get_slave_data(frame_data, slave_id)
        
        offset = led_index * V3_BYTES_PER_LED
        if offset + V3_BYTES_PER_LED > len(slave_data):
            raise ValueError(f"LED 索引 {led_index} 超出範圍")
        
        return LED(
            r=slave_data[offset],
            g=slave_data[offset + 1],
            b=slave_data[offset + 2],
            w=slave_data[offset + 3]
        )
    
    # ==================== 便捷方法 ====================
    
    def get_all_slaves(self, frame_data: Dict) -> Dict[int, List[LED]]:
        """獲取影格中所有 Slave 的 LED 資料"""
        return {
            slave['slave_id']: self.get_slave_leds(frame_data, slave['slave_id'])
            for slave in frame_data['slaves']
        }
    
    def close(self):
        """關閉檔案"""
        if self.file:
            self.file.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

# ==================== 使用範例 ====================
if __name__ == "__main__":
    filepath = r'/Users/tungkinlee/Downloads/demo_packet_slave0_v3.pxld'
    
    with PXLDv3Decoder(filepath) as decoder:
        
        # ===== 層級 1: 獲取完整影格 =====
        frame = decoder.get_frame(100)
        print(f"\n影格 {frame['frame_id']}, 時間: {frame['timestamp_ms']:.2f} ms")
        print(f"包含 {len(frame['slaves'])} 個 Slave")
        
        # ===== 層級 2: 獲取指定 Slave 的所有 LED =====
        slave_id = 0
        leds = decoder.get_slave_leds(frame, slave_id)
        print(f"\nSlave {slave_id} 共有 {len(leds)} 個 LED")
        
        # 顯示前 10 個 LED
        for i, led in enumerate(leds):
            print(f"  LED {i}: {led.to_tuple()}")
        
        # ===== 層級 3: 獲取特定 LED =====
        led_index = 5
        led = decoder.get_led(frame, slave_id, led_index)
        print(f"\nSlave {slave_id}, LED {led_index}: {led}")
        
        # ===== 獲取所有 Slave 的資料 =====
        all_slaves = decoder.get_all_slaves(frame)
        print(f"\n所有 Slave 統計:")
        for sid, leds in all_slaves.items():
            print(f"  Slave {sid}: {len(leds)} 個 LED")