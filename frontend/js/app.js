/* Page 1 controller: upload + configuration + run analysis.
   On completion, navigates to results.html?job=<job_id> (page 2). */
(function () {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  // ---------- 1. Upload ----------
  const dropzone = $("#dropzone");
  const fileInput = $("#file-input");

  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("dragover"); });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) handleFile(fileInput.files[0]);
  });

  async function handleFile(file) {
    try {
      dropzone.querySelector("span").textContent = "Uploading...";
      const uploaded = await API.uploadFile(file);
      AppState.uploadedFile = uploaded;

      dropzone.querySelector("span").textContent = `${uploaded.filename} (${uploaded.format.toUpperCase()})`;
      renderKvTable("#table-upload", {
        "file_id": uploaded.file_id,
        ...uploaded.metadata,
      });

      $("#cfg-format").value = uploaded.format;
      const isWav = uploaded.format === "wav";
      $("#cfg-samplerate-wrap").classList.toggle("hidden", isWav);
      $("#cfg-dtype-wrap").classList.toggle("hidden", isWav);
      if (isWav && uploaded.metadata.sample_rate) {
        $("#cfg-samplerate").value = uploaded.metadata.sample_rate;
      }

      $("#btn-analyze").disabled = false;
    } catch (e) {
      dropzone.querySelector("span").textContent = "Drop a .iq or .wav file here, or click to browse";
      alert("Upload failed: " + e.message);
    }
  }

  // ---------- 2. Configuration ----------
  $$('input[name="mode"]').forEach(r => r.addEventListener("change", () => {
    const manual = $('input[name="mode"]:checked').value === "manual";
    $("#manual-config").classList.toggle("hidden", !manual);
    $("#auto-config").classList.toggle("hidden", manual);
  }));

  async function loadConfigOptions() {
    const opts = await API.getConfigOptions();
    AppState.configOptions = opts;

    $("#mod-checkboxes").innerHTML = opts.modulations.map(m => checkboxHtml("mod", m, true)).join("");
    $("#deint-checkboxes").innerHTML = opts.deinterleaving_types.map(t => checkboxHtml("deint", t, true)).join("");
    $("#fec-checkboxes").innerHTML = opts.fec_types.map(t => checkboxHtml("fec", t, true)).join("");

    fillSelect("#cfg-manual-mod", opts.modulations, false);
    fillSelect("#cfg-manual-deint", opts.deinterleaving_types, true);
    fillSelect("#cfg-manual-fec", opts.fec_types, true);
  }

  function checkboxHtml(group, value, checked) {
    return `<label><input type="checkbox" data-group="${group}" value="${value}" ${checked ? "checked" : ""}/> ${value}</label>`;
  }

  function fillSelect(sel, values, withNoneOption) {
    $(sel).innerHTML = (withNoneOption ? '<option value="">none</option>' : "") +
      values.map(v => `<option value="${v}">${v}</option>`).join("");
  }

  function checkedValues(group) {
    return $$(`input[data-group="${group}"]:checked`).map(i => i.value);
  }

  function renderKvTable(sel, obj) {
    $(sel).innerHTML = Object.entries(obj).map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("");
  }

  loadConfigOptions().catch(e => console.error("Failed to load config options:", e));

  // ---------- Run analysis ----------
  $("#btn-analyze").addEventListener("click", async () => {
    if (!AppState.uploadedFile) return;
    const mode = $('input[name="mode"]:checked').value;
    const fmt = AppState.uploadedFile.format;

    const payload = {
      file_id: AppState.uploadedFile.file_id,
      format: fmt,
      sample_rate: fmt === "iq" ? Number($("#cfg-samplerate").value || 0) : undefined,
      center_frequency: Number($("#cfg-centerfreq").value || 0),
      iq_dtype: $("#cfg-dtype").value,
      mode,
    };

    if (fmt === "iq" && !payload.sample_rate) {
      alert("Sample rate is required for .iq files (raw I/Q has no header).");
      return;
    }

    if (mode === "manual") {
      payload.manual_modulation = $("#cfg-manual-mod").value || undefined;
      payload.manual_symbol_rate = Number($("#cfg-manual-symrate").value || 0) || undefined;
      payload.manual_deinterleave = $("#cfg-manual-deint").value || undefined;
      payload.manual_fec = $("#cfg-manual-fec").value || undefined;
    } else {
      payload.modulations = checkedValues("mod");
      payload.deinterleaving_enabled = checkedValues("deint").length > 0;
      payload.deinterleaving_types = checkedValues("deint");
      payload.fec_enabled = checkedValues("fec").length > 0;
      payload.fec_types = checkedValues("fec");
    }

    try {
      $("#btn-analyze").disabled = true;
      $("#progress-box").classList.remove("hidden");
      setProgress(0, "Starting...");

      const { job_id } = await API.startAnalysis(payload);
      AppState.jobId = job_id;

      API.watchJob(job_id,
        (state) => setProgress(state.percent || 0, `${state.stage || ""}: ${state.message || ""}`),
        () => {
          setProgress(100, "Complete — opening results...");
          window.location.href = `results.html?job=${encodeURIComponent(job_id)}`;
        },
        (err) => {
          setProgress(0, "Error: " + err);
          alert("Analysis failed: " + err);
          $("#btn-analyze").disabled = false;
        }
      );
    } catch (e) {
      alert("Failed to start analysis: " + e.message);
      $("#btn-analyze").disabled = false;
    }
  });

  function setProgress(percent, text) {
    $("#progress-fill").style.width = percent + "%";
    $("#progress-text").textContent = text;
  }
})();
