import time, math, struct, random
import os , gc, micropython

def disk_info(path):
    statvfs_fields  = ['bsize','frsize','blocks','bfree','bavail','files','ffree']
    vfs = dict(zip(statvfs_fields, os.statvfs(path)))
    total = vfs['bsize'] * vfs['blocks'] / 1024
    used  = vfs['bsize'] * (vfs['blocks'] - vfs['bfree']) / 1024
    avail = vfs['bsize'] * vfs['bavail'] / 1024
    used_percent = round(float(used) / float(used + avail) * 100, 2)
    print (f'總容量為： {total}')
    print (f'使用量為： {used}')
    print (f'有效容量為： {avail}')
    print (f'使用率為： {used_percent}')
    # 240_000_000
    # machine.freq(240_000_000)


def memory_info():
    print("\n=== Memory Information ===")
    print("Free:", gc.mem_free(), "bytes")
    print("Allocated:", gc.mem_alloc(), "bytes")
    print("Total:", gc.mem_free() + gc.mem_alloc(), "bytes")
    micropython.mem_info()


def random_list(input_No):
    """Randomly shuffles the input list."""
    input_list = [i for i in range(input_No)]
    shuffled_list = []
    while input_list:  # Continue until input_list is empty
        random_index = random.choice(range(len(input_list)))
        shuffled_list.append(input_list.pop(random_index))
    return shuffled_list  # Return the randomized list

def random_to_list(input_list):
    """Randomly shuffles the input list."""
    shuffled_list = []
    while input_list:  # Continue until input_list is empty
        random_index = random.choice(range(len(input_list)))
        shuffled_list.append(input_list.pop(random_index))
    return shuffled_list  # Return the randomized list


def fisher_yates_shuffle(input_list):
    """Shuffles the list in place using the Fisher-Yates algorithm."""
    for i in range(len(input_list) - 1, 0, -1):
        j = random.randint(0, i)
        input_list[i], input_list[j] = input_list[j], input_list[i]

def random_batch_generator(input_list, n):
    """
    Yields a batch of randomly shuffled elements from the input_list.
    
    Arguments:
    input_list -- the list to sample from
    n -- number of elements in each batch

    Yields:
    A list representing a batch of randomly chosen elements.
    """
    pool = []
    original_len = len(input_list)
    while True:
        if len(pool) < n:
            pool.extend(input_list)
            fisher_yates_shuffle(pool)
        
        batch, pool = pool[:n], pool[n:]
        yield batch


def shuffle(input_list):
    import utime
    seed = utime.ticks_ms()  # 利用時間戳作為種子
    for i in range(len(input_list) - 1, 0, -1):
        seed = (seed * 97 + 101) % len(input_list)  # 簡單的生成隨機索引
        j = seed % (i + 1)
        input_list[i], input_list[j] = input_list[j], input_list[i]
        
    return input_list


def _uart(_self, now):
    if _self._uart.any():
        _temp = _self._uart.read()
        
        for n, u in enumerate(_temp):
            if u == _self.address:
                _self.run_Sorting = _temp[n+1]
                return True
            
    return None


def alignment_buf(uart):
    _buf_temp= []
    while uart.any():
        alignment = uart.read(1)
        _buf_temp.append(alignment)
        if Alignment == 'xff':
            break
        
        time.sleep_ms(20 )
        
    if len(_buf_temp) == 3:
        return _buf_temp
    else:
        return False



def read_uart(uart):
    _buf_temp= []
    
    while uart.any():
        alignment = uart.read(1)
        _buf_temp.append(alignment)
        if Alignment == 'xff':
            break
        
        time.sleep_ms(20 )
        
    if len(_buf_temp) == 3:
        return _buf_temp
    else:
        return False


    

def zip_data(raw_data):
    z_data = []
    current_value = raw_data[0]
    count = 1 
    for value in raw_data:
        if value == current_value:
            count = count+1
        else:
            z_data.append([current_value,count])
            current_value = value
            count = 1
            
    z_data.append([value,count])
    return z_data

def unZip_data(raw_data):
    uz_data = []
    for value, count in raw_data:
        uz_data.extend([value]*count)
    return uz_data

