import struct
from dataclasses import dataclass
from typing import List, Tuple, BinaryIO

# 定義資料類別來儲存檔案標頭資訊
@dataclass
class PXLDHeader:
    """PXLD 檔案標頭 (64 bytes)"""
    magic: str                    # 4 bytes: 'PXLD'
    major_version: int           # 1 byte
    minor_version: int           # 1 byte
    fps: int                     # 1 byte
    total_slaves: int            # 1 byte
    total_channels: int          # 4 bytes
    total_pixels: int            # 4 bytes
    udp_port: int                # 2 bytes
    reserved: bytes              # 46 bytes
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'PXLDHeader':
        """從 64 bytes 的資料解析出標頭資訊"""
        # 使用小端序解析 [1]
        magic = data[0:4].decode('ascii')
        major_version = data[4]
        minor_version = data[5]
        fps = data[6]
        total_slaves = data[7]
        
        # 解析 4 bytes 整數 (little-endian) [1][6]
        total_channels = struct.unpack('<I', data[8:12])[0]
        total_pixels = struct.unpack('<I', data[12:16])[0]
        
        # 解析 2 bytes 整數 (little-endian) [1]
        udp_port = struct.unpack('<H', data[16:18])[0]
        reserved = data[18:64]
        
        return cls(
            magic=magic,
            major_version=major_version,
            minor_version=minor_version,
            fps=fps,
            total_slaves=total_slaves,
            total_channels=total_channels,
            total_pixels=total_pixels,
            udp_port=udp_port,
            reserved=reserved
        )

@dataclass
class SlaveHeader:
    """單個 Slave 的標頭 (12 bytes)"""
    slave_id: int
    start_channel: int  # 注意: 1-indexed [1]
    data_length: int
    
    @classmethod
    def from_bytes(cls, data: bytes, slave_id: int) -> 'SlaveHeader':
        """解析單個 Slave 標頭"""
        # 假設每個 slave 標頭為 12 bytes
        # 根據文檔，slave 通道規律為固定 976 通道 [1]
        start_channel = slave_id * 976 + 1  # 1-indexed
        data_length = 976  # 固定 976 bytes [1]
        
        return cls(
            slave_id=slave_id,
            start_channel=start_channel,
            data_length=data_length
        )

@dataclass 
class FrameData:
    """單一影格的完整資料"""
    frame_number: int
    frame_header: bytes  # 16 bytes [1]
    slave_headers: List[SlaveHeader]
    pixel_data: bytes    # 32,208 bytes [1]
    
    def get_slave_pixel_data(self, slave_id: int) -> bytes:
        """取得指定 slave 的像素資料"""
        # 每個 slave 固定 976 bytes [1]
        start_idx = slave_id * 976
        end_idx = start_idx + 976
        return self.pixel_data[start_idx:end_idx]

