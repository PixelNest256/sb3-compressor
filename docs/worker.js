/* SB3 Compressor — background worker.
 * Loads the compressor and JSZip, then reports progress to the page.
 */
"use strict";

importScripts("jszip.min.js", "compressor.js");

let lastPercent = 0;

function report(phase, frac, message) {
  const percent = Math.max(lastPercent, Math.min(100, SB3.progressPercent(phase, frac)));
  lastPercent = percent;
  self.postMessage({ type: "progress", phase, percent, message });
}

self.onmessage = async (event) => {
  const data = event.data || {};
  if (data.type !== "compress") return;
  lastPercent = 0;
  try {
    const result = await SB3.compressBuffer(
      data.buffer,
      data.filename,
      data.options,
      report
    );
    self.postMessage({
      type: "done",
      container: result.container,
      finalBytes: result.finalBytes,
      outputName: result.outputName,
      origJsonSize: result.origJsonSize,
      newJsonSize: result.newJsonSize,
      origFileSize: result.origFileSize,
      newFileSize: result.newFileSize,
      ratio: result.ratio,
      stats: result.stats
    }, [result.finalBytes.buffer]);
  } catch (error) {
    self.postMessage({
      type: "error",
      message: error && error.message ? error.message : String(error)
    });
  }
};
