# pip install opencv-python tqdm



#!/usr/bin/env python3
# mp4_to_frames.py  ── 終端互動版：輸出 JPEG / GS8 / GS4
# pip install opencv-python tqdm
import os
import cv2
import numpy as np
from tqdm import tqdm

def ask(prompt, default=None, cast=str):
    tail = f" [{default}]" if default is not None else ""
    ans = input(prompt + tail + ": ").strip()
    return cast(ans) if ans else default

def ask_choice(prompt, choices, default=None):
    """
    choices: list of str
    回傳 choices 其中之一（大寫）
    """
    c_up = [c.upper() for c in choices]
    default = default.upper() if default else None
    while True:
        tail = f" ({'/'.join(c_up)})"
        if default:
            tail += f" [{default}]"
        ans = input(prompt + tail + ": ").strip().upper()
        if not ans and default:
            return default
        if ans in c_up:
            return ans
        print("無效選項，請重新輸入：", "/".join(c_up))

def resize_crop(frame, W, H):
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
        # 理論上 W*H 應為偶數；保險起見補 0
        flat = np.concatenate([flat, np.zeros(1, dtype=np.uint8)])
    hi = flat[0::2]
    lo = flat[1::2]
    packed = (hi << 4) | lo
    return packed.tobytes()

def main():
    mp4_path = ask("MP4 位置")
    if not mp4_path or not os.path.isfile(mp4_path):
        print("檔案不存在")
        return

    cap = cv2.VideoCapture(mp4_path)
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    src_dir = os.path.dirname(mp4_path) or "."
    mp4_name = os.path.splitext(os.path.basename(mp4_path))[0]

    mode = ask_choice("輸出格式", ["JPEG", "GS8", "GS4"], default="JPEG")

    out_dir_default = os.path.join(src_dir, f"{mp4_name}_{mode.lower()}")
    out_dir = ask("輸出位置", default=out_dir_default)
    width   = ask("輸出寬度", default=src_w, cast=int)
    height  = ask("輸出高度", default=src_h, cast=int)

    # JPEG 需要品質參數；GS8/GS4 不需要
    quality = None
    if mode == "JPEG":
        quality = ask("JPEG 品質", default=100, cast=int)

    os.makedirs(out_dir, exist_ok=True)

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # 副檔名
    ext = {"JPEG": "jpeg", "GS8": "g8", "GS4": "g4"}[mode]

    idx_out = 0
    for _ in tqdm(range(total), desc=f"Export {mode}"):
        ret, frame = cap.read()
        if not ret:
            break

        img = resize_crop(frame, width, height)
        out_path = os.path.join(out_dir, f"{idx_out:03d}.{ext}")

        if mode == "JPEG":
            cv2.imwrite(out_path, img, [cv2.IMWRITE_JPEG_QUALITY, quality])

        elif mode == "GS8":
            # 轉 8-bit 灰階，直接存 raw bytes (W*H bytes)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  # uint8
            gray.tofile(out_path)

        elif mode == "GS4":
            # 轉 8-bit 灰階 → 4-bit (0..15) → 打包存 raw bytes (W*H/2 bytes)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            packed = pack_gs4(gray)
            with open(out_path, "wb") as f:
                f.write(packed)

        idx_out += 1

    cap.release()

    print("完成！輸出", idx_out, "幀至", out_dir)
    if mode in ("GS8", "GS4"):
        # 給用戶一個明確提示：raw 檔沒有 header，需要記得 W/H
        bpp = "1 byte/px" if mode == "GS8" else "4 bit/px"
        print(f"注意：{mode} 為 RAW 灰階資料({bpp})，無圖片 header。播放端需使用相同寬高：{width}x{height}")

if __name__ == "__main__":
    main()