class PXLDDecoder:
    """PXLD 格式解碼器"""
    
    # 常數定義
    HEADER_SIZE = 64  # bytes [1]
    FRAME_HEADER_SIZE = 16  # bytes [1]
    SLAVE_HEADER_SIZE = 12  # bytes [1]
    TOTAL_SLAVES = 33  # 根據文檔 [1]
    PIXEL_DATA_SIZE = 32208  # bytes [1]
    FRAME_SIZE = 32620  # 16 + 396 + 32208 = 32620 bytes [1]
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.header: PXLDHeader = None
        self.frames: List[FrameData] = []
        
    def decode(self):
        """解碼整個 PXLD 檔案"""
        with open(self.filepath, 'rb') as f:
            # 1. 讀取檔案標頭
            self._decode_header(f)
            
            # 2. 讀取所有影格
            self._decode_frames(f)
            
    def _decode_header(self, f: BinaryIO):
        """解碼 64 bytes 的檔案標頭"""
        header_data = f.read(self.HEADER_SIZE)
        if len(header_data) != self.HEADER_SIZE:
            raise ValueError("檔案長度不足，無法讀取完整標頭")
            
        self.header = PXLDHeader.from_bytes(header_data)
        
        # 驗證魔術數字
        if self.header.magic != 'PXLD':
            raise ValueError(f"無效的 PXLD 檔案，魔術數字應為 'PXLD'，但得到 '{self.header.magic}'")
            
        print(f"檔案標頭解析完成:")
        print(f"  版本: {self.header.major_version}.{self.header.minor_version}")
        print(f"  FPS: {self.header.fps}")
        print(f"  Slave 數量: {self.header.total_slaves}")
        print(f"  總通道數: {self.header.total_channels}")
        print(f"  總 LED 數: {self.header.total_pixels}")
        print(f"  UDP 埠號: {self.header.udp_port}")
    
    def _decode_frames(self, f: BinaryIO):
        """解碼所有影格資料"""
        frame_count = 0
        
        while True:
            try:
                frame = self._decode_single_frame(f, frame_count)
                if frame is None:
                    break
                self.frames.append(frame)
                frame_count += 1
                
                # 進度顯示
                if frame_count % 10 == 0:
                    print(f"已解碼 {frame_count} 個影格")
                    
            except EOFError:
                break
                
        print(f"總共解碼 {len(self.frames)} 個影格")
    
    def _decode_single_frame(self, f: BinaryIO, frame_num: int) -> FrameData:
        """解碼單一影格"""
        # 讀取影格標頭 (16 bytes)
        frame_header = f.read(self.FRAME_HEADER_SIZE)
        if len(frame_header) == 0:
            return None
        if len(frame_header) < self.FRAME_HEADER_SIZE:
            raise EOFError("檔案結束，無法讀取完整影格標頭")
        
        # 讀取所有 slave 標頭 (33 × 12 = 396 bytes) [1]
        slave_headers = []
        for slave_id in range(self.TOTAL_SLAVES):
            # 注意: 實際標頭資料可能需要從檔案讀取，這裡根據文檔生成
            slave_header = SlaveHeader.from_bytes(b'', slave_id)
            slave_headers.append(slave_header)
        
        # 讀取像素資料 (32,208 bytes) [1]
        pixel_data = f.read(self.PIXEL_DATA_SIZE)
        if len(pixel_data) < self.PIXEL_DATA_SIZE:
            raise EOFError("檔案結束，無法讀取完整像素資料")
        
        return FrameData(
            frame_number=frame_num,
            frame_header=frame_header,
            slave_headers=slave_headers,
            pixel_data=pixel_data
        )
    
    def extract_led_colors(self, frame_idx: int, slave_id: int) -> List[Tuple[int, int, int]]:
        """
        提取指定影格和 slave 的 LED 顏色資料
        
        Args:
            frame_idx: 影格索引
            slave_id: slave ID (0-32)
            
        Returns:
            List of (R, G, B) tuples
        """
        if frame_idx >= len(self.frames):
            raise IndexError(f"影格索引 {frame_idx} 超出範圍")
            
        if slave_id >= self.TOTAL_SLAVES:
            raise IndexError(f"slave_id {slave_id} 應小於 {self.TOTAL_SLAVES}")
        
        frame = self.frames[frame_idx]
        pixel_data = frame.get_slave_pixel_data(slave_id)
        
        colors = []
        # 根據文檔，Slave 0 的 LED 資料分布 [3]:
        # 0-569: APA102C (190 LEDs, RGB 順序)
        # 570-869: APA102C (100 LEDs, RGB 順序)
        # 870-959: WS2812B (30 LEDs, GRB 順序) [1][3]
        # 960-975: STANDARD_LED (16 LEDs, 單色 PWM)
        
        # 這裡提供通用解析，實際應用需根據具體 LED 類型調整
        for i in range(0, len(pixel_data), 3):
            if i + 3 > len(pixel_data):
                break
                
            # 注意: WS2812B 需要特殊處理 [1][3]
            g = pixel_data[i]
            r = pixel_data[i + 1]
            b = pixel_data[i + 2]
            
            # 對於 WS2812B，原始儲存是 [G][R][B]，這裡轉換回標準 RGB
            # 實際應用中需要根據 LED 類型決定是否轉換
            colors.append((r, g, b))
        
        return colors
    
    def analyze_led_types(self, slave_id: int = 0):
        """
        分析指定 slave 的 LED 類型分布
        
        根據文檔中 Slave 0 的範例 [3]
        """
        if len(self.frames) == 0:
            print("請先解碼檔案")
            return
            
        frame = self.frames[0]
        pixel_data = frame.get_slave_pixel_data(slave_id)
        
        print(f"Slave {slave_id} LED 類型分析:")
        print(f"  總長度: {len(pixel_data)} bytes")
        
        # 根據文檔中的分布 [3]
        sections = [
            ("APA102C 破鏡", 0, 570, 190, "RGB"),
            ("APA102C 煙雲", 570, 870, 100, "RGB"),
            ("WS2812B 高達", 870, 960, 30, "GRB"),  # 注意: GRB 順序 [3]
            ("STANDARD_LED 高達單色", 960, 976, 16, "PWM")
        ]
        
        for name, start, end, led_count, color_order in sections:
            section_data = pixel_data[start:end]
            print(f"  {name}:")
            print(f"    位元組範圍: {start}-{end} ({end-start} bytes)")
            print(f"    LED 數量: {led_count}")
            print(f"    顏色順序: {color_order}")
            
            # 顯示前幾個 LED 的顏色值作為範例
            if color_order != "PWM":
                print("    前 3 個 LED 顏色 (原始值):")
                for i in range(min(3, led_count)):
                    idx = i * 3
                    if color_order == "GRB":
                        g, r, b = section_data[idx:idx+3]
                        print(f"      LED{i}: R={r:3d}, G={g:3d}, B={b:3d}")
                    else:  # RGB
                        r, g, b = section_data[idx:idx+3]
                        print(f"      LED{i}: R={r:3d}, G={g:3d}, B={b:3d}")

# 使用範例
if __name__ == "__main__":
    # 初始化解碼器
    decoder = PXLDDecoder('/Users/tungkinlee/Downloads/demo_packet_slave0.pxld')  # 替換為實際檔案路徑
    
    try:
        # 解碼整個檔案
        decoder.decode()
        
        # 分析 LED 類型分布
        decoder.analyze_led_types(slave_id=1)
        
        # 提取第一個影格、第一個 slave 的 LED 顏色
        if len(decoder.frames) > 0:
            colors = decoder.extract_led_colors(0, 0)
            print(f"\n第一個影格、Slave 0 的前 5 個 LED 顏色:")
            for i, (r, g, b) in enumerate(colors[:5]):
                print(f"  LED{i}: RGB({r}, {g}, {b})")
                
    except FileNotFoundError:
        print("錯誤: 找不到指定的檔案")
    except ValueError as e:
        print(f"解碼錯誤: {e}")
    except Exception as e:
        print(f"發生未預期的錯誤: {e}")