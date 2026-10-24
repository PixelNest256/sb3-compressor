/* SB3 Compressor — page controller. */
(function () {
  "use strict";

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
    propagateConstants: true
  };

  var PHASE_LABELS = {
    load: "Reading file",
    parse: "Parsing project.json",
    collect: "Analyzing stores",
    targets: "Compressing scripts",
    finalize: "Finalizing project",
    serialize: "Writing project.json",
    package: "Repacking .sb3"
  };

  var STAT_LABELS = {
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
    const_reads_inlined: "constant reads replaced"
  };

  var KEY_STATS = [
    "blocks_renamed",
    "fields_removed",
    "unreachable_blocks_removed",
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
    el.figureLabel.textContent = "no file measured yet";
    el.downloadBtn.disabled = true;
    el.downloadBtn.textContent = "Download .sb3";
    el.stats.hidden = true;
    el.statsKey.textContent = "";
    el.statsAll.textContent = "";
    el.gauge.setAttribute("aria-label", "No compression measured yet");
    setProgress(0);
    setPhase("Ready");
    setMessage("Choose a project to begin.", false);
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
    setPhase("Settings changed");
    setMessage("Run again to apply the new options.", false);
  }

  function showError(message) {
    setPhase("Failed");
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
      showError("Choose a .sb3 file or a project.json file.");
      return;
    }
    if (!file.size) {
      showError("That file is empty. Choose a Scratch project.");
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
    el.downloadBtn.textContent = /\.json$/i.test(file.name) ? "Download .json" : "Download .sb3";
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
        reject(new Error("Could not load " + src + "."));
      };
      document.head.appendChild(script);
    });
  }

  function loadMainThreadEngine() {
    if (mainThreadEngine) return mainThreadEngine;
    mainThreadEngine = loadScript("jszip.min.js")
      .then(function () { return loadScript("compressor.js"); })
      .then(function () {
        if (!window.JSZip || !window.SB3) {
          throw new Error("The compressor engine did not start.");
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
    setPhase("Loading engine");
    setMessage("Running in this tab instead of a background worker. Keep the tab open.", false);

    loadMainThreadEngine().then(function () {
      if (myRun !== runId) return;
      el.cancelBtn.hidden = true;
      setPhase(PHASE_LABELS.load);
      setMessage("Compressing " + file.name + ". This can take a moment.", false);
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
          setPhase(PHASE_LABELS[phase] || "Compressing");
          if (message) setMessage(message, false);
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
      showError(
        "The compressor could not start in this tab: " +
        (error && error.message ? error.message : error) +
        " Serving the page over HTTP, for example with python -m http.server, avoids this."
      );
    });
  }

  function startCompression() {
    if (!currentFile) {
      showError("Choose a .sb3 or project.json file first.");
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
    el.figureLabel.textContent = "measuring project.json";
    el.gaugeKept.style.width = "100%";
    el.gaugeRemoved.style.width = "0%";
    el.gaugeKeptLabel.textContent = "—";
    el.gauge.setAttribute("aria-label", "Compressing project");
    setProgress(0);
    setPhase(PHASE_LABELS.load);
    setMessage("Reading " + currentFile.name + "…", false);
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
        worker = new Worker("worker.js");
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
      showError("Could not read that file: " + (error && error.message ? error.message : error));
    });
  }

  function onWorkerMessage(event) {
    var data = event.data || {};
    if (data.type === "progress") {
      if (!running) return;
      setProgress(data.percent || 0);
      setPhase(PHASE_LABELS[data.phase] || "Compressing");
      if (data.message) setMessage(data.message, false);
      return;
    }
    if (data.type === "error") {
      running = false;
      stopWorker();
      setBusy(false);
      el.cancelBtn.hidden = true;
      showError(data.message || "Compression failed.");
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
    el.gaugeKeptLabel.textContent = kept.toFixed(1) + "% kept";
    el.figureNum.textContent = Math.abs(ratio).toFixed(1);
    el.figureLabel.textContent = ratio >= 0 ? "smaller project.json" : "larger project.json";
    el.gauge.setAttribute("aria-label",
      "Compression gauge: " + kept.toFixed(1) + " percent of project.json kept, " +
      removed.toFixed(1) + " percent removed.");

    el.jsonSizes.textContent = humanSize(data.origJsonSize) + "  →  " + humanSize(data.newJsonSize);
    el.fileSizes.textContent = humanSize(data.origFileSize) + "  →  " + humanSize(data.newFileSize);

    el.downloadBtn.disabled = false;
    el.downloadBtn.textContent = "Download " + (isJson ? ".json" : ".sb3");
    el.stats.hidden = false;
    renderStats(data.stats || {});

    setProgress(100);
    setPhase("Complete");
    setMessage("Ready to download " + outputName + ".", false);

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
      el.statsKey.appendChild(statRow("no structural changes counted", 0));
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
    setPhase("Cancelled");
    setMessage("Compression cancelled. The file is still loaded.", false);
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
    setMessage("Downloaded " + result.name + ".", false);
  });

  optionInputs.forEach(function (input) {
    input.addEventListener("change", markStale);
  });

  el.resetOptions.addEventListener("click", function () {
    applyOptions(DEFAULTS);
    saveOptions();
    markStale();
    setMessage("Options reset. Run again to apply them.", false);
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

  applyOptions(mergedOptions());
  resetReadout();
  el.stats.hidden = true;
})();
