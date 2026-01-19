from machine import Pin, SDCard
import os, time, urandom
from esp32 import LDO

l = LDO(4, 3300, adjustable=True)
# ===== 1. 掛載 SD（你的腳位） =====
sd = SDCard(slot=0, width=4,
            sck=43, cmd=44,
            data=(39, 40, 41, 42),
            freq=40_000_000)
os.mount(sd, '/sd')
root_phat = '/sd'
root_phat = ''

# ===== 2. 測試參數 =====
TEST_FILE = f'{root_phat}/bench.dat'
FILE_MB   = 10               # 檔案大小 (MB)
BUF_KB    = 64               # 一次讀寫的 buffer (KB)
LOOP      = (FILE_MB * 1024) // BUF_KB

buf = bytearray(BUF_KB * 1024)
# 預先填亂數，避免寫入被壓縮
for i in range(0, len(buf), 4):
    buf[i:i+4] = urandom.getrandbits(32).to_bytes(4, 'little')

# ===== 3. 連續寫入 =====
print("Writing %d MB ..." % FILE_MB)
t0 = time.ticks_ms()
with open(TEST_FILE, 'wb') as f:
    for _ in range(LOOP):
        f.write(buf)
t_w = time.ticks_diff(time.ticks_ms(), t0)
os.sync()                      # 確保真正 flush 到卡

# ===== 4. 連續讀出 =====
print("Reading %d MB ..." % FILE_MB)
t0 = time.ticks_ms()
with open(TEST_FILE, 'rb') as f:
    for _ in range(LOOP):
        f.readinto(buf)
t_r = time.ticks_diff(time.ticks_ms(), t0)

# ===== 5. 結果 =====
def KBps(t_ms, size_MB):
    return size_MB * 1024 * 1000 / t_ms

print("Write: %.1f KB/s" % KBps(t_w, FILE_MB))
print("Read : %.1f KB/s" % KBps(t_r, FILE_MB))

# 清掉測試檔
os.remove(TEST_FILE)



TEST_DIR = f'{root_phat}/small_test'
try:
    os.mkdir(TEST_DIR)          # 只建一層，MicroPython 夠用
except OSError:                 # 已存在會拋 OSError: EEXIST
    pass

FILE_CNT  = 1000          # 寫 100 個小檔
SIZE_EACH = 4096         # 4 kB
buf = bytearray(SIZE_EACH)
for i in range(0, SIZE_EACH, 4):
    buf[i:i+4] = urandom.getrandbits(32).to_bytes(4, 'little')

print("Writing %d × 4 kB files ..." % FILE_CNT)
t0 = time.ticks_ms()
for n in range(FILE_CNT):
    with open(TEST_DIR + '/%04d.log' % n, 'wb') as f:
        f.write(buf)
os.sync()
t_w = time.ticks_diff(time.ticks_ms(), t0)

print("Reading %d × 4 kB files ..." % FILE_CNT)
t0 = time.ticks_ms()
for n in range(FILE_CNT):
    with open(TEST_DIR + '/%04d.log' % n, 'rb') as f:
        f.readinto(buf)
t_r = time.ticks_diff(time.ticks_ms(), t0)

total_kb = FILE_CNT * 4
print("Small-file write: %.1f KB/s" % (total_kb * 1000 / t_w))
print("Small-file read : %.1f KB/s" % (total_kb * 1000 / t_r))

# 清理
for n in range(FILE_CNT):
    os.remove(TEST_DIR + '/%04d.log' % n)
os.rmdir(TEST_DIR)

