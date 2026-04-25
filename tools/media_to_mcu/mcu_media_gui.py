#!/usr/bin/env python3
from __future__ import annotations

import cgi
import importlib
import json
import os
import re
import struct
import sys
import threading
import time
import uuid
import zipfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
STATIC_DIR = SCRIPT_DIR / "mcu_media_web"

SUPPORTED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
SUPPORTED_VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".m4v", ".webm"}


def natural_key(value: str) -> list[object]:
    return [int(token) if token.isdigit() else token.lower() for token in re.split(r"(\d+)", value)]


def import_optional(module_name: str):
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


def frame_digits(total: int | None = None) -> int:
    if not total or total <= 0:
        return 3
    return max(3, len(str(total - 1)))


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


def build_jpk(jpeg_dir: Path, jpk_path: Path) -> tuple[int, int]:
    jpeg_files = [p for p in jpeg_dir.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg"}]
    jpeg_files = sorted(jpeg_files, key=lambda item: natural_key(item.name))
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


def check_dependencies() -> None:
    missing: list[str] = []
    if import_optional("PIL.Image") is None:
        missing.append("Pillow")
    if import_optional("cv2") is None:
        missing.append("opencv-python")
    if not missing:
        print("依賴檢查：OK（可用 Python 後端轉換；也可純前端 JS）")
        return
    print("依賴檢查：目前是純前端 JS 流程，不需要安裝 Pillow / opencv-python")
    print("如果要啟用 Python 後端轉換（/api/convert），才需要安裝：" + "、".join(missing))
    print("建議安裝：python3 -m pip install " + " ".join(missing))


INDEX_HTML = """<!doctype html>
<html lang="zh-Hant">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>MCU Media GUI</title>
    <style>
      body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,"Noto Sans";margin:24px;background:#0b0f14;color:#e6edf3}
      .row{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap}
      .card{background:#111826;border:1px solid #1f2a3a;border-radius:10px;padding:16px;min-width:320px;flex:1}
      h1{font-size:18px;margin:0 0 12px 0}
      label{display:block;font-size:12px;color:#9fb0c0;margin:10px 0 6px}
      input,select,button{font-size:14px}
      input,select{width:100%;padding:10px;border-radius:8px;border:1px solid #223146;background:#0b1220;color:#e6edf3}
      button{padding:10px 12px;border-radius:8px;border:1px solid #2a3b52;background:#1a2a44;color:#e6edf3;cursor:pointer}
      button:disabled{opacity:.5;cursor:not-allowed}
      .drop{border:2px dashed #2a3b52;border-radius:10px;padding:16px;text-align:center;color:#9fb0c0}
      .drop.drag{border-color:#6aa6ff;color:#cfe2ff}
      .muted{color:#9fb0c0;font-size:12px;line-height:1.4}
      .kv{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:12px;white-space:pre-wrap}
      .bar{height:10px;background:#0b1220;border:1px solid #223146;border-radius:999px;overflow:hidden}
      .bar > div{height:100%;background:#6aa6ff;width:0%}
      a{color:#9ad0ff}
    </style>
  </head>
  <body>
    <h1>MCU Media GUI</h1>
    <div class="row">
      <div class="card">
        <div id="drop" class="drop">
          拖入影片檔或圖片（可多選）。<br />
          圖片資料夾請用「選擇資料夾」。
        </div>
        <div style="height:10px"></div>
        <div class="row" style="gap:10px">
          <button id="pickFiles">選擇檔案</button>
          <button id="pickFolder">選擇資料夾</button>
          <input id="fileInput" type="file" multiple style="display:none" />
          <input id="folderInput" type="file" webkitdirectory multiple style="display:none" />
        </div>
        <div style="height:10px"></div>
        <div class="muted">已選擇：<span id="pickedCount">0</span></div>
        <div style="height:10px"></div>
        <div class="bar"><div id="barFill"></div></div>
        <div style="height:10px"></div>
        <button id="run" disabled>開始轉換</button>
        <div style="height:12px"></div>
        <div id="result" class="kv"></div>
      </div>

      <div class="card">
        <div class="muted">參數</div>
        <label>裁切/縮放模式</label>
        <select id="cropMode">
          <option value="cover">中心裁切 (Cover)</option>
          <option value="contain">等比例縮放 + 補邊 (Contain)</option>
        </select>

        <label>輸出寬度</label>
        <input id="width" type="number" value="160" min="1" />
        <label>輸出高度</label>
        <input id="height" type="number" value="160" min="1" />

        <label>旋轉</label>
        <select id="rotate">
          <option value="0">0°</option>
          <option value="90">90°</option>
          <option value="180">180°</option>
          <option value="270">270°</option>
        </select>

        <label>對比度 (1.0 = 不變)</label>
        <input id="contrast" type="number" value="1.0" step="0.05" min="0.1" />

        <label>JPEG 品質</label>
        <input id="quality" type="number" value="85" min="1" max="100" />

        <label>並行工作數</label>
        <input id="workers" type="number" value="8" min="1" />
        <label>每批排程幀數/張數</label>
        <input id="maxPending" type="number" value="32" min="1" />

        <label>可用 RAM (MB)</label>
        <input id="ramMb" type="number" value="1024" min="0" />

        <div style="height:10px"></div>
        <div class="muted">輸出：提供 output.jpk 與 output.zip 下載（zip 內含 JPEG + JPK）。</div>
      </div>
    </div>
    <script src="/app.js"></script>
  </body>
</html>
"""


APP_JS = """const $ = (id) => document.getElementById(id);

let files = [];

function setPicked(newFiles) {
  files = newFiles;
  $("pickedCount").textContent = String(files.length);
  $("run").disabled = files.length === 0;
}

function addFiles(list) {
  const next = files.concat(Array.from(list));
  setPicked(next);
}

function resetProgress() {
  $("barFill").style.width = "0%";
  $("result").textContent = "";
}

function setProgress(p) {
  const pct = Math.max(0, Math.min(100, p));
  $("barFill").style.width = pct + "%";
}

function params() {
  return {
    crop_mode: $("cropMode").value,
    width: $("width").value,
    height: $("height").value,
    rotate: $("rotate").value,
    contrast: $("contrast").value,
    quality: $("quality").value,
    workers: $("workers").value,
    max_pending: $("maxPending").value,
    ram_mb: $("ramMb").value,
  };
}

async function run() {
  resetProgress();
  setProgress(5);
  $("run").disabled = true;

  const form = new FormData();
  const p = params();
  Object.keys(p).forEach((k) => form.append(k, p[k]));
  files.forEach((f) => form.append("files", f, f.webkitRelativePath || f.name));

  try {
    const res = await fetch("/api/convert", { method: "POST", body: form });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || ("HTTP " + res.status));
    }
    setProgress(90);
    const data = await res.json();
    const lines = [];
    lines.push("Mode: " + data.mode);
    lines.push("Count: " + data.count);
    lines.push("Max JPEG bytes: " + data.max_jpeg_bytes);
    lines.push("");
    lines.push("Download:");
    lines.push("  - " + data.jpk_url);
    lines.push("  - " + data.zip_url);
    $("result").textContent = lines.join("\\n");
    setProgress(100);
  } catch (e) {
    $("result").textContent = String(e && e.message ? e.message : e);
    setProgress(0);
  } finally {
    $("run").disabled = files.length === 0;
  }
}

$("run").addEventListener("click", run);

$("pickFiles").addEventListener("click", () => $("fileInput").click());
$("pickFolder").addEventListener("click", () => $("folderInput").click());

$("fileInput").addEventListener("change", (e) => setPicked(Array.from(e.target.files || [])));
$("folderInput").addEventListener("change", (e) => setPicked(Array.from(e.target.files || [])));

const drop = $("drop");
drop.addEventListener("dragover", (e) => {
  e.preventDefault();
  drop.classList.add("drag");
});
drop.addEventListener("dragleave", () => drop.classList.remove("drag"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("drag");
  if (e.dataTransfer && e.dataTransfer.files) addFiles(e.dataTransfer.files);
});
"""


def _json(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _text(handler: BaseHTTPRequestHandler, status: int, payload: str, content_type: str = "text/plain") -> None:
    data = payload.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", f"{content_type}; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _send_file(handler: BaseHTTPRequestHandler, file_path: Path, download_name: str) -> None:
    if not file_path.exists():
        _text(handler, HTTPStatus.NOT_FOUND, "Not found")
        return
    data = file_path.read_bytes()
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "application/octet-stream")
    handler.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _rotation_angle(value: str) -> int:
    try:
        angle = int(value)
    except Exception:
        return 0
    if angle in (0, 90, 180, 270):
        return angle
    return 0


def _float(value: str, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _int(value: str, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _resize_fit_pil(image, width: int, height: int, pil_image_module):
    resampling = getattr(pil_image_module, "Resampling", None)
    lanczos = resampling.LANCZOS if resampling else pil_image_module.LANCZOS
    src_w, src_h = image.size
    scale = min(width / src_w, height / src_h)
    resized = image.resize((max(1, int(src_w * scale)), max(1, int(src_h * scale))), lanczos)
    canvas = pil_image_module.new("RGB", (width, height), (0, 0, 0))
    x0 = (width - resized.width) // 2
    y0 = (height - resized.height) // 2
    canvas.paste(resized, (x0, y0))
    return canvas


def _resize_fit_cv2(frame, width: int, height: int, cv2_module):
    src_h, src_w = frame.shape[:2]
    scale = min(width / src_w, height / src_h)
    resized = cv2_module.resize(
        frame,
        (max(1, int(src_w * scale)), max(1, int(src_h * scale))),
        interpolation=cv2_module.INTER_AREA,
    )
    canvas = cv2_module.copyMakeBorder(
        resized,
        top=max(0, (height - resized.shape[0]) // 2),
        bottom=max(0, height - resized.shape[0] - max(0, (height - resized.shape[0]) // 2)),
        left=max(0, (width - resized.shape[1]) // 2),
        right=max(0, width - resized.shape[1] - max(0, (width - resized.shape[1]) // 2)),
        borderType=cv2_module.BORDER_CONSTANT,
        value=(0, 0, 0),
    )
    return canvas


def _apply_contrast_cv2(frame, contrast: float, cv2_module):
    if abs(contrast - 1.0) < 1e-6:
        return frame
    return cv2_module.convertScaleAbs(frame, alpha=float(contrast), beta=0)


def _apply_rotation_cv2(frame, angle: int, cv2_module):
    if angle == 90:
        return cv2_module.rotate(frame, cv2_module.ROTATE_90_CLOCKWISE)
    if angle == 180:
        return cv2_module.rotate(frame, cv2_module.ROTATE_180)
    if angle == 270:
        return cv2_module.rotate(frame, cv2_module.ROTATE_90_COUNTERCLOCKWISE)
    return frame


def _apply_rotation_pil(image, angle: int, pil_image_module):
    if angle == 90:
        return image.transpose(pil_image_module.ROTATE_90)
    if angle == 180:
        return image.transpose(pil_image_module.ROTATE_180)
    if angle == 270:
        return image.transpose(pil_image_module.ROTATE_270)
    return image


def _estimate_frame_bytes(frame) -> int:
    nbytes = getattr(frame, "nbytes", None)
    if isinstance(nbytes, int) and nbytes > 0:
        return nbytes
    try:
        return sys.getsizeof(frame)
    except Exception:
        return 0


def _detect_mode(files: list[Path]) -> str:
    if len(files) == 1 and files[0].suffix.lower() in SUPPORTED_VIDEO_EXTS:
        return "video"
    if any(item.suffix.lower() in SUPPORTED_IMAGE_EXTS for item in files):
        return "photo"
    return "unknown"


def _convert_photos(
    sources: list[Path],
    output_dir: Path,
    width: int,
    height: int,
    quality: int,
    rotate: int,
    contrast: float,
    crop_mode: str,
) -> tuple[int, int]:
    pil_image_module = import_optional("PIL.Image")
    if pil_image_module is None:
        raise RuntimeError("缺少 Pillow，無法處理圖片。")
    enhancer_module = import_optional("PIL.ImageEnhance")
    if enhancer_module is None:
        raise RuntimeError("缺少 Pillow ImageEnhance，無法調整對比度。")

    sources = sorted(sources, key=lambda p: natural_key(p.name))
    digits = frame_digits(len(sources))
    ok_count = 0

    for idx, file_path in enumerate(sources):
        try:
            with pil_image_module.open(file_path) as image:
                rgb = image.convert("RGB")
                rgb = _apply_rotation_pil(rgb, rotate, pil_image_module)
                if abs(contrast - 1.0) >= 1e-6:
                    rgb = enhancer_module.Contrast(rgb).enhance(float(contrast))
                if crop_mode == "contain":
                    processed = _resize_fit_pil(rgb, width, height, pil_image_module)
                else:
                    processed = resize_crop_pil(rgb, width, height, pil_image_module)
                out_path = output_dir / f"{ok_count:0{digits}d}.jpeg"
                processed.save(out_path, format="JPEG", quality=quality, optimize=False)
                ok_count += 1
        except Exception:
            continue

    if ok_count <= 0:
        raise RuntimeError("沒有成功輸出任何圖片。")

    _, max_size = build_jpk(output_dir, output_dir.parent / "output.jpk")
    return ok_count, max_size


def _convert_video(
    source: Path,
    output_dir: Path,
    width: int,
    height: int,
    quality: int,
    rotate: int,
    contrast: float,
    crop_mode: str,
    workers: int,
    max_pending: int,
    ram_budget_mb: int,
) -> tuple[int, int]:
    cv2_module = import_optional("cv2")
    if cv2_module is None:
        raise RuntimeError("缺少 opencv-python，無法處理影片。")

    capture = cv2_module.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError("無法開啟影片。")

    total_frames = int(capture.get(cv2_module.CAP_PROP_FRAME_COUNT)) or 0
    digits = frame_digits(total_frames) if total_frames > 0 else 6
    jpk_path = output_dir.parent / "output.jpk"
    ram_budget_bytes = max(0, int(ram_budget_mb)) * 1024 * 1024

    def encode_write(frame, frame_index: int) -> int:
        frame = _apply_rotation_cv2(frame, rotate, cv2_module)
        frame = _apply_contrast_cv2(frame, contrast, cv2_module)
        if crop_mode == "contain":
            processed = _resize_fit_cv2(frame, width, height, cv2_module)
        else:
            processed = resize_crop_cv2(frame, width, height, cv2_module)
        out_path = output_dir / f"{frame_index:0{digits}d}.jpeg"
        ok = cv2_module.imwrite(str(out_path), processed, [cv2_module.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            raise RuntimeError("寫檔失敗。")
        return frame_index

    exported = 0
    pending = set()

    from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED  # noqa: E402

    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as executor:
        batch_frames: list[object] = []
        batch_indices: list[int] = []
        batch_bytes = 0

        while True:
            ok, frame = capture.read()
            if not ok:
                break

            frame_bytes = _estimate_frame_bytes(frame)
            if ram_budget_bytes > 0 and batch_frames and batch_bytes + frame_bytes > ram_budget_bytes:
                for pos, idx in enumerate(batch_indices):
                    if len(pending) >= max_pending:
                        done, pending = wait(pending, return_when=FIRST_COMPLETED)
                        for fut in done:
                            fut.result()
                    pending.add(executor.submit(encode_write, batch_frames[pos], idx))
                batch_frames = []
                batch_indices = []
                batch_bytes = 0

            batch_frames.append(frame)
            batch_indices.append(exported)
            batch_bytes += frame_bytes
            exported += 1

        if batch_frames:
            for pos, idx in enumerate(batch_indices):
                if len(pending) >= max_pending:
                    done, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for fut in done:
                        fut.result()
                pending.add(executor.submit(encode_write, batch_frames[pos], idx))

        if pending:
            done, _ = wait(pending)
            for fut in done:
                fut.result()

    capture.release()

    if exported <= 0:
        raise RuntimeError("沒有匯出任何幀。")

    _, max_size = build_jpk(output_dir, jpk_path)
    return exported, max_size


class JobStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}

    def create(self) -> tuple[str, Path]:
        job_id = uuid.uuid4().hex
        job_dir = self.base_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._jobs[job_id] = {"dir": job_dir, "created": time.time()}
        return job_id, job_dir

    def get(self, job_id: str) -> Path | None:
        with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            return None
        return job["dir"]

    def cleanup(self, max_age_sec: int = 3600) -> None:
        now = time.time()
        to_delete: list[tuple[str, Path]] = []
        with self._lock:
            for job_id, job in list(self._jobs.items()):
                if now - job["created"] > max_age_sec:
                    to_delete.append((job_id, job["dir"]))
                    del self._jobs[job_id]
        for _, dir_path in to_delete:
            try:
                for item in dir_path.rglob("*"):
                    if item.is_file():
                        item.unlink()
                for item in sorted([p for p in dir_path.rglob("*") if p.is_dir()], reverse=True):
                    item.rmdir()
                dir_path.rmdir()
            except Exception:
                continue


JOBS = JobStore(SCRIPT_DIR / ".mcu_media_gui_jobs")


class Handler(BaseHTTPRequestHandler):
    server_version = "MCUMediaGUI/1.0"

    def log_message(self, format, *args):
        return

    def do_GET(self):
        if self.path == "/":
            rel = "index.html"
        else:
            rel = self.path.lstrip("/")

        if self.path.startswith("/download/"):
            parts = self.path.split("/")
            if len(parts) != 4:
                _text(self, HTTPStatus.NOT_FOUND, "Not found")
                return
            _, _, job_id, name = parts
            job_dir = JOBS.get(job_id)
            if job_dir is None:
                _text(self, HTTPStatus.NOT_FOUND, "Not found")
                return
            target = (job_dir / name).resolve()
            if target.parent != job_dir:
                _text(self, HTTPStatus.BAD_REQUEST, "Bad request")
                return
            _send_file(self, target, name)
            return

        if not rel or ".." in rel or rel.startswith("/"):
            _text(self, HTTPStatus.BAD_REQUEST, "Bad request")
            return

        target = (STATIC_DIR / rel).resolve()
        root = STATIC_DIR.resolve()
        if target.is_dir():
            _text(self, HTTPStatus.NOT_FOUND, "Not found")
            return
        if root != target and root not in target.parents:
            _text(self, HTTPStatus.BAD_REQUEST, "Bad request")
            return

        if target.exists():
            suffix = target.suffix.lower()
            if suffix in {".html", ".htm"}:
                _text(self, HTTPStatus.OK, target.read_text(encoding="utf-8"), content_type="text/html")
                return
            if suffix == ".js":
                _text(self, HTTPStatus.OK, target.read_text(encoding="utf-8"), content_type="application/javascript")
                return
            if suffix == ".css":
                _text(self, HTTPStatus.OK, target.read_text(encoding="utf-8"), content_type="text/css")
                return
            data = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if rel == "index.html":
            _text(self, HTTPStatus.OK, INDEX_HTML, content_type="text/html")
            return
        if rel == "app.js":
            _text(self, HTTPStatus.OK, APP_JS, content_type="application/javascript")
            return
        _text(self, HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self):
        if self.path != "/api/convert":
            _text(self, HTTPStatus.NOT_FOUND, "Not found")
            return

        JOBS.cleanup()

        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in ctype:
            _text(self, HTTPStatus.BAD_REQUEST, "Expected multipart/form-data")
            return

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": ctype},
        )

        width = max(1, _int(form.getfirst("width", "160"), 160))
        height = max(1, _int(form.getfirst("height", "160"), 160))
        quality = min(100, max(1, _int(form.getfirst("quality", "85"), 85)))
        rotate = _rotation_angle(form.getfirst("rotate", "0"))
        contrast = max(0.1, _float(form.getfirst("contrast", "1.0"), 1.0))
        crop_mode = form.getfirst("crop_mode", "cover")
        workers = max(1, _int(form.getfirst("workers", "8"), 8))
        max_pending = max(1, _int(form.getfirst("max_pending", "32"), 32))
        ram_mb = max(0, _int(form.getfirst("ram_mb", "1024"), 1024))

        upload_items = form["files"] if "files" in form else []
        if not isinstance(upload_items, list):
            upload_items = [upload_items]

        if not upload_items:
            _text(self, HTTPStatus.BAD_REQUEST, "No files")
            return

        job_id, job_dir = JOBS.create()
        input_dir = job_dir / "input"
        output_dir = job_dir / "output"
        input_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        saved: list[Path] = []
        for item in upload_items:
            if not getattr(item, "file", None):
                continue
            raw_name = getattr(item, "filename", "") or "file"
            safe_name = os.path.basename(raw_name)
            file_path = input_dir / safe_name
            with file_path.open("wb") as f:
                fileobj = item.file
                while True:
                    chunk = fileobj.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
            saved.append(file_path)

        if not saved:
            _text(self, HTTPStatus.BAD_REQUEST, "No valid files")
            return

        mode = _detect_mode(saved)
        if mode == "unknown":
            _text(self, HTTPStatus.BAD_REQUEST, "Unsupported input")
            return

        try:
            if mode == "photo":
                sources = [p for p in saved if p.suffix.lower() in SUPPORTED_IMAGE_EXTS]
                count, max_jpeg_bytes = _convert_photos(
                    sources=sources,
                    output_dir=output_dir,
                    width=width,
                    height=height,
                    quality=quality,
                    rotate=rotate,
                    contrast=contrast,
                    crop_mode=crop_mode,
                )
            else:
                source = saved[0]
                count, max_jpeg_bytes = _convert_video(
                    source=source,
                    output_dir=output_dir,
                    width=width,
                    height=height,
                    quality=quality,
                    rotate=rotate,
                    contrast=contrast,
                    crop_mode=crop_mode,
                    workers=workers,
                    max_pending=max_pending,
                    ram_budget_mb=ram_mb,
                )

            jpk_path = job_dir / "output.jpk"
            if not jpk_path.exists():
                src = output_dir.parent / "output.jpk"
                if src.exists():
                    src.replace(jpk_path)

            zip_path = job_dir / "output.zip"
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
                if jpk_path.exists():
                    zf.write(jpk_path, arcname="output.jpk")
                for item in sorted(output_dir.glob("*.jpeg"), key=lambda p: natural_key(p.name)):
                    zf.write(item, arcname=f"output/{item.name}")

            _json(
                self,
                HTTPStatus.OK,
                {
                    "job_id": job_id,
                    "mode": mode,
                    "count": count,
                    "max_jpeg_bytes": max_jpeg_bytes,
                    "jpk_url": f"/download/{job_id}/output.jpk",
                    "zip_url": f"/download/{job_id}/output.zip",
                },
            )
        except Exception as exc:
            _text(self, HTTPStatus.BAD_REQUEST, str(exc))


def main() -> int:
    check_dependencies()
    host = "127.0.0.1"
    port = int(os.environ.get("MCU_MEDIA_GUI_PORT", "8765"))
    try:
        httpd = ThreadingHTTPServer((host, port), Handler)
    except OSError:
        httpd = ThreadingHTTPServer((host, 0), Handler)
    actual_port = httpd.server_address[1]
    url = f"http://{host}:{actual_port}/"
    print(url)
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
