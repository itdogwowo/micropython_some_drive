import gc
import time
import binascii
import os

class PSRAMPerformancePro:
    def __init__(self, target_mb=10):
        self.target_bytes = target_mb * 1024 * 1024
        # 根據診斷，128KB 是最平衡的搬運大小 (SRAM -> PSRAM)
        self.io_chunk_size = 128 * 1024 
        gc.collect()
        
        try:
            self.buf = bytearray(self.target_bytes)
            self.mv = memoryview(self.buf)
            print(f"[*] 成功申請 {target_mb}MB PSRAM 測試空間")
        except:
            print("[-] 記憶體不足")
            
    def run_comprehensive_test(self):
        print(f"[{'='*45}]")
        print(f"  PSRAM 高性能壓力與穩定性測試")
        print(f"[{'='*45}]")

        # 1. SRAM -> PSRAM 寫入性能 (最佳化塊大小)
        sram_source = os.urandom(self.io_chunk_size)
        start = time.ticks_ms()
        for i in range(0, self.target_bytes, self.io_chunk_size):
            self.mv[i:i+self.io_chunk_size] = sram_source
        w_time = time.ticks_diff(time.ticks_ms(), start)
        w_speed = (self.target_bytes / 1024) / (w_time / 1000)

        # 2. PSRAM 內部對拷性能
        # 取中間點進行對換測試
        mid = self.target_bytes // 2
        src_part = self.mv[:mid]
        dst_part = self.mv[mid:]
        start = time.ticks_ms()
        dst_part[:] = src_part
        internal_time = time.ticks_diff(time.ticks_ms(), start)
        internal_speed = (mid / 1024) / (internal_time / 1000)

        # 3. PSRAM 全量讀取 (CRC32 校驗)
        start = time.ticks_ms()
        crc_val = binascii.crc32(self.mv)
        r_time = time.ticks_diff(time.ticks_ms(), start)
        r_speed = (self.target_bytes / 1024) / (r_time / 1000)

        # 4. 隨機壓力校驗 (Random Write & Verify)
        # 隨機挑選 10 個點寫入特定標記並立即讀回
        print("[*] 執行隨機邊界壓力測試...", end="")
        integrity = True
        for _ in range(10):
            offset = int.from_bytes(os.urandom(3), 'little') % (self.target_bytes - 1024)
            test_pattern = b"ULTIMATE_TEST_" + os.urandom(16)
            self.mv[offset : offset + len(test_pattern)] = test_pattern
            if self.mv[offset : offset + len(test_pattern)] != test_pattern:
                integrity = False
                break
        print(" 通過!" if integrity else " 失敗!")

        # --- 印出報表 ---
        print("\n" + "="*15 + " 性能報表 " + "="*15)
        print(f"  寫入速度 (SRAM->PSRAM): {w_speed:>10.2f} KB/s ({w_speed/1024:.2f} MB/s)")
        print(f"  內部速度 (PSRAM->PSRAM): {internal_speed:>9.2f} KB/s ({internal_speed/1024:.2f} MB/s)")
        print(f"  讀取速度 (PSRAM->CPU):   {r_speed:>10.2f} KB/s ({r_speed/1024:.2f} MB/s)")
        print(f"  資料校驗 (CRC32):        {hex(crc_val).upper()}")
        print(f"  穩定性測試:              {'[ PASS ]' if integrity else '[ FAIL ]'}")
        print("="*40)
        
        # 釋放記憶體
        del self.buf
        gc.collect()

# 執行 10MB 的完整測試
tester = PSRAMPerformancePro(target_mb=10)
tester.run_comprehensive_test()