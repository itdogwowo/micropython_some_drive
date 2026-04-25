import { buildJpk } from "./jpk.js";

const $ = (id) => document.getElementById(id);

const state = {
  files: [],
  imageFiles: [],
  jpegBlobs: [],
  previewBitmap: null,
  view: {
    scale: 1.0,
    offsetX: 0,
    offsetY: 0,
    dragging: false,
    dragX: 0,
    dragY: 0,
  },
};

function setProgress(p) {
  const pct = Math.max(0, Math.min(100, p));
  $("barFill").style.width = pct + "%";
}

function setResult(text) {
  $("result").textContent = text || "";
}

function params() {
  return {
    cropMode: $("cropMode").value,
    width: Math.max(1, parseInt($("width").value || "160", 10)),
    height: Math.max(1, parseInt($("height").value || "160", 10)),
    rotate: parseInt($("rotate").value || "0", 10),
    contrast: Math.max(0.1, parseFloat($("contrast").value || "1.0")),
    quality: Math.min(100, Math.max(1, parseInt($("quality").value || "85", 10))),
  };
}

function isImageFile(file) {
  const name = (file.name || "").toLowerCase();
  return (
    name.endsWith(".png") ||
    name.endsWith(".jpg") ||
    name.endsWith(".jpeg") ||
    name.endsWith(".bmp") ||
    name.endsWith(".webp") ||
    name.endsWith(".tif") ||
    name.endsWith(".tiff") ||
    (file.type || "").startsWith("image/")
  );
}

function naturalKey(s) {
  return s
    .split(/(\d+)/)
    .map((t) => (t.match(/^\d+$/) ? parseInt(t, 10) : t.toLowerCase()));
}

function naturalSort(a, b) {
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

function setPicked(list) {
  state.files = list;
  state.imageFiles = list.filter(isImageFile);
  state.imageFiles.sort((a, b) => naturalSort(a.webkitRelativePath || a.name, b.webkitRelativePath || b.name));
  $("pickedCount").textContent = String(list.length);
  $("run").disabled = state.imageFiles.length === 0;
  $("downloadJpk").disabled = true;
  $("downloadAll").disabled = true;
  state.jpegBlobs = [];
  setProgress(0);
  setResult("");
  loadPreview();
}

function addFiles(fileList) {
  const next = state.files.concat(Array.from(fileList || []));
  setPicked(next);
}

async function loadPreview() {
  const canvas = $("preview");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  state.previewBitmap = null;
  state.view.scale = 1.0;
  state.view.offsetX = 0;
  state.view.offsetY = 0;

  if (!state.imageFiles.length) {
    drawOverlay("請選擇圖片以預覽");
    return;
  }

  const file = state.imageFiles[0];
  const url = URL.createObjectURL(file);
  try {
    const bmp = await createImageBitmap(file);
    state.previewBitmap = bmp;
    renderPreview();
  } catch {
    drawOverlay("無法預覽此檔案");
  } finally {
    URL.revokeObjectURL(url);
  }
}

function drawOverlay(text) {
  const canvas = $("preview");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#9fb0c0";
  ctx.font = "14px system-ui";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, canvas.width / 2, canvas.height / 2);
}

function renderPreview() {
  const bmp = state.previewBitmap;
  if (!bmp) return;
  const canvas = $("preview");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const { scale, offsetX, offsetY } = state.view;
  const w = bmp.width * scale;
  const h = bmp.height * scale;
  const x = (canvas.width - w) / 2 + offsetX;
  const y = (canvas.height - h) / 2 + offsetY;
  ctx.drawImage(bmp, x, y, w, h);

  const p = params();
  const outAspect = p.width / p.height;
  const boxW = Math.min(canvas.width * 0.8, canvas.height * 0.8 * outAspect);
  const boxH = boxW / outAspect;
  const bx = (canvas.width - boxW) / 2;
  const by = (canvas.height - boxH) / 2;
  ctx.save();
  ctx.strokeStyle = "#6aa6ff";
  ctx.lineWidth = 2;
  ctx.strokeRect(bx, by, boxW, boxH);
  ctx.restore();
}

function clamp(n, min, max) {
  return Math.max(min, Math.min(max, n));
}

function applyContrast(imageData, contrast) {
  if (Math.abs(contrast - 1.0) < 1e-6) return imageData;
  const d = imageData.data;
  for (let i = 0; i < d.length; i += 4) {
    d[i] = clamp((d[i] - 128) * contrast + 128, 0, 255);
    d[i + 1] = clamp((d[i + 1] - 128) * contrast + 128, 0, 255);
    d[i + 2] = clamp((d[i + 2] - 128) * contrast + 128, 0, 255);
  }
  return imageData;
}

