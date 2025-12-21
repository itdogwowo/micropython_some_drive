import ustruct
import time
from machine import UART

class JQ8400:
    # 协议常量定义
    HEADER = 0xAA
    CMD_ONLINE_DRIVES = 0x09
    CMD_SWITCH_DRIVE = 0x0B
    CMD_PLAY_SPECIFIC = 0x16
    CMD_STOP = 0x10
    CMD_TOTAL_TRACKS = 0x0C
    CMD_CURRENT_TRACK = 0x0D
    CMD_SET_VOLUME = 0x13
    CMD_VOL_UP = 0x14
    CMD_VOL_DOWN = 0x15
    CMD_NEXT_FOLDER = 0x0F
    CMD_PREV_FOLDER = 0x0E

    def __init__(self, uart: UART, default_drive: int = 2, timeout: int = 500):
        """
        初始化语音模块控制器
        :param uart: 配置好的UART对象
        :param default_drive: 默认存储设备(0=USB,1=SD,2=FLASH)
        :param timeout: 响应超时(毫秒)
        """
        self.uart = uart
        self.default_drive = default_drive
        self.timeout = timeout

    def _build_command(self, cmd: int, params: bytes = b'') -> bytes:
        """
        构建完整指令帧
        :param cmd: 指令码
        :param params: 参数字节流
        :return: 完整指令帧bytes
        """
        data_len = len(params)
        header = ustruct.pack('BBB', self.HEADER, cmd, data_len)
        checksum = (sum(header) + sum(params)) & 0xFF
        return header + params + bytes([checksum])

    def _send_command(self, cmd: int, params: bytes = b'') -> bool:
        """
        发送指令并验证基础格式
        :return: 是否成功发送
        """
        frame = self._build_command(cmd, params)
        return self.uart.write(frame) == len(frame)

    def _read_response(self, expected_len: int) -> bytes:
        """
        读取模块响应数据
        :param expected_len: 预期最小数据长度
        :return: 原始响应数据
        """
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < self.timeout:
            if self.uart.any() >= expected_len:
                return self.uart.read()
        return b''

    # --------------------- 存储设备控制 ---------------------
    def query_online_drives(self) -> dict:
        """查询在线存储设备状态"""
        self._send_command(self.CMD_ONLINE_DRIVES)
        res = self._read_response(5)
        
        if len(res) >=5 and res[0] == self.HEADER and res[1] == self.CMD_ONLINE_DRIVES:
            status = res[3]
            return {
                'USB': bool(status & 0x01),
                'SD': bool(status & 0x02),
                'FLASH': bool(status & 0x04)
            }
        return {'USB': False, 'SD': False, 'FLASH': False}

    def switch_drive(self, drive: int) -> bool:
        """切换存储设备(0=USB,1=SD,2=FLASH)"""
        if drive not in {0,1,2}:
            raise ValueError("无效的存储设备编号")
        return self._send_command(self.CMD_SWITCH_DRIVE, bytes([drive]))

    # --------------------- 播放控制 ---------------------
    def play(self, track: int, drive: int = None) -> bool:
        """播放指定曲目"""
        drive = self.default_drive if drive is None else drive
        params = bytes([drive, (track >> 8) & 0xFF, track & 0xFF])
        return self._send_command(self.CMD_PLAY_SPECIFIC, params)

    def stop(self) -> bool:
        """停止播放"""
        return self._send_command(self.CMD_STOP)

    # --------------------- 曲目查询 ---------------------
    def get_total_tracks(self) -> int:
        """获取当前存储设备总曲目数"""
        self._send_command(self.CMD_TOTAL_TRACKS)
        res = self._read_response(6)
        if len(res) >=6 and res[0:3] == bytes([self.HEADER, self.CMD_TOTAL_TRACKS, 0x02]):
            return (res[3] << 8) | res[4]
        return 0

    def get_current_track(self) -> int:
        """获取当前播放曲目编号"""
        self._send_command(self.CMD_CURRENT_TRACK)
        res = self._read_response(6)
        if len(res) >=6 and res[0:3] == bytes([self.HEADER, self.CMD_CURRENT_TRACK, 0x02]):
            return (res[3] << 8) | res[4]
        return 0

    # --------------------- 音量控制 ---------------------
    def set_volume(self, level: int) -> bool:
        """设置音量等级(0-30)"""
        level = min(max(level, 0), 30)
        return self._send_command(self.CMD_SET_VOLUME, bytes([level]))

    def volume_up(self) -> bool:
        """音量增加一级"""
        return self._send_command(self.CMD_VOL_UP)

    def volume_down(self) -> bool:
        """音量减少一级"""
        return self._send_command(self.CMD_VOL_DOWN)

    # --------------------- 文件夹控制 ---------------------
    def next_folder(self) -> bool:
        """切换到下一文件夹"""
        return self._send_command(self.CMD_NEXT_FOLDER)

    def prev_folder(self) -> bool:
        """切换到上一文件夹"""
        return self._send_command(self.CMD_PREV_FOLDER)

# 使用示例
# if __name__ == '__main__':
#     uart = UART(1, baudrate=9600, tx=4, rx=5)
#     player = JQ8400(uart)
    
#     print("在线设备:", player.query_online_drives())
#     player.switch_drive(1)
#     player.set_volume(20)
#     player.play(5)
#     print("当前曲目:", player.get_current_track())