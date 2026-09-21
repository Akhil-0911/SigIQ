/* Canvas-based plotting -- plain JS, no charting library. */
const Plots = (() => {
  function clear(ctx, w, h) {
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#060b16";
    ctx.fillRect(0, 0, w, h);
  }

  function drawAxes(ctx, w, h, pad = 30) {
    ctx.strokeStyle = "#24314c";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pad, 0); ctx.lineTo(pad, h - pad);
    ctx.moveTo(pad, h - pad); ctx.lineTo(w, h - pad);
    ctx.stroke();
  }

  function waveform(canvas, points) {
    const ctx = canvas.getContext("2d");
    const w = canvas.width, h = canvas.height;
    clear(ctx, w, h);
    if (!points || points.length === 0) return;
    const pad = 30;
    const usableW = w - pad, usableH = h - pad;
    const mag = points.map(p => Math.hypot(p[0], p[1]));
    const maxMag = Math.max(...mag, 1e-9);

    ctx.strokeStyle = "#3fd0c9";
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    points.forEach((p, i) => {
      const x = pad + (i / (points.length - 1)) * usableW;
      const y = usableH / 2 - (mag[i] / maxMag) * (usableH / 2 - 5);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
    drawAxes(ctx, w, h, pad);
  }

  function spectrum(canvas, freqs, psdDb) {
    const ctx = canvas.getContext("2d");
    const w = canvas.width, h = canvas.height;
    clear(ctx, w, h);
    if (!freqs || freqs.length === 0) return;
    const pad = 36;
    const usableW = w - pad, usableH = h - pad;
    const minDb = Math.min(...psdDb), maxDb = Math.max(...psdDb);
    const range = Math.max(maxDb - minDb, 1e-6);

    ctx.strokeStyle = "#5b8cff";
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    psdDb.forEach((v, i) => {
      const x = pad + (i / (psdDb.length - 1)) * usableW;
      const y = usableH - ((v - minDb) / range) * (usableH - 10);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
    drawAxes(ctx, w, h, pad);

    ctx.fillStyle = "#8ea0c0";
    ctx.font = "11px sans-serif";
    ctx.fillText(`${freqs[0].toFixed(0)} Hz`, pad, h - 8);
    ctx.fillText(`${freqs[freqs.length - 1].toFixed(0)} Hz`, w - 90, h - 8);
  }

  function waterfall(canvas, freqs, times, sxxDb) {
    const ctx = canvas.getContext("2d");
    const w = canvas.width, h = canvas.height;
    clear(ctx, w, h);
    if (!sxxDb || sxxDb.length === 0) return;
    const nT = sxxDb.length, nF = sxxDb[0].length;

    let minDb = Infinity, maxDb = -Infinity;
    for (const row of sxxDb) for (const v of row) { if (v < minDb) minDb = v; if (v > maxDb) maxDb = v; }
    const range = Math.max(maxDb - minDb, 1e-6);

    const cellW = w / nT, cellH = h / nF;
    for (let t = 0; t < nT; t++) {
      for (let f = 0; f < nF; f++) {
        const v = (sxxDb[t][f] - minDb) / range; // 0..1
        ctx.fillStyle = heatColor(v);
        ctx.fillRect(t * cellW, h - (f + 1) * cellH, cellW + 1, cellH + 1);
      }
    }
  }

  function heatColor(v) {
    // simple blue -> teal -> yellow -> red heatmap
    const stops = [
      [11, 18, 32], [63, 208, 201], [255, 180, 84], [255, 107, 107],
    ];
    const scaled = Math.max(0, Math.min(1, v)) * (stops.length - 1);
    const i = Math.floor(scaled);
    const frac = scaled - i;
    const a = stops[i], b = stops[Math.min(i + 1, stops.length - 1)];
    const r = Math.round(a[0] + (b[0] - a[0]) * frac);
    const g = Math.round(a[1] + (b[1] - a[1]) * frac);
    const bl = Math.round(a[2] + (b[2] - a[2]) * frac);
    return `rgb(${r},${g},${bl})`;
  }

  function constellation(canvas, points) {
    const ctx = canvas.getContext("2d");
    const w = canvas.width, h = canvas.height;
    clear(ctx, w, h);
    if (!points || points.length === 0) return;
    const maxAbs = Math.max(...points.map(p => Math.max(Math.abs(p[0]), Math.abs(p[1]))), 1e-9);
    const cx = w / 2, cy = h / 2, scale = (Math.min(w, h) / 2 - 20) / maxAbs;

    ctx.strokeStyle = "#24314c";
    ctx.beginPath();
    ctx.moveTo(0, cy); ctx.lineTo(w, cy);
    ctx.moveTo(cx, 0); ctx.lineTo(cx, h);
    ctx.stroke();

    ctx.fillStyle = "#3fd0c9";
    points.forEach(([re, im]) => {
      const x = cx + re * scale, y = cy - im * scale;
      ctx.beginPath();
      ctx.arc(x, y, 2, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  return { waveform, spectrum, waterfall, constellation };
})();
