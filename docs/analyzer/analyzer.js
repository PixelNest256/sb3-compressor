/* SB3 Analyzer — engine.
 *
 * Reads a Scratch / TurboWarp .sb3 in the tab and reports:
 *   - the project.json size (against the 5 MB scratch limit)
 *   - media bytes and asset counts per sprite (against the 10 MB per-asset limit)
 *   - block counts per sprite
 * Nothing is uploaded.
 */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.ANALYZE = api;
})(typeof self !== "undefined" ? self : globalThis, function () {
  "use strict";

  // Scratch's upload limits (bytes).
  const LIMITS = { projectJson: 5 * 1024 * 1024, asset: 10 * 1024 * 1024 };

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

  function extOf(name) {
    const dot = name.lastIndexOf(".");
    return dot >= 0 ? name.slice(dot + 1).toLowerCase() : "";
  }
  function kindOf(name) {
    const ext = extOf(name);
    if (ext === "png") return "png";
    if (ext === "jpg" || ext === "jpeg") return "jpg";
    if (ext === "svg") return "svg";
    if (ext === "wav") return "wav";
    if (ext === "mp3") return "mp3";
    return "other";
  }

  let JSZipLib = (typeof JSZip !== "undefined") ? JSZip : null;
  function setJSZip(lib) { JSZipLib = lib; }
  function getJSZip() {
    if (!JSZipLib) throw new Error("The ZIP library is not loaded.");
    return JSZipLib;
  }

  async function analyzeBuffer(buffer, filename) {
    const raw = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
    const name = String(filename || "project.sb3").split(/[\\/]/).pop() || "project.sb3";
    if (!/\.sb3$/i.test(name)) throw new Error("Please provide an .sb3 file.");

    let zip;
    try {
      zip = await getJSZip().loadAsync(raw);
    } catch (_) {
      throw new Error("Could not read the .sb3 file. Is it a valid Scratch project?");
    }
    const pj = zip.file("project.json");
    if (!pj) throw new Error("project.json was not found inside the .sb3 file");
    const pjRaw = await pj.async("uint8array");
    let project;
    try {
      project = JSON.parse(new TextDecoder("utf-8").decode(pjRaw));
    } catch (_) {
      throw new Error("Could not parse project.json");
    }

    const entries = [];
    for (const [entryName, entry] of Object.entries(zip.files)) {
      if (entryName === "project.json" || entry.dir) continue;
      entries.push({ name: entryName, size: (await entry.async("uint8array")).length });
    }

    const targetsRaw = Array.isArray(project.targets) ? project.targets : [];
    const targets = targetsRaw.map((t) => ({
      name: (t && t.name) || "(unnamed)",
      isStage: !!(t && t.isStage),
      costumes: (t && Array.isArray(t.costumes)) ? t.costumes.length : 0,
      sounds: (t && Array.isArray(t.sounds)) ? t.sounds.length : 0,
      blocks: (t && t.blocks && typeof t.blocks === "object") ? Object.keys(t.blocks).length : 0,
      vars: (t && t.variables && typeof t.variables === "object") ? Object.keys(t.variables).length : 0,
      lists: (t && t.lists && typeof t.lists === "object") ? Object.keys(t.lists).length : 0,
      mediaBytes: 0, mediaCount: 0, costumeBytes: 0, soundBytes: 0,
      costumeCount: 0, soundCount: 0
    }));
    const byName = new Map(targets.map((t) => [t.name, t]));
    const sizeOf = new Map(entries.map((e) => [e.name, e.size]));

    // Attribute each asset to the first sprite that references it; collect all
    // owners so shared assets can be marked.
    const owners = new Map();      // entryName -> Set(targetName)
    const ownerFirst = new Map();  // entryName -> targetName
    for (const t of targetsRaw) {
      if (!t || typeof t !== "object") continue;
      const refs = [];
      for (const c of (Array.isArray(t.costumes) ? t.costumes : [])) {
        if (c && c.md5ext) refs.push([c.md5ext, "costume"]);
      }
      for (const s of (Array.isArray(t.sounds) ? t.sounds : [])) {
        if (s && s.md5ext) refs.push([s.md5ext, "sound"]);
      }
      for (const [assetName, kind] of refs) {
        if (!sizeOf.has(assetName)) continue;
        if (!owners.has(assetName)) owners.set(assetName, new Set());
        owners.get(assetName).add(t.name);
        if (ownerFirst.has(assetName)) continue;
        ownerFirst.set(assetName, t.name);
        const info = byName.get(t.name);
        const size = sizeOf.get(assetName);
        info.mediaBytes += size;
        info.mediaCount += 1;
        if (kind === "costume") { info.costumeBytes += size; info.costumeCount += 1; }
        else { info.soundBytes += size; info.soundCount += 1; }
      }
    }

    const assets = entries.map((e) => ({
      name: e.name,
      ext: kindOf(e.name),
      size: e.size,
      owner: ownerFirst.get(e.name) || null,
      owners: owners.has(e.name) ? Array.from(owners.get(e.name)) : [],
      referenced: ownerFirst.has(e.name)
    })).sort((a, b) => b.size - a.size);

    const referencedAssets = assets.filter((a) => a.referenced);
    const mediaTotal = entries.reduce((sum, e) => sum + e.size, 0);
    const referencedTotal = referencedAssets.reduce((sum, a) => sum + a.size, 0);
    const blockTotal = targets.reduce((sum, t) => sum + t.blocks, 0);

    const warnings = [];
    if (pjRaw.length > LIMITS.projectJson) {
      warnings.push({ kind: "projectJson", bytes: pjRaw.length, limit: LIMITS.projectJson });
    }
    for (const a of assets) {
      if (a.size > LIMITS.asset) {
        warnings.push({ kind: "asset", name: a.name, bytes: a.size, limit: LIMITS.asset, owner: a.owner });
      }
    }

    return {
      filename: name,
      fileSize: raw.length,
      projectJsonSize: pjRaw.length,
      targets,
      assets,
      mediaTotal,
      referencedTotal,
      totalAssetCount: entries.length,
      referencedCount: referencedAssets.length,
      unusedCount: entries.length - referencedAssets.length,
      blockTotal,
      warnings,
      limits: LIMITS,
      meta: (project && project.meta) || {},
      extensions: (project && Array.isArray(project.extensions)) ? project.extensions.length : 0,
      monitors: (project && Array.isArray(project.monitors)) ? project.monitors.length : 0
    };
  }

  function percent(value, total) {
    return total > 0 ? (value / total) * 100 : 0;
  }

  return { setJSZip, analyzeBuffer, humanSize, kindOf, LIMITS, percent };
});