function drawToOutputCanvas(bmp, p) {
  const out = new OffscreenCanvas(p.width, p.height);
  const ctx = out.getContext("2d", { willReadFrequently: true });
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, p.width, p.height);

  ctx.save();
  if (p.rotate) {
    ctx.translate(p.width / 2, p.height / 2);
    ctx.rotate((p.rotate * Math.PI) / 180);
    ctx.translate(-p.width / 2, -p.height / 2);
  }

  if (p.cropMode === "contain") {
    const scale = Math.min(p.width / bmp.width, p.height / bmp.height);
    const w = bmp.width * scale;
    const h = bmp.height * scale;
    const x = (p.width - w) / 2;
    const y = (p.height - h) / 2;
    ctx.drawImage(bmp, x, y, w, h);
  } else {
    const scale = Math.max(p.width / bmp.width, p.height / bmp.height);
    const w = bmp.width * scale;
    const h = bmp.height * scale;
    const x = (p.width - w) / 2;
    const y = (p.height - h) / 2;
    ctx.drawImage(bmp, x, y, w, h);
  }
  ctx.restore();

  if (Math.abs(p.contrast - 1.0) >= 1e-6) {
    const img = ctx.getImageData(0, 0, p.width, p.height);
    applyContrast(img, p.contrast);
    ctx.putImageData(img, 0, 0);
  }

  return out;
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

async function runImages() {
  setProgress(0);
  setResult("");
  $("run").disabled = true;
  $("downloadJpk").disabled = true;
  $("downloadAll").disabled = true;

  try {
    if (!state.imageFiles.length) throw new Error("沒有圖片可處理");
    const p = params();
    const blobs = [];
    for (let i = 0; i < state.imageFiles.length; i++) {
      const file = state.imageFiles[i];
      const bmp = await createImageBitmap(file);
      const canvas = drawToOutputCanvas(bmp, p);
      const jpeg = await canvas.convertToBlob({
        type: "image/jpeg",
        quality: p.quality / 100,
      });
      blobs.push(jpeg);
      const pct = ((i + 1) / state.imageFiles.length) * 80;
      setProgress(pct);
    }
    state.jpegBlobs = blobs;
    const maxBytes = Math.max(...(await Promise.all(blobs.map(async (b) => (await b.arrayBuffer()).byteLength))));
    const jpk = await buildJpk(blobs);
    state.jpkBlob = jpk;
    setProgress(100);
    $("downloadJpk").disabled = false;
    $("downloadAll").disabled = false;
    setResult(`Mode: photo\nCount: ${blobs.length}\nMax JPEG bytes: ${maxBytes}\n\n可下載 output.jpk 或逐張 JPEG`);
  } catch (e) {
    setProgress(0);
    setResult(String(e && e.message ? e.message : e));
  } finally {
    $("run").disabled = state.imageFiles.length === 0;
  }
}

$("run").addEventListener("click", runImages);

$("downloadJpk").addEventListener("click", async () => {
  if (!state.jpkBlob) return;
  downloadBlob(state.jpkBlob, "output.jpk");
});

$("downloadAll").addEventListener("click", async () => {
  if (!state.jpegBlobs.length) return;
  const digits = Math.max(3, String(state.jpegBlobs.length - 1).length);
  for (let i = 0; i < state.jpegBlobs.length; i++) {
    downloadBlob(state.jpegBlobs[i], String(i).padStart(digits, "0") + ".jpeg");
    await new Promise((r) => setTimeout(r, 80));
  }
});

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

["width", "height", "cropMode", "rotate", "contrast"].forEach((id) => {
  $(id).addEventListener("change", renderPreview);
});

const canvas = $("preview");
canvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  const delta = Math.sign(e.deltaY);
  const factor = delta > 0 ? 0.9 : 1.1;
  state.view.scale = clamp(state.view.scale * factor, 0.1, 10);
  renderPreview();
});

canvas.addEventListener("mousedown", (e) => {
  state.view.dragging = true;
  state.view.dragX = e.clientX;
  state.view.dragY = e.clientY;
});
window.addEventListener("mouseup", () => (state.view.dragging = false));
window.addEventListener("mousemove", (e) => {
  if (!state.view.dragging) return;
  const dx = e.clientX - state.view.dragX;
  const dy = e.clientY - state.view.dragY;
  state.view.dragX = e.clientX;
  state.view.dragY = e.clientY;
  state.view.offsetX += dx;
  state.view.offsetY += dy;
  renderPreview();
});

setPicked([]);