def r_unZip_data(raw_data,in_I,calculate_I = 0,calculate_II = 0):
    uz_data = []
    now_i = calculate_I
    run_term= len(raw_data)
    re_i = 0
    
    
    for i in range(calculate_II,run_term ) :
        re_i = i
        value, count =raw_data[i]
        if in_I <= now_i :
            re_value = value
            break
        if in_I >= now_i :
            now_i = now_i + count


    return {'re_value':re_value,'now_i':now_i,'re_i':re_i}


def zip_rgb_data(rgb_data, output_path, row_size=100):
    ## zip_rgb_data(ppp, 'compressed_rgb_data.bin')
    with open(output_path, 'wb') as f:
        for i in range(0, len(rgb_data), row_size):
            row = rgb_data[i:i + row_size]
            for pixel in row:
                packed_data = struct.pack('BBB', int(pixel[0]),int(pixel[1]),int(pixel[2]))
                f.write(packed_data)
    return

def read_rgb_zip_data(input_path,  col):
    #offset = (row * row_size + col) * 3  # 每个RGB值占用12字节 (3 * 1 bytes)
    offset = col * 3  # 每个RGB值占用12字节 (3 * 1 bytes)
    with open(input_path, 'rb') as f:
        f.seek(offset)  # 移动文件指针到指定位置
        packed_data = f.read(3)  # 读取3字节的数据
        if packed_data:
            pixel = struct.unpack('BBB', packed_data)
            return list(pixel)
        else:
            raise ValueError("Invalid row or column specified.")
        

def zip_led_data(in_data, output_path, row_size=100):
    ## zip_rgb_data(ppp, 'compressed_rgb_data.bin')
    with open(output_path, 'wb') as f:
        for i in range(0, len(in_data), row_size):
            row = in_data[i:i + row_size]
            packed_data = struct.pack('H', int(row))
            f.write(packed_data)
    return

def read_led_zip_data(input_path,  col):
    offset = col * 2  
    with open(input_path, 'rb') as f:
        f.seek(offset)  
        packed_data = f.read(2) 
        if packed_data:
            pixel = struct.unpack('H', packed_data)
            return int(pixel[0])
        else:
            raise ValueError("Invalid row or column specified.")

def rgb_buffer(in_data, output_path):
    with open(output_path, 'wb') as f:
        for i in in_data:
            packed_data = struct.pack('BBB', int(i[0]),int(i[1]),int(i[2]))
            f.write(packed_data)
    return

def read_rgb_buffer(input_path,now=0,led_n=None, buf_seek=None,buf_read=None):
    led_n = 1  if led_n == None else led_n
    rgb_LED = 3 * led_n  if buf_read == None else buf_read
    offset = rgb_LED  * now  if buf_seek == None else buf_seek

    with open(input_path, 'rb') as f:
        f.seek(offset)  
        packed_data = f.read(rgb_LED)
        if packed_data:
            return packed_data
        else:
            raise ValueError("Invalid row or column specified.")


def read_rgb_buffer_old(input_path,now=0,led_n=None, buf_seek=None,buf_read=None):
    led_n = 1  if led_n == None else led_n
    rgb_LED = 3 * led_n  if buf_read == None else buf_read
    offset = rgb_LED  * now  if buf_seek == None else buf_seek
    b_type = 'B'*rgb_LED
    with open(input_path, 'rb') as f:
        f.seek(offset)  
        packed_data = f.read(rgb_LED)
        if packed_data:
            pixel = struct.unpack(b_type, packed_data)
            return pixel
        else:
            raise ValueError("Invalid row or column specified.")



def led_buffer(in_data, output_path):
    with open(output_path, 'wb') as f:
        for i in in_data:
            packed_data = struct.pack('H', int(i))
            f.write(packed_data)
    return

def read_led_buffer(input_path,now=0,led_n=None, buf_seek=None,buf_read=None):
    offset = now * 2  if buf_seek == None else buf_seek
    with open(input_path, 'rb') as f:
        f.seek(offset)  
        packed_data = f.read(2) 
        if packed_data:
            pixel = struct.unpack('H', packed_data)
            return int(pixel[0])
        else:
            raise ValueError("Invalid row or column specified.")

def calculate_write_count(input_path,led_n=1):
    """Calculate how many times data has been written to the file."""
    try:
        file_size = os.path.getsize(input_path)
        write_size = led_n * 3  # Number of bytes per write
        return file_size // write_size  # Integer division
    except FileNotFoundError:
        return 0

