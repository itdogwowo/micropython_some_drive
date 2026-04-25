#!/usr/bin/env python3
"""Interactive MCU media conversion tool."""

from __future__ import annotations

import importlib
import os
import re
import shutil
import struct
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path
from typing import List, Sequence


SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
SUPPORTED_VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".m4v", ".webm"}
DEFAULT_WIDTH = 160
DEFAULT_HEIGHT = 160
DEFAULT_JPEG_QUALITY = 85


class ConsoleUI:
    @staticmethod
    def hide_cursor() -> None:
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()

    @staticmethod
    def show_cursor() -> None:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

    @staticmethod
    def clear_screen() -> None:
        sys.stdout.write("\033[H\033[2J\033[3J")
        sys.stdout.flush()

    @staticmethod
    def draw_progress_bar(percent: float, width: int = 30) -> str:
        pct = max(0.0, min(100.0, float(percent)))
        filled = int(width * pct / 100.0)
        return "█" * filled + "░" * (width - filled)


class ProgressPanel:
    def __init__(self, title: str, total: int | None, workers: int, width: int = 84) -> None:
        self.title = title
        self.total = total if (total is not None and total > 0) else None
        self.workers = max(1, int(workers))
        self.width = max(60, int(width))
        self._lines = 0
        self._last_render = 0.0
        self._t0 = time.perf_counter()
        self._done = 0

    def _pad(self, text: str) -> str:
        inner = self.width - 2
        if len(text) > inner:
            text = text[:inner]
        return text.ljust(inner)

    def _format(self, done: int, scheduled: int, pending: int, running: int, queued: int) -> str:
        total = self.total
        elapsed = max(0.0, time.perf_counter() - self._t0)
        percent = 0.0
        if total:
            percent = (done / total) * 100.0
            line1 = f" Done: {done}/{total} ({percent:5.1f}%)  Elapsed: {elapsed:6.1f}s"
        else:
            line1 = f" Done: {done}  Elapsed: {elapsed:6.1f}s"
        line2 = f" Scheduled: {scheduled}  Pending: {pending}  Workers: {self.workers}"
        line3 = f" Total: {ConsoleUI.draw_progress_bar(percent, 60)} {percent:5.1f}%" if total else ""
        run_pct = (running / self.workers) * 100.0 if self.workers else 0.0
        line4 = f" Running: {ConsoleUI.draw_progress_bar(run_pct, 30)} {running}/{self.workers}"
        q_pct = 0.0 if pending <= 0 else min(100.0, (queued / max(1, pending)) * 100.0)
        line5 = f" Queue  : {ConsoleUI.draw_progress_bar(q_pct, 30)} {queued}"

        top = "╔" + "═" * (self.width - 2) + "╗"
        head = "║" + self._pad(f" {self.title}") + "║"
        mid = "╠" + "═" * (self.width - 2) + "╣"
        rows = [
            "║" + self._pad(line1) + "║",
            "║" + self._pad(line2) + "║",
            "║" + self._pad(line3) + "║" if line3 else None,
            "║" + self._pad(line4) + "║",
            "║" + self._pad(line5) + "║",
        ]
        rows = [row for row in rows if row is not None]
        bot = "╚" + "═" * (self.width - 2) + "╝"
        lines = [top, head, mid, *rows, bot]
        return "\n".join(lines) + "\n", len(lines)

    def complete_index(self, index: int) -> None:
        self._done += 1

    def update(self, scheduled: int, pending: int) -> None:
        if not sys.stdout.isatty():
            return
        now = time.perf_counter()
        if self._last_render and now - self._last_render < 0.12:
            return
        self._last_render = now

        running = min(max(0, pending), self.workers)
        queued = max(0, pending - self.workers)
        content, lines = self._format(self._done, scheduled, pending, running, queued)

        if self._lines:
            sys.stdout.write(f"\033[{self._lines}A")
        sys.stdout.write(content)
        sys.stdout.flush()
        self._lines = lines


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


