#!/usr/bin/env python3
# media_processor.py ── 統一媒體處理工具：支援 MP4/AVI/MOV/JPG/JPEG/PNG
# pip install opencv-python tqdm
import os
import cv2
import numpy as np
import re
from pathlib import Path
from tqdm import tqdm
import sys

def ask(prompt, default=None, cast=str):
    """通用詢問函數"""
    tail = f" [{default}]" if default is not None else ""
    ans = input(prompt + tail + ": ").strip()
    return cast(ans) if ans else default

def ask_choice(prompt, choices, default=None):
    """選擇題詢問函數"""
    c_up = [c.upper() for c in choices]
    default_up = default.upper() if default else None
    while True:
        tail = f" ({'/'.join(choices)})"
        if default:
            tail += f" [{default}]"
        ans = input(prompt + tail + ": ").strip().upper()
        if not ans and default_up:
            return default_up
        if ans in c_up:
            return ans
        print("無效選項，請重新輸入：", "/".join(choices))

def natural_key(name):
    """自然排序鍵函數"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', name)]

def list_media_files(directory=".", media_type="all"):
    """列出目錄下的媒體文件"""
    # 定義支援的格式
    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.m4v', '.webm']
    image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif', '.webp']
    
    media_files = []
    try:
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            if os.path.isfile(item_path):
                ext = os.path.splitext(item)[1].lower()
                
                if media_type == "all":
                    if ext in video_extensions or ext in image_extensions:
                        media_files.append(item_path)
                elif media_type == "video":
                    if ext in video_extensions:
                        media_files.append(item_path)
                elif media_type == "image":
                    if ext in image_extensions:
                        media_files.append(item_path)
    except Exception as e:
        print(f"讀取目錄錯誤: {e}")
    
    # 自然排序
    media_files.sort(key=lambda x: natural_key(os.path.basename(x)))
    return media_files

def list_folders(directory="."):
    """列出當前目錄下的所有文件夾"""
    folders = []
    try:
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            if os.path.isdir(item_path):
                folders.append(item_path)
    except Exception as e:
        print(f"讀取目錄錯誤: {e}")
    return sorted(folders)

def preview_media_files(folder_path, media_type="all"):
    """預覽文件夾中的媒體文件"""
    path = Path(folder_path)
    if not path.exists():
        print(f"文件夾不存在: {folder_path}")
        return []
    
    # 獲取媒體文件
    media_files = list_media_files(folder_path, media_type)
    
    print(f"\n媒體文件預覽: {folder_path}")
    print("-" * 50)
    
    # 顯示文件列表
    max_show = min(20, len(media_files))
    for i, file_path in enumerate(media_files[:max_show], 1):
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path) // 1024  # KB
        print(f"  {i:2d}. {file_name} ({file_size} KB)")
    
    if len(media_files) > max_show:
        print(f"  ... 還有 {len(media_files) - max_show} 個媒體文件")
    
    # 統計信息
    print("-" * 50)
    print(f"總媒體文件數: {len(media_files)}")
    
    # 按類型統計
    video_count = sum(1 for f in media_files if os.path.splitext(f)[1].lower() in 
                     ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.m4v', '.webm'])
    image_count = len(media_files) - video_count
    print(f"視頻文件: {video_count} 個")
    print(f"圖片文件: {image_count} 個")
    
    return media_files

def resize_crop(frame, W, H):
    """調整大小並居中裁剪"""
    h, w = frame.shape[:2]
    scale = max(W / w, H / h)
    rs = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    x0 = (rs.shape[1] - W) // 2
    y0 = (rs.shape[0] - H) // 2
    return rs[y0:y0 + H, x0:x0 + W]

def pack_gs4(gray_u8):
    """
    gray_u8: HxW uint8 (0..255)
    回傳 packed bytes：每 byte 兩像素 (hi_nibble, lo_nibble)
    """
    g4 = (gray_u8 >> 4).astype(np.uint8)  # 0..15
    flat = g4.reshape(-1)
    if (flat.size % 2) != 0:
        flat = np.concatenate([flat, np.zeros(1, dtype=np.uint8)])
    hi = flat[0::2]
    lo = flat[1::2]
    packed = (hi << 4) | lo
    return packed.tobytes()

def process_video_file(video_path, output_format, width, height, quality=None, output_dir=None, rotate=0):
    """處理單個視頻文件"""
    if not os.path.isfile(video_path):
        print(f"檔案不存在: {video_path}")
        return False
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"無法開啟視頻文件: {video_path}")
        return False
    
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # 確定輸出目錄
    if output_dir is None:
        src_dir = os.path.dirname(video_path) or "."
        file_name = os.path.splitext(os.path.basename(video_path))[0]
        output_dir = os.path.join(src_dir, f"{file_name}_{output_format.lower()}")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 副檔名
    ext = {"JPEG": "jpeg", "GS8": "g8", "GS4": "g4"}[output_format]
    
    print(f"處理: {os.path.basename(video_path)}")
    print(f"原始尺寸: {src_w}x{src_h}, FPS: {fps:.1f}, 總幀數: {total_frames}")
    print(f"輸出尺寸: {width}x{height}, 格式: {output_format}")
    if rotate:
        print(f"旋轉: {rotate * 90}° 順時針")
    print(f"輸出目錄: {output_dir}")
    
    idx_out = 0
    success_count = 0
    
    for _ in tqdm(range(total_frames), desc=f"Export {output_format}", unit="frame"):
        ret, frame = cap.read()
        if not ret:
            break
        
        # 處理圖像
        img = resize_crop(frame, width, height)
        
        # 旋轉
        if rotate:
            for _ in range(rotate % 4):
                img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        
        out_path = os.path.join(output_dir, f"{idx_out:06d}.{ext}")
        
        try:
            if output_format == "JPEG":
                cv2.imwrite(out_path, img, [cv2.IMWRITE_JPEG_QUALITY, quality])
            elif output_format == "GS8":
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                gray.tofile(out_path)
            elif output_format == "GS4":
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                packed = pack_gs4(gray)
                with open(out_path, "wb") as f:
                    f.write(packed)
            
            success_count += 1
        except Exception as e:
            print(f"錯誤: 處理第 {idx_out} 幀時發生錯誤: {e}")
        
        idx_out += 1
    
    cap.release()
    
    print(f"完成！成功輸出 {success_count} 幀至 {output_dir}")
    if output_format in ("GS8", "GS4"):
        bpp = "1 byte/px" if output_format == "GS8" else "4 bit/px"
        print(f"注意：{output_format} 為 RAW 灰階資料({bpp})，播放端需使用相同寬高：{width}x{height}")
    
    return True

def process_image_file(image_path, output_format, width, height, quality=None, output_dir=None, rotate=0, index=0):
    """處理單個圖片文件"""
    if not os.path.isfile(image_path):
        print(f"檔案不存在: {image_path}")
        return False
    
    img = cv2.imread(image_path)
    if img is None:
        print(f"無法讀取圖片: {image_path}")
        return False
    
    src_h, src_w = img.shape[:2]
    
    # 確定輸出目錄
    if output_dir is None:
        src_dir = os.path.dirname(image_path) or "."
        output_dir = os.path.join(src_dir, f"converted_{output_format.lower()}")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 副檔名
    ext = {"JPEG": "jpeg", "GS8": "g8", "GS4": "g4"}[output_format]
    
    # 處理圖像
    processed_img = resize_crop(img, width, height)
    
    # 旋轉
    if rotate:
        for _ in range(rotate % 4):
            processed_img = cv2.rotate(processed_img, cv2.ROTATE_90_CLOCKWISE)
    
    out_path = os.path.join(output_dir, f"{index:03d}.{ext}")
    
    try:
        if output_format == "JPEG":
            cv2.imwrite(out_path, processed_img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        elif output_format == "GS8":
            gray = cv2.cvtColor(processed_img, cv2.COLOR_BGR2GRAY)
            gray.tofile(out_path)
        elif output_format == "GS4":
            gray = cv2.cvtColor(processed_img, cv2.COLOR_BGR2GRAY)
            packed = pack_gs4(gray)
            with open(out_path, "wb") as f:
                f.write(packed)
        
        return True
    except Exception as e:
        print(f"錯誤: 處理圖片時發生錯誤: {e}")
        return False

def process_media_folder(folder_path, output_format, width, height, quality=None, 
                        output_base_dir=None, rotate=0, media_type="all"):
    """處理文件夾中的所有媒體文件"""
    if not os.path.isdir(folder_path):
        print(f"文件夾不存在: {folder_path}")
        return False
    
    # 獲取所有媒體文件
    media_files = list_media_files(folder_path, media_type)
    
    if not media_files:
        print(f"在 {folder_path} 中未找到媒體文件")
        return False
    
    print(f"\n找到 {len(media_files)} 個媒體文件:")
    for i, media in enumerate(media_files, 1):
        print(f"  {i:2d}. {os.path.basename(media)}")
    
    # 確認處理
    confirm = ask_choice(f"是否處理所有 {len(media_files)} 個媒體文件?", ["Y", "N"], default="Y")
    if confirm != "Y":
        return False
    
    # 分離視頻和圖片
    video_files = []
    image_files = []
    
    for file_path in media_files:
        ext = os.path.splitext(file_path)[1].lower()
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.m4v', '.webm']
        
        if ext in video_extensions:
            video_files.append(file_path)
        else:
            image_files.append(file_path)
    
    # 處理視頻文件
    video_success = 0
    if video_files:
        print(f"\n處理 {len(video_files)} 個視頻文件...")
        for i, video_path in enumerate(video_files, 1):
            print(f"\n[{i}/{len(video_files)}] 視頻: {os.path.basename(video_path)}")
            
            # 為每個視頻創建獨立的輸出目錄
            if output_base_dir:
                video_name = os.path.splitext(os.path.basename(video_path))[0]
                output_dir = os.path.join(output_base_dir, f"{video_name}_{output_format.lower()}")
            else:
                output_dir = None
            
            success = process_video_file(video_path, output_format, width, height, 
                                       quality, output_dir, rotate)
            if success:
                video_success += 1
    
    # 處理圖片文件
    image_success = 0
    if image_files:
        print(f"\n處理 {len(image_files)} 個圖片文件...")
        
        # 為所有圖片創建統一的輸出目錄
        if output_base_dir:
            output_dir = os.path.join(output_base_dir, f"images_{output_format.lower()}")
        else:
            output_dir = os.path.join(folder_path, f"converted_{output_format.lower()}")
        
        os.makedirs(output_dir, exist_ok=True)
        
        for i, image_path in enumerate(tqdm(image_files, desc="Processing images", unit="image")):
            success = process_image_file(image_path, output_format, width, height,
                                       quality, output_dir, rotate, i)
            if success:
                image_success += 1
    
    print(f"\n文件夾處理完成！")
    print(f"視頻文件: {video_success}/{len(video_files)} 成功")
    print(f"圖片文件: {image_success}/{len(image_files)} 成功")
    print(f"總計: {video_success + image_success}/{len(media_files)} 成功")
    
    return True

def main():
    """主函數"""
    print("=" * 60)
    print("統一媒體處理工具 - 支援 MP4/AVI/MOV/JPG/JPEG/PNG 等格式")
    print("=" * 60)
    
    while True:
        print("\n處理模式選擇:")
        print("1. 處理單個媒體文件")
        print("2. 處理整個文件夾")
        print("3. 退出")
        
        mode_choice = ask_choice("請選擇處理模式", ["1", "2", "3"], default="1")
        
        if mode_choice == "3":
            print("感謝使用！")
            break
        
        # 獲取輸出格式
        output_format = ask_choice("輸出格式", ["JPEG", "GS8", "GS4"], default="JPEG")
        
        # 獲取輸出尺寸
        width = ask("輸出寬度", default=320, cast=int)
        height = ask("輸出高度", default=240, cast=int)
        
        # JPEG 需要品質參數
        quality = None
        if output_format == "JPEG":
            quality = ask("JPEG 品質 (1-100)", default=85, cast=int)
            quality = max(1, min(100, quality))
        
        # 旋轉參數
        rotate = ask("順時針旋轉 90° 次數 (0-3)", default=0, cast=int)
        rotate = rotate % 4  # 確保在 0-3 範圍內
        
        if mode_choice == "1":
            # 處理單個文件
            print("\n" + "=" * 50)
            print("單文件處理模式")
            print("=" * 50)
            
            # 列出當前目錄的媒體文件
            current_dir = os.getcwd()
            media_files = list_media_files(current_dir, "all")
            
            if media_files:
                print(f"\n當前目錄下的媒體文件:")
                for i, file_path in enumerate(media_files, 1):
                    file_name = os.path.basename(file_path)
                    file_size = os.path.getsize(file_path) // 1024
                    print(f"  {i}. {file_name} ({file_size} KB)")
                print("  0. 手動輸入路徑")
                
                file_choice = ask("選擇文件編號或輸入路徑", default="1")
                
                if file_choice.isdigit():
                    choice_num = int(file_choice)
                    if 1 <= choice_num <= len(media_files):
                        media_path = media_files[choice_num - 1]
                    else:
                        media_path = ask("請輸入媒體文件路徑")
                else:
                    media_path = file_choice
            else:
                media_path = ask("請輸入媒體文件路徑")
            
            # 判斷文件類型並處理
            ext = os.path.splitext(media_path)[1].lower()
            video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.m4v', '.webm']
            
            if ext in video_extensions:
                # 處理視頻文件
                process_video_file(media_path, output_format, width, height, quality, None, rotate)
            else:
                # 處理圖片文件
                process_image_file(media_path, output_format, width, height, quality, None, rotate, 0)
            
        elif mode_choice == "2":
            # 處理文件夾
            print("\n" + "=" * 50)
            print("文件夾批量處理模式")
            print("=" * 50)
            
            # 選擇媒體類型
            print("\n處理類型選擇:")
            print("1. 所有媒體文件 (視頻+圖片)")
            print("2. 僅視頻文件")
            print("3. 僅圖片文件")
            
            type_choice = ask_choice("請選擇處理類型", ["1", "2", "3"], default="1")
            
            media_type_map = {"1": "all", "2": "video", "3": "image"}
            media_type = media_type_map[type_choice]
            
            # 列出當前目錄的文件夾
            current_dir = os.getcwd()
            folders = list_folders(current_dir)
            
            if folders:
                print(f"\n當前目錄下的文件夾:")
                for i, folder_path in enumerate(folders, 1):
                    folder_name = os.path.basename(folder_path)
                    print(f"  {i}. {folder_name}")
                print("  0. 手動輸入路徑")
                
                folder_choice = ask("選擇文件夾編號或輸入路徑", default="0")
                
                if folder_choice.isdigit():
                    choice_num = int(folder_choice)
                    if 1 <= choice_num <= len(folders):
                        folder_path = folders[choice_num - 1]
                    else:
                        folder_path = ask("請輸入文件夾路徑")
                else:
                    folder_path = folder_choice
            else:
                folder_path = ask("請輸入文件夾路徑")
            
            # 預覽文件夾內容
            media_files = preview_media_files(folder_path, media_type)
            
            if not media_files:
                print("未找到媒體文件，請選擇其他文件夾")
                continue
            
            # 詢問輸出目錄
            output_base_dir = ask("輸出根目錄 (留空則在每個媒體所在目錄創建輸出文件夾)", default="")
            if output_base_dir and not os.path.exists(output_base_dir):
                os.makedirs(output_base_dir, exist_ok=True)
            
            # 處理文件夾
            process_media_folder(folder_path, output_format, width, height, 
                               quality, output_base_dir, rotate, media_type)
        
        # 詢問是否繼續
        continue_choice = ask_choice("\n是否繼續處理其他文件?", ["Y", "N"], default="Y")
        if continue_choice != "Y":
            print("感謝使用！")
            break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程序被用戶中斷")
        sys.exit(0)
    except Exception as e:
        print(f"\n發生錯誤: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)