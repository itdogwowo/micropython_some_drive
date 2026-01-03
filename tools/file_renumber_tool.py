#!/usr/bin/env python3
# file_renumber.py - 文件重新編號工具
import os
import shutil
from pathlib import Path
import sys

def ask(prompt, default=None, cast=str):
    """
    通用詢問函數
    """
    tail = f" [{default}]" if default is not None else ""
    ans = input(prompt + tail + ": ").strip()
    return cast(ans) if ans else default

def ask_choice(prompt, choices, default=None):
    """
    選擇題詢問函數
    """
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

def list_folders(directory="."):
    """
    列出當前目錄下的所有文件夾
    """
    folders = []
    try:
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            if os.path.isdir(item_path):
                folders.append(item)
    except Exception as e:
        print(f"讀取目錄錯誤: {e}")
    return sorted(folders)

def extract_number_from_filename(filename):
    """
    從文件名中提取數字部分
    
    支持格式:
    - "001.txt" -> 1
    - "123_image.jpg" -> 123
    - "file_456.png" -> 456
    - "789" -> 789
    """
    # 移除副檔名
    name_without_ext = os.path.splitext(filename)[0]
    
    # 嘗試直接轉換
    try:
        return int(name_without_ext)
    except ValueError:
        pass
    
    # 嘗試從字符串中提取數字
    import re
    match = re.search(r'\d+', name_without_ext)
    if match:
        try:
            return int(match.group())
        except ValueError:
            pass
    
    return None

def get_sorted_files_by_number(folder_path, filter_ext=None):
    """
    獲取按數字排序的文件列表
    
    返回: (文件列表, 數字列表)
    """
    path = Path(folder_path)
    files = []
    numbers = []
    
    for item in path.iterdir():
        if item.is_file():
            # 檢查副檔名過濾
            if filter_ext and item.suffix.lower() != filter_ext.lower():
                continue
            
            # 提取數字
            num = extract_number_from_filename(item.name)
            if num is not None:
                files.append(item)
                numbers.append(num)
            else:
                print(f"警告: 無法從文件名提取數字: {item.name}")
    
    # 按數字排序
    sorted_pairs = sorted(zip(numbers, files))
    sorted_numbers = [pair[0] for pair in sorted_pairs]
    sorted_files = [pair[1] for pair in sorted_pairs]
    
    return sorted_files, sorted_numbers

def renumber_files(folder_path, start_number=0, digits=3, filter_ext=None, 
                   keep_original=False, prefix="", suffix=""):
    """
    重新編號文件
    
    參數:
        folder_path: 文件夾路徑
        start_number: 起始編號
        digits: 數字位數 (如3表示001, 002)
        filter_ext: 過濾副檔名
        keep_original: 是否保留原始文件
        prefix: 文件名前綴
        suffix: 文件名後綴 (在編號和副檔名之間)
    """
    path = Path(folder_path)
    
    if not path.exists():
        print(f"錯誤: 文件夾 '{folder_path}' 不存在！")
        return False
    
    # 獲取排序後的文件
    sorted_files, original_numbers = get_sorted_files_by_number(folder_path, filter_ext)
    
    if not sorted_files:
        print("警告: 未找到可重新編號的文件！")
        return False
    
    print(f"找到 {len(sorted_files)} 個文件需要重新編號")
    print("原始編號順序:", original_numbers[:10], "..." if len(original_numbers) > 10 else "")
    
    # 確認操作
    confirm = ask_choice(f"確定要重新編號 {len(sorted_files)} 個文件嗎?", ["Y", "N"], default="Y")
    if confirm != "Y":
        print("操作取消")
        return False
    
    # 重新編號
    renamed_count = 0
    failed_count = 0
    
    for i, file_path in enumerate(sorted_files):
        current_number = start_number + i
        new_number_str = f"{current_number:0{digits}d}"
        
        # 構建新文件名
        file_ext = file_path.suffix
        new_filename = f"{prefix}{new_number_str}{suffix}{file_ext}"
        new_path = path / new_filename
        
        try:
            if keep_original:
                # 複製文件
                shutil.copy2(str(file_path), str(new_path))
                action = "複製並重命名"
            else:
                # 移動/重命名文件
                file_path.rename(new_path)
                action = "重命名"
            
            print(f"{action}: {file_path.name} -> {new_filename}")
            renamed_count += 1
            
        except Exception as e:
            print(f"錯誤: 無法重命名 {file_path.name}: {e}")
            failed_count += 1
    
    # 輸出結果
    print("\n" + "=" * 50)
    print("重新編號完成！")
    print(f"成功處理: {renamed_count} 個文件")
    print(f"處理失敗: {failed_count} 個文件")
    print(f"新編號範圍: {start_number:0{digits}d} 到 {(start_number + len(sorted_files) - 1):0{digits}d}")
    print("=" * 50)
    
    return True

