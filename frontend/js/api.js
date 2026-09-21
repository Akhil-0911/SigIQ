/* Thin fetch wrapper around the FastAPI backend. Plain JS, no build step. */
const API = (() => {
  const BASE = ""; // same-origin (backend serves this frontend as static files)

  async function uploadFile(file) {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/api/upload`, { method: "POST", body: form });
    if (!res.ok) throw new Error((await res.json()).detail || "Upload failed");
    return res.json();
  }

  async function getConfigOptions() {
    const res = await fetch(`${BASE}/api/configuration/options`);
    if (!res.ok) throw new Error("Failed to load configuration options");
    return res.json();
  }

  async function startAnalysis(payload) {
    const res = await fetch(`${BASE}/api/analysis/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Failed to start analysis");
    return res.json();
  }

  async function getJobStatus(jobId) {
    const res = await fetch(`${BASE}/api/analysis/${jobId}`);
    if (!res.ok) throw new Error("Failed to fetch job status");
    return res.json();
  }

  async function getResult(jobId) {
    const res = await fetch(`${BASE}/api/results/${jobId}`);
    if (!res.ok) throw new Error((await res.json()).detail || "Failed to fetch result");
    return res.json();
  }

  function watchJob(jobId, onUpdate, onDone, onError) {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    let ws;
    try {
      ws = new WebSocket(`${proto}://${location.host}/ws/analysis/${jobId}`);
    } catch (e) {
      return pollJob(jobId, onUpdate, onDone, onError);
    }
    ws.onmessage = (evt) => {
      const state = JSON.parse(evt.data);
      onUpdate(state);
      if (state.status === "complete") { onDone(state); ws.close(); }
      else if (state.status === "error") { onError(state.error || "Analysis failed"); ws.close(); }
    };
    ws.onerror = () => pollJob(jobId, onUpdate, onDone, onError);
    return ws;
  }

  function pollJob(jobId, onUpdate, onDone, onError) {
    const interval = setInterval(async () => {
      try {
        const state = await getJobStatus(jobId);
        onUpdate(state);
        if (state.status === "complete") { clearInterval(interval); onDone(state); }
        else if (state.status === "error") { clearInterval(interval); onError(state.error || "Analysis failed"); }
      } catch (e) {
        clearInterval(interval);
        onError(e.message);
      }
    }, 800);
    return interval;
  }

  return { uploadFile, getConfigOptions, startAnalysis, getJobStatus, getResult, watchJob };
})();
