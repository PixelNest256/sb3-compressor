/* SB3 Media Compressor — browser edition.
 * Compresses the images and sounds packed inside a Scratch / TurboWarp .sb3
 * file, then repacks the zip. Everything runs in the tab: no upload, no
 * server, no Python.
 *
 *   images : PNG  -> palette + lossy quantisation (indexed PNG, our own writer)
 *            JPEG -> re-encode through a canvas at a chosen quality
 *   vector : SVG  -> drop comments / metadata / editor cruft, round path data
 *   audio  : WAV  -> resample, downmix, re-encode PCM (pure JS, worker-safe)
 *            MP3  -> strip ID3v2 / ID3v1 tags (no re-encode in the browser)
 *
 * Media keeps its original file name and format, so project.json never has to
 * change: the Scratch VM loads a costume/sound by its `md5ext` name and does
 * not re-hash the bytes.
 */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.MEDIA = api;
})(typeof self !== "undefined" ? self : globalThis, function () {
  "use strict";

  // ------------------------------------------------------------------
  // small helpers

  const isU8 = (v) => v instanceof Uint8Array;
  const asU8 = (v) => (isU8(v) ? v : new Uint8Array(v));

  function concatBytes(parts) {
    let total = 0;
    for (const p of parts) total += p.length;
    const out = new Uint8Array(total);
    let at = 0;
    for (const p of parts) { out.set(p, at); at += p.length; }
    return out;
  }

  function groupDigits(text) {
    const parts = String(text).split(".");
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return parts.join(".");
  }

  function humanSize(n) {
    const units = ["B", "KB", "MB", "GB"];
    for (const unit of units) {
      if (Math.abs(n) < 1024 || unit === "GB") {
        if (unit === "B") return groupDigits(String(Math.trunc(n))) + " B";
        return groupDigits(n.toFixed(1)) + " " + unit;
      }
      n /= 1024;
    }
    return groupDigits(n.toFixed(1)) + " GB";
  }

  function readU32(b, o) {
    return (b[o] * 0x1000000) + (b[o + 1] * 0x10000) + (b[o + 2] * 0x100) + b[o + 3];
  }
  function readStr(b, o, n) {
    let s = "";
    for (let i = 0; i < n; i++) s += String.fromCharCode(b[o + i]);
    return s;
  }

  function extOf(name) {
    const dot = name.lastIndexOf(".");
    return dot >= 0 ? name.slice(dot + 1).toLowerCase() : "";
  }

  function baseName(name) {
    return String(name || "").split(/[\\/]/).pop() || "project.sb3";
  }

  function defaultOutputName(inPath) {
    const base = baseName(inPath);
    const dot = base.lastIndexOf(".");
    const root = dot > 0 ? base.slice(0, dot) : base;
    let ext = dot > 0 ? base.slice(dot).toLowerCase() : ".sb3";
    if (ext !== ".sb3") ext = ".sb3";
    return root + "_media" + ext;
  }

  // ------------------------------------------------------------------
  // CRC32 (for our PNG writer) and DEFLATE via CompressionStream

  const CRC_TABLE = (() => {
    const t = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
      t[n] = c >>> 0;
    }
    return t;
  })();

  function crc32(bytes, start, end) {
    let c = 0xFFFFFFFF;
    for (let i = start; i < end; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  }

  async function deflateZlib(u8) {
    if (typeof CompressionStream === "undefined") return null;
    const cs = new CompressionStream("deflate");
    const writer = cs.writable.getWriter();
    writer.write(u8);
    writer.close();
    const buf = await new Response(cs.readable).arrayBuffer();
    return new Uint8Array(buf);
  }

  // ------------------------------------------------------------------
  // PNG writer: indexed (palette) PNG, colour type 3

  const PNG_SIG = new Uint8Array([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]);

  function pngChunk(type, data) {
    const out = new Uint8Array(12 + data.length);
    const dv = new DataView(out.buffer);
    dv.setUint32(0, data.length);
    out[4] = type.charCodeAt(0);
    out[5] = type.charCodeAt(1);
    out[6] = type.charCodeAt(2);
    out[7] = type.charCodeAt(3);
    out.set(data, 8);
    dv.setUint32(8 + data.length, crc32(out, 4, 8 + data.length));
    return out;
  }

  // Build RGB histograms, keeping transparency in its own class so that a
  // fully transparent region is never averaged into an opaque colour (which
  // would turn clear areas into grey ghosts).
  function buildHistograms(rgba) {
    const SIZE = 4096;
    const make = () => ({
      cnt: new Uint32Array(SIZE),
      r: new Float64Array(SIZE), g: new Float64Array(SIZE),
      b: new Float64Array(SIZE), a: new Float64Array(SIZE)
    });
    const solid = make(), soft = make();
    let transparent = 0;
    for (let i = 0; i < rgba.length; i += 4) {
      const a = rgba[i + 3];
      if (a < 128) { transparent++; continue; }
      const grp = a >= 224 ? solid : soft;
      const k = ((rgba[i] >> 4) << 8) | ((rgba[i + 1] >> 4) << 4) | (rgba[i + 2] >> 4);
      grp.cnt[k]++;
      grp.r[k] += rgba[i]; grp.g[k] += rgba[i + 1];
      grp.b[k] += rgba[i + 2]; grp.a[k] += a;
    }
    const toEntries = (grp) => {
      const out = [];
      for (let k = 0; k < SIZE; k++) {
        const n = grp.cnt[k];
        if (!n) continue;
        out.push({ r: grp.r[k] / n, g: grp.g[k] / n, b: grp.b[k] / n, a: grp.a[k] / n, count: n });
      }
      return out;
    };
    return { transparent, solid: toEntries(solid), soft: toEntries(soft) };
  }

  // Median cut over RGB. Alpha is carried through as a weighted average.
  function medianCut(entries, maxColors) {
    if (maxColors < 1 || !entries.length) return [];
    if (entries.length <= maxColors) {
      return entries.map((e) => ({
        r: Math.round(e.r), g: Math.round(e.g), b: Math.round(e.b),
        a: Math.round(e.a), count: e.count
      }));
    }

    const makeBox = (items) => {
      let minR = 255, maxR = 0, minG = 255, maxG = 0, minB = 255, maxB = 0;
      let count = 0, sr = 0, sg = 0, sb = 0, sa = 0;
      for (const it of items) {
        if (it.r < minR) minR = it.r; if (it.r > maxR) maxR = it.r;
        if (it.g < minG) minG = it.g; if (it.g > maxG) maxG = it.g;
        if (it.b < minB) minB = it.b; if (it.b > maxB) maxB = it.b;
        count += it.count; sr += it.r * it.count; sg += it.g * it.count;
        sb += it.b * it.count; sa += it.a * it.count;
      }
      return {
        items, count,
        rangeR: maxR - minR, rangeG: maxG - minG, rangeB: maxB - minB,
        avg: { r: sr / count, g: sg / count, b: sb / count, a: sa / count }
      };
    };

    let boxes = [makeBox(entries)];
    while (boxes.length < maxColors) {
      let pick = -1, bestScore = -1;
      for (let i = 0; i < boxes.length; i++) {
        const box = boxes[i];
        if (box.items.length < 2) continue;
        const score = Math.max(box.rangeR, box.rangeG, box.rangeB) * box.count;
        if (score > bestScore) { bestScore = score; pick = i; }
      }
      if (pick < 0) break;
      const box = boxes[pick];
      let ch = "r";
      if (box.rangeG >= box.rangeR && box.rangeG >= box.rangeB) ch = "g";
      else if (box.rangeB >= box.rangeR && box.rangeB >= box.rangeG) ch = "b";
      const items = box.items.slice().sort((a, b) => a[ch] - b[ch]);
      let total = 0;
      for (const it of items) total += it.count;
      let acc = 0, split = 0;
      for (let i = 0; i < items.length - 1; i++) {
        acc += items[i].count;
        if (acc * 2 >= total) { split = i + 1; break; }
      }
      if (split <= 0) split = 1;
      if (split >= items.length) split = items.length - 1;
      boxes.splice(pick, 1, makeBox(items.slice(0, split)), makeBox(items.slice(split)));
    }

    return boxes.map((b) => ({
      r: Math.round(b.avg.r), g: Math.round(b.avg.g),
      b: Math.round(b.avg.b), a: Math.round(b.avg.a), count: b.count
    }));
  }

  // Map each 4-4-4 RGB bucket to its nearest palette index once.
  function buildLut(palette) {
    const lut = new Int16Array(1 << 12);
    for (let k = 0; k < (1 << 12); k++) {
      const r = ((k >> 8) & 15) << 4 | 8;
      const g = ((k >> 4) & 15) << 4 | 8;
      const b = (k & 15) << 4 | 8;
      let best = 0, bestD = Infinity;
      for (let p = 0; p < palette.length; p++) {
        const c = palette[p];
        const dr = r - c.r, dg = g - c.g, db = b - c.b;
        const d = dr * dr + dg * dg + db * db;
        if (d < bestD) { bestD = d; best = p; if (d === 0) break; }
      }
      lut[k] = best;
    }
    return lut;
  }

  async function encodeIndexedPng(rgba, width, height, maxColors) {
    const hist = buildHistograms(rgba);
    if (!hist.solid.length && !hist.soft.length && !hist.transparent) return null;
    const limit = Math.max(2, Math.min(256, maxColors | 0));

    const palette = [];
    let tIndex = -1;
    if (hist.transparent > 0) { tIndex = 0; palette.push({ r: 0, g: 0, b: 0, a: 0, count: hist.transparent }); }

    let budget = limit - palette.length;
    const totSolid = hist.solid.reduce((s, e) => s + e.count, 0);
    const totSoft = hist.soft.reduce((s, e) => s + e.count, 0);
    let solidColors = budget, softColors = 0;
    if (totSolid > 0 && totSoft > 0) {
      if (budget <= 1) {
        if (totSolid >= totSoft) { solidColors = 1; softColors = 0; }
        else { solidColors = 0; softColors = 1; }
      } else {
        softColors = Math.max(1, Math.round(budget * totSoft / (totSolid + totSoft)));
        solidColors = Math.max(1, budget - softColors);
      }
    } else if (totSoft > 0) {
      softColors = budget; solidColors = 0;
    }
    const solidPal = medianCut(hist.solid, solidColors).map((e) => ({ ...e, a: 255 }));
    const softPal = medianCut(hist.soft, softColors).map((e) => ({
      ...e, a: Math.max(128, Math.min(254, e.a))
    }));
    const solidOffset = palette.length;
    const solidLut = buildLut(solidPal);
    for (const e of solidPal) palette.push(e);
    const softOffset = palette.length;
    const softLut = buildLut(softPal);
    for (const e of softPal) palette.push(e);
    if (!palette.length) return null;

    let depth;
    if (palette.length <= 2) depth = 1;
    else if (palette.length <= 4) depth = 2;
    else if (palette.length <= 16) depth = 4;
    else depth = 8;

    const indices = new Uint8Array(width * height);
    for (let i = 0, p = 0; i < rgba.length; i += 4, p++) {
      const a = rgba[i + 3];
      const k = ((rgba[i] >> 4) << 8) | ((rgba[i + 1] >> 4) << 4) | (rgba[i + 2] >> 4);
      if (a < 128 && tIndex >= 0) { indices[p] = tIndex; continue; }
      if (a < 128) { indices[p] = solidOffset + solidLut[k]; continue; }
      if (a >= 224 || !softPal.length) {
        indices[p] = solidOffset + solidLut[k];
      } else {
        indices[p] = softOffset + softLut[k];
      }
    }

    const rowBytes = (width * depth + 7) >> 3;
    const raw = new Uint8Array(height * (1 + rowBytes));
    for (let y = 0; y < height; y++) {
      const rowStart = y * (1 + rowBytes);
      raw[rowStart] = 0; // filter: none
      const base = y * width;
      for (let x = 0; x < width; x++) {
        const idx = indices[base + x];
        const bitPos = x * depth;
        if (depth === 8) {
          raw[rowStart + 1 + x] = idx;
        } else {
          const byte = 1 + (bitPos >> 3);
          const shift = 8 - depth - (bitPos & 7);
          raw[rowStart + byte] |= (idx & ((1 << depth) - 1)) << shift;
        }
      }
    }

    const compressed = await deflateZlib(raw);
    if (!compressed) return null;

    const ihdr = new Uint8Array(13);
    const dv = new DataView(ihdr.buffer);
    dv.setUint32(0, width);
    dv.setUint32(4, height);
    ihdr[8] = depth;
    ihdr[9] = 3; // colour type: palette
    ihdr[10] = 0;
    ihdr[11] = 0;
    ihdr[12] = 0;

    const plte = new Uint8Array(palette.length * 3);
    for (let i = 0; i < palette.length; i++) {
      plte[i * 3] = palette[i].r;
      plte[i * 3 + 1] = palette[i].g;
      plte[i * 3 + 2] = palette[i].b;
    }

    let hasAlpha = false;
    const trns = new Uint8Array(palette.length);
    for (let i = 0; i < palette.length; i++) {
      trns[i] = palette[i].a;
      if (palette[i].a < 255) hasAlpha = true;
    }

    const parts = [PNG_SIG, pngChunk("IHDR", ihdr), pngChunk("PLTE", plte)];
    if (hasAlpha) parts.push(pngChunk("tRNS", trns));
    parts.push(pngChunk("IDAT", compressed));
    parts.push(pngChunk("IEND", new Uint8Array(0)));
    return concatBytes(parts);
  }

  // ------------------------------------------------------------------
  // canvas helpers: work both in a Worker (OffscreenCanvas) and on the page

  const MIME = {
    png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg",
    svg: "image/svg+xml", bmp: "image/bmp", gif: "image/gif"
  };

  function hasCanvas() {
    return typeof OffscreenCanvas !== "undefined" ||
      (typeof document !== "undefined" && !!document.createElement);
  }

  function makeCanvas(w, h) {
    if (typeof OffscreenCanvas !== "undefined") return new OffscreenCanvas(w, h);
    const c = document.createElement("canvas");
    c.width = w; c.height = h;
    return c;
  }

  async function decodeImage(data, mime) {
    const blob = new Blob([data], { type: mime });
    if (typeof createImageBitmap === "function") {
      try {
        return await createImageBitmap(blob);
      } catch (_) { /* fall through to <img> */ }
    }
    if (typeof document === "undefined") throw new Error("no image decoder");
    return await new Promise((resolve, reject) => {
      const url = URL.createObjectURL(blob);
      const img = new Image();
      img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("decode failed")); };
      img.src = url;
    });
  }

  async function canvasToBytes(canvas, type, quality) {
    if (typeof canvas.convertToBlob === "function") {
      const blob = await canvas.convertToBlob(
        quality == null ? { type } : { type, quality });
      return new Uint8Array(await blob.arrayBuffer());
    }
    return await new Promise((resolve, reject) => {
      canvas.toBlob((blob) => {
        if (!blob) { reject(new Error("encode failed")); return; }
        blob.arrayBuffer().then((ab) => resolve(new Uint8Array(ab)), reject);
      }, type, quality);
    });
  }

  // ------------------------------------------------------------------
  // image compression

  async function compressPng(data, params) {
    if (!hasCanvas()) return null;
    const bmp = await decodeImage(data, MIME.png);
    const w = bmp.width, h = bmp.height;
    const canvas = makeCanvas(w, h);
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.clearRect(0, 0, w, h);
    ctx.drawImage(bmp, 0, 0, w, h);
    if (bmp.close) bmp.close();
    const img = ctx.getImageData(0, 0, w, h);
    const out = await encodeIndexedPng(img.data, w, h, params.colors || 128);
    if (!out) return null;
    return { bytes: out, note: `${w}×${h}, ${params.colors} colours` };
  }

  async function compressJpeg(data, params) {
    if (!hasCanvas()) return null;
    const bmp = await decodeImage(data, MIME.jpg);
    const w = bmp.width, h = bmp.height;
    const canvas = makeCanvas(w, h);
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, w, h);
    ctx.drawImage(bmp, 0, 0, w, h);
    if (bmp.close) bmp.close();
    const out = await canvasToBytes(canvas, MIME.jpg, params.quality || 0.72);
    return {
      bytes: out,
      note: `${w}×${h}, q${Math.round((params.quality || 0.72) * 100)}`
    };
  }

  // ------------------------------------------------------------------
  // SVG optimiser (text level, no DOM)

  function roundPathData(value, decimals) {
    return value.replace(/-?\d*\.?\d+(?:[eE][-+]?\d+)?/g, (m) => {
      const num = parseFloat(m);
      if (!isFinite(num)) return m;
      let out = num.toFixed(decimals);
      if (out.indexOf(".") >= 0) out = out.replace(/0+$/, "").replace(/\.$/, "");
      if (out === "-0") out = "0";
      return out;
    });
  }

  function optimizeSvg(src, level) {
    let s = src.replace(/^\uFEFF/, "");
    s = s.replace(/<\?xml[^>]*\?>\s*/i, "");
    s = s.replace(/<!DOCTYPE[^>]*>\s*/i, "");
    s = s.replace(/<!--[\s\S]*?-->/g, "");
    s = s.replace(/<metadata\b[\s\S]*?<\/metadata>/gi, "");
    s = s.replace(/<metadata\b[^>]*\/>/gi, "");

    if (level !== "safe") {
      // drop editor namespace elements and their subtrees
      s = s.replace(/<(sodipodi|inkscape|rdf|dc|cc):[A-Za-z][\w.-]*\b[\s\S]*?<\/\1:[A-Za-z][\w.-]*>/g, "");
      s = s.replace(/<(?:sodipodi|inkscape|rdf|dc|cc):[A-Za-z][\w.-]*\b[^>]*\/>/g, "");
      // drop editor / private attributes (both quote styles)
      s = s.replace(/\s(?:inkscape|sodipodi|xmlns:inkscape|xmlns:sodipodi|xmlns:dc|xmlns:cc|xmlns:rdf):[A-Za-z][\w.-]*\s*=\s*"[^"]*"/g, "");
      s = s.replace(/\s(?:inkscape|sodipodi|xmlns:inkscape|xmlns:sodipodi|xmlns:dc|xmlns:cc|xmlns:rdf):[A-Za-z][\w.-]*\s*=\s*'[^']*'/g, "");
      s = s.replace(/\sdata-[A-Za-z][\w.-]*\s*=\s*"[^"]*"/g, "");
      s = s.replace(/\sdata-[A-Za-z][\w.-]*\s*=\s*'[^']*'/g, "");
      // drop now-unused editor namespace declarations
      s = s.replace(/\sxmlns:(?:inkscape|sodipodi|dc|cc|rdf)\s*=\s*"[^"]*"/g, "");
      s = s.replace(/\sxmlns:(?:inkscape|sodipodi|dc|cc|rdf)\s*=\s*'[^']*'/g, "");
    }

    if (level === "balanced" || level === "aggressive") {
      const decimals = level === "aggressive" ? 1 : 2;
      s = s.replace(/\bd\s*=\s*"([^"]*)"/g, (m, v) => 'd="' + roundPathData(v, decimals) + '"');
      s = s.replace(/\bpoints\s*=\s*"([^"]*)"/g, (m, v) => 'points="' + roundPathData(v, decimals) + '"');
    }

    s = s.replace(/>\s+</g, "><");
    s = s.trim();
    return s;
  }

  function compressSvg(data, params) {
    const src = new TextDecoder("utf-8").decode(data);
    if (!/<svg[\s>]/i.test(src)) return null;
    const out = optimizeSvg(src, params.level || "balanced");
    if (!/<svg[\s>]/i.test(out)) return null;
    const bytes = new TextEncoder().encode(out);
    if (bytes.length >= data.length) return null;
    return { bytes, note: `${params.level || "balanced"} clean-up` };
  }

  // ------------------------------------------------------------------
  // WAV: parse, resample, re-encode PCM

  function parseWav(bytes) {
    if (bytes.length < 44) return null;
    if (readStr(bytes, 0, 4) !== "RIFF" || readStr(bytes, 8, 4) !== "WAVE") return null;
    const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    let fmt = null, dataOff = -1, dataLen = 0;
    let off = 12;
    while (off + 8 <= bytes.length) {
      const id = readStr(bytes, off, 4);
      const size = dv.getUint32(off + 4, true);
      const body = off + 8;
      if (id === "fmt " && body + 16 <= bytes.length) {
        let format = dv.getUint16(body, true);
        if (format === 0xFFFE && body + 26 <= bytes.length) format = dv.getUint16(body + 24, true);
        fmt = {
          format,
          channels: dv.getUint16(body + 2, true),
          sampleRate: dv.getUint32(body + 4, true),
          bitsPerSample: dv.getUint16(body + 14, true)
        };
      } else if (id === "data") {
        dataOff = body;
        dataLen = Math.min(size, bytes.length - body);
      }
      off = body + size + (size & 1);
    }
    if (!fmt || dataOff < 0 || !fmt.channels || !fmt.sampleRate) return null;
    fmt.dataOffset = dataOff;
    fmt.dataLength = dataLen;
    fmt.extraBytes = bytes.length - (dataOff + dataLen);
    return fmt;
  }

  function wavToChannels(bytes, fmt) {
    const { channels, bitsPerSample, format, dataOffset, dataLength } = fmt;
    const frames = Math.floor(dataLength / (channels * (bitsPerSample >> 3)));
    const out = [];
    for (let c = 0; c < channels; c++) out.push(new Float32Array(frames));
    const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const bytesPerSample = bitsPerSample >> 3;
    for (let f = 0; f < frames; f++) {
      for (let c = 0; c < channels; c++) {
        const at = dataOffset + (f * channels + c) * bytesPerSample;
        let v = 0;
        if (format === 3) {
          v = bitsPerSample === 64 ? dv.getFloat64(at, true) : dv.getFloat32(at, true);
        } else if (bitsPerSample === 8) {
          v = (bytes[at] - 128) / 128;
        } else if (bitsPerSample === 16) {
          v = dv.getInt16(at, true) / 32768;
        } else if (bitsPerSample === 24) {
          let s = bytes[at] | (bytes[at + 1] << 8) | (bytes[at + 2] << 16);
          if (s & 0x800000) s -= 0x1000000;
          v = s / 8388608;
        } else if (bitsPerSample === 32) {
          v = dv.getInt32(at, true) / 2147483648;
        }
        out[c][f] = v;
      }
    }
    return out;
  }

  function resampleChannel(src, inRate, outRate) {
    if (inRate === outRate) return src;
    const outLen = Math.max(1, Math.round(src.length * outRate / inRate));
    const out = new Float32Array(outLen);
    const last = src.length - 1;
    for (let i = 0; i < outLen; i++) {
      const pos = i * inRate / outRate;
      const i0 = Math.min(last, Math.floor(pos));
      const i1 = Math.min(last, i0 + 1);
      const frac = pos - i0;
      out[i] = src[i0] * (1 - frac) + src[i1] * frac;
    }
    return out;
  }

  function downmix(channels) {
    const frames = channels[0].length;
    const out = new Float32Array(frames);
    for (let f = 0; f < frames; f++) {
      let sum = 0;
      for (const ch of channels) sum += ch[f];
      out[f] = sum / channels.length;
    }
    return [out];
  }

  function encodeWav(channels, sampleRate, bitsPerSample) {
    const numCh = channels.length;
    const frames = channels[0].length;
    const bytesPerSample = bitsPerSample >> 3;
    const dataLen = frames * numCh * bytesPerSample;
    const out = new Uint8Array(44 + dataLen);
    const dv = new DataView(out.buffer);
    const wr = (o, s) => { for (let i = 0; i < s.length; i++) out[o + i] = s.charCodeAt(i); };
    wr(0, "RIFF"); dv.setUint32(4, 36 + dataLen, true); wr(8, "WAVE");
    wr(12, "fmt "); dv.setUint32(16, 16, true);
    dv.setUint16(20, 1, true);          // PCM
    dv.setUint16(22, numCh, true);
    dv.setUint32(24, sampleRate, true);
    dv.setUint32(28, sampleRate * numCh * bytesPerSample, true);
    dv.setUint16(32, numCh * bytesPerSample, true);
    dv.setUint16(34, bitsPerSample, true);
    wr(36, "data"); dv.setUint32(40, dataLen, true);
    let at = 44;
    for (let f = 0; f < frames; f++) {
      for (let c = 0; c < numCh; c++) {
        let v = channels[c][f];
        if (v > 1) v = 1; else if (v < -1) v = -1;
        if (bitsPerSample === 8) {
          out[at++] = Math.max(0, Math.min(255, Math.round(v * 127 + 128)));
        } else if (bitsPerSample === 16) {
          dv.setInt16(at, Math.round(v * 32767), true); at += 2;
        } else if (bitsPerSample === 24) {
          let s = Math.round(v * 8388607);
          if (s < 0) s += 0x1000000;
          out[at++] = s & 0xFF; out[at++] = (s >> 8) & 0xFF; out[at++] = (s >> 16) & 0xFF;
        } else {
          dv.setInt32(at, Math.round(v * 2147483647), true); at += 4;
        }
      }
    }
    return out;
  }

  function compressWav(data, params) {
    const fmt = parseWav(data);
    if (!fmt) return null;
    const channels = wavToChannels(data, fmt);
    let chans = channels;
    const targetRate = params.rate && params.rate > 0 ? params.rate : fmt.sampleRate;
    const rate = Math.min(targetRate, fmt.sampleRate);
    let outBits = params.bits && params.bits > 0 ? params.bits : fmt.bitsPerSample;
    if (![8, 16, 24, 32].includes(outBits)) outBits = 16;
    if (params.mono && chans.length > 1) chans = downmix(chans);
    if (rate !== fmt.sampleRate) {
      chans = chans.map((c) => resampleChannel(c, fmt.sampleRate, rate));
    }
    const out = encodeWav(chans, rate, outBits);
    if (out.length >= data.length) return null;
    const notes = [];
    if (rate !== fmt.sampleRate) notes.push(`${fmt.sampleRate}→${rate} Hz`);
    if (chans.length !== fmt.channels) notes.push(`${fmt.channels}ch→mono`);
    if (outBits !== fmt.bitsPerSample) notes.push(`${fmt.bitsPerSample}→${outBits} bit`);
    if (!notes.length) notes.push("PCM re-pack");
    return { bytes: out, note: notes.join(", ") };
  }

  // ------------------------------------------------------------------
  // MP3: strip ID3v2 / ID3v1 tags (browser cannot re-encode MP3)

  function stripMp3Tags(data) {
    let start = 0, end = data.length;
    if (data.length > 10 && data[0] === 0x49 && data[1] === 0x44 && data[2] === 0x33) {
      const flags = data[5];
      const size = ((data[6] & 0x7F) << 21) | ((data[7] & 0x7F) << 14) |
        ((data[8] & 0x7F) << 7) | (data[9] & 0x7F);
      start = 10 + size;
      if (flags & 0x10) start += 10; // footer
    }
    if (end - start > 128 &&
        data[end - 128] === 0x54 && data[end - 127] === 0x41 && data[end - 126] === 0x47) {
      end -= 128;
    }
    if (start >= end || (start === 0 && end === data.length)) return null;
    return data.subarray(start, end);
  }

  function compressMp3(data, params) {
    if (!params.stripTags) return null;
    const out = stripMp3Tags(data);
    if (!out || out.length >= data.length) return null;
    const saved = data.length - out.length;
    return { bytes: out, note: `tags stripped (−${humanSize(saved)})` };
  }

  // ------------------------------------------------------------------
  // classification and metadata (header only, no full decode)

  const IMAGE_EXT = new Set(["png", "jpg", "jpeg", "bmp", "gif"]);
  const AUDIO_EXT = new Set(["wav", "mp3", "ogg", "oga", "m4a", "aac", "flac"]);

  function kindOf(name) {
    const ext = extOf(name);
    if (ext === "svg") return "vector";
    if (ext === "png" || ext === "jpg" || ext === "jpeg") return "image";
    if (ext === "wav") return "wav";
    if (ext === "mp3") return "mp3";
    if (IMAGE_EXT.has(ext) || AUDIO_EXT.has(ext)) return "other-media";
    return "other";
  }

  function isCompressible(kind) {
    return kind === "image" || kind === "vector" || kind === "wav" || kind === "mp3";
  }

  function pngSize(bytes) {
    if (bytes.length < 24) return null;
    if (bytes[0] !== 0x89 || bytes[1] !== 0x50) return null;
    return [readU32(bytes, 16), readU32(bytes, 20)];
  }

  function jpegSize(bytes) {
    let o = 2;
    while (o + 9 < bytes.length) {
      if (bytes[o] !== 0xFF) { o++; continue; }
      const marker = bytes[o + 1];
      if (marker >= 0xC0 && marker <= 0xCF && marker !== 0xC4 && marker !== 0xC8 && marker !== 0xCC) {
        return [(bytes[o + 7] << 8) | bytes[o + 8], (bytes[o + 5] << 8) | bytes[o + 6]];
      }
      const len = (bytes[o + 2] << 8) | bytes[o + 3];
      o += 2 + len;
    }
    return null;
  }

  function svgSize(text) {
    const wm = /width\s*=\s*"([\d.]+)/i.exec(text);
    const hm = /height\s*=\s*"([\d.]+)/i.exec(text);
    if (wm && hm) return [Math.round(parseFloat(wm[1])), Math.round(parseFloat(hm[1]))];
    const vm = /viewBox\s*=\s*"([-\d.]+)[ ,]+([-\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)"/i.exec(text);
    if (vm) return [Math.round(parseFloat(vm[3])), Math.round(parseFloat(vm[4]))];
    return null;
  }

  function wavMeta(bytes) {
    const fmt = parseWav(bytes);
    if (!fmt) return null;
    const frames = fmt.dataLength / (fmt.channels * (fmt.bitsPerSample >> 3) || 1);
    return {
      width: null, height: null,
      duration: frames / fmt.sampleRate,
      sampleRate: fmt.sampleRate,
      channels: fmt.channels,
      bits: fmt.bitsPerSample
    };
  }

  function describeBytes(bytes, name) {
    const ext = extOf(name);
    if (ext === "png") { const s = pngSize(bytes); return s ? { width: s[0], height: s[1] } : {}; }
    if (ext === "jpg" || ext === "jpeg") { const s = jpegSize(bytes); return s ? { width: s[0], height: s[1] } : {}; }
    if (ext === "svg") {
      const text = new TextDecoder("utf-8").decode(bytes);
      const s = svgSize(text);
      return s ? { width: s[0], height: s[1] } : {};
    }
    if (ext === "wav") return wavMeta(bytes) || {};
    return {};
  }

  // ------------------------------------------------------------------
  // file I/O

  let JSZipLib = (typeof JSZip !== "undefined") ? JSZip : null;
  function setJSZip(lib) { JSZipLib = lib; }
  function getJSZip() {
    if (!JSZipLib) throw new Error("The ZIP library is not loaded.");
    return JSZipLib;
  }

  async function loadInput(buffer, filename) {
    const name = baseName(filename || "project.sb3");
    const raw = asU8(buffer);
    if (!name.toLowerCase().endsWith(".sb3")) {
      throw new Error("Please provide an .sb3 file.");
    }
    let zip;
    try {
      zip = await getJSZip().loadAsync(raw);
    } catch (_) {
      throw new Error("Could not read the .sb3 file. Is it a valid Scratch project?");
    }
    const pj = zip.file("project.json");
    if (!pj) throw new Error("project.json was not found inside the .sb3 file");
    const pjRaw = await pj.async("uint8array");
    const entries = [];
    for (const [entryName, entry] of Object.entries(zip.files)) {
      if (entryName === "project.json" || entry.dir) continue;
      entries.push({ name: entryName, data: await entry.async("uint8array") });
    }
    return { entries, pjRaw };
  }

  function scanEntries(entries) {
    const assets = [];
    let mediaBytes = 0, totalBytes = 0, mediaCount = 0;
    for (const entry of entries) {
      totalBytes += entry.data.length;
      const kind = kindOf(entry.name);
      if (!isCompressible(kind)) continue;
      const meta = describeBytes(entry.data, entry.name);
      mediaCount += 1;
      mediaBytes += entry.data.length;
      assets.push({
        name: entry.name,
        kind,
        ext: extOf(entry.name),
        size: entry.data.length,
        width: meta.width || null,
        height: meta.height || null,
        duration: meta.duration || null,
        sampleRate: meta.sampleRate || null,
        channels: meta.channels || null,
        bits: meta.bits || null
      });
    }
    // stable order: images, vectors, audio, then by size desc
    const order = { image: 0, vector: 1, wav: 2, mp3: 3 };
    assets.sort((a, b) => (order[a.kind] - order[b.kind]) || (b.size - a.size));
    return { assets, mediaBytes, totalBytes, mediaCount, entryCount: entries.length };
  }

  async function scanBuffer(buffer, filename, progress) {
    const report = typeof progress === "function" ? progress : () => {};
    report("load", 0.5, "Reading file...");
    const loaded = await loadInput(buffer, filename);
    report("load", 1.0, "File read");
    report("scan", 0.3, "Listing media...");
    const info = scanEntries(loaded.entries);
    report("scan", 1.0, "Media listed");
    return {
      container: "sb3",
      outputName: defaultOutputName(filename),
      origFileSize: asU8(buffer).length,
      mix: mixOf(info.assets),
      ...info
    };
  }

  async function packageSb3(entries, projectBytes, progress) {
    const zip = new (getJSZip())();
    zip.file("project.json", projectBytes, { binary: true });
    for (const entry of entries) {
      zip.file(entry.name, entry.data, { binary: true });
    }
    progress("package", 0.5, "Repacking .sb3...");
    const out = await zip.generateAsync({
      type: "uint8array",
      compression: "DEFLATE",
      compressionOptions: { level: 9 }
    });
    progress("package", 1.0, "Repack complete");
    return out;
  }

  // ------------------------------------------------------------------
  // presets, auto planning, and the compression pass

  const PRESETS = {
    light: {
      jpeg: { quality: 0.82 },
      png: { colors: 256 },
      svg: "safe",
      wav: { rate: 0, bits: 0, mono: false },
      mp3: { stripTags: true }
    },
    balanced: {
      jpeg: { quality: 0.72 },
      png: { colors: 128 },
      svg: "balanced",
      wav: { rate: 22050, bits: 16, mono: false },
      mp3: { stripTags: true }
    },
    strong: {
      jpeg: { quality: 0.55 },
      png: { colors: 64 },
      svg: "aggressive",
      wav: { rate: 16000, bits: 16, mono: true },
      mp3: { stripTags: true }
    }
  };

  function presetFor(strength) {
    return PRESETS[strength] || PRESETS.balanced;
  }

  function autoSetting(asset, preset) {
    if (asset.kind === "image") {
      if (asset.ext === "png") return { method: "png", ...preset.png };
      if (asset.ext === "jpg" || asset.ext === "jpeg") return { method: "jpeg", ...preset.jpeg };
      return { method: "keep" };
    }
    if (asset.kind === "vector") return { method: "svg", level: preset.svg };
    if (asset.kind === "wav") return { method: "wav", ...preset.wav };
    if (asset.kind === "mp3") return { method: "mp3", ...preset.mp3 };
    return { method: "keep" };
  }

  async function compressAsset(asset, setting) {
    const entry = asset.entry;
    const data = entry.data;
    const method = setting.method || "keep";
    if (method === "keep") return { entry, changed: false, method: "keep" };
    let result = null;
    try {
      if (method === "png") result = await compressPng(data, setting);
      else if (method === "jpeg") result = await compressJpeg(data, setting);
      else if (method === "svg") result = compressSvg(data, setting);
      else if (method === "wav") result = compressWav(data, setting);
      else if (method === "mp3") result = compressMp3(data, setting);
    } catch (_) {
      result = null;
    }
    if (!result || !result.bytes || result.bytes.length >= data.length) {
      return { entry, changed: false, method, note: result ? "no gain — kept original" : "kept original" };
    }
    return {
      entry: { name: entry.name, data: result.bytes },
      changed: true,
      method,
      note: result.note || ""
    };
  }

  async function compressBuffer(buffer, filename, options, plan, progress, cancelled) {
    const opts = options || {};
    const report = typeof progress === "function" ? progress : () => {};
    const isCancelled = typeof cancelled === "function" ? cancelled : () => false;

    report("load", 0.4, "Reading file...");
    const loaded = await loadInput(buffer, filename);
    report("load", 1.0, "File read");

    // Attach each media entry to its inventory record so we compress the same
    // set the caller saw during the scan.
    const inventory = scanEntries(loaded.entries);
    const byName = new Map();
    for (const entry of loaded.entries) byName.set(entry.name, entry);
    for (const asset of inventory.assets) asset.entry = byName.get(asset.name);

    const preset = presetFor(opts.strength);
    const manual = opts.mode === "manual" && plan && typeof plan === "object";

    const targets = inventory.assets;
    const results = [];
    let newMediaBytes = 0;

    report("compress", 0, "Compressing media...");
    for (let i = 0; i < targets.length; i++) {
      if (isCancelled()) throw new Error("Cancelled");
      const asset = targets[i];
      const setting = manual
        ? (plan[asset.name] || { method: "keep" })
        : autoSetting(asset, preset);
      const res = await compressAsset(asset, setting);
      if (res.changed) {
        byName.set(asset.name, res.entry);
        newMediaBytes += res.entry.data.length;
      } else {
        newMediaBytes += asset.size;
      }
      results.push({
        name: asset.name,
        kind: asset.kind,
        ext: asset.ext,
        origSize: asset.size,
        newSize: res.changed ? res.entry.data.length : asset.size,
        changed: res.changed,
        method: res.method,
        note: res.note || ""
      });
      report("compress", (i + 1) / Math.max(1, targets.length),
        `Compressed ${i + 1}/${targets.length}`);
    }

    // Rebuild the entry list, keeping original order; project.json is copied
    // through untouched.
    const finalEntries = loaded.entries.map((entry) => byName.get(entry.name) || entry);
    report("package", 0.2, "Repacking .sb3...");
    const finalBytes = await packageSb3(finalEntries, loaded.pjRaw, report);

    const origMedia = inventory.mediaBytes;
    const newMedia = newMediaBytes;
    return {
      container: "sb3",
      finalBytes,
      outputName: defaultOutputName(filename),
      origFileSize: asU8(buffer).length,
      newFileSize: finalBytes.length,
      origMediaSize: origMedia,
      newMediaSize: newMedia,
      mediaRatio: origMedia ? (1 - newMedia / origMedia) * 100 : 0,
      fileRatio: asU8(buffer).length ? (1 - finalBytes.length / asU8(buffer).length) * 100 : 0,
      assetCount: targets.length,
      changedCount: results.filter((r) => r.changed).length,
      results,
      mix: mixOf(inventory.assets)
    };
  }

  function mixOf(assets) {
    const mix = { image: 0, vector: 0, audio: 0 };
    for (const a of assets) {
      if (a.kind === "image") mix.image += a.size;
      else if (a.kind === "vector") mix.vector += a.size;
      else mix.audio += a.size;
    }
    return mix;
  }

  // ------------------------------------------------------------------
  // progress

  const PROGRESS_WEIGHTS = {
    load: [4, 0], scan: [8, 4], compress: [66, 12], package: [20, 78], finalize: [2, 98]
  };
  function progressPercent(phase, frac) {
    const entry = PROGRESS_WEIGHTS[phase];
    if (!entry) return 78;
    return entry[1] + entry[0] * Math.min(Math.max(frac, 0), 1);
  }

  return {
    setJSZip,
    scanBuffer,
    scanEntries,
    compressBuffer,
    progressPercent,
    defaultOutputName,
    humanSize,
    // test hooks for the pure parts (used by the Node QC script)
    __test: {
      crc32, deflateZlib, encodeIndexedPng, buildHistograms, medianCut,
      optimizeSvg, compressSvg, parseWav, encodeWav, compressWav,
      stripMp3Tags, compressMp3, pngSize, jpegSize, svgSize, kindOf
    }
  };
});
