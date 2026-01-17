import time

import gc

import network

import machine

from app import App

from lib.net_bus import NetBus

from apa102 import APA102

# 🚀 提前導入，避免在循環中動態導入產生開銷

from action.stream_actions import is_streaming, get_mode, get_frame_count

CONFIG = {

    "refresh_rate_ms": 1,         # 🚀 縮短為 1ms，讓 NetBus 響應達到物理極限

    "discovery_port": 9000,

    "stream_port": 4050,

    "heartbeat_interval": 10000,

    "local_fps_ms": 25,           # 本地播放的時鐘步長 (40 FPS)

}

def setup_network():

    lan = network.LAN(mdc=31, mdio=52, phy_addr=1, phy_type=network.PHY_IP101, ref_clk=50)

    lan.active(True)

    for _ in range(20): # 等待 10 秒

        if lan.isconnected(): return True

        time.sleep(0.5)

    return False

def main():

    

    if not setup_network(): return

    

    apa = APA102(num_leds=336,sck_pin=22, mosi_pin=23)

    app = App(apa_driver=apa)

    app.disp.debug_level = 1 

    # 初始化總線

    ctrl_bus = NetBus(NetBus.TYPE_WS, app=app, label="CTRL-WS")

    discovery_bus = NetBus(NetBus.TYPE_UDP, app=app, label="UDP-DISCV")

    discovery_bus.connect(None, CONFIG["discovery_port"])

    stream_bus = NetBus(NetBus.TYPE_UDP, app=app, label="UDP-FAST")

    stream_bus.connect(None, CONFIG["stream_port"])

    # 🚀 將狀態函數緩存為本地變量，速度提升 5-10%

    check_streaming = is_streaming

    check_mode = get_mode

    file_rx = app.file_rx

    def on_connect_request(url):

        if not ctrl_bus.connected:

            parts = url.replace("ws://", "").split("/", 1)

            host_port = parts[0]

            path = "/" + parts[1] if len(parts) > 1 else "/"

            host = host_port.split(":")[0]

            port = int(host_port.split(":")[1]) if ":" in host_port else 80

            ctrl_bus.connect(host, port, path=path)

    ctx_extra = {"on_connect": on_connect_request}

    

    # 初始化狀態字典

    s = {

        "f_local": None,

        "is_playing": False,

        "last_hbeat": 0,

        "last_frame_t": 0,

        "has_next_frame": False,

        "frame_count": 0,       # 🚀 新增：累積播放幀數

        "last_report_t": 0      # 🚀 新增：上次報告時間

    }

    print("🚀 [Core] 極速輪詢模式已啟動")

    

    # 🚀 為了性能，我們將 ticks_ms 緩存

    get_ticks = time.ticks_ms

    diff_ticks = time.ticks_diff

    

    

    s["last_report_t"] = get_ticks()

    try:

        while True:

            now = get_ticks()

            

            # --- 1. 網路優先級 (始終最高) ---

            discovery_bus.poll(**ctx_extra)

            if ctrl_bus.connected: ctrl_bus.poll()

            stream_bus.poll() 

            # 2. 第二優先級：本地播放邏輯

            # 使用緩存的函數 check_streaming()，不產生 import 查找

            is_active = check_streaming()

            if is_active:

                if check_mode() == "local":

                    # --- A. 本地播放 (Local Mode) ---

                    if check_mode() == "local":

                        if not s["is_playing"]:

                            try:

                                s["f_local"] = open('data.bin', 'rb')

                                s["is_playing"] = True

                            except: s["is_playing"] = False

                    

                    # 預讀取

                    if s["is_playing"] and not s["has_next_frame"]:

                        if s["f_local"].readinto(apa.raw_buffer) == 0:

                            s["f_local"].seek(0)

                            s["f_local"].readinto(apa.raw_buffer)

                        s["has_next_frame"] = True

                    # 觸發顯示

                    if s["has_next_frame"] and diff_ticks(now, s["last_frame_t"]) >= CONFIG["local_fps_ms"]:

                        s["last_frame_t"] = now

                        apa.show() 

                        s["has_next_frame"] = False

                        s["frame_count"] += 1 # 🚀 計數

                # --- B. 純串流 (Direct Mode) ---

                else:

                    # 在 Direct 模式下，計數器需要在 stream_actions.py 裡遞增

                    # 或者從這裡動態讀取，我們在 action 裡增加一個全局 count

                    if s["f_local"]:

                        s["f_local"].close()

                        s["f_local"] = None

                        s["is_playing"] = False

                        

                    s["frame_count"] = get_frame_count()

            else:

                # 靜止狀態清理

                if s["is_playing"]:

                    if s["f_local"]: s["f_local"].close()

                    s["f_local"] = None

                    s["is_playing"] = False

                    apa.clear()

                    apa.show_raw()

                    

                    

            if diff_ticks(now, s["last_hbeat"]) > CONFIG["heartbeat_interval"]:

                # 計算實際 FPS

                elapsed_ms = diff_ticks(now, s["last_report_t"])

                actual_fps = (s["frame_count"] * 1000) / elapsed_ms if elapsed_ms > 0 else 0

                

                gc.collect()

                mem = gc.mem_free() // 1024

                

                # 豪華日誌輸出面版

                print("-" * 40)

                print(f"📊 [Monitor] Actual FPS: {actual_fps:.2f} / {1000/CONFIG['local_fps_ms']:.0f}")

                print(f"💓 [System] RAM: {mem}KB | Frames: {s['frame_count']}")

                print("-" * 40)

                

                # 重置計數器進入下一個週期

                s["last_hbeat"] = now

                s["last_report_t"] = now

                s["frame_count"] = 0 

                if check_mode() != "local": # 同步重置 Direct 模式的計數器

                    from action.stream_actions import reset_frame_count

                    reset_frame_count()

            # 🚀 ESP32-P4 強大之處在於不需要長的 sleep，1ms 即可維持穩定

#             time.sleep_ms(CONFIG["refresh_rate_ms"])

            time.sleep_ms(1)

    except KeyboardInterrupt: pass

    finally:

        if s["f_local"]: s["f_local"].close()

        apa.deinit()

if __name__ == "__main__":

    main()