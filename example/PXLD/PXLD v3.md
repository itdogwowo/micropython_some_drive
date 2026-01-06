# PXLD v3 協議技術文檔

**版本**: 3.0  
**狀態**: 最終定稿  
**最後更新**: 2024

---

## 📋 目錄

1. [設計目標](#1-設計目標)
2. [檔案結構總覽](#2-檔案結構總覽)
3. [FileHeader 結構](#3-fileheader-結構)
4. [Frame 結構](#4-frame-結構)
5. [數據格式規範](#5-數據格式規範)
6. [CRC32 校驗機制](#6-crc32-校驗機制)
7. [解析流程](#7-解析流程)
8. [Python 實現範例](#8-python-實現範例)
9. [常見問題](#9-常見問題)

---

## 1. 設計目標

### 1.1 核心原則

根據 PXLD v3 協議規範 [1]，本協議遵循以下設計原則：

✅ **自描述優先**: 所有結構尺寸、數量在 header 中明確宣告，解碼器零硬編碼 [1]  
✅ **職責分離**: PXLD 僅負責播放資料，硬體配置由 slave config 管理 [1]  
✅ **消除冗餘**: 移除可計算欄位 (timestamp_ms, total_channels) [1]  
✅ **極簡驗證**: 本地檔案僅在 FileHeader 做一次 CRC32 驗證 [1]  
✅ **高效解析**: 支援隨機跳轉到任意 frame [1]  
✅ **向後兼容**: 保留核心特性 (UDP 4050 埠、40 FPS) [1]

### 1.2 職責劃分

```
PXLD 檔案 (本協議)              ←→  Slave Config JSON
───────────────────                 ─────────────────────
• Frame 資料                        • LED 類型/數量/排列
• Channel 映射                      • GPIO 配置
• Pixel 原始資料                    • 時序參數
• 播放元數據                        • 硬體特性
```

---

## 2. 檔案結構總覽

### 2.1 整體架構

```
┌─────────────────────────────────────────────────┐
│ FileHeader (64 bytes, 固定)                     │
│ - Magic, Version, FPS                           │
│ - Total Frames, Total Slaves, Total Pixels      │
│ - CRC32 校驗碼                                  │
├─────────────────────────────────────────────────┤
│ Frame 0                                         │
│  ├─ FrameHeader (32 bytes)                      │
│  ├─ SlaveTable (24 × total_slaves bytes)        │
│  └─ PixelData (variable size)                   │
├─────────────────────────────────────────────────┤
│ Frame 1                                         │
│  ├─ FrameHeader (32 bytes)                      │
│  ├─ SlaveTable (24 × total_slaves bytes)        │
│  └─ PixelData (variable size)                   │
├─────────────────────────────────────────────────┤
│ ...                                             │
└─────────────────────────────────────────────────┘
```

### 2.2 尺寸規範

- **FileHeader**: 固定 64 bytes
- **FrameHeader**: 固定 32 bytes
- **SlaveEntry**: 固定 24 bytes
- **LED 數據**: 固定 4 bytes/LED (RGBW 格式)

---

## 3. FileHeader 結構

### 3.1 欄位定義 (64 bytes 總計)

| Offset | 欄位名稱             | 類型  | 大小   | 說明                          |
|--------|---------------------|-------|--------|-------------------------------|
| 0-3    | magic               | char  | 4      | 魔術數字 "PXLD"               |
| 4      | major_version       | u8    | 1      | 主版本號 (3)                  |
| 5      | minor_version       | u8    | 1      | 次版本號 (0)                  |
| 6      | fps                 | u8    | 1      | 幀率 (預設 40)                |
| 7-8    | total_slaves        | u16   | 2      | Slave 總數                    |
| 9-12   | total_frames        | u32   | 4      | 總幀數                        |
| 13-16  | total_pixels        | u32   | 4      | 總 LED 數量                   |
| 17-18  | frame_header_size   | u16   | 2      | FrameHeader 大小 (固定 32)    |
| 19-20  | slave_entry_size    | u16   | 2      | SlaveEntry 大小 (固定 24)     |
| 21-22  | udp_port            | u16   | 2      | UDP 埠 (預設 4050)            |
| 23-26  | file_crc32          | u32   | 4      | CRC32 校驗碼                  |
| 27     | checksum_type       | u8    | 1      | 校驗類型 (1=CRC32, 0=無)      |
| 28-63  | reserved            | u8[]  | 36     | 保留欄位 (填 0)               |

### 3.2 Python 解析範例

```python
import struct

def parse_file_header(data: bytes) -> dict:
    """解析 FileHeader (64 bytes)"""
    
    # 驗證 Magic
    magic = data[0:4].decode('ascii')
    if magic != 'PXLD':
        raise ValueError(f"無效檔案格式: {magic}")
    
    # 解析欄位 (little-endian)
    return {
        'magic': magic,
        'major_version': data[4],
        'minor_version': data[5],
        'fps': data[6],
        'total_slaves': struct.unpack('<H', data[7:9])[0],
        'total_frames': struct.unpack('<I', data[9:13])[0],
        'total_pixels': struct.unpack('<I', data[13:17])[0],
        'frame_header_size': struct.unpack('<H', data[17:19])[0],
        'slave_entry_size': struct.unpack('<H', data[19:21])[0],
        'udp_port': struct.unpack('<H', data[21:23])[0],
        'file_crc32': struct.unpack('<I', data[23:27])[0],
        'checksum_type': data[27]
    }
```

---

## 4. Frame 結構

### 4.1 FrameHeader (32 bytes)

| Offset | 欄位名稱           | 類型  | 大小 | 說明                        |
|--------|--------------------|-------|------|----------------------------|
| 0-3    | frame_id           | u32   | 4    | 幀 ID (從 0 開始)           |
| 4-5    | flags              | u16   | 2    | 標誌位 (預留，填 0)         |
| 6-7    | reserved1          | u16   | 2    | 保留                       |
| 8-11   | slave_table_size   | u32   | 4    | SlaveTable 總大小 (bytes)   |
| 12-15  | pixel_data_size    | u32   | 4    | PixelData 總大小 (bytes)    |
| 16-31  | reserved2          | u8[]  | 16   | 保留欄位                   |

**計算公式** [1]:
```python
timestamp_ms = frame_id × (1000 / fps)  # 不存儲在檔案中
```

### 4.2 SlaveEntry (24 bytes)

| Offset | 欄位名稱        | 類型  | 大小 | 說明                        |
|--------|----------------|-------|------|-----------------------------|
| 0      | slave_id       | u8    | 1    | Slave ID                    |
| 1      | flags          | u8    | 1    | 標誌位 (預留，填 0)         |
| 2-3    | channel_start  | u16   | 2    | 起始通道號 (從 1 開始)      |
| 4-5    | channel_count  | u16   | 2    | 通道數量                    |
| 6-7    | pixel_count    | u16   | 2    | LED 數量                    |
| 8-11   | data_offset    | u32   | 4    | 在 PixelData 中的偏移       |
| 12-15  | data_length    | u32   | 4    | 數據長度 (bytes)            |
| 16-23  | reserved       | u8[]  | 8    | 保留欄位                    |

### 4.3 PixelData (可變長度)

- **格式**: 連續的 RGBW 數據塊
- **每個 LED**: 固定 4 bytes (R, G, B, W)
- **排列順序**: 按 SlaveEntry 中的 data_offset 排列

---

## 5. 數據格式規範

### 5.1 LED 類型與數據格式

根據 slave config [2]，v3 協議支援以下 LED 類型：

#### 5.1.1 APA102C (RGB LED)
```
原始格式 (v2): [R][G][B]
v3 格式:       [R][G][B][0x1F]  ← W 通道設為最大亮度
```

**配置範例** [2]:
```json
{
  "type": "APA102C",
  "label": "smoke_rgb",
  "description": "雲煙",
  "count": 100,
  "bytes_per_pixel": 3,
  "data_offset": 570,
  "data_length": 300
}
```

#### 5.1.2 WS2812B (RGB LED)
```
原始格式 (v2): [G][R][B]  ← 注意順序!
v3 格式:       [R][G][B][0xFF]
```

**配置範例** [2]:
```json
{
  "type": "WS2812B",
  "label": "gundam_rgb",
  "description": "高達 RGB",
  "count": 30,
  "bytes_per_pixel": 3,
  "data_offset": 870,
  "data_length": 90
}
```

#### 5.1.3 STANDARD_LED (單色 LED)
```
原始格式 (v2): [Brightness]  ← 只佔 1 byte (0-255)
v3 格式:       [0x00][0x00][0x00][Brightness]
```

**配置範例** [2]:
```json
{
  "type": "STANDARD_LED",
  "label": "gundam_led",
  "description": "高達單色 LED",
  "count": 16,
  "channels_per_pixel": 1,
  "bytes_per_pixel": 1,
  "data_offset": 960,
  "data_length": 16
}
```

### 5.2 RGBW 字節順序

所有 LED 統一使用 **小端序 (little-endian)** RGBW 格式：

```
Byte 0: Red   (0-255)
Byte 1: Green (0-255)
Byte 2: Blue  (0-255)
Byte 3: White (0-255, 亮度或保留值)
```

---

## 6. CRC32 校驗機制

### 6.1 校驗範圍

根據協議規範 [1]：

- **起始位置**: offset 27 (checksum_type 欄位)
- **結束位置**: 檔案結尾
- **排除範圍**: offset 23-26 (file_crc32 欄位本身)

### 6.2 Python 實現

```python
import binascii

def verify_crc32(file_path: str) -> bool:
    """驗證 PXLD v3 檔案的 CRC32"""
    
    with open(file_path, 'rb') as f:
        # 讀取宣告的 CRC32 值
        f.seek(23)
        declared_crc32 = struct.unpack('<I', f.read(4))[0]
        
        # 計算實際 CRC32 (從 offset 27 開始)
        f.seek(27)
        data = f.read()
        calculated_crc32 = binascii.crc32(data) & 0xFFFFFFFF
        
        return declared_crc32 == calculated_crc32
```

### 6.3 checksum_type 說明 [1]

| 值 | 說明             |
|----|------------------|
| 0  | 不使用校驗       |
| 1  | CRC32 校驗       |

---

## 7. 解析流程

### 7.1 完整解析流程圖

```
┌─────────────────┐
│ 1. 讀取檔案     │
└────────┬────────┘
         ↓
┌─────────────────┐
│ 2. 解析 Header  │
│  - 驗證 Magic   │
│  - 檢查版本     │
└────────┬────────┘
         ↓
┌─────────────────┐
│ 3. CRC32 驗證   │ [1]
└────────┬────────┘
         ↓
┌─────────────────┐
│ 4. 建立索引     │
│  - 計算 Frame   │
│    偏移位置     │
└────────┬────────┘
         ↓
┌─────────────────┐
│ 5. 讀取 Frame   │
│  - FrameHeader  │
│  - SlaveTable   │
│  - PixelData    │
└─────────────────┘
```

### 7.2 驗證清單 [1]

- [ ] FileHeader CRC32 驗證通過
- [ ] Magic = "PXLD", Version = 3.0
- [ ] frame_header_size = 32, slave_entry_size = 24
- [ ] slave_table_size = total_slaves × 24
- [ ] 所有 slave.data_offset + data_length ≤ pixel_data_size

---

## 8. Python 實現範例

### 8.1 完整解碼器

```python
class PXLDv3Decoder:
    """PXLD v3 解碼器"""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.file_header = None
        self.frame_offsets = []
        
        self._parse_file()
    
    def _parse_file(self):
        """解析檔案"""
        with open(self.filepath, 'rb') as f:
            # 1. 解析 FileHeader
            header_data = f.read(64)
            self.file_header = parse_file_header(header_data)
            
            # 2. 驗證 CRC32
            if not verify_crc32(self.filepath):
                raise ValueError("CRC32 校驗失敗")
            
            # 3. 建立 Frame 索引
            self._build_frame_index(f)
    
    def _build_frame_index(self, f):
        """建立 Frame 偏移索引"""
        current_offset = 64  # FileHeader 之後
        
        for _ in range(self.file_header['total_frames']):
            self.frame_offsets.append(current_offset)
            
            # 讀取 FrameHeader
            f.seek(current_offset)
            frame_header = f.read(32)
            
            slave_table_size = struct.unpack('<I', frame_header[8:12])[0]
            pixel_data_size = struct.unpack('<I', frame_header[12:16])[0]
            
            current_offset += 32 + slave_table_size + pixel_data_size
    
    def read_frame(self, frame_id: int) -> dict:
        """讀取指定 Frame"""
        if frame_id >= len(self.frame_offsets):
            raise ValueError(f"Frame {frame_id} 超出範圍")
        
        with open(self.filepath, 'rb') as f:
            f.seek(self.frame_offsets[frame_id])
            
            # 讀取 FrameHeader
            frame_header = f.read(32)
            slave_table_size = struct.unpack('<I', frame_header[8:12])[0]
            pixel_data_size = struct.unpack('<I', frame_header[12:16])[0]
            
            # 讀取 SlaveTable
            slave_table = f.read(slave_table_size)
            slaves = self._parse_slave_table(slave_table)
            
            # 讀取 PixelData
            pixel_data = f.read(pixel_data_size)
            
            return {
                'frame_id': struct.unpack('<I', frame_header[0:4])[0],
                'timestamp_ms': frame_id * (1000 / self.file_header['fps']),  # 計算
                'slaves': slaves,
                'pixel_data': pixel_data
            }
    
    def _parse_slave_table(self, data: bytes) -> list:
        """解析 SlaveTable"""
        slaves = []
        entry_size = 24
        
        for i in range(0, len(data), entry_size):
            entry = data[i:i+entry_size]
            slaves.append({
                'slave_id': entry[0],
                'channel_start': struct.unpack('<H', entry[2:4])[0],
                'channel_count': struct.unpack('<H', entry[4:6])[0],
                'pixel_count': struct.unpack('<H', entry[6:8])[0],
                'data_offset': struct.unpack('<I', entry[8:12])[0],
                'data_length': struct.unpack('<I', entry[12:16])[0]
            })
        
        return slaves
    
    def get_slave_data(self, frame_data: dict, slave_id: int) -> bytes:
        """提取指定 Slave 的數據"""
        slave = next((s for s in frame_data['slaves'] if s['slave_id'] == slave_id), None)
        if not slave:
            raise ValueError(f"找不到 Slave {slave_id}")
        
        start = slave['data_offset']
        end = start + slave['data_length']
        return frame_data['pixel_data'][start:end]
```

### 8.2 使用範例 [1]

```python
if __name__ == '__main__':
    decoder = PXLDv3Decoder('show.pxld')
    
    print("\n=== FileHeader ===")
    fh = decoder.file_header
    print(f"Version: {fh['major_version']}.{fh['minor_version']}")
    print(f"FPS: {fh['fps']}")
    print(f"Total Frames: {fh['total_frames']}")
    print(f"Total Slaves: {fh['total_slaves']}")
    print(f"Total Pixels: {fh['total_pixels']}")
    
    # 計算 total_channels (不儲存在檔案中)
    total_channels = fh['total_pixels'] * 4
    print(f"Total Channels (計算): {total_channels}")
    
    # 讀取第 0 frame
    print("\n=== Frame 0 ===")
    frame0 = decoder.read_frame(0)
    print(f"Frame ID: {frame0['frame_id']}")
    print(f"Timestamp: {frame0['timestamp_ms']:.2f} ms (計算)")
    print(f"Slaves: {len(frame0['slaves'])}")
    
    # 提取 slave 0 的資料
    slave0_data = decoder.get_slave_data(frame0, slave_id=0)
    print(f"\nSlave 0 data length: {len(slave0_data)} bytes")
```

---

## 9. 常見問題

### Q1: 為什麼移除 `total_channels`?

**A**: 可由公式計算 `total_channels = total_pixels × 4`，避免冗餘 [1]。

### Q2: 為什麼移除 `timestamp_ms`?

**A**: 可由公式計算 `timestamp_ms = frame_id × (1000/fps)`，避免冗餘 [1]。

### Q3: `flags` 欄位當前如何使用?

**A**: 當前版本填 `0`，預留未來擴展 (壓縮/關鍵幀等) [1]。

### Q4: CRC32 覆蓋範圍?

**A**: offset 27 到檔案結尾 (不包含 offset 23-26 的 CRC32 值本身) [1]。

### Q5: 單色 LED 如何表示?

**A**: 使用 RGBW 格式的 W 通道，R/G/B 填 0 [2]。例如：`[0x00][0x00][0x00][0xFF]` 表示全亮。

---

## 10. 附錄

### 10.1 字節序約定

- **所有多字節整數**: 小端序 (little-endian)
- **字符串**: ASCII 編碼
- **填充字節**: 填 0x00

### 10.2 版本歷史 [1]

| 版本 | 日期 | 變更 |
|------|------|------|
| 3.0  | 2024 | 自描述架構，移除冗餘欄位 (total_channels, timestamp_ms, status) |

---
