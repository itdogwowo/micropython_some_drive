# /action/stream_actions.py
import time

# --- 全局狀態 ---
_STREAM_STATE = {
    "active": False,
    "mode": "local",      # "local" (本地自跑) 或 "direct" (純串流)
    "frame_id": 0,
    "fps": 40,
    "last_recv_t": 0
}
_FRAME_COUNT = 0

CMD_STREAM_START = 0x3001
CMD_STREAM_STOP  = 0x3002
CMD_STREAM_FRAME = 0x3003

def get_frame_count():
    return _FRAME_COUNT

def reset_frame_count():
    global _FRAME_COUNT
    _FRAME_COUNT = 0
    
def is_streaming():
    return _STREAM_STATE["active"]

def get_mode():
    return _STREAM_STATE["mode"]

def on_stream_start(ctx, args):
    global _FRAME_COUNT, _STREAM_STATE
#     if not _STREAM_STATE["active"]: return
    
    _STREAM_STATE["active"] = True
    # 根據參數決定模式，如果帶了特定的 flag 則進入 direct 模式
    _STREAM_STATE["fps"] = args.get("fps", 40)
    _STREAM_STATE["mode"] = args.get("mode", "local") 
    _STREAM_STATE["frame_id"] = 0
    print(f"🎬 [Stream] 啟動 | 模式: {_STREAM_STATE['mode']} | FPS: {_STREAM_STATE['fps']}")
    app.apa.show()
    
    _FRAME_COUNT += 1
    
def on_stream_stop(ctx, args):
    global _STREAM_STATE
    _STREAM_STATE["active"] = False
    print(f"⏹️ [Stream] 停止 | 總幀數: {_STREAM_STATE['frame_id']}")

def on_stream_frame(ctx, args):
    """
    純串流模式 (Direct Mode) 的入口
    """
    global _STREAM_STATE
    if not _STREAM_STATE["active"]: return
    
    # 只要收到這個指令，我們就自動強制切換到 direct 模式 (高優先權)
    _STREAM_STATE["mode"] = "direct"
    
    app = ctx["app"]
    pixel_data = args.get("pixel_data")
    
    if app.apa and pixel_data:
        # 直接更新緩衝區並顯示
        app.apa.raw_buffer[:len(pixel_data)] = pixel_data
        app.apa.show(is_rgbw=True)
        
        _STREAM_STATE["frame_id"] = args.get("frame_id", 0)
        _STREAM_STATE["last_recv_t"] = time.ticks_ms()

def register(app):
    app.disp.on(CMD_STREAM_START, on_stream_start)
    app.disp.on(CMD_STREAM_STOP, on_stream_stop)
    app.disp.on(CMD_STREAM_FRAME, on_stream_frame)
    print("✅ [Action] Stream actions (Dual-Mode) registered")