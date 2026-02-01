import machine
import time
import _thread
import gc

# 🚀 壓測配置
FRAME_SIZE = 2000 * 4  # 2000 顆 LED (RGBA) = 8000 Bytes
BUFFER_COUNT = 1000     # 總緩衝幀數 (約 800KB)
TEST_DURATION = 5      # 測試持續秒數

# 數據源
source_data = bytearray(FRAME_SIZE)
for i in range(FRAME_SIZE): source_data[i] = i % 256

# 🚀 分配 PSRAM 空間
print(f"🛠️ Allocating {FRAME_SIZE * BUFFER_COUNT / 1024:.2f} KB in PSRAM...")
psram_pool = bytearray(FRAME_SIZE * BUFFER_COUNT)
pool_view = memoryview(psram_pool)
# 預切片以消除運行時開銷
frames = [pool_view[i*FRAME_SIZE : (i+1)*FRAME_SIZE] for i in range(BUFFER_COUNT)]

# 統計變量
stats = {
    "write_count": 0,
    "read_count": 0,
    "running": True
}

def core1_consumer():
    """模擬 LED 渲染核心: 持續從 PSRAM 讀取"""
    dummy_target = bytearray(FRAME_SIZE) # 模擬 SPI 傳輸緩衝
    target_view = memoryview(dummy_target)
    
    idx = 0
    while stats["running"]:
        # 模擬從 PSRAM 讀取一幀 (Bus Read)
        # 使用切片拷貝是最接近底層 memmove 的方式
        target_view[:] = frames[idx]
        
        idx = (idx + 1) % BUFFER_COUNT
        stats["read_count"] += 1
        
        # 模擬 SPI 傳輸延遲 (40FPS = 25ms, 但我們測極限不加 delay)
        # time.sleep_us(100) 

def run_test():
    gc.collect()
    print("🔥 Starting PSRAM Bus Contention Test...")
    
    # 啟動消費者 (Core 1)
    _thread.start_new_thread(core1_consumer, ())
    
    start_time = time.ticks_ms()
    idx = 0
    
    # 生產者 (Core 0)
    while time.ticks_diff(time.ticks_ms(), start_time) < TEST_DURATION * 1000:
        # 模擬從文件系統讀取到 PSRAM (Bus Write)
        frames[idx][:] = source_data
        
        idx = (idx + 1) % BUFFER_COUNT
        stats["write_index"] = idx
        stats["write_count"] += 1
    
    stats["running"] = False
    time.sleep_ms(200) # 等待 Core 1 退出
    
    # 🚀 結果分析
    elapsed = TEST_DURATION
    w_speed = (stats["write_count"] * FRAME_SIZE) / (1024 * 1024) / elapsed
    r_speed = (stats["read_count"] * FRAME_SIZE) / (1024 * 1024) / elapsed
    
    print("\n" + "="*30)
    print(f"📊 PSRAM PERFORMANCE REPORT")
    print(f"Total Bytes Processed: {(stats['write_count'] + stats['read_count']) * FRAME_SIZE / 1024 / 1024:.2f} MB")
    print(f"Producer (Write): {w_speed:.2f} MB/s | {stats['write_count']/elapsed:.1f} FPS")
    print(f"Consumer (Read) : {r_speed:.2f} MB/s | {stats['read_count']/elapsed:.1f} FPS")
    print(f"Aggregate Bandwidth: {w_speed + r_speed:.2f} MB/s")
    print("="*30)

if __name__ == "__main__":
    run_test()