def preview_renumbering(folder_path, start_number=0, digits=3, filter_ext=None, 
                       prefix="", suffix=""):
    """
    預覽重新編號結果
    """
    path = Path(folder_path)
    
    if not path.exists():
        print(f"錯誤: 文件夾 '{folder_path}' 不存在！")
        return
    
    # 獲取排序後的文件
    sorted_files, original_numbers = get_sorted_files_by_number(folder_path, filter_ext)
    
    if not sorted_files:
        print("未找到可重新編號的文件")
        return
    
    print(f"\n重新編號預覽 - {folder_path}")
    print("=" * 60)
    print(f"文件總數: {len(sorted_files)}")
    print(f"起始編號: {start_number}")
    print(f"數字位數: {digits}")
    print(f"文件名前綴: '{prefix}'")
    print(f"文件名後綴: '{suffix}'")
    print("-" * 60)
    
    # 顯示前後對比
    print("編號對比 (顯示前10個):")
    print(f"{'原始文件名':<30} -> {'新文件名':<30}")
    print("-" * 65)
    
    for i, file_path in enumerate(sorted_files[:10]):
        current_number = start_number + i
        new_number_str = f"{current_number:0{digits}d}"
        file_ext = file_path.suffix
        new_filename = f"{prefix}{new_number_str}{suffix}{file_ext}"
        
        print(f"{file_path.name:<30} -> {new_filename:<30}")
    
    if len(sorted_files) > 10:
        print(f"... 還有 {len(sorted_files) - 10} 個文件")
    
    print("-" * 60)
    print(f"新編號範圍: {start_number:0{digits}d} 到 {(start_number + len(sorted_files) - 1):0{digits}d}")

def batch_renumber_folders(base_folder, start_number=0, digits=3, filter_ext=None,
                          keep_original=False, prefix="", suffix=""):
    """
    批量重新編號多個文件夾
    """
    path = Path(base_folder)
    
    if not path.exists():
        print(f"錯誤: 文件夾 '{base_folder}' 不存在！")
        return False
    
    # 獲取所有子文件夾
    subfolders = []
    for item in path.iterdir():
        if item.is_dir():
            subfolders.append(item)
    
    if not subfolders:
        print("未找到子文件夾")
        return False
    
    print(f"找到 {len(subfolders)} 個子文件夾:")
    for i, folder in enumerate(subfolders[:10], 1):
        print(f"  {i}. {folder.name}")
    if len(subfolders) > 10:
        print(f"  ... 還有 {len(subfolders) - 10} 個文件夾")
    
    # 確認批量操作
    confirm = ask_choice(f"確定要批量重新編號 {len(subfolders)} 個文件夾嗎?", ["Y", "N"], default="N")
    if confirm != "Y":
        print("操作取消")
        return False
    
    # 執行批量重新編號
    total_renamed = 0
    total_failed = 0
    
    for folder in subfolders:
        print(f"\n處理文件夾: {folder.name}")
        
        # 獲取該文件夾中的文件數量
        sorted_files, _ = get_sorted_files_by_number(folder, filter_ext)
        
        if not sorted_files:
            print(f"  跳過: 無可重新編號的文件")
            continue
        
        # 重新編號
        success = renumber_files(
            folder,
            start_number=start_number,
            digits=digits,
            filter_ext=filter_ext,
            keep_original=keep_original,
            prefix=prefix,
            suffix=suffix
        )
        
        if success:
            total_renamed += len(sorted_files)
        else:
            total_failed += 1
    
    print("\n" + "=" * 50)
    print("批量重新編號完成！")
    print(f"總共處理文件夾: {len(subfolders)} 個")
    print(f"總共重新編號文件: {total_renamed} 個")
    print(f"處理失敗的文件夾: {total_failed} 個")
    print("=" * 50)
    
    return True

