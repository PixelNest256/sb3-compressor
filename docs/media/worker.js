/* SB3 Media Compressor — background worker.
 * Loads the engine and JSZip, then runs scan / compress jobs off the page.
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

self.onmessage = async (event) => {
  const data = event.data || {};
  try {
    if (data.type === "scan") {
      lastPercent = 0;
      const scan = await MEDIA.scanBuffer(data.buffer, data.filename, report);
      self.postMessage({ type: "scanned", scan });
      return;
    }
    if (data.type === "compress") {
      lastPercent = 0;
      const result = await MEDIA.compressBuffer(
        data.buffer, data.filename, data.options, data.plan, report
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
        mix: result.mix,
        results: result.results
      }, [result.finalBytes.buffer]);
    }
  } catch (error) {
    self.postMessage({
      type: "error",
      message: error && error.message ? error.message : String(error)
    });
  }
};
