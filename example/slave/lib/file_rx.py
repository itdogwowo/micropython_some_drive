import hashlib
import ubinascii
import os
import gc

class FileRx:
    def __init__(self):
        self.reset()

    def reset(self):
        self.active = False
        self.file_id = 0
        self.total = 0
        self.path = None
        self.fp = None
        self.written = 0
        self.sha_expect = None
        self.last_error = None
        # --- 核心：這個 context 會在整個傳輸期間保持狀態 ---
        self.sha_ctx = None 

    def _close(self):
        """安全關閉文件並釋放資源"""
        if self.fp:
            try:
                self.fp.flush()
                os.sync() 
                self.fp.close()
            except: pass
        self.fp = None

    def begin(self, args: dict) -> bool:
        self.last_error = None
        self._close()
        self.reset()
        
        self.file_id = int(args.get("file_id", 0))
        self.total = int(args.get("total_size", 0))
        self.path = args.get("path")
        self.sha_expect = args.get("sha256") # 這是 PC 發過來的目標 Hash

        if not self.path or not self.sha_expect:
            self.last_error = "MISSING_PARAMS"
            return False

        # --- 準備工作 ---
        # 1. 初始化 SHA256 串流計算器
        self.sha_ctx = hashlib.sha256()

        # 2. 預分配文件空間 (防止寫入過程中磁碟空間不足)
        try:
            with open(self.path, "wb") as f:
                if self.total > 0:
                    f.seek(self.total - 1)
                    f.write(b"\x00")
            
            # 3. 以讀寫模式打開，準備接收 Chunk
            self.fp = open(self.path, "r+b")
            self.active = True
            print(f"📂 [FileRx] Ready: {self.path} ({self.total} bytes)")
            return True
        except Exception as e:
            self.last_error = f"OPEN_FAIL:{e}"
            return False

    def chunk(self, args: dict) -> bool:
        """接收並處理分片"""
        if not self.active or not self.fp:
            return False

        data = args.get("data", b"")
        off = int(args.get("offset", 0))

        # --- 關鍵步驟 1：在數據還在 RAM 時，更新 Hash 計算器 ---
        # 這一步完全代替了文件寫完後重新讀取文件的操作
        self.sha_ctx.update(data)

        # --- 關鍵步驟 2：寫入磁碟 ---
        try:
            self.fp.seek(off)
            self.fp.write(data)
            self.written += len(data)
            return True
        except Exception as e:
            self.last_error = f"WRITE_FAIL:{e}"
            self.active = False
            return False

    def end(self, args: dict) -> bool:
        """結束傳輸並執行最終校驗"""
        if not self.active:
            return False

        print(f"🏁 [FileRx] Received {self.written} bytes. Finalizing SHA256...")

        # --- 關鍵步驟 3：獲取最終計算出的 Hash 值 ---
        got_digest = self.sha_ctx.digest()
        
        # 關閉文件句柄
        self._close()

        # --- 顯式校驗步驗 ---
        if got_digest == self.sha_expect:
            print(f"✅ [FileRx] SHA256 Match! File is intact.")
            self.active = False
            # 傳輸成功，清理計算器
            self.sha_ctx = None
            return True
        else:
            # 校驗失敗處理
            exp_h = ubinascii.hexlify(self.sha_expect).decode()
            got_h = ubinascii.hexlify(got_digest).decode()
            self.last_error = f"SHA_MISMATCH! Expect: {exp_h}, Got: {got_h}"
            print(f"❌ [FileRx] {self.last_error}")
            self.active = False
            self.sha_ctx = None
            return False