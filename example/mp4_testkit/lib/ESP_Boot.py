from machine import Timer, I2C, ADC, Pin, PWM,UART
import esp, gc, time, json,  neopixel, utime, struct  ,ubinascii 
from lib.LEDController import *

from lib.WiFiManager import *
from lib.ConfigManager import *

from lib.PCA9685 import *    

import usocket as socket
import network ,webrepl
from lib.globalMethod import debugPrint
# ============================================
# 全局變量
# ============================================

USER_CONNECT = False

WEBREPL_CHECK_INTERVAL = 10  # 每 30 秒檢查一次
WEBREPL_MAX_CHECKS = 12      # 最多檢查 6 次 (WEBREPL_CHECK_INTERVAL * WEBREPL_MAX_CHECKS = 秒 // 60 = 分鐘)
webrepl_check_count = 0      # 全局計數器
webrepl_timer = None
wifi = None




def check_looping(loop_one_success,cfg):
    global USER_CONNECT, wifi, webrepl_timer, webrepl_check_count
    
    if not loop_one_success:
        debugPrint(f"{'='*70}")
        debugPrint("📡 首次循環未成功,啟動網絡服務...")
        debugPrint(f"{'='*70}\n")
        
        try:
            # 初始化 WiFi
            wifi = init_Network(cfg)
            
            if wifi and wifi.get_connection_info()['connected']:
                # 啟動 WebREPL
                webrepl.start(password='12345678')
                
                # 顯示連接信息
                info = wifi.get_connection_info()
                debugPrint(f"📱 WebREPL 連接信息:")
                debugPrint(f"  URL: ws://{info['ip']}:8266")
                debugPrint(f"  IP: {info['ip']}")
                debugPrint(f"  mDNS: {info['mdns_name']}")
                debugPrint(f"  密碼: 12345678")
                
                debugPrint(f"\n⏰ 啟動定期檢查:")
                debugPrint(f"  檢查間隔: {WEBREPL_CHECK_INTERVAL} 秒")
                debugPrint(f"  檢查次數: {WEBREPL_MAX_CHECKS} 次")
                debugPrint(f"  總等待時間: {WEBREPL_CHECK_INTERVAL * WEBREPL_MAX_CHECKS} 秒")
                
                debugPrint(f"\n💡 連接後請執行:")
                debugPrint(f"  >>> USER_CONNECT = True")
                debugPrint(f"{'='*70}\n")
                
                # 啟動周期性計時器 - 使用虛擬計時器
                webrepl_timer = Timer(0) 
                webrepl_timer.init(
                    period=WEBREPL_CHECK_INTERVAL * 1000,  # 轉換為毫秒
                    mode=Timer.PERIODIC,  # 周期模式
                    callback=webrepl_check_handler
                )
                
                debugPrint(f"✓ 計時器已啟動 (每 {WEBREPL_CHECK_INTERVAL} 秒檢查一次)\n")
            else:
                debugPrint(f"⚠ WiFi 連接失敗,跳過網絡服務\n")
        
        except Exception as e:
            debugPrint(f"✗ 網絡初始化失敗: {e}\n")
            import sys
            sys.debugPrint_exception(e)
            wifi = None

    else:
        debugPrint(f"{'='*70}")
        debugPrint("⏭️  上次循環成功,跳過網絡服務")
        debugPrint(f"{'='*70}\n")
    
    
    return
    

def webrepl_check_handler(timer):
    # ============================================
    # 計時器回調函數
    # ============================================


    """
    定期檢查 WebREPL 連接狀態
    每 30 秒觸發一次,共 6 次
    
    Args:
        timer: Timer 對象
    """
    global USER_CONNECT, wifi, webrepl_timer, webrepl_check_count
    
    webrepl_check_count += 1
    remaining_checks = WEBREPL_MAX_CHECKS - webrepl_check_count
    remaining_time = remaining_checks * WEBREPL_CHECK_INTERVAL
    
    debugPrint(f"\n{'='*70}")
    debugPrint(f"⏰ WebREPL 檢查 [{webrepl_check_count}/{WEBREPL_MAX_CHECKS}]")
    debugPrint(f"{'='*70}")
    
    # 檢查用戶是否已連接
    if USER_CONNECT:
        debugPrint("✅ 檢測到用戶已連接!")
        debugPrint("🌐 網絡服務將保持運行")
        debugPrint(f"{'='*70}\n")
        
        # 停止計時器
        if webrepl_timer:
            webrepl_timer.deinit()
            webrepl_timer = None
            debugPrint("✓ 計時器已停止\n")
    
    # 檢查是否達到最大次數
    elif webrepl_check_count >= WEBREPL_MAX_CHECKS:
        debugPrint(f"⏰ 已達到最大等待時間 ({(WEBREPL_CHECK_INTERVAL * WEBREPL_MAX_CHECKS)//60 } 分鐘)")
        debugPrint("❌ 未檢測到用戶連接")
        debugPrint("🧹 正在關閉網絡服務...")
        
        try:
            webrepl.stop()
            debugPrint("  ✓ WebREPL 已停止")
        except Exception as e:
            debugPrint(f"  ⚠ 停止 WebREPL 失敗: {e}")
        
        try:
            if wifi:
                wifi.disconnect()
                debugPrint("  ✓ WiFi 已斷開")
        except Exception as e:
            debugPrint(f"  ⚠ 斷開 WiFi 失敗: {e}")
        
        debugPrint(f"{'='*70}\n")
        
        # 停止計時器
        if webrepl_timer:
            webrepl_timer.deinit()
            webrepl_timer = None
            debugPrint("✓ 計時器已停止\n")
    
    # 繼續等待
    else:
        debugPrint(f"⏳ 等待用戶連接...")
        debugPrint(f"⏱️  剩餘時間: {remaining_time} 秒 ({remaining_checks} 次檢查)")
        debugPrint(f"\n💡 如果你已通過 WebREPL 連接,請執行:")
        debugPrint(f"  >>> USER_CONNECT = True")
        debugPrint(f"或:")
        debugPrint(f"  >>> import main")
        debugPrint(f"  >>> main.USER_CONNECT = True")
        debugPrint(f"{'='*70}\n")
        
