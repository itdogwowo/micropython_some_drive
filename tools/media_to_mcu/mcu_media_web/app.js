const $ = (id) => document.getElementById(id);

let files = [];
let srcUrl = null;
let rafId = 0;
let videoFrameCb = null;
let lastVideoW = 0;
let lastVideoH = 0;
let mode = "—";
let images = [];
let imageIndex = 0;
let imageObjUrl = null;
let jpegBlobs = [];
let jpkBlob = null;
let isConverting = false;
let isPlaying = false;
let slideshowTimer = 0;
let _thumbVideo = null;
let _thumbSeq = 0;
let _previewSeq = 0;
let _thumbLastFrame = -1;
let _thumbHideTimer = 0;
let _videoDetectedFps = 0;
let _lastPhotoInputFps = 30;
let _lastVideoInputFps = 30;
let _pickSeq = 0;
let _rangeReset = true;
let _convertVideoT = 0;
let _convertVideoFrame = 0;
let _photoWorkerUrl = null;
let _previewPending = null;
let _previewRaf = 0;
let _lastPreviewSyncT = -1;
let _lastPreviewSyncAt = 0;
let _afterPreviewSeq = 0;
let _convertPreviewPct = -1;
let _convertPreviewAt = 0;

const PHOTO_WORKER_CODE = `self.onmessage = async (e) => {
  const d = e.data || {};
  const id = d.id;
  try {
    if (typeof OffscreenCanvas === "undefined") throw new Error("OffscreenCanvas not supported");
    const hasCreateImageBitmap = typeof createImageBitmap === "function";
    const file = d.file;
    const w = Math.max(1, d.w | 0);
    const h = Math.max(1, d.h | 0);
    const rotate = (d.rotate | 0) || 0;
    const cropMode = d.cropMode === "contain" ? "contain" : "cover";
    const contrast = typeof d.contrast === "number" ? d.contrast : parseFloat(String(d.contrast || "1"));
    const quality = Math.min(100, Math.max(1, d.quality | 0));
    const maxBytes = Math.max(0, d.maxBytes | 0);
    let bmp = d.bitmap;
    if (!bmp) {
      if (!hasCreateImageBitmap) throw new Error("createImageBitmap not supported");
      if (!file) throw new Error("No input");
      bmp = await createImageBitmap(file);
    }
    const canvas = new OffscreenCanvas(w, h);
    const ctx = canvas.getContext("2d", { alpha: false });
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, w, h);
    ctx.save();
    if (rotate) {
      ctx.translate(w / 2, h / 2);
      ctx.rotate((rotate * Math.PI) / 180);
      ctx.translate(-w / 2, -h / 2);
    }
    ctx.filter = Math.abs(contrast - 1.0) < 1e-6 ? "none" : \`contrast(\${Math.max(0.1, contrast) * 100}%)\`;
    const sx = bmp.width;
    const sy = bmp.height;
    const scale = cropMode === "contain" ? Math.min(w / sx, h / sy) : Math.max(w / sx, h / sy);
    const dw = sx * scale;
    const dh = sy * scale;
    const dx = (w - dw) / 2;
    const dy = (h - dh) / 2;
    ctx.drawImage(bmp, dx, dy, dw, dh);
    ctx.restore();
    let blob;
    if (typeof canvas.convertToBlob === "function") {
      const encode = async (q) => await canvas.convertToBlob({ type: "image/jpeg", quality: q / 100 });
      if (maxBytes > 0) {
        let lo = 1;
        let hi = quality;
        let best = null;
        for (let i = 0; i < 7 && lo <= hi; i++) {
          const mid = Math.floor((lo + hi) / 2);
          const b = await encode(mid);
          if (b && b.size <= maxBytes) {
            best = b;
            lo = mid + 1;
          } else {
            hi = mid - 1;
          }
        }
        blob = best ? best : await encode(1);
      } else {
        blob = await encode(quality);
      }
    } else {
      throw new Error("convertToBlob not supported");
    }
    try { if (bmp && typeof bmp.close === "function") bmp.close(); } catch {}
    self.postMessage({ id, ok: true, blob });
  } catch (err) {
    self.postMessage({ id, ok: false, error: String(err && err.message ? err.message : err) });
  }
};`;

function getPhotoWorkerUrl() {
  if (_photoWorkerUrl) return _photoWorkerUrl;
  const blob = new Blob([PHOTO_WORKER_CODE], { type: "text/javascript" });
  _photoWorkerUrl = URL.createObjectURL(blob);
  return _photoWorkerUrl;
}

class PhotoWorkerPool {
  constructor(size) {
    this.size = Math.max(1, size | 0);
    this.queue = [];
    this.pending = new Map();
    this.workers = [];
    this.seq = 0;
    const url = getPhotoWorkerUrl();
    for (let i = 0; i < this.size; i++) {
      const w = new Worker(url);
      const state = { w, busy: false };
      w.onmessage = (e) => {
        const d = e.data || {};
        const rec = this.pending.get(d.id);
        if (rec) {
          this.pending.delete(d.id);
          if (d && d.ok) rec.resolve(d.blob);
          else rec.reject(new Error(d && d.error ? d.error : "worker error"));
        }
        state.busy = false;
        this.pump();
      };
      w.onerror = () => {
        state.busy = false;
        this.pump();
      };
      this.workers.push(state);
    }
  }

  pump() {
    for (const state of this.workers) {
      if (state.busy) continue;
      const job = this.queue.shift();
      if (!job) return;
      state.busy = true;
      if (job.transfer && job.transfer.length) state.w.postMessage(job.msg, job.transfer);
      else state.w.postMessage(job.msg);
    }
  }

  exec(msg) {
    const id = ++this.seq;
    const payload = { ...msg, id };
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.queue.push({ msg: payload });
      this.pump();
    });
  }

  execTransfer(msg, transfer) {
    const id = ++this.seq;
    const payload = { ...msg, id };
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.queue.push({ msg: payload, transfer: Array.isArray(transfer) ? transfer : [] });
      this.pump();
    });
  }

  terminate() {
    for (const state of this.workers) {
      try {
        state.w.terminate();
      } catch {
      }
    }
    this.workers = [];
    this.queue = [];
    this.pending.clear();
  }
}

function getSelectedFrameRange() {
  const sr = $("videoStartRange");
  const er = $("videoEndRange");
  const max = Number(sr?.max || 0) || 0;
  const a = Math.round(Number(sr?.value || 0) || 0);
  const b = Math.round(Number(er?.value || 0) || 0);
  const start = Math.max(0, Math.min(max, Math.min(a, b)));
  const end = Math.max(0, Math.min(max, Math.max(a, b)));
  return { start, end, max };
}

function resetSelectedRangeInputs() {
  const sr = $("videoStartRange");
  const er = $("videoEndRange");
  const sn = $("videoStartFrame");
  const en = $("videoEndFrame");
  if (sn) sn.value = "0";
  if (en) en.value = "0";
  if (sr) sr.value = "0";
  if (er) er.value = String(Number(er.max || 0) || 0);
}

function isZipFileName(name) {
  const lower = String(name || "").toLowerCase();
  const ext = lower.split(".").pop();
  return ext === "zip";
}

function isJpkFileName(name) {
  const lower = String(name || "").toLowerCase();
  const ext = lower.split(".").pop();
  return ext === "jpk";
}

function setProgress(p) {
  const pct = Math.max(0, Math.min(100, p));
  $("barFill").style.width = pct + "%";
}

function resetProgress() {
  setProgress(0);
  $("result").textContent = "";
  const ps = $("pickStatus");
  if (ps) ps.textContent = "";
  $("downloadJpk").disabled = true;
  $("downloadAll").disabled = true;
  jpegBlobs = [];
  jpkBlob = null;
}

function ensureThumbVideo() {
  if (_thumbVideo) return _thumbVideo;
  const v = document.createElement("video");
  v.muted = true;
  v.playsInline = true;
  v.preload = "auto";
  v.style.display = "none";
  document.body.appendChild(v);
  _thumbVideo = v;
  return v;
}

function getThumbUi() {
  return {
    tip: $("videoThumbTip"),
    canvas: $("videoThumbCanvas"),
    text: $("videoThumbText"),
    stack: $("videoRangeTrack") ? $("videoRangeTrack").parentElement : null,
  };
}

function showThumbTip() {
  const ui = getThumbUi();
  if (ui.tip) ui.tip.classList.add("show");
}

function hideThumbTipSoon() {
  if (_thumbHideTimer) clearTimeout(_thumbHideTimer);
  _thumbHideTimer = setTimeout(() => {
    const ui = getThumbUi();
    if (ui.tip) ui.tip.classList.remove("show");
  }, 120);
}

function hideThumbTipNow() {
  if (_thumbHideTimer) clearTimeout(_thumbHideTimer);
  _thumbHideTimer = 0;
  const ui = getThumbUi();
  if (ui.tip) ui.tip.classList.remove("show");
}

function positionThumbTip(frame) {
  const ui = getThumbUi();
  if (!ui.tip || !ui.stack) return;
  const max = Number($("videoStartRange")?.max || 0);
  const stackRect = ui.stack.getBoundingClientRect();
  const cs = getComputedStyle(ui.stack);
  const thumbR = parseFloat(cs.getPropertyValue("--thumb-r")) || 9;
  const usable = Math.max(1, stackRect.width - thumbR * 2);
  const pct = max > 0 ? Math.max(0, Math.min(1, frame / max)) : 0;
  const x = thumbR + pct * usable;
  const tipW = 168;
  let left = x - tipW / 2;
  left = Math.max(0, Math.min(stackRect.width - tipW, left));
  ui.tip.style.left = `${left}px`;
}

function drawVideoFrameToCanvas(videoEl, canvasEl) {
  const ctx = canvasEl.getContext("2d");
  const w = canvasEl.width;
  const h = canvasEl.height;
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, w, h);
  const vw = videoEl.videoWidth || 0;
  const vh = videoEl.videoHeight || 0;
  if (!vw || !vh) return;
  const scale = Math.min(w / vw, h / vh);
  const dw = vw * scale;
  const dh = vh * scale;
  const dx = (w - dw) / 2;
  const dy = (h - dh) / 2;
  ctx.drawImage(videoEl, dx, dy, dw, dh);
}

