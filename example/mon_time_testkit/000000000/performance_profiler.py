# =========================================
# performance_profiler.py - 性能分析工具
# =========================================

import time
import gc

class PerformanceProfiler:
    """性能分析器 - 精确定位瓶颈"""
    
    def __init__(self):
        self.timings = {}
        self.call_counts = {}
    
    def measure(self, label):
        """装饰器:测量函数执行时间"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                start = time.ticks_us()  # 使用微秒级精度
                result = func(*args, **kwargs)
                elapsed = time.ticks_diff(time.ticks_us(), start)
                
                if label not in self.timings:
                    self.timings[label] = []
                    self.call_counts[label] = 0
                
                self.timings[label].append(elapsed)
                self.call_counts[label] += 1
                
                return result
            return wrapper
        return decorator
    
    def time_block(self, label):
        """上下文管理器:测量代码块时间"""
        return TimingContext(self, label)
    
    def print_report(self, top_n=20):
        """打印性能报告"""
        print("\n" + "="*60)
        print("PERFORMANCE REPORT (times in microseconds)")
        print("="*60)
        
        # 计算统计数据
        stats = []
        for label, times in self.timings.items():
            if len(times) == 0:
                continue
            
            total = sum(times)
            count = len(times)
            avg = total / count
            min_time = min(times)
            max_time = max(times)
            
            stats.append({
                'label': label,
                'total': total,
                'count': count,
                'avg': avg,
                'min': min_time,
                'max': max_time
            })
        
        # 按总时间排序
        stats.sort(key=lambda x: x['total'], reverse=True)
        
        # 打印表头
        print(f"{'Function':<30} {'Calls':>8} {'Total(ms)':>10} {'Avg(us)':>10} {'Min(us)':>10} {'Max(us)':>10}")
        print("-"*60)
        
        # 打印统计
        for s in stats[:top_n]:
            print(f"{s['label']:<30} {s['count']:>8} {s['total']/1000:>10.2f} {s['avg']:>10.1f} {s['min']:>10} {s['max']:>10}")
        
        print("="*60)
    
    def reset(self):
        """重置统计"""
        self.timings = {}
        self.call_counts = {}


class TimingContext:
    """计时上下文管理器"""
    
    def __init__(self, profiler, label):
        self.profiler = profiler
        self.label = label
        self.start = 0
    
    def __enter__(self):
        self.start = time.ticks_us()
        return self
    
    def __exit__(self, *args):
        elapsed = time.ticks_diff(time.ticks_us(), self.start)
        
        if self.label not in self.profiler.timings:
            self.profiler.timings[self.label] = []
            self.profiler.call_counts[self.label] = 0
        
        self.profiler.timings[self.label].append(elapsed)
        self.profiler.call_counts[self.label] += 1


# 全局分析器实例
profiler = PerformanceProfiler()