def hsv2rgb(h, s, v):
    h = float(h)
    s = float(s)
    v = float(v)
    h60 = h / 60.0
    h60f = math.floor(h60)
    hi = int(h60f) % 6
    f = h60 - h60f
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    r, g, b = 0, 0, 0
    if hi == 0: r, g, b = v, t, p
    elif hi == 1: r, g, b = q, v, p
    elif hi == 2: r, g, b = p, v, t
    elif hi == 3: r, g, b = p, q, v
    elif hi == 4: r, g, b = t, p, v
    elif hi == 5: r, g, b = v, p, q
    r, g, b = int(r * 255), int(g * 255), int(b * 255)
    return r, g, b


def hsv2grb(h, s, v):
    h = float(h)
    s = float(s)
    v = float(v)
    h60 = h / 60.0
    h60f = math.floor(h60)
    hi = int(h60f) % 6
    f = h60 - h60f
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    r, g, b = 0, 0, 0
    if hi == 0: r, g, b = v, t, p
    elif hi == 1: r, g, b = q, v, p
    elif hi == 2: r, g, b = p, v, t
    elif hi == 3: r, g, b = p, q, v
    elif hi == 4: r, g, b = t, p, v
    elif hi == 5: r, g, b = v, p, q
    r, g, b = int(r * 255), int(g * 255), int(b * 255)
    return  g,r,b



def rgb2hsv(r, g, b):
    r, g, b = r/255.0, g/255.0, b/255.0
    mx = max(r, g, b)
    mn = min(r, g, b)
    df = mx-mn
    if mx == mn:
        h = 0
    elif mx == r:
        h = (60 * ((g-b)/df) + 360) % 360
    elif mx == g:
        h = (60 * ((b-r)/df) + 120) % 360
    elif mx == b:
        h = (60 * ((r-g)/df) + 240) % 360
    if mx == 0:
        s = 0
    else:
        s = df/mx
    v = mx
    return h, s, v


