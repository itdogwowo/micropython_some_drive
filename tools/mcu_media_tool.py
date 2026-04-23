#!/usr/bin/env python3
"""Interactive MCU media conversion tool."""

from __future__ import annotations

import importlib
import os
import re
import shutil
import struct
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Sequence


SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
SUPPORTED_VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".m4v", ".webm"}
DEFAULT_WIDTH = 160
DEFAULT_HEIGHT = 160
DEFAULT_JPEG_QUALITY = 85


def natural_key(value: str) -> List[object]:
    return [int(token) if token.isdigit() else token.lower() for token in re.split(r"(\d+)", value)]


def import_optional(module_name: str):
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


def resize_crop_cv2(frame, width: int, height: int, cv2_module):
    src_h, src_w = frame.shape[:2]
    scale = max(width / src_w, height / src_h)
    resized = cv2_module.resize(
        frame,
        (max(1, int(src_w * scale)), max(1, int(src_h * scale))),
        interpolation=cv2_module.INTER_AREA,
    )
    x0 = max(0, (resized.shape[1] - width) // 2)
    y0 = max(0, (resized.shape[0] - height) // 2)
    return resized[y0 : y0 + height, x0 : x0 + width]


def resize_crop_pil(image, width: int, height: int, pil_image_module):
    resampling = getattr(pil_image_module, "Resampling", None)
    lanczos = resampling.LANCZOS if resampling else pil_image_module.LANCZOS
    src_w, src_h = image.size
    scale = max(width / src_w, height / src_h)
    resized = image.resize((max(1, int(src_w * scale)), max(1, int(src_h * scale))), lanczos)
    x0 = max(0, (resized.width - width) // 2)
    y0 = max(0, (resized.height - height) // 2)
    return resized.crop((x0, y0, x0 + width, y0 + height))


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def list_image_files(folder: Path) -> List[Path]:
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_IMAGE_EXTS]
    return sorted(files, key=lambda item: natural_key(item.name))


def list_jpegs(folder: Path) -> List[Path]:
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg"}]
    return sorted(files, key=lambda item: natural_key(item.name))


def build_jpk(jpeg_dir: Path, jpk_path: Path) -> tuple[int, int]:
    jpeg_files = list_jpegs(jpeg_dir)
    if not jpeg_files:
        raise RuntimeError(f"找不到可封包的 JPEG: {jpeg_dir}")

    max_size = max(item.stat().st_size for item in jpeg_files)

    with jpk_path.open("wb") as output:
        output.write(b"JPK1")
        output.write(struct.pack("<III", len(jpeg_files), max_size, 0))
        for file_path in jpeg_files:
            file_size = file_path.stat().st_size
            output.write(struct.pack("<I", file_size))
            with file_path.open("rb") as source:
                while True:
                    chunk = source.read(4096)
                    if not chunk:
                        break
                    output.write(chunk)

    return len(jpeg_files), max_size


def frame_digits() -> int:
    return 3


class MCUMediaTool:
    def __init__(self) -> None:
        self.running = True
        self.dependencies = self._check_dependencies()

    def _check_dependencies(self) -> dict[str, bool]:
        checks = {
            "Pillow": import_optional("PIL") is not None,
            "opencv-python": import_optional("cv2") is not None,
            "numpy": import_optional("numpy") is not None,
        }
        return checks

    def print_dependency_report(self) -> None:
        print("=" * 68)
        print("MCU 媒體整理工具")
        print("=" * 68)
        print("步驟 1: 檢查執行環境")

        missing = []
        for package_name, ok in self.dependencies.items():
            status = "OK" if ok else "MISSING"
            print(f"  - {package_name:<14} {status}")
            if not ok:
                missing.append(package_name)

        if not missing:
            print("\n所有必要套件都已安裝，可直接開始。")
            return

        print("\n偵測到缺少套件，請依需求安裝:")
        if "Pillow" in missing:
            print("  - 照片轉換需要: python3 -m pip install Pillow")
        if "opencv-python" in missing or "numpy" in missing:
            print("  - 影片轉換需要: python3 -m pip install opencv-python numpy")
        print("安裝完成後重新執行本工具即可。\n")

    def _print_menu(self) -> None:
        print("\n可執行動作:")
        print("  1. 影片轉換 -> output/*.jpeg + output.jpk")
        print("  2. 照片轉換 -> output/*.jpeg + output.jpk")
        print("  q. 離開")

    def main_loop(self) -> None:
        self.print_dependency_report()
        self._print_menu()

        while self.running:
            choice = self.prompt("\n請選擇操作", default="1").lower()
            if not choice:
                continue

            if choice == "1":
                self.handle_video_conversion()
                self._print_menu()
            elif choice == "2":
                self.handle_photo_conversion()
                self._print_menu()
            elif choice == "q":
                self.running = False
            else:
                print("無效選項，請重新輸入。")

        print("已結束。")

    def prompt(self, message: str, default: str | None = None) -> str:
        suffix = f" [{default}]" if default is not None else ""
        try:
            raw = input(f"{message}{suffix}: ").strip()
        except EOFError:
            return ""
        value = raw or (default if default is not None else "")
        return self.clean_path_input(value)

    def prompt_int(self, message: str, default: int) -> int:
        while True:
            value = self.prompt(message, default=str(default))
            try:
                number = int(value)
            except ValueError:
                print("請輸入整數。")
                continue
            if number <= 0:
                print("請輸入大於 0 的值。")
                continue
            return number

    def prompt_choice(self, message: str, choices: Sequence[str], default: str) -> str:
        allowed = {item.lower() for item in choices}
        while True:
            value = self.prompt(f"{message} ({'/'.join(choices)})", default=default).lower()
            if value in allowed:
                return value
            print("無效選項，請重新輸入。")

    def clean_path_input(self, value: str) -> str:
        cleaned = value.strip()
        if cleaned.startswith('"') and cleaned.endswith('"'):
            cleaned = cleaned[1:-1]
        if cleaned.startswith("'") and cleaned.endswith("'"):
            cleaned = cleaned[1:-1]
        return os.path.expanduser(cleaned)

    def list_browser_entries(self, current_dir: Path, expected: str) -> List[Path]:
        entries: List[Path] = []
        try:
            all_items = sorted(current_dir.iterdir(), key=lambda item: (not item.is_dir(), natural_key(item.name)))
        except OSError as exc:
            print(f"無法讀取目錄: {exc}")
            return entries

        for item in all_items:
            if item.is_dir():
                entries.append(item)
                continue
            suffix = item.suffix.lower()
            if expected == "video" and suffix in SUPPORTED_VIDEO_EXTS:
                entries.append(item)
            elif expected == "photo" and suffix in SUPPORTED_IMAGE_EXTS:
                entries.append(item)
        return entries

    def print_browser(self, current_dir: Path, expected: str, entries: Sequence[Path]) -> None:
        mode_text = "影片檔" if expected == "video" else "圖片檔或圖片資料夾"
        print(f"\n目前位置: {current_dir}")
        print(f"請選擇 {mode_text}，也可以直接貼完整路徑。")
        print("  ..  回上一層")
        if expected == "photo":
            print("  .   使用目前資料夾")
        print("  q   取消")
        print("  r   重新整理")

        if not entries:
            print("  這一層沒有可用的媒體檔，請進入資料夾或直接輸入路徑。")
            return

        for index, item in enumerate(entries, start=1):
            label = "[DIR]" if item.is_dir() else "[FILE]"
            print(f"  {index:2d}. {label} {item.name}")

    def validate_target(self, target: Path, expected: str) -> Path | None:
        if not target.exists():
            print(f"路徑不存在: {target}")
            return None
        if expected == "video" and not target.is_file():
            print("影片模式只接受單一影片檔。")
            return None
        if expected == "video" and target.suffix.lower() not in SUPPORTED_VIDEO_EXTS:
            print("這不是支援的影片格式。")
            return None
        if expected == "photo" and target.is_file() and target.suffix.lower() not in SUPPORTED_IMAGE_EXTS:
            print("這不是支援的圖片格式。")
            return None
        if expected == "photo" and target.is_dir() and not list_image_files(target):
            print("資料夾內沒有可處理的圖片。")
            return None
        return target

    def require_for_action(self, action: str) -> bool:
        if action == "video":
            needed = ["opencv-python", "numpy"]
        else:
            needed = ["Pillow"]

        missing = [name for name in needed if not self.dependencies.get(name, False)]
        if not missing:
            return True

        print("\n目前無法執行，缺少必要套件:")
        for item in missing:
            print(f"  - {item}")
        if action == "video":
            print("請先安裝: python3 -m pip install opencv-python numpy")
        else:
            print("請先安裝: python3 -m pip install Pillow")
        return False

    def ask_target_path(self, expected: str) -> Path | None:
        current_dir = Path.cwd().resolve()
        while True:
            entries = self.list_browser_entries(current_dir, expected)
            self.print_browser(current_dir, expected, entries)

            raw = self.prompt("請輸入編號或路徑")
            if not raw:
                print("已取消。")
                return None
            if raw.lower() == "q":
                print("已取消。")
                return None
            if raw.lower() == "r":
                continue
            if raw == "..":
                parent = current_dir.parent
                if parent != current_dir:
                    current_dir = parent
                continue
            if raw == "." and expected == "photo":
                target = self.validate_target(current_dir, expected)
                if target is not None:
                    return target
                continue
            if raw.isdigit():
                index = int(raw) - 1
                if not (0 <= index < len(entries)):
                    print("編號超出範圍。")
                    continue
                chosen = entries[index]
                if chosen.is_dir():
                    current_dir = chosen.resolve()
                    continue
                target = self.validate_target(chosen.resolve(), expected)
                if target is not None:
                    return target
                continue

            target = self.validate_target(Path(raw).expanduser().resolve(), expected)
            if target is not None:
                return target

    def choose_output_paths(self, base_dir: Path) -> tuple[Path, Path] | None:
        output_dir = base_dir / "output"
        jpk_path = base_dir / "output.jpk"

        if output_dir.exists() or jpk_path.exists():
            print("\n偵測到現有輸出:")
            print(f"  - JPEG 目錄: {output_dir}")
            print(f"  - JPK 檔案: {jpk_path}")
            print("  1. 清空後重新產生")
            print("  2. 建立新的時間戳輸出")
            print("  3. 取消")

            action = self.prompt_choice("請選擇", ["1", "2", "3"], default="2")
            if action == "1":
                if output_dir.exists():
                    shutil.rmtree(output_dir)
                if jpk_path.exists():
                    jpk_path.unlink()
            elif action == "2":
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_dir = base_dir / f"output_{stamp}"
                jpk_path = base_dir / f"output_{stamp}.jpk"
            else:
                print("已取消本次轉換。")
                return None

        ensure_dir(output_dir)
        return output_dir, jpk_path

    def ask_output_size(self, default_width: int, default_height: int) -> tuple[int, int]:
        print(f"建議輸出尺寸: {DEFAULT_WIDTH}x{DEFAULT_HEIGHT}")
        width = self.prompt_int("輸出寬度", default=default_width)
        height = self.prompt_int("輸出高度", default=default_height)
        return width, height

    def ask_jpeg_quality(self) -> int:
        while True:
            quality = self.prompt_int("JPEG 品質", default=DEFAULT_JPEG_QUALITY)
            if 1 <= quality <= 100:
                return quality
            print("JPEG 品質必須介於 1 到 100。")

    def handle_video_conversion(self) -> None:
        if not self.require_for_action("video"):
            return

        target = self.ask_target_path("video")
        if target is None:
            return

        cv2_module = import_optional("cv2")
        if cv2_module is None:
            print("無法載入 opencv-python。")
            return

        capture = cv2_module.VideoCapture(str(target))
        if not capture.isOpened():
            print(f"無法開啟影片: {target}")
            return

        src_width = int(capture.get(cv2_module.CAP_PROP_FRAME_WIDTH)) or DEFAULT_WIDTH
        src_height = int(capture.get(cv2_module.CAP_PROP_FRAME_HEIGHT)) or DEFAULT_HEIGHT
        total_frames = int(capture.get(cv2_module.CAP_PROP_FRAME_COUNT)) or 0
        fps = float(capture.get(cv2_module.CAP_PROP_FPS)) or 0.0

        print(f"\n來源影片: {target.name}")
        print(f"原始尺寸: {src_width}x{src_height}")
        print(f"總幀數: {total_frames}")
        print(f"FPS: {fps:.2f}")

        width, height = self.ask_output_size(DEFAULT_WIDTH, DEFAULT_HEIGHT)
        quality = self.ask_jpeg_quality()

        base_dir = target.parent
        paths = self.choose_output_paths(base_dir)
        if paths is None:
            capture.release()
            return
        output_dir, jpk_path = paths

        print(f"\n開始輸出 JPEG 到: {output_dir}")
        digits = frame_digits()
        exported = 0

        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break

                processed = resize_crop_cv2(frame, width, height, cv2_module)
                out_path = output_dir / f"{exported:0{digits}d}.jpeg"
                ok = cv2_module.imwrite(str(out_path), processed, [cv2_module.IMWRITE_JPEG_QUALITY, quality])
                if not ok:
                    raise RuntimeError(f"無法寫入檔案: {out_path}")
                exported += 1

                if exported == 1 or exported % 25 == 0:
                    print(f"  已輸出 {exported} 幀...")
        finally:
            capture.release()

        if exported == 0:
            print("沒有匯出任何幀，已停止。")
            return

        packed_count, max_size = build_jpk(output_dir, jpk_path)
        print("\n完成。")
        print(f"  - JPEG 張數: {exported}")
        print(f"  - JPEG 目錄: {output_dir}")
        print(f"  - JPK 檔案: {jpk_path}")
        print(f"  - JPK 幀數: {packed_count}")
        print(f"  - 最大 JPEG bytes: {max_size}")

    def handle_photo_conversion(self) -> None:
        if not self.require_for_action("photo"):
            return

        target = self.ask_target_path("photo")
        if target is None:
            return

        pil_image_module = import_optional("PIL.Image")
        if pil_image_module is None:
            print("無法載入 Pillow。")
            return

        source_files = [target] if target.is_file() else list_image_files(target)
        if not source_files:
            print("沒有找到可處理的圖片。")
            return

        try:
            with pil_image_module.open(source_files[0]) as preview:
                default_width, default_height = preview.size
        except Exception:
            default_width, default_height = DEFAULT_WIDTH, DEFAULT_HEIGHT

        print(f"\n找到 {len(source_files)} 張圖片。")
        print(f"第一張尺寸: {default_width}x{default_height}")

        width, height = self.ask_output_size(default_width, default_height)
        quality = self.ask_jpeg_quality()

        base_dir = target if target.is_dir() else target.parent
        paths = self.choose_output_paths(base_dir)
        if paths is None:
            return
        output_dir, jpk_path = paths

        digits = frame_digits()
        exported = 0

        for file_path in source_files:
            try:
                with pil_image_module.open(file_path) as image:
                    rgb = image.convert("RGB")
                    processed = resize_crop_pil(rgb, width, height, pil_image_module)
                    out_path = output_dir / f"{exported:0{digits}d}.jpeg"
                    processed.save(out_path, format="JPEG", quality=quality, optimize=False)
                    exported += 1
            except Exception as exc:
                print(f"  跳過 {file_path.name}: {exc}")
                continue

            if exported == 1 or exported % 25 == 0:
                print(f"  已輸出 {exported} 張...")

        if exported == 0:
            print("沒有成功輸出任何圖片。")
            return

        packed_count, max_size = build_jpk(output_dir, jpk_path)
        print("\n完成。")
        print(f"  - JPEG 張數: {exported}")
        print(f"  - JPEG 目錄: {output_dir}")
        print(f"  - JPK 檔案: {jpk_path}")
        print(f"  - JPK 幀數: {packed_count}")
        print(f"  - 最大 JPEG bytes: {max_size}")


def main() -> int:
    tool = MCUMediaTool()
    tool.main_loop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