async function updateThumb(frame) {
  const ui = getThumbUi();
  if (!ui.tip || !ui.canvas || !ui.text) return;
  if (mode !== "video" && mode !== "photo") return;

  const fps = getInputFps();
  const max = Number($("videoStartRange")?.max || 0);
  const f = Math.max(0, Math.min(max, Math.round(frame)));
  const t = fps > 0 ? f / fps : 0;
  ui.text.textContent = mode === "video" ? `frame ${f}  (t=${t.toFixed(2)}s)` : `frame ${f}`;
  positionThumbTip(f);

  if (_thumbLastFrame === f) return;
  _thumbLastFrame = f;

  const seq = ++_thumbSeq;
  if (mode === "video") {
    const v = ensureThumbVideo();
    if (!v.src && srcUrl) {
      v.src = srcUrl;
      v.load();
    }
    if (!v.src) return;
    try {
      await ensureVideoReady(v);
      await seekVideo(v, t);
      if (seq !== _thumbSeq) return;
      drawVideoFrameToCanvas(v, ui.canvas);
    } catch {
    }
    return;
  }

  if (mode === "photo") {
    const img = images[f];
    if (!img) return;
    try {
      const bmp = await createImageBitmap(img);
      if (seq !== _thumbSeq) return;
      const ctx = ui.canvas.getContext("2d");
      const w = ui.canvas.width;
      const h = ui.canvas.height;
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, w, h);
      const scale = Math.min(w / bmp.width, h / bmp.height);
      const dw = bmp.width * scale;
      const dh = bmp.height * scale;
      const dx = (w - dw) / 2;
      const dy = (h - dh) / 2;
      ctx.drawImage(bmp, dx, dy, dw, dh);
      try {
        bmp.close();
      } catch {
      }
    } catch {
    }
  }
}

function isVideoFileName(name) {
  const lower = String(name || "").toLowerCase();
  const base = lower.split("/").pop();
  if (base === ".ds_store" || base.startsWith("._") || base.startsWith(".")) return false;
  const ext = lower.split(".").pop();
  return ["mp4", "mov", "mkv", "avi", "webm", "m4v"].includes(ext);
}

function isImageFileName(name) {
  const lower = String(name || "").toLowerCase();
  const base = lower.split("/").pop();
  if (base === ".ds_store" || base.startsWith("._") || base.startsWith(".")) return false;
  const ext = lower.split(".").pop();
  return ["png", "jpg", "jpeg", "bmp", "webp", "tif", "tiff"].includes(ext);
}

function naturalKey(value) {
  return String(value)
    .split(/(\d+)/)
    .map((token) => (/^\d+$/.test(token) ? parseInt(token, 10) : token.toLowerCase()));
}

function naturalCompare(a, b) {
  const ak = naturalKey(a);
  const bk = naturalKey(b);
  const n = Math.max(ak.length, bk.length);
  for (let i = 0; i < n; i++) {
    if (i >= ak.length) return -1;
    if (i >= bk.length) return 1;
    const av = ak[i];
    const bv = bk[i];
    if (av === bv) continue;
    if (typeof av === "number" && typeof bv === "number") return av - bv;
    return String(av).localeCompare(String(bv));
  }
  return 0;
}

function detectMode(list) {
  if (!list.length) return "—";
  if (list.length === 1 && isVideoFileName(list[0].name)) return "video";
  if (list.length === 1 && isZipFileName(list[0].name)) return "photo";
  if (list.length === 1 && isJpkFileName(list[0].name)) return "photo";
  if (list.some((f) => isImageFileName(f.name))) return "photo";
  return "unknown";
}

function dedupeFiles(list) {
  const map = new Map();
  for (const f of list) {
    const key = `${f.webkitRelativePath || f.name}::${f.size}::${f.lastModified}`;
    if (!map.has(key)) map.set(key, f);
  }
  return Array.from(map.values());
}

function u16le(bytes, o) {
  return bytes[o] | (bytes[o + 1] << 8);
}

function u32le(bytes, o) {
  return (bytes[o] | (bytes[o + 1] << 8) | (bytes[o + 2] << 16) | (bytes[o + 3] << 24)) >>> 0;
}

async function inflateRaw(compressedBytes) {
  if (typeof DecompressionStream !== "function") {
    throw new Error("此瀏覽器不支援解壓縮 ZIP（缺少 DecompressionStream）。");
  }
  const tryAlg = async (alg) => {
    const ds = new DecompressionStream(alg);
    const stream = new Blob([compressedBytes]).stream().pipeThrough(ds);
    return new Uint8Array(await new Response(stream).arrayBuffer());
  };
  try {
    return await tryAlg("deflate-raw");
  } catch {
    return await tryAlg("deflate");
  }
}

async function extractJpegsFromZip(zipFile) {
  const bytes = new Uint8Array(await zipFile.arrayBuffer());
  const len = bytes.length;

  let eocd = -1;
  const min = Math.max(0, len - 65557);
  for (let i = len - 22; i >= min; i--) {
    if (bytes[i] === 0x50 && bytes[i + 1] === 0x4b && bytes[i + 2] === 0x05 && bytes[i + 3] === 0x06) {
      eocd = i;
      break;
    }
  }
  if (eocd < 0) throw new Error("ZIP 格式錯誤：找不到 EOCD。");

  const totalEntries = u16le(bytes, eocd + 10);
  const cdSize = u32le(bytes, eocd + 12);
  const cdOffset = u32le(bytes, eocd + 16);

  let p = cdOffset;
  const out = [];
  const decoder = new TextDecoder("utf-8");

  for (let idx = 0; idx < totalEntries; idx++) {
    if (!(bytes[p] === 0x50 && bytes[p + 1] === 0x4b && bytes[p + 2] === 0x01 && bytes[p + 3] === 0x02)) {
      throw new Error("ZIP 格式錯誤：中央目錄簽名不正確。");
    }
    const gpFlag = u16le(bytes, p + 8);
    const method = u16le(bytes, p + 10);
    const crc = u32le(bytes, p + 16);
    const compSize = u32le(bytes, p + 20);
    const uncompSize = u32le(bytes, p + 24);
    const nameLen = u16le(bytes, p + 28);
    const extraLen = u16le(bytes, p + 30);
    const commentLen = u16le(bytes, p + 32);
    const localOff = u32le(bytes, p + 42);
    const nameBytes = bytes.slice(p + 46, p + 46 + nameLen);
    const name = decoder.decode(nameBytes);

    p = p + 46 + nameLen + extraLen + commentLen;

    const base = name.split("/").pop();
    if (!base || base.endsWith("/")) continue;
    if (base === ".ds_store" || base.startsWith("._") || base.startsWith(".")) continue;
    if (!isImageFileName(base)) continue;

    if (!(bytes[localOff] === 0x50 && bytes[localOff + 1] === 0x4b && bytes[localOff + 2] === 0x03 && bytes[localOff + 3] === 0x04)) {
      throw new Error("ZIP 格式錯誤：Local header 簽名不正確。");
    }
    const lNameLen = u16le(bytes, localOff + 26);
    const lExtraLen = u16le(bytes, localOff + 28);
    const dataOff = localOff + 30 + lNameLen + lExtraLen;
    const comp = bytes.slice(dataOff, dataOff + compSize);

    let data = null;
    if (method === 0) data = comp;
    else if (method === 8) data = await inflateRaw(comp);
    else throw new Error(`ZIP 壓縮方法不支援：${method}`);

    if (uncompSize && data.length !== uncompSize) {
      throw new Error(`ZIP 解壓縮大小不一致：${name}`);
    }
    if (crc && crc32(data) !== crc) {
      throw new Error(`ZIP CRC32 驗證失敗：${name}`);
    }

    out.push(new File([data], base, { type: "image/jpeg", lastModified: Date.now() }));
    if (idx % 50 === 0) await new Promise((r) => setTimeout(r, 0));
  }

  if (!out.length) throw new Error("ZIP 裡找不到 JPEG 圖片。");
  out.sort((a, b) => naturalCompare(a.name, b.name));
  return out;
}

async function extractJpegsFromJpk(jpkFile) {
  const bytes = new Uint8Array(await jpkFile.arrayBuffer());
  if (bytes.length < 16) throw new Error("JPK 格式錯誤：檔案太小。");
  const sig = String.fromCharCode(bytes[0], bytes[1], bytes[2], bytes[3]);
  if (sig !== "JPK1") throw new Error("JPK 格式錯誤：signature 不正確。");
  const count = u32le(bytes, 4);
  const maxSize = u32le(bytes, 8);
  if (!count) throw new Error("JPK 格式錯誤：count = 0。");

  let off = 16;
  const out = [];
  const digits = 3;
  for (let i = 0; i < count; i++) {
    if (off + 4 > bytes.length) throw new Error("JPK 格式錯誤：frame header 越界。");
    const size = u32le(bytes, off);
    off += 4;
    if (size > maxSize && maxSize !== 0) {
      throw new Error(`JPK 格式錯誤：frame size 超過 max_size（${size} > ${maxSize}）。`);
    }
    if (off + size > bytes.length) throw new Error("JPK 格式錯誤：frame data 越界。");
    const data = bytes.slice(off, off + size);
    off += size;
    if (!(data.length >= 2 && data[0] === 0xff && data[1] === 0xd8)) {
      throw new Error(`JPK 內容不是 JPEG：frame ${i}`);
    }
    const name = String(i).padStart(digits, "0") + ".jpeg";
    out.push(new File([data], name, { type: "image/jpeg", lastModified: Date.now() }));
    if (i % 50 === 0) await new Promise((r) => setTimeout(r, 0));
  }
  return out;
}

function setPicked(newFiles) {
  const seq = ++_pickSeq;
  (async () => {
    const deduped = dedupeFiles(newFiles.slice());
    const isIgnoredFile = (f) => {
      const lower = String(f.name || "").toLowerCase();
      const base = lower.split("/").pop();
      return base === ".ds_store" || base.startsWith("._") || base.startsWith(".");
    };
    const ignored = deduped.filter(isIgnoredFile);
    files = deduped.filter((f) => !isIgnoredFile(f));

    resetProgress();
    clearSrc();
    images = [];
    mode = "—";
    _rangeReset = true;

    $("pickedCount").textContent = String(files.length);
    $("pickedIgnored").textContent = String(ignored.length);
    const ps = $("pickStatus");
    if (ps) ps.textContent = "";
    if (seq !== _pickSeq) return;

    if (files.length === 1 && isJpkFileName(files[0].name)) {
      $("mode").textContent = "photo(jpk)";
      $("run").disabled = true;
      $("togglePlay").disabled = true;
      if (ps) ps.textContent = "正在解析 JPK...";
      setProgress(5);
      try {
        images = await extractJpegsFromJpk(files[0]);
        if (seq !== _pickSeq) return;
        $("pickedImages").textContent = String(images.length);
        $("run").disabled = false;
        if (ps) ps.textContent = "";
        setProgress(0);
        mode = "photo";
        const ifr = $("inputFps");
        const ifn = $("inputFpsNum");
        if (ifr) ifr.value = String(_lastPhotoInputFps);
        if (ifn) ifn.value = String(_lastPhotoInputFps);
        updateFpsInfo();
        showImageAt(0);
        updateVideoFrameDomain();
      } catch (e) {
        if (seq !== _pickSeq) return;
        mode = "unknown";
        $("mode").textContent = "unknown";
        $("pickedImages").textContent = "0";
        if (ps) ps.textContent = String(e && e.message ? e.message : e);
        setProgress(0);
      } finally {
        if (seq === _pickSeq) setPlayButton();
      }
      return;
    }

    if (files.length === 1 && isZipFileName(files[0].name)) {
      $("mode").textContent = "photo(zip)";
      $("run").disabled = true;
      $("togglePlay").disabled = true;
      if (ps) ps.textContent = "正在解析 ZIP...";
      setProgress(5);
      try {
        images = await extractJpegsFromZip(files[0]);
        if (seq !== _pickSeq) return;
        $("pickedImages").textContent = String(images.length);
        $("run").disabled = false;
        if (ps) ps.textContent = "";
        setProgress(0);
        mode = "photo";
        const ifr = $("inputFps");
        const ifn = $("inputFpsNum");
        if (ifr) ifr.value = String(_lastPhotoInputFps);
        if (ifn) ifn.value = String(_lastPhotoInputFps);
        updateFpsInfo();
        showImageAt(0);
        updateVideoFrameDomain();
      } catch (e) {
        if (seq !== _pickSeq) return;
        mode = "unknown";
        $("mode").textContent = "unknown";
        $("pickedImages").textContent = "0";
        if (ps) ps.textContent = String(e && e.message ? e.message : e);
        setProgress(0);
      } finally {
        if (seq === _pickSeq) setPlayButton();
      }
      return;
    }

    images = files
      .filter((f) => isImageFileName(f.name))
      .sort((a, b) => naturalCompare(a.webkitRelativePath || a.name, b.webkitRelativePath || b.name));
    $("pickedImages").textContent = String(images.length);

    mode = detectMode(files);
    $("mode").textContent = mode;
    $("run").disabled = mode === "unknown" || mode === "—";
    await loadPreview(seq);
    if (seq !== _pickSeq) return;
    setPlayButton();
  })();
}

