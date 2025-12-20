import usocket as socket
import network
import time


SSID = ""
PASSWORD = ""

PORT = 5000
PROTOCOL = "UDP"  # 或 "TCP"
PROTOCOL = "TCP"  # 或 "TCP"

def connect_wifi():
    """連接到 WiFi"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    if not wlan.isconnected():
        print(f"Connecting to {SSID}...")
        wlan.connect(SSID, PASSWORD)
        
        # 等待連接
        for i in range(10):
            if wlan.isconnected():
                break
            print(f"等待... {i+1}/10")
            time.sleep(1)
    
    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        print(f"Connected! IP: {ip}")
        return ip
    else:
        print("Connection failed")
        return None

def handle_tcp():
    """處理 TCP 連接"""
    print("Starting TCP server...")
    
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('0.0.0.0', PORT))
    s.listen(1)
    
    print(f"TCP server listening on port {PORT}")
    
    try:
        while True:
            print("Waiting for connection...")
            conn, addr = s.accept()
            print(f"Connected by {addr}")
            
            try:
                while True:
                    data = conn.recv(1024)
                    if not data:
                        break
                    
                    try:
                        msg = data.decode('utf-8')
                    except:
                        msg = str(data)
                    
                    print(f"Received: {msg}")
                    print(f"Received: {data}")
                    
                    # 回傳確認
                    conn.send(f"ACK: {msg}".encode())
                    
            except Exception as e:
                print(f"Error: {e}")
            finally:
                conn.close()
                print("Connection closed")
                
    except KeyboardInterrupt:
        print("Server stopped")
    finally:
        s.close()

def handle_udp():
    """處理 UDP 連接"""
    print("Starting UDP server...")
    
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(('0.0.0.0', PORT))
    
    print(f"UDP server listening on port {PORT}")
    
    try:
        while True:
            try:
                data, addr = s.recvfrom(1024)
                
                try:
                    msg = data.decode('utf-8')
                except:
                    msg = str(data)
                
                print(f"From {addr}: {msg}")
                
                # 回傳確認
                s.sendto(f"ACK: {msg}".encode(), addr)
                
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(0.1)
                
    except KeyboardInterrupt:
        print("Server stopped")
    finally:
        s.close()

def main():
    """主程序"""
    print("MicroPython Socket Receiver")
    print("=" * 30)
    
    ip = connect_wifi()
    if not ip:
        return
    
    print(f"Using protocol: {PROTOCOL}")
    
    if PROTOCOL.upper() == "TCP":
        handle_tcp()
    elif PROTOCOL.upper() == "UDP":
        handle_udp()
    else:
        print("Invalid protocol")

if __name__ == "__main__":
    main()