@micropython.viper
def hsv_to_rgb_viper(h: int, s: int, v: int) -> int:
    """
    Convert HSV to RGB and return as an integer packed with RGB components.
    
    Arguments:
    h -- Hue value (0 to 360)
    s -- Saturation value (0 to 255)
    v -- Value/brightness (0 to 255)
    
    Returns:
    An integer where the most significant byte is red, the next byte is green, and the least significant byte is blue.
    """
    if s == 0:
        r = g = b = v
        return (r << 16) | (g << 8) | b

    h = h % 360
    region = h // 60
    remainder = (h - (region * 60)) * 255 // 60

    p = (v * (255 - s)) // 255
    q = (v * (255 - ((s * remainder) // 255))) // 255
    t = (v * (255 - ((s * (255 - remainder)) // 255))) // 255

    if region == 0:
        r, g, b = v, t, p
    elif region == 1:
        r, g, b = q, v, p
    elif region == 2:
        r, g, b = p, v, t
    elif region == 3:
        r, g, b = p, q, v
    elif region == 4:
        r, g, b = t, p, v
    else:
        r, g, b = v, p, q
    
#     print(r)
#     print(g)
#     print(b)
    return (r << 16) | (g << 8) | b


def unpack_rgb(rgb: int) -> tuple:
    r = (rgb >> 16) & 0xFF
    g = (rgb >> 8) & 0xFF
    b = rgb & 0xFF
    return g, r, b

def hsv_to_grb(h: int, s: int, v: int):

    return unpack_rgb(hsv_to_rgb_viper(h, s, v))




def is_math_iii(F,l_max,phi,fs):
    t = 1
    A = l_max/2
    dot_count = int(t * fs /F)
    time_ms = t/F
    x_ = []
    x_step = time_ms / dot_count
    math_pi_F = 2 * math.pi * F
    math_radians = math.radians(phi)
    for i in range(fs):
        x_.append(i*x_step)
    y_ = []
    for i in range(len(x_)):
        cur_x = x_[i]
        cur_y = A * math.sin(math_pi_F * cur_x + math_radians)+A
        # y_.append(int(cur_y))
        y_.append(cur_y)

    return y_

# def is_math_now(F,l_max,phi,fs,t):
#     A = l_max/2
#     Ts = 1/fs 
#     n=1/Ts
#     dot_count = int(1 * fs /F)
#     time_ms = 1/F
#     x_step = time_ms / dot_count
#     cur_x = t*x_step
#     y= A * math.sin(2 * math.pi * F * cur_x + phi*(math.pi/180))+A
#     return y

@micropython.native
def is_math_now(F, l_max, phi, fs, t):
    A = l_max / 2  # 振幅
    dot_count = fs / F  # 每個週期的樣本數
    time_ms = 1 / F  # 每個周期的時間
    x_step = time_ms / dot_count  # 每一步的時間
    cur_x = t * x_step  # 當前時間點
    # 計算正弦波值
    y = A * math.sin(2 * math.pi * F * cur_x + math.radians(phi)) + A
    return y



def is_math_XXX(F,l_max,phi,fs):
    A = l_max
    dot_count = fs /F
    time_ms = 1/F
    x_ = []
    x_step = time_ms / dot_count
    math_pi_F = 2 * math.pi * F
    math_radians = math.radians(phi)

    for i in range(fs):
        x_.append(i*x_step)
    y_ = []
    for i in range(len(x_)):
        cur_x = x_[i]
        cur_y = A * math.sin(math_pi_F * cur_x + math_radians)
        y_.append(int(cur_y))
    return y_

def is_math_XXX_now(F,l_max,phi,fs,t):
    A = l_max   # 振幅
    dot_count = fs / F  # 每個週期的樣本數
    time_ms = 1 / F  # 每個周期的時間
    x_step = time_ms / dot_count  # 每一步的時間
    cur_x = t * x_step  # 當前時間點
    y = A * math.sin(2 * math.pi * F * cur_x + math.radians(phi))
    return y


def is_square_wave_now(F,l_max,phi,fs,t):    
        return l_max if is_math_XXX_now(F,1,phi,fs,t%fs) >=0 else 0

def is_square_True_now(F,phi,fs,t ):    
        return True if is_math_XXX_now(F,1,phi,fs,t%fs) >=0 else False


##############################################

def keep_next(l_max,fs):
    for i in range(fs):
        yield l_max


def is_math_next(F, l_max, phi, fs):
    A = l_max / 2  # 振幅
    Ts = 1 / fs   # 取樣週期
    t = 0
    math_pi_F = 2 * math.pi * F
    math_radians = math.radians(phi)
    for i in range(fs):
        y = A * math.sin(math_pi_F * t + math_radians) + A
        yield round(y,4)  # 生成當前值
        t += Ts
    # while True:
    #     # 計算正弦波值
    #     y = A * math.sin(math_pi_F * t + math_radians) + A
    #     yield y  # 生成當前值
    #     t = (t + Ts)%1  # 增加時間


def is_math_XXX_next(F,l_max,phi,fs):
    A = l_max  # 振幅
    Ts = 1 / fs   # 取樣週期
    t = 0
    math_pi_F = 2 * math.pi * F
    math_radians = math.radians(phi)

    for i in range(fs):
        y = A * math.sin(math_pi_F * t + math_radians) 
        value = round(y,4)
        yield value if value < 0 else  0
        t += Ts


def is_square_wave_next(F,l_max,phi,fs):
    math_XXX = is_math_XXX_next(F,1,phi,fs)
    for i in range(fs):
        yield l_max if next(math_XXX) >=0 else 0


def is_square_True_next(F,phi,fs):
    math_XXX = is_math_XXX_next(F,1,phi,fs)
    for i in range(fs):
        yield True if next(math_XXX) >=0 else False



def is_math_pattern_next(led_Pattern, setMax: int = 4095, notice:bool= False):

    while 1:

        run_time = 0
        
        for i in led_Pattern:
            run_fs = i['end_Time'] - run_time
            run_time = i['end_Time']

            l_max = max(0, min(setMax, i['l_max']))

            l_lim = max(0, min(setMax, i['l_lim']))

            l_range = l_max - l_lim

            if i['type'] == 'keep':
                re_value = keep_next(l_range,run_fs) 
            
            elif i['type'] == 'math_now':
                re_value = is_math_next(i['F'],l_range,i['phi'],run_fs)

            elif i['type'] == 'square_wave_now':
                re_value =  is_square_wave_next(i['F'],l_range ,i['phi'],run_fs)

            elif i['type'] == 'math_XXX_now':
                re_value =  is_math_XXX_next(i['F'],l_range ,i['phi'],run_fs)

            for value in re_value:
                yield int(value) + i['l_lim']

            if notice :
                yield True
    
    return 



def dynamic_rearrange(data: bytearray, block_size: int = 3) -> bytearray:
    """
    通用版本，支援任意區塊長度
    
    參數:
        block_size (int): 區塊大小（例如 3 或 4）
    """
    if len(data) % block_size != 0:
        raise ValueError(f"Length must be multiple of {block_size}")
    
    buf = bytearray(len(data))
    num_blocks = len(data) // block_size
    
    for i in range(num_blocks):
        src_start = i * block_size
        dest_start = (num_blocks - 1 - i) * block_size
        buf[dest_start : dest_start+block_size] = data[src_start : src_start+block_size]
    
    return buf


def run_map(wide, length , counter,end,step = 1,gap=0):
    from random import choice
#     jump_list = [1,2,3,4]
    jump_list =range(wide)
    
    _location  = [(choice(jump_list),0)] * length
    
    def _run_map(_location,target_location,step,end,i,counter):
        if _location[0][0] != target_location:
                
            if _location[0][0] > target_location:
                l = _location[0][0]-1
            elif _location[0][0] < target_location:
                l = _location[0][0]+1
            else:
                l = target_location
                    
            _location = [(l,_location[0][1])]+_location[:-1]
        else:
            for j in range(step):
                _location = [(_location[0][0],(_location[0][1]+1)%end)]+_location[:-1]
                
            target_location  = choice(jump_list)
            
        return _location , target_location

#     next_point = random_batch_generator(jump_list, 1)
    
    target_location  = choice(jump_list)
    
    i = 0
    g = 0
    while True:
        if gap == g:
            if counter == i:
                for j in range(step):
                
                    _location , target_location = _run_map(_location , target_location,step,end,i,counter)
                    
                i = 0
            else:     
                i = i+1
        elif gap>g:
            g = g+1

        redata =  _location if   gap == g else []  
        
        counter = yield redata


def fade_out(_self, now):
    for i in rgb_list:
        for n, v in enumerate(i.rgb_Buffer):
            if v <= 0:
                i.rgb_Buffer[n] = 0
            else:
                i.rgb_Buffer[n] = v -1
            
    for i in all_led_list:
        
        for n, v in enumerate(i.LED_Buffer):
            if v <= 0:
                i.LED_Buffer[n] = 0
            else:
               i.LED_Buffer[n] = v -1
                

    return

import array

class LEDMathMethod:
    """
    pattern = [
                {'type':'keep',             'F':1,'l_max':10,'l_lim':10, 'phi':1024,                'end_Time':10},
                {'type':'math_now',         'F':2,'l_max':20,'l_lim':40, 'phi':2048,                'end_Time':20},
                {'type':'square_wave_now',  'F':3,'l_max':30,'l_lim':50, 'phi':1024*3,              'end_Time':30},
                {'type':'pulse_wave',       'F':4,'l_max':40,'l_lim':50, 'phi':4096,   'pulse':10, 'end_Time':40},
                {'type':'pulse',            'F':5,'l_max':50,'l_lim':40, 'phi':0,      'pulse':10, 'end_Time':50},

            ]
    """
    def __init__(self):
        self.SCALE = 2048
        self.TABLE_SIZE = 65536

        self.grb = bytearray(3)

        self.sin_table = open('/buf/sin_table.bin', 'rb')       

        self._sin_table = array.array('H', self.sin_table.read())



    @micropython.viper
    def keep_now(self,F, l_max, phi, fs,t):
        return l_max

    @micropython.viper  
    def is_math_now(self,F:int, l_max:int, phi:int, fs:int,t:int) ->int:
        _step = (phi + ((65536 * F*t) // 10 // fs))%65536
        tbl = ptr16(self._sin_table) # 本地變數存取更快
        return (tbl[_step] * l_max) >> 12

    @micropython.viper
    def is_square_wave_now(self,F:int, l_max:int, phi:int, fs:int,t:int) ->int:
        _step = (phi + ((65536 * F*t) // 10 // fs))%65536
        tbl = ptr16(self._sin_table)
        return  l_max if (tbl[_step] * l_max) >> 12 >=2048 else 0


    @micropython.viper
    def is_square_True_now(self,F:int, l_max:int, phi:int, fs:int,t:int) ->int:
        _step = (phi + ((65536 * F*t) // 10 // fs))%65536
        tbl = ptr16(self._sin_table)
        return  1 if tbl[_step] >> 12 >=2048 else 0

    ###########################################################################

    @micropython.native 
    def keep_next(self,F, l_max, phi, fs):
        for i in range(fs):
            yield l_max

    @micropython.native  
    def is_math_next(self,F, l_max, phi, fs):
        __step = int(65536 * F) //10 // fs
        _step = (phi + __step )%65536
        tbl = self._sin_table  # 本地變數存取更快
        for i in range(fs):
            yield (tbl[_step] * l_max) >> 12
            _step = (_step + __step)%65536

    @micropython.native
    def is_square_wave_next(self,F, l_max, phi, fs):
        __step = int(65536 * F) //10 // fs
        _step = (phi + __step )%65536
        tbl = self._sin_table
        for i in range(fs):
            yield  l_max if (tbl[_step]) >> 12 >=2047 else 0
            _step = (_step + __step)%65536


    @micropython.native 
    def is_pulse_wave_next(self,F, l_max, phi, fs,pulse = 2047):
        __step = int(65536 * F) //10 // fs
        _step = (phi + __step )%65536
        tbl = self._sin_table
        for i in range(fs):
            yield  l_max if (tbl[_step]) >> 12 >=pulse else 0
            _step = (_step + __step)%65536

    @micropython.native 
    def is_pulse_next(self,F, l_max, phi, fs,pulse = 1):
        if F <= 0:
            raise ValueError("Frequency F must be greater than zero.")
        p = phi
        gap = int(fs/F)
        if gap == 0:
            gap = 1
        pulse = pulse%gap
        re_value = 0
        for i in range(fs):
            if (i+phi)%gap == 0:
                p = 0
            yield l_max if p <= pulse else 0
            p = p+1


    @micropython.native 
    def is_square_True_next(self,F, l_max, phi, fs):
        __step = int(65536 * F) //10 // fs
        _step = (phi + __step )%65536
        tbl = self._sin_table
        for i in range(fs):
            yield  True if tbl[_step] >> 12 >=2047 else False
            _step = (_step + __step)%65536


    @micropython.native 
    def is_math_pattern_next(self,led_Pattern, setMax: int = 4095, stop:bool= False):
        run_time_List = []
        l_range_List = []
        _run_time = 0
        stop = stop

        if led_Pattern[0]['type'] == 'starter':
            sp = led_Pattern.pop(0)
            for i in range(sp['end_Time']):
                yield 


        for i in led_Pattern:
            run_fs = i['end_Time'] - _run_time
            _run_time = i['end_Time']
            run_time_List.append(run_fs)
            l_max = max(0, min(setMax, i['l_max']))
            l_lim = max(0, min(setMax, i['l_lim']))
            l_range = l_max - l_lim
            l_range_List.append(l_range)

        _stop = True

        while _stop :
            for n, i in enumerate(led_Pattern):
                run_fs = run_time_List[n]
                l_range = l_range_List[n]

                if i['type'] == 'keep':
                    re_value = self.keep_next(i['F'],l_range,i['phi']<<4,run_fs)
                
                elif i['type'] == 'math_now':
                    re_value = self.is_math_next(i['F'],l_range,i['phi']<<4,run_fs)

                elif i['type'] == 'square_wave_now':
                    re_value =  self.is_square_wave_next(i['F'],l_range ,i['phi']<<4,run_fs)

                elif i['type'] == 'pulse_wave':
                    re_value =  self.is_pulse_wave_next(i['F'],l_range ,i['phi']<<4,run_fs,i.get('pulse',2047))

                elif i['type'] == 'pulse':
                    re_value =  self.is_pulse_next(i['F'],l_range ,i['phi']<<4,run_fs,i.get('pulse',2047))


                for value in re_value:
                    yield int(value) + i['l_lim']

            if stop :
                _stop = False
        
        return 



    ###########################################################################
    @micropython.viper
    def _hsv2grb_buf_index(self,h: int, s: int, v: int,index: int, buf: ptr8):
        """
        Convert HSV to RGB and return as an integer packed with RGB components.
        
        Arguments:
        h -- Hue value (0 to 360)
        s -- Saturation value (0 to 255)
        v -- Value/brightness (0 to 255)
        
        Returns:
        An integer where the most significant byte is red, the next byte is green, and the least significant byte is blue.
        """
        
        buf_index = index *3
        if s == 0:
            r = g = b = v
            buf[buf_index] = 255 if g > 255 else int(g)
            buf[buf_index+1] = 255 if r > 255 else int(r)
            buf[buf_index+2] = 255 if b > 255 else int(b)
            return 

        h = h % 360
        region = h // 60
        remainder = (h - (region * 60)) * 255 // 60

        p = (v * (255 - s)) // 255
        q = (v * (255 - ((s * remainder) // 255))) // 255
        t = (v * (255 - ((s * (255 - remainder)) // 255))) // 255

        if region == 0:
            r, g, b = v, t, p
        elif region == 1:
            r, g, b = q, v, p
        elif region == 2:
            r, g, b = p, v, t
        elif region == 3:
            r, g, b = p, q, v
        elif region == 4:
            r, g, b = t, p, v
        else:
            r, g, b = v, p, q
        
        buf[buf_index] = 255 if g > 255 else int(g)
        buf[buf_index+1] = 255 if r > 255 else int(r)
        buf[buf_index+2] = 255 if b > 255 else int(b)
        
        return 

    @micropython.viper
    def hsv_to_rgb_viper(self,h: int, s: int, v: int,buf: ptr8):
        """
        Convert HSV to RGB and return as an integer packed with RGB components.
        
        Arguments:
        h -- Hue value (0 to 360)
        s -- Saturation value (0 to 255)
        v -- Value/brightness (0 to 255)
        
        Returns:
        An integer where the most significant byte is red, the next byte is green, and the least significant byte is blue.
        """
        if s == 0:
            r = g = b = v
            buf[0] = 255 if g > 255 else int(g)
            buf[1] = 255 if r > 255 else int(r)
            buf[2] = 255 if b > 255 else int(b)
            return 

        h = h % 360
        region = h // 60
        remainder = (h - (region * 60)) * 255 // 60

        p = (v * (255 - s)) // 255
        q = (v * (255 - ((s * remainder) // 255))) // 255
        t = (v * (255 - ((s * (255 - remainder)) // 255))) // 255

        if region == 0:
            r, g, b = v, t, p
        elif region == 1:
            r, g, b = q, v, p
        elif region == 2:
            r, g, b = p, v, t
        elif region == 3:
            r, g, b = p, q, v
        elif region == 4:
            r, g, b = t, p, v
        else:
            r, g, b = v, p, q
            
        buf[0] = 255 if g > 255 else int(g)
        buf[1] = 255 if r > 255 else int(r)
        buf[2] = 255 if b > 255 else int(b)
            
        return 


    @micropython.native
    def hsv_to_grb(self,h: int, s: int, v: int):
        self.hsv_to_rgb_viper(h,s,v,self.grb)
        return self.grb[0],self.grb[1],self.grb[2]


    @micropython.viper
    def rgb_to_hsv_viper(self,r: int, g: int, b: int,buf: ptr8)-> ptr16:
        # 類型聲明與記憶體操作
        max_val = r if r > g else g
        max_val = max_val if max_val > b else b
        min_val = r if r < g else g
        min_val = min_val if min_val < b else b
        
        delta = int(max_val - min_val)
        v = int(max_val)
        
        if delta == 0:
            buf[0] = 0
            buf[1] = 0
            buf[2] = v        
            return buf
        
        # 定點數運算參數 (Q16 格式)
        scale = 0x10000  # 65536
        h_temp = 0
        
        # 分支預測優化
        if max_val == min_val:
            h_temp = 0
        elif max_val == r:
            numerator = int(g) - int(b)
            h_temp = (60 * ((numerator) << 16) // delta) + (360 //65535)
        elif max_val == g:
            numerator = int(b) - int(r)
            h_temp = (60 * (numerator << 16) // delta) + (120 //65535)
        elif max_val == b:
            numerator = int(r) - int(g)
            h_temp = (60 * (numerator << 16) // delta) + (240 //65535)
            # 色相歸一化 (0-360)
        h = (h_temp  //65535 ) % 360
        
        # 飽和度計算 (0-255)
        if max_val == 0:
            s = 0
        else:
            s = delta //255 // max_val  # 使用位移取代除法
        
        
        # 飽和度超範圍保護
        s = 255 if s > 255 else s
        
        buf[0] = h
        buf[1] = s
        buf[2] = v   
        
        return buf

    @micropython.native
    def rgb_to_hsv(self,h: int, s: int, v: int):
        self.rgb_to_hsv_viper(h,s,v,self.hsv)
        return self.hsv[0],self.hsv[1],self.hsv[2]


        


        