function addFiles(list) {
  setPicked(Array.from(list || []));
}

function params() {
  return {
    crop_mode: $("cropMode").value,
    width: $("width").value,
    height: $("height").value,
    rotate: $("rotate").value,
    contrast: $("contrast").value,
    quality: $("quality").value,
    max_jpeg_kb: $("maxJpegKb") ? $("maxJpegKb").value : "0",
    input_fps: $("inputFps") ? $("inputFps").value : "30",
    frame_step: $("frameStep") ? $("frameStep").value : "1",
    video_parallel: $("videoParallel") ? $("videoParallel").value : "4",
    video_start_frame: $("videoStartFrame") ? $("videoStartFrame").value : "0",
    video_end_frame: $("videoEndFrame") ? $("videoEndFrame").value : "0",
  };
}

function clampToInput(el, value) {
  const min = el.min !== "" ? Number(el.min) : -Infinity;
  const max = el.max !== "" ? Number(el.max) : Infinity;
  const step = el.step !== "" ? Number(el.step) : 0;
  let v = Number(value);
  if (!isFinite(v)) v = Number(el.value) || 0;
  v = Math.max(min, Math.min(max, v));
  if (step && isFinite(step) && step > 0) v = Math.round(v / step) * step;
  return v;
}

function linkRangeAndNumber(rangeId, numberId, format) {
  const r = $(rangeId);
  const n = $(numberId);
  if (!r || !n) return;

  const syncFromRange = () => {
    const v = clampToInput(r, r.value);
    r.value = String(v);
    n.value = format ? format(v) : String(v);
  };
  const syncFromNumber = () => {
    const v = clampToInput(n, n.value);
    r.value = String(v);
    n.value = format ? format(v) : String(v);
  };

  r.addEventListener("input", () => {
    syncFromRange();
  });
  n.addEventListener("input", () => {
    syncFromNumber();
  });
  n.addEventListener("blur", () => {
    syncFromNumber();
  });

  syncFromRange();
}

function initRanges() {
  linkRangeAndNumber("width", "widthNum");
  linkRangeAndNumber("height", "heightNum");
  linkRangeAndNumber("quality", "qualityNum");
  linkRangeAndNumber("maxJpegKb", "maxJpegKbNum");
  linkRangeAndNumber("inputFps", "inputFpsNum");
  linkRangeAndNumber("frameStep", "frameStepNum");
  linkRangeAndNumber("videoParallel", "videoParallelNum");
  linkRangeAndNumber("contrast", "contrastNum", (v) => Number(v).toFixed(2));
  const fs = $("frameStep");
  const fsn = $("frameStepNum");
  const onOutChange = () => updateFpsInfo();
  if (fs) fs.addEventListener("input", onOutChange);
  if (fsn) fsn.addEventListener("input", onOutChange);

  const ifr = $("inputFps");
  const ifn = $("inputFpsNum");
  const onInChange = () => {
    const fps = getInputFps();
    if (mode === "photo") _lastPhotoInputFps = fps;
    if (mode === "video") _lastVideoInputFps = fps;
    updateFpsInfo();
    if (mode === "video") updateVideoFrameDomain();
  };
  if (ifr) ifr.addEventListener("input", onInChange);
  if (ifn) ifn.addEventListener("input", onInChange);
  updateFpsInfo();
}

function enableVideoRangeControls(enabled) {
  const sr = $("videoStartRange");
  const er = $("videoEndRange");
  const hint = $("videoRangeHint");
  if (sr) sr.disabled = !enabled;
  if (er) er.disabled = !enabled;
  if (hint) hint.textContent = enabled ? "" : "請先載入來源以啟用範圍拖動（以 Frames 計）";
}

function updateVideoRangeGradient(maxFrameIndex) {
  const sr = $("videoStartRange");
  const er = $("videoEndRange");
  const trackEl = $("videoRangeTrack");
  if (!sr || !er || !trackEl) return;
  const s = Number(sr.value) || 0;
  const e = Number(er.value) || 0;
  const max = maxFrameIndex > 0 ? maxFrameIndex : Number(sr.max) || 0;
  if (max <= 0) return;
  const a = Math.max(0, Math.min(100, (Math.min(s, e) / max) * 100));
  const b = Math.max(0, Math.min(100, (Math.max(s, e) / max) * 100));
  const track = `linear-gradient(to right, #223146 0%, #223146 ${a}%, #6aa6ff ${a}%, #6aa6ff ${b}%, #223146 ${b}%, #223146 100%)`;
  trackEl.style.background = track;
}

let _activeVideoHandle = "end";

function setVideoHandleZ(sr, er) {
  if (!sr || !er) return;
  if (_activeVideoHandle === "start") {
    sr.style.zIndex = "3";
    er.style.zIndex = "2";
  } else {
    sr.style.zIndex = "2";
    er.style.zIndex = "3";
  }
}

let _videoDurationSec = 0;
let _videoTotalFrames = 0;

function getInputFps() {
  const raw = parseFloat(params().input_fps || "30");
  const v = isFinite(raw) ? raw : 30;
  return Math.max(1, v);
}

function computeTotalFrames(durationSec, fps) {
  const dur = Math.max(0, durationSec || 0);
  const f = Math.max(1, fps || 1);
  return Math.max(1, Math.floor(dur * f) + 1);
}

function getFrameStep() {
  const v = Math.max(1, parseInt(params().frame_step || "1", 10));
  return isFinite(v) ? v : 1;
}

function updateFpsInfo() {
  const info = $("fpsInfo");
  const out = $("fpsOutInfo");
  const step = getFrameStep();
  const vin = getInputFps();
  if (info) {
    const det = _videoDetectedFps > 0 ? _videoDetectedFps.toFixed(2) : "—";
    info.textContent = `Video 偵測: ${det}　Photo 參考: 30（可調）`;
  }
  if (out) {
    const fout = vin > 0 ? vin / step : 0;
    out.textContent = `Output FPS: ${fout.toFixed(2)}  (每 ${step} 幀取 1 幀)`;
  }
}

async function detectVideoFpsFromVideo(v) {
  if (!v || typeof v.requestVideoFrameCallback !== "function") return 0;
  if (!isFinite(v.duration) || v.duration <= 0) return 0;
  const times = [];
  let resolveDone = null;
  const p = new Promise((resolve) => {
    resolveDone = resolve;
  });
  const timeoutP = new Promise((resolve) => setTimeout(() => resolve(0), 900));
  const t0 = performance.now();
  const cb = (_now, meta) => {
    if (meta && isFinite(meta.mediaTime)) times.push(meta.mediaTime);
    const tooLong = performance.now() - t0 > 800;
    if (times.length >= 10 || tooLong) {
      if (times.length >= 2) {
        const dt = times[times.length - 1] - times[0];
        const fps = dt > 0 ? (times.length - 1) / dt : 0;
        resolveDone(fps);
      } else {
        resolveDone(0);
      }
      return;
    }
    v.requestVideoFrameCallback(cb);
  };
  try {
    const wasPaused = v.paused;
    const wasMuted = v.muted;
    v.muted = true;
    await seekVideo(v, 0);
    if (wasPaused) {
      await v.play().catch(() => {});
    }
    v.requestVideoFrameCallback(cb);
    const fps = await Promise.race([p, timeoutP]);
    v.pause();
    v.muted = wasMuted;
    return fps;
  } catch {
    return 0;
  }
}

function updateVideoFrameDomain() {
  const sr = $("videoStartRange");
  const er = $("videoEndRange");
  const sn = $("videoStartFrame");
  const en = $("videoEndFrame");
  if (!sr || !er || !sn || !en) return;

  if (mode === "photo") {
    const total = images.length;
    if (!total) {
      enableVideoRangeControls(false);
      return;
    }
    _videoDurationSec = 0;
    _videoTotalFrames = total;
    const maxIndex = total - 1;
    sr.max = String(maxIndex);
    er.max = String(maxIndex);
    sr.step = "1";
    er.step = "1";
    sn.max = String(maxIndex);
    en.max = String(maxIndex);
    enableVideoRangeControls(true);
    if (_rangeReset) {
      resetSelectedRangeInputs();
      _rangeReset = false;
    }
    clampVideoRangeToInputs();
    return;
  }

  if (mode === "video") {
    const v = $("srcVideo");
    if (!v || !isFinite(v.duration) || v.duration <= 0) {
      enableVideoRangeControls(false);
      return;
    }
    _videoDurationSec = v.duration;
    const fps = getInputFps();
    _videoTotalFrames = computeTotalFrames(_videoDurationSec, fps);
    const maxIndex = _videoTotalFrames - 1;
    sr.max = String(maxIndex);
    er.max = String(maxIndex);
    sr.step = "1";
    er.step = "1";
    sn.max = String(maxIndex);
    en.max = String(maxIndex);
    enableVideoRangeControls(true);
    if (_rangeReset) {
      resetSelectedRangeInputs();
      _rangeReset = false;
    }
    clampVideoRangeToInputs();
    return;
  }

  enableVideoRangeControls(false);
  return;
}

