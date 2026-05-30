"""
mp3_tf_16p.py — MP3-TF-16P 模組驅動

API 相容 JQ8400，底層走 MP3-TF-16P 的 0x7E 協定。

協定:
  7E FF 06 CMD FB P1 P2 CS CS EF
  校驗: 6 個資料字節 (FF~P2) 的 16-bit 兩's 補數
"""

import time
from machine import UART

# ── 協定常數 ──
_HEADER = 0x7E
_VER    = 0xFF
_LEN    = 0x06
_END    = 0xEF

# 設備號映射: JQ8400 → MP3-TF-16P
_DRIVE_MAP = {0: 1, 1: 2, 2: 5}


def _checksum(data: bytes) -> tuple:
    s = sum(data) & 0xFFFF
    cs = (-s) & 0xFFFF
    return (cs >> 8) & 0xFF, cs & 0xFF


def _build_cmd(cmd: int, fb: int = 0, p1: int = 0, p2: int = 0) -> bytes:
    data = bytes([_VER, _LEN, cmd, fb, p1 & 0xFF, p2 & 0xFF])
    ch, cl = _checksum(data)
    return bytes([_HEADER]) + data + bytes([ch, cl, _END])


class MP3TF16P:
    """
    MP3-TF-16P 驅動，API 盡量相容 JQ8400。

    參數:
      uart          — 已配置的 machine.UART 物件
      default_drive — 預設設備 (0=USB, 1=SD/TF, 2=FLASH)
      timeout       — 回應超時 ms (預設 500)
    """

    def __init__(self, uart: UART, default_drive: int = 1, timeout: int = 500):
        self.uart = uart
        self.default_drive = default_drive
        self.timeout = timeout
        self._current_folder = 1

    # ── 底層 ──

    def _send(self, cmd: int, fb: int = 0, p1: int = 0, p2: int = 0) -> bool:
        frame = _build_cmd(cmd, fb, p1, p2)
        return self.uart.write(frame) == len(frame)

    def _read_response(self, expected_len: int) -> bytes:
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < self.timeout:
            if self.uart.any() >= expected_len:
                return self.uart.read()
        return b''

    # ── 儲存設備控制 ──

    def query_online_drives(self) -> dict:
        """
        查詢在線設備狀態。
        利用 0x3F (發送初始化參數, FB=1) 觸發模組回報。
        回傳 {'USB': bool, 'SD': bool, 'FLASH': bool}
        """
        self._send(0x3F, fb=1)
        res = self._read_response(6)
        if len(res) >= 6 and res[0] == _HEADER and res[3] == 0x3F:
            status = res[5]
            return {
                'USB':   bool(status & 0x01),
                'SD':    bool(status & 0x02),
                'FLASH': bool(status & 0x04),
            }
        return {'USB': False, 'SD': False, 'FLASH': False}

    def switch_drive(self, drive: int) -> bool:
        """切換設備 (0=USB, 1=SD/TF, 2=FLASH)"""
        if drive not in _DRIVE_MAP:
            raise ValueError("無效設備編號 (0=USB, 1=SD, 2=FLASH)")
        dev = _DRIVE_MAP[drive]
        ok = self._send(0x09, p2=dev)
        if ok:
            time.sleep_ms(200)  # 設備切換後需延遲
        return ok

    # ── 播放控制 ──

    def play(self, track: int, drive: int = None) -> bool:
        """播放指定曲目 (1-2999)。drive=None 使用 default_drive"""
        d = self.default_drive if drive is None else drive
        if d not in _DRIVE_MAP:
            raise ValueError("無效設備編號")
        dev = _DRIVE_MAP[d]
        # MP3-TF-16P: 先選設備, 再播曲目
        self._send(0x09, p2=dev)
        time.sleep_ms(50)
        return self._send(0x03, p1=(track >> 8) & 0xFF, p2=track & 0xFF)

    def stop(self) -> bool:
        """停止播放"""
        return self._send(0x16)

    # ── 曲目查詢 ──

    def get_total_tracks(self) -> int:
        """查詢 TF 卡總曲目數 (0x48, FB=1)"""
        self._send(0x48, fb=1)
        res = self._read_response(8)
        if len(res) >= 8 and res[0] == _HEADER:
            return (res[4] << 8) | res[5]
        return 0

    def get_current_track(self) -> int:
        """查詢 TF 卡當前曲目 (0x4C, FB=1)"""
        self._send(0x4C, fb=1)
        res = self._read_response(8)
        if len(res) >= 8 and res[0] == _HEADER:
            return (res[4] << 8) | res[5]
        return 0

    # ── 音量控制 ──

    def set_volume(self, level: int) -> bool:
        """音量 0-30"""
        return self._send(0x06, p2=max(0, min(level, 30)))

    def volume_up(self) -> bool:
        return self._send(0x04)

    def volume_down(self) -> bool:
        return self._send(0x05)

    # ── 資料夾控制 ──

    def next_folder(self) -> bool:
        """下一資料夾 (1-10, 循環)"""
        self._current_folder = (self._current_folder % 10) + 1
        return self._send(0x0F, p2=self._current_folder)

    def prev_folder(self) -> bool:
        """上一資料夾 (1-10, 循環)"""
        self._current_folder = (self._current_folder - 2) % 10 + 1
        return self._send(0x0F, p2=self._current_folder)
