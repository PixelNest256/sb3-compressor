/* SB3 Media Compressor — page controller. */
(function () {
  "use strict";

  var LANG = /^ja\b/i.test(document.documentElement.lang || "") ? "ja" : "en";

  var STRINGS = {
    en: {
      phases: {
        load: "Reading file",
        scan: "Listing media",
        compress: "Compressing media",
        package: "Repacking .sb3",
        other: "Working"
      },
      kind: { image: "Image", vector: "Vector", audio: "Audio", wav: "Sound", mp3: "Sound" },
      ready: "Ready",
      chooseProject: "Choose a project to begin.",
      reading: "Reading {name}…",
      scanning: "Listing the media in {name}…",
      compressing: "Compressing {name}. This can take a moment.",
      complete: "Complete",
      failed: "Failed",
      cancelled: "Cancelled",
      cancelMessage: "Compression stopped. The file is still loaded.",
      settingsChanged: "Settings changed",
      runAgainPrompt: "Run again to apply the new options.",
      noMeasured: "no media measured yet",
      smaller: "smaller media",
      larger: "media grew",
      measuring: "measuring media",
      downloadSb3: "Download .sb3",
      downloaded: "Downloaded {name}.",
      downloadReady: "Ready to download {name}.",
      invalidFile: "Choose an .sb3 file.",
      emptyFile: "That file is empty. Choose a Scratch project.",
      chooseFirst: "Choose an .sb3 file first.",
      readFileError: "Could not read that file: {error}",
      loadScriptError: "Could not load {src}.",
      engineMissing: "The compressor engine did not start.",
      compressionFailed: "Compression failed.",
      scanFailed: "Could not read the media in that project: {error}",
      loadingEngine: "Loading engine",
      mainThreadNote: "Running in this tab instead of a background worker. Keep the tab open.",
      mainThreadError: "The compressor could not start in this tab: {error} Serving the page over HTTP, for example with python -m http.server, avoids this.",
      modeAutoDesc: "Every asset gets the strength you pick below.",
      modeManualDesc: "Set the method for each asset in the list, then compress.",
      mixNone: "No media measured yet",
      mixAria: "Media mix: images {image}%, vector {vector}%, audio {audio}%.",
      ledgerTitle: "{count} assets · {media}",
      ledgerShrunk: "{changed} of {count} assets shrunk",
      ledgerNone: "No compressible media in this project.",
      showList: "Show list",
      hideList: "Hide list",
      keepAll: "Keep all",
      autoAll: "Auto defaults for all",
      compressButton: "Compress media",
      noGain: "no gain — kept",
      keptOriginal: "kept original",
      optionsReset: "Options reset.",
      confirmManual: "Choose a project to list its media.",
      glyph: { image: "IMG", vector: "SVG", audio: "SND", wav: "WAV", mp3: "MP3" }
    },
    ja: {
      phases: {
        load: "ファイル読み込み",
        scan: "メディア一覧",
        compress: "メディアを圧縮",
        package: ".sb3 再パッケージ",
        other: "処理中"
      },
      kind: { image: "画像", vector: "ベクター", audio: "音声", wav: "音声", mp3: "音声" },
      ready: "準備完了",
      chooseProject: "プロジェクトを選ぶと開始します。",
      reading: "{name} を読み込んでいます…",
      scanning: "{name} のメディアを一覧しています…",
      compressing: "{name} を圧縮しています。少しお待ちください。",
      complete: "完了",
      failed: "失敗",
      cancelled: "中止",
      cancelMessage: "圧縮を中止しました。ファイルは読み込まれたままです。",
      settingsChanged: "設定を変更しました",
      runAgainPrompt: "新しい設定で再実行してください。",
      noMeasured: "まだメディアがありません",
      smaller: "メディアの削減率",
      larger: "メディアが増えました",
      measuring: "メディアを計測中",
      downloadSb3: ".sb3 をダウンロード",
      downloaded: "{name} をダウンロードしました。",
      downloadReady: "{name} をダウンロードできます。",
      invalidFile: ".sb3 を選んでください。",
      emptyFile: "ファイルが空です。Scratch プロジェクトを選んでください。",
      chooseFirst: "先に .sb3 を選んでください。",
      readFileError: "ファイルを読み込めませんでした: {error}",
      loadScriptError: "{src} を読み込めませんでした。",
      engineMissing: "圧縮エンジンが起動しませんでした。",
      compressionFailed: "圧縮に失敗しました。",
      scanFailed: "メディアを読み込めませんでした: {error}",
      loadingEngine: "エンジンを読み込み中",
      mainThreadNote: "バックグラウンドではなく、このタブ内で実行します。タブを閉じずにお待ちください。",
      mainThreadError: "このタブ内で圧縮を開始できませんでした: {error} ページを HTTP で配信すると回避できます（例: python -m http.server）。",
      modeAutoDesc: "すべてのアセットに下の強さを適用します。",
      modeManualDesc: "一覧でアセットごとに方法を選んでから圧縮します。",
      mixNone: "まだ計測結果はありません",
      mixAria: "メディア構成: 画像 {image}%、ベクター {vector}%、音声 {audio}%。",
      ledgerTitle: "{count} 件 · {media}",
      ledgerShrunk: "{count} 件中 {changed} 件を削減",
      ledgerNone: "圧縮できるメディアがありません。",
      showList: "一覧を表示",
      hideList: "一覧を隠す",
      keepAll: "すべてそのまま",
      autoAll: "すべて自動設定",
      compressButton: "メディアを圧縮",
      noGain: "効果なし — そのまま",
      keptOriginal: "そのまま",
      optionsReset: "設定を初期値に戻しました。",
      confirmManual: "プロジェクトを選ぶとメディアを一覧できます。",
      glyph: { image: "画像", vector: "SVG", audio: "音声", wav: "WAV", mp3: "MP3" }
    }
  };

  var L = STRINGS[LANG];
  var PHASE_LABELS = L.phases;

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

  var STRENGTH_KEY = "sb3-media-strength-v1";
  var MODE_KEY = "sb3-media-mode-v1";
  var AUDIO_KEY = "sb3-media-audio-v1";

  var el = {
    dropzone: document.getElementById("dropzone"),
    fileInput: document.getElementById("fileInput"),
    fileRow: document.getElementById("fileRow"),
    fileName: document.getElementById("fileName"),
    fileSize: document.getElementById("fileSize"),
    clearBtn: document.getElementById("clearBtn"),
    resetOptions: document.getElementById("resetOptions"),
    modeAuto: document.getElementById("modeAuto"),
    modeManual: document.getElementById("modeManual"),
    modeDesc: document.getElementById("modeDesc"),
    strengthWrap: document.getElementById("strengthWrap"),
    autoExtra: document.getElementById("autoExtra"),
    optWavMp3: document.getElementById("optWavMp3"),
    wavMp3Bitrate: document.getElementById("wavMp3Bitrate"),
    optMp3Reenc: document.getElementById("optMp3Reenc"),
    mp3Bitrate: document.getElementById("mp3Bitrate"),
    ledger: document.getElementById("ledger"),
    ledgerSummary: document.getElementById("ledgerSummary"),
    ledgerToggle: document.getElementById("ledgerToggle"),
    ledgerList: document.getElementById("ledgerList"),
    bulkRow: document.getElementById("bulkRow"),
    autoAllBtn: document.getElementById("autoAllBtn"),
    keepAllBtn: document.getElementById("keepAllBtn"),
    compressBtn: document.getElementById("compressBtn"),
    mediaSizes: document.getElementById("mediaSizes"),
    fileSizes: document.getElementById("fileSizes"),
    mix: document.getElementById("mix"),
    mixTotal: document.getElementById("mixTotal"),
    mixImage: document.getElementById("mixImage"),
    mixVector: document.getElementById("mixVector"),
    mixAudio: document.getElementById("mixAudio"),
    figureNum: document.getElementById("figureNum"),
    figureLabel: document.getElementById("figureLabel"),
    phaseLabel: document.getElementById("phaseLabel"),
    percentLabel: document.getElementById("percentLabel"),
    progress: document.getElementById("progress"),
    progressBar: document.getElementById("progressBar"),
    runMessage: document.getElementById("runMessage"),
    downloadBtn: document.getElementById("downloadBtn"),
    runAgainBtn: document.getElementById("runAgainBtn"),
    cancelBtn: document.getElementById("cancelBtn")
  };

  var strengthButtons = Array.prototype.slice.call(
    document.querySelectorAll("button[data-strength]"));
  var modeButtons = [el.modeAuto, el.modeManual];
  var themeButtons = Array.prototype.slice.call(
    document.querySelectorAll("button[data-theme-set]"));

  var worker = null;
  var currentFile = null;
  var scan = null;
  var result = null;
  var objectUrl = null;
  var running = false;
  var stale = false;
  var staleAfterRun = false;
  var mode = "auto";
  var strength = "balanced";
  var runId = 0;
  var ledgerOpen = true;
  var deltaEls = new Map();
  var controlEls = new Map();
  var mainThreadCancelled = false;

  // ------------------------------------------------------------ helpers

  function groupDigits(text) {
    var parts = String(text).split(".");
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return parts.join(".");
  }

  function humanSize(n) {
    var units = ["B", "KB", "MB", "GB"];
    for (var i = 0; i < units.length; i++) {
      var unit = units[i];
      if (Math.abs(n) < 1024 || unit === "GB") {
        if (unit === "B") return groupDigits(String(Math.trunc(n))) + " B";
        return groupDigits(n.toFixed(1)) + " " + unit;
      }
      n /= 1024;
    }
    return groupDigits(n.toFixed(1)) + " GB";
  }

  function loadSetting(key, fallback) {
    try {
      var v = localStorage.getItem(key);
      return v == null ? fallback : v;
    } catch (_) { return fallback; }
  }
  function saveSetting(key, value) {
    try { localStorage.setItem(key, value); } catch (_) { /* ignore */ }
  }

  function readAudio() {
    var out = { wavToMp3: false, wavMp3Bitrate: 96, reencodeMp3: false, mp3Bitrate: 96 };
    try {
      var s = JSON.parse(localStorage.getItem(AUDIO_KEY) || "null");
      if (s && typeof s === "object") {
        out.wavToMp3 = !!s.wavToMp3;
        out.reencodeMp3 = !!s.reencodeMp3;
        if ([64, 96, 128].indexOf(Number(s.wavMp3Bitrate)) >= 0) out.wavMp3Bitrate = Number(s.wavMp3Bitrate);
        if ([64, 96, 128].indexOf(Number(s.mp3Bitrate)) >= 0) out.mp3Bitrate = Number(s.mp3Bitrate);
      }
    } catch (_) { /* ignore */ }
    return out;
  }

  function applyAudio(a) {
    if (el.optWavMp3) el.optWavMp3.checked = !!a.wavToMp3;
    if (el.optMp3Reenc) el.optMp3Reenc.checked = !!a.reencodeMp3;
    if (el.wavMp3Bitrate) el.wavMp3Bitrate.value = String(a.wavMp3Bitrate);
    if (el.mp3Bitrate) el.mp3Bitrate.value = String(a.mp3Bitrate);
  }

  function saveAudio() {
    var a = {
      wavToMp3: !!(el.optWavMp3 && el.optWavMp3.checked),
      reencodeMp3: !!(el.optMp3Reenc && el.optMp3Reenc.checked),
      wavMp3Bitrate: el.wavMp3Bitrate ? parseInt(el.wavMp3Bitrate.value, 10) : 96,
      mp3Bitrate: el.mp3Bitrate ? parseInt(el.mp3Bitrate.value, 10) : 96
    };
    try { localStorage.setItem(AUDIO_KEY, JSON.stringify(a)); } catch (_) { /* ignore */ }
  }

  function onAudioChange() {
    saveAudio();
    if (mode === "auto" && scan) startCompression();
    else markStale();
  }

  // ----------------------------------------------------------- strength

  var PRESET_OPTION = {
    light: {
      png: "png:256", jpeg: "jpeg:85", svg: "svg:safe",
      wav: "wav:repack", mp3: "mp3tags"
    },
    balanced: {
      png: "png:128", jpeg: "jpeg:72", svg: "svg:balanced",
      wav: "wav:22050", mp3: "mp3tags"
    },
    strong: {
      png: "png:32", jpeg: "jpeg:55", svg: "svg:aggressive",
      wav: "wav:16000:m", mp3: "mp3tags"
    }
  };

  function defaultValueFor(asset) {
    var preset = PRESET_OPTION[strength] || PRESET_OPTION.balanced;
    if (asset.kind === "image") {
      if (asset.ext === "png") return preset.png;
      if (asset.ext === "jpg" || asset.ext === "jpeg") return preset.jpeg;
      return "keep";
    }
    if (asset.kind === "vector") return preset.svg;
    if (asset.kind === "wav") return preset.wav;
    if (asset.kind === "mp3") return preset.mp3;
    return "keep";
  }

  function optionHint(asset, value) {
    if (value === "keep") return L.keptOriginal;
    if (value === "pnglossless") return "lossless (OxiPNG)";
    if (value.indexOf("pngd:") === 0) return "palette " + value.slice(5) + " + dither";
    if (value.indexOf("png:") === 0) return "palette " + value.slice(4);
    if (value.indexOf("jpeg:") === 0) return "q" + value.slice(5);
    if (value === "svg:safe") return "SVGO (safe)";
    if (value === "svg:balanced") return "SVGO";
    if (value === "svg:aggressive") return "SVGO (strong)";
    if (value === "wav:repack") return "PCM repack";
    if (value.indexOf("wav2mp3:") === 0) {
      var mp = value.slice(8).split(":");
      return "→ MP3 " + mp[0] + "k" + (mp[1] === "m" ? " mono" : "");
    }
    if (value.indexOf("wav:") === 0) {
      var wp = value.slice(4).split(":");
      return wp[0] + " Hz" + (wp[1] === "m" ? " mono" : "");
    }
    if (value === "mp3tags") return "strip tags";
    if (value.indexOf("mp3enc:") === 0) {
      var q = value.slice(7).split(":");
      return "MP3 " + q[0] + "k" + (q[1] === "m" ? " mono" : "");
    }
    return value;
  }

  function settingFromValue(asset, value) {
    if (value === "keep") return { method: "keep" };
    if (value === "pnglossless") return { method: "pnglossless", level: 3 };
    if (value.indexOf("pngd:") === 0) return { method: "png", colors: parseInt(value.slice(5), 10), dither: true, oxilevel: 3 };
    if (value.indexOf("png:") === 0) return { method: "png", colors: parseInt(value.slice(4), 10), oxilevel: 3 };
    if (value.indexOf("jpeg:") === 0) return { method: "jpeg", quality: parseInt(value.slice(5), 10) };
    if (value.indexOf("svg:") === 0) return { method: "svg", level: value.slice(4) };
    if (value === "wav:repack") return { method: "wav", rate: 0, bits: 0, mono: false };
    if (value.indexOf("wav2mp3:") === 0) {
      var mp = value.slice(8).split(":");
      return { method: "wav2mp3", bitrate: parseInt(mp[0], 10), mono: mp[1] === "m" };
    }
    if (value.indexOf("wav:") === 0) {
      var w = value.slice(4).split(":");
      return { method: "wav", rate: parseInt(w[0], 10), bits: 16, mono: w[1] === "m" };
    }
    if (value === "mp3tags") return { method: "mp3tags" };
    if (value.indexOf("mp3enc:") === 0) {
      var q = value.slice(7).split(":");
      return { method: "mp3enc", bitrate: parseInt(q[0], 10), mono: q[1] === "m" };
    }
    return { method: "keep" };
  }

  function readPlan() {
    var plan = {};
    controlEls.forEach(function (control, name) {
      if (control.tagName === "SELECT") {
        plan[name] = settingFromValue(null, control.value);
      }
    });
    return plan;
  }

  function sizeText(asset) {
    var bits = [humanSize(asset.size)];
    if (asset.width && asset.height) bits.push(asset.width + "×" + asset.height);
    if (asset.duration) bits.push(asset.duration.toFixed(2) + "s");
    if (asset.sampleRate) bits.push((asset.sampleRate / 1000).toFixed(1) + "k");
    if (asset.channels) bits.push(asset.channels + "ch");
    return bits.join(" · ");
  }

  // ---------------------------------------------------------------- UI

  function setPhase(text) { el.phaseLabel.textContent = text; }

  function setMessage(text, isError) {
    el.runMessage.textContent = text;
    el.runMessage.classList.toggle("is-error", !!isError);
    if (isError) el.runMessage.setAttribute("role", "alert");
    else el.runMessage.removeAttribute("role");
  }

  function setProgress(percent) {
    var p = Math.max(0, Math.min(100, percent));
    el.progressBar.style.width = p + "%";
    el.percentLabel.textContent = Math.round(p) + "%";
    el.progress.setAttribute("aria-valuenow", String(Math.round(p)));
  }

  function setBusy(busy) { el.dropzone.classList.toggle("is-busy", !!busy); }

  function revokeUrl() {
    if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null; }
  }

  function applyModeUI() {
    el.modeAuto.setAttribute("aria-pressed", String(mode === "auto"));
    el.modeManual.setAttribute("aria-pressed", String(mode === "manual"));
    el.modeDesc.textContent = mode === "auto" ? L.modeAutoDesc : L.modeManualDesc;
    el.bulkRow.hidden = mode !== "manual";
    el.strengthWrap.hidden = false;
    if (el.autoExtra) el.autoExtra.hidden = mode !== "auto";
    // swap the control column
    controlEls.forEach(function (control, name) {
      renderControl(name, control);
    });
  }

  function renderControl(name, control) {
    var asset = scan && scan.assets ? scan.assets.find(function (a) { return a.name === name; }) : null;
    if (!asset) return;
    var holder = control.parentNode;
    if (mode === "manual") {
      if (control.tagName !== "SELECT") {
        var select = buildSelect(asset, defaultValueFor(asset));
        holder.replaceChild(select, control);
        controlEls.set(name, select);
      }
    } else {
      if (control.tagName === "SELECT") {
        var hint = document.createElement("span");
        hint.className = "asset-hint";
        hint.textContent = optionHint(asset, defaultValueFor(asset));
        holder.replaceChild(hint, control);
        controlEls.set(name, hint);
      } else {
        control.textContent = optionHint(asset, defaultValueFor(asset));
      }
    }
  }

  function buildSelect(asset, value) {
    var select = document.createElement("select");
    select.className = "select";
    select.setAttribute("aria-label", asset.name);
    var options = optionsFor(asset);
    options.forEach(function (opt) {
      var o = document.createElement("option");
      o.value = opt.value;
      o.textContent = opt.label;
      if (opt.value === value) o.selected = true;
      select.appendChild(o);
    });
    select.addEventListener("change", markStale);
    return select;
  }

  function optionsFor(asset) {
    var keep = { value: "keep", label: L.keptOriginal };
    if (asset.kind === "image" && asset.ext === "png") {
      return [keep,
        { value: "png:256", label: "Palette · 256 colours" },
        { value: "png:128", label: "Palette · 128 colours" },
        { value: "png:64", label: "Palette · 64 colours" },
        { value: "png:32", label: "Palette · 32 colours" },
        { value: "png:16", label: "Palette · 16 colours" },
        { value: "pngd:64", label: "Palette · 64 + dither" },
        { value: "pngd:32", label: "Palette · 32 + dither" },
        { value: "pnglossless", label: "Lossless optimize (OxiPNG)" }];
    }
    if (asset.kind === "image") {
      return [keep,
        { value: "jpeg:85", label: "Quality 85" },
        { value: "jpeg:72", label: "Quality 72" },
        { value: "jpeg:55", label: "Quality 55" }];
    }
    if (asset.kind === "vector") {
      return [keep,
        { value: "svg:safe", label: "Clean up · safe (SVGO)" },
        { value: "svg:balanced", label: "Clean up (SVGO)" },
        { value: "svg:aggressive", label: "Clean up · strong (SVGO)" }];
    }
    if (asset.kind === "wav") {
      return [keep,
        { value: "wav:repack", label: "Repack only (lossless)" },
        { value: "wav:22050", label: "22,050 Hz" },
        { value: "wav:16000", label: "16,000 Hz" },
        { value: "wav:16000:m", label: "16,000 Hz · mono" },
        { value: "wav:11025:m", label: "11,025 Hz · mono" },
        { value: "wav2mp3:128", label: "→ MP3 128 kbps" },
        { value: "wav2mp3:96", label: "→ MP3 96 kbps" },
        { value: "wav2mp3:64:m", label: "→ MP3 64 kbps · mono" }];
    }
    if (asset.kind === "mp3") {
      return [keep,
        { value: "mp3tags", label: "Strip ID3 tags" },
        { value: "mp3enc:128", label: "Re-encode · 128 kbps" },
        { value: "mp3enc:96", label: "Re-encode · 96 kbps" },
        { value: "mp3enc:64", label: "Re-encode · 64 kbps" }];
    }
    return [keep];
  }

  // ------------------------------------------------------------- ledger

  function badgeClass(kind) {
    if (kind === "image") return "image";
    if (kind === "vector") return "vector";
    if (kind === "wav" || kind === "mp3" || kind === "audio") return "audio";
    return "";
  }

  function renderLedger() {
    el.ledgerList.textContent = "";
    deltaEls = new Map();
    controlEls = new Map();
    if (!scan) { el.ledger.hidden = true; return; }
    el.ledger.hidden = false;

    if (!scan.assets.length) {
      var empty = document.createElement("div");
      empty.className = "ledger-row";
      empty.textContent = L.ledgerNone;
      el.ledgerList.appendChild(empty);
      el.ledgerSummary.textContent = fmt(L.ledgerTitle, { count: 0, media: "0 B" });
      return;
    }

    scan.assets.forEach(function (asset) {
      var row = document.createElement("div");
      row.className = "ledger-row";

      var badge = document.createElement("span");
      badge.className = "badge " + badgeClass(asset.kind);
      badge.textContent = (L.glyph[asset.ext] || L.glyph[asset.kind] || asset.ext).toUpperCase();
      row.appendChild(badge);

      var nameCell = document.createElement("div");
      nameCell.className = "asset-name";
      var file = document.createElement("span");
      file.className = "file";
      file.textContent = asset.name;
      file.title = asset.name;
      var meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = sizeText(asset);
      nameCell.appendChild(file);
      nameCell.appendChild(meta);
      row.appendChild(nameCell);

      var controlCell = document.createElement("div");
      controlCell.className = "asset-control";
      var control;
      if (mode === "manual") {
        control = buildSelect(asset, defaultValueFor(asset));
      } else {
        control = document.createElement("span");
        control.className = "asset-hint";
        control.textContent = optionHint(asset, defaultValueFor(asset));
      }
      controlCell.appendChild(control);
      controlEls.set(asset.name, control);
      row.appendChild(controlCell);

      var delta = document.createElement("div");
      delta.className = "asset-delta";
      delta.textContent = "—";
      deltaEls.set(asset.name, delta);
      row.appendChild(delta);

      el.ledgerList.appendChild(row);
    });

    updateLedgerSummary();
    el.ledgerToggle.hidden = false;
  }

  function updateLedgerSummary() {
    if (!scan) return;
    var text = fmt(L.ledgerTitle, { count: scan.assets.length, media: humanSize(scan.mediaBytes) });
    if (result) {
      text += " · " + fmt(L.ledgerShrunk, { changed: result.changedCount, count: result.assetCount });
    }
    el.ledgerSummary.textContent = text;
  }

  function updateDeltas() {
    var map = {};
    if (result && result.results) {
      result.results.forEach(function (r) { map[r.name] = r; });
    }
    deltaEls.forEach(function (delta, name) {
      var asset = scan.assets.find(function (a) { return a.name === name; });
      if (!asset) return;
      var res = map[name];
      var from = humanSize(asset.size);
      if (!res) {
        delta.textContent = from;
        delta.classList.remove("is-saved");
        return;
      }
      var to = humanSize(res.newSize);
      delta.textContent = "";
      var span = document.createElement("span");
      span.className = "from";
      span.textContent = from;
      var arrow = document.createElement("span");
      arrow.className = "arrow";
      arrow.textContent = "→";
      var toSpan = document.createElement("span");
      toSpan.className = "to";
      toSpan.textContent = to;
      delta.appendChild(span);
      delta.appendChild(arrow);
      delta.appendChild(toSpan);
      if (res.note) {
        var note = document.createElement("span");
        note.className = "note";
        note.textContent = res.note;
        delta.appendChild(note);
      }
      delta.classList.toggle("is-saved", !!res.changed);
    });
  }

  function renderMix(info) {
    var mix = info.mix || { image: 0, vector: 0, audio: 0 };
    var total = mix.image + mix.vector + mix.audio;
    if (!total) {
      el.mixImage.style.width = "100%";
      el.mixVector.style.width = "0%";
      el.mixAudio.style.width = "0%";
      el.mixTotal.textContent = "0 B";
      el.mix.setAttribute("aria-label", L.mixNone);
      return;
    }
    var pi = mix.image / total * 100, pv = mix.vector / total * 100, pa = mix.audio / total * 100;
    el.mixImage.style.width = pi + "%";
    el.mixVector.style.width = pv + "%";
    el.mixAudio.style.width = pa + "%";
    el.mixTotal.textContent = humanSize(total);
    el.mix.setAttribute("aria-label", fmt(L.mixAria, {
      image: pi.toFixed(0), vector: pv.toFixed(0), audio: pa.toFixed(0)
    }));
  }

  function resetReadout() {
    el.mediaSizes.textContent = "—";
    el.fileSizes.textContent = "—";
    el.figureNum.textContent = "0.0";
    el.figureLabel.textContent = L.smaller;
    el.downloadBtn.disabled = true;
    el.downloadBtn.textContent = L.downloadSb3;
    renderMix({ mix: { image: 0, vector: 0, audio: 0 } });
    setProgress(0);
    setPhase(L.ready);
    setMessage(L.chooseProject, false);
  }

  function resetAll() {
    runId += 1;
    revokeUrl();
    result = null;
    scan = null;
    currentFile = null;
    stale = false;
    staleAfterRun = false;
    el.fileRow.hidden = true;
    el.fileName.textContent = "project.sb3";
    el.fileSize.textContent = "—";
    el.fileInput.value = "";
    el.runAgainBtn.hidden = true;
    el.cancelBtn.hidden = true;
    el.ledger.hidden = true;
    el.compressBtn.disabled = true;
    setBusy(false);
    resetReadout();
  }

  function markStale() {
    if (!currentFile) return;
    if (running) { staleAfterRun = true; return; }
    if (!result && !scan) return;
    stale = true;
    el.runAgainBtn.hidden = false;
    setPhase(L.settingsChanged);
    setMessage(L.runAgainPrompt, false);
  }

  function showError(message) {
    setPhase(L.failed);
    setMessage(message, true);
    el.downloadBtn.disabled = !result;
    el.runAgainBtn.hidden = !currentFile;
    el.cancelBtn.hidden = true;
    setBusy(false);
    setProgress(0);
  }

  // --------------------------------------------------------------- file

  function chooseFile() {
    el.fileInput.value = "";
    el.fileInput.click();
  }

  function isSb3(name) { return /\.sb3$/i.test(name || ""); }

  function handleFile(file) {
    if (!file) return;
    if (!isSb3(file.name)) { showError(L.invalidFile); return; }
    if (!file.size) { showError(L.emptyFile); return; }

    stopWorker();
    running = false;
    runId += 1;
    revokeUrl();
    result = null;
    scan = null;
    stale = false;
    staleAfterRun = false;
    currentFile = file;
    el.fileName.textContent = file.name;
    el.fileSize.textContent = humanSize(file.size);
    el.fileRow.hidden = false;
    el.runAgainBtn.hidden = true;
    el.downloadBtn.disabled = true;
    el.compressBtn.disabled = true;
    el.cancelBtn.hidden = true;
    resetReadout();
    startScan();
  }

  // ------------------------------------------------------------- engine

  var mainThreadEngine = null;

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var script = document.createElement("script");
      script.src = src;
      script.onload = function () { script.remove(); resolve(); };
      script.onerror = function () { script.remove(); reject(new Error(fmt(L.loadScriptError, { src: src }))); };
      document.head.appendChild(script);
    });
  }

  function loadMainThreadEngine() {
    if (mainThreadEngine) return mainThreadEngine;
    mainThreadEngine = loadScript(APP_BASE + "jszip.min.js")
      .then(function () { return loadScript(APP_BASE + "compressor.js"); })
      .then(function () {
        if (!window.JSZip || !window.MEDIA) throw new Error(L.engineMissing);
        window.MEDIA.setJSZip(window.JSZip);
      })
      .catch(function (error) { mainThreadEngine = null; throw error; });
    return mainThreadEngine;
  }

  function stopWorker() {
    if (worker) { worker.terminate(); worker = null; }
  }

  function progressReporter(myRun) {
    return function (phase, frac, message) {
      if (myRun !== runId) return;
      setProgress(window.MEDIA ? window.MEDIA.progressPercent(phase, frac) : 0);
      setPhase(PHASE_LABELS[phase] || PHASE_LABELS.other);
      if (message) setMessage(message, false);
    };
  }

  // ---- scan

  function startScan() {
    if (!currentFile) { showError(L.chooseFirst); return; }
    runId += 1;
    var myRun = runId;
    running = true;
    setBusy(true);
    el.cancelBtn.hidden = false;
    el.compressBtn.disabled = true;
    setProgress(0);
    setPhase(PHASE_LABELS.load);
    setMessage(fmt(L.scanning, { name: currentFile.name }), false);

    var file = currentFile;
    file.arrayBuffer().then(function (buffer) {
      if (!running || myRun !== runId) return;
      if (window.location.protocol === "file:") { scanOnMainThread(buffer, file, myRun); return; }
      createWorker(buffer, myRun, function () { scanOnMainThread(buffer, file, myRun); });
      worker.postMessage({ type: "scan", buffer: buffer, filename: file.name }, [buffer]);
    }).catch(function (error) {
      if (myRun !== runId) return;
      running = false; setBusy(false);
      showError(fmt(L.readFileError, { error: error && error.message ? error.message : error }));
    });
  }

  function createWorker(buffer, myRun, fallback) {
    stopWorker();
    var fellBack = { value: false };
    try {
      worker = new Worker(APP_BASE + "worker.js");
    } catch (error) {
      fallback();
      return;
    }
    worker.onmessage = function (event) {
      if (myRun !== runId) return;
      onWorkerMessage(event);
    };
    worker.onerror = function (event) {
      if (event && event.preventDefault) event.preventDefault();
      if (myRun !== runId || fellBack.value) return;
      fellBack.value = true;
      stopWorker();
      fallback();
    };
  }

  function onWorkerMessage(event) {
    var data = event.data || {};
    if (data.type === "progress") {
      if (!running) return;
      setProgress(data.percent || 0);
      setPhase(PHASE_LABELS[data.phase] || PHASE_LABELS.other);
      if (data.message) setMessage(data.message, false);
      return;
    }
    if (data.type === "scanned") {
      running = false;
      stopWorker();
      setBusy(false);
      el.cancelBtn.hidden = true;
      finishScan(data.scan);
      return;
    }
    if (data.type === "error") {
      running = false;
      stopWorker();
      setBusy(false);
      el.cancelBtn.hidden = true;
      showError(data.message || L.compressionFailed);
      return;
    }
    if (data.type === "done") {
      running = false;
      stopWorker();
      setBusy(false);
      el.cancelBtn.hidden = true;
      finish(data);
    }
  }

  // ---- compress

  function startCompression() {
    if (!currentFile) { showError(L.chooseFirst); return; }
    if (!scan) { setMessage(L.confirmManual, false); return; }
    if (running) return;
    runId += 1;
    var myRun = runId;
    running = true;
    stale = false;
    staleAfterRun = false;
    revokeUrl();
    result = null;
    el.runAgainBtn.hidden = true;
    el.cancelBtn.hidden = false;
    el.downloadBtn.disabled = true;
    el.compressBtn.disabled = true;
    el.fileSizes.textContent = humanSize(currentFile.size) + "  →  —";
    el.mediaSizes.textContent = humanSize(scan.mediaBytes) + "  →  —";
    el.figureNum.textContent = "0.0";
    el.figureLabel.textContent = L.measuring;
    setProgress(0);
    setPhase(PHASE_LABELS.compress);
    setMessage(fmt(L.compressing, { name: currentFile.name }), false);
    setBusy(true);

    var options = { mode: mode, strength: strength };
    if (mode === "auto") {
      options.wavToMp3 = !!(el.optWavMp3 && el.optWavMp3.checked);
      options.reencodeMp3 = !!(el.optMp3Reenc && el.optMp3Reenc.checked);
      options.wavMp3Bitrate = el.wavMp3Bitrate ? parseInt(el.wavMp3Bitrate.value, 10) : 96;
      options.mp3Bitrate = el.mp3Bitrate ? parseInt(el.mp3Bitrate.value, 10) : 96;
    }
    var plan = mode === "manual" ? readPlan() : null;
    var file = currentFile;
    file.arrayBuffer().then(function (buffer) {
      if (!running || myRun !== runId) return;
      if (window.location.protocol === "file:") { compressOnMainThread(buffer, file, myRun, options, plan); return; }
      createWorker(buffer, myRun, function () {
        compressOnMainThread(buffer, file, myRun, options, plan);
      });
      worker.postMessage({
        type: "compress", buffer: buffer, filename: file.name, options: options, plan: plan
      }, [buffer]);
    }).catch(function (error) {
      if (myRun !== runId) return;
      running = false; setBusy(false);
      showError(fmt(L.readFileError, { error: error && error.message ? error.message : error }));
    });
  }

  // ---- main-thread fallbacks

  function scanOnMainThread(buffer, file, myRun) {
    setPhase(L.loadingEngine);
    setMessage(L.mainThreadNote, false);
    loadMainThreadEngine().then(function () {
      if (myRun !== runId) return;
      el.cancelBtn.hidden = true;
      return window.MEDIA.scanBuffer(buffer, file.name, progressReporter(myRun));
    }).then(function (out) {
      if (myRun !== runId) return;
      running = false; setBusy(false);
      finishScan(out);
    }).catch(function (error) {
      if (myRun !== runId) return;
      running = false; setBusy(false);
      showError(fmt(L.mainThreadError, { error: error && error.message ? error.message : error }));
    });
  }

  function compressOnMainThread(buffer, file, myRun, options, plan) {
    setPhase(L.loadingEngine);
    setMessage(L.mainThreadNote, false);
    mainThreadCancelled = false;
    loadMainThreadEngine().then(function () {
      if (myRun !== runId) return;
      el.cancelBtn.hidden = true;
      return window.MEDIA.compressBuffer(
        buffer, file.name, options, plan, progressReporter(myRun), function () { return mainThreadCancelled; });
    }).then(function (out) {
      if (myRun !== runId) return;
      running = false; setBusy(false);
      finish(out);
    }).catch(function (error) {
      if (myRun !== runId) return;
      running = false; setBusy(false);
      showError(fmt(L.mainThreadError, { error: error && error.message ? error.message : error }));
    });
  }

  // ---- results

  function finishScan(out) {
    scan = out;
    el.fileSize.textContent = humanSize(out.origFileSize);
    el.mediaSizes.textContent = humanSize(out.mediaBytes);
    el.fileSizes.textContent = humanSize(out.origFileSize);
    renderMix(out);
    renderLedger();
    el.compressBtn.disabled = mode !== "manual";
    if (mode === "auto") {
      startCompression();
    } else {
      setPhase(L.ready);
      setMessage(L.modeManualDesc, false);
    }
  }

  function finish(data) {
    var bytes = data.finalBytes instanceof Uint8Array ? data.finalBytes : new Uint8Array(data.finalBytes);
    var outputName = data.outputName || "project_media.sb3";
    revokeUrl();
    objectUrl = URL.createObjectURL(new Blob([bytes], { type: "application/zip" }));
    result = {
      bytes: bytes,
      name: outputName,
      origFileSize: data.origFileSize,
      newFileSize: data.newFileSize,
      origMediaSize: data.origMediaSize,
      newMediaSize: data.newMediaSize,
      mediaRatio: data.mediaRatio,
      fileRatio: data.fileRatio,
      assetCount: data.assetCount,
      changedCount: data.changedCount,
      results: data.results || []
    };

    var ratio = Number(data.mediaRatio) || 0;
    el.figureNum.textContent = Math.abs(ratio).toFixed(1);
    el.figureLabel.textContent = ratio >= 0 ? L.smaller : L.larger;

    el.mediaSizes.textContent = humanSize(data.origMediaSize) + "  →  " + humanSize(data.newMediaSize);
    el.fileSizes.textContent = humanSize(data.origFileSize) + "  →  " + humanSize(data.newFileSize);
    renderMix({ mix: data.mix || (scan && scan.mix) || { image: 0, vector: 0, audio: 0 } });

    el.downloadBtn.disabled = false;
    el.compressBtn.disabled = mode !== "manual";
    updateDeltas();
    updateLedgerSummary();

    setProgress(100);
    setPhase(L.complete);
    setMessage(fmt(L.downloadReady, { name: outputName }), false);

    if (staleAfterRun) { staleAfterRun = false; markStale(); }
  }

  function cancelRun() {
    if (!running) return;
    runId += 1;
    mainThreadCancelled = true;
    stopWorker();
    running = false;
    setBusy(false);
    el.cancelBtn.hidden = true;
    el.runAgainBtn.hidden = !currentFile;
    el.downloadBtn.disabled = !result;
    el.compressBtn.disabled = !scan || mode !== "manual";
    setPhase(L.cancelled);
    setMessage(L.cancelMessage, false);
    setProgress(0);
  }

  // ---------------------------------------------------------------- theme

  var THEME_KEY = "sb3-media-theme-v1";

  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function setTheme(theme, persist) {
    var dark = theme === "dark";
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", dark ? "#15180f" : "#e7e8e1");
    themeButtons.forEach(function (button) {
      button.setAttribute("aria-pressed",
        String(button.getAttribute("data-theme-set") === (dark ? "dark" : "light")));
    });
    if (persist) saveSetting(THEME_KEY, dark ? "dark" : "light");
  }

  function storedTheme() {
    try {
      var value = localStorage.getItem(THEME_KEY);
      return value === "dark" || value === "light" ? value : null;
    } catch (_) { return null; }
  }

  // --------------------------------------------------------------- events

  el.dropzone.addEventListener("click", chooseFile);
  el.dropzone.addEventListener("keydown", function (event) {
    if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
      event.preventDefault(); chooseFile();
    }
  });

  el.fileInput.addEventListener("change", function () {
    handleFile(el.fileInput.files && el.fileInput.files[0]);
  });

  el.clearBtn.addEventListener("click", function () {
    if (running) cancelRun();
    resetAll();
  });

  el.runAgainBtn.addEventListener("click", function () {
    if (mode === "manual" && scan) startCompression();
    else if (currentFile) startScan();
  });
  el.cancelBtn.addEventListener("click", cancelRun);
  el.compressBtn.addEventListener("click", startCompression);

  el.downloadBtn.addEventListener("click", function () {
    if (!result || !objectUrl) return;
    var link = document.createElement("a");
    link.href = objectUrl;
    link.download = result.name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setMessage(fmt(L.downloaded, { name: result.name }), false);
  });

  modeButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      var next = button.getAttribute("data-mode");
      if (next === mode) return;
      mode = next;
      saveSetting(MODE_KEY, mode);
      applyModeUI();
      if (!scan) return;
      renderLedger();
      result = null;
      updateDeltas();
      if (mode === "auto") startCompression();
      else {
        el.runAgainBtn.hidden = true;
        setPhase(L.ready);
        setMessage(L.modeManualDesc, false);
      }
    });
  });

  strengthButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      strength = button.getAttribute("data-strength");
      saveSetting(STRENGTH_KEY, strength);
      strengthButtons.forEach(function (b) {
        b.setAttribute("aria-pressed", String(b.getAttribute("data-strength") === strength));
      });
      if (!scan) return;
      if (mode === "auto") startCompression();
      else markStale();
    });
  });

  [el.optWavMp3, el.wavMp3Bitrate, el.optMp3Reenc, el.mp3Bitrate].forEach(function (control) {
    if (control) control.addEventListener("change", onAudioChange);
  });

  themeButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      setTheme(button.getAttribute("data-theme-set"), true);
    });
  });

  el.resetOptions.addEventListener("click", function () {
    strength = "balanced";
    mode = "auto";
    saveSetting(STRENGTH_KEY, strength);
    saveSetting(MODE_KEY, mode);
    strengthButtons.forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-strength") === strength));
    });
    applyAudio({ wavToMp3: false, reencodeMp3: false, wavMp3Bitrate: 96, mp3Bitrate: 96 });
    saveAudio();
    applyModeUI();
    if (scan) renderLedger();
    setMessage(L.optionsReset, false);
    if (mode === "auto" && scan) startCompression();
  });

  el.ledgerToggle.addEventListener("click", function () {
    ledgerOpen = !ledgerOpen;
    el.ledgerList.hidden = !ledgerOpen;
    el.ledgerToggle.textContent = ledgerOpen ? L.hideList : L.showList;
  });

  el.autoAllBtn.addEventListener("click", function () {
    controlEls.forEach(function (control, name) {
      if (control.tagName !== "SELECT") return;
      var asset = scan.assets.find(function (a) { return a.name === name; });
      if (asset) control.value = defaultValueFor(asset);
    });
    markStale();
  });

  el.keepAllBtn.addEventListener("click", function () {
    controlEls.forEach(function (control) {
      if (control.tagName === "SELECT") control.value = "keep";
    });
    markStale();
  });

  // Accept a dropped file anywhere on the page.
  var dragDepth = 0;
  function hasFiles(event) {
    var types = event.dataTransfer && event.dataTransfer.types;
    if (!types) return false;
    for (var i = 0; i < types.length; i++) if (types[i] === "Files") return true;
    return false;
  }
  window.addEventListener("dragenter", function (event) {
    if (!hasFiles(event)) return;
    event.preventDefault(); dragDepth += 1; el.dropzone.classList.add("is-dragging");
  });
  window.addEventListener("dragover", function (event) {
    if (!hasFiles(event)) return;
    event.preventDefault(); event.dataTransfer.dropEffect = "copy";
  });
  window.addEventListener("dragleave", function (event) {
    if (!hasFiles(event)) return;
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) el.dropzone.classList.remove("is-dragging");
  });
  window.addEventListener("drop", function (event) {
    if (!hasFiles(event)) return;
    event.preventDefault(); dragDepth = 0; el.dropzone.classList.remove("is-dragging");
    var file = event.dataTransfer.files && event.dataTransfer.files[0];
    if (file) handleFile(file);
  });

  // ---------------------------------------------------------------- boot

  setTheme(currentTheme(), false);
  var scheme = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  if (scheme) {
    var onSchemeChange = function (event) {
      if (storedTheme()) return;
      setTheme(event.matches ? "dark" : "light", false);
    };
    if (scheme.addEventListener) scheme.addEventListener("change", onSchemeChange);
    else if (scheme.addListener) scheme.addListener(onSchemeChange);
  }

  mode = loadSetting(MODE_KEY, "auto");
  strength = loadSetting(STRENGTH_KEY, "balanced");
  if (!PRESET_OPTION[strength]) strength = "balanced";
  if (mode !== "manual") mode = "auto";
  strengthButtons.forEach(function (b) {
    b.setAttribute("aria-pressed", String(b.getAttribute("data-strength") === strength));
  });
  applyAudio(readAudio());
  applyModeUI();
  resetReadout();
})();