function clampVideoRangeToInputs() {
  const sr = $("videoStartRange");
  const er = $("videoEndRange");
  const sn = $("videoStartFrame");
  const en = $("videoEndFrame");
  if (!sr || !er || !sn || !en) return;

  const max = Number(sr.max) || 0;
  const clamp = (v) => Math.max(0, Math.min(max, v));

  let s = clamp(Number(sn.value) || 0);
  let eRaw = Number(en.value) || 0;
  const endIsToEnd = eRaw <= 0;
  let e = endIsToEnd ? max : clamp(eRaw);
  if (e < s) e = s;

  s = Math.round(s);
  e = Math.round(e);

  sr.value = String(s);
  er.value = String(e);
  sn.value = String(s);
  en.value = endIsToEnd && e === max ? "0" : String(e);

  const vd = $("videoDur");
  if (vd) {
    const total = max + 1;
    if (mode === "video") {
      const fps = getInputFps();
      vd.textContent = total > 0 ? `Frames: ${total}  (${_videoDurationSec.toFixed(2)}s @ ${fps}fps)` : "Frames: —";
    } else if (mode === "photo") {
      vd.textContent = total > 0 ? `Frames: ${total}  (photo)` : "Frames: —";
    } else {
      vd.textContent = "Frames: —";
    }
  }
  updateVideoRangeGradient(max);
  setVideoHandleZ(sr, er);
  updateFpsInfo();
}

function initVideoRange() {
  const sr = $("videoStartRange");
  const er = $("videoEndRange");
  const sn = $("videoStartFrame");
  const en = $("videoEndFrame");
  if (!sr || !er || !sn || !en) return;

  enableVideoRangeControls(false);
  setVideoHandleZ(sr, er);

  let thumbPending = null;
  let thumbRaf = 0;
  const requestThumb = (frame) => {
    thumbPending = frame;
    if (thumbRaf) return;
    thumbRaf = requestAnimationFrame(() => {
      thumbRaf = 0;
      const f = thumbPending;
      thumbPending = null;
      if (f == null) return;
      updateThumb(f);
    });
  };

  const refreshActiveHandleFromFocus = () => {
    const ae = document.activeElement;
    if (ae === sr || ae === sn) _activeVideoHandle = "start";
    else if (ae === er || ae === en) _activeVideoHandle = "end";
    setVideoHandleZ(sr, er);
  };

  const keepVisibleWhileEditing = () => {
    const ae = document.activeElement;
    if (ae === sr || ae === er || ae === sn || ae === en) showThumbTip();
  };

  const applyRangeToPreviewIfNeeded = () => {
    if (mode === "photo") {
      const r = getSelectedFrameRange();
      if (images.length) {
        if (imageIndex < r.start || imageIndex > r.end) {
          imageIndex = r.start;
          showImageAt(imageIndex);
        }
      }
      updateScrubUI();
      return;
    }
    if (mode === "video") {
      const v = $("srcVideo");
      if (!v || !isFinite(v.duration) || v.duration <= 0) return;
      if (!v.paused) return;
      const fps = getInputFps();
      const r = getSelectedFrameRange();
      const startT = r.start / fps;
      const endT = r.end / fps;
      const t = isFinite(v.currentTime) ? v.currentTime : 0;
      if (t < startT - 0.002 || t > endT + 0.002) v.currentTime = startT;
      updateScrubUI();
    }
  };

  const syncFromRanges = () => {
    refreshActiveHandleFromFocus();
    const max = Number(sr.max) || 0;
    let s = Number(sr.value) || 0;
    let e = Number(er.value) || 0;
    if (e < s) {
      if (_activeVideoHandle === "start") e = s;
      else s = e;
    }
    s = Math.round(s);
    e = Math.round(e);
    sn.value = String(s);
    en.value = e === max ? "0" : String(e);
    updateVideoRangeGradient(max);
    keepVisibleWhileEditing();
    requestThumb(_activeVideoHandle === "end" ? e : s);
    applyRangeToPreviewIfNeeded();
  };

  sr.addEventListener("pointerdown", () => {
    _activeVideoHandle = "start";
    setVideoHandleZ(sr, er);
    showThumbTip();
    requestThumb(Number(sr.value) || 0);
  });
  er.addEventListener("pointerdown", () => {
    _activeVideoHandle = "end";
    setVideoHandleZ(sr, er);
    showThumbTip();
    requestThumb(Number(er.value) || 0);
  });

  sr.addEventListener("input", () => syncFromRanges());
  er.addEventListener("input", () => syncFromRanges());
  const syncFromInputs = () => {
    refreshActiveHandleFromFocus();
    clampVideoRangeToInputs();
    keepVisibleWhileEditing();
    const v = _activeVideoHandle === "end" ? Number(er.value) || 0 : Number(sr.value) || 0;
    requestThumb(v);
    applyRangeToPreviewIfNeeded();
  };
  sn.addEventListener("input", () => syncFromInputs());
  en.addEventListener("input", () => syncFromInputs());
  sn.addEventListener("blur", () => clampVideoRangeToInputs());
  en.addEventListener("blur", () => clampVideoRangeToInputs());

  const onFocus = () => {
    refreshActiveHandleFromFocus();
    showThumbTip();
    const v = _activeVideoHandle === "end" ? Number(er.value) || 0 : Number(sr.value) || 0;
    requestThumb(v);
  };
  sr.addEventListener("focus", onFocus);
  er.addEventListener("focus", onFocus);
  sn.addEventListener("focus", onFocus);
  en.addEventListener("focus", onFocus);

  const hideIfNotEditing = () => {
    setTimeout(() => {
      const ae = document.activeElement;
      if (ae === sr || ae === er || ae === sn || ae === en) return;
      hideThumbTipNow();
    }, 0);
  };
  sr.addEventListener("blur", hideIfNotEditing);
  er.addEventListener("blur", hideIfNotEditing);
  sn.addEventListener("blur", hideIfNotEditing);
  en.addEventListener("blur", hideIfNotEditing);

  const tip = $("videoThumbTip");
  const stack = $("videoRangeTrack") ? $("videoRangeTrack").parentElement : null;
  const hideIfOutside = (e) => {
    const t = e.target;
    if (!t) return;
    if (t === sr || t === er || t === sn || t === en) return;
    if (stack && (t === stack || stack.contains(t))) return;
    if (tip && (t === tip || tip.contains(t))) return;
    hideThumbTipNow();
  };
  document.addEventListener("pointerdown", hideIfOutside, true);
}


function clearSrc() {
  if (srcUrl) URL.revokeObjectURL(srcUrl);
  srcUrl = null;
  lastVideoW = 0;
  lastVideoH = 0;
  stopVideoLoop();
  stopPlayback();
  imageIndex = 0;
  if (imageObjUrl) URL.revokeObjectURL(imageObjUrl);
  imageObjUrl = null;
  enableVideoRangeControls(false);
  const vd = $("videoDur");
  if (vd) vd.textContent = "Frames: —";
  _videoDetectedFps = 0;
  updateFpsInfo();
  hideThumbTipNow();
  _thumbLastFrame = -1;
  _thumbSeq++;
  _previewSeq++;
  _lastVideoPreviewOutIndex = -1;
  _previewPending = null;
  if (_previewRaf) cancelAnimationFrame(_previewRaf);
  _previewRaf = 0;
  if (_thumbVideo) {
    _thumbVideo.pause();
    _thumbVideo.removeAttribute("src");
    _thumbVideo.load();
  }
}

function stopVideoLoop() {
  if (rafId) cancelAnimationFrame(rafId);
  rafId = 0;
  const v = $("srcVideo");
  if (videoFrameCb && v && typeof v.cancelVideoFrameCallback === "function") {
    try {
      v.cancelVideoFrameCallback(videoFrameCb);
    } catch {
    }
  }
  videoFrameCb = null;
}

function setPlayButton() {
  const btn = $("togglePlay");
  if (!btn) return;
  btn.textContent = isPlaying ? "暫停" : "播放";
  btn.disabled = isConverting || mode === "unknown" || mode === "—";
}

function stopPlayback() {
  if (slideshowTimer) clearInterval(slideshowTimer);
  slideshowTimer = 0;
  isPlaying = false;
  const v = $("srcVideo");
  if (v && !v.paused) v.pause();
  setPlayButton();
}

function enforceVideoRangeLoop(v) {
  if (!v || mode !== "video" || v.paused || isConverting) return;
  const fps = getInputFps();
  const { start, end } = getSelectedFrameRange();
  const startT = start / fps;
  const endT = end / fps;
  const t = isFinite(v.currentTime) ? v.currentTime : 0;
  if (t < startT - 0.002) {
    v.currentTime = startT;
    return;
  }
  if (t > endT + 0.002) {
    v.currentTime = startT;
  }
}

function startPlayback() {
  if (isConverting) return;
  if (mode === "video") {
    const v = $("srcVideo");
    if (!v) return;
    const fps = getInputFps();
    const { start, end } = getSelectedFrameRange();
    const startT = start / fps;
    const endT = end / fps;
    const t = isFinite(v.currentTime) ? v.currentTime : 0;
    if (t < startT - 0.002 || t > endT + 0.002) v.currentTime = startT;
    isPlaying = true;
    setPlayButton();
    v.play().catch(() => {
      isPlaying = false;
      setPlayButton();
    });
    return;
  }
  if (mode === "photo") {
    const fps = getInputFps();
    const { start, end } = getSelectedFrameRange();
    if (images.length) {
      if (imageIndex < start || imageIndex > end) {
        imageIndex = start;
        showImageAt(imageIndex);
      }
    }
    const interval = Math.max(20, Math.round(1000 / fps));
    isPlaying = true;
    setPlayButton();
    if (slideshowTimer) clearInterval(slideshowTimer);
    slideshowTimer = setInterval(() => {
      if (!images.length) return;
      const range = getSelectedFrameRange();
      const s = Math.max(0, Math.min(images.length - 1, range.start));
      const e = Math.max(0, Math.min(images.length - 1, range.end));
      if (imageIndex < s || imageIndex > e) imageIndex = s;
      const next = imageIndex >= e ? s : imageIndex + 1;
      showImageAt(next);
    }, interval);
  }
}
function startVideoLoop() {
  stopVideoLoop();
  const v = $("srcVideo");
  if (!v) return;
  if (typeof v.requestVideoFrameCallback === "function") {
    const cb = () => {
      enforceVideoRangeLoop(v);
      renderProcessedFromVideo();
      videoFrameCb = v.requestVideoFrameCallback(cb);
    };
    videoFrameCb = v.requestVideoFrameCallback(cb);
    return;
  }
  const loop = () => {
    enforceVideoRangeLoop(v);
    renderProcessedFromVideo();
    rafId = requestAnimationFrame(loop);
  };
  rafId = requestAnimationFrame(loop);
}

function canvasSizeToElement(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max(1, Math.round(rect.width * dpr));
  const h = Math.max(1, Math.round(rect.height * dpr));
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
}

