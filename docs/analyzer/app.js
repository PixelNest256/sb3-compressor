/* SB3 Analyzer — page controller. */
(function () {
  "use strict";

  var LANG = /^ja\b/i.test(document.documentElement.lang || "") ? "ja" : "en";

  var STRINGS = {
    en: {
      ready: "Ready",
      chooseProject: "Choose a project to analyze.",
      reading: "Reading {name}…",
      analyzing: "Analyzing {name}…",
      complete: "Complete",
      failed: "Failed",
      invalidFile: "Choose an .sb3 file.",
      emptyFile: "That file is empty. Choose a Scratch project.",
      readFileError: "Could not read that file: {error}",
      analyzeFailed: "Analysis failed.",
      engineMissing: "The analyzer did not start.",
      // readout
      projectJson: "project.json",
      mediaBytes: "media bytes",
      assetsCount: "assets",
      blocks: "blocks",
      fileSize: ".sb3 file",
      statusLabel: "status",
      statusOk: "No issues",
      statusWarn: "{n} warning(s)",
      limitText: "{size} / 5.0 MB ({pct}%)",
      overLimit: "over limit",
      limitNote: "Scratch upload limits: project.json 5 MB, each asset 10 MB.",
      // sections
      secWarnings: "Warnings",
      secMedia: "Media by sprite",
      secBlocks: "Blocks by sprite",
      secAssets: "Largest assets",
      secUnused: "Unused files",
      noWarnings: "No issues detected against the Scratch limits.",
      unusedNote: "{n} file(s) are not referenced by any costume or sound.",
      // table headers
      tSprite: "Sprite", tAssets: "Assets", tBytes: "Bytes",
      tShareBytes: "Bytes share", tShareCount: "Count share",
      tBlocks: "Blocks", tShare: "Share",
      tFile: "File", tOwner: "Owner", tKind: "Kind", tSize: "Size",
      stage: "Stage", shared: "shared", unreferenced: "unreferenced",
      // warnings
      warnProjectJsonTitle: "project.json over the limit",
      warnProjectJson: "project.json is {size}, which exceeds Scratch's 5 MB limit ({over} over).",
      warnAssetTitle: "Asset over the limit",
      warnAsset: "{name} is {size}, which exceeds Scratch's 10 MB per-asset limit (owner: {owner}).",
      unknownOwner: "unreferenced",
      footerLeft: "SB3 Analyzer · everything runs in your browser; files are never uploaded.",
      footerRight: "MIT License"
    },
    ja: {
      ready: "準備完了",
      chooseProject: "プロジェクトを選ぶと解析します。",
      reading: "{name} を読み込んでいます…",
      analyzing: "{name} を解析しています…",
      complete: "完了",
      failed: "失敗",
      invalidFile: ".sb3 を選んでください。",
      emptyFile: "ファイルが空です。Scratch プロジェクトを選んでください。",
      readFileError: "ファイルを読み込めませんでした: {error}",
      analyzeFailed: "解析に失敗しました。",
      engineMissing: "解析エンジンが起動しませんでした。",
      projectJson: "project.json",
      mediaBytes: "メディア",
      assetsCount: "アセット数",
      blocks: "ブロック数",
      fileSize: ".sb3 ファイル",
      statusLabel: "状態",
      statusOk: "問題なし",
      statusWarn: "警告 {n} 件",
      limitText: "{size} / 5.0 MB（{pct}%）",
      overLimit: "上限超過",
      limitNote: "Scratch の上限: project.json は 5 MB、アセット1件あたり 10 MB。",
      secWarnings: "警告",
      secMedia: "スプライト別メディア",
      secBlocks: "スプライト別ブロック数",
      secAssets: "大きいアセット",
      secUnused: "未使用ファイル",
      noWarnings: "Scratch の上限に対して問題は見つかりませんでした。",
      unusedNote: "{n} 件のファイルが、どのコスチューム・音からも参照されていません。",
      tSprite: "スプライト", tAssets: "アセット数", tBytes: "容量",
      tShareBytes: "容量の割合", tShareCount: "個数の割合",
      tBlocks: "ブロック数", tShare: "割合",
      tFile: "ファイル", tOwner: "所有", tKind: "種類", tSize: "サイズ",
      stage: "ステージ", shared: "共有", unreferenced: "未参照",
      warnProjectJsonTitle: "project.json が上限超過",
      warnProjectJson: "project.json は {size} で、Scratch の 5 MB 制限を {over} 超えています。",
      warnAssetTitle: "アセットが上限超過",
      warnAsset: "{name} は {size} で、Scratch のアセット上限 10 MB を超えています（所有: {owner}）。",
      unknownOwner: "未参照",
      footerLeft: "SB3 Analyzer · すべてブラウザ内で処理され、ファイルは送信されません。",
      footerRight: "MIT ライセンス"
    }
  };

  var L = STRINGS[LANG];

  function fmt(template, vars) {
    return String(template).replace(/\{(\w+)\}/g, function (match, key) {
      return vars && Object.prototype.hasOwnProperty.call(vars, key) ? vars[key] : match;
    });
  }

  var APP_BASE = (function () {
    var script = document.currentScript;
    var src = script && script.src ? script.src : window.location.href;
    try { return new URL(".", src).href; } catch (_) { return ""; }
  })();

  var THEME_KEY = "sb3-analyzer-theme-v1";

  var el = {
    dropzone: document.getElementById("dropzone"),
    fileInput: document.getElementById("fileInput"),
    fileRow: document.getElementById("fileRow"),
    fileName: document.getElementById("fileName"),
    fileSize: document.getElementById("fileSize"),
    clearBtn: document.getElementById("clearBtn"),
    report: document.getElementById("report"),
    jsonValue: document.getElementById("jsonValue"),
    jsonLimitFill: document.getElementById("jsonLimitFill"),
    jsonLimitText: document.getElementById("jsonLimitText"),
    jsonTag: document.getElementById("jsonTag"),
    mediaValue: document.getElementById("mediaValue"),
    assetValue: document.getElementById("assetValue"),
    blockValue: document.getElementById("blockValue"),
    fileValue: document.getElementById("fileValue"),
    statusValue: document.getElementById("statusValue"),
    statusTag: document.getElementById("statusTag"),
    warnBox: document.getElementById("warnBox"),
    mediaTbody: document.getElementById("mediaTbody"),
    blocksTbody: document.getElementById("blocksTbody"),
    assetsTbody: document.getElementById("assetsTbody"),
    unusedNote: document.getElementById("unusedNote"),
    unusedBox: document.getElementById("unusedBox"),
    phaseLabel: document.getElementById("phaseLabel")
  };

  var themeButtons = Array.prototype.slice.call(document.querySelectorAll("button[data-theme-set]"));

  var currentFile = null;
  var running = false;
  var runId = 0;

  var humanSize = (n) => window.ANALYZE.humanSize(n);
  function pct(value, total) { return window.ANALYZE.percent(value, total); }

  // ------------------------------------------------------------- helpers

  function setPhase(text) { el.phaseLabel.textContent = text; }

  function showError(message) {
    setPhase(L.failed);
    el.fileSize.textContent = message;
  }

  function shareCell(value, total, alt) {
    var td = document.createElement("td");
    var wrap = document.createElement("div");
    wrap.className = "share";
    var track = document.createElement("span");
    track.className = "share-track";
    var fill = document.createElement("i");
    fill.className = "share-fill" + (alt ? " alt" : "");
    fill.style.width = Math.max(0, Math.min(100, pct(value, total))) + "%";
    track.appendChild(fill);
    var val = document.createElement("span");
    val.className = "share-val";
    val.textContent = pct(value, total).toFixed(1) + "%";
    wrap.appendChild(track);
    wrap.appendChild(val);
    td.appendChild(wrap);
    return td;
  }

  function nameCell(target) {
    var td = document.createElement("td");
    td.className = "name";
    if (target.isStage) {
      var badge = document.createElement("span");
      badge.className = "badge-sprite";
      badge.textContent = L.stage;
      td.appendChild(badge);
    }
    td.appendChild(document.createTextNode(target.name));
    return td;
  }

  function numCell(text) {
    var td = document.createElement("td");
    td.className = "num";
    td.textContent = text;
    return td;
  }

  // ------------------------------------------------------------- render

  function render(report) {
    el.report.hidden = false;
    setPhase(L.complete);

    // readout
    el.jsonValue.textContent = humanSize(report.projectJsonSize);
    var jsonPct = pct(report.projectJsonSize, report.limits.projectJson);
    el.jsonLimitFill.style.width = Math.max(0, Math.min(100, jsonPct)) + "%";
    el.jsonLimitFill.classList.toggle("is-over", report.projectJsonSize > report.limits.projectJson);
    el.jsonLimitText.textContent = fmt(L.limitText, {
      size: humanSize(report.projectJsonSize),
      pct: jsonPct.toFixed(0)
    });
    el.jsonTag.hidden = report.projectJsonSize <= report.limits.projectJson;
    el.jsonTag.textContent = L.overLimit;

    el.mediaValue.textContent = humanSize(report.referencedTotal);
    el.assetValue.textContent = report.referencedCount + " / " + report.totalAssetCount;
    el.blockValue.textContent = report.blockTotal.toLocaleString("en-US");
    el.fileValue.textContent = humanSize(report.fileSize);
    el.statusValue.textContent = report.warnings.length ? fmt(L.statusWarn, { n: report.warnings.length }) : L.statusOk;
    el.statusTag.hidden = report.warnings.length === 0;
    if (report.warnings.length) el.statusTag.textContent = L.overLimit;

    // warnings
    el.warnBox.textContent = "";
    if (report.warnings.length) {
      report.warnings.forEach(function (w) {
        var item = document.createElement("div");
        item.className = "warn-item";
        var tag = document.createElement("span");
        tag.className = "tag";
        var p = document.createElement("p");
        if (w.kind === "projectJson") {
          tag.textContent = L.overLimit;
          p.textContent = fmt(L.warnProjectJson, {
            size: humanSize(w.bytes),
            over: humanSize(w.bytes - w.limit)
          });
        } else {
          tag.textContent = L.overLimit;
          p.textContent = fmt(L.warnAsset, {
            name: w.name,
            size: humanSize(w.bytes),
            owner: w.owner || L.unknownOwner
          });
        }
        item.appendChild(tag);
        item.appendChild(p);
        el.warnBox.appendChild(item);
      });
    } else {
      var ok = document.createElement("div");
      ok.className = "ok-line";
      ok.textContent = L.noWarnings;
      el.warnBox.appendChild(ok);
    }

    // media by sprite
    var mediaRows = report.targets.slice().sort(function (a, b) { return b.mediaBytes - a.mediaBytes; });
    el.mediaTbody.textContent = "";
    mediaRows.forEach(function (t) {
      var tr = document.createElement("tr");
      tr.appendChild(nameCell(t));
      tr.appendChild(numCell(String(t.mediaCount)));
      tr.appendChild(numCell(humanSize(t.mediaBytes)));
      tr.appendChild(shareCell(t.mediaBytes, report.referencedTotal, false));
      tr.appendChild(shareCell(t.mediaCount, report.referencedCount, true));
      el.mediaTbody.appendChild(tr);
    });

    // blocks by sprite
    var blockRows = report.targets.slice().sort(function (a, b) { return b.blocks - a.blocks; });
    el.blocksTbody.textContent = "";
    blockRows.forEach(function (t) {
      var tr = document.createElement("tr");
      tr.appendChild(nameCell(t));
      tr.appendChild(numCell(t.blocks.toLocaleString("en-US")));
      tr.appendChild(shareCell(t.blocks, report.blockTotal, false));
      el.blocksTbody.appendChild(tr);
    });

    // largest assets
    el.assetsTbody.textContent = "";
    report.assets.slice(0, 12).forEach(function (a) {
      var tr = document.createElement("tr");
      var nameTd = document.createElement("td");
      nameTd.className = "name";
      nameTd.textContent = a.name;
      tr.appendChild(nameTd);
      var ownerTd = document.createElement("td");
      if (a.owner) {
        ownerTd.textContent = a.owner + (a.owners.length > 1 ? " (" + a.owners.length + ")" : "");
      } else {
        var sub = document.createElement("span");
        sub.className = "sub";
        sub.textContent = L.unreferenced;
        ownerTd.appendChild(sub);
      }
      tr.appendChild(ownerTd);
      tr.appendChild(numCell(a.ext));
      var sizeTd = document.createElement("td");
      sizeTd.className = "num";
      if (a.size > report.limits.asset) {
        var warn = document.createElement("span");
        warn.className = "asset-warn";
        warn.textContent = humanSize(a.size);
        sizeTd.appendChild(warn);
        var tag = document.createElement("span");
        tag.className = "sub";
        tag.textContent = L.overLimit;
        sizeTd.appendChild(tag);
      } else {
        sizeTd.textContent = humanSize(a.size);
      }
      tr.appendChild(sizeTd);
      el.assetsTbody.appendChild(tr);
    });

    // unused files
    var unused = report.assets.filter(function (a) { return !a.referenced; });
    if (unused.length) {
      el.unusedNote.textContent = fmt(L.unusedNote, { n: unused.length });
      el.unusedBox.textContent = "";
      unused.sort(function (a, b) { return b.size - a.size; });
      unused.forEach(function (a) {
        var row = document.createElement("div");
        row.className = "filelist-row";
        var name = document.createElement("span");
        name.textContent = a.name;
        var size = document.createElement("span");
        size.textContent = humanSize(a.size);
        row.appendChild(name);
        row.appendChild(size);
        el.unusedBox.appendChild(row);
      });
      el.unusedBox.parentNode.hidden = false;
    }
  }

  // --------------------------------------------------------------- file

  function chooseFile() { el.fileInput.value = ""; el.fileInput.click(); }
  function isSb3(name) { return /\.sb3$/i.test(name || ""); }

  function resetReport() {
    el.report.hidden = true;
    el.warnBox.textContent = "";
    el.mediaTbody.textContent = "";
    el.blocksTbody.textContent = "";
    el.assetsTbody.textContent = "";
    el.unusedBox.textContent = "";
    el.unusedBox.parentNode.hidden = true;
    el.jsonValue.textContent = "—";
    el.jsonLimitFill.style.width = "0%";
    el.jsonLimitFill.classList.remove("is-over");
    el.jsonLimitText.textContent = "—";
    el.jsonTag.hidden = true;
    el.mediaValue.textContent = "—";
    el.assetValue.textContent = "—";
    el.blockValue.textContent = "—";
    el.fileValue.textContent = "—";
    el.statusValue.textContent = "—";
    el.statusTag.hidden = true;
    setPhase(L.ready);
  }

  function handleFile(file) {
    if (!file) return;
    if (!isSb3(file.name)) { showError(L.invalidFile); return; }
    if (!file.size) { showError(L.emptyFile); return; }
    runId += 1;
    var myRun = runId;
    running = true;
    currentFile = file;
    el.fileName.textContent = file.name;
    el.fileSize.textContent = humanSize(file.size);
    el.fileRow.hidden = false;
    resetReport();
    el.fileSize.textContent = humanSize(file.size);
    setPhase(fmt(L.analyzing, { name: file.name }));

    file.arrayBuffer().then(function (buffer) {
      if (myRun !== runId) return;
      return window.ANALYZE.analyzeBuffer(buffer, file.name);
    }).then(function (report) {
      if (myRun !== runId) return;
      running = false;
      render(report);
    }).catch(function (error) {
      if (myRun !== runId) return;
      running = false;
      setPhase(L.failed);
      el.fileSize.textContent = error && error.message ? error.message : L.analyzeFailed;
      el.report.hidden = true;
    });
  }

  // ---------------------------------------------------------------- theme

  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }
  function setTheme(theme, persist) {
    var dark = theme === "dark";
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", dark ? "#15180f" : "#e7e8e1");
    themeButtons.forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-theme-set") === (dark ? "dark" : "light")));
    });
    if (persist) { try { localStorage.setItem(THEME_KEY, dark ? "dark" : "light"); } catch (_) { /* ignore */ } }
  }
  function storedTheme() {
    try { var v = localStorage.getItem(THEME_KEY); return v === "dark" || v === "light" ? v : null; }
    catch (_) { return null; }
  }

  // --------------------------------------------------------------- events

  el.dropzone.addEventListener("click", chooseFile);
  el.dropzone.addEventListener("keydown", function (event) {
    if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") { event.preventDefault(); chooseFile(); }
  });
  el.fileInput.addEventListener("change", function () { handleFile(el.fileInput.files && el.fileInput.files[0]); });
  el.clearBtn.addEventListener("click", function () {
    runId += 1; running = false;
    currentFile = null;
    el.fileRow.hidden = true;
    el.fileInput.value = "";
    el.fileName.textContent = "project.sb3";
    el.fileSize.textContent = "—";
    resetReport();
  });

  themeButtons.forEach(function (button) {
    button.addEventListener("click", function () { setTheme(button.getAttribute("data-theme-set"), true); });
  });

  var dragDepth = 0;
  function hasFiles(event) {
    var types = event.dataTransfer && event.dataTransfer.types;
    if (!types) return false;
    for (var i = 0; i < types.length; i++) if (types[i] === "Files") return true;
    return false;
  }
  window.addEventListener("dragenter", function (e) { if (!hasFiles(e)) return; e.preventDefault(); dragDepth += 1; el.dropzone.classList.add("is-dragging"); });
  window.addEventListener("dragover", function (e) { if (!hasFiles(e)) return; e.preventDefault(); e.dataTransfer.dropEffect = "copy"; });
  window.addEventListener("dragleave", function (e) { if (!hasFiles(e)) return; dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) el.dropzone.classList.remove("is-dragging"); });
  window.addEventListener("drop", function (e) {
    if (!hasFiles(e)) return;
    e.preventDefault(); dragDepth = 0; el.dropzone.classList.remove("is-dragging");
    var f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) handleFile(f);
  });

  // ---------------------------------------------------------------- boot

  setTheme(currentTheme(), false);
  var scheme = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  if (scheme) {
    var onScheme = function (event) { if (storedTheme()) return; setTheme(event.matches ? "dark" : "light", false); };
    if (scheme.addEventListener) scheme.addEventListener("change", onScheme);
    else if (scheme.addListener) scheme.addListener(onScheme);
  }
  resetReport();

  window._analyzerLoad = function (buffer, name) {
    return window.ANALYZE.analyzeBuffer(buffer, name).then(function (report) {
      render(report);
      return report;
    });
  };
})();


