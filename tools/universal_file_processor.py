#!/usr/bin/env python3
# universal_file_processor.py - 通用文件分離工具
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

def separate_odd_even_files(source_folder, odd_folder="odd_files", even_folder="even_files", 
                           move_files=True, filter_ext=None):
    """
    將源文件夾中的文件按編號奇偶性分離
    
    參數:
        source_folder: 源文件夾路徑
        odd_folder: 奇數文件存儲文件夾名
        even_folder: 偶數文件存儲文件夾名
        move_files: True=移動文件, False=複製文件
        filter_ext: 過濾特定副檔名 (如 ".txt", ".jpg")，None表示所有文件
    """
    source_path = Path(source_folder)
    
    # 檢查源文件夾是否存在
    if not source_path.exists():
        print(f"錯誤: 源文件夾 '{source_folder}' 不存在！")
        return False
    
    # 創建目標文件夾路徑
    odd_path = source_path / odd_folder
    even_path = source_path / even_folder
    
    # 創建目標文件夾
    odd_path.mkdir(exist_ok=True)
    even_path.mkdir(exist_ok=True)
    
    # 統計
    odd_count = 0
    even_count = 0
    skipped_count = 0
    non_numeric_count = 0
    
    print(f"正在處理文件夾: {source_path}")
    if filter_ext:
        print(f"過濾副檔名: {filter_ext}")
    print("=" * 50)
    
    # 獲取所有文件
    all_files = []
    for item in source_path.iterdir():
        if item.is_file():
            if filter_ext:
                if item.suffix.lower() == filter_ext.lower():
                    all_files.append(item)
            else:
                all_files.append(item)
    
    if not all_files:
        print("警告: 未找到符合條件的文件！")
        return False
    
    # 處理每個文件
    for file_path in all_files:
        # 獲取文件名（不含擴展名）
        file_stem = file_path.stem
        
        try:
            # 嘗試將文件名轉換為整數
            file_number = int(file_stem)
            
            # 根據奇偶性決定目標文件夾
            if file_number % 2 == 0:  # 偶數
                target_path = even_path / file_path.name
                even_count += 1
                status = "偶數"
            else:  # 奇數
                target_path = odd_path / file_path.name
                odd_count += 1
                status = "奇數"
            
            # 移動或複製文件
            if move_files:
                shutil.move(str(file_path), str(target_path))
                action = "移動"
            else:
                shutil.copy2(str(file_path), str(target_path))
                action = "複製"
            
            print(f"{action}: {file_path.name} -> {status}文件夾")
            
        except ValueError:
            # 如果文件名不是數字，跳過該文件
            non_numeric_count += 1
            if non_numeric_count <= 5:  # 只顯示前5個非數字文件
                print(f"跳過: {file_path.name} (非數字命名)")
            elif non_numeric_count == 6:
                print(f"... 還有更多非數字命名的文件")
            skipped_count += 1
            continue
    
    # 輸出結果摘要
    print("\n" + "=" * 50)
    print("處理完成！")
    print(f"源文件夾: {source_path}")
    print(f"奇數文件夾: {odd_path} ({odd_count} 個文件)")
    print(f"偶數文件夾: {even_path} ({even_count} 個文件)")
    if skipped_count > 0:
        print(f"跳過的非數字文件: {skipped_count} 個")
    print("=" * 50)
    
    return True

