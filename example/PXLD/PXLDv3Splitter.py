#!/usr/bin/env python3
"""
PXLD v3 分離器 - 增加幀範圍控制
功能: 將PXLD檔案中的每個Slave數據提取為純二進制文件 (BBBB格式)，支持指定幀範圍
風格: 分層訪問、類型提示、優雅錯誤處理
"""

import struct
import os
from typing import Dict, List, Optional, BinaryIO, Generator, Tuple
from dataclasses import dataclass
from pathlib import Path
import argparse

# ==================== 常數 ====================
V3_HEADER_SIZE = 64
V3_FRAME_HEADER_SIZE = 32
V3_SLAVE_ENTRY_SIZE = 24
V3_BYTES_PER_LED = 4  # 固定 RGBW 4 bytes

# ==================== 資料結構 ====================
@dataclass
class SlaveInfo:
    """Slave 元數據"""
    slave_id: int
    channel_start: int
    channel_count: int
    pixel_count: int
    data_offset: int
    data_length: int
    
    def __repr__(self) -> str:
        return f"Slave(id={self.slave_id}, pixels={self.pixel_count}, offset={self.data_offset})"

@dataclass  
class FrameData:
    """影格數據容器"""
    frame_id: int
    timestamp_ms: float
    slaves: List[SlaveInfo]
    pixel_data: bytes
    
    def __repr__(self) -> str:
        return f"Frame(id={self.frame_id}, slaves={len(self.slaves)}, data_size={len(self.pixel_data)})"

