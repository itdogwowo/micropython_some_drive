# /action/file_actions.py
import gc

# 協議指令定義
CMD_FILE_BEGIN = 0x2001
CMD_FILE_CHUNK = 0x2002
CMD_FILE_END   = 0x2003

# 1. 先定義 Begin
def on_file_begin(ctx, args):
    app = ctx["app"]
    ok = app.file_rx.begin(args)
    err = app.file_rx.last_error
    if ok:
        print(f"📂 [File] Begin OK: {args.get('path')} ({args.get('total_size')} bytes)")
    else:
        print(f"📂 [File] Begin FAIL: {err}")

# 2. 再定義 Chunk (必須在 register 之前)
def on_file_chunk(ctx, args):
    app = ctx["app"]
    # 執行 chunk 寫入 (內部會處理 sh256.update 和磁碟寫入)
    ok = app.file_rx.chunk(args)
    if not ok:
        # 如果失敗，可以打印錯誤原因（例如磁碟滿了）
        print(f"⚠️  [File] Chunk Error: {app.file_rx.last_error}")

# 3. 定義 End
def on_file_end(ctx, args):
    app = ctx["app"]
    path = app.file_rx.path
    # 執行最後的校驗與結尾
    ok = app.file_rx.end(args)
    
    if ok:
        print(f"🏁 [File] Success: {path}")
        # 傳輸成功後，主動觸發一次 GC 回收記憶體碎片
        gc.collect()
    else:
        err = app.file_rx.last_error
        print(f"❌ [File] Failed! Reason: {err}")

# 4. 最後才是 register (它需要引用上面的函數)
def register(app):
    """註冊文件指令到分發器"""
    # 確保對應的函數名在當前作用域都已定義
    app.disp.on(CMD_FILE_BEGIN, on_file_begin)
    app.disp.on(CMD_FILE_CHUNK, on_file_chunk)
    app.disp.on(CMD_FILE_END,   on_file_end)
    print("✅ [Action] File actions registered")