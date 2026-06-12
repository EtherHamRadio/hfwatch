#!/usr/bin/env python3
"""
server.py — HFWatch web dashboard
Serves the band activity dashboard and a JSON API.

Usage:
    python3 server.py [--db /path/to/hfwatch.db] [--port 5000] [--host 0.0.0.0]

To run as a service, see hfwatch.service in this directory.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request

import sys
sys.path.insert(0, str(Path(__file__).parent))
from db import DEFAULT_DB, get_conn, init_db, get_config, set_config
from query import get_heatmap, get_weekly_avg, get_stats, get_timeseries

app = Flask(__name__)
DB_PATH = DEFAULT_DB   # overridden by --db arg at startup


def ts_to_str(ts):
    if ts is None:
        return "N/A"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ── JSON API ──────────────────────────────────────────────────────────────────

@app.route("/api/heatmap")
def api_heatmap():
    hours = int(request.args.get("hours", 24))
    hours = min(max(hours, 1), 168)
    grid = request.args.get("grid", "CN87").upper().strip()
    data = get_heatmap(hours=hours, target_grid=grid, db_path=DB_PATH)
    return jsonify(data)
@app.route("/api/timeseries")
def api_timeseries():
    hours = int(request.args.get("hours", 24))
    hours = min(max(hours, 1), 168)
    res   = int(request.args.get("res", 30))
    res   = min(max(res, 5), 120)
    grid  = request.args.get("grid", "CN87").upper().strip()
    snap  = request.args.get("snap", "0") == "1"
    data  = get_timeseries(hours=hours, resolution_minutes=res, target_grid=grid,
                           snap_to_utc_day=snap, db_path=DB_PATH)
    return jsonify(data)


@app.route("/api/weekly")
def api_weekly():
    grid = request.args.get("grid", "CN87").upper().strip()
    data = get_weekly_avg(target_grid=grid, db_path=DB_PATH)
    return jsonify(data)

@app.route("/api/grids")
def api_grids():
    from db import get_active_grids
    with get_conn(DB_PATH) as conn:
        grids = get_active_grids(conn)
    return jsonify({"grids": grids})


@app.route("/api/stats")
def api_stats():
    data = get_stats(db_path=DB_PATH)
    data["oldest_str"] = ts_to_str(data["oldest_spot"])
    data["newest_str"] = ts_to_str(data["latest_spot"])
    return jsonify(data)


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    with get_conn(DB_PATH) as conn:
        if request.method == "POST":
            body = request.get_json(force=True)
            if "grid" in body:
                grid = body["grid"].upper().strip()
                if len(grid) in (4, 6) and grid.isalnum():
                    set_config(conn, "grid", grid)
                else:
                    return jsonify({"error": "Invalid grid square"}), 400
        cfg = get_config(conn)
    return jsonify(cfg)


# ── Dashboard HTML ─────────────────────────────────────────────────────────────

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HFWatch — Band Activity</title>
<link rel="icon" type="image/png" href="data:image/png;base64,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">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Barlow:wght@300;400;600&display=swap');

  :root {
    --bg:        #f0f4f8;
    --surface:   #ffffff;
    --border:    #b0c4d8;
    --accent:    #0066aa;
    --accent2:   #cc4400;
    --text:      #1a2a3a;
    --muted:     #5a7a9a;
    --mono:      'Share Tech Mono', monospace;
    --sans:      'Barlow', sans-serif;
    --cell-size: 28px;
  }

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    font-weight: 300;
    min-height: 100vh;
    padding: 0 0 60px;
  }

  /* ── Header ── */
  header {
    background: linear-gradient(135deg, #0d1a24 0%, #0a1520 100%);
    border-bottom: 1px solid var(--border);
    padding: 18px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
    position: sticky;
    top: 0;
    z-index: 100;
  }

  .logo {
    font-family: var(--mono);
    font-size: 1.35rem;
    color: #00aaff;
    letter-spacing: 0.08em;
    display: flex;
    align-items: center;
    gap: 10px;
    text-shadow: 0 0 8px #00aaffaa;
    font-weight: 700;
  }

  .logo::before {
    content: '▶';
    font-size: 0.7em;
    animation: blink 1.4s step-end infinite;
  }
  @keyframes blink { 50% { opacity: 0; } }

  .header-right {
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
  }

  .grid-control {
    display: flex;
    align-items: center;
    gap: 8px;
    font-family: var(--mono);
    font-size: 0.8rem;
    color: var(--muted);
  }
  .grid-control input {
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--accent);
    font-family: var(--mono);
    font-size: 0.9rem;
    padding: 4px 8px;
    width: 72px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  .grid-control input:focus { outline: 1px solid var(--accent); }

  .btn {
    background: transparent;
    border: 1px solid var(--accent);
    color: var(--accent);
    font-family: var(--mono);
    font-size: 0.75rem;
    padding: 5px 12px;
    cursor: pointer;
    letter-spacing: 0.06em;
    transition: background 0.15s, color 0.15s;
  }
  .btn:hover { background: var(--accent); color: var(--bg); }
  .btn.active { background: var(--accent); color: var(--bg); }

  /* ── Layout ── */
  main { max-width: 1400px; margin: 0 auto; padding: 28px 24px 0; }

  .status-bar {
    font-family: var(--mono);
    font-size: 0.72rem;
    color: var(--muted);
    margin-bottom: 24px;
    display: flex;
    gap: 24px;
    flex-wrap: wrap;
  }
  .status-bar span { color: var(--text); }

  .controls {
    display: flex;
    gap: 8px;
    margin-bottom: 28px;
    flex-wrap: wrap;
    align-items: center;
  }
  .controls-label {
    font-family: var(--mono);
    font-size: 1.28rem;
    font-weight: 700;
    color: var(--muted);
    margin-right: 4px;
    letter-spacing: 0.1em;
  }

  /* ── Heatmap ── */
  .chart-card {
    background: var(--surface);
    border: 1px solid var(--border);
    padding: 24px;
    margin-bottom: 24px;
  }

  .chart-title {
    font-family: var(--mono);
    font-size: 1.28rem;
    font-weight: 700;
    color: var(--accent);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .chart-title::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
  }

  .heatmap-wrap { overflow-x: auto; }
  .heatmap {
    display: grid;
    gap: 2px;
  }
  .hm-row {
    display: flex;
    align-items: center;
    gap: 2px;
  }
  .hm-label {
    font-family: var(--mono);
    font-size: 0.72rem;
    color: var(--muted);
    width: 42px;
    text-align: right;
    padding-right: 8px;
    flex-shrink: 0;
  }
  .hm-label.active { color: var(--accent); }

  .hm-cell {
    width: var(--cell-size);
    height: var(--cell-size);
    position: relative;
    cursor: default;
    transition: transform 0.08s;
    flex-shrink: 0;
  }
  .hm-cell:hover { transform: scale(1.3); z-index: 10; }
  .hm-cell:hover::after {
    content: attr(data-tip);
    position: absolute;
    bottom: calc(100% + 4px);
    left: 50%;
    transform: translateX(-50%);
    background: #ffffffee;
    border: 1px solid var(--accent);
    color: #1a2a3a;
    font-family: var(--mono);
    font-size: 0.65rem;
    padding: 3px 6px;
    white-space: nowrap;
    pointer-events: none;
    z-index: 20;
  }

  .hm-hour-labels {
    display: flex;
    gap: 2px;
    padding-left: 50px;
    margin-bottom: 4px;
    width: fit-content;
  }
  .hm-hour-label {
    width: var(--cell-size);
    height: 1rem;
    font-family: var(--mono);
    font-size: 0.6rem;
    color: var(--muted);
    flex-shrink: 0;
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 0;
    margin: 0;
    padding-right: 1.1em;
  }

  .hm-total {
    font-family: var(--mono);
    font-size: 0.65rem;
    color: var(--muted);
    padding-left: 8px;
    flex-shrink: 0;
  }

  .hm-hour-label.current-hour {
    color: var(--accent);
    font-weight: 700;
  }
  .hm-hour-label.current-hour span {
    outline: 1px solid var(--accent);
    outline-offset: 2px;
    border-radius: 2px;
  }

  /* ── Band bar chart ── */
  .band-bars {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding-left: 12px;
    flex-shrink: 0;
    justify-content: flex-start;
  }
  .band-bar-row {
    display: flex;
    align-items: center;
    height: var(--cell-size);
  }
  .band-bar-track {
    width: 160px;
    height: 16px;
    background: #dde6ef;
    position: relative;
    overflow: visible;
  }
  .band-bar-fill {
    height: 100%;
    transition: width 0.4s ease;
  }
  .band-bar-label {
    font-family: var(--mono);
    font-size: 0.65rem;
    color: var(--text);
    position: absolute;
    right: 4px;
    top: 50%;
    transform: translateY(-50%);
    white-space: nowrap;
    mix-blend-mode: multiply;
    pointer-events: none;
  }

  /* ── Legend ── */
  .legend {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-top: 16px;
    font-family: var(--mono);
    font-size: 0.65rem;
    color: var(--muted);
  }
  .legend-cells { display: flex; gap: 2px; }
  .legend-cell {
    width: 20px;
    height: 12px;
  }

  /* ── Loading/Error ── */
  .loading {
    font-family: var(--mono);
    font-size: 0.85rem;
    color: var(--muted);
    padding: 40px;
    text-align: center;
    letter-spacing: 0.08em;
  }
  .err {
    color: #ff4444;
    font-family: var(--mono);
    font-size: 0.8rem;
    padding: 20px;
    border: 1px solid #ff444444;
    background: #1a0808;
  }

  /* ── Time-series chart ── */
  .ts-canvas-wrap { width: 100%; overflow-x: auto; }
  .ts-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 16px;
    margin-top: 12px;
    font-family: var(--mono);
    font-size: 0.68rem;
  }
  .ts-legend-item {
    display: flex;
    align-items: center;
    gap: 5px;
    cursor: pointer;
    transition: opacity 0.15s;
  }
  .ts-legend-item.muted { opacity: 0.3; }
  .ts-controls {
    font-family: var(--mono);
    font-size: 0.7rem;
    color: var(--muted);
    margin-bottom: 12px;
  }

  /* ── SNR overlay ── */
  .snr-label {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: var(--mono);
    font-size: 7px;
    font-weight: 700;
    color: rgba(255,255,255,0.92);
    text-shadow: 0 0 3px rgba(0,0,0,0.8);
    pointer-events: none;
    line-height: 1;
  }
</style>
</head>
<body>

<header>
  <div class="logo">HFWatch</div>
  <div class="header-right">
    <div class="local-clock" id="localClock" style="font-family:var(--mono);font-size:0.85rem;color:#00aaff;letter-spacing:0.06em;font-weight:700;text-shadow:0 0 8px #00aaffaa;"></div>
    <div class="grid-control">
      GRID&nbsp;
      <select id="gridSelect" onchange="switchGrid(this.value)" style="font-family:var(--mono);font-size:0.8rem;background:var(--surface);color:var(--text);border:1px solid var(--border);padding:3px 6px;border-radius:3px;">
        <option value="CN87">CN87</option>
      </select>
    </div>
  </div> 
</header>

<main>
  <div class="status-bar" id="statusBar">
    <span>Loading…</span>
  </div>
  <div class="controls">
    <span class="controls-label">WINDOW //</span>
    <button class="btn active" onclick="setWindow(24, this)">24H</button>
    <button class="btn" onclick="setWindow(48, this)">48H</button>
    <button class="btn" onclick="setWindow(72, this)">72H</button>
    <button class="btn" onclick="setWindow(168, this)">7D</button>
    <button class="btn" id="weeklyBtn" onclick="toggleWeekly(this)" style="margin-left:16px; border-color: var(--accent2); color: var(--accent2)">7D AVG</button>
    <button class="btn" id="tableBtn" onclick="toggleTable(this)" style="margin-left:16px; border-color: #888; color: #888">TABLE</button>
    <button class="btn" id="chartBtn" onclick="toggleChart(this)" style="border-color: #888; color: #888">CHART</button>
    <button class="btn" id="snrBtn" onclick="toggleSNR(this)" style="border-color: #888; color: #888">SNR</button>
  </div>
  <div class="chart-card">
    <div class="chart-title">Band × Hour Activity (UTC spot count)</div>
    <div id="heatmapContainer" class="loading">Fetching data…</div>
    <div id="tableContainer" style="display:none;overflow-x:auto;"></div>
    <div id="chartContainer" style="display:none;"></div>
  </div>
</main>

<script>
const HOURS = Array.from({length: 24}, (_, i) => i);
let currentWindow = 24;
let weeklyMode = false;
let currentGrid = 'CN87';
let snrMode = false;

// ── Colour scale: dark navy → teal → orange ──────────────────────────────────
function spotColor(count, peak) {
  if (count === 0) return '#dde6ef';
  const t = Math.min(count / peak, 1);
  // 0→0.5: navy to teal; 0.5→1: teal to orange
  let r, g, b;
  if (t < 0.5) {
    const u = t * 2;
    r = Math.round(0   + u * 0);
    g = Math.round(60  + u * (212 - 60));
    b = Math.round(120 + u * (255 - 120));
  } else {
    const u = (t - 0.5) * 2;
    r = Math.round(0   + u * 255);
    g = Math.round(212 - u * (212 - 107));
    b = Math.round(255 - u * 255);
  }
  return `rgb(${r},${g},${b})`;
}

function legendGradient(peak) {
  const steps = 10;
  return Array.from({length: steps}, (_, i) =>
    `<div class="legend-cell" style="background:${spotColor(i/steps*peak, peak)}"></div>`
  ).join('');
}

// ── Render heatmap from data ─────────────────────────────────────────────────
function renderHeatmap(data) {
  const container = document.getElementById('heatmapContainer');
  if (!data.bands || data.bands.length === 0) {
    container.innerHTML = '<div class="loading">No spots recorded yet. Collector running?</div>';
    return;
  }

  const peak = data.peak || 1;
  const fmtTs = ts => ts ? new Date(ts*1000).toISOString().slice(5,16).replace('T',' ') + ' UTC' : '?';
  const subtitle = data.mode === '7-day average'
    ? '7-day average spots/hour'
    : `${data.window_hours}h window · ${fmtTs(data.from_ts)} → ${fmtTs(data.to_ts)} · ${data.target_grid || ''}`;

  // Current UTC hour for highlight
  const nowUTC = new Date().getUTCHours();
  // Current local hour for local-time row highlight
  const nowLocal = new Date().getHours();

  // Build UTC hour labels with current-hour highlight
  const utcLabels = HOURS.map(h => {
    const cls = h === nowUTC ? 'hm-hour-label current-hour' : 'hm-hour-label';
    const txt = String(h).padStart(2,'0');
    return h === nowUTC ? `<div class="${cls}"><span>${txt}</span></div>` : `<div class="${cls}">${txt}</div>`;
  }).join('');

  // Build local time row with current-hour highlight
  const localLabels = HOURS.map(h => {
    const d = new Date();
    d.setUTCHours(h, 0, 0, 0);
    const localH = d.getHours();
    const ampm = localH >= 12 ? 'p' : 'a';
    const h12 = localH % 12 || 12;
    const cls = localH === nowLocal ? 'hm-hour-label current-hour' : 'hm-hour-label';
    const txt2 = `${h12}${ampm}`;
    return localH === nowLocal ? `<div class="${cls}"><span>${txt2}</span></div>` : `<div class="${cls}">${txt2}</div>`;
  }).join('');

  // Max total for bar chart scaling
  const maxTotal = data.totals
    ? Math.max(...data.bands.map(b => data.totals[b] || 0), 1)
    : 1;

  let html = `
    <div style="font-family:var(--mono);font-size:0.65rem;color:var(--muted);margin-bottom:12px;">${subtitle}</div>
    <div style="display:flex;align-items:flex-start;">
      <div class="heatmap-wrap" style="flex:0 0 auto;">
        <div style="font-family:var(--mono);font-size:0.6rem;color:var(--muted);padding-left:50px;margin-bottom:2px;letter-spacing:0.03em;">UTC</div>
        <div class="hm-hour-labels">${utcLabels}</div>
  `;

  for (const band of data.bands) {
    const row = data.matrix[band];
    const total = data.totals ? (data.totals[band] || 0) : 0;
    const pct = data.totals ? (total / maxTotal) * 100 : 0;
    const barColor = spotColor(total, maxTotal);
    html += `<div class="hm-row">
      <div class="hm-label active">${band}</div>
      ${HOURS.map(h => {
        const cnt = row[h] || 0;
        const bg  = spotColor(cnt, peak);
        const tip = `${band} ${String(h).padStart(2,'0')}:00 UTC — ${cnt} spot${cnt!==1?'s':''}`;
        const snrVal = (snrMode && data.snr_matrix) ? data.snr_matrix[band][h] : null;
        const snrStr = (snrVal !== null && snrVal !== undefined) ? (snrVal > 0 ? '+' : '') + snrVal : '';
        const snrTip = snrStr ? ` · avg SNR ${snrStr} dB` : '';
        return `<div class="hm-cell" style="background:${bg}" data-tip="${tip}${snrTip}">${snrStr ? `<span class="snr-label">${snrStr}</span>` : ''}</div>`;
      }).join('')}
      <div class="hm-total" style="width:52px;text-align:right;">${total ? total.toLocaleString() : ''}</div>
      <div style="padding-left:10px;display:flex;align-items:center;width:180px;flex-shrink:0;">
        <div style="position:relative;width:100%;height:16px;background:#dde6ef;overflow:visible;">
          <div style="width:${pct}%;height:100%;background:${barColor};"></div>
          <span style="position:absolute;right:4px;top:50%;transform:translateY(-50%);font-family:var(--mono);font-size:0.65rem;color:var(--text);white-space:nowrap;mix-blend-mode:multiply;">${total ? total.toLocaleString() : ''}</span>
        </div>
      </div>
    </div>`;
  }

  html += `
        <div style="font-family:var(--mono);font-size:0.6rem;color:var(--muted);padding-left:50px;margin-top:4px;margin-bottom:2px;letter-spacing:0.03em;">LOCAL</div>
        <div class="hm-hour-labels" style="margin-bottom:12px;">${localLabels}</div>
        <div class="legend">
          <span>NONE</span>
          <div class="legend-cells">${legendGradient(peak)}</div>
          <span>PEAK (${peak})</span>
        </div>
      </div>`;

  html += `</div>`; // close outer flex
  container.innerHTML = html;
  container.className = '';
}

// ── Fetch and render ──────────────────────────────────────────────────────────
async function loadHeatmap(hours) {
  const container = document.getElementById('heatmapContainer');
  container.className = 'loading';
  container.textContent = 'Fetching…';
  try {
    const resp = await fetch(`/api/heatmap?hours=${hours}&grid=${currentGrid}`);
    const data = await resp.json();
    lastData = data;
    renderHeatmap(data); 
  } catch(e) {
    container.className = 'err';
    container.textContent = 'Failed to load: ' + e.message;
  }
}

async function loadWeekly() {
  const container = document.getElementById('heatmapContainer');
  container.className = 'loading';
  container.textContent = 'Fetching…';
  try {
    const resp = await fetch(`/api/weekly?grid=${currentGrid}`);
    const data = await resp.json();
    lastData = data;
    renderHeatmap(data);
  } catch(e) {
    container.className = 'err';
    container.textContent = 'Failed to load: ' + e.message;
  }
}

async function loadStats() {
  try {
    const resp = await fetch('/api/stats');
    const d = await resp.json();
    const bar = document.getElementById('statusBar');
    const errBit = '';
    bar.innerHTML = `
      GRID <span>${currentGrid}</span> ·
      SPOTS <span>${(d.total_spots||0).toLocaleString()}</span> ·
      OLDEST <span>${d.oldest_str}</span> ·
      LATEST <span>${d.newest_str}</span>
      ${d.last_fetch_str ? ` · LAST FETCH <span>${d.last_fetch_str}</span> (+${d.last_fetch_new||0} new)` : ''}
    `;
    // populate grid dropdown
    if (d.active_grids && d.active_grids.length > 0) {
      const sel = document.getElementById('gridSelect');
      if (sel) {
        const current = sel.value || currentGrid;
        sel.innerHTML = d.active_grids.map(g =>
          `<option value="${g}" ${g===current?'selected':''}>${g}</option>`
        ).join('');
        currentGrid = sel.value;
      }
    }
  } catch(e) { /* non-fatal */ }
}

// ── Controls ──────────────────────────────────────────────────────────────────
let tableMode = false;
let lastData = null;

// ── setSNRButtonState: grey-out SNR when heatmap is not showing ───────────────
function setSNRButtonState() {
  const btn = document.getElementById('snrBtn');
  if (!btn) return;
  const heatmapVisible = !tableMode && !chartMode;
  btn.disabled = !heatmapVisible;
  btn.style.opacity = heatmapVisible ? '1' : '0.35';
  btn.style.cursor  = heatmapVisible ? 'pointer' : 'not-allowed';
  // if SNR was on and we're hiding heatmap, visually reset button
  if (!heatmapVisible && snrMode) {
    btn.style.background = '';
    btn.style.color = '#888';
  } else if (heatmapVisible && snrMode) {
    btn.style.background = '#446688';
    btn.style.color = '#fff';
  }
}

// ── exitOverlayModes: called by window buttons to return to heatmap ───────────
function exitOverlayModes() {
  if (tableMode) {
    tableMode = false;
    const b = document.getElementById('tableBtn');
    if (b) { b.style.background = ''; b.style.color = '#888'; }
    document.getElementById('tableContainer').style.display = 'none';
    document.getElementById('heatmapContainer').style.display = 'block';
  }
  if (chartMode) {
    chartMode = false;
    const b = document.getElementById('chartBtn');
    if (b) { b.style.background = ''; b.style.color = '#888'; }
    document.getElementById('chartContainer').style.display = 'none';
    document.getElementById('heatmapContainer').style.display = 'block';
  }
  setSNRButtonState();
}

function setWindow(hours, btn) {
  currentWindow = hours;
  weeklyMode = false;
  exitOverlayModes();
  document.querySelectorAll('.controls .btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  loadHeatmap(hours);
}

function toggleWeekly(btn) {
  weeklyMode = !weeklyMode;
  exitOverlayModes();
  if (weeklyMode) {
    document.querySelectorAll('.controls .btn:not(#weeklyBtn)').forEach(b => b.classList.remove('active'));
    btn.style.background = 'var(--accent2)';
    btn.style.color = 'var(--bg)';
    loadWeekly();
  } else {
    btn.style.background = '';
    btn.style.color = 'var(--accent2)';
    loadHeatmap(currentWindow);
  }
}

function toggleTable(btn) {
  if (tableMode) {
    // toggle off
    tableMode = false;
    btn.style.background = '';
    btn.style.color = '#888';
    document.getElementById('tableContainer').style.display = 'none';
    document.getElementById('heatmapContainer').style.display = 'block';
  } else {
    // toggle on — turn off CHART if active
    if (chartMode) {
      chartMode = false;
      const cb = document.getElementById('chartBtn');
      if (cb) { cb.style.background = ''; cb.style.color = '#888'; }
      document.getElementById('chartContainer').style.display = 'none';
    }
    tableMode = true;
    btn.style.background = '#888';
    btn.style.color = '#fff';
    document.getElementById('heatmapContainer').style.display = 'none';
    document.getElementById('tableContainer').style.display = 'block';
    if (lastData) renderTable(lastData);
  }
  setSNRButtonState();
}

function renderTable(data) {
  const tb = document.getElementById('tableContainer');
  if (!data.bands || data.bands.length === 0) {
    tb.innerHTML = '<div class="loading">No data.</div>';
    return;
  }
  let html = `<table style="border-collapse:collapse;font-family:var(--mono);font-size:0.72rem;color:var(--text);width:100%;">`;
  html += `<tr><th style="text-align:right;padding:3px 8px;color:var(--muted);border-bottom:1px solid var(--border);">BAND</th>`;
  for (const h of HOURS) {
    html += `<th style="padding:3px 4px;color:var(--muted);border-bottom:1px solid var(--border);text-align:center;">${String(h).padStart(2,'0')}</th>`;
  }
  html += `<th style="padding:3px 8px;color:var(--muted);border-bottom:1px solid var(--border);text-align:right;">TOTAL</th></tr>`;

  for (const band of data.bands) {
    const row = data.matrix[band];
    const total = data.totals ? data.totals[band] : '';
    const peak = data.peak || 1;
    html += `<tr>`;
    html += `<td style="text-align:right;padding:3px 8px;color:#00aaff;font-weight:700;">${band}</td>`;
    for (const h of HOURS) {
      const cnt = row[h] || 0;
      const bg = cnt === 0 ? '' : `background:${spotColor(cnt, peak)}22;`;
      const fw = cnt > 0 ? 'font-weight:600;' : 'color:var(--muted);';
      html += `<td style="text-align:center;padding:3px 4px;${bg}${fw}">${cnt === 0 ? '·' : cnt}</td>`;
    }
    html += `<td style="text-align:right;padding:3px 8px;font-weight:700;">${total ? total.toLocaleString() : ''}</td>`;
    html += `</tr>`;
  }
  // local time footer row — appended to same table
  html += `<tr style="border-top:1px solid var(--border);">`;
  html += `<td style="text-align:right;padding:3px 8px;color:var(--muted);">LOCAL</td>`;
  for (const h of HOURS) {
    const d = new Date();
    d.setUTCHours(h, 0, 0, 0);
    const localH = d.getHours();
    const ampm = localH >= 12 ? 'p' : 'a';
    const h12 = localH % 12 || 12;
    html += `<td style="text-align:center;padding:3px 4px;color:var(--muted);">${h12}${ampm}</td>`;
  }
  html += `<td style="padding:3px 8px;"></td></tr>`;
  html += `</table>`;
  tb.innerHTML = html;
}

function switchGrid(grid) {
  currentGrid = grid.toUpperCase().trim();
  if (weeklyMode) loadWeekly(); else loadHeatmap(currentWindow);
  loadStats();
}

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  await loadStats();
  loadHeatmap(24);
  // refresh stats every 5 minutes
  setInterval(loadStats, 5 * 60 * 1000);
  // refresh chart every 15 minutes (aligned with collector)
  setInterval(() => {
    if (weeklyMode) loadWeekly(); else loadHeatmap(currentWindow);
  }, 15 * 60 * 1000);
}

init();
function updateClock() {
  const now = new Date();
  const dateStr = now.toLocaleDateString('en-US', {weekday:'short', year:'numeric', month:'short', day:'numeric'});
  const timeStr = now.toLocaleTimeString('en-US', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  document.getElementById('localClock').textContent = dateStr + '  ' + timeStr;
}
updateClock();
setInterval(updateClock, 1000);

// ── Time-series chart ─────────────────────────────────────────────────────────

const BAND_COLORS = {
  '160m': '#6644cc', '80m': '#0066aa', '60m': '#0099cc',
  '40m': '#00aaff', '30m': '#00ccbb', '20m': '#00bb66',
  '17m': '#88cc00', '15m': '#ccaa00', '12m': '#dd7700',
  '10m': '#ee4400', '6m':  '#cc0044',
};
function bandColor(b) { return BAND_COLORS[b] || '#888888'; }

let chartMode = false;
let chartData = null;
let hiddenBands = new Set();

function toggleChart(btn) {
  if (chartMode) {
    // toggle off
    chartMode = false;
    btn.style.background = '';
    btn.style.color = '#888';
    document.getElementById('chartContainer').style.display = 'none';
    document.getElementById('heatmapContainer').style.display = 'block';
  } else {
    // toggle on — turn off TABLE if active
    if (tableMode) {
      tableMode = false;
      const tb2 = document.getElementById('tableBtn');
      if (tb2) { tb2.style.background = ''; tb2.style.color = '#888'; }
      document.getElementById('tableContainer').style.display = 'none';
    }
    chartMode = true;
    btn.style.background = '#444';
    btn.style.color = '#fff';
    document.getElementById('heatmapContainer').style.display = 'none';
    document.getElementById('chartContainer').style.display = 'block';
    loadChart();
  }
  setSNRButtonState();
}

async function loadChart() {
  const ct = document.getElementById('chartContainer');
  ct.innerHTML = '<div class="loading">Fetching time-series data\u2026</div>';
  const res = currentWindow <= 24 ? 30 : currentWindow <= 72 ? 60 : 120;
  // snap to UTC midnight for ≤72h windows so the chart aligns with the heatmap
  const snap = currentWindow <= 72 ? 1 : 0;
  try {
    const resp = await fetch(`/api/timeseries?hours=${currentWindow}&res=${res}&grid=${currentGrid}&snap=${snap}`);
    chartData = await resp.json();
    renderChart(chartData);
  } catch(e) {
    ct.innerHTML = `<div class="err">Failed to load: ${e.message}</div>`;
  }
}

function renderChart(data) {
  const ct = document.getElementById('chartContainer');
  if (!data.bands || data.bands.length === 0) {
    ct.innerHTML = '<div class="loading">No data for this window.</div>';
    return;
  }

  const PAD = { top: 20, right: 20, bottom: 60, left: 52 };
  const H = 320;
  const W = Math.max(ct.clientWidth || 800, 600);
  const iW = W - PAD.left - PAD.right;
  const iH = H - PAD.top  - PAD.bottom;

  const visibleBands = data.bands.filter(b => !hiddenBands.has(b));
  let yMax = 1;
  for (const b of visibleBands)
    for (const v of data.series[b]) yMax = Math.max(yMax, v);
  yMax = Math.ceil(yMax * 1.1) || 1;

  const buckets = data.buckets;
  const n = buckets.length;
  const xScale = i => PAD.left + (i / Math.max(n - 1, 1)) * iW;
  const yScale = v => PAD.top  + iH - (v / yMax) * iH;

  let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" style="font-family:'Share Tech Mono',monospace;">`;

  // Y grid + labels
  for (let i = 0; i <= 5; i++) {
    const v = Math.round((yMax / 5) * i);
    const y = yScale(v);
    svg += `<line x1="${PAD.left}" y1="${y}" x2="${PAD.left+iW}" y2="${y}" stroke="#b0c4d8" stroke-width="0.5" stroke-dasharray="${i===0?'none':'3,3'}"/>`;
    svg += `<text x="${PAD.left-6}" y="${y+4}" text-anchor="end" font-size="9" fill="#5a7a9a">${v}</text>`;
  }

  // X labels — show HH:MM UTC, plus a date hint on the first tick and at each midnight rollover
  const labelEvery = Math.ceil(n / 12);
  const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  let lastDateStr = null;
  for (let i = 0; i < n; i += labelEvery) {
    const x = xScale(i);
    const d = new Date(buckets[i] * 1000);
    const timeLabel = String(d.getUTCHours()).padStart(2,'0') + ':' + String(d.getUTCMinutes()).padStart(2,'0');
    const dateStr = MONTHS[d.getUTCMonth()] + '\u00a0' + String(d.getUTCDate()).padStart(2,'0');
    const showDate = (i === 0) || (d.getUTCHours() === 0 && d.getUTCMinutes() < labelEvery * (data.resolution_minutes || 30)) || dateStr !== lastDateStr;
    lastDateStr = dateStr;
    svg += `<line x1="${x}" y1="${PAD.top}" x2="${x}" y2="${PAD.top+iH}" stroke="#b0c4d8" stroke-width="0.5" stroke-dasharray="3,3"/>`;
    svg += `<text x="${x}" y="${PAD.top+iH+14}" text-anchor="middle" font-size="9" fill="#5a7a9a">${timeLabel}</text>`;
    if (showDate) {
      svg += `<text x="${x}" y="${PAD.top+iH+26}" text-anchor="middle" font-size="8" fill="#8aaccc">${dateStr}</text>`;
    }
  }

  // Axes
  svg += `<line x1="${PAD.left}" y1="${PAD.top}" x2="${PAD.left}" y2="${PAD.top+iH}" stroke="#b0c4d8" stroke-width="1"/>`;
  svg += `<line x1="${PAD.left}" y1="${PAD.top+iH}" x2="${PAD.left+iW}" y2="${PAD.top+iH}" stroke="#b0c4d8" stroke-width="1"/>`;
  svg += `<text x="${PAD.left-38}" y="${PAD.top+iH/2}" text-anchor="middle" font-size="9" fill="#5a7a9a" transform="rotate(-90,${PAD.left-38},${PAD.top+iH/2})">SPOTS</text>`;
  svg += `<text x="${PAD.left+iW/2}" y="${H-2}" text-anchor="middle" font-size="9" fill="#5a7a9a">UTC</text>`;

  // "Now" marker — vertical line at current time when day-snapped (future is empty)
  if (data.snap_to_utc_day) {
    const nowTs = Math.floor(Date.now() / 1000);
    const nowBucket = Math.floor(nowTs / (data.resolution_minutes * 60)) * (data.resolution_minutes * 60);
    const nowIdx = buckets.indexOf(nowBucket);
    if (nowIdx >= 0) {
      const nx = xScale(nowIdx);
      svg += `<line x1="${nx}" y1="${PAD.top}" x2="${nx}" y2="${PAD.top+iH}" stroke="#cc4400" stroke-width="1" stroke-dasharray="4,3" opacity="0.7"/>`;
      svg += `<text x="${nx+3}" y="${PAD.top+10}" font-size="8" fill="#cc4400" opacity="0.8">NOW</text>`;
    }
  }

  // Lines
  for (const band of data.bands) {
    if (hiddenBands.has(band)) continue;
    const pts = data.series[band];
    const path = pts.map((v,i) => `${i===0?'M':'L'}${xScale(i).toFixed(1)},${yScale(v).toFixed(1)}`).join(' ');
    svg += `<path d="${path}" fill="none" stroke="${bandColor(band)}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>`;
  }
  svg += `</svg>`;

  const resLabel = data.resolution_minutes >= 60 ? `${data.resolution_minutes/60}h buckets` : `${data.resolution_minutes}m buckets`;
  const windowLabel = data.snap_to_utc_day
    ? `${data.lookback_hours}h · UTC day-aligned`
    : `${data.lookback_hours}h window`;
  const legend = data.bands.map(b =>
    `<div class="ts-legend-item${hiddenBands.has(b)?' muted':''}" onclick="toggleBand('${b}',this)">
      <div style="width:22px;height:3px;border-radius:2px;background:${bandColor(b)}"></div>
      <span style="color:${bandColor(b)}">${b}</span>
    </div>`).join('');

  ct.innerHTML = `
    <div class="ts-controls">TIME-SERIES &middot; ${windowLabel} &middot; ${resLabel} &middot; UTC</div>
    <div class="ts-canvas-wrap">${svg}</div>
    <div class="ts-legend">${legend}</div>`;
}

function toggleBand(band, el) {
  if (hiddenBands.has(band)) hiddenBands.delete(band);
  else hiddenBands.add(band);
  el.classList.toggle('muted');
  if (chartData) renderChart(chartData);
}


// ── SNR overlay toggle ────────────────────────────────────────────────────────
function toggleSNR(btn) {
  if (tableMode || chartMode) return;  // no-op when heatmap not visible
  snrMode = !snrMode;
  if (snrMode) {
    btn.style.background = '#446688';
    btn.style.color = '#fff';
  } else {
    btn.style.background = '';
    btn.style.color = '#888';
  }
  if (lastData) renderHeatmap(lastData);
}

</script>
</body>
</html>
"""


@app.route("/")
def dashboard():
    return render_template_string(DASHBOARD_HTML)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    global DB_PATH
    parser = argparse.ArgumentParser(description="HFWatch web dashboard")
    parser.add_argument("--db",   default=str(DEFAULT_DB), help="Path to SQLite database")
    parser.add_argument("--port", type=int, default=5000,  help="HTTP port (default: 5000)")
    parser.add_argument("--host", default="0.0.0.0",       help="Bind address (default: 0.0.0.0)")
    args = parser.parse_args()

    DB_PATH = Path(args.db)
    init_db(DB_PATH)

    print(f"HFWatch dashboard starting on http://{args.host}:{args.port}")
    print(f"Database: {DB_PATH}")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