# ==================== 核心解碼器 ====================
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
    
    def _open_and_index(self) -> None:
        """開啟檔案並建立索引"""
        self.file = open(self.filepath, 'rb')
        
        # 讀取 FileHeader
        header = self.file.read(V3_HEADER_SIZE)
        
        # 驗證 Magic
        magic = header[0:4].decode('ascii')
        if magic != 'PXLD':
            raise ValueError(f"不是有效的 PXLD 檔案 (Magic: {magic})")
        
        # 解析 Header
        major_version = header[4]
        if major_version != 3:
            raise ValueError(f"不支援版本 {major_version}, 僅支援 v3")
        
        self.fps = header[6]
        self.total_slaves = struct.unpack('<H', header[7:9])[0]
        self.total_frames = struct.unpack('<I', header[9:13])[0]
        self.total_pixels = struct.unpack('<I', header[13:17])[0]
        
        # 建立影格索引
        self._build_frame_index()
        
        print(f"✅ PXLD v3 解碼器初始化成功")
        print(f"   檔案: {Path(self.filepath).name}")
        print(f"   FPS: {self.fps}")
        print(f"   總影格: {self.total_frames}")
        print(f"   總 Slave: {self.total_slaves}")
        print(f"   總 LED: {self.total_pixels}")
    
    def _build_frame_index(self) -> None:
        """建立所有影格的偏移索引"""
        self.frame_offsets = []
        current_offset = V3_HEADER_SIZE
        
        for frame_id in range(self.total_frames):
            self.frame_offsets.append(current_offset)
            
            # 讀取 FrameHeader 計算下一個影格位置
            self.file.seek(current_offset)
            frame_header = self.file.read(V3_FRAME_HEADER_SIZE)
            
            if len(frame_header) < V3_FRAME_HEADER_SIZE:
                print(f"⚠️  影格 {frame_id} 數據不完整，停止建立索引")
                break
            
            slave_table_size = struct.unpack('<I', frame_header[8:12])[0]
            pixel_data_size = struct.unpack('<I', frame_header[12:16])[0]
            
            current_offset += V3_FRAME_HEADER_SIZE + slave_table_size + pixel_data_size
    
    # ==================== 層級 1: Frame 訪問 ====================
    
    def get_frame(self, frame_id: int) -> FrameData:
        """
        獲取完整影格資料
        
        參數:
            frame_id: 影格索引 (0-based)
            
        返回:
            FrameData: 影格數據容器
        """
        if frame_id >= len(self.frame_offsets):
            raise ValueError(f"影格 {frame_id} 超出範圍 (總共 {len(self.frame_offsets)} 個)")
        
        self.file.seek(self.frame_offsets[frame_id])
        
        # 讀取 FrameHeader
        frame_header = self.file.read(V3_FRAME_HEADER_SIZE)
        actual_frame_id = struct.unpack('<I', frame_header[0:4])[0]
        slave_table_size = struct.unpack('<I', frame_header[8:12])[0]
        pixel_data_size = struct.unpack('<I', frame_header[12:16])[0]
        
        # 讀取 SlaveTable
        slave_table_data = self.file.read(slave_table_size)
        slaves = []
        
        for i in range(self.total_slaves):
            offset = i * V3_SLAVE_ENTRY_SIZE
            if offset + V3_SLAVE_ENTRY_SIZE > len(slave_table_data):
                continue
                
            entry = slave_table_data[offset:offset + V3_SLAVE_ENTRY_SIZE]
            
            slaves.append(SlaveInfo(
                slave_id=entry[0],
                channel_start=struct.unpack('<H', entry[2:4])[0],
                channel_count=struct.unpack('<H', entry[4:6])[0],
                pixel_count=struct.unpack('<H', entry[6:8])[0],
                data_offset=struct.unpack('<I', entry[8:12])[0],
                data_length=struct.unpack('<I', entry[12:16])[0]
            ))
        
        # 讀取 PixelData
        pixel_data = self.file.read(pixel_data_size)
        
        return FrameData(
            frame_id=actual_frame_id,
            timestamp_ms=(actual_frame_id * 1000) / self.fps if self.fps > 0 else 0,
            slaves=slaves,
            pixel_data=pixel_data
        )
    
    def iterate_frames(self, start_frame: int = 0, end_frame: Optional[int] = None) -> Generator[FrameData, None, None]:
        """
        迭代指定範圍內的影格 (生成器)
        
        參數:
            start_frame: 起始影格索引 (包含，默認0)
            end_frame: 結束影格索引 (不包含，默認為總影格數)
            
        返回:
            Generator[FrameData, None, None]: 影格數據生成器
        """
        if end_frame is None:
            end_frame = self.total_frames
        
        # 驗證範圍
        if start_frame < 0 or start_frame >= self.total_frames:
            raise ValueError(f"起始影格 {start_frame} 超出範圍 (0-{self.total_frames-1})")
        
        if end_frame < 0 or end_frame > self.total_frames:
            raise ValueError(f"結束影格 {end_frame} 超出範圍 (0-{self.total_frames})")
        
        if start_frame >= end_frame:
            raise ValueError(f"起始影格 {start_frame} 必須小於結束影格 {end_frame}")
        
        print(f"📊 處理影格範圍: {start_frame} - {end_frame} (共 {end_frame - start_frame} 個影格)")
        
        for frame_id in range(start_frame, end_frame):
            try:
                yield self.get_frame(frame_id)
            except Exception as e:
                print(f"⚠️  跳過影格 {frame_id}: {e}")
                break
    
    # ==================== 層級 2: Slave 訪問 ====================
    
    def get_slave_data(self, frame_data: FrameData, slave_id: int) -> bytes:
        """
        從影格中提取指定 Slave 的原始資料
        
        參數:
            frame_data: 影格數據
            slave_id: Slave ID
            
        返回:
            bytes: 該 Slave 的所有像素資料
        """
        slave = next((s for s in frame_data.slaves if s.slave_id == slave_id), None)
        if not slave:
            raise ValueError(f"找不到 Slave {slave_id}")
        
        start = slave.data_offset
        end = start + slave.data_length
        
        if end > len(frame_data.pixel_data):
            raise ValueError(f"Slave {slave_id} 數據超出範圍")
        
        return frame_data.pixel_data[start:end]
    
    def get_slave_info(self, frame_data: FrameData, slave_id: int) -> Optional[SlaveInfo]:
        """
        獲取指定 Slave 的元數據
        
        參數:
            frame_data: 影格數據
            slave_id: Slave ID
            
        返回:
            Optional[SlaveInfo]: Slave元數據，如果找不到則返回None
        """
        return next((s for s in frame_data.slaves if s.slave_id == slave_id), None)
    
    # ==================== 便捷方法 ====================
    
    def get_all_slaves_info(self, frame_data: FrameData) -> Dict[int, SlaveInfo]:
        """
        獲取影格中所有 Slave 的元數據
        
        參數:
            frame_data: 影格數據
            
        返回:
            Dict[int, SlaveInfo]: Slave ID 到 SlaveInfo 的映射
        """
        return {slave.slave_id: slave for slave in frame_data.slaves}
    
    def get_frame_range_info(self) -> Tuple[int, int, float]:
        """
        獲取影格範圍信息
        
        返回:
            Tuple[int, int, float]: (總影格數, FPS, 總時長(秒))
        """
        total_duration = self.total_frames / self.fps if self.fps > 0 else 0
        return self.total_frames, self.fps, total_duration
    
    def close(self) -> None:
        """關閉檔案"""
        if self.file:
            self.file.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

