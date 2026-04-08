import os
import gc
from uio import BytesIO

class BufferReader:
    def __init__(self, file_paths, buffer_ratio=0.25, min_buffer=4096):
        # 初始化文件句柄
        self.files = [open(path, 'rb') for path in file_paths]
        self.file_sizes = [os.stat(path)[6] for path in file_paths]
        
        # 计算可用内存
        gc.collect()
        free_mem = gc.mem_free()  # 对于没有 gc 的环境改用 psutil
        self.buffer_size = max(min_buffer, int(free_mem * buffer_ratio))
        print(f"Allocated buffer: {self.buffer_size//1024}KB")
        
        # 初始化缓存系统
        self._current_file_idx = -1
        self._buffer = BytesIO()
        self._buffer_start = 0
        self._buffer_end = 0


    def disk_info(self,path):
        statvfs_fields  = ['bsize','frsize','blocks','bfree','bavail','files','ffree']
        vfs = dict(zip(statvfs_fields, os.statvfs(path)))
        total = vfs['bsize'] * vfs['blocks'] / 1024
        used  = vfs['bsize'] * (vfs['blocks'] - vfs['bfree']) / 1024
        avail = vfs['bsize'] * vfs['bavail'] / 1024
        used_percent = round(float(used) / float(used + avail) * 100, 2)
        print (f'總容量為： {total}')
        print (f'使用量為： {used}')
        print (f'有效容量為： {avail}')
        print (f'使用率為： {used_percent}')
        # 240_000_000
        # machine.freq(240_000_000)

    def _load_to_buffer(self, file_idx, start, length, stride):
        """智能缓存加载策略"""
        file = self.files[file_idx]
        file_size = self.file_sizes[file_idx]
        
        # 判断是否适合批量预读
        if stride == 1:  # 连续读取
            read_size = min(length, self.buffer_size)
            file.seek(start)
            data = file.read(read_size)
            return data
        else:
            # 计算间隔读取的总跨度
            total_span = start + (length-1)*stride + 1
            if total_span <= self.buffer_size:
                # 批量读取跨度范围内的数据
                file.seek(start)
                bulk_data = file.read(total_span)
                # 内存中隔位提取
                return bytes(bulk_data[i*stride] for i in range(length))
            else:
                # 标记需要按需读取
                return None

    def read_generator(self, file_idx, seek=0, length=None, stride=1):
        """智能读取生成器"""
        if file_idx < 0 or file_idx >= len(self.files):
            raise ValueError("Invalid file index")
        
        file_size = self.file_sizes[file_idx]
        length = length or (file_size - seek)
        
        # 自动选择读取策略
        strategy = 'direct' if stride > 32 or length > self.buffer_size else 'buffered'
        
        if strategy == 'buffered':
            # 缓存友好型读取
            chunk_size = self.buffer_size // (stride or 1)
            for i in range(0, length, chunk_size):
                chunk_len = min(chunk_size, length - i)
                data = self._load_to_buffer(file_idx, seek + i*stride, chunk_len, stride)
                if data:
                    yield from data
                else:
                    # Fallback 到直接读取
                    for j in range(chunk_len):
                        pos = seek + (i + j)*stride
                        if pos >= file_size:
                            break
                        self.files[file_idx].seek(pos)
                        yield self.files[file_idx].read(1)
        else:
            # 直接按需读取
            for i in range(length):
                pos = seek + i*stride
                if pos >= file_size:
                    break
                self.files[file_idx].seek(pos)
                yield self.files[file_idx].read(1)


    def read_rgb_buffer(file_idx,now=0,led_n=None, buf_seek=None,buf_read=None):
        led_n = 1  if led_n == None else led_n
        rgb_LED = 3 * led_n  if buf_read == None else buf_read
        offset = rgb_LED  * now  if buf_seek == None else buf_seek

        if file_idx < 0 or file_idx >= len(self.files):
            raise ValueError("Invalid file index")
        
        file_size = self.file_sizes[file_idx]
        length = rgb_LED

        if offset >= file_size:
            break
        self.files[file_idx].seek(offset)
        return self.files[file_idx].read(rgb_LED)




    def close(self):
        """清理资源"""
        for f in self.files:
            f.close()
        self._buffer.close()