function drawFit(ctx, sourceCanvas, w, h) {
  const sw = sourceCanvas.width;
  const sh = sourceCanvas.height;
  const scale = Math.min(w / sw, h / sh);
  const dw = sw * scale;
  const dh = sh * scale;
  const dx = (w - dw) / 2;
  const dy = (h - dh) / 2;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#0b1220";
  ctx.fillRect(0, 0, w, h);
  ctx.drawImage(sourceCanvas, dx, dy, dw, dh);
}

function renderImageAfter(imgBitmap) {
  const p = params();
  const w = Math.max(1, parseInt(p.width || "160", 10));
  const h = Math.max(1, parseInt(p.height || "160", 10));
  const rotate = parseInt(p.rotate || "0", 10) || 0;
  const cropMode = p.crop_mode || "cover";
  const contrast = parseFloat(p.contrast || "1.0");

  const tmp = document.createElement("canvas");
  tmp.width = w;
  tmp.height = h;
  const tctx = tmp.getContext("2d");
  tctx.fillStyle = "#000";
  tctx.fillRect(0, 0, w, h);
  tctx.save();
  if (rotate) {
    tctx.translate(w / 2, h / 2);
    tctx.rotate((rotate * Math.PI) / 180);
    tctx.translate(-w / 2, -h / 2);
  }
  tctx.filter = Math.abs(contrast - 1.0) < 1e-6 ? "none" : `contrast(${Math.max(0.1, contrast) * 100}%)`;
  const sx = imgBitmap.width;
  const sy = imgBitmap.height;
  const scale = cropMode === "contain" ? Math.min(w / sx, h / sy) : Math.max(w / sx, h / sy);
  const dw = sx * scale;
  const dh = sy * scale;
  const dx = (w - dw) / 2;
  const dy = (h - dh) / 2;
  tctx.drawImage(imgBitmap, dx, dy, dw, dh);
  tctx.restore();

  const out = $("dstCanvas");
  canvasSizeToElement(out);
  const octx = out.getContext("2d");
  drawFit(octx, tmp, out.width, out.height);
}

function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const _crcTable = (() => {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let k = 0; k < 8; k++) c = (c & 1) ? 0xedb88320 ^ (c >>> 1) : (c >>> 1);
    table[i] = c >>> 0;
  }
  return table;
})();

