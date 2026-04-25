export function uint32le(n) {
  const b = new Uint8Array(4);
  const v = n >>> 0;
  b[0] = v & 0xff;
  b[1] = (v >>> 8) & 0xff;
  b[2] = (v >>> 16) & 0xff;
  b[3] = (v >>> 24) & 0xff;
  return b;
}

export async function buildJpk(jpegBlobs) {
  const parts = [];
  parts.push(new TextEncoder().encode("JPK1"));

  const sizes = [];
  let maxSize = 0;
  for (const blob of jpegBlobs) {
    const buf = new Uint8Array(await blob.arrayBuffer());
    sizes.push(buf.length);
    if (buf.length > maxSize) maxSize = buf.length;
  }

  parts.push(uint32le(jpegBlobs.length));
  parts.push(uint32le(maxSize));
  parts.push(uint32le(0));

  for (let i = 0; i < jpegBlobs.length; i++) {
    const blob = jpegBlobs[i];
    const buf = new Uint8Array(await blob.arrayBuffer());
    parts.push(uint32le(buf.length));
    parts.push(buf);
  }

  return new Blob(parts, { type: "application/octet-stream" });
}

