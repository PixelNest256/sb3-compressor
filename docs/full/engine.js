/* SB3 Full Compressor — orchestration.
 *
 * Combines the two engines that ship in this repository:
 *   G.MEDIA  (media.js)   — compresses costumes and sounds
 *   G.SB3    (project.js) — compresses project.json
 *
 * The media pass runs first (its worker pool does the heavy lifting), then the
 * project pass rewrites project.json, then the zip is repacked once.
 */
(function (root, factory) {
  "use strict";
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  root.FULL = api;
})(typeof self !== "undefined" ? self : globalThis, function (G) {
  "use strict";

  const isDict = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
  const humanSize = (n) => G.MEDIA.humanSize(n);
  const getJSZip = () => {
    if (!G.JSZip) throw new Error("The ZIP library is not loaded.");
    return G.JSZip;
  };

  function baseName(name) {
    return String(name || "").split(/[\\/]/).pop() || "project.sb3";
  }
  function defaultOutputName(inPath) {
    const base = baseName(inPath);
    const dot = base.lastIndexOf(".");
    const root = dot > 0 ? base.slice(0, dot) : base;
    return root + "_full.sb3";
  }

  async function packageSb3(entries, projectBytes, progress) {
    const zip = new (getJSZip())();
    zip.file("project.json", projectBytes, { binary: true });
    for (const entry of entries) zip.file(entry.name, entry.data, { binary: true });
    if (progress) progress("package", 0.5, "Repacking .sb3...");
    const out = await zip.generateAsync({
      type: "uint8array", compression: "DEFLATE", compressionOptions: { level: 9 }
    });
    if (progress) progress("package", 1.0, "Repack complete");
    return out;
  }

  async function scanBuffer(buffer, filename, progress) {
    const report = typeof progress === "function" ? progress : () => {};
    return await G.MEDIA.scanBuffer(buffer, filename, (phase, frac, message) => {
      report(phase === "load" ? "load" : "scan", frac, message);
    });
  }

  async function compressBuffer(buffer, filename, options, plan, progress, cancelled, runner) {
    const opts = options || {};
    const report = typeof progress === "function" ? progress : () => {};
    const isCancelled = typeof cancelled === "function" ? cancelled : () => false;

    const mediaOptions = Object.assign({}, opts.media || {}, { skipPackage: true });

    // 1. media pass (parallel; returns the rewritten entries and project.json)
    const mediaOut = await G.MEDIA.compressBuffer(
      buffer, filename, mediaOptions, plan,
      (phase, frac, message) => {
        if (phase === "load") report("load", frac, message);
        else if (phase === "scan") report("scan", frac, message);
        else if (phase === "compress") report("media", frac, message);
        // the media engine's "package" report is skipped (we package once)
      },
      isCancelled, runner
    );

    if (isCancelled()) throw new Error("Cancelled");

    // 2. project.json pass
    report("project", 0, "Compressing project data...");
    const origJsonSize = mediaOut.origProjectSize || mediaOut.projectBytes.length;
    let project;
    try {
      project = JSON.parse(new TextDecoder("utf-8").decode(mediaOut.projectBytes));
    } catch (_) {
      throw new Error("Could not parse project.json");
    }
    const comp = new G.SB3.Compressor(
      new G.SB3.Options(opts.project || {}),
      (phase, frac) => {
        let f = 0.15;
        if (phase === "collect") f = 0.15;
        else if (phase === "targets") f = 0.15 + 0.7 * frac;
        else f = 1.0;
        report("project", f, "Compressing project data...");
      },
      isCancelled
    );
    const outProject = comp.run(project);
    const pjBytes = G.SB3.dumpsCompact(outProject);

    // 3. repack once
    report("package", 0.2, "Repacking .sb3...");
    const finalBytes = await packageSb3(mediaOut.entries, pjBytes, report);

    const origFileSize = mediaOut.origFileSize;
    return {
      container: "sb3",
      finalBytes,
      outputName: defaultOutputName(filename),
      origFileSize,
      newFileSize: finalBytes.length,
      fileRatio: origFileSize ? (1 - finalBytes.length / origFileSize) * 100 : 0,
      origJsonSize,
      newJsonSize: pjBytes.length,
      jsonRatio: origJsonSize ? (1 - pjBytes.length / origJsonSize) * 100 : 0,
      origMediaSize: mediaOut.origMediaSize,
      newMediaSize: mediaOut.newMediaSize,
      mediaRatio: mediaOut.mediaRatio,
      assetCount: mediaOut.assetCount,
      changedCount: mediaOut.changedCount,
      convertedCount: mediaOut.convertedCount,
      mediaRewroteProject: mediaOut.projectChanged,
      projectStats: comp.stats,
      results: mediaOut.results,
      mix: mediaOut.mix
    };
  }

  const PROGRESS_WEIGHTS = {
    load: [3, 0], scan: [4, 3], media: [58, 7], project: [20, 65], package: [15, 85]
  };
  function progressPercent(phase, frac) {
    const entry = PROGRESS_WEIGHTS[phase];
    if (!entry) return 85;
    return entry[1] + entry[0] * Math.min(Math.max(frac, 0), 1);
  }

  return { scanBuffer, compressBuffer, progressPercent, defaultOutputName, humanSize };
});
