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

async function processFile(file, params) {
  const bmp = await createImageBitmap(file);
  try {
    const canvas = drawToOutputCanvas(bmp, params);
    const blob = await canvas.convertToBlob({
      type: "image/jpeg",
      quality: params.quality / 100,
    });
    const buffer = await blob.arrayBuffer();
    return buffer;
  } finally {
    try {
      bmp.close();
    } catch {}
  }
}

self.onmessage = async (e) => {
  const port = e.data && e.data.port;
  if (!port) return;
  try {
    const buffer = await processFile(e.data.file, e.data.params);
    port.postMessage({ ok: true, buffer }, [buffer]);
  } catch (err) {
    port.postMessage({ ok: false, error: String(err && err.message ? err.message : err) });
  } finally {
    try {
      port.close();
    } catch {}
  }
};
