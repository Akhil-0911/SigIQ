/* Page 2 controller: fetches a completed job's result and renders it. */
(function () {
  const $ = (sel) => document.querySelector(sel);

  function hide(sel) { $(sel).classList.add("hidden"); }
  function show(sel) { $(sel).classList.remove("hidden"); }

  const jobId = new URLSearchParams(window.location.search).get("job");

  if (!jobId) {
    show("#no-job-msg");
    return;
  }
  hide("#no-job-msg");
  AppState.jobId = jobId;

  API.getResult(jobId)
    .then((result) => {
      AppState.result = result;
      renderResult(result);
    })
    .catch((e) => {
      show("#no-job-msg");
      $("#no-job-msg").textContent = "Could not load result: " + e.message;
    });

  function renderResult(result) {
    hide("#viz-placeholder"); hide("#analysis-placeholder"); hide("#hypotheses-placeholder");
    hide("#recovery-placeholder"); hide("#results-placeholder");
    show("#bits-recovered-label"); show("#bits-payload-label");
    $("#btn-export").disabled = false;

    Plots.waveform($("#canvas-waveform"), result.visualizations.waveform);
    Plots.spectrum($("#canvas-spectrum"), result.visualizations.spectrum_freqs, result.visualizations.spectrum_db);
    Plots.waterfall($("#canvas-waterfall"), result.visualizations.waterfall_freqs, result.visualizations.waterfall_times, result.visualizations.waterfall_db);
    Plots.constellation($("#canvas-constellation"), result.visualizations.constellation);

    renderKvTable("#table-estimate", {
      "Sample rate (Hz)": fmtNum(result.estimate.sample_rate),
      "Estimated symbol rate (Hz)": fmtNum(result.estimate.symbol_rate),
      "Carrier frequency (Hz)": fmtNum(result.estimate.carrier_frequency),
      "Occupied bandwidth (Hz)": fmtNum(result.estimate.bandwidth),
      "SNR (dB)": fmtNum(result.estimate.snr_db),
    });
    renderKvTable("#table-features", {
      "PAPR (dB)": fmtNum(result.features.papr_db),
      "Spectral flatness": fmtNum(result.features.spectral_flatness),
      "Kurtosis": fmtNum(result.features.kurtosis),
      "Skewness": fmtNum(result.features.skewness),
      "Spectral peaks (Hz)": (result.features.spectral_peaks || []).map(fmtNum).join(", "),
    });

    const tbody = $("#table-hypotheses tbody");
    tbody.innerHTML = result.hypotheses.map((h, i) => `
      <tr class="${i === 0 ? "best" : ""}">
        <td>${h.modulation}</td>
        <td>${fmtNum(h.score)}</td>
        <td>${h.confidence}%</td>
        <td>${fmtNum(h.evidence.evm)}</td>
        <td>${h.evidence.matched_cluster_order}</td>
      </tr>
    `).join("");

    if (result.recovered) {
      renderKvTable("#table-recovery", {
        "Modulation": result.recovered.modulation,
        "De-interleaving method": result.recovered.deinterleave_method,
        "FEC method": result.recovered.fec_method,
        "FEC success": String(result.recovered.fec_success),
        "Header correlation": fmtNum(result.recovered.diagnostics && result.recovered.diagnostics.header_correlation),
      });
      $("#bits-recovered").textContent = bitsPreview(result.recovered.bits);
    }

    if (result.bitstream) {
      renderKvTable("#table-bitstream", {
        "Header pattern": result.bitstream.header_pattern || "not found",
        "Header offset (bits)": result.bitstream.header_offset ?? "-",
        "Correlation peak": fmtNum(result.bitstream.correlation_peak),
      });
      $("#bits-payload").textContent = bitsPreview(result.bitstream.payload_bits);
    }
  }

  function renderKvTable(sel, obj) {
    $(sel).innerHTML = Object.entries(obj).map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("");
  }

  function fmtNum(v) {
    if (v === null || v === undefined || Number.isNaN(v)) return "-";
    if (typeof v !== "number") return v;
    return Math.abs(v) >= 1000 ? v.toFixed(1) : v.toFixed(3);
  }

  function bitsPreview(bits) {
    if (!bits || !bits.length) return "(none)";
    return bits.slice(0, 512).join("");
  }

  $("#btn-export").addEventListener("click", () => {
    if (!AppState.result) return;
    const blob = new Blob([JSON.stringify(AppState.result, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `analysis_${AppState.jobId || "report"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  });
})();