def init_Network(config):
    
    """
    初始化網絡 (兼容你原有的函數名)
    
    Args:
        network_config: Network 配置字典
        
    Returns:
        WiFiManager: WiFi 管理器實例
    """
    
    _config = {
        "enable"   : config.get('Network.enable') ,
        "pcName"   : config.get('Network.pcName', 'esp32'),
        "ssid"     : config.get('Network.ssid', '00'),
        "password" : config.get('Network.password', '00')
    }
    
    
    # 創建 WiFi 管理器
    _wifi = WiFiManager(config_dict=_config)
    
    # 自動連接
    _wifi.connect()
    
    # 打印信息
    _wifi.debugPrint_info()
    
    return _wifi


def init_i2c_led(i2c_led):
    re_ledPwm = []

    led_IO = {'led_IO':i2c_led,'Q':16}
    ledPwm = LEDcontroller('i2c_LED',led_IO)

    return re_ledPwm

def init_UART(uart_io):
    uart = None
    if uart_io['enable'] :
        uart = UART(1, baudrate=uart_io['baudrate'], bits=8, tx=uart_io['GPIO']['tx'], rx=uart_io['GPIO']['rx'])
    return uart

def init_i2c(led_io):
    i2c_led_list = []
    if led_io['enable'] :
        for i2cc in led_io['i2c_List']:
            debugPrint(i2cc['GPIO']['scl'],i2cc['GPIO']['sda'])
            i2c = I2C(scl=i2cc['GPIO']['scl'], sda=i2cc['GPIO']['sda'])
            #debugPrint(i2c.scan())
            for i in i2c.scan():
                debugPrint(hex(i))
            for i in i2cc['address']:
                try:
                    pca = PCA9685(i2c,address=int(i,16))
                    pca.freq(1000)
                    # i2c_Object = init_i2c_led(pca)
                    # i2c_led_list.append(i2c_Object)

                    led_IO = {'led_IO':pca,'Q':16}
                    ledPwm = LEDcontroller('i2c_LED',led_IO)
                    i2c_led_list.append(ledPwm)

                except BaseException as e:
                    debugPrint(f'missing address : {i}')
                    led_IO = {'led_IO':None,'Q':16}
                    ledPwm = LEDcontroller('v_i2c_LED',led_IO)
                    i2c_led_list.append(ledPwm)
                    
    return i2c_led_list

def init_led(led_io):
    led_l = []
    if led_io['enable'] :
        led_IO = {'led_IO':led_io['GPIO_List'],'Q':len(led_io['GPIO_List']),'i2c_Object':''}
        led_l.append(LEDcontroller('esp_LED',led_IO))
    return led_l

def init_rgb(led_io):
    rgb_l = []
    if led_io['enable'] :
        for i in led_io['GPIO'] :
            led_IO = {'led_IO':i['GPIO'],'Q':i['Q'],'i2c_Object':''}
            rgb = LEDcontroller('RGB',led_IO)
            rgb_l.append(rgb)
#     debugPrint(rgb_l)
    return rgb_l

def init_i2s(led_io):
    
    i2s = None
    if led_io['enable'] :
        from lib.audio_tools import AudioBuffer

        # 硬件引脚配置 (ESP32)
        sck_pin = Pin(led_io['i2s_List'][0]['GPIO']['sck'])   # 串行时钟
        ws_pin = Pin(led_io['i2s_List'][0]['GPIO']['ws'])    # 字选择（声道时钟）
        sd_pin = Pin(led_io['i2s_List'][0]['GPIO']['sd'])    # 串行数据输入

        # I2S参数配置
        sample_rate = led_io['sampling_rate']  # 采样率 (Hz)
        sample_bits = led_io['sample_bits']     # 采样位深
        buffer_frames = led_io['buffer_frames']  # 样本帧数（每个帧包含左右声道）
        channel_to_use = led_io['channel_to_use']   # 0=左声道, 1=右声道（根据实际硬件连接选择）

        # 初始化I2S（立体声模式）
        _i2s = I2S(
            0,                              # 使用I2S0
            sck=sck_pin,                    # 时钟引脚
            ws=ws_pin,                      # 字选择引脚
            sd=sd_pin,                      # 数据引脚
            mode=I2S.RX,                    # 接收模式
            bits=sample_bits,               # 采样位数
            format=I2S.STEREO,              # 立体声
            rate=sample_rate,               # 采样率
            ibuf=buffer_frames * 4 * 2,       # 输入缓冲区大小
        )
        


        i2s = AudioBuffer(
            i2s_device=_i2s,
            buffer_size=buffer_frames,
            history_size=15,
            beat_threshold=1.5,
            debug=0
        )


    return i2s



