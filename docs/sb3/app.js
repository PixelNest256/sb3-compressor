/* SB3 Compressor — page controller. */
(function () {
  "use strict";

  var LANG = /^ja\b/i.test(document.documentElement.lang || "") ? "ja" : "en";

  var STRINGS = {
    en: {
      phases: {
        load: "Reading file",
        parse: "Parsing project.json",
        collect: "Analyzing stores",
        targets: "Compressing scripts",
        finalize: "Finalizing project",
        serialize: "Writing project.json",
        package: "Repacking .sb3",
        other: "Compressing"
      },
      phaseMessages: null,
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
        mutation_keys_removed: "legacy mutation keys removed",
        monitors_removed: "hidden monitors removed",
        comments_removed: "comments removed",
        workspace_compacted: "workspace blocks re-flowed",
        float_values_rounded: "long decimals rounded"
      },
      ready: "Ready",
      settingsChanged: "Settings changed",
      runAgainPrompt: "Run again to apply the new options.",
      failed: "Failed",
      complete: "Complete",
      cancelled: "Cancelled",
      cancelMessage: "Compression cancelled. The file is still loaded.",
      chooseProject: "Choose a project to begin.",
      noFileMeasured: "no file measured yet",
      measuring: "measuring project.json",
      smaller: "smaller project.json",
      larger: "larger project.json",
      downloadSb3: "Download .sb3",
      downloadJson: "Download .json",
      reading: "Reading {name}…",
      compressing: "Compressing",
      compressingProject: "Compressing {name}. This can take a moment.",
      loadingEngine: "Loading engine",
      mainThreadNote: "Running in this tab instead of a background worker. Keep the tab open.",
      mainThreadError: "The compressor could not start in this tab: {error} Serving the page over HTTP, for example with python -m http.server, avoids this.",
      readFileError: "Could not read that file: {error}",
      loadScriptError: "Could not load {src}.",
      engineMissing: "The compressor engine did not start.",
      compressionFailed: "Compression failed.",
      invalidFile: "Choose a .sb3 file or a project.json file.",
      emptyFile: "That file is empty. Choose a Scratch project.",
      chooseFirst: "Choose a .sb3 or project.json file first.",
      optionsReset: "Options reset. Run again to apply them.",
      downloaded: "Downloaded {name}.",
      downloadReady: "Ready to download {name}.",
      noStructuralChanges: "no structural changes counted",
      gaugeKept: "{kept}% kept",
      gaugeAria: "Compression gauge: {kept} percent of project.json kept, {removed} percent removed.",
      gaugeNone: "No compression measured yet",
      gaugeRunning: "Compressing project"
    },
    ja: {
      phases: {
        load: "ファイル読み込み",
        parse: "project.json 解析",
        collect: "変数とリストの解析",
        targets: "スクリプト圧縮",
        finalize: "仕上げ",
        serialize: "JSON 書き出し",
        package: ".sb3 再パッケージ",
        other: "圧縮中"
      },
      phaseMessages: {
        load: "ファイルを読み込んでいます…",
        parse: "project.json を解析しています…",
        collect: "変数とリストを解析しています…",
        targets: "スクリプトを圧縮しています…",
        finalize: "プロジェクトを仕上げています…",
        serialize: "JSON を書き出しています…",
        package: ".sb3 を再パッケージしています…"
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
        mutation_keys_removed: "旧形式の mutation キーを削除",
        monitors_removed: "非表示モニターを削除",
        comments_removed: "コメントを削除",
        workspace_compacted: "ブロックの配置を再構成",
        float_values_rounded: "長い小数を丸め"
      },
      ready: "準備完了",
      settingsChanged: "設定を変更しました",
      runAgainPrompt: "新しい設定で再実行してください。",
      failed: "失敗",
      complete: "完了",
      cancelled: "キャンセル",
      cancelMessage: "圧縮を中止しました。ファイルは読み込まれたままです。",
      chooseProject: "プロジェクトを選ぶと開始します。",
      noFileMeasured: "まだファイルがありません",
      measuring: "project.json を計測中",
      smaller: "project.json の削減率",
      larger: "project.json が増えました",
      downloadSb3: ".sb3 をダウンロード",
      downloadJson: ".json をダウンロード",
      reading: "{name} を読み込んでいます…",
      compressing: "圧縮しています",
      compressingProject: "{name} を圧縮しています。少しお待ちください。",
      loadingEngine: "エンジンを読み込み中",
      mainThreadNote: "バックグラウンドではなく、このタブ内で実行します。タブを閉じずにお待ちください。",
      mainThreadError: "このタブ内で圧縮を開始できませんでした: {error} ページを HTTP で配信すると回避できます（例: python -m http.server）。",
      readFileError: "ファイルを読み込めませんでした: {error}",
      loadScriptError: "{src} を読み込めませんでした。",
      engineMissing: "圧縮エンジンが起動しませんでした。",
      compressionFailed: "圧縮に失敗しました。",
      invalidFile: ".sb3 または project.json を選んでください。",
      emptyFile: "ファイルが空です。Scratch プロジェクトを選んでください。",
      chooseFirst: "先に .sb3 または project.json を選んでください。",
      optionsReset: "設定を初期値に戻しました。再実行すると反映されます。",
      downloaded: "{name} をダウンロードしました。",
      downloadReady: "{name} をダウンロードできます。",
      noStructuralChanges: "構造の変更はありません",
      gaugeKept: "{kept}% 残存",
      gaugeAria: "圧縮ゲージ: project.json の {kept}% が残り、{removed}% を削減しました。",
      gaugeNone: "まだ計測結果はありません",
      gaugeRunning: "プロジェクトを圧縮中"
    }
  };

  var L = STRINGS[LANG];

  function fmt(template, vars) {
    return String(template).replace(/\{(\w+)\}/g, function (match, key) {
      return vars && Object.prototype.hasOwnProperty.call(vars, key) ? vars[key] : match;
    });
  }

  // The page may live in a subdirectory (for example /ja/), so resolve the
  // worker and engine files from this script's own location.
  var APP_BASE = (function () {
    var script = document.currentScript;
    var src = script && script.src ? script.src : window.location.href;
    try {
      return new URL(".", src).href;
    } catch (_) {
      return "";
    }
  })();

  var DEFAULTS = {
    stripDefaults: true,
    shortenIds: true,
    clickToStage: false,
    removeUnused: true,
    compressProcs: true,
    freqIds: true,
    dropObscuredShadows: true,
    removeUnreachable: true,
    clearInitialValues: true,
    extractDuplicates: true,
    nearDuplicates: true,
    simplifyIfElse: true,
    removeNoops: true,
    inlineSingleCall: true,
    foldConstants: true,
    loopDuplicates: true,
    propagateConstants: true,
    stripComments: false,
    compactWorkspace: false
  };

  var PHASE_LABELS = L.phases;

  // Progress details come from the engine in English; the Japanese page uses
  // a localized description for each phase instead.
  function progressText(phase, detail) {
    if (L.phaseMessages) return L.phaseMessages[phase] || L.compressing;
    return detail;
  }

  var STAT_LABELS = L.stats;

  var KEY_STATS = [
    "blocks_renamed",
    "fields_removed",
    "arg_ids_shortened",
    "unreachable_blocks_removed",
    "monitors_removed",
    "duplicates_extracted",
    "near_duplicates_extracted",
    "loops_created",
    "vars_removed",
    "lists_removed",
    "procs_renamed",
    "const_values_folded",
    "procs_inlined"
  ];

  var STORAGE_KEY = "sb3-compressor-options-v1";

  var el = {
    dropzone: document.getElementById("dropzone"),
    fileInput: document.getElementById("fileInput"),
    fileRow: document.getElementById("fileRow"),
    fileName: document.getElementById("fileName"),
    fileSize: document.getElementById("fileSize"),
    clearBtn: document.getElementById("clearBtn"),
    resetOptions: document.getElementById("resetOptions"),
    jsonSizes: document.getElementById("jsonSizes"),
    fileSizes: document.getElementById("fileSizes"),
    gauge: document.getElementById("gauge"),
    gaugeKept: document.getElementById("gaugeKept"),
    gaugeKeptLabel: document.getElementById("gaugeKeptLabel"),
    gaugeRemoved: document.getElementById("gaugeRemoved"),
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
    stats: document.getElementById("stats"),
    statsKey: document.getElementById("statsKey"),
    statsAll: document.getElementById("statsAll")
  };

  var optionInputs = Array.prototype.slice.call(
    document.querySelectorAll("input[data-opt]")
  );

  var worker = null;
  var currentFile = null;
  var result = null;
  var objectUrl = null;
  var running = false;
  var stale = false;
  var staleAfterRun = false;
  var lastPercent = 0;
  var runId = 0;

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

  function count(n) {
    return Number(n || 0).toLocaleString("en-US");
  }

  function readOptions() {
    var out = {};
    optionInputs.forEach(function (input) {
      out[input.getAttribute("data-opt")] = input.checked;
    });
    return out;
  }

  function mergedOptions() {
    var out = {};
    Object.keys(DEFAULTS).forEach(function (key) {
      out[key] = DEFAULTS[key];
    });
    var stored = null;
    try {
      stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    } catch (_) {
      stored = null;
    }
    if (stored && typeof stored === "object") {
      Object.keys(DEFAULTS).forEach(function (key) {
        if (typeof stored[key] === "boolean") out[key] = stored[key];
      });
    }
    return out;
  }

  function applyOptions(values) {
    optionInputs.forEach(function (input) {
      var key = input.getAttribute("data-opt");
      input.checked = values[key] === true;
    });
  }

  function saveOptions() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(readOptions()));
    } catch (_) {
      /* storage can be unavailable in private modes */
    }
  }

  // ---------------------------------------------------------------- theme

  var THEME_KEY = "sb3-compressor-theme-v1";
  var themeInputs = Array.prototype.slice.call(
    document.querySelectorAll("button[data-theme-set]")
  );

  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function setTheme(theme, persist) {
    var dark = theme === "dark";
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", dark ? "#15180f" : "#e7e8e1");
    themeInputs.forEach(function (button) {
      button.setAttribute(
        "aria-pressed",
        String(button.getAttribute("data-theme-set") === (dark ? "dark" : "light"))
      );
    });
    if (persist) {
      try {
        localStorage.setItem(THEME_KEY, dark ? "dark" : "light");
      } catch (_) {
        /* storage can be unavailable in private modes */
      }
    }
  }

  function storedTheme() {
    try {
      var value = localStorage.getItem(THEME_KEY);
      return value === "dark" || value === "light" ? value : null;
    } catch (_) {
      return null;
    }
  }

  function setPhase(text) {
    el.phaseLabel.textContent = text;
  }

  function setMessage(text, isError) {
    el.runMessage.textContent = text;
    el.runMessage.classList.toggle("is-error", !!isError);
    if (isError) el.runMessage.setAttribute("role", "alert");
    else el.runMessage.removeAttribute("role");
  }

  function setProgress(percent) {
    lastPercent = Math.max(0, Math.min(100, percent));
    el.progressBar.style.width = lastPercent + "%";
    el.percentLabel.textContent = Math.round(lastPercent) + "%";
    el.progress.setAttribute("aria-valuenow", String(Math.round(lastPercent)));
  }

  function setBusy(busy) {
    el.dropzone.classList.toggle("is-busy", !!busy);
  }

  function revokeUrl() {
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      objectUrl = null;
    }
  }

  function resetReadout() {
    el.jsonSizes.textContent = "—";
    el.fileSizes.textContent = "—";
    el.gaugeKept.style.width = "100%";
    el.gaugeRemoved.style.width = "0%";
    el.gaugeKeptLabel.textContent = "—";
    el.figureNum.textContent = "0.0";
    el.figureLabel.textContent = L.noFileMeasured;
    el.downloadBtn.disabled = true;
    el.downloadBtn.textContent = L.downloadSb3;
    el.stats.hidden = true;
    el.statsKey.textContent = "";
    el.statsAll.textContent = "";
    el.gauge.setAttribute("aria-label", L.gaugeNone);
    setProgress(0);
    setPhase(L.ready);
    setMessage(L.chooseProject, false);
  }

  function resetAll() {
    runId += 1;
    revokeUrl();
    result = null;
    currentFile = null;
    stale = false;
    staleAfterRun = false;
    el.fileRow.hidden = true;
    el.fileName.textContent = "project.sb3";
    el.fileSize.textContent = "—";
    el.fileInput.value = "";
    el.runAgainBtn.hidden = true;
    el.cancelBtn.hidden = true;
    setBusy(false);
    resetReadout();
  }

  function markStale() {
    saveOptions();
    if (!currentFile) return;
    if (running) {
      staleAfterRun = true;
      return;
    }
    if (!result) return;
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

  // --------------------------------------------------------------- files

  function chooseFile() {
    el.fileInput.value = "";
    el.fileInput.click();
  }

  function isProjectName(name) {
    return /\.(sb3|json)$/i.test(name || "");
  }

  function handleFile(file) {
    if (!file) return;
    if (!isProjectName(file.name)) {
      showError(L.invalidFile);
      return;
    }
    if (!file.size) {
      showError(L.emptyFile);
      return;
    }

    if (running) {
      runId += 1;
      stopWorker();
      running = false;
      el.cancelBtn.hidden = true;
      setBusy(false);
    }

    revokeUrl();
    result = null;
    stale = false;
    staleAfterRun = false;
    currentFile = file;
    el.fileName.textContent = file.name;
    el.fileSize.textContent = humanSize(file.size);
    el.fileRow.hidden = false;
    el.runAgainBtn.hidden = true;
    el.downloadBtn.disabled = true;
    el.downloadBtn.textContent = /\.json$/i.test(file.name) ? L.downloadJson : L.downloadSb3;
    el.stats.hidden = true;
    startCompression();
  }

  // ------------------------------------------------------------- worker

  var mainThreadEngine = null;

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var script = document.createElement("script");
      script.src = src;
      script.onload = function () {
        script.remove();
        resolve();
      };
      script.onerror = function () {
        script.remove();
        reject(new Error(fmt(L.loadScriptError, { src: src })));
      };
      document.head.appendChild(script);
    });
  }

  function loadMainThreadEngine() {
    if (mainThreadEngine) return mainThreadEngine;
    mainThreadEngine = loadScript(APP_BASE + "jszip.min.js")
      .then(function () { return loadScript(APP_BASE + "compressor.js"); })
      .then(function () {
        if (!window.JSZip || !window.SB3) {
          throw new Error(L.engineMissing);
        }
      })
      .catch(function (error) {
        mainThreadEngine = null;
        throw error;
      });
    return mainThreadEngine;
  }

  function stopWorker() {
    if (worker) {
      worker.terminate();
      worker = null;
    }
  }

  // Used when a Worker cannot be created (for example when the page is
  // opened directly from disk). The compression itself is identical, but it
  // occupies the tab until the readout appears.
  function runOnMainThread(buffer, file, myRun) {
    setPhase(L.loadingEngine);
    setMessage(L.mainThreadNote, false);

    loadMainThreadEngine().then(function () {
      if (myRun !== runId) return;
      el.cancelBtn.hidden = true;
      setPhase(PHASE_LABELS.load);
      setMessage(fmt(L.compressingProject, { name: file.name }), false);
      // Give the browser one frame to paint the message above before the
      // synchronous part of the compression starts.
      return new Promise(function (resolve) { setTimeout(resolve, 40); });
    }).then(function () {
      if (myRun !== runId) return;
      return window.SB3.compressBuffer(
        buffer,
        file.name,
        readOptions(),
        function (phase, frac, message) {
          if (myRun !== runId) return;
          setProgress(window.SB3.progressPercent(phase, frac));
          setPhase(PHASE_LABELS[phase] || PHASE_LABELS.other);
          if (message) setMessage(progressText(phase, message), false);
        }
      );
    }).then(function (out) {
      if (myRun !== runId) return;
      running = false;
      setBusy(false);
      el.cancelBtn.hidden = true;
      finish(out);
    }).catch(function (error) {
      if (myRun !== runId) return;
      running = false;
      setBusy(false);
      el.cancelBtn.hidden = true;
      showError(fmt(L.mainThreadError, {
        error: error && error.message ? error.message : error
      }));
    });
  }

  function startCompression() {
    if (!currentFile) {
      showError(L.chooseFirst);
      return;
    }
    if (running) return;

    running = true;
    runId += 1;
    var myRun = runId;
    stale = false;
    staleAfterRun = false;
    revokeUrl();
    result = null;
    el.runAgainBtn.hidden = true;
    el.cancelBtn.hidden = false;
    el.downloadBtn.disabled = true;
    el.stats.hidden = true;
    el.statsKey.textContent = "";
    el.statsAll.textContent = "";
    el.fileSizes.textContent = humanSize(currentFile.size) + "  →  —";
    el.jsonSizes.textContent = "—";
    el.figureNum.textContent = "0.0";
    el.figureLabel.textContent = L.measuring;
    el.gaugeKept.style.width = "100%";
    el.gaugeRemoved.style.width = "0%";
    el.gaugeKeptLabel.textContent = "—";
    el.gauge.setAttribute("aria-label", L.gaugeRunning);
    setProgress(0);
    setPhase(PHASE_LABELS.load);
    setMessage(fmt(L.reading, { name: currentFile.name }), false);
    setBusy(true);
    stopWorker();

    var file = currentFile;
    currentFile.arrayBuffer().then(function (buffer) {
      if (!running || myRun !== runId) return;

      // A Worker cannot load from a file:// page, so go straight to the
      // in-tab path there instead of producing a security error.
      if (window.location.protocol === "file:") {
        runOnMainThread(buffer, file, myRun);
        return;
      }

      var fellBack = false;
      try {
        worker = new Worker(APP_BASE + "worker.js");
      } catch (error) {
        runOnMainThread(buffer, file, myRun);
        return;
      }

      worker.onmessage = function (event) {
        if (myRun !== runId) return;
        onWorkerMessage(event);
      };
      worker.onerror = function (event) {
        if (event && event.preventDefault) event.preventDefault();
        if (!running || myRun !== runId || fellBack) return;
        // The worker script may be blocked or missing; the same engine can
        // still run in the page.
        fellBack = true;
        stopWorker();
        runOnMainThread(buffer, file, myRun);
      };
      worker.postMessage({
        type: "compress",
        buffer: buffer,
        filename: file.name,
        options: readOptions()
      }, [buffer]);
    }).catch(function (error) {
      if (myRun !== runId) return;
      running = false;
      setBusy(false);
      showError(fmt(L.readFileError, {
        error: error && error.message ? error.message : error
      }));
    });
  }

  function onWorkerMessage(event) {
    var data = event.data || {};
    if (data.type === "progress") {
      if (!running) return;
      setProgress(data.percent || 0);
      setPhase(PHASE_LABELS[data.phase] || PHASE_LABELS.other);
      if (data.message) setMessage(progressText(data.phase, data.message), false);
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

  function finish(data) {
    var bytes = data.finalBytes instanceof Uint8Array
      ? data.finalBytes
      : new Uint8Array(data.finalBytes);
    var isJson = data.container === "json";
    var mime = isJson ? "application/json" : "application/zip";
    var outputName = data.outputName || (isJson ? "project_compressed.json" : "project_compressed.sb3");

    revokeUrl();
    objectUrl = URL.createObjectURL(new Blob([bytes], { type: mime }));
    result = {
      bytes: bytes,
      name: outputName,
      container: data.container,
      ratio: data.ratio,
      origJsonSize: data.origJsonSize,
      newJsonSize: data.newJsonSize,
      origFileSize: data.origFileSize,
      newFileSize: data.newFileSize,
      stats: data.stats || {}
    };

    var ratio = Number(data.ratio) || 0;
    var kept = Math.max(0, Math.min(100, 100 - ratio));
    var removed = Math.max(0, Math.min(100, ratio));
    el.gaugeKept.style.width = kept + "%";
    el.gaugeRemoved.style.width = removed + "%";
    el.gaugeKeptLabel.textContent = fmt(L.gaugeKept, { kept: kept.toFixed(1) });
    el.figureNum.textContent = Math.abs(ratio).toFixed(1);
    el.figureLabel.textContent = ratio >= 0 ? L.smaller : L.larger;
    el.gauge.setAttribute("aria-label", fmt(L.gaugeAria, {
      kept: kept.toFixed(1),
      removed: removed.toFixed(1)
    }));

    el.jsonSizes.textContent = humanSize(data.origJsonSize) + "  →  " + humanSize(data.newJsonSize);
    el.fileSizes.textContent = humanSize(data.origFileSize) + "  →  " + humanSize(data.newFileSize);

    el.downloadBtn.disabled = false;
    el.downloadBtn.textContent = isJson ? L.downloadJson : L.downloadSb3;
    el.stats.hidden = false;
    renderStats(data.stats || {});

    setProgress(100);
    setPhase(L.complete);
    setMessage(fmt(L.downloadReady, { name: outputName }), false);

    if (staleAfterRun) {
      staleAfterRun = false;
      markStale();
    }
  }

  function renderStats(stats) {
    el.statsKey.textContent = "";
    el.statsAll.textContent = "";

    var shown = 0;
    KEY_STATS.forEach(function (key) {
      if (shown >= 6) return;
      var value = Number(stats[key] || 0);
      if (!value) return;
      el.statsKey.appendChild(statRow(STAT_LABELS[key] || key, value));
      shown += 1;
    });
    if (!shown) {
      el.statsKey.appendChild(statRow(L.noStructuralChanges, 0));
    }

    var keys = Object.keys(STAT_LABELS).filter(function (key) {
      return Number(stats[key] || 0) > 0;
    });
    keys.forEach(function (key) {
      var row = document.createElement("div");
      var dt = document.createElement("dt");
      var dd = document.createElement("dd");
      dt.textContent = STAT_LABELS[key];
      dd.textContent = count(stats[key]);
      row.appendChild(dt);
      row.appendChild(dd);
      el.statsAll.appendChild(row);
    });
  }

  function statRow(label, value) {
    var row = document.createElement("div");
    var dt = document.createElement("dt");
    var dd = document.createElement("dd");
    dt.textContent = label;
    dd.textContent = count(value);
    row.appendChild(dt);
    row.appendChild(dd);
    return row;
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

  // -------------------------------------------------------------- events

  el.dropzone.addEventListener("click", chooseFile);
  el.dropzone.addEventListener("keydown", function (event) {
    if (event.key === "Enter" || event.key === " " || event.key === "Spacebar") {
      event.preventDefault();
      chooseFile();
    }
  });

  el.fileInput.addEventListener("change", function () {
    handleFile(el.fileInput.files && el.fileInput.files[0]);
  });

  el.clearBtn.addEventListener("click", function () {
    if (running) cancelRun();
    resetAll();
  });

  el.runAgainBtn.addEventListener("click", startCompression);
  el.cancelBtn.addEventListener("click", cancelRun);

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

  optionInputs.forEach(function (input) {
    input.addEventListener("change", markStale);
  });

  themeInputs.forEach(function (button) {
    button.addEventListener("click", function () {
      setTheme(button.getAttribute("data-theme-set"), true);
    });
  });

  el.resetOptions.addEventListener("click", function () {
    applyOptions(DEFAULTS);
    saveOptions();
    markStale();
    setMessage(L.optionsReset, false);
  });

  // Accept a dropped file anywhere on the page.
  var dragDepth = 0;
  var hasFiles = function (event) {
    var types = event.dataTransfer && event.dataTransfer.types;
    if (!types) return false;
    for (var i = 0; i < types.length; i++) {
      if (types[i] === "Files") return true;
    }
    return false;
  };
  window.addEventListener("dragenter", function (event) {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth += 1;
    el.dropzone.classList.add("is-dragging");
  });
  window.addEventListener("dragover", function (event) {
    if (!hasFiles(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  });
  window.addEventListener("dragleave", function (event) {
    if (!hasFiles(event)) return;
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) el.dropzone.classList.remove("is-dragging");
  });
  window.addEventListener("drop", function (event) {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth = 0;
    el.dropzone.classList.remove("is-dragging");
    var file = event.dataTransfer.files && event.dataTransfer.files[0];
    if (file) handleFile(file);
  });

  // --------------------------------------------------------------- boot

  setTheme(currentTheme(), false);
  var scheme = window.matchMedia
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;
  if (scheme) {
    var onSchemeChange = function (event) {
      if (storedTheme()) return;
      setTheme(event.matches ? "dark" : "light", false);
    };
    if (scheme.addEventListener) scheme.addEventListener("change", onSchemeChange);
    else if (scheme.addListener) scheme.addListener(onSchemeChange);
  }

  applyOptions(mergedOptions());
  resetReadout();
  el.stats.hidden = true;
})();
