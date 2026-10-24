/* SB3 Full Compressor — page controller. */
(function () {
  "use strict";

  var LANG = /^ja\b/i.test(document.documentElement.lang || "") ? "ja" : "en";

  var STRINGS = {
    en: {
      phases: {
        load: "Reading file", scan: "Listing media", media: "Compressing media",
        project: "Compressing project data", package: "Repacking .sb3", other: "Working"
      },
      glyph: { image: "IMG", vector: "SVG", wav: "WAV", mp3: "MP3" },
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
      noMeasured: "no file measured yet",
      measuring: "measuring",
      smallerFile: "smaller .sb3 file",
      largerFile: "file grew",
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
      loadingEngine: "Loading engine",
      mainThreadNote: "Running in this tab instead of a background worker. Keep the tab open.",
      mainThreadError: "The compressor could not start in this tab: {error} Serving the page over HTTP, for example with python -m http.server, avoids this.",
      mixNone: "No media measured yet",
      mixAria: "Media mix: images {image}%, vector {vector}%, audio {audio}%.",
      ledgerTitle: "{count} media assets · {media}",
      ledgerShrunk: "{changed} shrunk",
      ledgerNone: "No compressible media in this project.",
      showList: "Show list",
      hideList: "Hide list",
      keptOriginal: "kept original",
      optionsReset: "Options reset.",
      threadsNote: "({n} parallel workers)",
      projectLine: "project.json {from} → {to}",
      mediaLine: "media {from} → {to}",
      statsTitle: "Reduction items",
      statMediaShrunk: "media assets shrunk",
      statConverted: "sounds converted to MP3",
      statKeptAsIs: "assets kept as-is",
      statKind: {
        png: "PNG costumes compressed", jpg: "JPEG costumes compressed",
        svg: "SVG costumes optimised", wav: "WAV sounds compressed",
        mp3: "MP3 sounds compressed", other: "other media compressed"
      },
      stats: {
        blocks_renamed: "block IDs renamed",
        vars_renamed: "variables renamed",
        lists_renamed: "lists renamed",
        broadcasts_renamed: "broadcasts renamed",
        fields_removed: "default fields removed",
        monitors_updated: "monitors updated",
        click_rewrites: "click hats rewritten",
        vars_removed: "unused variables removed",
        lists_removed: "unused lists removed",
        procs_renamed: "custom blocks shortened",
        args_renamed: "arguments renamed",
        obscured_shadows_removed: "hidden defaults removed",
        unreachable_blocks_removed: "unreachable blocks removed",
        unreachable_comments_removed: "unreachable comments removed",
        broadcasts_removed: "unused broadcasts removed",
        procs_removed: "unused definitions removed",
        vars_initialized: "variable starting values blanked",
        lists_initialized: "list starting values blanked",
        duplicates_extracted: "duplicate groups extracted",
        dup_blocks_saved: "blocks saved by duplicates",
        near_duplicates_extracted: "near-duplicate groups extracted",
        near_blocks_saved: "blocks saved by near-duplicates",
        ifelse_converted: "if-else blocks simplified",
        noop_procs_removed: "do-nothing definitions removed",
        noop_calls_removed: "do-nothing calls removed",
        noop_receivers_removed: "do-nothing receivers removed",
        noop_broadcasts_removed: "dead broadcasts removed",
        noop_messages_removed: "dead messages removed",
        procs_inlined: "single-use definitions inlined",
        const_values_folded: "constant expressions folded",
        loops_created: "repeat loops created",
        loop_blocks_saved: "blocks saved by loops",
        const_vars_inlined: "constant variables inlined",
        const_reads_inlined: "constant reads replaced",
        arg_ids_shortened: "argument IDs shortened",
        mutation_keys_removed: "mutation keys removed",
        monitors_removed: "monitors removed",
        comments_removed: "comments removed",
        workspace_compacted: "workspace re-flowed",
        float_values_rounded: "rounded values"
      }
    },
    ja: {
      phases: {
        load: "ファイル読み込み", scan: "メディア一覧", media: "メディアを圧縮",
        project: "プロジェクトデータを圧縮", package: ".sb3 再パッケージ", other: "処理中"
      },
      glyph: { image: "画像", vector: "SVG", wav: "WAV", mp3: "MP3" },
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
      noMeasured: "まだファイルがありません",
      measuring: "計測中",
      smallerFile: ".sb3 ファイルの削減率",
      largerFile: "ファイルが増えました",
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
      loadingEngine: "エンジンを読み込み中",
      mainThreadNote: "バックグラウンドではなく、このタブ内で実行します。タブを閉じずにお待ちください。",
      mainThreadError: "このタブ内で圧縮を開始できませんでした: {error} ページを HTTP で配信すると回避できます（例: python -m http.server）。",
      mixNone: "まだ計測結果はありません",
      mixAria: "メディア構成: 画像 {image}%、ベクター {vector}%、音声 {audio}%。",
      ledgerTitle: "メディア {count} 件 · {media}",
      ledgerShrunk: "{changed} 件を削減",
      ledgerNone: "圧縮できるメディアがありません。",
      showList: "一覧を表示",
      hideList: "一覧を隠す",
      keptOriginal: "そのまま",
      optionsReset: "設定を初期値に戻しました。",
      threadsNote: "（並列 {n}）",
      projectLine: "project.json {from} → {to}",
      mediaLine: "メディア {from} → {to}",
      statsTitle: "削減項目",
      statMediaShrunk: "圧縮したメディア",
      statConverted: "MP3 に変換した音",
      statKeptAsIs: "そのまま残したアセット",
      statKind: {
        png: "PNG コスチュームを圧縮", jpg: "JPEG コスチュームを圧縮",
        svg: "SVG コスチュームを最適化", wav: "WAV 音声を圧縮",
        mp3: "MP3 音声を圧縮", other: "その他メディアを圧縮"
      },
      stats: {
        blocks_renamed: "ブロック ID を短縮",
        vars_renamed: "変数名を短縮",
        lists_renamed: "リスト名を短縮",
        broadcasts_renamed: "ブロードキャスト名を短縮",
        fields_removed: "既定フィールドを削除",
        monitors_updated: "モニターを更新",
        click_rewrites: "クリックの書き換え",
        vars_removed: "未使用の変数を削除",
        lists_removed: "未使用のリストを削除",
        procs_renamed: "カスタムブロック名を短縮",
        args_renamed: "引数名を短縮",
        obscured_shadows_removed: "隠れた既定値を削除",
        unreachable_blocks_removed: "到達しないブロックを削除",
        unreachable_comments_removed: "到達しないコメントを削除",
        broadcasts_removed: "未使用のブロードキャストを削除",
        procs_removed: "未使用の定義を削除",
        vars_initialized: "変数の初期値を空に",
        lists_initialized: "リストの初期値を空に",
        duplicates_extracted: "重複したコードを抽出",
        dup_blocks_saved: "重複で削減したブロック",
        near_duplicates_extracted: "似たコードを統合",
        near_blocks_saved: "似たコードで削減したブロック",
        ifelse_converted: "if-else を if に",
        noop_procs_removed: "何もしない定義を削除",
        noop_calls_removed: "何もしない呼び出しを削除",
        noop_receivers_removed: "何もしない受信を削除",
        noop_broadcasts_removed: "不要なブロードキャストを削除",
        noop_messages_removed: "不要なメッセージを削除",
        procs_inlined: "1回だけの定義を展開",
        const_values_folded: "定数計算を畳み込み",
        loops_created: "repeat ループを作成",
        loop_blocks_saved: "ループで削減したブロック",
        const_vars_inlined: "定数変数を値に置換",
        const_reads_inlined: "定数の参照を置換",
        arg_ids_shortened: "引数 ID を短縮",
        mutation_keys_removed: "mutation キーを削除",
        monitors_removed: "モニターを削除",
        comments_removed: "コメントを削除",
        workspace_compacted: "ワークスペースを再配置",
        float_values_rounded: "小数を丸め"
      }
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

  var PROJECT_KEYS = [
    "stripDefaults", "shortenIds", "removeUnused", "clearInitialValues",
    "dropObscuredShadows", "removeUnreachable", "extractDuplicates", "nearDuplicates",
    "loopDuplicates", "inlineSingleCall", "removeNoops", "simplifyIfElse",
    "compressProcs", "freqIds", "foldConstants", "propagateConstants", "clickToStage"
  ];
  var PROJECT_KEY = "sb3-full-project-v1";
  var MEDIA_KEY = "sb3-full-media-v1";
  var THEME_KEY = "sb3-full-theme-v1";

  var el = {
    dropzone: document.getElementById("dropzone"),
    fileInput: document.getElementById("fileInput"),
    fileRow: document.getElementById("fileRow"),
    fileName: document.getElementById("fileName"),
    fileSize: document.getElementById("fileSize"),
    clearBtn: document.getElementById("clearBtn"),
    resetOptions: document.getElementById("resetOptions"),
    strengthWrap: document.getElementById("strengthWrap"),
    autoExtra: document.getElementById("autoExtra"),
    optPngOptimize: document.getElementById("optPngOptimize"),
    optWavMp3: document.getElementById("optWavMp3"),
    wavMp3Bitrate: document.getElementById("wavMp3Bitrate"),
    optMp3Reenc: document.getElementById("optMp3Reenc"),
    mp3Bitrate: document.getElementById("mp3Bitrate"),
    jsonSizes: document.getElementById("jsonSizes"),
    mediaSizes: document.getElementById("mediaSizes"),
    fileSizes: document.getElementById("fileSizes"),
    jsonKept: document.getElementById("jsonKept"),
    jsonKeptLabel: document.getElementById("jsonKeptLabel"),
    jsonRemoved: document.getElementById("jsonRemoved"),
    mediaKept: document.getElementById("mediaKept"),
    mediaKeptLabel: document.getElementById("mediaKeptLabel"),
    mediaRemoved: document.getElementById("mediaRemoved"),
    fileKept: document.getElementById("fileKept"),
    fileKeptLabel: document.getElementById("fileKeptLabel"),
    fileRemoved: document.getElementById("fileRemoved"),
    statsDetails: document.getElementById("statsDetails"),
    statsList: document.getElementById("statsList"),
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
    cancelBtn: document.getElementById("cancelBtn"),
    ledger: document.getElementById("ledger"),
    ledgerSummary: document.getElementById("ledgerSummary"),
    ledgerToggle: document.getElementById("ledgerToggle"),
    ledgerList: document.getElementById("ledgerList"),
    projStats: document.getElementById("projStats")
  };

  var projectInputs = Array.prototype.slice.call(document.querySelectorAll("input[data-popt]"));
  var strengthButtons = Array.prototype.slice.call(document.querySelectorAll("button[data-strength]"));
  var themeButtons = Array.prototype.slice.call(document.querySelectorAll("button[data-theme-set]"));

  var worker = null;
  var currentFile = null;
  var scan = null;
  var result = null;
  var objectUrl = null;
  var running = false;
  var stale = false;
  var staleAfterRun = false;
  var strength = "balanced";
  var runId = 0;
  var ledgerOpen = true;
  var poolSize = 0;
  var deltaEls = new Map();

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
  function loadJSON(key, fallback) {
    try { var v = JSON.parse(localStorage.getItem(key) || "null"); return v || fallback; }
    catch (_) { return fallback; }
  }
  function saveJSON(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) { /* ignore */ }
  }

  function readProjectOptions() {
    var out = {};
    projectInputs.forEach(function (input) {
      out[input.getAttribute("data-popt")] = input.checked;
    });
    return out;
  }
  function applyProjectOptions(values) {
    projectInputs.forEach(function (input) {
      var key = input.getAttribute("data-popt");
      input.checked = values[key] === true;
    });
  }
  function defaultProjectOptions() {
    var out = {};
    PROJECT_KEYS.forEach(function (key) { out[key] = key !== "clickToStage"; });
    return out;
  }

  function readMediaOptions() {
    var out = { pngOptimize: false, wavToMp3: false, wavMp3Bitrate: 96, reencodeMp3: false, mp3Bitrate: 96 };
    try {
      var s = JSON.parse(localStorage.getItem(MEDIA_KEY) || "null");
      if (s && typeof s === "object") {
        out.pngOptimize = s.pngOptimize === true;
        out.wavToMp3 = !!s.wavToMp3;
        out.reencodeMp3 = !!s.reencodeMp3;
        if ([64, 96, 128].indexOf(Number(s.wavMp3Bitrate)) >= 0) out.wavMp3Bitrate = Number(s.wavMp3Bitrate);
        if ([64, 96, 128].indexOf(Number(s.mp3Bitrate)) >= 0) out.mp3Bitrate = Number(s.mp3Bitrate);
      }
    } catch (_) { /* ignore */ }
    return out;
  }
  function applyMediaOptions(a) {
    if (el.optPngOptimize) el.optPngOptimize.checked = a.pngOptimize === true;
    if (el.optWavMp3) el.optWavMp3.checked = !!a.wavToMp3;
    if (el.optMp3Reenc) el.optMp3Reenc.checked = !!a.reencodeMp3;
    if (el.wavMp3Bitrate) el.wavMp3Bitrate.value = String(a.wavMp3Bitrate);
    if (el.mp3Bitrate) el.mp3Bitrate.value = String(a.mp3Bitrate);
  }
  function saveMediaOptions() {
    saveJSON(MEDIA_KEY, {
      pngOptimize: !!(el.optPngOptimize && el.optPngOptimize.checked),
      wavToMp3: !!(el.optWavMp3 && el.optWavMp3.checked),
      reencodeMp3: !!(el.optMp3Reenc && el.optMp3Reenc.checked),
      wavMp3Bitrate: el.wavMp3Bitrate ? parseInt(el.wavMp3Bitrate.value, 10) : 96,
      mp3Bitrate: el.mp3Bitrate ? parseInt(el.mp3Bitrate.value, 10) : 96
    });
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
  function revokeUrl() { if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null; } }

  function renderMix(info) {
    var mix = (info && info.mix) || { image: 0, vector: 0, audio: 0 };
    var total = mix.image + mix.vector + mix.audio;
    if (!total) {
      el.mixImage.style.width = "100%"; el.mixVector.style.width = "0%"; el.mixAudio.style.width = "0%";
      el.mixTotal.textContent = "0 B";
      el.mix.setAttribute("aria-label", L.mixNone);
      return;
    }
    var pi = mix.image / total * 100, pv = mix.vector / total * 100, pa = mix.audio / total * 100;
    el.mixImage.style.width = pi + "%";
    el.mixVector.style.width = pv + "%";
    el.mixAudio.style.width = pa + "%";
    el.mixTotal.textContent = humanSize(total);
    el.mix.setAttribute("aria-label", fmt(L.mixAria, { image: pi.toFixed(0), vector: pv.toFixed(0), audio: pa.toFixed(0) }));
  }

  function setBar(keptEl, keptLabelEl, removedEl, ratio) {
    var r = Number(ratio) || 0;
    var removed = Math.max(0, Math.min(100, r));
    var kept = Math.max(0, Math.min(100, 100 - r));
    if (keptEl) keptEl.style.width = kept + "%";
    if (removedEl) removedEl.style.width = removed + "%";
    if (keptLabelEl) keptLabelEl.textContent = Math.round(kept) + "%";
  }
  function resetBars() {
    [[el.jsonKept, el.jsonKeptLabel, el.jsonRemoved],
     [el.mediaKept, el.mediaKeptLabel, el.mediaRemoved],
     [el.fileKept, el.fileKeptLabel, el.fileRemoved]].forEach(function (t) {
      if (t[0]) t[0].style.width = "100%";
      if (t[2]) t[2].style.width = "0%";
      if (t[1]) t[1].textContent = "—";
    });
  }
  function statRow(label, value) {
    var row = document.createElement("div");
    var dt = document.createElement("dt");
    dt.textContent = label;
    var dd = document.createElement("dd");
    dd.textContent = Number(value).toLocaleString("en-US");
    row.appendChild(dt);
    row.appendChild(dd);
    return row;
  }
  function renderStats(data) {
    if (!el.statsList) return;
    el.statsList.textContent = "";
    var added = 0;
    if (data.changedCount) { el.statsList.appendChild(statRow(L.statMediaShrunk, data.changedCount)); added++; }
    if (data.convertedCount) { el.statsList.appendChild(statRow(L.statConverted, data.convertedCount)); added++; }
    var keptAsIs = (data.assetCount || 0) - (data.changedCount || 0);
    if (keptAsIs > 0) { el.statsList.appendChild(statRow(L.statKeptAsIs, keptAsIs)); added++; }
    var kinds = {};
    (data.results || []).forEach(function (r) {
      if (!r.changed) return;
      var k = r.ext === "jpeg" ? "jpg" : r.ext;
      if (!L.statKind[k]) k = "other";
      kinds[k] = (kinds[k] || 0) + 1;
    });
    Object.keys(L.statKind).forEach(function (k) {
      if (kinds[k]) { el.statsList.appendChild(statRow(L.statKind[k], kinds[k])); added++; }
    });
    var ps = data.projectStats || {};
    Object.keys(L.stats).forEach(function (key) {
      var v = Number(ps[key] || 0);
      if (v > 0) { el.statsList.appendChild(statRow(L.stats[key], v)); added++; }
    });
    el.statsDetails.hidden = added === 0;
  }

  function resetReadout() {
    el.jsonSizes.textContent = "—";
    el.mediaSizes.textContent = "—";
    el.fileSizes.textContent = "—";
    resetBars();
    if (el.statsDetails) el.statsDetails.hidden = true;
    if (el.statsList) el.statsList.textContent = "";
    el.figureNum.textContent = "0.0";
    el.figureLabel.textContent = L.smallerFile;
    el.downloadBtn.disabled = true;
    el.downloadBtn.textContent = L.downloadSb3;
    if (el.projStats) el.projStats.textContent = "";
    renderMix(null);
    setProgress(0);
    setPhase(L.ready);
    setMessage(L.chooseProject, false);
  }

  function resetAll() {
    runId += 1;
    revokeUrl();
    result = null; scan = null; currentFile = null;
    stale = false; staleAfterRun = false;
    el.fileRow.hidden = true;
    el.fileName.textContent = "project.sb3";
    el.fileSize.textContent = "—";
    el.fileInput.value = "";
    el.runAgainBtn.hidden = true;
    el.cancelBtn.hidden = true;
    el.ledger.hidden = true;
    setBusy(false);
    stopWorker();
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

  // ------------------------------------------------------------- ledger

  function badgeClass(kind) {
    if (kind === "image") return "image";
    if (kind === "vector") return "vector";
    if (kind === "wav" || kind === "mp3" || kind === "audio") return "audio";
    return "";
  }
  function sizeText(asset) {
    var bits = [humanSize(asset.size)];
    if (asset.width && asset.height) bits.push(asset.width + "×" + asset.height);
    if (asset.duration) bits.push(asset.duration.toFixed(2) + "s");
    if (asset.sampleRate) bits.push((asset.sampleRate / 1000).toFixed(1) + "k");
    if (asset.channels) bits.push(asset.channels + "ch");
    return bits.join(" · ");
  }

  function renderResults(results, origMedia, changedCount) {
    el.ledgerList.textContent = "";
    if (!results || !results.length) { el.ledger.hidden = true; return; }
    el.ledger.hidden = false;
    results.forEach(function (r) {
      var row = document.createElement("div");
      row.className = "ledger-row";

      var badge = document.createElement("span");
      badge.className = "badge " + badgeClass(r.kind);
      badge.textContent = (L.glyph[r.ext] || L.glyph[r.kind] || r.ext || "").toUpperCase();
      row.appendChild(badge);

      var nameCell = document.createElement("div");
      nameCell.className = "asset-name";
      var file = document.createElement("span");
      file.className = "file";
      file.textContent = r.name !== r.origName ? (r.origName + " → " + r.name) : r.origName;
      file.title = file.textContent;
      var meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = humanSize(r.origSize);
      nameCell.appendChild(file);
      nameCell.appendChild(meta);
      row.appendChild(nameCell);

      var control = document.createElement("div");
      control.className = "asset-control";
      var hint = document.createElement("span");
      hint.className = "asset-hint";
      hint.textContent = r.changed ? (r.note || r.method || "") : L.keptOriginal;
      control.appendChild(hint);
      row.appendChild(control);

      var delta = document.createElement("div");
      delta.className = "asset-delta" + (r.changed ? " is-saved" : "");
      delta.textContent = "";
      var from = document.createElement("span");
      from.className = "from"; from.textContent = humanSize(r.origSize);
      var arrow = document.createElement("span");
      arrow.className = "arrow"; arrow.textContent = "→";
      var to = document.createElement("span");
      to.className = "to"; to.textContent = humanSize(r.newSize);
      delta.appendChild(from); delta.appendChild(arrow); delta.appendChild(to);
      row.appendChild(delta);

      el.ledgerList.appendChild(row);
    });
    var summary = fmt(L.ledgerTitle, { count: results.length, media: humanSize(origMedia || 0) });
    if (changedCount != null) summary += " · " + fmt(L.ledgerShrunk, { changed: changedCount });
    el.ledgerSummary.textContent = summary;
    el.ledgerToggle.hidden = false;
  }

  // --------------------------------------------------------------- file

  function chooseFile() { el.fileInput.value = ""; el.fileInput.click(); }
  function isSb3(name) { return /\.sb3$/i.test(name || ""); }

  function handleFile(file) {
    if (!file) return;
    if (!isSb3(file.name)) { showError(L.invalidFile); return; }
    if (!file.size) { showError(L.emptyFile); return; }
    stopWorker();
    running = false;
    runId += 1;
    revokeUrl();
    result = null; scan = null;
    stale = false; staleAfterRun = false;
    currentFile = file;
    el.fileName.textContent = file.name;
    el.fileSize.textContent = humanSize(file.size);
    el.fileRow.hidden = false;
    el.runAgainBtn.hidden = true;
    el.downloadBtn.disabled = true;
    el.cancelBtn.hidden = true;
    resetReadout();
    startRun();
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
      .then(function () { return loadScript(APP_BASE + "media.js"); })
      .then(function () { return loadScript(APP_BASE + "project.js"); })
      .then(function () { return loadScript(APP_BASE + "engine.js"); })
      .then(function () {
        if (!window.JSZip || !window.MEDIA || !window.SB3 || !window.FULL) throw new Error(L.engineMissing);
        window.MEDIA.setJSZip(window.JSZip);
        window.SB3.setJSZip(window.JSZip);
      })
      .catch(function (error) { mainThreadEngine = null; throw error; });
    return mainThreadEngine;
  }

  function stopWorker() { if (worker) { worker.terminate(); worker = null; poolSize = 0; } }

  function createWorker(myRun, fallback) {
    var fellBack = { value: false };
    if (!worker) {
      try { worker = new Worker(APP_BASE + "worker.js"); }
      catch (error) { fallback(); return; }
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

  function readOptions() {
    var media = readMediaOptions();
    return {
      media: {
        mode: "auto", strength: strength,
        pngOptimize: media.pngOptimize, wavToMp3: media.wavToMp3,
        wavMp3Bitrate: media.wavMp3Bitrate, reencodeMp3: media.reencodeMp3,
        mp3Bitrate: media.mp3Bitrate
      },
      project: readProjectOptions()
    };
  }

  function startRun() {
    if (!currentFile) { showError(L.chooseFirst); return; }
    runId += 1;
    var myRun = runId;
    running = true;
    stale = false; staleAfterRun = false;
    revokeUrl();
    result = null;
    el.runAgainBtn.hidden = true;
    el.cancelBtn.hidden = false;
    el.downloadBtn.disabled = true;
    el.fileSizes.textContent = humanSize(currentFile.size) + "  →  —";
    el.jsonSizes.textContent = "—";
    el.mediaSizes.textContent = "—";
    el.figureNum.textContent = "0.0";
    el.figureLabel.textContent = L.measuring;
    if (el.projStats) el.projStats.textContent = "";
    el.ledger.hidden = true;
    el.ledgerList.textContent = "";
    setProgress(0);
    setPhase(PHASE_LABELS.load);
    setMessage(fmt(L.reading, { name: currentFile.name }), false);
    setBusy(true);

    var options = readOptions();
    var file = currentFile;
    file.arrayBuffer().then(function (buffer) {
      if (!running || myRun !== runId) return;
      if (window.location.protocol === "file:") { runOnMainThread(buffer, file, myRun, options); return; }
      createWorker(myRun, function () { runOnMainThread(buffer, file, myRun, options); });
      worker.postMessage({ type: "compress", buffer: buffer, filename: file.name, options: options, plan: null }, [buffer]);
    }).catch(function (error) {
      if (myRun !== runId) return;
      running = false; setBusy(false);
      showError(fmt(L.readFileError, { error: error && error.message ? error.message : error }));
    });
  }

  function runOnMainThread(buffer, file, myRun, options) {
    setPhase(L.loadingEngine);
    setMessage(L.mainThreadNote, false);
    loadMainThreadEngine().then(function () {
      if (myRun !== runId) return;
      el.cancelBtn.hidden = true;
      return window.FULL.compressBuffer(buffer, file.name, options, null, function (phase, frac, message) {
        if (myRun !== runId) return;
        setProgress(window.FULL.progressPercent(phase, frac));
        setPhase(PHASE_LABELS[phase] || PHASE_LABELS.other);
        if (message) setMessage(message, false);
      });
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

  function onWorkerMessage(event) {
    var data = event.data || {};
    if (data.type === "pool") { poolSize = data.size || 0; return; }
    if (data.type === "scanned") {
      running = false;
      setBusy(false);
      el.cancelBtn.hidden = true;
      scan = data.scan;
      renderMix(scan);
      return;
    }
    if (data.type === "progress") {
      if (!running) return;
      setProgress(data.percent || 0);
      setPhase(PHASE_LABELS[data.phase] || PHASE_LABELS.other);
      if (data.message) {
        var msg = data.message;
        if (data.phase === "media" && poolSize > 1) msg += " " + fmt(L.threadsNote, { n: poolSize });
        setMessage(msg, false);
      }
      return;
    }
    if (data.type === "error") {
      running = false; stopWorker(); setBusy(false);
      el.cancelBtn.hidden = true;
      showError(data.message || L.compressionFailed);
      return;
    }
    if (data.type === "done") {
      running = false;
      setBusy(false);
      el.cancelBtn.hidden = true;
      finish(data);
    }
  }

  function finish(data) {
    var bytes = data.finalBytes instanceof Uint8Array ? data.finalBytes : new Uint8Array(data.finalBytes);
    var outputName = data.outputName || "project_full.sb3";
    revokeUrl();
    objectUrl = URL.createObjectURL(new Blob([bytes], { type: "application/zip" }));
    result = {
      bytes: bytes, name: outputName,
      origFileSize: data.origFileSize, newFileSize: data.newFileSize, fileRatio: data.fileRatio,
      origJsonSize: data.origJsonSize, newJsonSize: data.newJsonSize, jsonRatio: data.jsonRatio,
      origMediaSize: data.origMediaSize, newMediaSize: data.newMediaSize, mediaRatio: data.mediaRatio,
      assetCount: data.assetCount, changedCount: data.changedCount, convertedCount: data.convertedCount,
      results: data.results || [], projectStats: data.projectStats || {}
    };

    var ratio = Number(data.fileRatio) || 0;
    el.figureNum.textContent = Math.abs(ratio).toFixed(1);
    el.figureLabel.textContent = ratio >= 0 ? L.smallerFile : L.largerFile;

    el.jsonSizes.textContent = humanSize(data.origJsonSize) + "  →  " + humanSize(data.newJsonSize);
    el.mediaSizes.textContent = humanSize(data.origMediaSize) + "  →  " + humanSize(data.newMediaSize);
    el.fileSizes.textContent = humanSize(data.origFileSize) + "  →  " + humanSize(data.newFileSize);
    setBar(el.jsonKept, el.jsonKeptLabel, el.jsonRemoved, data.jsonRatio);
    setBar(el.mediaKept, el.mediaKeptLabel, el.mediaRemoved, data.mediaRatio);
    setBar(el.fileKept, el.fileKeptLabel, el.fileRemoved, data.fileRatio);
    renderStats(data);
    renderMix(data);

    if (el.projStats) el.projStats.textContent = projectSummary(data.projectStats);

    el.downloadBtn.disabled = false;
    renderResults(result.results, data.origMediaSize, data.changedCount);

    setProgress(100);
    setPhase(L.complete);
    var msg = fmt(L.downloadReady, { name: outputName });
    if (poolSize > 1) msg += " " + fmt(L.threadsNote, { n: poolSize });
    setMessage(msg, false);

    if (staleAfterRun) { staleAfterRun = false; markStale(); }
  }

  function projectSummary(stats) {
    var s = stats || {};
    var pick = [
      ["blocks renamed", s.blocks_renamed], ["stores renamed", (s.vars_renamed || 0) + (s.lists_renamed || 0)],
      ["defaults removed", s.fields_removed], ["unused vars/lists", (s.vars_removed || 0) + (s.lists_removed || 0)],
      ["unreachable blocks", s.unreachable_blocks_removed], ["duplicates", s.duplicates_extracted],
      ["near-duplicates", s.near_duplicates_extracted], ["loops", s.loops_created],
      ["folded values", s.const_values_folded], ["defs inlined", s.procs_inlined]
    ];
    return pick.filter(function (p) { return Number(p[1]) > 0; })
      .map(function (p) { return p[0] + " " + Number(p[1]).toLocaleString("en-US"); })
      .join(" · ");
  }

  function cancelRun() {
    if (!running) return;
    runId += 1;
    stopWorker();
    running = false;
    setBusy(false);
    el.cancelBtn.hidden = true;
    el.runAgainBtn.hidden = !currentFile;
    el.downloadBtn.disabled = !result;
    setPhase(L.cancelled);
    setMessage(L.cancelMessage, false);
    setProgress(0);
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
    themeButtons.forEach(function (button) {
      button.setAttribute("aria-pressed", String(button.getAttribute("data-theme-set") === (dark ? "dark" : "light")));
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
  el.clearBtn.addEventListener("click", function () { if (running) cancelRun(); resetAll(); });
  el.runAgainBtn.addEventListener("click", startRun);
  el.cancelBtn.addEventListener("click", cancelRun);
  el.downloadBtn.addEventListener("click", function () {
    if (!result || !objectUrl) return;
    var link = document.createElement("a");
    link.href = objectUrl; link.download = result.name;
    document.body.appendChild(link); link.click(); link.remove();
    setMessage(fmt(L.downloaded, { name: result.name }), false);
  });

  strengthButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      strength = button.getAttribute("data-strength");
      saveJSON(MEDIA_KEY, Object.assign(readMediaOptions(), { strength: strength }));
      strengthButtons.forEach(function (b) {
        b.setAttribute("aria-pressed", String(b.getAttribute("data-strength") === strength));
      });
      if (running) staleAfterRun = true; else markStale();
    });
  });

  [el.optPngOptimize, el.optWavMp3, el.wavMp3Bitrate, el.optMp3Reenc, el.mp3Bitrate].forEach(function (control) {
    if (control) control.addEventListener("change", function () {
      saveMediaOptions();
      
      if (running) staleAfterRun = true; else markStale();
    });
  });

  projectInputs.forEach(function (input) {
    input.addEventListener("change", function () {
      saveJSON(PROJECT_KEY, readProjectOptions());
      if (running) staleAfterRun = true; else markStale();
    });
  });

  themeButtons.forEach(function (button) {
    button.addEventListener("click", function () { setTheme(button.getAttribute("data-theme-set"), true); });
  });

  el.resetOptions.addEventListener("click", function () {
    strength = "balanced";
    strengthButtons.forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-strength") === strength));
    });
    applyProjectOptions(defaultProjectOptions());
    applyMediaOptions({ pngOptimize: false, wavToMp3: false, reencodeMp3: false, wavMp3Bitrate: 96, mp3Bitrate: 96 });
    saveJSON(PROJECT_KEY, readProjectOptions());
    saveMediaOptions();
    saveJSON(MEDIA_KEY, Object.assign(readMediaOptions(), { strength: strength }));
    
    setMessage(L.optionsReset, false);
    if (running) staleAfterRun = true; else markStale();
  });

  el.ledgerToggle.addEventListener("click", function () {
    ledgerOpen = !ledgerOpen;
    el.ledgerList.hidden = !ledgerOpen;
    el.ledgerToggle.textContent = ledgerOpen ? L.hideList : L.showList;
  });

  var dragDepth = 0;
  function hasFiles(event) {
    var types = event.dataTransfer && event.dataTransfer.types;
    if (!types) return false;
    for (var i = 0; i < types.length; i++) if (types[i] === "Files") return true;
    return false;
  }
  window.addEventListener("dragenter", function (event) { if (!hasFiles(event)) return; event.preventDefault(); dragDepth += 1; el.dropzone.classList.add("is-dragging"); });
  window.addEventListener("dragover", function (event) { if (!hasFiles(event)) return; event.preventDefault(); event.dataTransfer.dropEffect = "copy"; });
  window.addEventListener("dragleave", function (event) { if (!hasFiles(event)) return; dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) el.dropzone.classList.remove("is-dragging"); });
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
    var onSchemeChange = function (event) { if (storedTheme()) return; setTheme(event.matches ? "dark" : "light", false); };
    if (scheme.addEventListener) scheme.addEventListener("change", onSchemeChange);
    else if (scheme.addListener) scheme.addListener(onSchemeChange);
  }

  var mediaStored = readMediaOptions();
  strength = mediaStored.strength && ["light", "balanced", "strong"].indexOf(mediaStored.strength) >= 0
    ? mediaStored.strength : "balanced";
  strengthButtons.forEach(function (b) {
    b.setAttribute("aria-pressed", String(b.getAttribute("data-strength") === strength));
  });
  applyMediaOptions(mediaStored);
  var projectStored = loadJSON(PROJECT_KEY, null);
  applyProjectOptions(projectStored ? Object.assign(defaultProjectOptions(), projectStored) : defaultProjectOptions());
  resetReadout();
})();
