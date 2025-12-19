# pip install opencv-python tqdm



#!/usr/bin/env python3
# mp4_to_jpeg_all_frames.py  ── 終端互動版，全部幀，03d.jpeg
import os, cv2
from tqdm import tqdm

def ask(prompt, default=None, cast=str):
    tail = f" [{default}]" if default is not None else ""
    ans = input(prompt + tail + ": ").strip()
    return cast(ans) if ans else default

def resize_crop(frame, W, H):
    h, w = frame.shape[:2]
    scale = max(W / w, H / h)
    rs = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    x0 = (rs.shape[1] - W) // 2
    y0 = (rs.shape[0] - H) // 2
    return rs[y0:y0 + H, x0:x0 + W]

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

    out_dir = ask("輸出位置", default=os.path.join(src_dir, mp4_name))
    width   = ask("輸出寬度", default=src_w, cast=int)
    height  = ask("輸出高度", default=src_h, cast=int)
    quality = ask("JPEG 品質", default=100, cast=int)

    os.makedirs(out_dir, exist_ok=True)

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    idx_out = 0
    for idx in tqdm(range(total), desc="Extracting"):
        ret, frame = cap.read()
        if not ret:
            continue
        out_name = os.path.join(out_dir, f"{idx_out:03d}.jpeg")
        out_img  = resize_crop(frame, width, height)
        cv2.imwrite(out_name, out_img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        idx_out += 1
    cap.release()
    print("完成！輸出", idx_out, "張圖片至", out_dir)

if __name__ == "__main__":
    main()