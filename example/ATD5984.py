# This file is executed on every boot (including wake-boot from deepsleep)
#import esp
#esp.osdebug(None)
#import webrepl
#webrepl.start()


from machine import UART,Pin,ADC, PWM



import time



servo = PWM(Pin(0))
servo.freq(50)



pot = ADC(Pin(4))
pot.atten(ADC.ATTN_11DB)

uart = UART(1, baudrate=115200, tx=Pin(2), rx=Pin(3))

def send_cmd(mode, speed, force, cycle, direction):
    # 建立一個 20 字節全為 0x00 的緩衝區
    buf = bytearray(20)
    
    # 填充前 6 個字節
    buf[0] = 0xFF       # 幀頭
    buf[1] = mode       # 模式 (0x01 ~ 0x0A)
    buf[2] = speed      # 速度 (1 ~ 250)
    buf[3] = force      # 力度 (1 ~ 250)
    buf[4] = cycle      # 週期 (1 ~ 250)
    buf[5] = direction  # 方向
    
    # 發送完整的 20 字節
    uart.write(buf)
    print("已發送:", [hex(b) for b in buf])



def map_input_to_servo(input_val):
    """
    將 0-1023 的輸入映射到 0.5ms-2.5ms 的 PWM 佔空比 (1638-8192)
    """
    # 限制輸入範圍避免報錯
    if input_val < 0: input_val = 0
    if input_val > 1023: input_val = 1023
    
    # 映射公式：(input / 1023) * (最大佔空比 - 最小佔空比) + 最小佔空比
    duty = int((input_val / 1023) * (8192 - 1638) + 1638)
    return duty



def set_servo_from_4095(input_val):
    # 限制範圍
    input_val = max(0, min(4095, input_val))
    # 計算並回傳 duty 值
    duty = int((input_val / 4095) * (8192 - 1638) + 1638)
    return duty  # <--- 關鍵：一定要 return！


def set_servo_from_4095(input_val):
    # 限制輸入
    input_val = max(0, min(4095, input_val))
    
    # 根據你測試的「實測有效範圍」進行映射
    # 3000 (約 0度) 到 6000 (約 180度或其最大角度)
    MIN_DUTY = 3000 
    MAX_DUTY = 6000
    
    duty = int((input_val / 4095) * (MAX_DUTY - MIN_DUTY) + MIN_DUTY)
    return duty



# send_cmd(1, 249, 70, 47, 0)

# while 1:
#     
#     val = pot.read()
# #     servo.duty_u16(map_input_to_servo(val>>2))
#     servo.duty_u16(set_servo_from_4095(val))
# 
#     data = uart.read()
#     if data:
#         print(data[1],data[2],data[3],data[4],data[5])
#     
#     time.sleep(1)

send_cmd(0x03, 249, 249, 10, 1)
last_print_time = time.ticks_ms()
while 1:
    # 1. 高頻率更新：舵機控制 (0.01秒等級)
    val = pot.read()
    # 確保你的 set_servo_from_4095 函數裡有 return duty
    set_servo = set_servo_from_4095(val)
    
    servo.duty_u16(set_servo)

    # 2. 處理 UART 數據 (有資料就讀，不等待)
    
    
    # 3. 低頻率觸發：檢查是否過了 1 秒
    current_time = time.ticks_ms()
    ticks = time.ticks_diff(current_time, last_print_time)

    if ticks >= 1000:
        print(val,set_servo)
#         send_cmd(0x03, 249, 70, 15, 1)
        data = uart.read()
        if data:
#             for i in data:
#                 print(i)
            if len(data) >= 6:
                print(data[1], data[2], data[3], data[4], data[5])
        
        # 更新計時器
        last_print_time = current_time
    
    # 4. 基礎循環延遲 (0.01秒)，讓 CPU 喘口氣
    time.sleep(0.01)

