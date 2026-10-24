/* SB3 Media Compressor — background worker.
 * Loads the engine and JSZip. Handles three job types:
 *   scan      — list the media in a project
 *   compress  — run the whole pipeline, spreading asset compression across a
 *               pool of nested workers (one per CPU core, capped)
 *   asset     — compress a single asset (run inside a pool worker)
 */
"use strict";

importScripts("jszip.min.js", "compressor.js");

if (typeof MEDIA !== "undefined" && typeof JSZip !== "undefined") {
  MEDIA.setJSZip(JSZip);
}

let lastPercent = 0;

function report(phase, frac, message) {
  const percent = Math.max(lastPercent, Math.min(100, MEDIA.progressPercent(phase, frac)));
  lastPercent = percent;
  self.postMessage({ type: "progress", phase, percent, message });
}

// ------------------------------------------------------------------
// Worker pool for parallel asset compression

let pool = null;
let poolUnavailable = false;
let poolAnnounced = false;

function poolSize() {
  const hc = (typeof navigator !== "undefined" && navigator.hardwareConcurrency) || 4;
  return Math.max(1, Math.min(12, hc - 1));
}

function createPool() {
  const size = poolSize();
  if (size < 2 || typeof Worker === "undefined") return null;

  const workers = [];
  const idle = [];
  const queue = [];
  const pending = new Map();
  let seq = 0;

  function spawn() {
    const w = new Worker(self.location.href);
    w.onmessage = (ev) => {
      const d = ev.data || {};
      if (d.type !== "assetResult") return;
      const job = pending.get(d.id);
      if (!job) return;
      pending.delete(d.id);
      idle.push(w);
      job.resolve(d);
      dispatch();
    };
    w.onerror = (ev) => {
      if (ev && ev.preventDefault) ev.preventDefault();
      for (const [id, job] of [...pending]) {
        if (job.worker === w) { pending.delete(id); job.reject(new Error("asset worker failed")); }
      }
      const i = idle.indexOf(w);
      if (i >= 0) idle.splice(i, 1);
      const j = workers.indexOf(w);
      if (j >= 0) workers.splice(j, 1);
      try { w.terminate(); } catch (_) { /* ignore */ }
    };
    return w;
  }

  function dispatch() {
    if (!workers.length && queue.length) {
      for (const job of queue.splice(0)) job.reject(new Error("no asset workers"));
      return;
    }
    while (idle.length && queue.length) {
      const w = idle.pop();
      const job = queue.shift();
      const id = ++seq;
      job.worker = w;
      pending.set(id, job);
      let copy;
      try { copy = job.bytes.slice(); } catch (_) { copy = job.bytes; }
      w.postMessage({ type: "asset", id, bytes: copy, setting: job.setting }, [copy.buffer]);
    }
  }

  for (let i = 0; i < size; i++) { const w = spawn(); workers.push(w); idle.push(w); }

  return {
    size,
    run(bytes, setting) {
      return new Promise((resolve, reject) => {
        queue.push({ bytes, setting, resolve, reject });
        dispatch();
      });
    },
    terminate() {
      for (const w of workers) { try { w.terminate(); } catch (_) { /* ignore */ } }
      workers.length = 0; idle.length = 0; pending.clear(); queue.length = 0;
    }
  };
}

function getRunner() {
  if (poolUnavailable) return null;
  if (!pool) {
    try { pool = createPool(); } catch (_) { pool = null; }
    if (!pool) poolUnavailable = true;
  }
  if (!pool) return null;
  if (!poolAnnounced) {
    poolAnnounced = true;
    try { self.postMessage({ type: "pool", size: pool.size }); } catch (_) { /* ignore */ }
  }
  return async function runAsset(bytes, setting) {
    try {
      return await pool.run(bytes, setting);
    } catch (_) {
      // A pool worker failed: fall back to compressing in this worker so the
      // asset is never silently skipped.
      return await MEDIA.compressAssetBytes(bytes, setting);
    }
  };
}

// ------------------------------------------------------------------

self.onmessage = async (event) => {
  const data = event.data || {};
  try {
    if (data.type === "asset") {
      const res = await MEDIA.compressAssetBytes(data.bytes, data.setting);
      const msg = {
        type: "assetResult", id: data.id, changed: !!res.changed,
        note: res.note || "", method: res.method || "keep",
        newExt: res.newExt || null, newFormat: res.newFormat || null, audio: res.audio || null
      };
      const transfer = [];
      if (res.changed && res.bytes) { msg.bytes = res.bytes; transfer.push(res.bytes.buffer); }
      self.postMessage(msg, transfer);
      return;
    }

    if (data.type === "scan") {
      lastPercent = 0;
      const scan = await MEDIA.scanBuffer(data.buffer, data.filename, report);
      self.postMessage({ type: "scanned", scan });
      return;
    }

    if (data.type === "compress") {
      lastPercent = 0;
      const runner = getRunner();
      const result = await MEDIA.compressBuffer(
        data.buffer, data.filename, data.options, data.plan, report, null, runner
      );
      self.postMessage({
        type: "done",
        container: result.container,
        finalBytes: result.finalBytes,
        outputName: result.outputName,
        origFileSize: result.origFileSize,
        newFileSize: result.newFileSize,
        origMediaSize: result.origMediaSize,
        newMediaSize: result.newMediaSize,
        mediaRatio: result.mediaRatio,
        fileRatio: result.fileRatio,
        assetCount: result.assetCount,
        changedCount: result.changedCount,
        convertedCount: result.convertedCount,
        projectChanged: result.projectChanged,
        mix: result.mix,
        results: result.results
      }, [result.finalBytes.buffer]);
      return;
    }

    if (data.type === "cancel" && pool) {
      pool.terminate();
      pool = null;
      return;
    }
  } catch (error) {
    self.postMessage({
      type: "error",
      message: error && error.message ? error.message : String(error)
    });
  }
};
