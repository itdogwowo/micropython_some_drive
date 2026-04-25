# pip install opencv-python tqdm



#!/usr/bin/env python3
# jpg_to_jpeg_tty.py  ── 互動版：單檔/單層 *.jpg → 000.jpeg 開始，縮放+裁切+轉90°×N
import os, cv2, re
from tqdm import tqdm

def ask(prompt, default=None, cast=str):
    tail = f" [{default}]" if default is not None else ""
    ans = input(prompt + tail + ": ").strip()
    return cast(ans) if ans else default

def natural_key(name):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', name)]

def resize_crop(frame, W, H):
    h, w = frame.shape[:2]
    scale = max(W / w, H / h)
    rs = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    x0 = (rs.shape[1] - W) // 2
    y0 = (rs.shape[0] - H) // 2
    return rs[y0:y0 + H, x0:x0 + W]

def main():
    path = ask("請輸入 JPG 檔案或資料夾路徑")
    if not os.path.exists(path):
        print("路徑不存在")
        return

    # 建立檔案清單
    if os.path.isfile(path):
        jpg_list = [path]
    else:
        jpg_list = sorted(
            [os.path.join(path, f) for f in os.listdir(path) if f.lower().endswith('.jpg')],
            key=lambda x: natural_key(os.path.basename(x))
        )
    if not jpg_list:
        print("找不到任何 .jpg")
        return

    # 預設值來源
    sample = cv2.imread(jpg_list[0])
    if sample is None:
        print("無法讀取樣本圖片")
        return
    src_h, src_w = sample.shape[:2]
    src_dir = os.path.dirname(jpg_list[0]) if len(jpg_list) == 1 else path

    # 互動問答
    out_dir = ask("輸出位置", default=os.path.join(src_dir, "jpeg"))
    width   = ask("輸出寬度", default=src_w, cast=int)
    height  = ask("輸出高度", default=src_h, cast=int)
    quality = ask("JPEG 品質", default=100, cast=int)
    rotate  = ask("順時針轉 90° 幾次", default=0, cast=int)

    os.makedirs(out_dir, exist_ok=True)

    for idx, file in tqdm(enumerate(jpg_list), desc="Re-encoding"):
        img = cv2.imread(file)
        if img is None:
            continue
        img = resize_crop(img, width, height)
        if rotate:
            for _ in range(rotate):
                img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE )
        out_path = os.path.join(out_dir, f"{idx:03d}.jpeg")
        cv2.imwrite(out_path, img, [cv2.IMWRITE_JPEG_QUALITY, quality])

    print(f"完成！共 {len(jpg_list)} 張 → {out_dir}/000.jpeg …")

if __name__ == "__main__":
    main()