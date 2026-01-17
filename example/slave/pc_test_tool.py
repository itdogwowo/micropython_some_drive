import socket
import time
import threading
import os
import hashlib
import struct
from lib.proto import Proto, StreamParser
from lib.schema_loader import SchemaStore
from lib.schema_codec import SchemaCodec

# ==================== 自動獲取 PC IP ====================
def get_local_ip():
    """獲取本機在區域網中的 IP，這對嵌入式設備自動連接 PC 至關重要"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 不需要真的連通，目的是誘發系統選擇正確的路由網卡
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

# ==================== 配置 ====================
PC_IP = get_local_ip()
WS_PORT = 8000
UDP_PORT = 9000
STREAM_PORT = 4050

class PCTestTool:
    def __init__(self):
        # 載入與 MCU 一致的 Schema 定義
        self.store = SchemaStore(dir_path="./schema")
        self.parser = StreamParser()
        self.conn = None       # WebSocket 連接對象
        self.slave_addr = None  # 記錄從機 (MCU) 的 IP
        self.running = True

    # -------------------- WebSocket 服務器 --------------------
    def start_ws_server(self):
        """啟動 WebSocket Server，負責與 MCU 建立長連接控制通道"""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', WS_PORT))
        s.listen(5)
        
        while self.running:
            try:
                s.settimeout(1.0)
                conn, addr = s.accept()
                print(f"\n🤝 [WS] 偵測到連接: {addr}")
                
                # RFC6455 握手簡化處理 (用於測試環境)
                request = conn.recv(1024).decode(errors='ignore')
                if "Upgrade: websocket" in request:
                    response = (
                        "HTTP/1.1 101 Switching Protocols\r\n"
                        "Upgrade: websocket\r\n"
                        "Connection: Upgrade\r\n"
                        "Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n\r\n"
                    )
                    conn.send(response.encode())
                    self.conn = conn
                    self.slave_addr = addr[0]
                    print(f"✅ [WS] 握手成功！Slave IP: {self.slave_addr}")
                    threading.Thread(target=self.receive_loop, daemon=True).start()
            except socket.timeout:
                continue
            except Exception as e:
                print(f"❌ [WS] 錯誤: {e}")

    def receive_loop(self):
        """解析來自 MCU 的數據包，轉換為可讀的 Schema JSON"""
        while self.conn:
            try:
                raw = self.conn.recv(4096)
                if not raw: break
                
                # 簡單的 WebSocket 解幀 (處理 Binary 0x82)
                if raw[0] == 0x82:
                    payload_len = raw[1] & 0x7F
                    off = 2
                    if payload_len == 126: off = 4
                    elif payload_len == 127: off = 10
                    data = raw[off:]
                else:
                    data = raw
                
                self.parser.feed(data)
                for ver, addr, cmd, payload in self.parser.pop():
                    c_def = self.store.get(cmd)
                    name = c_def["name"] if c_def else f"0x{cmd:04X}"
                    args = SchemaCodec.decode(c_def, payload) if c_def else {"raw": payload.hex()}
                    print(f"\n📥 [MCU->PC] {name}: {args}")
            except Exception as e:
                print(f"\n❌ [Recv] 失敗: {e}")
                break
        self.conn = None
        print("\n📴 [WS] Slave 連接中斷")

    def _pack_ws_frame(self, data: bytes):
        """將數據封裝成 WebSocket 二進制幀 (無 Mask)"""
        header = bytearray([0x82])
        ln = len(data)
        if ln < 126:
            header.append(ln)
        elif ln < 65536:
            header.append(126)
            header.extend(struct.pack(">H", ln))
        else:
            header.append(127)
            header.extend(struct.pack(">Q", ln))
        return header + data

    def send_cmd(self, cmd_id, args):
        """封裝自定義協議並通過 WebSocket 發送"""
        if not self.conn:
            print("⚠️ 請先等待 Slave 連接！")
            return
        
        c_def = self.store.get(cmd_id)
        if not c_def:
            print(f"❌ Schema 中找不到命令 0x{cmd_id:04X}")
            return
            
        payload = SchemaCodec.encode(c_def, args)
        pkt = Proto.pack(cmd_id, payload)
        
        try:
            self.conn.send(self._pack_ws_frame(pkt))
        except Exception as e:
            print(f"❌ 發送失敗: {e}")

    # -------------------- 文件上傳邏輯 --------------------
    def upload_file_interactive(self):
        """
        交互式上傳引導：輸入路徑並上傳
        """
        if not self.conn:
            print("⚠️ [Error] MCU 尚未連接，無法上傳文件。")
            return

        # 1. 獲取本地文件路徑
        local_path = input("\n📂 請輸入要上傳的本地文件路徑 (e.g., test.bin): ").strip()
        # 清除引號 (防止用戶直接拖文件進來產生的引號)
        local_path = local_path.replace('"', '').replace("'", "")
        
        if not os.path.exists(local_path):
            print(f"❌ [Error] 找不到本地文件: {local_path}")
            return

        # 2. 獲取遠端路徑 (預設使用同名文件)
        default_remote = "/" + os.path.basename(local_path)
        remote_path = input(f"💾 請輸入遠端保存路徑 (直接 Enter 使用 {default_remote}): ").strip()
        if not remote_path:
            remote_path = default_remote

        # 3. 執行發送
        self.upload_file(local_path, remote_path)

    def upload_file(self, local_file, remote_path):
        """
        優化版上傳：精確控制流量，防止 MCU 緩衝區溢出
        """
        print(f"\n🚀 [File] 準備上傳: {local_file}")
        
        try:
            with open(local_file, "rb") as f:
                file_data = f.read()
            
            total_size = len(file_data)
            sha256_bytes = hashlib.sha256(file_data).digest()
            file_id = int(time.time()) & 0xFFFF
            
            # --- 性能參數調整 ---
            # 減小分片大小：讓 MCU 每次 read 壓力變小
            chunk_size = 512  
            # 每發送 N 包就進行一次大停頓 (這回給 MCU 呼吸的空間)
            burst_count = 5  
            # 每包之間的微小延遲 (防止 Socket 溢出)
            step_delay = 0.05 
            # 每批次之間的大延遲 (給 MCU 寫入 Flash 的時間)
            burst_delay = 0.1 

            # 1. FILE_BEGIN
            self.send_cmd(0x2001, {
                "file_id": file_id,
                "total_size": total_size,
                "chunk_size": chunk_size,
                "sha256": sha256_bytes,
                "path": remote_path
            })
            print(f"   ﹂ ⏳ 等待 MCU 初始化 Flash (給予 2 秒預留時間)...")
            time.sleep(2.0) 

            # 2. FILE_CHUNK
            sent_bytes = 0
            start_time = time.time()
            
            chunks = [file_data[i:i + chunk_size] for i in range(0, total_size, chunk_size)]
            total_chunks = len(chunks)

            for idx, chunk in enumerate(chunks):
                self.send_cmd(0x2002, {
                    "file_id": file_id,
                    "offset": idx * chunk_size,
                    "data": chunk
                })
                
                sent_bytes += len(chunk)
                
                # --- 強制流控 ---
                # 每包基本的發送間隔
                time.sleep(step_delay) 
                
                # 每發送一個批次，進行深度休眠，等待 MCU 完成內存回寫
                if (idx + 1) % burst_count == 0:
                    progress = (sent_bytes / total_size) * 100
                    print(f"   ﹂ 📤 已發送 {progress:6.2f}% | 批次冷卻中...", end="\r")
                    time.sleep(burst_delay) # 核心：給 Flash 喘息時間

            # 3. FILE_END
            # 發送結束指令前，多等一下，確保最後一包已經流進 MCU
            time.sleep(1.0)
            self.send_cmd(0x2003, {"file_id": file_id})
            
            duration = time.time() - start_time
            print(f"\n✅ [File] 上傳結束！耗時: {duration:.2f}s | 速度: {(total_size/1024)/duration:.2f} KB/s")

        except Exception as e:
            print(f"\n❌ [File] 發生錯誤: {e}")

    # -------------------- 其他功能 --------------------
    def broadcast_discover(self):
        """UDP 廣播，讓 MCU 發現伺服器 IP 並回連 WebSocket"""
        print(f"📡 [Discovery] 廣播本機 IP: {PC_IP} 到端口 {UDP_PORT}")
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        cmd_def = self.store.get(0x1001)
        payload = SchemaCodec.encode(cmd_def, {
            "server_ip": PC_IP,
            "ws_url": f"ws://{PC_IP}:{WS_PORT}/ws"
        })
        pkt = Proto.pack(0x1001, payload)
        s.sendto(pkt, ('255.255.255.255', UDP_PORT))
        s.close()

    def send_udp_frame(self):
        """透過 UDP 發送快速燈光幀 (不經過 WebSocket 握手，追求極致低延遲)"""
        if not self.slave_addr:
            print("⚠️ 尚未知道 Slave IP，請先執行 1.廣播發現")
            return
        
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        cmd_def = self.store.get(0x3003)
        # 測試數據：336 顆 LED
        pixel_data = b'\x1F\x00\x00\x00' * 336 
        payload = SchemaCodec.encode(cmd_def, {
            "frame_id": int(time.time()),
            "pixel_data": pixel_data
        })
        pkt = Proto.pack(0x3003, payload)
        s.sendto(pkt, (self.slave_addr, STREAM_PORT))
        s.close()
        print(f"✨ [UDP] 已向 {self.slave_addr} 發送燈光包")
        
    def run(self):
        """主循環菜單"""
        threading.Thread(target=self.start_ws_server, daemon=True).start()
        
        while True:
            print(f"\n--- 🚀 Net-Light 專業開發者調試工具 ({PC_IP}) ---")
            print("1. [Discovery] 發送廣播 (讓 MCU 找我)")
            print("2. [Uploader]  上傳本地文件 (手動指定路徑)")
            print("3. [Stream]    啟動快速串流模式")
            print("4. [UDP Frame] 發送單幀測試數據")
            print("5. [Stream]    停止串流模式")
            print("q. [Exit]      退出程序")
            
            c = input("\n👉 選擇指令: ").lower()
            if c == '1': self.broadcast_discover()
            elif c == '2': self.upload_file_interactive()
            elif c == '3': self.send_cmd(0x3001, {"fps": 40})
            elif c == '4': self.send_udp_frame()
            elif c == '5': self.send_cmd(0x3002, {})
            elif c == 'q': break

if __name__ == "__main__":
    # 生成測試文件
    if not os.path.exists("test.bin"):
        with open("test.bin", "wb") as f:
            f.write(os.urandom(1024 * 50)) 
            
    try:
        PCTestTool().run()
    except KeyboardInterrupt:
        print("\n👋 程式已退出")