def main():
    """
    主交互函數
    """
    print("=" * 60)
    print("文件重新編號工具")
    print("=" * 60)
    
    while True:
        print("\n主選單:")
        print("1. 單個文件夾重新編號")
        print("2. 預覽重新編號結果")
        print("3. 批量文件夾重新編號")
        print("4. 列出當前目錄文件夾")
        print("5. 退出")
        
        choice = ask_choice("請選擇操作", ["1", "2", "3", "4", "5"], default="1")
        
        if choice == "1":
            # 單個文件夾重新編號
            print("\n" + "=" * 50)
            print("單個文件夾重新編號")
            print("=" * 50)
            
            # 選擇文件夾
            current_dir = os.getcwd()
            folders = list_folders(current_dir)
            
            if folders:
                print(f"\n當前目錄下的文件夾:")
                for i, folder in enumerate(folders, 1):
                    print(f"  {i}. {folder}")
                print("  0. 手動輸入路徑")
                
                folder_choice = ask("選擇文件夾編號或輸入路徑", default="0")
                
                if folder_choice.isdigit():
                    choice_num = int(folder_choice)
                    if 1 <= choice_num <= len(folders):
                        folder_path = os.path.join(current_dir, folders[choice_num - 1])
                    else:
                        folder_path = ask("請輸入文件夾路徑")
                else:
                    folder_path = folder_choice
            else:
                folder_path = ask("請輸入文件夾路徑")
            
            # 預覽當前狀態
            print("\n當前文件夾內容預覽:")
            sorted_files, numbers = get_sorted_files_by_number(folder_path)
            if sorted_files:
                print(f"找到 {len(sorted_files)} 個數字命名的文件")
                print("當前編號:", numbers[:10], "..." if len(numbers) > 10 else "")
            else:
                print("未找到數字命名的文件")
                continue
            
            # 設置重新編號參數
            print("\n重新編號設置:")
            start_num = ask("起始編號", default=0, cast=int)
            digits = ask("數字位數 (如3表示001, 002)", default=3, cast=int)
            
            # 詢問是否過濾副檔名
            filter_ext = None
            filter_choice = ask_choice("是否過濾特定副檔名?", ["Y", "N"], default="N")
            if filter_choice == "Y":
                filter_ext = ask("請輸入副檔名 (如 .txt, .jpg)", default=".txt")
                if not filter_ext.startswith("."):
                    filter_ext = "." + filter_ext
            
            # 文件名前綴和後綴
            prefix = ask("文件名前綴 (可選)", default="")
            suffix = ask("文件名後綴 (可選，在編號和副檔名之間)", default="")
            
            # 操作模式
            print("\n操作模式:")
            print("  M: 移動/重命名 (原始文件會被覆蓋)")
            print("  C: 複製 (保留原始文件)")
            mode = ask_choice("選擇模式", ["M", "C"], default="M")
            keep_original = (mode == "C")
            
            # 預覽結果
            preview_renumbering(folder_path, start_num, digits, filter_ext, prefix, suffix)
            
            # 執行重新編號
            success = renumber_files(
                folder_path,
                start_number=start_num,
                digits=digits,
                filter_ext=filter_ext,
                keep_original=keep_original,
                prefix=prefix,
                suffix=suffix
            )
            
            if success:
                print("\n重新編號完成！")
            
            # 是否繼續
            continue_choice = ask_choice("\n是否處理其他文件夾?", ["Y", "N"], default="Y")
            if continue_choice != "Y":
                print("感謝使用！")
                break
        
        elif choice == "2":
            # 預覽重新編號結果
            print("\n" + "=" * 50)
            print("預覽重新編號結果")
            print("=" * 50)
            
            folder_path = ask("請輸入文件夾路徑")
            
            # 設置參數
            start_num = ask("起始編號", default=0, cast=int)
            digits = ask("數字位數", default=3, cast=int)
            
            filter_ext = None
            filter_choice = ask_choice("是否過濾特定副檔名?", ["Y", "N"], default="N")
            if filter_choice == "Y":
                filter_ext = ask("請輸入副檔名", default=".txt")
                if not filter_ext.startswith("."):
                    filter_ext = "." + filter_ext
            
            prefix = ask("文件名前綴 (可選)", default="")
            suffix = ask("文件名後綴 (可選)", default="")
            
            # 顯示預覽
            preview_renumbering(folder_path, start_num, digits, filter_ext, prefix, suffix)
        
        elif choice == "3":
            # 批量文件夾重新編號
            print("\n" + "=" * 50)
            print("批量文件夾重新編號")
            print("=" * 50)
            
            base_folder = ask("請輸入包含多個文件夾的根目錄路徑", default=os.getcwd())
            
            # 設置參數
            print("\n批量重新編號設置:")
            start_num = ask("起始編號", default=0, cast=int)
            digits = ask("數字位數", default=3, cast=int)
            
            filter_ext = None
            filter_choice = ask_choice("是否過濾特定副檔名?", ["Y", "N"], default="N")
            if filter_choice == "Y":
                filter_ext = ask("請輸入副檔名", default=".txt")
                if not filter_ext.startswith("."):
                    filter_ext = "." + filter_ext
            
            prefix = ask("文件名前綴 (可選)", default="")
            suffix = ask("文件名後綴 (可選)", default="")
            
            mode = ask_choice("操作模式 (M=移動, C=複製)", ["M", "C"], default="M")
            keep_original = (mode == "C")
            
            # 執行批量重新編號
            batch_renumber_folders(
                base_folder,
                start_number=start_num,
                digits=digits,
                filter_ext=filter_ext,
                keep_original=keep_original,
                prefix=prefix,
                suffix=suffix
            )
        
        elif choice == "4":
            # 列出當前目錄文件夾
            print("\n" + "=" * 50)
            print("當前目錄文件夾列表")
            print("=" * 50)
            
            current_dir = os.getcwd()
            folders = list_folders(current_dir)
            
            print(f"當前目錄: {current_dir}")
            print("-" * 50)
            
            if folders:
                for i, folder in enumerate(folders, 1):
                    folder_path = os.path.join(current_dir, folder)
                    try:
                        # 檢查文件夾中數字命名的文件數量
                        sorted_files, _ = get_sorted_files_by_number(folder_path)
                        file_count = len(sorted_files)
                        print(f"{i:2d}. {folder} ({file_count}# 文件重新編號工具（續")

                        print(f"{i:2d}. {folder} ({file_count} 個數字命名文件)")
                    except:
                        print(f"{i:2d}. {folder} (無法訪問)")
            else:
                print("沒有找到文件夾")
        
        elif choice == "5":
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
        sys.exit(1)