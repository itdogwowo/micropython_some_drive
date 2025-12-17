#!/usr/bin/env python3
import http.server, socketserver, socket, time, os, sys

PORT   = 5000
DL_MB  = 5               # 下載檔大小 MB
UL_KB  = 512             # 上傳後要回送的資料大小 KB

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):   # 關掉日誌
        pass

    # ---- 1. 下載測速 /dl ----
    def do_GET(self):
        if self.path != '/dl':
            self.send_error(404)
            return
        sz = DL_MB * 1024 * 1024
        self.send_response(200)
        self.send_header('Content-Length', str(sz))
        self.send_header('Content-Type', 'application/octet-stream')
        self.end_headers()
        # 懶得讀檔，直接噴 0x00
        blk = b'\0' * 65536
        left = sz
        while left:
            chunk = blk if left >= len(blk) else blk[:left]
            self.wfile.write(chunk)
            left -= len(chunk)

    # ---- 2. 上傳測速 /up ----
    def do_POST(self):
        if self.path != '/up':
            self.send_error(404)
            return
        clen = int(self.headers.get('Content-Length', 0))
        # 把上傳資料全讀進黑洞
        while clen:
            chunk = self.rfile.read(min(clen, 65536))
            if not chunk:
                break
            clen -= len(chunk)
        # 回送 UL_KB 亂數，讓客戶端有下載流量
        payload = os.urandom(UL_KB * 1024)
        self.send_response(200)
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

# ---- 3. TCP Ping 監聽（echo 1 byte）----
def tcp_ping_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', PORT))
    sock.listen(5)
    while True:
        try:
            conn, addr = sock.accept()
            conn.recv(1)   # 收 1 byte 立即關閉
            conn.close()
        except Exception:
            pass

if __name__ == '__main__':
    import threading
    # 把 TCP Ping 放背景
    t = threading.Thread(target=tcp_ping_server, daemon=True)
    t.start()
    # HTTP 主循環
    with socketserver.TCPServer(('0.0.0.0', PORT), Handler) as httpd:
        print("Speed server listening on 0.0.0.0:%d" % PORT)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            sys.exit(0)