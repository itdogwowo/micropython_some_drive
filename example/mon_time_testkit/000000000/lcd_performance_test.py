# =========================================
# lcd_performance_test.py - LCD写入性能测试
# =========================================

import time
from performance_profiler import profiler

def test_lcd_write_performance(lcd):
    """测试LCD写入性能"""
    print("\n=== LCD Write Performance Test ===")
    
    # 测试不同大小的写入
    test_sizes = [
        (100, 100, "Small"),
        (240, 240, "Medium"),
        (320, 240, "Full Screen"),
    ]
    
    for width, height, label in test_sizes:
        buffer_size = width * height * 2
        test_buffer = bytearray(buffer_size)
        
        # 填充测试数据
        for i in range(0, buffer_size, 2):
            test_buffer[i] = 0xFF
            test_buffer[i+1] = 0x00
        
        print(f"\nTest: {label} ({width}x{height}, {buffer_size} bytes)")
        
        times = []
        for i in range(10):
            # 设置窗口
            window_start = time.ticks_us()
            lcd.set_window(0, 0, width-1, height-1)
            window_time = time.ticks_diff(time.ticks_us(), window_start)
            
            # 写入数据
            write_start = time.ticks_us()
            lcd.write_data(test_buffer)
            write_time = time.ticks_diff(time.ticks_us(), write_start)
            
            total_time = window_time + write_time
            times.append({
                'window': window_time,
                'write': write_time,
                'total': total_time
            })
        
        # 计算平均值
        avg_window = sum(t['window'] for t in times) / len(times)
        avg_write = sum(t['write'] for t in times) / len(times)
        avg_total = sum(t['total'] for t in times) / len(times)
        
        print(f"  set_window: {avg_window/1000:.2f}ms")
        print(f"  write_data: {avg_write/1000:.2f}ms")
        print(f"  Total:      {avg_total/1000:.2f}ms")
        print(f"  Throughput: {buffer_size / (avg_total / 1000000) / 1024 / 1024:.2f} MB/s")


def test_framebuffer_vs_bytearray(lcd, width, height):
    """测试FrameBuffer vs bytearray写入性能"""
    print(f"\n=== FrameBuffer vs bytearray ({width}x{height}) ===")
    
    import framebuf
    
    buffer_size = width * height * 2
    
    # 创建bytearray
    byte_buffer = bytearray(buffer_size)
    for i in range(0, buffer_size, 2):
        byte_buffer[i] = 0xFF
        byte_buffer[i+1] = 0x00
    
    # 创建FrameBuffer
    fb_buffer = bytearray(buffer_size)
    fb = framebuf.FrameBuffer(fb_buffer, width, height, framebuf.RGB565)
    fb.fill(0xFF00)
    
    lcd.set_window(0, 0, width-1, height-1)
    
    # 测试bytearray
    times_bytearray = []
    for i in range(10):
        start = time.ticks_us()
        lcd.write_data(byte_buffer)
        times_bytearray.append(time.ticks_diff(time.ticks_us(), start))
    
    avg_bytearray = sum(times_bytearray) / len(times_bytearray)
    
    # 测试FrameBuffer
    times_fb = []
    for i in range(10):
        start = time.ticks_us()
        lcd.write_data(fb)
        times_fb.append(time.ticks_diff(time.ticks_us(), start))
    
    avg_fb = sum(times_fb) / len(times_fb)
    
    print(f"  bytearray:    {avg_bytearray/1000:.2f}ms")
    print(f"  FrameBuffer:  {avg_fb/1000:.2f}ms")
    print(f"  Difference:   {(avg_fb - avg_bytearray)/1000:.2f}ms ({(avg_fb/avg_bytearray - 1)*100:.1f}%)")


def test_spi_speed(lcd):
    """测试SPI速度"""
    print("\n=== SPI Speed Test ===")
    
    # 测试不同的SPI波特率
    baudrates = [
        40_000_000,
        60_000_000,
        80_000_000,
    ]
    
    buffer_size = 240 * 240 * 2
    test_buffer = bytearray(buffer_size)
    
    for baudrate in baudrates:
        # 重新配置SPI
        try:
            lcd.spi.init(baudrate=baudrate)
            
            times = []
            for i in range(5):
                lcd.set_window(0, 0, 239, 239)
                start = time.ticks_us()
                lcd.write_data(test_buffer)
                times.append(time.ticks_diff(time.ticks_us(), start))
            
            avg_time = sum(times) / len(times)
            throughput = buffer_size / (avg_time / 1000000) / 1024 / 1024
            
            print(f"  {baudrate/1000000:.0f}MHz: {avg_time/1000:.2f}ms ({throughput:.2f} MB/s)")
            
        except Exception as e:
            print(f"  {baudrate/1000000:.0f}MHz: Failed - {e}")