def preview_folder(folder_path, show_all=False, filter_ext=None):
    """
    預覽文件夾內容
    """
    path = Path(folder_path)
    if not path.exists():
        print(f"文件夾不存在: {folder_path}")
        return
    
    print(f"\n文件夾內容預覽: {folder_path}")
    if filter_ext:
        print(f"過濾副檔名: {filter_ext}")
    print("-" * 50)
    
    # 獲取所有文件
    all_files = []
    file_types = {}
    
    for item in path.iterdir():
        if item.is_file():
            if filter_ext:
                if item.suffix.lower() == filter_ext.lower():
                    all_files.append(item)
            else:
                all_files.append(item)
            
            # 統計文件類型
            ext = item.suffix.lower()
            if ext:
                file_types[ext] = file_types.get(ext, 0) + 1
            else:
                file_types["無副檔名"] = file_types.get("無副檔名", 0) + 1
    
    # 顯示文件列表
    max_show = 20 if not show_all else len(all_files)
    for i, item in enumerate(all_files[:max_show]):
        # 檢查是否為數字命名
        try:
            file_num = int(item.stem)
            num_info = f" [編號:{file_num:03d}]"
        except ValueError:
            num_info = " [非數字]"
        
        print(f"  {item.name}{num_info}")
    
    if len(all_files) > max_show and not show_all:
        print(f"  ... 還有 {len(all_files) - max_show} 個文件")
    
    # 統計信息
    print("-" * 50)
    print(f"總文件數: {len(all_files)}")
    
    if file_types:
        print("文件類型統計:")
        for ext, count in sorted(file_types.items()):
            print(f"  {ext if ext else '無副檔名'}: {count} 個")
    
    # 數字文件統計
    numeric_files = 0
    for item in all_files:
        try:
            int(item.stem)
            numeric_files += 1
        except ValueError:
            pass
    
    print(f"數字命名文件: {numeric_files} 個")
    print(f"非數字命名文件: {len(all_files) - numeric_files} 個")

