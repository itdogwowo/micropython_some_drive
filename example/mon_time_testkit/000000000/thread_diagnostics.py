# =========================================
# thread_diagnostics.py - 线程诊断工具
# =========================================

import _thread
import time
import gc

class ThreadDiagnostics:
    """线程诊断工具"""
    
    def __init__(self):
        self.test_counter = 0
        self.thread_started = False
        self.thread_completed = False
        self.thread_error = None
        
    def test_basic_threading(self):
        """测试1: 基础线程功能"""
        print("\n=== Test 1: Basic Threading ===")
        
        self.test_counter = 0
        self.thread_started = False
        self.thread_completed = False
        
        def worker():
            self.thread_started = True
            print("  Worker thread started")
            for i in range(5):
                self.test_counter += 1
                print(f"  Worker count: {self.test_counter}")
                time.sleep_ms(100)
            self.thread_completed = True
            print("  Worker thread completed")
        
        try:
            _thread.start_new_thread(worker, ())
            print("✓ Thread started successfully")
            
            # 等待线程完成
            timeout = 0
            while not self.thread_completed and timeout < 1000:
                time.sleep_ms(10)
                timeout += 10
            
            if self.thread_completed:
                print(f"✓ Thread completed. Counter: {self.test_counter}")
                return True
            else:
                print("✗ Thread timeout!")
                return False
                
        except Exception as e:
            print(f"✗ Thread failed: {e}")
            return False
    
    def test_thread_with_args(self):
        """测试2: 带参数的线程"""
        print("\n=== Test 2: Thread with Arguments ===")
        
        self.test_counter = 0
        result = []
        
        def worker(value, multiplier):
            print(f"  Worker received: value={value}, multiplier={multiplier}")
            for i in range(3):
                result.append(value * multiplier * (i+1))
                time.sleep_ms(50)
            print(f"  Worker result: {result}")
        
        try:
            _thread.start_new_thread(worker, (5, 10))
            print("✓ Thread with args started")
            
            time.sleep_ms(500)
            
            if len(result) == 3:
                print(f"✓ Results: {result}")
                return True
            else:
                print(f"✗ Expected 3 results, got {len(result)}")
                return False
                
        except Exception as e:
            print(f"✗ Thread failed: {e}")
            return False
    
    def test_thread_lock(self):
        """测试3: 线程锁"""
        print("\n=== Test 3: Thread Lock ===")
        
        lock = _thread.allocate_lock()
        shared_counter = [0]  # 使用list避免作用域问题
        
        def worker(worker_id):
            for i in range(3):
                with lock:
                    old_value = shared_counter[0]
                    time.sleep_ms(10)  # 模拟竞争
                    shared_counter[0] = old_value + 1
                    print(f"  Worker {worker_id}: {shared_counter[0]}")
        
        try:
            _thread.start_new_thread(worker, (1,))
            _thread.start_new_thread(worker, (2,))
            print("✓ Two threads started with lock")
            
            time.sleep_ms(500)
            
            if shared_counter[0] == 6:
                print(f"✓ Shared counter correct: {shared_counter[0]}")
                return True
            else:
                print(f"✗ Expected 6, got {shared_counter[0]}")
                return False
                
        except Exception as e:
            print(f"✗ Thread lock failed: {e}")
            return False
    
    def test_jpeg_decode_thread(self):
        """测试4: JPEG解码线程 (模拟实际场景)"""
        print("\n=== Test 4: JPEG Decode Simulation ===")
        
        decode_started = [False]
        decode_completed = [False]
        decode_frame = [-1]
        
        def decode_worker(frame_index):
            decode_started[0] = True
            print(f"  Decoding frame {frame_index}...")
            
            # 模拟JPEG解码耗时
            start = time.ticks_ms()
            time.sleep_ms(100)  # 模拟解码时间
            elapsed = time.ticks_diff(time.ticks_ms(), start)
            
            decode_frame[0] = frame_index
            decode_completed[0] = True
            print(f"  Decode completed in {elapsed}ms")
        
        try:
            _thread.start_new_thread(decode_worker, (42,))
            print("✓ Decode thread started")
            
            # 主线程继续执行
            print("  Main thread continues...")
            main_counter = 0
            while not decode_completed[0] and main_counter < 20:
                print(f"  Main loop: {main_counter}")
                time.sleep_ms(10)
                main_counter += 1
            
            if decode_completed[0] and decode_frame[0] == 42:
                print(f"✓ Decode completed: frame {decode_frame[0]}")
                return True
            else:
                print("✗ Decode failed or timeout")
                return False
                
        except Exception as e:
            print(f"✗ Decode thread failed: {e}")
            return False
    
    def test_memory_allocation_in_thread(self):
        """测试5: 线程中的内存分配"""
        print("\n=== Test 5: Memory Allocation in Thread ===")
        
        gc.collect()
        initial_free = gc.mem_free()
        print(f"  Initial free: {initial_free} bytes")
        
        allocated_size = [0]
        allocation_success = [False]
        
        def worker():
            try:
                # 在线程中分配大块内存
                test_buffer = bytearray(50000)
                allocated_size[0] = len(test_buffer)
                test_buffer[0] = 0xFF
                test_buffer[-1] = 0xFF
                allocation_success[0] = True
                print(f"  Thread allocated {allocated_size[0]} bytes")
                time.sleep_ms(100)
            except MemoryError as e:
                print(f"  Thread memory error: {e}")
            except Exception as e:
                print(f"  Thread error: {e}")
        
        try:
            _thread.start_new_thread(worker, ())
            time.sleep_ms(500)
            
            gc.collect()
            final_free = gc.mem_free()
            print(f"  Final free: {final_free} bytes")
            
            if allocation_success[0]:
                print(f"✓ Thread allocated {allocated_size[0]} bytes")
                return True
            else:
                print("✗ Thread allocation failed")
                return False
                
        except Exception as e:
            print(f"✗ Test failed: {e}")
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "="*50)
        print("THREAD DIAGNOSTICS")
        print("="*50)
        
        results = []
        
        # 测试1: 基础线程
        results.append(("Basic Threading", self.test_basic_threading()))
        time.sleep_ms(200)
        
        # 测试2: 带参数
        results.append(("Thread with Args", self.test_thread_with_args()))
        time.sleep_ms(200)
        
        # 测试3: 线程锁
        results.append(("Thread Lock", self.test_thread_lock()))
        time.sleep_ms(200)
        
        # 测试4: JPEG解码模拟
        results.append(("JPEG Decode Sim", self.test_jpeg_decode_thread()))
        time.sleep_ms(200)
        
        # 测试5: 内存分配
        results.append(("Memory Allocation", self.test_memory_allocation_in_thread()))
        time.sleep_ms(200)
        
        # 打印结果
        print("\n" + "="*50)
        print("TEST RESULTS")
        print("="*50)
        for name, result in results:
            status = "✓ PASS" if result else "✗ FAIL"
            print(f"{status} - {name}")
        
        passed = sum(1 for _, r in results if r)
        total = len(results)
        print(f"\nTotal: {passed}/{total} tests passed")
        
        return passed == total


# =========================================
# 使用方法
# =========================================

# 在REPL中运行:
from thread_diagnostics import ThreadDiagnostics
diag = ThreadDiagnostics()
diag.run_all_tests()