def frame_digits(total: int | None = None) -> int:
    if not total or total <= 0:
        return 3
    return max(3, len(str(total - 1)))


def estimate_object_size(value) -> int:
    nbytes = getattr(value, "nbytes", None)
    if isinstance(nbytes, int) and nbytes > 0:
        return nbytes
    try:
        return sys.getsizeof(value)
    except Exception:
        return 0


def convert_photo_one(
    source_path: str,
    output_path: str,
    width: int,
    height: int,
    quality: int,
) -> tuple[bool, str]:
    pil_image_module = import_optional("PIL.Image")
    if pil_image_module is None:
        return False, "無法載入 Pillow。"

    try:
        with pil_image_module.open(source_path) as image:
            rgb = image.convert("RGB")
            processed = resize_crop_pil(rgb, width, height, pil_image_module)
            processed.save(output_path, format="JPEG", quality=quality, optimize=False)
        return True, ""
    except Exception as exc:
        return False, str(exc)


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

    def prompt_yes_no(self, message: str, default: str = "n") -> bool:
        value = self.prompt_choice(message, ["y", "n"], default=default)
        return value == "y"

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
        digits = frame_digits(total_frames)
        exported = 0
        use_parallel = self.prompt_yes_no("並行輸出 (加速 JPEG 編碼/寫檔)", default="y" if total_frames >= 50 else "n")
        workers = 1
        max_pending = 1
        if use_parallel:
            default_workers = min(os.cpu_count() or 4, 8)
            workers = self.prompt_int("並行工作數", default=default_workers)
            max_pending = self.prompt_int("每批排程幀數", default=max(workers * 4, workers))
            max_pending = max(max_pending, workers)

        try:
            if workers <= 1:
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
            else:
                def _write_one(out_path: Path, frame, frame_index: int) -> int:
                    processed = resize_crop_cv2(frame, width, height, cv2_module)
                    ok = cv2_module.imwrite(
                        str(out_path),
                        processed,
                        [cv2_module.IMWRITE_JPEG_QUALITY, quality],
                    )
                    if not ok:
                        raise RuntimeError(f"無法寫入檔案: {out_path}")
                    return int(frame_index)

                pending = set()
                completed = 0
                submitted = 0
                ram_budget_mb = self.prompt_int("可用 RAM (MB)", default=1024)
                ram_budget_bytes = max(0, int(ram_budget_mb)) * 1024 * 1024

                panel = ProgressPanel("Video Encode/Write (Parallel)", total_frames if total_frames > 0 else None, workers)
                if sys.stdout.isatty():
                    ConsoleUI.hide_cursor()
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    def submit_batch(batch: list[object], batch_indices: list[int]) -> None:
                        nonlocal pending, completed, submitted
                        iterator = iter(enumerate(batch_indices))
                        while len(pending) < max_pending:
                            try:
                                pos, index = next(iterator)
                            except StopIteration:
                                break
                            frame = batch[pos]
                            out_path = output_dir / f"{index:0{digits}d}.jpeg"
                            pending.add(executor.submit(_write_one, out_path, frame, index))
                            batch[pos] = None
                            submitted += 1
                            panel.update(scheduled=submitted, pending=len(pending))

                        while pending:
                            done, _ = wait(pending, return_when=FIRST_COMPLETED)
                            for item in done:
                                pending.remove(item)
                                frame_index = item.result()
                                panel.complete_index(frame_index)
                                completed += 1
                                panel.update(scheduled=submitted, pending=len(pending))

                                try:
                                    pos, index = next(iterator)
                                except StopIteration:
                                    continue
                                frame = batch[pos]
                                out_path = output_dir / f"{index:0{digits}d}.jpeg"
                                pending.add(executor.submit(_write_one, out_path, frame, index))
                                batch[pos] = None
                                submitted += 1
                                panel.update(scheduled=submitted, pending=len(pending))

                    batch: list[object] = []
                    batch_indices: list[int] = []
                    batch_bytes = 0
                    while True:
                        ok, frame = capture.read()
                        if not ok:
                            break

                        frame_bytes = estimate_object_size(frame)
                        if ram_budget_bytes > 0 and batch and batch_bytes + frame_bytes > ram_budget_bytes:
                            submit_batch(batch, batch_indices)
                            batch = []
                            batch_indices = []
                            batch_bytes = 0

                        batch.append(frame)
                        batch_indices.append(exported)
                        batch_bytes += frame_bytes
                        exported += 1

                    if batch:
                        submit_batch(batch, batch_indices)

                    if pending:
                        done, _ = wait(pending)
                        for item in done:
                            frame_index = item.result()
                            panel.complete_index(frame_index)
                            completed += 1
                        panel.update(scheduled=submitted, pending=0)
        finally:
            capture.release()
            if use_parallel and workers > 1 and sys.stdout.isatty():
                ConsoleUI.show_cursor()

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

        digits = frame_digits(len(source_files))
        exported = 0
        use_parallel = self.prompt_yes_no("並行轉換 (加速批次處理)", default="y" if len(source_files) >= 20 else "n")
        workers = 1
        max_pending = 1
        if use_parallel:
            default_workers = min(os.cpu_count() or 4, 8)
            workers = self.prompt_int("並行工作數", default=default_workers)
            max_pending = self.prompt_int("每批排程張數", default=max(workers * 4, workers))
            max_pending = max(max_pending, workers)

        if workers <= 1:
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
        else:
            temp_paths: list[Path] = []
            success: dict[int, Path] = {}

            with ProcessPoolExecutor(max_workers=workers) as executor:
                iterator = iter(enumerate(source_files))
                pending: dict[object, tuple[int, Path, Path]] = {}
                completed = 0
                submitted = 0
                panel = ProgressPanel("Photo Convert (Parallel)", len(source_files), workers)
                if sys.stdout.isatty():
                    ConsoleUI.hide_cursor()

                while len(pending) < max_pending:
                    try:
                        index, file_path = next(iterator)
                    except StopIteration:
                        break
                    temp_path = output_dir / f"tmp_{index:0{digits}d}.jpeg"
                    temp_paths.append(temp_path)
                    fut = executor.submit(
                        convert_photo_one,
                        str(file_path),
                        str(temp_path),
                        width,
                        height,
                        quality,
                    )
                    pending[fut] = (index, file_path, temp_path)
                    submitted += 1
                    panel.update(scheduled=submitted, pending=len(pending))

                while pending:
                    done, _ = wait(list(pending.keys()), return_when=FIRST_COMPLETED)
                    for fut in done:
                        index, file_path, temp_path = pending.pop(fut)
                        ok, err = fut.result()
                        if ok:
                            success[index] = temp_path
                        else:
                            print(f"  跳過 {file_path.name}: {err}")
                        completed += 1
                        panel.complete_index(index)
                        panel.update(scheduled=submitted, pending=len(pending))

                        try:
                            next_index, next_path = next(iterator)
                        except StopIteration:
                            continue
                        next_temp = output_dir / f"tmp_{next_index:0{digits}d}.jpeg"
                        temp_paths.append(next_temp)
                        next_fut = executor.submit(
                            convert_photo_one,
                            str(next_path),
                            str(next_temp),
                            width,
                            height,
                            quality,
                        )
                        pending[next_fut] = (next_index, next_path, next_temp)
                        submitted += 1
                        panel.update(scheduled=submitted, pending=len(pending))
            if sys.stdout.isatty():
                ConsoleUI.show_cursor()

            exported = 0
            for idx in sorted(success):
                src_path = success[idx]
                final_path = output_dir / f"{exported:0{digits}d}.jpeg"
                src_path.replace(final_path)
                exported += 1

            for path in temp_paths:
                if path.exists() and path.name.startswith("tmp_"):
                    path.unlink()

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
