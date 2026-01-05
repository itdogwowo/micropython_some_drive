#!/usr/bin/env python3
"""
PXLD v2 到 v3 格式轉換器 (最終修正版)
規則: 每個 LED 固定 4 字節，數據順序 RGBW。
      WS2812B 原始數據為 [G][R][B] [1]，轉換為 [R,G,B,W]。
      APA102C 亮度設置為 0x1F (最高)，單色 LED 亮度存入 W 通道。
作者: 基於 PXLD 技術文檔 [1] 及最新 v3 規範
"""

import struct
import json
import binascii
import os
import sys
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

# ==================== 常數定義 ====================
V2_HEADER_SIZE = 64
V2_FRAME_SIZE = 32620
V2_FRAME_HEADER_SIZE = 16
V2_SLAVE_HEADER_SIZE = 396
V2_PIXEL_DATA_SIZE = 32208
V2_TOTAL_SLAVES = 33
V2_CHANNELS_PER_SLAVE = 976

V3_HEADER_SIZE = 64
V3_FRAME_HEADER_SIZE = 32
V3_SLAVE_ENTRY_SIZE = 24
V3_BYTES_PER_LED = 4
V3_MAGIC = b'PXLD'
V3_MAJOR_VERSION = 3
V3_MINOR_VERSION = 0
V3_UDP_PORT = 4050
V3_CHECKSUM_TYPE = 1

# ==================== 資料結構 ====================
@dataclass
class V2Header:
    magic: str
    major_version: int
    minor_version: int
    fps: int
    total_slaves: int
    total_channels: int
    total_pixels: int
    udp_port: int
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'V2Header':
        magic = data[0:4].decode('ascii', errors='ignore')
        if magic != 'PXLD':
            raise ValueError(f"無效的 PXLD 檔案")
        return cls(
            magic=magic,
            major_version=data[4],
            minor_version=data[5],
            fps=data[6],
            total_slaves=data[7],
            total_channels=struct.unpack('<I', data[8:12])[0],
            total_pixels=struct.unpack('<I', data[12:16])[0],
            udp_port=struct.unpack('<H', data[16:18])[0]
        )