def main():
    """
    主交互函數
    """
    print("=" * 60)
    print("通用文件分離工具 - 按數字編號奇偶分離")
    print("=" * 60)
    
    while True:
        print("\n主選單:")
        print("1. 選擇文件夾進行處理")
        print("2. 預覽文件夾內容")
        print("3. 列出當前目錄文件夾")
        print("4. 批量處理多個文件夾")
        print("5. 退出")
        
        choice = ask_choice("請選擇操作", ["1", "2", "3", "4", "5"], default="1")
        
        if choice == "1":
            # 選擇文件夾進行處理
            print("\n" + "=" * 50)
            print("文件夾處理選項")
            print("=" * 50)
            
            # 輸入文件夾路徑
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
            
            # 預覽文件夾
            preview_folder(folder_path)
            
            # 詢問是否過濾副檔名
            filter_ext = None
            filter_choice = ask_choice("是否過濾特定副檔名?", ["Y", "N"], default="N")
            if filter_choice == "Y":
                filter_ext = ask("請輸入副檔名 (如 .txt, .jpg, .png)", default=".txt")
                if not filter_ext.startswith("."):
                    filter_ext = "." + filter_ext
            
            # 確認是否繼續
            confirm = ask_choice("是否處理此文件夾?", ["Y", "N"], default="Y")
            if confirm != "Y":
                continue
            
            # 選擇操作模式
            print("\n處理模式:")
            print("  M: 移動文件 (原始文件會被移除)")
            print("  C: 複製文件 (保留原始文件)")
            mode = ask_choice("選擇模式", ["M", "C"], default="M")
            move_files = (mode == "M")
            
            # 自定義文件夾名稱
            print("\n目標文件夾設置 (按Enter使用默認值):")
            odd_name = ask("奇數文件夾名稱", default="odd_files")
            even_name = ask("偶數文件夾名稱", default="even_files")
            
            # 執行處理
            print("\n開始處理...")
            success = separate_odd_even_files(
                folder_path, 
                odd_folder=odd_name,
                even_folder=even_name,
                move_files=move_files,
                filter_ext=filter_ext
            )
            
            if success:
                print("\n處理完成！")
                if move_files:
                    print("文件已移動到新文件夾。")
                else:
                    print("文件已複製到新文件夾。")
            
            # 是否繼續處理其他文件夾
            continue_choice = ask_choice("\n是否處理其他文件夾?", ["Y", "N"], default="Y")
            if continue_choice != "Y":
                print("感謝使用！")
                break
        
        elif choice == "2":
            # 預覽文件夾內容
            print("\n" + "=" * 50)
            print("文件夾預覽")
            print("=" * 50)
            
            folder_path = ask("請輸入要預覽的文件夾路徑")
            
            # 詢問是否顯示所有文件
            show_all_choice = ask_choice("顯示所有文件?", ["Y", "N"], default="N")
            show_all = (show_all_choice == "Y")
            
            # 詢問是否過濾副檔名
            filter_ext = None
            filter_choice = ask_choice("是否過濾特定副檔名?", ["Y", "N"], default="N")
            if filter_choice == "Y":
                filter_ext = ask("請輸入副檔名 (如 .txt, .jpg, .png)", default=".txt")
                if not filter_ext.startswith("."):
                    filter_ext = "." + filter_ext
            
            preview_folder(folder_path, show_all=show_all, filter_ext=filter_ext)
        
        elif choice == "3":
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
                        file_count = len([f for f in os.listdir(folder_path) 
                                        if os.path.isfile(os.path.join(folder_path, f))])
                        print(f"{i:2d}. {folder} ({file_count} 個文件)")
                    except:
                        print(f"{i:2d}. {folder} (無法訪問)")
            else:
                print("沒有找到文件夾")
        
        elif choice == "4":
            # 批量處理多個文件夾
            print("\n" + "=" * 50)
            print("批量處理多個文件夾")
            print("=" * 50)
            
            base_dir = ask("請輸入包含多個文件夾的根目錄路徑", default=os.getcwd())
            
            if not os.path.exists(base_dir):
                print(f"錯誤: 目錄 '{base_dir}' 不存在！")
                continue
            
            # 列出所有子文件夾
            subfolders = []
            for root, dirs, files in os.walk(base_dir):
                for dir_name in dirs:
                    subfolders.append(os.path.join(root, dir_name))
            
            if not subfolders:
                print("未找到子文件夾！")
                continue
            
            print(f"\n找到 {len(subfolders)} 個子文件夾:")
            for i, folder in enumerate(subfolders[:10], 1):
                print(f"  {i}. {os.path.basename(folder)}")
            if len(subfolders) > 10:
                print(f"  ... 還有 {len(subfolders) - 10} 個文件夾")
            
            # 確認批量處理
            confirm = ask_choice(f"是否批量處理所有 {len(subfolders)} 個文件夾?", ["Y", "N"], default="N")
            if confirm != "Y":
                continue
            
            # 批量處理設置
            print("\n批量處理設置:")
            mode = ask_choice("處理模式 (M=移動, C=複製)", ["M", "C"], default="M")
            move_files = (mode == "M")
            
            odd_name = ask("奇數文件夾名稱", default="odd_files")
            even_name = ask("偶數文件夾名稱", default="even_files")
            
            filter_ext = None
            filter_choice = ask_choice("是否過濾特定副檔名?", ["Y", "N"], default="N")
            if filter_choice == "Y":
                filter_ext = ask("請輸入副檔名", default=".txt")
                if not filter_ext.startswith("."):
                    filter_ext = "." + filter_ext
            
            # 執行批量處理
            print(f"\n開始批量處理 {len(subfolders)} 個文件夾...")
            processed_count = 0
            failed_count = 0
            
            for folder in subfolders:
                print(f"\n處理: {folder}")
                success = separate_odd_even_files(
                    folder,
                    odd_folder=odd_name,
                    even_folder=even_name,
                    move_files=move_files,
                    filter_ext=filter_ext
                )
                
                if success:
                    processed_count += 1
                else:
                    failed_count += 1
            
            print("\n" + "=" * 50)
            print("批量處理完成！")
            print(f"成功處理: {processed_count} 個文件夾")
            print(f"處理失敗: {failed_count} 個文件夾")
            print("=" * 50)
        
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
