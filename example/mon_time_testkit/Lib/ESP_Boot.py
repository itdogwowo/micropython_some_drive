from machine import Timer, I2C,SoftI2C, ADC, Pin, PWM,UART,I2S
import esp, gc, time, json,  neopixel, utime, struct  ,ubinascii 
from Lib.LEDController import *
from Lib.audio_tools import *

from Lib.pca9685 import *    

import usocket as socket
import network   

sta_if = network.WLAN(network.STA_IF)
APP = False

def do_connect(net_Config):
    global sta_if
    
    sta_if.active(False)
    
    if not sta_if.isconnected():
        print('connecting to network...')
        sta_if.active(True)
        sta_if.connect(net_Config['ssid'], net_Config['password'])
        i = 1
        while not sta_if.isconnected():
            print("connecting...{}".format(i))
            i += 1
            time.sleep(1)
            if i> 10 :
                do_AP(net_Config)
                break
            pass
    if sta_if.isconnected():
        print('Connected! Network config:', sta_if.ifconfig())
    return True

def do_AP(net_Config):
    print(f'Unable to connect to local network : {net_Config["ssid"]}')
    print('Turn on AB mode')
    print(f'network name  {net_Config["pcName"]}')
    ap_if = network.WLAN(network.AP_IF)
    ap_if.active(False)
    ap_if.active(True)
    #ap_if.config(essid='RGbLed', authmode=network.AUTH_WPA_WPA2_PSK, password='12345678')
    ap_if.config(essid=net_Config['pcName'],authmode=0)
    ap_if.ifconfig(('10.10.1.1', '255.255.255.0', '10.10.1.1', '8.8.8.8'))
#     print(ap_if.ifconfig())
#     i = 1
#     while not ap_if.isconnected():
#         print(f"connecting AP ...{i}")
#         i += 1
#         time.sleep(1)
#         if i> 10 :
#             break
#         pass
    print('Connected! Network config:', ap_if.ifconfig())
    return True

def reset_timer():
    global last_access_time
    global in_running
    with lock:
        in_running = True
        last_access_time = time.time()

def timeout_checker():
    global server_running
    global in_running
    global APP
    while server_running and not in_running:
        with lock:
            current_time = time.time()
            if (current_time - last_access_time) > timeout_interval:
                print("Timeout reached, shutting down server.")
                server_running = False
                try:
                    APP.shutdown()
                except Exception as e:
                    print("Error during shutdown:", e)
                break
        time.sleep(1)


def run_server():
    global APP
    APP.run(port=80,debug=False)
    
    
def init_Network(config):
    
    if config['enable'] :
        do_connect(config)

    # if config['webREPL_enable'] :
    #     do_connect(config)

    # if config['web_enable'] :
    #     from Lib.microdot.microdot import Microdot
    #     from Lib.microdot.microdot import Request, Response
    #     from Lib.microdot.utemplate import Template
    #     global server_running
    #     global last_access_time
        
        
    #     print("Connecting to your wifi...")
    #     time.sleep(0.5)        
            
    #     app = init_webApp()
    #     # 启动超时检查线程
    #     _thread.start_new_thread(timeout_checker, ())
    #     # 启动服务器线程
    #     _thread.start_new_thread(run_server, ())
        
    #     try:
    #         while server_running:
    #             time.sleep(1)
    #     except KeyboardInterrupt:
    #         with lock:
    #             server_running = False
    #     print("Server interrupted and shut down manually.")
    #     clear_all_variables(config['enable'])

    return

def init_webApp():
    global APP

    from Lib.microdot.microdot import Microdot
    from subApp.root import root_app 
    from subApp.api import api_app
    app = Microdot()

    @root_app.route('/', methods=['GET', 'POST'])
    def index(request):
        reset_timer()
        if request.method == 'GET':
            re_Data = 'Hello, world!'
        
        if request.method == 'POST':
            name = request.form.get('name')
            re_Data = 'POST'
        return re_Data
    
    app.mount(root_app, url_prefix='/')
    app.mount(api_app, url_prefix='/api')
    APP = app
    return app


#pinOut = Pin(20,Pin.OUT)
#pinIn = Pin(21,Pin.IN)

# def init_i2c_led(i2c_led):
#     re_ledPwm = []
#     for i in range(16):
#         led_IO = {'led_IO':i,'Q':0,'i2c_Object':i2c_led}
#         ledPwm = LEDcontroller('i2c_LED',led_IO)
#         re_ledPwm.append(ledPwm)
#     return re_ledPwm

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
            print(i2cc['GPIO']['scl'],i2cc['GPIO']['sda'])
            i2c = SoftI2C(scl=i2cc['GPIO']['scl'], sda=i2cc['GPIO']['sda'])
            #print(i2c.scan())
            for i in i2c.scan():
                print(hex(i))
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
                    print(f'missing address : {i}')
                    led_IO = {'led_IO':None,'Q':16}
                    ledPwm = LEDcontroller('v_i2c_LED',led_IO)
                    i2c_led_list.append(ledPwm)
                    
    return i2c_led_list

def init_led(led_io):
    led_l = []
    if led_io['enable'] :
        led_IO = {'led_IO':led_io['GPIO'],'Q':len(led_io['GPIO']),'i2c_Object':''}
        led_l.append(LEDcontroller('esp_LED',led_IO))

    return led_l

def init_rgb(led_io):
    rgb_l = []
    if led_io['enable'] :
        for i in led_io['GPIO'] :
            led_IO = {'led_IO':i['GPIO'],'Q':i['Q'],'i2c_Object':''}
            rgb = LEDcontroller('RGB',led_IO)
            rgb_l.append(rgb)
#     print(rgb_l)
    return rgb_l

def init_i2s(led_io):
    i2s = None
    if led_io['enable'] :

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

def clear_all_variables(network_enable):
    global APP, last_access_time, timeout_interval, server_running, lock, in_running
    global reset_timer, init_webApp ,init_Network,run_server,timeout_checker
    # if network_enable:
    #     del APP
    del APP
    del last_access_time
    del timeout_interval
    del server_running
    del lock
    del reset_timer
    del init_webApp
    del init_Network
    del run_server
    del timeout_checker
    gc.collect()
    print("All variables are cleared and garbage collected.")