# ==================== 核心轉換器 ====================
class PXLDv2ToV3Converter:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.slave_configs = {}
        self.stats = {
            'input_size': 0, 'output_size': 0, 'frames_converted': 0,
            'total_pixels': 0, 'total_pixels_v3': 0, 'errors': []
        }
        if config_path:
            self.load_slave_configs(config_path)
    
    def load_slave_configs(self, config_path: str):
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
            print("⚠️  將使用預設配置規則")
    
    def convert_led_data(self, led_type: str, original_data: bytes) -> bytes:
        """
        將單個 LED 的原始資料轉換為 4 字節 RGBW 格式
        注意: WS2812B 原始順序為 [G][R][B] [1]
        """
        if led_type in ['APA102C', 'WS2812B']:
            if len(original_data) >= 3:
                if led_type == 'WS2812B':
                    # WS2812B: 原始順序為 [G][R][B] [1]，轉換為 [R,G,B,W]
                    g, r, b = original_data[0], original_data[1], original_data[2]
                else:  # APA102C
                    # APA102C: 假設原始順序為 [R,G,B]
                    r, g, b = original_data[0], original_data[1], original_data[2]
                
                # 設置亮度通道
                w = 0x1F if led_type == 'APA102C' else 0xFF
                return bytes([r, g, b, w])
            else:
                w = 0x1F if led_type == 'APA102C' else 0xFF
                return bytes([0x00, 0x00, 0x00, w])
                
        elif led_type == 'STANDARD_LED':
            if len(original_data) >= 1:
                brightness = original_data[0]
                return bytes([0x00, 0x00, 0x00, brightness])
            else:
                return bytes([0x00, 0x00, 0x00, 0x00])
        else:
            return bytes([0x00, 0x00, 0x00, 0x00])
    
    def calculate_slave_pixel_count(self, slave_id: int) -> int:
        if slave_id in self.slave_configs:
            config = self.slave_configs[slave_id]
            total = 0
            for output in config.get('outputs', []):
                total += output.get('count', 0)
            return total
        return V2_CHANNELS_PER_SLAVE // 3
    
    def convert_slave_data(self, v2_slave_data: bytes, slave_id: int) -> Tuple[bytes, int]:
        if len(v2_slave_data) != V2_CHANNELS_PER_SLAVE:
            raise ValueError(f"Slave 資料長度錯誤")
        
        if slave_id in self.slave_configs:
            config = self.slave_configs[slave_id]
            v3_data = bytearray()
            pixel_count = 0
            
            for output in config.get('outputs', []):
                output_type = output.get('type', 'UNKNOWN')
                count = output.get('count', 0)
                data_offset = output.get('data_offset', 0)
                bytes_per_pixel = output.get('bytes_per_pixel', 3)
                
                start_offset = data_offset
                end_offset = start_offset + (count * bytes_per_pixel)
                output_data = v2_slave_data[start_offset:end_offset]
                
                for i in range(count):
                    pixel_start = i * bytes_per_pixel
                    pixel_end = pixel_start + bytes_per_pixel
                    pixel_data = output_data[pixel_start:pixel_end]
                    v3_pixel = self.convert_led_data(output_type, pixel_data)
                    v3_data.extend(v3_pixel)
                    pixel_count += 1
            return bytes(v3_data), pixel_count
        else:
            pixel_count = V2_CHANNELS_PER_SLAVE // 3
            v3_data = bytearray()
            for i in range(pixel_count):
                start_offset = i * 3
                pixel_data = v2_slave_data[start_offset:start_offset + 3]
                v3_pixel = self.convert_led_data('APA102C', pixel_data)
                v3_data.extend(v3_pixel)
            return bytes(v3_data), pixel_count
    
    def convert_file(self, input_path: str, output_path: str, total_frames: Optional[int] = None) -> Dict:
        print(f"🔧 開始轉換: {input_path} -> {output_path}")
        print(f"📐 轉換規則: 每個 LED 固定 {V3_BYTES_PER_LED} 字節 (RGBW 順序)")
        
        try:
            input_size = os.path.getsize(input_path)
            self.stats['input_size'] = input_size
            
            with open(input_path, 'rb') as f_in:
                v2_header_data = f_in.read(V2_HEADER_SIZE)
                v2_header = V2Header.from_bytes(v2_header_data)
                
                print(f"\n📄 輸入檔案資訊 (v2):")
                print(f"   版本: {v2_header.major_version}.{v2_header.minor_version}")
                print(f"   FPS: {v2_header.fps}")
                print(f"   Slave 數量: {v2_header.total_slaves}")
                print(f"   總 LED 數 (v2): {v2_header.total_pixels}")
                
                data_start = V2_HEADER_SIZE
                file_data_size = input_size - data_start
                
                if total_frames is None:
                    total_frames = file_data_size // V2_FRAME_SIZE
                    if file_data_size % V2_FRAME_SIZE != 0:
                        print(f"⚠️  檔案大小不是 V2_FRAME_SIZE 的倍數")
                
                print(f"   總影格數: {total_frames}")
                
                # 計算每個 Slave 的 pixel_count 和總 pixel_count
                slave_pixel_counts = []
                total_pixels_v3 = 0
                for slave_id in range(v2_header.total_slaves):
                    pixel_count = self.calculate_slave_pixel_count(slave_id)
                    slave_pixel_counts.append(pixel_count)
                    total_pixels_v3 += pixel_count
                
                self.stats['total_pixels'] = v2_header.total_pixels
                self.stats['total_pixels_v3'] = total_pixels_v3
                total_channels_v3 = total_pixels_v3 * V3_BYTES_PER_LED
                
                print(f"\n📄 輸出檔案資訊 (v3):")
                print(f"   總 LED 數 (v3): {total_pixels_v3}")
                print(f"   總通道數 (v3): {total_channels_v3} (每個 LED {V3_BYTES_PER_LED} 字節)")
                
                # 第一步: 寫入所有資料（CRC32暫時為0）
                with open(output_path, 'wb') as f_out:
                    # 寫入暫時的 v3 標頭
                    header = bytearray(V3_HEADER_SIZE)
                    header[0:4] = V3_MAGIC
                    header[4] = V3_MAJOR_VERSION
                    header[5] = V3_MINOR_VERSION
                    header[6] = v2_header.fps
                    struct.pack_into('<H', header, 7, v2_header.total_slaves)
                    struct.pack_into('<I', header, 9, total_frames)
                    struct.pack_into('<I', header, 13, total_pixels_v3)
                    struct.pack_into('<H', header, 17, V3_FRAME_HEADER_SIZE)
                    struct.pack_into('<H', header, 19, V3_SLAVE_ENTRY_SIZE)
                    struct.pack_into('<H', header, 21, V3_UDP_PORT)
                    struct.pack_into('<I', header, 23, 0)  # CRC32 暫時為0
                    header[27] = V3_CHECKSUM_TYPE
                    header[28:64] = bytes(36)
                    f_out.write(header)
                    
                    # 建立 SlaveEntry 列表
                    slave_entries = []
                    current_data_offset = 0
                    for slave_id in range(v2_header.total_slaves):
                        pixel_count = slave_pixel_counts[slave_id]
                        data_length = pixel_count * V3_BYTES_PER_LED
                        channel_start = 1
                        for i in range(slave_id):
                            channel_start += slave_pixel_counts[i] * V3_BYTES_PER_LED
                        channel_count = pixel_count * V3_BYTES_PER_LED
                        
                        slave_entry = bytearray(V3_SLAVE_ENTRY_SIZE)
                        slave_entry[0] = slave_id
                        slave_entry[1] = 0
                        struct.pack_into('<H', slave_entry, 2, channel_start)
                        struct.pack_into('<H', slave_entry, 4, channel_count)
                        struct.pack_into('<H', slave_entry, 6, pixel_count)
                        struct.pack_into('<I', slave_entry, 8, current_data_offset)
                        struct.pack_into('<I', slave_entry, 12, data_length)
                        slave_entry[16:24] = bytes(8)
                        slave_entries.append(slave_entry)
                        current_data_offset += data_length
                    
                    total_pixel_data_size = current_data_offset
                    
                    # 轉換並寫入每個影格
                    for frame_id in range(total_frames):
                        try:
                            v2_frame_data = f_in.read(V2_FRAME_SIZE)
                            if len(v2_frame_data) < V2_FRAME_SIZE:
                                print(f"⚠️  影格 {frame_id} 資料不完整，停止處理")
                                break
                            
                            v2_pixel_data = v2_frame_data[V2_FRAME_HEADER_SIZE + V2_SLAVE_HEADER_SIZE:]
                            if len(v2_pixel_data) != V2_PIXEL_DATA_SIZE:
                                raise ValueError(f"v2 像素資料長度錯誤")
                            
                            # 建立 v3 PixelData
                            v3_pixel_data = bytearray()
                            for slave_id in range(v2_header.total_slaves):
                                slave_start = slave_id * V2_CHANNELS_PER_SLAVE
                                slave_end = slave_start + V2_CHANNELS_PER_SLAVE
                                v2_slave_data = v2_pixel_data[slave_start:slave_end]
                                v3_slave_data, _ = self.convert_slave_data(v2_slave_data, slave_id)
                                v3_pixel_data.extend(v3_slave_data)
                            
                            # 寫入 v3 FrameHeader
                            frame_header = bytearray(V3_FRAME_HEADER_SIZE)
                            struct.pack_into('<I', frame_header, 0, frame_id)
                            struct.pack_into('<H', frame_header, 4, 0)
                            struct.pack_into('<H', frame_header, 6, 0)
                            struct.pack_into('<I', frame_header, 8, len(slave_entries) * V3_SLAVE_ENTRY_SIZE)
                            struct.pack_into('<I', frame_header, 12, len(v3_pixel_data))
                            frame_header[16:32] = bytes(16)
                            f_out.write(frame_header)
                            
                            # 寫入 SlaveTable
                            for entry in slave_entries:
                                f_out.write(entry)
                            
                            # 寫入 PixelData
                            f_out.write(v3_pixel_data)
                            
                            self.stats['frames_converted'] += 1
                            if (frame_id + 1) % 100 == 0:
                                progress = (frame_id + 1) / total_frames * 100
                                print(f"  轉換進度: {frame_id + 1}/{total_frames} 影格 ({progress:.1f}%)")
                                
                        except Exception as e:
                            error_msg = f"影格 {frame_id} 轉換失敗: {e}"
                            self.stats['errors'].append(error_msg)
                            print(f"❌ {error_msg}")
                
                print(f"   所有影格資料寫入完成，開始計算 CRC32...")
                
                # 第二步: 重新開啟檔案計算 CRC32
                with open(output_path, 'rb') as f_in_crc:
                    f_in_crc.seek(27)  # 從 offset 27 開始計算 [1]
                    file_data_for_crc = f_in_crc.read()
                    crc32_value = binascii.crc32(file_data_for_crc) & 0xFFFFFFFF
                    print(f"✅ CRC32 計算完成: 0x{crc32_value:08X}")
                
                # 第三步: 更新標頭中的 CRC32 值
                with open(output_path, 'r+b') as f_update:
                    f_update.seek(23)
                    f_update.write(struct.pack('<I', crc32_value))
                
                print(f"✅ CRC32 值已更新至檔案標頭。")
                self.stats['output_size'] = os.path.getsize(output_path)
                    
        except Exception as e:
            error_msg = f"轉換過程發生錯誤: {e}"
            self.stats['errors'].append(error_msg)
            print(f"❌ {error_msg}")
            raise
        
        return self.stats

# ==================== 主程式 ====================
def main():
    import argparse
    parser = argparse.ArgumentParser(description='PXLD v2 到 v3 轉換器')
    parser.add_argument('input', nargs='?', help='輸入檔案路徑')
    parser.add_argument('output', nargs='?', help='輸出檔案路徑')
    parser.add_argument('-c', '--config', help='Slave 配置 JSON 檔案')
    parser.add_argument('-f', '--frames', type=int, help='總影格數')
    
    args = parser.parse_args()
    
    if not args.input or not args.output:
        parser.print_help()
        return 1
    
    try:
        converter = PXLDv2ToV3Converter(args.config)
        stats = converter.convert_file(args.input, args.output, args.frames)
        
        print(f"\n轉換統計:")
        print(f"  輸入: {stats['input_size']:,} bytes")
        print(f"  輸出: {stats['output_size']:,} bytes")
        print(f"  影格: {stats['frames_converted']}")
        if stats['errors']:
            print(f"\n⚠️  發生 {len(stats['errors'])} 個錯誤")
        return 0
    except Exception as e:
        print(f"❌ 轉換失敗: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())