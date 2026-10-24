/* SB3 Media Compressor — browser edition.
 * Compresses the images and sounds packed inside a Scratch / TurboWarp .sb3
 * file, then repacks the zip. Everything runs in the tab: no upload, no
 * server, no Python.
 *
 * Codecs (vendored under vendor/, loaded lazily):
 *   images : PNG  -> palette quantisation (own writer) + OxiPNG lossless pass
 *            JPEG -> MozJPEG (WASM)
 *   vector : SVG  -> SVGO
 *   audio  : WAV  -> windowed-sinc resample, PCM re-encode, or MP3 transcode
 *            MP3  -> ID3 tag strip, or re-encode (mpg123 decode + LAME encode)
 *
 * Media keeps its file name and format unless a method explicitly converts a
 * sound to MP3, in which case project.json is updated. Otherwise project.json
 * is copied through untouched.
 */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.MEDIA = api;
})(typeof self !== "undefined" ? self : globalThis, function () {
  "use strict";

  const G = (typeof self !== "undefined") ? self
    : (typeof globalThis !== "undefined" ? globalThis : {});

  // ------------------------------------------------------------------
  // small helpers

  const isU8 = (v) => v instanceof Uint8Array;
  const asU8 = (v) => (isU8(v) ? v : new Uint8Array(v));
  const isDict = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

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
  function baseNoExt(name) {
    const dot = name.lastIndexOf(".");
    return dot >= 0 ? name.slice(0, dot) : name;
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
  // vendor loading (WASM codecs + SVGO) and BASE URL

  const SELF_URL = (function () {
    try {
      if (typeof document !== "undefined" && document.currentScript && document.currentScript.src) {
        return document.currentScript.src;
      }
    } catch (_) { /* ignore */ }
    try { if (typeof self !== "undefined" && self.location && self.location.href) return self.location.href; } catch (_) { /* ignore */ }
    try { if (typeof location !== "undefined" && location.href) return location.href; } catch (_) { /* ignore */ }
    return "";
  })();
  const BASE = (function () {
    if (!SELF_URL) return "";
    try { return new URL(".", SELF_URL).href; } catch (_) { return ""; }
  })();

  const vendorPromises = new Map();

  function loadVendorScript(url) {
    if (typeof importScripts === "function") {
      return Promise.resolve().then(() => { importScripts(url); });
    }
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = url;
      s.onload = () => { s.remove(); resolve(); };
      s.onerror = () => { s.remove(); reject(new Error("Could not load " + url)); };
      document.head.appendChild(s);
    });
  }

  function ensureVendor(name) {
    if (!vendorPromises.has(name)) {
      const p = loadVendorScript(BASE + "vendor/" + name + ".js")
        .catch((error) => { vendorPromises.delete(name); throw error; });
      vendorPromises.set(name, p);
    }
    return vendorPromises.get(name);
  }

  const wasmCache = new Map();
  async function loadWasmModule(url) {
    if (!wasmCache.has(url)) {
      wasmCache.set(url, (async () => {
        const res = await fetch(url);
        if (!res.ok) throw new Error("Could not fetch " + url);
        return WebAssembly.compile(await res.arrayBuffer());
      })());
    }
    return wasmCache.get(url);
  }

  let jpegReady = null;
  function ensureJpeg() {
    if (!jpegReady) {
      jpegReady = (async () => {
        await ensureVendor("jpeg");
        if (!G.JSQ_JPEG) throw new Error("jpeg codec unavailable");
        await G.JSQ_JPEG.init(await loadWasmModule(BASE + "vendor/mozjpeg_enc.wasm"));
        return G.JSQ_JPEG;
      })().catch((error) => { jpegReady = null; throw error; });
    }
    return jpegReady;
  }

  let oxipngReady = null;
  function ensureOxipng() {
    if (!oxipngReady) {
      oxipngReady = (async () => {
        await ensureVendor("oxipng");
        if (!G.JSQ_OXIPNG) throw new Error("oxipng codec unavailable");
        await G.JSQ_OXIPNG.init(await loadWasmModule(BASE + "vendor/oxipng_bg.wasm"));
        return G.JSQ_OXIPNG;
      })().catch((error) => { oxipngReady = null; throw error; });
    }
    return oxipngReady;
  }

  let mp3EncoderPromise = null;
  function getMp3Encoder() {
    if (!mp3EncoderPromise) {
      mp3EncoderPromise = (async () => {
        await ensureVendor("mp3");
        if (!G.WME) throw new Error("mp3 encoder unavailable");
        return await G.WME.createMp3Encoder();
      })().catch((error) => { mp3EncoderPromise = null; throw error; });
    }
    return mp3EncoderPromise;
  }

  async function svgoOptimize(text, level) {
    await ensureVendor("svgo");
    if (!G.SVGO || typeof G.SVGO.optimize !== "function") throw new Error("svgo unavailable");
    const precision = level === "safe" ? 3 : level === "aggressive" ? 1 : 2;
    const res = G.SVGO.optimize(text, {
      multipass: level !== "safe",
      floatPrecision: precision,
      plugins: [{
        name: "preset-default",
        params: { overrides: { removeViewBox: false, cleanupIds: level !== "safe" } }
      }]
    });
    if (!res || typeof res.data !== "string") throw new Error("svgo failed");
    return res.data;
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

  // Lloyd (k-means) refinement of a palette against the histogram buckets.
  function refinePalette(entries, palette, iterations) {
    let pal = palette.map((p) => ({ r: p.r, g: p.g, b: p.b, a: p.a, count: p.count }));
    if (pal.length < 2) return pal;
    for (let it = 0; it < iterations; it++) {
      const n = pal.length;
      const sr = new Float64Array(n), sg = new Float64Array(n);
      const sb = new Float64Array(n), sa = new Float64Array(n), cnt = new Float64Array(n);
      for (const e of entries) {
        let best = 0, bd = Infinity;
        for (let p = 0; p < n; p++) {
          const dr = e.r - pal[p].r, dg = e.g - pal[p].g, db = e.b - pal[p].b;
          const d = dr * dr + dg * dg + db * db;
          if (d < bd) { bd = d; best = p; }
        }
        const w = e.count;
        sr[best] += e.r * w; sg[best] += e.g * w; sb[best] += e.b * w;
        sa[best] += e.a * w; cnt[best] += w;
      }
      for (let p = 0; p < n; p++) {
        if (!cnt[p]) continue;
        pal[p] = { r: sr[p] / cnt[p], g: sg[p] / cnt[p], b: sb[p] / cnt[p], a: sa[p] / cnt[p], count: cnt[p] };
      }
    }
    return pal.map((p) => ({
      r: Math.round(p.r), g: Math.round(p.g), b: Math.round(p.b), a: Math.round(p.a), count: p.count
    }));
  }

  function nearestPaletteIndex(palette, r, g, b) {
    let best = 0, bestD = Infinity;
    for (let p = 0; p < palette.length; p++) {
      const c = palette[p];
      const dr = r - c.r, dg = g - c.g, db = b - c.b;
      const d = dr * dr + dg * dg + db * db;
      if (d < bestD) { bestD = d; best = p; if (d === 0) break; }
    }
    return best;
  }
  function bucketColor4(k) {
    return [((k >> 8) & 15) << 4 | 8, ((k >> 4) & 15) << 4 | 8, (k & 15) << 4 | 8];
  }
  function bucketColor5(k) {
    return [((k >> 10) & 31) * 8 + 4, ((k >> 5) & 31) * 8 + 4, (k & 31) * 8 + 4];
  }

  // Floyd–Steinberg dithering against an opaque palette.
  function ditherIndices(rgba, w, h, palette) {
    const lut = new Int16Array(1 << 15).fill(-1);
    const idxs = new Uint8Array(w * h);
    const size = (w + 3) * 3;
    let rowErr = new Float32Array(size);
    let nextErr = new Float32Array(size);
    for (let y = 0; y < h; y++) {
      nextErr.fill(0);
      for (let x = 0; x < w; x++) {
        const i = (y * w + x) * 4;
        const eo = (x + 1) * 3;
        let r = rgba[i] + rowErr[eo];
        let g = rgba[i + 1] + rowErr[eo + 1];
        let b = rgba[i + 2] + rowErr[eo + 2];
        r = r < 0 ? 0 : r > 255 ? 255 : r;
        g = g < 0 ? 0 : g > 255 ? 255 : g;
        b = b < 0 ? 0 : b > 255 ? 255 : b;
        const key = (((r | 0) >> 3) << 10) | (((g | 0) >> 3) << 5) | ((b | 0) >> 3);
        let p = lut[key];
        if (p < 0) {
          const bc = bucketColor5(key);
          p = nearestPaletteIndex(palette, bc[0], bc[1], bc[2]);
          lut[key] = p;
        }
        idxs[y * w + x] = p;
        const c = palette[p];
        const er = r - c.r, eg = g - c.g, eb = b - c.b;
        rowErr[eo + 3] += er * 0.4375; nextErr[eo - 3] += er * 0.1875;
        nextErr[eo] += er * 0.3125; nextErr[eo + 3] += er * 0.0625;
        rowErr[eo + 4] += eg * 0.4375; nextErr[eo - 2] += eg * 0.1875;
        nextErr[eo + 1] += eg * 0.3125; nextErr[eo + 4] += eg * 0.0625;
        rowErr[eo + 5] += eb * 0.4375; nextErr[eo - 1] += eb * 0.1875;
        nextErr[eo + 2] += eb * 0.3125; nextErr[eo + 5] += eb * 0.0625;
      }
      const tmp = rowErr; rowErr = nextErr; nextErr = tmp;
    }
    return idxs;
  }

  async function encodeIndexedPng(rgba, width, height, maxColors, dither) {
    const hist = buildHistograms(rgba);
    if (!hist.solid.length && !hist.soft.length && !hist.transparent) return null;
    const limit = Math.max(2, Math.min(256, maxColors | 0));

    const palette = [];
    let tIndex = -1;
    let indices = null;

    const canDither = !!dither && hist.transparent === 0 && !hist.soft.length && hist.solid.length > 1;
    if (canDither) {
      let pal = medianCut(hist.solid, limit);
      pal = refinePalette(hist.solid, pal, 4);
      if (pal.length >= 2) {
        for (const e of pal) palette.push({ r: e.r, g: e.g, b: e.b, a: 255, count: e.count });
        indices = ditherIndices(rgba, width, height, palette);
      }
    }

    if (!indices) {
      palette.length = 0;
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
      let solidPal = medianCut(hist.solid, solidColors);
      solidPal = refinePalette(hist.solid, solidPal, 4).map((e) => ({ ...e, a: 255 }));
      let softPal = medianCut(hist.soft, softColors);
      softPal = refinePalette(hist.soft, softPal, 4).map((e) => ({
        ...e, a: Math.max(128, Math.min(254, e.a))
      }));
      const solidOffset = palette.length;
      const solidLut = new Int16Array(1 << 12).fill(-1);
      for (const e of solidPal) palette.push(e);
      const softOffset = palette.length;
      const softLut = new Int16Array(1 << 12).fill(-1);
      for (const e of softPal) palette.push(e);
      if (!palette.length) return null;

      indices = new Uint8Array(width * height);
      for (let i = 0, p = 0; i < rgba.length; i += 4, p++) {
        const a = rgba[i + 3];
        const k = ((rgba[i] >> 4) << 8) | ((rgba[i + 1] >> 4) << 4) | (rgba[i + 2] >> 4);
        if (a < 128 && tIndex >= 0) { indices[p] = tIndex; continue; }
        const useSoft = a < 224 && softPal.length;
        const lut = useSoft ? softLut : solidLut;
        const pal = useSoft ? softPal : solidPal;
        const offset = useSoft ? softOffset : solidOffset;
        let idx = lut[k];
        if (idx < 0) {
          const bc = bucketColor4(k);
          idx = nearestPaletteIndex(pal, bc[0], bc[1], bc[2]);
          lut[k] = idx;
        }
        indices[p] = offset + idx;
      }
    }

    let depth;
    if (palette.length <= 2) depth = 1;
    else if (palette.length <= 4) depth = 2;
    else if (palette.length <= 16) depth = 4;
    else depth = 8;

    const rowBytes = (width * depth + 7) >> 3;
    const raw = new Uint8Array(height * (1 + rowBytes));
    for (let y = 0; y < height; y++) {
      const rowStart = y * (1 + rowBytes);
      raw[rowStart] = 0;
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
    ihdr[9] = 3;
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

  const MIME = { png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", svg: "image/svg+xml" };

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
      try { return await createImageBitmap(blob); } catch (_) { /* fall through */ }
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
      const blob = await canvas.convertToBlob(quality == null ? { type } : { type, quality });
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

  async function oxipngOptimise(bytes, level) {
    try {
      const m = await ensureOxipng();
      const res = await m.optimise(bytes, { level: level || 2, interlace: false, optimiseAlpha: false });
      const out = new Uint8Array(res);
      return out.length ? out : bytes;
    } catch (_) {
      return bytes;
    }
  }

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
    let out = await encodeIndexedPng(img.data, w, h, params.colors || 128, params.dither);
    if (!out) return null;
    if (params.oxilevel !== 0) out = await oxipngOptimise(out, params.oxilevel || 1);
    return {
      bytes: out,
      note: `${w}×${h}, ${params.colors} colours` + (params.dither ? ", dithered" : "")
    };
  }

  async function compressPngLossless(data, params) {
    const out = await oxipngOptimise(data, params.level || 3);
    if (!out || out.length >= data.length) return null;
    return { bytes: out, note: "lossless optimize" };
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
    let quality = params.quality || 72;
    if (quality <= 1) quality = Math.round(quality * 100);
    const img = ctx.getImageData(0, 0, w, h);
    let out = null;
    try {
      const m = await ensureJpeg();
      out = new Uint8Array(await m.encode(img, {
        quality,
        progressive: true,
        optimize_coding: true,
        trellis_multipass: true,
        trellis_opt_zero: true,
        chroma_subsample: 2
      }));
    } catch (_) {
      out = await canvasToBytes(canvas, MIME.jpg, quality / 100);
    }
    return { bytes: out, note: `${w}×${h}, q${quality}` };
  }

  // ------------------------------------------------------------------
  // SVG

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

  function optimizeSvgRegex(src, level) {
    let s = src.replace(/^\uFEFF/, "");
    s = s.replace(/<\?xml[^>]*\?>\s*/i, "");
    s = s.replace(/<!DOCTYPE[^>]*>\s*/i, "");
    s = s.replace(/<!--[\s\S]*?-->/g, "");
    s = s.replace(/<metadata\b[\s\S]*?<\/metadata>/gi, "");
    s = s.replace(/<metadata\b[^>]*\/>/gi, "");
    if (level !== "safe") {
      s = s.replace(/<(sodipodi|inkscape|rdf|dc|cc):[A-Za-z][\w.-]*\b[\s\S]*?<\/\1:[A-Za-z][\w.-]*>/g, "");
      s = s.replace(/<(?:sodipodi|inkscape|rdf|dc|cc):[A-Za-z][\w.-]*\b[^>]*\/>/g, "");
      s = s.replace(/\s(?:inkscape|sodipodi|xmlns:inkscape|xmlns:sodipodi|xmlns:dc|xmlns:cc|xmlns:rdf):[A-Za-z][\w.-]*\s*=\s*"[^"]*"/g, "");
      s = s.replace(/\s(?:inkscape|sodipodi|xmlns:inkscape|xmlns:sodipodi|xmlns:dc|xmlns:cc|xmlns:rdf):[A-Za-z][\w.-]*\s*=\s*'[^']*'/g, "");
      s = s.replace(/\sdata-[A-Za-z][\w.-]*\s*=\s*"[^"]*"/g, "");
      s = s.replace(/\sdata-[A-Za-z][\w.-]*\s*=\s*'[^']*'/g, "");
      s = s.replace(/\sxmlns:(?:inkscape|sodipodi|dc|cc|rdf)\s*=\s*"[^"]*"/g, "");
      s = s.replace(/\sxmlns:(?:inkscape|sodipodi|dc|cc|rdf)\s*=\s*'[^']*'/g, "");
    }
    if (level === "balanced" || level === "aggressive") {
      const decimals = level === "aggressive" ? 1 : 2;
      s = s.replace(/\bd\s*=\s*"([^"]*)"/g, (m, v) => 'd="' + roundPathData(v, decimals) + '"');
      s = s.replace(/\bpoints\s*=\s*"([^"]*)"/g, (m, v) => 'points="' + roundPathData(v, decimals) + '"');
    }
    s = s.replace(/>\s+</g, "><");
    return s.trim();
  }

  async function compressSvg(data, params) {
    const src = new TextDecoder("utf-8").decode(data);
    if (!/<svg[\s>]/i.test(src)) return null;
    const level = params.level || "balanced";
    let out = null;
    try {
      out = await svgoOptimize(src, level);
    } catch (_) {
      out = null;
    }
    if (!out || !/<svg[\s>]/i.test(out)) out = optimizeSvgRegex(src, level);
    const bytes = new TextEncoder().encode(out);
    if (bytes.length >= data.length) return null;
    return { bytes, note: `SVGO ${level}` };
  }

  // ------------------------------------------------------------------
  // WAV: parse, resample (windowed sinc), re-encode PCM

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
    return fmt;
  }

  function wavToChannels(bytes, fmt) {
    const { channels, bitsPerSample, format, dataOffset, dataLength } = fmt;
    const bytesPerSample = bitsPerSample >> 3;
    const frames = Math.floor(dataLength / (channels * bytesPerSample));
    const out = [];
    for (let c = 0; c < channels; c++) out.push(new Float32Array(frames));
    const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
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

  function buildResampleKernel(cutoff, taps, phases) {
    const half = (taps >> 1) - 1;
    const table = new Float32Array(phases * taps);
    for (let p = 0; p < phases; p++) {
      const frac = p / phases;
      let norm = 0;
      for (let t = 0; t < taps; t++) {
        const hx = (t - half) - frac;
        const s = hx === 0 ? 2 * cutoff : Math.sin(2 * Math.PI * cutoff * hx) / (Math.PI * hx);
        const w = 0.5 - 0.5 * Math.cos(2 * Math.PI * t / (taps - 1));
        const c = s * w;
        table[p * taps + t] = c;
        norm += c;
      }
      for (let t = 0; t < taps; t++) table[p * taps + t] /= norm;
    }
    return table;
  }

  // Band-limited resampler (removes the aliasing of naive interpolation).
  function resampleChannel(src, inRate, outRate) {
    if (inRate === outRate || !src.length) return src;
    const ratio = outRate / inRate;
    const taps = 32, phases = 256, half = (taps >> 1) - 1;
    const cutoff = 0.5 * Math.min(1, ratio) * 0.98;
    const table = buildResampleKernel(cutoff, taps, phases);
    const outLen = Math.max(1, Math.round(src.length * ratio));
    const last = src.length - 1;
    const out = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const pos = i / ratio;
      const center = Math.floor(pos);
      const frac = pos - center;
      const ph = Math.min(phases - 1, (frac * phases) | 0);
      const base = ph * taps;
      const start = center - half;
      let acc = 0;
      for (let t = 0; t < taps; t++) {
        let idx = start + t;
        if (idx < 0) idx = 0; else if (idx > last) idx = last;
        acc += src[idx] * table[base + t];
      }
      out[i] = acc;
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
    dv.setUint16(20, 1, true);
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
        if (bitsPerSample === 8) out[at++] = Math.max(0, Math.min(255, Math.round(v * 127 + 128)));
        else if (bitsPerSample === 16) { dv.setInt16(at, Math.round(v * 32767), true); at += 2; }
        else if (bitsPerSample === 24) {
          let s = Math.round(v * 8388607);
          if (s < 0) s += 0x1000000;
          out[at++] = s & 0xFF; out[at++] = (s >> 8) & 0xFF; out[at++] = (s >> 16) & 0xFF;
        } else { dv.setInt32(at, Math.round(v * 2147483647), true); at += 4; }
      }
    }
    return out;
  }

  function compressWav(data, params) {
    const fmt = parseWav(data);
    if (!fmt) return null;
    let chans = wavToChannels(data, fmt);
    const targetRate = params.rate && params.rate > 0 ? params.rate : fmt.sampleRate;
    const rate = Math.min(targetRate, fmt.sampleRate);
    let outBits = params.bits && params.bits > 0 ? params.bits : fmt.bitsPerSample;
    if (![8, 16, 24, 32].includes(outBits)) outBits = 16;
    if (params.mono && chans.length > 1) chans = downmix(chans);
    if (rate !== fmt.sampleRate) chans = chans.map((c) => resampleChannel(c, fmt.sampleRate, rate));
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
  // MP3: tag strip, encode, decode + re-encode

  function stripMp3Tags(data) {
    let start = 0, end = data.length;
    if (data.length > 10 && data[0] === 0x49 && data[1] === 0x44 && data[2] === 0x33) {
      const flags = data[5];
      const size = ((data[6] & 0x7F) << 21) | ((data[7] & 0x7F) << 14) |
        ((data[8] & 0x7F) << 7) | (data[9] & 0x7F);
      start = 10 + size;
      if (flags & 0x10) start += 10;
    }
    if (end - start > 128 &&
        data[end - 128] === 0x54 && data[end - 127] === 0x41 && data[end - 126] === 0x47) {
      end -= 128;
    }
    if (start >= end || (start === 0 && end === data.length)) return null;
    return data.subarray(start, end);
  }

  function compressMp3Tags(data) {
    const out = stripMp3Tags(data);
    if (!out || out.length >= data.length) return null;
    return { bytes: out, note: `tags stripped (−${humanSize(data.length - out.length)})` };
  }

  async function mp3EncodeChannels(channels, sampleRate, bitrate) {
    if (!channels.length || !channels[0].length) return null;
    const enc = await getMp3Encoder();
    enc.configure({ sampleRate, channels: channels.length, bitrate });
    const parts = [];
    parts.push(new Uint8Array(enc.encode(channels)));
    parts.push(new Uint8Array(enc.finalize()));
    return concatBytes(parts);
  }

  async function mp3Decode(data) {
    await ensureVendor("mp3dec");
    if (!G.WAD_MP3) throw new Error("mp3 decoder unavailable");
    const dec = new G.WAD_MP3.MPEGDecoder();
    await dec.ready;
    const res = dec.decode(data);
    dec.free();
    if (!res || !res.channelData || !res.channelData.length) return null;
    return { channels: res.channelData, sampleRate: res.sampleRate, frames: res.samplesDecoded };
  }

  async function compressWavToMp3(data, params) {
    const fmt = parseWav(data);
    if (!fmt) return null;
    let chans = wavToChannels(data, fmt);
    if (params.mono && chans.length > 1) chans = downmix(chans);
    const bitrate = params.bitrate || 128;
    let out = null;
    try {
      out = await mp3EncodeChannels(chans, fmt.sampleRate, bitrate);
    } catch (_) { out = null; }
    if (!out || out.length >= data.length) return null;
    return {
      bytes: out,
      note: `${bitrate} kbps MP3${params.mono && fmt.channels > 1 ? ", mono" : ""}`,
      newExt: "mp3", newFormat: "mp3",
      audio: { rate: fmt.sampleRate, sampleCount: chans[0].length }
    };
  }

  async function compressMp3Reencode(data, params) {
    let decoded = null;
    try { decoded = await mp3Decode(data); } catch (_) { decoded = null; }
    if (!decoded) return null;
    let chans = decoded.channels;
    let rate = decoded.sampleRate;
    if (params.mono && chans.length > 1) chans = downmix(chans);
    if (params.rate && params.rate > 0 && params.rate < rate) {
      chans = chans.map((c) => resampleChannel(c, rate, params.rate));
      rate = params.rate;
    }
    const bitrate = params.bitrate || 96;
    let out = null;
    try {
      out = await mp3EncodeChannels(chans, rate, bitrate);
    } catch (_) { out = null; }
    if (!out || out.length >= data.length) return null;
    return {
      bytes: out,
      note: `MP3 ${bitrate} kbps${params.mono ? ", mono" : ""}`,
      audio: { rate, sampleCount: chans[0].length }
    };
  }

  // ------------------------------------------------------------------
  // classification and metadata (header only)

  const IMAGE_EXT = new Set(["bmp", "gif"]);
  const AUDIO_EXT = new Set(["ogg", "oga", "m4a", "aac", "flac"]);

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
      duration: frames / fmt.sampleRate,
      sampleRate: fmt.sampleRate, channels: fmt.channels, bits: fmt.bitsPerSample
    };
  }
  function describeBytes(bytes, name) {
    const ext = extOf(name);
    if (ext === "png") { const s = pngSize(bytes); return s ? { width: s[0], height: s[1] } : {}; }
    if (ext === "jpg" || ext === "jpeg") { const s = jpegSize(bytes); return s ? { width: s[0], height: s[1] } : {}; }
    if (ext === "svg") {
      const s = svgSize(new TextDecoder("utf-8").decode(bytes));
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
    if (!name.toLowerCase().endsWith(".sb3")) throw new Error("Please provide an .sb3 file.");
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
        name: entry.name, kind, ext: extOf(entry.name), size: entry.data.length,
        width: meta.width || null, height: meta.height || null,
        duration: meta.duration || null, sampleRate: meta.sampleRate || null,
        channels: meta.channels || null, bits: meta.bits || null
      });
    }
    const order = { image: 0, vector: 1, wav: 2, mp3: 3 };
    assets.sort((a, b) => (order[a.kind] - order[b.kind]) || (b.size - a.size));
    return { assets, mediaBytes, totalBytes, mediaCount, entryCount: entries.length };
  }

  async function scanBuffer(buffer, filename, progress) {
    const report = typeof progress === "function" ? progress : () => {};
    report("load", 0.5, "Reading file...");
    const loaded = await loadInput(buffer, filename);
    report("load", 1.0, "File read");
    report("scan", 0.5, "Listing media...");
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
    for (const entry of entries) zip.file(entry.name, entry.data, { binary: true });
    progress("package", 0.5, "Repacking .sb3...");
    const out = await zip.generateAsync({
      type: "uint8array", compression: "DEFLATE", compressionOptions: { level: 9 }
    });
    progress("package", 1.0, "Repack complete");
    return out;
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

  // Rewrite project.json references after an asset changes format.
  function applyAssetRenames(project, renames) {
    let changed = false;
    const targets = isDict(project) && Array.isArray(project.targets) ? project.targets : [];
    for (const tgt of targets) {
      if (!isDict(tgt)) continue;
      for (const key of ["costumes", "sounds"]) {
        if (!Array.isArray(tgt[key])) continue;
        for (const a of tgt[key]) {
          if (!isDict(a)) continue;
          const info = (a.md5ext && renames.get(a.md5ext)) || (a.assetId && renames.get(a.assetId));
          if (!info) continue;
          a.md5ext = info.newName;
          a.assetId = info.newId;
          a.dataFormat = info.newFormat;
          if (key === "sounds" && info.audio) {
            if ("rate" in a) a.rate = info.audio.rate;
            if ("sampleCount" in a) a.sampleCount = info.audio.sampleCount;
          }
          changed = true;
        }
      }
    }
    return changed;
  }

  // ------------------------------------------------------------------
  // presets, auto planning, and the compression pass

  const PRESETS = {
    light: {
      jpeg: { quality: 85 }, png: { colors: 256, oxilevel: 1 }, svg: "safe",
      wav: { rate: 0, bits: 0, mono: false }, mp3: { tags: true }
    },
    balanced: {
      jpeg: { quality: 72 }, png: { colors: 128, oxilevel: 1 }, svg: "balanced",
      wav: { rate: 22050, bits: 16, mono: false }, mp3: { tags: true }
    },
    strong: {
      jpeg: { quality: 55 }, png: { colors: 32, oxilevel: 2 }, svg: "aggressive",
      wav: { rate: 16000, bits: 16, mono: true }, mp3: { tags: true }
    }
  };

  function presetFor(strength) { return PRESETS[strength] || PRESETS.balanced; }

  function autoSetting(asset, preset, opts) {
    const o = opts || {};
    if (asset.kind === "image") {
      if (asset.ext === "png") {
        const png = { ...preset.png };
        if (o.pngOptimize === false) png.oxilevel = 0;
        return { method: "png", ...png };
      }
      if (asset.ext === "jpg" || asset.ext === "jpeg") return { method: "jpeg", ...preset.jpeg };
      return { method: "keep" };
    }
    if (asset.kind === "vector") return { method: "svg", level: preset.svg };
    if (asset.kind === "wav") {
      if (o.wavToMp3) return { method: "wav2mp3", bitrate: o.wavMp3Bitrate || 96, mono: preset.wav.mono };
      return { method: "wav", ...preset.wav };
    }
    if (asset.kind === "mp3") {
      if (o.reencodeMp3) return { method: "mp3enc", bitrate: o.mp3Bitrate || 96, mono: false };
      return { method: "mp3tags" };
    }
    return { method: "keep" };
  }

  async function compressOne(data, setting) {
    const method = setting.method || "keep";
    try {
      if (method === "png") return await compressPng(data, setting);
      if (method === "pnglossless") return await compressPngLossless(data, setting);
      if (method === "jpeg") return await compressJpeg(data, setting);
      if (method === "svg") return await compressSvg(data, setting);
      if (method === "wav") return compressWav(data, setting);
      if (method === "wav2mp3") return await compressWavToMp3(data, setting);
      if (method === "mp3tags" || method === "mp3") return compressMp3Tags(data);
      if (method === "mp3enc") return await compressMp3Reencode(data, setting);
    } catch (_) {
      return null;
    }
    return null;
  }

  // Canonical per-asset result, shared by the in-process path and the worker pool.
  async function compressAssetBytes(data, setting) {
    const method = (setting && setting.method) || "keep";
    if (method === "keep") return { changed: false, method };
    const res = await compressOne(data, setting);
    if (!res || !res.bytes || res.bytes.length >= data.length) {
      return { changed: false, method, note: "kept original" };
    }
    return {
      changed: true, bytes: res.bytes, note: res.note || "", method,
      newExt: res.newExt || null, newFormat: res.newFormat || null, audio: res.audio || null
    };
  }

  async function compressBuffer(buffer, filename, options, plan, progress, cancelled, runner) {
    const opts = options || {};
    const report = typeof progress === "function" ? progress : () => {};
    const isCancelled = typeof cancelled === "function" ? cancelled : () => false;
    const run = typeof runner === "function" ? runner : compressAssetBytes;

    report("load", 0.4, "Reading file...");
    const loaded = await loadInput(buffer, filename);
    report("load", 1.0, "File read");

    const inventory = scanEntries(loaded.entries);
    const byName = new Map();
    for (const entry of loaded.entries) byName.set(entry.name, entry);
    for (const asset of inventory.assets) asset.entry = byName.get(asset.name);

    const preset = presetFor(opts.strength);
    const manual = opts.mode === "manual" && plan && typeof plan === "object";
    const targets = inventory.assets;
    const renames = new Map();
    const taken = new Set(loaded.entries.map((e) => e.name));
    const results = [];
    let newMediaBytes = 0;

    const settingFor = (asset) =>
      manual ? (plan[asset.name] || { method: "keep" }) : autoSetting(asset, preset, opts);

    report("compress", 0, "Compressing media...");
    const total = Math.max(1, targets.length);
    let done = 0;
    const prepared = new Array(targets.length);

    if (runner) {
      // Dispatched in parallel (e.g. across a worker pool).
      await Promise.all(targets.map(async (asset, i) => {
        if (isCancelled()) throw new Error("Cancelled");
        const setting = settingFor(asset);
        let res = null;
        try { res = await run(asset.entry.data, setting); } catch (_) { res = null; }
        prepared[i] = { asset, setting, res };
        done += 1;
        report("compress", done / total, `Compressed ${done}/${total}`);
      }));
    } else {
      for (let i = 0; i < targets.length; i++) {
        if (isCancelled()) throw new Error("Cancelled");
        const asset = targets[i];
        const setting = settingFor(asset);
        let res = null;
        try { res = await run(asset.entry.data, setting); } catch (_) { res = null; }
        prepared[i] = { asset, setting, res };
        done += 1;
        report("compress", done / total, `Compressed ${done}/${total}`);
      }
    }

    // Naming and aggregation (sequential and cheap).
    for (const item of prepared) {
      const asset = item.asset;
      const res = item.res;
      const setting = item.setting;
      let finalName = asset.name;
      const changed = !!(res && res.changed);
      if (changed && res.newExt) {
        const base = baseNoExt(asset.name);
        let candidate = base + "." + res.newExt;
        let n = 1;
        while (taken.has(candidate) && candidate !== asset.name) { candidate = base + "_" + n + "." + res.newExt; n++; }
        taken.delete(asset.name);
        taken.add(candidate);
        renames.set(asset.name, {
          newName: candidate,
          newId: baseNoExt(candidate),
          newFormat: res.newFormat || res.newExt,
          audio: res.audio || null
        });
        finalName = candidate;
      }
      if (changed) {
        byName.delete(asset.name);
        byName.set(finalName, { name: finalName, data: res.bytes });
        newMediaBytes += res.bytes.length;
      } else {
        newMediaBytes += asset.size;
      }

      results.push({
        name: finalName,
        origName: asset.name,
        kind: asset.kind,
        ext: extOf(finalName),
        origSize: asset.size,
        newSize: changed ? res.bytes.length : asset.size,
        changed,
        method: setting.method || "keep",
        formatChanged: !!(changed && res.newExt),
        note: changed ? (res.note || "") : "kept original"
      });
    }

    const finalEntries = loaded.entries.map((entry) => {
      const replaced = byName.get(entry.name);
      if (replaced && replaced.name === entry.name && replaced.data !== entry.data) return replaced;
      const info = renames.get(entry.name);
      if (info) {
        const renamed = byName.get(info.newName);
        if (renamed) return renamed;
      }
      return entry;
    });

    let projectBytes = loaded.pjRaw;
    let projectChanged = false;
    if (renames.size) {
      try {
        const project = JSON.parse(new TextDecoder("utf-8").decode(loaded.pjRaw));
        if (applyAssetRenames(project, renames)) {
          projectBytes = new TextEncoder().encode(JSON.stringify(project));
          projectChanged = true;
        }
      } catch (_) { /* keep original project.json on any parse trouble */ }
    }

    report("package", 0.2, "Repacking .sb3...");
    const finalBytes = await packageSb3(finalEntries, projectBytes, report);

    const origMedia = inventory.mediaBytes;
    return {
      container: "sb3",
      finalBytes,
      outputName: defaultOutputName(filename),
      origFileSize: asU8(buffer).length,
      newFileSize: finalBytes.length,
      origMediaSize: origMedia,
      newMediaSize: newMediaBytes,
      mediaRatio: origMedia ? (1 - newMediaBytes / origMedia) * 100 : 0,
      fileRatio: asU8(buffer).length ? (1 - finalBytes.length / asU8(buffer).length) * 100 : 0,
      assetCount: targets.length,
      changedCount: results.filter((r) => r.changed).length,
      convertedCount: results.filter((r) => r.formatChanged).length,
      projectChanged,
      results,
      mix: mixOf(inventory.assets)
    };
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
    compressAssetBytes,
    progressPercent,
    defaultOutputName,
    humanSize,
    applyAssetRenames,
    __test: {
      crc32, deflateZlib, encodeIndexedPng, buildHistograms, medianCut, refinePalette,
      optimizeSvgRegex, parseWav, encodeWav, compressWav, stripMp3Tags, compressMp3Tags,
      resampleChannel, buildResampleKernel, pngSize, jpegSize, svgSize, kindOf
    }
  };
});
