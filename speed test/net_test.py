import socket, time, urandom, gc
try:
    import urequests as requests
except ImportError:
    import requests                # 某些移植版叫 requests

# ===== 1. 自行改成你板子實際的聯網方式 =====
# 例：ESP32 已經連上 Wi-Fi，ssid/pwd 在 boot.py 就做完
# import network
# sta = network.WLAN(network.STA_IF)
# sta.active(True)
# sta.connect('SSID','PASSWORD')
# 這裡直接「假設」網路已經 OK
# =========================================

# DOWNLOAD_URL = "http://192.168.1.88:5000/dl"   # 換成你的主機 IP
# UPLOAD_URL   = "http://192.168.1.88:5000/up"

DOWNLOAD_URL = "http://httpbin.org/bytes/5242880"   # 5 MB
UPLOAD_URL   = "http://httpbin.org/post"
DL_MB        = 5                                    # 下載幾 MB
UL_KB        = 512                                  # 上傳幾 KB
BUF_SZ       = 4096                                 # 每次讀寫 buffer

# ----- 小工具：human KB/s -----
def KBps(t_us, bytes_cnt):
    return bytes_cnt / 1024 * 1_000_000 / t_us

# ----- 2. 下載測速 -----
print("Downloading %d MB ..." % DL_MB)
gc.collect()
t0 = time.ticks_us()
r = requests.get(DOWNLOAD_URL, stream=True)
cnt = 0
buf = bytearray(BUF_SZ)
while True:
    n = r.raw.readinto(buf)
    if n == 0:
        break
    cnt += n
r.close()
t_dl = time.ticks_diff(time.ticks_us(), t0)
print("Download: %.1f KB/s  (%d bytes in %.2f s)" %
      (KBps(t_dl, cnt), cnt, t_dl/1_000_000))

# ----- 3. 上傳測速 -----
payload = bytearray(UL_KB * 1024)
for i in range(0, len(payload), 4):
    payload[i:i+4] = urandom.getrandbits(32).to_bytes(4, 'little')

print("Uploading %d KB ..." % UL_KB)
gc.collect()
t0 = time.ticks_us()
r = requests.post(UPLOAD_URL, data=payload)
r.close()
t_ul = time.ticks_diff(time.ticks_us(), t0)
print("Upload  : %.1f KB/s" % KBps(t_ul, len(payload)))

# ----- 4. TCP Ping（RTT） -----
HOST = "httpbin.org"
PORT = 80
print("TCP Ping %s:%d ..." % (HOST, PORT))
avg = 0
N = 5
for i in range(N):
    s = socket.socket()
    t0 = time.ticks_us()
    s.connect((HOST, PORT))
    t = time.ticks_diff(time.ticks_us(), t0)
    s.close()
    avg += t
    print("  #%d  %.0f ms" % (i+1, t/1000))
print("Avg RTT : %.0f ms" % (avg/N/1000))