function crc32(bytes) {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) c = _crcTable[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function uint32le(n) {
  const b = new Uint8Array(4);
  const v = n >>> 0;
  b[0] = v & 0xff;
  b[1] = (v >>> 8) & 0xff;
  b[2] = (v >>> 16) & 0xff;
  b[3] = (v >>> 24) & 0xff;
  return b;
}

function uint16le(n) {
  const b = new Uint8Array(2);
  const v = n & 0xffff;
  b[0] = v & 0xff;
  b[1] = (v >>> 8) & 0xff;
  return b;
}

function dosTimeDate(d) {
  const dt = d || new Date();
  const sec = Math.floor(dt.getSeconds() / 2);
  const min = dt.getMinutes();
  const hour = dt.getHours();
  const day = dt.getDate();
  const month = dt.getMonth() + 1;
  const year = dt.getFullYear();
  const dosTime = (hour << 11) | (min << 5) | sec;
  const dosDate = ((year - 1980) << 9) | (month << 5) | day;
  return { dosTime, dosDate };
}

async function buildZipFromJpegs(blobs) {
  const parts = [];
  const central = [];
  let offset = 0;
  const { dosTime, dosDate } = dosTimeDate();
  const encoder = new TextEncoder();

  const digits = 3;

  for (let i = 0; i < blobs.length; i++) {
    const name = String(i).padStart(digits, "0") + ".jpeg";
    const nameBytes = encoder.encode(name);
    const data = new Uint8Array(await blobs[i].arrayBuffer());
    const c = crc32(data);
    const size = data.length >>> 0;

    const localHeader = [
      uint32le(0x04034b50),
      uint16le(20),
      uint16le(0),
      uint16le(0),
      uint16le(dosTime),
      uint16le(dosDate),
      uint32le(c),
      uint32le(size),
      uint32le(size),
      uint16le(nameBytes.length),
      uint16le(0),
    ];
    for (const p of localHeader) parts.push(p);
    parts.push(nameBytes);
    parts.push(data);

    const localOffset = offset;
    offset += localHeader.reduce((s, b) => s + b.length, 0) + nameBytes.length + data.length;

    const centralHeader = [
      uint32le(0x02014b50),
      uint16le(20),
      uint16le(20),
      uint16le(0),
      uint16le(0),
      uint16le(dosTime),
      uint16le(dosDate),
      uint32le(c),
      uint32le(size),
      uint32le(size),
      uint16le(nameBytes.length),
      uint16le(0),
      uint16le(0),
      uint16le(0),
      uint16le(0),
      uint32le(0),
      uint32le(localOffset),
    ];
    for (const p of centralHeader) central.push(p);
    central.push(nameBytes);

    if (i % 20 === 0) await new Promise((r) => setTimeout(r, 0));
  }

  const centralStart = offset;
  let centralSize = 0;
  for (const p of central) {
    parts.push(p);
    centralSize += p.length;
  }
  offset += centralSize;

  const eocd = [
    uint32le(0x06054b50),
    uint16le(0),
    uint16le(0),
    uint16le(blobs.length),
    uint16le(blobs.length),
    uint32le(centralSize),
    uint32le(centralStart),
    uint16le(0),
  ];
  for (const p of eocd) parts.push(p);

  return new Blob(parts, { type: "application/zip" });
}

async function buildJpk(blobs) {
  const parts = [];
  parts.push(new TextEncoder().encode("JPK1"));
  const sizes = [];
  let maxSize = 0;
  for (const blob of blobs) {
    const size = blob.size;
    sizes.push(size);
    if (size > maxSize) maxSize = size;
  }
  parts.push(uint32le(blobs.length));
  parts.push(uint32le(maxSize));
  parts.push(uint32le(0));
  for (let i = 0; i < blobs.length; i++) {
    const buf = new Uint8Array(await blobs[i].arrayBuffer());
    parts.push(uint32le(buf.length));
    parts.push(buf);
  }
  return new Blob(parts, { type: "application/octet-stream" });
}

async function renderImageToJpegBlob(file, p) {
  const bmp = await createImageBitmap(file);
  const w = Math.max(1, parseInt(p.width || "160", 10));
  const h = Math.max(1, parseInt(p.height || "160", 10));
  const rotate = parseInt(p.rotate || "0", 10) || 0;
  const cropMode = p.crop_mode || "cover";
  const contrast = parseFloat(p.contrast || "1.0");
  const quality = Math.min(100, Math.max(1, parseInt(p.quality || "85", 10)));
  const capKb = Math.max(0, parseInt(p.max_jpeg_kb || "0", 10) || 0);
  const maxBytes = capKb > 0 ? capKb * 1024 : 0;

  const canvas = typeof OffscreenCanvas !== "undefined" ? new OffscreenCanvas(w, h) : document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, w, h);

  ctx.save();
  if (rotate) {
    ctx.translate(w / 2, h / 2);
    ctx.rotate((rotate * Math.PI) / 180);
    ctx.translate(-w / 2, -h / 2);
  }
  ctx.filter = Math.abs(contrast - 1.0) < 1e-6 ? "none" : `contrast(${Math.max(0.1, contrast) * 100}%)`;
  const sx = bmp.width;
  const sy = bmp.height;
  const scale = cropMode === "contain" ? Math.min(w / sx, h / sy) : Math.max(w / sx, h / sy);
  const dw = sx * scale;
  const dh = sy * scale;
  const dx = (w - dw) / 2;
  const dy = (h - dh) / 2;
  ctx.drawImage(bmp, dx, dy, dw, dh);
  ctx.restore();

  const encode = async (q) => {
    if (typeof canvas.convertToBlob === "function") {
      return await canvas.convertToBlob({ type: "image/jpeg", quality: q / 100 });
    }
    return await new Promise((resolve) => canvas.toBlob((b) => resolve(b), "image/jpeg", q / 100));
  };

  if (maxBytes > 0) {
    let lo = 1;
    let hi = quality;
    let best = null;
    for (let i = 0; i < 7 && lo <= hi; i++) {
      const mid = Math.floor((lo + hi) / 2);
      const b = await encode(mid);
      if (b && b.size <= maxBytes) {
        best = b;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    return best ? best : await encode(1);
  }
  return await encode(quality);
}

function updateScrubUI() {
  const scrub = $("scrub");
  const l1 = $("scrubLine1");
  const l2 = $("scrubLine2");
  if (mode === "photo") {
    const r = getSelectedFrameRange();
    const start = Math.max(0, Math.min(images.length ? images.length - 1 : 0, r.start));
    const end = Math.max(0, Math.min(images.length ? images.length - 1 : 0, r.end));
    const s = Math.min(start, end);
    const e = Math.max(start, end);
    scrub.min = String(s);
    scrub.max = String(e);
    scrub.step = "1";
    if (imageIndex < s || imageIndex > e) imageIndex = s;
    scrub.value = String(imageIndex);
    $("scrubLabel").textContent = "Frame";
    const denom = Math.max(1, e - s + 1);
    const numer = Math.max(1, imageIndex - s + 1);
    if (l1) l1.textContent = images.length ? `Frame: ${numer}/${denom}` : "";
    if (l2) l2.textContent = images.length ? `Range: ${s}..${e}  (of ${Math.max(0, images.length - 1)})` : "";
    return;
  }
  if (mode === "video") {
    scrub.min = "0";
    scrub.max = "100";
    scrub.step = "1";
    const v = $("srcVideo");
    const dur = v && isFinite(v.duration) ? v.duration : 0;
    const t = isConverting ? _convertVideoT : v && isFinite(v.currentTime) ? v.currentTime : 0;
    const fps = getInputFps();
    const r = getSelectedFrameRange();
    const startT = r.start / fps;
    const endT = r.end / fps;
    const rangeDur = Math.max(0, endT - startT);
    const rel = rangeDur > 0 ? (t - startT) / rangeDur : 0;
    const pct = Math.round(Math.max(0, Math.min(1, rel)) * 100);
    scrub.value = String(pct);
    $("scrubLabel").textContent = "Time";
    const frame = isConverting ? _convertVideoFrame : Math.max(0, Math.round(t * fps));
    const rangePos = Math.max(0, Math.min(r.end - r.start, Math.round((t - startT) * fps)));
    const rangeDenom = Math.max(1, r.end - r.start + 1);
    const rangeNumer = Math.max(1, rangePos + 1);
    if (l1) l1.textContent = dur > 0 ? `Time: ${t.toFixed(2)}s / ${dur.toFixed(2)}s` : "";
    if (l2) l2.textContent = dur > 0 ? `Frame: ${frame}  •  Range: ${rangeNumer}/${rangeDenom}` : "";
    return;
  }
  $("scrubLabel").textContent = "Progress";
  if (l1) l1.textContent = "";
  if (l2) l2.textContent = "";
}

function renderProcessedFromVideo() {
  if (isConverting) return;
  const v = $("srcVideo");
  if (!v || v.readyState < 2) return;
  if (!v.videoWidth || !v.videoHeight) return;
  if (v.videoWidth !== lastVideoW || v.videoHeight !== lastVideoH) {
    lastVideoW = v.videoWidth;
    lastVideoH = v.videoHeight;
  }

  const p = params();
  const w = Math.max(1, parseInt(p.width || "160", 10));
  const h = Math.max(1, parseInt(p.height || "160", 10));
  const rotate = parseInt(p.rotate || "0", 10) || 0;
  const cropMode = p.crop_mode || "cover";
  const contrast = parseFloat(p.contrast || "1.0");

  const tmp = document.createElement("canvas");
  tmp.width = w;
  tmp.height = h;
  const tctx = tmp.getContext("2d");
  tctx.fillStyle = "#000";
  tctx.fillRect(0, 0, w, h);
  tctx.save();
  if (rotate) {
    tctx.translate(w / 2, h / 2);
    tctx.rotate((rotate * Math.PI) / 180);
    tctx.translate(-w / 2, -h / 2);
  }
  tctx.filter = Math.abs(contrast - 1.0) < 1e-6 ? "none" : `contrast(${Math.max(0.1, contrast) * 100}%)`;

  const sx = v.videoWidth;
  const sy = v.videoHeight;
  const scale = cropMode === "contain" ? Math.min(w / sx, h / sy) : Math.max(w / sx, h / sy);
  const dw = sx * scale;
  const dh = sy * scale;
  const dx = (w - dw) / 2;
  const dy = (h - dh) / 2;
  tctx.drawImage(v, dx, dy, dw, dh);
  tctx.restore();

  const out = $("dstCanvas");
  canvasSizeToElement(out);
  const octx = out.getContext("2d");
  octx.clearRect(0, 0, out.width, out.height);
  octx.fillStyle = "#0b1220";
  octx.fillRect(0, 0, out.width, out.height);
  drawFit(octx, tmp, out.width, out.height);
  updateScrubUI();
}

function renderProcessedFromVideoEl(v) {
  if (!v || v.readyState < 2) return;
  if (!v.videoWidth || !v.videoHeight) return;
  const p = params();
  const w = Math.max(1, parseInt(p.width || "160", 10));
  const h = Math.max(1, parseInt(p.height || "160", 10));
  const rotate = parseInt(p.rotate || "0", 10) || 0;
  const cropMode = p.crop_mode || "cover";
  const contrast = parseFloat(p.contrast || "1.0");

  const tmp = document.createElement("canvas");
  tmp.width = w;
  tmp.height = h;
  const tctx = tmp.getContext("2d");
  tctx.fillStyle = "#000";
  tctx.fillRect(0, 0, w, h);
  tctx.save();
  if (rotate) {
    tctx.translate(w / 2, h / 2);
    tctx.rotate((rotate * Math.PI) / 180);
    tctx.translate(-w / 2, -h / 2);
  }
  tctx.filter = Math.abs(contrast - 1.0) < 1e-6 ? "none" : `contrast(${Math.max(0.1, contrast) * 100}%)`;

  const sx = v.videoWidth;
  const sy = v.videoHeight;
  const scale = cropMode === "contain" ? Math.min(w / sx, h / sy) : Math.max(w / sx, h / sy);
  const dw = sx * scale;
  const dh = sy * scale;
  const dx = (w - dw) / 2;
  const dy = (h - dh) / 2;
  tctx.drawImage(v, dx, dy, dw, dh);
  tctx.restore();

  const out = $("dstCanvas");
  canvasSizeToElement(out);
  const octx = out.getContext("2d");
  octx.clearRect(0, 0, out.width, out.height);
  octx.fillStyle = "#0b1220";
  octx.fillRect(0, 0, out.width, out.height);
  drawFit(octx, tmp, out.width, out.height);
}

function renderBeforeFromVideoEl(v) {
  if (!v || v.readyState < 2) return;
  if (!v.videoWidth || !v.videoHeight) return;
  const c = $("srcCanvas");
  if (!c) return;
  canvasSizeToElement(c);
  const ctx = c.getContext("2d");
  ctx.clearRect(0, 0, c.width, c.height);
  ctx.fillStyle = "#0b1220";
  ctx.fillRect(0, 0, c.width, c.height);
  const vw = v.videoWidth;
  const vh = v.videoHeight;
  const scale = Math.min(c.width / vw, c.height / vh);
  const dw = vw * scale;
  const dh = vh * scale;
  const dx = (c.width - dw) / 2;
  const dy = (c.height - dh) / 2;
  ctx.drawImage(v, dx, dy, dw, dh);
}

function updateVideoPreviewDuringConvert(t) {
  const v = $("srcVideo");
  if (!v || !isFinite(v.duration) || v.duration <= 0) return;
  try {
    v.pause();
  } catch {
  }
  const target = Math.max(0, t || 0);
  if (Math.abs((v.currentTime || 0) - target) < 0.0005) {
    renderProcessedFromVideoEl(v);
    updateScrubUI();
    return;
  }
  const seq = ++_previewSeq;
  const on = () => {
    if (seq !== _previewSeq) return;
    renderProcessedFromVideoEl(v);
    updateScrubUI();
  };
  try {
    v.addEventListener("seeked", on, { once: true });
    v.currentTime = target;
  } catch {
  }
}

function requestVideoPreviewUpdate(outIndex, t) {
  _previewPending = { t: t || 0 };
  if (_previewRaf) return;
  _previewRaf = requestAnimationFrame(() => {
    _previewRaf = 0;
    const p = _previewPending;
    _previewPending = null;
    if (!p) return;
    if (!isConverting || mode !== "video") return;
    scheduleConvertPreview(p.t || 0);
    updateScrubUI();
  });
}

function syncSrcVideoToConvertTime(t) {
  const v = $("srcVideo");
  if (!v || !isFinite(v.duration) || v.duration <= 0) return;
  const dur = isFinite(v.duration) ? v.duration : 0;
  const target = Math.min(dur, Math.max(0, t || 0));
  const now = performance.now();
  if (Math.abs((_lastPreviewSyncT || 0) - target) < 0.0005 && now - (_lastPreviewSyncAt || 0) < 180) return;
  _lastPreviewSyncT = target;
  _lastPreviewSyncAt = now;
  try {
    v.pause();
  } catch {
  }
  try {
    v.currentTime = target;
  } catch {
  }
}

function renderAfterFromJpegBlob(blob) {
  const seq = ++_afterPreviewSeq;
  const out = $("dstCanvas");
  if (!out) return;
  canvasSizeToElement(out);
  const octx = out.getContext("2d");
  octx.clearRect(0, 0, out.width, out.height);
  octx.fillStyle = "#0b1220";
  octx.fillRect(0, 0, out.width, out.height);
  if (!blob) return;

  const w = out.width;
  const h = out.height;
  const drawImg = (img) => {
    if (seq !== _afterPreviewSeq) return;
    const sw = img.width || img.videoWidth || 1;
    const sh = img.height || img.videoHeight || 1;
    const scale = Math.min(w / sw, h / sh);
    const dw = sw * scale;
    const dh = sh * scale;
    const dx = (w - dw) / 2;
    const dy = (h - dh) / 2;
    octx.drawImage(img, dx, dy, dw, dh);
  };

  if (typeof createImageBitmap === "function") {
    createImageBitmap(blob)
      .then((bmp) => {
        try {
          drawImg(bmp);
        } finally {
          try {
            if (bmp && typeof bmp.close === "function") bmp.close();
          } catch {
          }
        }
      })
      .catch(() => {
        const url = URL.createObjectURL(blob);
        const img = new Image();
        img.onload = () => {
          try {
            drawImg(img);
          } finally {
            URL.revokeObjectURL(url);
          }
        };
        img.onerror = () => URL.revokeObjectURL(url);
        img.src = url;
      });
    return;
  }

  const url = URL.createObjectURL(blob);
  const img = new Image();
  img.onload = () => {
    try {
      drawImg(img);
    } finally {
      URL.revokeObjectURL(url);
    }
  };
  img.onerror = () => URL.revokeObjectURL(url);
  img.src = url;
}

function scheduleConvertPreview(t) {
  const now = performance.now();
  const fps = getInputFps();
  const r = getSelectedFrameRange();
  const startT = r.start / fps;
  const endT = r.end / fps;
  const rangeDur = Math.max(0, endT - startT);
  const rel = rangeDur > 0 ? (t - startT) / rangeDur : 0;
  const pct = Math.round(Math.max(0, Math.min(1, rel)) * 100);
  if (pct <= _convertPreviewPct && now - (_convertPreviewAt || 0) < 600) return;
  if (pct === _convertPreviewPct && now - (_convertPreviewAt || 0) < 250) return;
  _convertPreviewPct = pct;
  _convertPreviewAt = now;
  updateVideoPreviewDuringConvert(t);
}

function showImageAt(index) {
  if (!images.length) return;
  const next = Math.max(0, Math.min(images.length - 1, Number(index) || 0));
  imageIndex = next;

  const srcImg = $("srcImg");
  const srcHint = $("srcHint");
  const srcVideo = $("srcVideo");
  const srcCanvas = $("srcCanvas");
  srcVideo.pause();
  srcVideo.style.display = "none";
  srcVideo.removeAttribute("src");
  srcVideo.load();
  if (srcCanvas) srcCanvas.style.display = "none";

  if (imageObjUrl) URL.revokeObjectURL(imageObjUrl);
  imageObjUrl = URL.createObjectURL(images[imageIndex]);
  srcImg.src = imageObjUrl;
  srcImg.style.display = "block";
  srcHint.style.display = "none";

  srcImg.onload = async () => {
    try {
      const bmp = await createImageBitmap(images[imageIndex]);
      renderImageAfter(bmp);
    } catch {
    }
    updateScrubUI();
    setPlayButton();
  };
}
function waitOnce(el, eventName, timeoutMs) {
  return new Promise((resolve, reject) => {
    let done = false;
    const on = () => {
      if (done) return;
      done = true;
      cleanup();
      resolve();
    };
    const timer = setTimeout(() => {
      if (done) return;
      done = true;
      cleanup();
      reject(new Error(`Timeout waiting for ${eventName}`));
    }, timeoutMs);
    const cleanup = () => {
      clearTimeout(timer);
      try {
        el.removeEventListener(eventName, on);
      } catch {
      }
    };
    el.addEventListener(eventName, on, { once: true });
  });
}

async function ensureVideoReady(v) {
  if (isFinite(v.duration) && v.duration > 0) return;
  await waitOnce(v, "loadedmetadata", 8000);
}

async function seekVideo(v, t) {
  const target = Math.max(0, t);
  if (Math.abs((v.currentTime || 0) - target) < 0.0005) return;
  v.currentTime = target;
  await waitOnce(v, "seeked", 8000);
}

async function renderVideoToJpegBlob(v, p) {
  const w = Math.max(1, parseInt(p.width || "160", 10));
  const h = Math.max(1, parseInt(p.height || "160", 10));
  const rotate = parseInt(p.rotate || "0", 10) || 0;
  const cropMode = p.crop_mode || "cover";
  const contrast = parseFloat(p.contrast || "1.0");
  const quality = Math.min(100, Math.max(1, parseInt(p.quality || "85", 10)));
  const capKb = Math.max(0, parseInt(p.max_jpeg_kb || "0", 10) || 0);
  const maxBytes = capKb > 0 ? capKb * 1024 : 0;

  const useOffscreen = typeof OffscreenCanvas !== "undefined";
  const canvas = useOffscreen ? new OffscreenCanvas(w, h) : document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, w, h);

  ctx.save();
  if (rotate) {
    ctx.translate(w / 2, h / 2);
    ctx.rotate((rotate * Math.PI) / 180);
    ctx.translate(-w / 2, -h / 2);
  }
  ctx.filter = Math.abs(contrast - 1.0) < 1e-6 ? "none" : `contrast(${Math.max(0.1, contrast) * 100}%)`;

  const sx = v.videoWidth || 1;
  const sy = v.videoHeight || 1;
  const scale = cropMode === "contain" ? Math.min(w / sx, h / sy) : Math.max(w / sx, h / sy);
  const dw = sx * scale;
  const dh = sy * scale;
  const dx = (w - dw) / 2;
  const dy = (h - dh) / 2;
  ctx.drawImage(v, dx, dy, dw, dh);
  ctx.restore();

  const encode = async (q) => {
    if (typeof canvas.convertToBlob === "function") {
      return await canvas.convertToBlob({ type: "image/jpeg", quality: q / 100 });
    }
    return await new Promise((resolve) => canvas.toBlob((b) => resolve(b), "image/jpeg", q / 100));
  };

  if (maxBytes > 0) {
    let lo = 1;
    let hi = quality;
    let best = null;
    for (let i = 0; i < 7 && lo <= hi; i++) {
      const mid = Math.floor((lo + hi) / 2);
      const b = await encode(mid);
      if (b && b.size <= maxBytes) {
        best = b;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    return best ? best : await encode(1);
  }
  return await encode(quality);
}

async function waitVideoFrameReady(v, timeoutMs) {
  const t0 = performance.now();
  while (true) {
    if (v && v.readyState >= 2 && (v.videoWidth || 0) > 0 && (v.videoHeight || 0) > 0) return;
    if (performance.now() - t0 > (timeoutMs || 2000)) throw new Error("Video frame not ready");
    await new Promise((r) => requestAnimationFrame(r));
  }
}

async function captureVideoFrameBitmap(v) {
  await waitVideoFrameReady(v, 2500);
  const vw = v.videoWidth || 0;
  const vh = v.videoHeight || 0;
  if (!vw || !vh) throw new Error("No video size");
  if (typeof OffscreenCanvas !== "undefined") {
    const c = new OffscreenCanvas(vw, vh);
    const ctx = c.getContext("2d", { alpha: false });
    ctx.drawImage(v, 0, 0, vw, vh);
    if (typeof c.transferToImageBitmap === "function") return c.transferToImageBitmap();
    if (typeof createImageBitmap === "function") return await createImageBitmap(c);
    throw new Error("No way to make ImageBitmap");
  }
  if (typeof document !== "undefined") {
    const c = document.createElement("canvas");
    c.width = vw;
    c.height = vh;
    const ctx = c.getContext("2d");
    ctx.drawImage(v, 0, 0, vw, vh);
    if (typeof createImageBitmap === "function") return await createImageBitmap(c);
  }
  throw new Error("Canvas capture not supported");
}

function getVideoParallelism(p, count) {
  const n = Math.max(1, Math.floor(parseFloat(p.video_parallel || "1") || 1));
  const hc = Math.max(1, navigator.hardwareConcurrency || 4);
  return Math.max(1, Math.min(n, 8, hc, count));
}

function makeHiddenVideo(src) {
  const v = document.createElement("video");
  v.muted = true;
  v.playsInline = true;
  v.preload = "auto";
  v.style.display = "none";
  v.src = src;
  v.load();
  document.body.appendChild(v);
  return v;
}

class AsyncSemaphore {
  constructor(max) {
    this.max = Math.max(1, max | 0);
    this.cur = 0;
    this.q = [];
  }

  acquire() {
    if (this.cur < this.max) {
      this.cur++;
      return Promise.resolve();
    }
    return new Promise((resolve) => this.q.push(resolve));
  }

  release() {
    this.cur = Math.max(0, this.cur - 1);
    const next = this.q.shift();
    if (next) {
      this.cur++;
      next();
    }
  }
}


async function loadPreview(pickSeq) {
  if (pickSeq !== _pickSeq) return;
  const mode = detectMode(files);
  clearSrc();
  if (pickSeq !== _pickSeq) return;

  const srcVideo = $("srcVideo");
  const srcImg = $("srcImg");
  const srcHint = $("srcHint");
  const srcCanvas = $("srcCanvas");
  srcVideo.pause();
  srcVideo.removeAttribute("src");
  srcVideo.load();
  srcVideo.style.display = "none";
  srcImg.style.display = "none";
  if (srcCanvas) srcCanvas.style.display = "none";
  srcHint.style.display = "block";
  if (pickSeq !== _pickSeq) return;

  const out = $("dstCanvas");
  canvasSizeToElement(out);
  const octx = out.getContext("2d");
  octx.clearRect(0, 0, out.width, out.height);
  octx.fillStyle = "#0b1220";
  octx.fillRect(0, 0, out.width, out.height);
  octx.fillStyle = "#9fb0c0";
  octx.font = "14px system-ui";
  octx.textAlign = "center";
  octx.textBaseline = "middle";
  octx.fillText("選擇檔案以顯示 After", out.width / 2, out.height / 2);

  if (mode === "photo") {
    if (!images.length) return;
    const ifr = $("inputFps");
    const ifn = $("inputFpsNum");
    if (ifr) ifr.value = String(_lastPhotoInputFps);
    if (ifn) ifn.value = String(_lastPhotoInputFps);
    updateFpsInfo();
    imageIndex = 0;
    showImageAt(0);
    _rangeReset = true;
    updateVideoFrameDomain();
    setPlayButton();
    return;
  }

  if (mode === "video") {
    const f = files[0];
    srcUrl = URL.createObjectURL(f);
    srcVideo.src = srcUrl;
    const tv = ensureThumbVideo();
    tv.src = srcUrl;
    tv.load();
    srcVideo.style.display = "block";
    srcHint.style.display = "none";
    srcVideo.onloadeddata = () => renderProcessedFromVideo();
    srcVideo.onplay = () => {
      isPlaying = true;
      setPlayButton();
      startVideoLoop();
    };
    srcVideo.onpause = () => {
      stopVideoLoop();
      renderProcessedFromVideo();
      isPlaying = false;
      setPlayButton();
    };
    srcVideo.onseeked = () => renderProcessedFromVideo();
    srcVideo.ontimeupdate = () => renderProcessedFromVideo();
    srcVideo.onloadedmetadata = async () => {
      if (pickSeq !== _pickSeq) return;
      try {
        await ensureVideoReady(tv);
        if (pickSeq !== _pickSeq) return;
        const fps = await detectVideoFpsFromVideo(tv);
        if (pickSeq !== _pickSeq) return;
        _videoDetectedFps = fps > 0 ? Math.max(1, Math.round(fps * 100) / 100) : 0;
        _lastVideoInputFps = _videoDetectedFps > 0 ? _videoDetectedFps : _lastVideoInputFps;
      } catch {
        if (pickSeq !== _pickSeq) return;
        _videoDetectedFps = 0;
      }
      const ifr = $("inputFps");
      const ifn = $("inputFpsNum");
      if (ifr) ifr.value = String(_lastVideoInputFps);
      if (ifn) ifn.value = String(_lastVideoInputFps);
      updateFpsInfo();
      _rangeReset = true;
      updateVideoFrameDomain();
      updateScrubUI();
    };
    updateScrubUI();
    setPlayButton();
  }
}

async function run() {
  resetProgress();
  if (mode === "photo") {
    $("run").disabled = true;
    try {
      if (!images.length) throw new Error("沒有圖片可處理");
      const p = params();
      const blobs = [];
      let maxBytes = 0;
      const step = Math.max(1, parseInt(p.frame_step || "1", 10));
      const totalFrames = images.length;
      let startFrame = Math.max(0, Math.floor(parseFloat(p.video_start_frame || "0") || 0));
      let endFrameRaw = Math.floor(parseFloat(p.video_end_frame || "0") || 0);
      const endIsToEnd = endFrameRaw <= 0;
      let endFrame = endIsToEnd ? totalFrames - 1 : Math.max(0, endFrameRaw);
      startFrame = Math.min(totalFrames - 1, startFrame);
      endFrame = Math.min(totalFrames - 1, endFrame);
      if (endFrame < startFrame) endFrame = startFrame;

      const rangeFrames = endFrame - startFrame + 1;
      const total = Math.max(1, Math.floor((rangeFrames - 1) / step) + 1);
      const canParallel =
        typeof Worker !== "undefined" &&
        typeof OffscreenCanvas !== "undefined" &&
        typeof createImageBitmap === "function" &&
        total > 1;
      let done = 0;
      if (canParallel) {
        const hc = Math.max(1, navigator.hardwareConcurrency || 4);
        const poolSize = Math.min(8, hc, total);
        const pool = new PhotoWorkerPool(poolSize);
        try {
          const w = Math.max(1, parseInt(p.width || "160", 10));
          const h = Math.max(1, parseInt(p.height || "160", 10));
          const rotate = parseInt(p.rotate || "0", 10) || 0;
          const cropMode = p.crop_mode || "cover";
          const contrast = parseFloat(p.contrast || "1.0");
          const quality = Math.min(100, Math.max(1, parseInt(p.quality || "85", 10)));
          const capKb = Math.max(0, parseInt(p.max_jpeg_kb || "0", 10) || 0);
          const maxBytesCap = capKb > 0 ? capKb * 1024 : 0;
          const indices = [];
          for (let i = startFrame; i <= endFrame; i += step) indices.push(i);
          const out = new Array(indices.length);
          const promises = indices.map((srcIndex, outIndex) =>
            pool
              .exec({ file: images[srcIndex], w, h, rotate, cropMode, contrast, quality, maxBytes: maxBytesCap })
              .then((blob) => {
                out[outIndex] = blob;
                if (blob.size > maxBytes) maxBytes = blob.size;
                done++;
                if (done % 10 === 0 || done === total) {
                  showImageAt(srcIndex);
                  updateScrubUI();
                }
                setProgress(Math.round((done / total) * 90));
              })
          );
          await Promise.all(promises);
          for (const b of out) blobs.push(b);
        } finally {
          pool.terminate();
        }
      } else {
        for (let i = startFrame; i <= endFrame; i += step) {
          const blob = await renderImageToJpegBlob(images[i], p);
          blobs.push(blob);
          if (blob.size > maxBytes) maxBytes = blob.size;
          done++;
          if (done % 10 === 0 || i + step > endFrame) {
            showImageAt(i);
            updateScrubUI();
          }
          setProgress(Math.round((done / total) * 90));
        }
      }
      jpegBlobs = blobs;
      jpkBlob = await buildJpk(blobs);
      setProgress(100);
      $("downloadJpk").disabled = false;
      $("downloadAll").disabled = false;
      $("result").textContent = `Mode: photo\nCount: ${blobs.length}\nInput FPS: ${getInputFps()}\nStep: every ${step} frames\nRange: ${startFrame}..${endFrame} (of ${totalFrames - 1})\nMax JPEG bytes: ${maxBytes}\nMax JPEG cap: ${Math.max(0, parseInt(p.max_jpeg_kb || "0", 10) || 0) ? `${Math.max(0, parseInt(p.max_jpeg_kb || "0", 10) || 0)}KB` : "—"}\n\n已產生 output.jpk，可下載或逐張下載 JPEG。`;
    } catch (e) {
      setProgress(0);
      $("result").textContent = String(e && e.message ? e.message : e);
    } finally {
      $("run").disabled = mode === "unknown" || mode === "—";
      setPlayButton();
    }
    return;
  }

  if (mode === "video") {
    $("run").disabled = true;
    isConverting = true;
    stopPlayback();
    stopVideoLoop();
    const srcVideoEl = $("srcVideo");
    if (srcVideoEl) srcVideoEl.style.display = "block";
    const v = $("srcVideo");
    try {
      if (!v || !isFinite(v.readyState)) throw new Error("沒有影片可處理");
      v.pause();
      await ensureVideoReady(v);
      const dur = isFinite(v.duration) ? v.duration : 0;
      if (!dur || dur <= 0) throw new Error("無法取得影片長度（瀏覽器不支援此格式或尚未載入完成）");

      const p = params();
      const fps = getInputFps();
      const step = Math.max(1, parseInt(p.frame_step || "1", 10));
      const totalFrames = computeTotalFrames(dur, fps);
      let startFrame = Math.max(0, Math.floor(parseFloat(p.video_start_frame || "0") || 0));
      let endFrameRaw = Math.floor(parseFloat(p.video_end_frame || "0") || 0);
      const endIsToEnd = endFrameRaw <= 0;
      let endFrame = endIsToEnd ? totalFrames - 1 : Math.max(0, endFrameRaw);
      startFrame = Math.min(totalFrames - 1, startFrame);
      endFrame = Math.min(totalFrames - 1, endFrame);
      if (endFrame < startFrame) endFrame = startFrame;

      const rangeFrames = endFrame - startFrame + 1;
      const count = Math.max(1, Math.floor((rangeFrames - 1) / step) + 1);

      const blobs = [];
      let maxBytes = 0;
      $("result").textContent = `Mode: video\nFrames: 0/${count}\nInput FPS: ${fps}\nStep: every ${step} frames\nRange: ${startFrame}..${endFrame} (of ${totalFrames - 1})\n\n抽幀中...`;
      setProgress(1);
      const parallel = getVideoParallelism(p, count);
      const indices = [];
      for (let i = 0; i < count; i++) {
        const frame = Math.min(endFrame, startFrame + i * step);
        indices.push({ outIndex: i, frame, t: frame / fps });
      }
      const vids = [];
      const procPoolSize = Math.min(8, Math.max(1, navigator.hardwareConcurrency || 4), count);
      const procPool = new PhotoWorkerPool(procPoolSize);
      const inFlight = new AsyncSemaphore(procPoolSize * 2);
      const capKb = Math.max(0, parseInt(p.max_jpeg_kb || "0", 10) || 0);
      const maxBytesCap = capKb > 0 ? capKb * 1024 : 0;
      try {
        for (let i = 0; i < parallel; i++) vids.push(makeHiddenVideo(v.src));
        await Promise.all(vids.map((vv) => ensureVideoReady(vv)));
        const buckets = Array.from({ length: parallel }, () => []);
        for (let i = 0; i < indices.length; i++) buckets[i % parallel].push(indices[i]);
        const out = new Array(indices.length);
        let done = 0;
        const pickSeq = _pickSeq;
        const tasks = [];
        const runners = buckets.map((list, wi) =>
          (async () => {
            const vv = vids[wi];
            for (const item of list) {
              if (pickSeq !== _pickSeq) throw new Error("來源已變更");
              await seekVideo(vv, item.t);
              await inFlight.acquire();
              const w = Math.max(1, parseInt(p.width || "160", 10));
              const h = Math.max(1, parseInt(p.height || "160", 10));
              const rotate = parseInt(p.rotate || "0", 10) || 0;
              const cropMode = p.crop_mode || "cover";
              const contrast = parseFloat(p.contrast || "1.0");
              const quality = Math.min(100, Math.max(1, parseInt(p.quality || "85", 10)));
              let bmp = null;
              try {
                bmp = await captureVideoFrameBitmap(vv);
              } catch (e) {
                const blob = await renderVideoToJpegBlob(vv, p);
                out[item.outIndex] = blob;
                if (blob.size > maxBytes) maxBytes = blob.size;
                done++;
                _convertVideoT = Math.max(_convertVideoT || 0, item.t || 0);
                _convertVideoFrame = Math.max(_convertVideoFrame || 0, item.frame || 0);
                if (done % 5 === 0 || done === count) {
                  $("result").textContent = `Mode: video\nFrames: ${done}/${count}\nLast: frame ${item.frame}  (t=${item.t.toFixed(2)}s / ${dur.toFixed(2)}s)\nDecode parallel: ${parallel}\nProcess workers: ${procPoolSize}\nMax JPEG bytes: ${maxBytes}`;
                  updateScrubUI();
                  requestVideoPreviewUpdate(item.outIndex, _convertVideoT);
                }
                setProgress(Math.round((done / count) * 90));
                inFlight.release();
                continue;
              }
              const task = procPool
                .execTransfer({ bitmap: bmp, w, h, rotate, cropMode, contrast, quality, maxBytes: maxBytesCap }, [bmp])
                .then((blob) => {
                  out[item.outIndex] = blob;
                  if (blob.size > maxBytes) maxBytes = blob.size;
                  done++;
                  _convertVideoT = Math.max(_convertVideoT || 0, item.t || 0);
                  _convertVideoFrame = Math.max(_convertVideoFrame || 0, item.frame || 0);
                  if (done % 5 === 0 || done === count) {
                    $("result").textContent = `Mode: video\nFrames: ${done}/${count}\nLast: frame ${item.frame}  (t=${item.t.toFixed(2)}s / ${dur.toFixed(2)}s)\nDecode parallel: ${parallel}\nProcess workers: ${procPoolSize}\nMax JPEG bytes: ${maxBytes}`;
                    updateScrubUI();
                    requestVideoPreviewUpdate(item.outIndex, _convertVideoT);
                  }
                  setProgress(Math.round((done / count) * 90));
                })
                .finally(() => {
                  inFlight.release();
                });
              tasks.push(task);
            }
          })()
        );
        await Promise.all(runners);
        await Promise.all(tasks);
        for (const b of out) blobs.push(b);
      } finally {
        procPool.terminate();
        for (const vv of vids) {
          try {
            vv.pause();
            vv.removeAttribute("src");
            vv.load();
            vv.remove();
          } catch {
          }
        }
      }
      jpegBlobs = blobs;
      jpkBlob = await buildJpk(blobs);
      setProgress(100);
      $("downloadJpk").disabled = false;
      $("downloadAll").disabled = false;
      $("result").textContent = `Mode: video\nCount: ${blobs.length}\nMax JPEG bytes: ${maxBytes}\nMax JPEG cap: ${capKb ? `${capKb}KB` : "—"}\n\n已產生 output.jpk，可下載或逐張下載 JPEG。`;
    } catch (e) {
      setProgress(0);
      $("result").textContent = String(e && e.message ? e.message : e);
    } finally {
      isConverting = false;
      _convertVideoT = 0;
      _convertVideoFrame = 0;
      $("run").disabled = mode === "unknown" || mode === "—";
      renderProcessedFromVideo();
      setPlayButton();
      if (srcVideoEl) srcVideoEl.style.display = "block";
    }
    return;
  }

  $("result").textContent = "Unsupported";
}

$("run").addEventListener("click", run);
["cropMode", "width", "height", "rotate", "contrast"].forEach((id) =>
  $(id).addEventListener("input", () => {
    if (mode === "photo") showImageAt(imageIndex);
    if (mode === "video") renderProcessedFromVideo();
  })
);

$("scrub").addEventListener("input", (e) => {
  stopPlayback();
  if (mode === "photo") {
    showImageAt(parseInt(e.target.value || "0", 10));
    return;
  }
  if (mode === "video") {
    const v = $("srcVideo");
    const dur = v && isFinite(v.duration) ? v.duration : 0;
    if (dur > 0) {
      const pct = Math.max(0, Math.min(100, parseInt(e.target.value || "0", 10)));
      const fps = getInputFps();
      const r = getSelectedFrameRange();
      const startT = r.start / fps;
      const endT = r.end / fps;
      const rangeDur = Math.max(0, endT - startT);
      v.currentTime = startT + (pct / 100) * rangeDur;
    }
    updateScrubUI();
  }
});

$("togglePlay").addEventListener("click", () => {
  if (isConverting) return;
  if (isPlaying) {
    stopPlayback();
    return;
  }
  startPlayback();
});

$("pickFiles").addEventListener("click", () => $("fileInput").click());
$("pickFolder").addEventListener("click", () => $("folderInput").click());
$("fileInput").addEventListener("change", (e) => {
  setPicked(Array.from(e.target.files || []));
  e.target.value = "";
});
$("folderInput").addEventListener("change", (e) => {
  setPicked(Array.from(e.target.files || []));
  e.target.value = "";
});

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

$("downloadJpk").addEventListener("click", () => {
  if (!jpkBlob) return;
  downloadBlob(jpkBlob, "output.jpk");
});

$("downloadAll").addEventListener("click", async () => {
  if (!jpegBlobs.length) return;
  $("downloadAll").disabled = true;
  try {
    setProgress(95);
    $("result").textContent = $("result").textContent + "\n\n正在打包 JPEG.zip ...";
    const zipBlob = await buildZipFromJpegs(jpegBlobs);
    downloadBlob(zipBlob, "output.zip");
  } catch (e) {
    $("result").textContent = String(e && e.message ? e.message : e);
  } finally {
    $("downloadAll").disabled = false;
  }
});

setPicked([]);
setPlayButton();
initRanges();
initVideoRange();
window.addEventListener("resize", () => {
  if (mode === "photo") showImageAt(imageIndex);
  if (mode === "video") renderProcessedFromVideo();
});