# ==================== 分離器 ====================
class PXLDv3Splitter:
    """PXLD v3 分離器 - 支持幀範圍控制"""
    
    def __init__(self, decoder: PXLDv3Decoder):
        """
        初始化分離器
        
        參數:
            decoder: PXLDv3Decoder 實例
        """
        self.decoder = decoder
        self.output_files: Dict[int, BinaryIO] = {}
        
        print(f"🔧 PXLD v3 分離器初始化成功")
    
    def split_single_slave(self, slave_id: int, 
                          output_path: Optional[str] = None,
                          start_frame: int = 0,
                          end_frame: Optional[int] = None) -> str:
        """
        分離單個 Slave 的數據（可指定幀範圍）
        
        參數:
            slave_id: Slave ID
            output_path: 輸出文件路徑 (可選)
            start_frame: 起始影格索引 (包含，默認0)
            end_frame: 結束影格索引 (不包含，默認為總影格數)
            
        返回:
            str: 輸出文件路徑
        """
        # 驗證 Slave ID
        if slave_id < 0 or slave_id >= self.decoder.total_slaves:
            raise ValueError(f"無效的 Slave ID: {slave_id} (總共 {self.decoder.total_slaves} 個)")
        
        # 設置結束幀
        if end_frame is None:
            end_frame = self.decoder.total_frames
        
        # 獲取輸出文件路徑
        if output_path is None:
            input_path = Path(self.decoder.filepath)
            output_dir = input_path.parent
            
            # 如果有指定幀範圍，在文件名中加入範圍信息
            if start_frame != 0 or end_frame != self.decoder.total_frames:
                range_suffix = f"_frames{start_frame}to{end_frame-1}"
            else:
                range_suffix = ""
                
            output_path = output_dir / f"{input_path.stem}_slave{slave_id}_raw{range_suffix}.bin"
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
        
        print(f"\n🎯 開始分離 Slave {slave_id}")
        print(f"   影格範圍: {start_frame} - {end_frame} (共 {end_frame - start_frame} 個影格)")
        print(f"   輸出文件: {output_path.name}")
        
        # 打開輸出文件
        output_file = open(output_path, 'wb')
        
        # 處理每個影格
        processed_frames = 0
        total_bytes = 0
        target_frames = end_frame - start_frame
        
        for frame_data in self.decoder.iterate_frames(start_frame, end_frame):
            try:
                # 提取 Slave 數據
                slave_data = self.decoder.get_slave_data(frame_data, slave_id)
                
                # 寫入文件
                output_file.write(slave_data)
                
                processed_frames += 1
                total_bytes += len(slave_data)
                
                # 顯示進度
                if target_frames >= 10 and processed_frames % (max(1, target_frames // 10)) == 0:
                    progress = processed_frames / target_frames * 100
                    print(f"   {progress:.0f}% 完成 ({processed_frames}/{target_frames})")
                    
            except Exception as e:
                print(f"⚠️  影格 {frame_data.frame_id} 跳過: {e}")
                continue
        
        # 關閉文件
        output_file.close()
        
        # 顯示統計信息
        print(f"\n✅ Slave {slave_id} 分離完成!")
        print(f"   已處理影格: {processed_frames}/{target_frames}")
        print(f"   總數據量: {total_bytes:,} bytes")
        
        if processed_frames > 0:
            bytes_per_frame = total_bytes // processed_frames
            leds_per_frame = bytes_per_frame // V3_BYTES_PER_LED
            duration_seconds = processed_frames / self.decoder.fps
            
            print(f"   每個影格: {bytes_per_frame:,} bytes ({leds_per_frame:,} LEDs)")
            print(f"   總時長: {duration_seconds:.2f} 秒")
        
        return str(output_path)
    
    def split_all_slaves(self, output_dir: Optional[str] = None,
                        start_frame: int = 0,
                        end_frame: Optional[int] = None) -> Dict[int, str]:
        """
        分離所有 Slave 的數據（可指定幀範圍）
        
        參數:
            output_dir: 輸出目錄 (可選)
            start_frame: 起始影格索引 (包含，默認0)
            end_frame: 結束影格索引 (不包含，默認為總影格數)
            
        返回:
            Dict[int, str]: Slave ID 到輸出文件路徑的映射
        """
        # 設置結束幀
        if end_frame is None:
            end_frame = self.decoder.total_frames
        
        # 設置輸出目錄
        if output_dir is None:
            input_path = Path(self.decoder.filepath)
            output_dir = input_path.parent
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\n📁 輸出目錄: {output_dir}")
        print(f"📊 影格範圍: {start_frame} - {end_frame} (共 {end_frame - start_frame} 個影格)")
        
        # 準備輸出文件
        input_stem = Path(self.decoder.filepath).stem
        output_paths = {}
        
        for slave_id in range(self.decoder.total_slaves):
            # 如果有指定幀範圍，在文件名中加入範圍信息
            if start_frame != 0 or end_frame != self.decoder.total_frames:
                range_suffix = f"_frames{start_frame}to{end_frame-1}"
            else:
                range_suffix = ""
                
            output_path = output_dir / f"{input_stem}_slave{slave_id}_raw{range_suffix}.bin"
            self.output_files[slave_id] = open(output_path, 'wb')
            output_paths[slave_id] = str(output_path)
            
            print(f"   準備輸出 Slave {slave_id} → {output_path.name}")
        
        print(f"\n🚀 開始處理所有 Slave...")
        
        # 處理每個影格
        processed_frames = 0
        target_frames = end_frame - start_frame
        
        for frame_data in self.decoder.iterate_frames(start_frame, end_frame):
            for slave_info in frame_data.slaves:
                slave_id = slave_info.slave_id
                
                try:
                    # 提取 Slave 數據
                    slave_data = self.decoder.get_slave_data(frame_data, slave_id)
                    
                    # 寫入對應文件
                    if slave_id in self.output_files:
                        self.output_files[slave_id].write(slave_data)
                        
                except Exception as e:
                    print(f"⚠️  影格 {frame_data.frame_id}, Slave {slave_id} 跳過: {e}")
            
            processed_frames += 1
            
            # 顯示進度
            if target_frames >= 10 and processed_frames % (max(1, target_frames // 10)) == 0:
                progress = processed_frames / target_frames * 100
                print(f"   {progress:.0f}% 完成 ({processed_frames}/{target_frames})")
        
        # 關閉所有文件
        for slave_id, file_obj in self.output_files.items():
            file_obj.close()
            
            # 顯示每個 Slave 的統計信息
            file_path = Path(output_paths[slave_id])
            file_size = file_path.stat().st_size
            
            if processed_frames > 0:
                bytes_per_frame = file_size // processed_frames
                leds_per_frame = bytes_per_frame // V3_BYTES_PER_LED
                print(f"   Slave {slave_id}: {file_size:,} bytes (每個影格 {bytes_per_frame:,} bytes, {leds_per_frame:,} LEDs)")
        
        # 總體統計
        total_duration = processed_frames / self.decoder.fps if self.decoder.fps > 0 else 0
        
        print(f"\n✅ 所有 Slave 分離完成!")
        print(f"   已處理影格: {processed_frames}/{target_frames}")
        print(f"   總時長: {total_duration:.2f} 秒")
        
        return output_paths
    
    def extract_frame_range(self, start_frame: int, end_frame: int, output_dir: Optional[str] = None) -> Dict[int, List[str]]:
        """
        提取多個幀範圍（分段提取）
        
        參數:
            start_frame: 起始幀
            end_frame: 結束幀（不包含）
            output_dir: 輸出目錄
            
        返回:
            Dict[int, List[str]]: Slave ID 到多個輸出文件路徑列表的映射
        """
        if start_frame < 0 or end_frame > self.decoder.total_frames or start_frame >= end_frame:
            raise ValueError(f"無效的幀範圍: {start_frame}-{end_frame}")
        
        # 設置輸出目錄
        if output_dir is None:
            output_dir = Path(self.decoder.filepath).parent
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\n🎬 分段提取: 幀 {start_frame} 到 {end_frame-1}")
        
        # 分段處理（每100幀為一個文件，可根據需要調整）
        segment_size = 100
        segments = []
        
        for segment_start in range(start_frame, end_frame, segment_size):
            segment_end = min(segment_start + segment_size, end_frame)
            segments.append((segment_start, segment_end))
        
        results = {slave_id: [] for slave_id in range(self.decoder.total_slaves)}
        
        for segment_idx, (seg_start, seg_end) in enumerate(segments):
            print(f"\n   處理段 {segment_idx+1}/{len(segments)}: 幀 {seg_start}-{seg_end-1}")
            
            # 為每個段創建獨立的分離器
            segment_output_dir = output_dir / f"segment_{seg_start:04d}_{seg_end-1:04d}"
            segment_output_dir.mkdir(exist_ok=True)
            
            # 分離這個段的所有Slave
            segment_paths = self.split_all_slaves(
                output_dir=str(segment_output_dir),
                start_frame=seg_start,
                end_frame=seg_end
            )
            
            # 收集結果
            for slave_id, path in segment_paths.items():
                results[slave_id].append(path)
        
        return results
    
    def close(self) -> None:
        """關閉所有輸出文件"""
        for file_obj in self.output_files.values():
            if not file_obj.closed:
                file_obj.close()

# ==================== 驗證工具 ====================
def verify_bin_file(filepath: str) -> Dict:
    """
    驗證二進制文件格式
    
    參數:
        filepath: 二進制文件路徑
        
    返回:
        Dict: 文件統計信息
    """
    path = Path(filepath)
    
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {filepath}")
    
    file_size = path.stat().st_size
    
    # 讀取並分析文件
    with open(filepath, 'rb') as f:
        # 讀取前幾個LED的值
        sample_data = []
        for i in range(min(5, file_size // V3_BYTES_PER_LED)):
            led_data = f.read(V3_BYTES_PER_LED)
            if len(led_data) == V3_BYTES_PER_LED:
                sample_data.append({
                    'index': i,
                    'rgbw': tuple(led_data),
                    'hex': led_data.hex()
                })
    
    # 檢查格式
    is_valid = file_size % V3_BYTES_PER_LED == 0
    
    # 計算可能包含的影格數（需要知道每個影格有多少個LED）
    # 這需要額外的信息，所以我們先不計算
    
    return {
        'filepath': str(path),
        'filename': path.name,
        'size_bytes': file_size,
        'total_leds': file_size // V3_BYTES_PER_LED,
        'is_valid_format': is_valid,
        'sample_data': sample_data
    }

def print_file_stats(stats: Dict) -> None:
    """打印文件統計信息"""
    print(f"\n📊 文件分析: {stats['filename']}")
    print(f"   大小: {stats['size_bytes']:,} bytes")
    print(f"   LED數量: {stats['total_leds']:,}")
    print(f"   格式驗證: {'✅ 正確' if stats['is_valid_format'] else '❌ 錯誤'}")
    
    if stats['sample_data']:
        print(f"\n   前 {len(stats['sample_data'])} 個LED:")
        for led in stats['sample_data']:
            rgbw = led['rgbw']
            print(f"     LED {led['index']}: R={rgbw[0]:3d}, G={rgbw[1]:3d}, B={rgbw[2]:3d}, W={rgbw[3]:3d}  (hex: {led['hex']})")

# ==================== 主程序 ====================
def main():
    """主程序"""
    parser = argparse.ArgumentParser(
        description='PXLD v3 分離器 - 支持幀範圍控制',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用範例:
  基本分離: python pxld_splitter.py demo.pxld
  分離指定幀範圍: python pxld_splitter.py demo.pxld --start-frame 100 --end-frame 200
  分離指定Slave和幀範圍: python pxld_splitter.py demo.pxld -s 0 --start-frame 100 --end-frame 200
  分段提取: python pxld_splitter.py demo.pxld --segment 0-100,200-300
        """
    )
    
    parser.add_argument('input_file', help='輸入的PXLD v3檔案路徑')
    parser.add_argument('-o', '--output-dir', help='輸出目錄 (默認為輸入檔案目錄)')
    parser.add_argument('-s', '--slave-id', type=int, help='只分離指定的Slave ID')
    parser.add_argument('-a', '--all', action='store_true', help='分離所有Slave (默認)')
    parser.add_argument('-v', '--verify', action='store_true', help='驗證輸出文件')
    parser.add_argument('-i', '--info', action='store_true', help='顯示檔案信息但不分離')
    
    # 新增的幀範圍參數
    parser.add_argument('--start-frame', type=int, default=0, 
                       help='起始影格索引 (包含，默認: 0)')
    parser.add_argument('--end-frame', type=int, 
                       help='結束影格索引 (不包含，默認: 總影格數)')
    parser.add_argument('--segment', type=str,
                       help='分段提取，格式: "起始1-結束1,起始2-結束2" (例如: "0-100,200-300")')
    
    args = parser.parse_args()
    
    try:
        print("=" * 60)
        print("PXLD v3 分離器 - 支持幀範圍控制")
        print("=" * 60)
        
        # 1. 初始化解碼器
        with PXLDv3Decoder(args.input_file) as decoder:
            
            # 2. 顯示影格範圍信息
            total_frames, fps, total_duration = decoder.get_frame_range_info()
            print(f"\n📊 影格信息:")
            print(f"   總影格: {total_frames}")
            print(f"   FPS: {fps}")
            print(f"   總時長: {total_duration:.2f} 秒")
            
            if args.end_frame is None:
                args.end_frame = total_frames
            
            # 3. 如果只需要信息
            if args.info:
                print("\n📋 詳細檔案信息:")
                
                # 讀取第一個影格以獲取更多信息
                try:
                    frame = decoder.get_frame(0)
                    print(f"   第一個影格包含 {len(frame.slaves)} 個Slave:")
                    
                    for slave in frame.slaves:
                        print(f"     Slave {slave.slave_id}: {slave.pixel_count} LEDs, {slave.data_length} bytes/影格")
                        
                except Exception as e:
                    print(f"   無法讀取影格數據: {e}")
                
                return
            
            # 4. 初始化分離器
            splitter = PXLDv3Splitter(decoder)
            
            # 5. 執行分離
            if args.segment:
                # 分段提取模式
                print(f"\n🎬 分段提取模式")
                
                # 解析分段參數
                segments = []
                for segment_str in args.segment.split(','):
                    if '-' in segment_str:
                        start, end = segment_str.split('-')
                        segments.append((int(start), int(end)))
                    else:
                        print(f"⚠️  忽略無效的分段: {segment_str}")
                
                if not segments:
                    print("❌ 沒有有效的分段")
                    return
                
                # 執行分段提取
                all_results = {}
                for seg_start, seg_end in segments:
                    print(f"\n🔧 處理分段: {seg_start}-{seg_end}")
                    
                    if args.slave_id is not None:
                        # 單個Slave分段
                        output_path = splitter.split_single_slave(
                            args.slave_id, 
                            args.output_dir,
                            seg_start,
                            seg_end
                        )
                        
                        if args.verify:
                            print(f"\n🔍 驗證輸出文件...")
                            stats = verify_bin_file(output_path)
                            print_file_stats(stats)
                    else:
                        # 所有Slave分段
                        output_paths = splitter.split_all_slaves(
                            args.output_dir,
                            seg_start,
                            seg_end
                        )
                        
                        if args.verify:
                            print(f"\n🔍 驗證所有輸出文件...")
                            for slave_id, filepath in output_paths.items():
                                stats = verify_bin_file(filepath)
                                print_file_stats(stats)
                        
                splitter.close()
                
            else:
                # 普通提取模式
                if args.slave_id is not None:
                    # 分離單個Slave
                    output_path = splitter.split_single_slave(
                        args.slave_id, 
                        args.output_dir,
                        args.start_frame,
                        args.end_frame
                    )
                    
                    if args.verify:
                        print(f"\n🔍 驗證輸出文件...")
                        stats = verify_bin_file(output_path)
                        print_file_stats(stats)
                        
                else:
                    # 分離所有Slave
                    output_paths = splitter.split_all_slaves(
                        args.output_dir,
                        args.start_frame,
                        args.end_frame
                    )
                    
                    if args.verify:
                        print(f"\n🔍 驗證所有輸出文件...")
                        for slave_id, filepath in output_paths.items():
                            stats = verify_bin_file(filepath)
                            print_file_stats(stats)
                
                splitter.close()
            
    except Exception as e:
        print(f"\n❌ 錯誤: {e}")
        import traceback
        traceback.print_exc()

# ==================== 使用範例 ====================
if __name__ == "__main__":
    import sys
    
    # 如果沒有命令行參數，顯示使用範例
    if len(sys.argv) == 1:
        print("使用方法:")
        print("  基本分離: python pxld_splitter.py demo.pxld")
        print("  分離指定幀範圍: python pxld_splitter.py demo.pxld --start-frame 100 --end-frame 200")
        print("  分離指定Slave和幀範圍: python pxld_splitter.py demo.pxld -s 0 --start-frame 100 --end-frame 200")
        print("  分段提取: python pxld_splitter.py demo.pxld --segment '0-100,200-300'")
        print("  顯示檔案信息: python pxld_splitter.py demo.pxld -i")
        print()
        print("或直接運行以下範例代碼:")
        
        # 示例代碼
        filepath = r"/Users/tungkinlee/Documents/Git/Sourcetree/micropython_some_drive/example/PXLD/show.pxld"
        
        try:
            with PXLDv3Decoder(filepath) as decoder:
                
                # ===== 顯示基本信息 =====
                total_frames, fps, total_duration = decoder.get_frame_range_info()
                print(f"\n📊 檔案信息:")
                print(f"   總影格: {total_frames}")
                print(f"   FPS: {fps}")
                print(f"   總時長: {total_duration:.2f} 秒")
                
                # ===== 層級 1: 獲取完整影格 =====
                frame = decoder.get_frame(100)
                print(f"\n影格 {frame.frame_id}, 時間: {frame.timestamp_ms:.2f} ms")
                print(f"包含 {len(frame.slaves)} 個 Slave")
                
                # ===== 層級 2: 查看 Slave 信息 =====
                slave_id = 0
                slave_info = decoder.get_slave_info(frame, slave_id)
                print(f"\nSlave {slave_id} 信息: {slave_info}")
                
                # ===== 層級 3: 提取 Slave 數據 =====
                slave_data = decoder.get_slave_data(frame, slave_id)
                print(f"Slave {slave_id} 數據大小: {len(slave_data)} bytes")
                print(f"包含 {len(slave_data) // V3_BYTES_PER_LED} 個 LED")
                
                # ===== 使用分離器 =====
                print(f"\n🔧 使用分離器...")
                splitter = PXLDv3Splitter(decoder)

                for i in range(33):
                
                    # 分離單個Slave（幀範圍: 0-50）
                    print(f"\n🎯 分離幀 0-50:")
                    output_path = splitter.split_single_slave(i, start_frame=0, end_frame=int(10707/2))
                    print(f"輸出文件: {output_path}")
                
                # # 分離單個Slave（幀範圍: 100-150）
                # print(f"\n🎯 分離幀 100-150:")
                # output_path = splitter.split_single_slave(slave_id, start_frame=100, end_frame=150)
                # print(f"輸出文件: {output_path}")
                
                splitter.close()
                
        except FileNotFoundError:
            print(f"找不到檔案: {filepath}")
            print("請確保檔案路徑正確，或使用命令行參數")
            
    else:
        # 運行命令行模式
        main()