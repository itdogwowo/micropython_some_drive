# test_udp_broadcast.py
import socket
import json
import time

def test_broadcast():
    """測試 UDP 廣播"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    
    # 綁定到所有網卡
    sock.bind(('0.0.0.0', 0))
    
    message = json.dumps({
        "cmd": "DISCOVER",
        "timestamp": time.time()
    })
    
    print(f"發送廣播: {message}")
    
    # 嘗試多個廣播地址
    broadcast_addrs = [
        '255.255.255.255',     # 全網廣播
        '10.10.255.255',       # /16 網段廣播
        '10.255.255.255',      # /8 網段廣播
    ]
    
    for addr in broadcast_addrs:
        try:
            sock.sendto(message.encode('utf-8'), (addr, 9000))
            print(f"✅ 已發送到 {addr}:9000")
        except Exception as e:
            print(f"❌ 發送到 {addr} 失敗: {e}")
    
    sock.close()

if __name__ == '__main__':
    test_broadcast()