/* CAT Operator Copilot — client app. Renders each page from the backend APIs. */
(function () {
  "use strict";

  const LANG_LABEL = { "en-IN": "English", "hi-IN": "हिन्दी", "es-ES": "Español", "ta-IN": "தமிழ்" };
  const weatherIcon = { Sunny: "☀", Cloudy: "☁", Rainy: "🌧", Windy: "🌬", Storm: "⛈" };
  const statusTone = { Completed: "b-ok", "In Progress": "b-info", Delayed: "b-warn", Scheduled: "", Cancelled: "" };

  // ---- session state ----
  const session = loadSession();
  function loadSession() {
    let s = { operatorId: "OP1001", machineId: "EXC001", language: "en-IN" };
    try { const raw = localStorage.getItem("cat-session"); if (raw) Object.assign(s, JSON.parse(raw)); } catch (e) {}
    return s;
  }
  function saveSession() { try { localStorage.setItem("cat-session", JSON.stringify(session)); } catch (e) {} }

  // ---- helpers ----
  const $ = (sel, root) => (root || document).querySelector(sel);
  async function api(path, opts) {
    const r = await fetch(path, opts);
    if (r.status === 401) { window.location.href = "/login"; throw new Error("unauthorized"); }
    return r.json();
  }
  // Identity now comes from the signed session cookie server-side; no params sent.
  function qs() { return "_=" + Date.now(); }

  // ---- connectivity + voice mode ----
  const conn = { online: navigator.onLine, voice: null };
  function isOffline() { return !navigator.onLine; }

  async function initConnectivity() {
    try { const s = await fetch("/api/voice/status").then(r => r.json()); conn.voice = s; } catch (e) {}
    paintConn();
    window.addEventListener("online", paintConn);
    window.addEventListener("offline", paintConn);
  }
  function paintConn() {
    const badge = $("#conn-badge"), text = $("#conn-text"), vm = $("#voice-mode");
    if (!badge) return;
    const off = isOffline();
    badge.classList.toggle("conn-online", !off);
    badge.classList.toggle("conn-offline", off);
    if (text) text.textContent = off ? "Offline" : "Online";
    if (vm) {
      // Which voice engine will actually run right now.
      const hasVosk = conn.voice && conn.voice.offlineAvailable;
      const mode = off ? (hasVosk ? "On-device voice" : "Text only")
        : (hasVosk ? "On-device voice" : "Browser voice");
      vm.textContent = "🎙 " + mode;
    }
    if (off) flushQueue(); // no-op offline, but harmless; real flush on 'online'
  }
  window.addEventListener("online", () => { paintConn(); flushQueue(); });

  // ---- WAV recorder (16k mono) for the offline/on-device STT pipeline ----
  function VoiceRecorder() {
    let ac, source, proc, stream, chunks = [], sr = 16000;
    this.start = async function () {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      ac = new (window.AudioContext || window.webkitAudioContext)();
      sr = ac.sampleRate;
      source = ac.createMediaStreamSource(stream);
      proc = ac.createScriptProcessor(4096, 1, 1);
      chunks = [];
      proc.onaudioprocess = e => chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
      source.connect(proc); proc.connect(ac.destination);
    };
    this.stop = function () {
      try { proc.disconnect(); source.disconnect(); ac.close(); stream.getTracks().forEach(t => t.stop()); } catch (e) {}
      const flat = flatten(chunks);
      const down = downsample(flat, sr, 16000);
      return encodeWavBase64(down, 16000);
    };
  }
  function flatten(chunks) {
    let len = 0; chunks.forEach(c => len += c.length);
    const out = new Float32Array(len); let o = 0;
    chunks.forEach(c => { out.set(c, o); o += c.length; });
    return out;
  }
  function downsample(buf, inRate, outRate) {
    if (outRate >= inRate) return buf;
    const ratio = inRate / outRate, outLen = Math.round(buf.length / ratio);
    const out = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const start = Math.floor(i * ratio), end = Math.floor((i + 1) * ratio);
      let sum = 0, n = 0;
      for (let j = start; j < end && j < buf.length; j++) { sum += buf[j]; n++; }
      out[i] = n ? sum / n : 0;
    }
    return out;
  }
  function encodeWavBase64(samples, rate) {
    const buf = new ArrayBuffer(44 + samples.length * 2), view = new DataView(buf);
    const ws = (o, s) => { for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i)); };
    ws(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); ws(8, "WAVE"); ws(12, "fmt ");
    view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true);
    view.setUint16(34, 16, true); ws(36, "data"); view.setUint32(40, samples.length * 2, true);
    let o = 44;
    for (let i = 0; i < samples.length; i++) { let s = Math.max(-1, Math.min(1, samples[i])); view.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true); o += 2; }
    let bin = ""; const bytes = new Uint8Array(buf);
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin);
  }

  // ---- offline write queue (shift notes) ----
  function queueKey() { return "cat-offline-queue"; }
  function enqueue(item) {
    try { const q = JSON.parse(localStorage.getItem(queueKey()) || "[]"); q.push(item); localStorage.setItem(queueKey(), JSON.stringify(q)); } catch (e) {}
  }
  async function flushQueue() {
    if (isOffline()) return;
    let q = [];
    try { q = JSON.parse(localStorage.getItem(queueKey()) || "[]"); } catch (e) { return; }
    if (!q.length) return;
    const remaining = [];
    for (const item of q) {
      try { const r = await fetch(item.url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(item.body) }); if (!r.ok) remaining.push(item); }
      catch (e) { remaining.push(item); }
    }
    try { localStorage.setItem(queueKey(), JSON.stringify(remaining)); } catch (e) {}
    if (q.length !== remaining.length && document.body.dataset.page === "shift") renderShift();
  }
  function queuedCount() { try { return JSON.parse(localStorage.getItem(queueKey()) || "[]").length; } catch (e) { return 0; } }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
  const root = () => $("#page-root");

  // ---- logged-in operator badge (nav) ----
  async function initIdentity() {
    const logout = $("#logout-btn");
    if (logout) logout.addEventListener("click", async () => {
      try { await fetch("/api/logout", { method: "POST" }); } catch (e) {}
      window.location.href = "/login";
    });
    const nameEl = $("#op-name");
    if (!nameEl) return;
    try {
      const me = await api("/api/me");
      session.operatorId = me.operatorId; session.machineId = me.machineId;
      if (me.language && !localStorage.getItem("cat-lang-set")) session.language = me.language;
      saveSession();
      nameEl.textContent = me.operatorName;
      $("#op-machine").textContent = me.machineModel + " · " + me.machineId;
      $("#op-avatar").textContent = me.operatorName.split(" ").map(s => s[0]).join("").slice(0, 2);
    } catch (e) { /* api() already redirected on 401 */ }
  }

  // ================= HOME =================
  async function renderHome() {
    const c = await api("/api/context?" + qs());
    const hour = parseInt(c.now.slice(11, 13));
    const greet = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
    const first = c.operator.operator_name.split(" ")[0];
    const w = c.weather.current, cur = c.currentTask, nxt = c.nextTask;
    const attn = [];
    if (c.safety.todayAlerts > 0) attn.push(["b-danger", `⚠ ${c.safety.todayAlerts} safety alert(s) recorded${c.safety.lastAlertTime ? " — last at " + c.safety.lastAlertTime : ""}`]);
    if (c.safety.seatbeltViolations > 0) attn.push(["b-warn", `⚠ ${c.safety.seatbeltViolations} seatbelt violation(s) today`]);
    if (c.counts.delayed > 0) attn.push(["b-warn", `⏱ ${c.counts.delayed} task(s) delayed`]);
    if (c.weather.rainExpected) attn.push(["b-info", "🌧 Weather may affect afternoon tasks — try “Optimize My Day”"]);
    if (attn.length === 0) attn.push(["b-ok", "✓ All clear — no items need attention."]);

    root().innerHTML = `
      <div class="between">
        <div>
          <div class="label">${esc(c.today)} · ${esc(c.now.slice(11, 16))}</div>
          <h1 class="title">${greet}, <span class="yellow">${esc(first)}</span></h1>
          <p class="sub" style="font-size:18px">${esc(c.machine.machine_model)} · ${esc(c.machine.machine_id)} &nbsp;•&nbsp; ${esc(c.site.name)}</p>
          <p class="muted">Shift ${esc((c.shift && c.shift.shift_start) || "08:00")} – ${esc((c.shift && c.shift.shift_end) || "17:00")} · ${esc(c.operator.shift_type)}</p>
        </div>
        <a href="/assistant" class="btn btn-primary">🎙 Ask Operator Assistant</a>
      </div>

      <div class="grid grid-3 mt5">
        <div class="card">
          <div class="between"><span class="label">Current Task</span>
            <span class="pill ${cur ? "b-info" : ""}">${cur ? esc(cur.task_status) : "Between tasks"}</span></div>
          ${cur ? `<h2 style="font-size:24px;margin:8px 0 0">${esc(cur.task_type)}</h2>
            <p class="sub">${esc(cur.zone)} · Priority ${esc(cur.priority)}</p>
            <div class="mt4"><div class="between" style="font-size:13px;color:var(--gray)">
              <span>${esc(cur.scheduled_start)} → ${esc(cur.scheduled_end)}</span><span>${c.progress}%</span></div>
              <div class="progress"><span style="width:${c.progress}%"></span></div></div>`
            : `<p class="sub mt3">No task in progress right now.</p>`}
          <div class="between mt5" style="border-top:1px solid var(--line);padding-top:16px">
            <div><span class="label">Next</span><p style="font-weight:600;font-size:18px;margin:2px 0 0">${nxt ? esc(nxt.task_type) + " · " + esc(nxt.scheduled_start) : "No further tasks"}</p></div>
            <a href="/tasks" class="btn btn-ghost">View tasks</a>
          </div>
        </div>

        <div class="card">
          <span class="label">Weather · ${esc(c.site.name)}</span>
          <div class="row mt3" style="align-items:center">
            <span class="wea-icon">${weatherIcon[w && w.weather_condition] || "☁"}</span>
            <div><div style="font-size:30px;font-weight:800">${esc(w && w.temperature)}°C</div><div class="sub">${esc(w && w.weather_condition)}</div></div>
          </div>
          <div class="mt3" style="font-size:14px">
            <div class="between"><span class="muted">Rain probability</span><b>${esc(w && w.rain_probability)}%</b></div>
            <div class="between"><span class="muted">Wind</span><b>${esc(w && w.wind_speed)} km/h</b></div>
            <div class="between"><span class="muted">Ground</span><b>${esc(w && w.ground_condition)}</b></div>
          </div>
          ${c.weather.rainExpected ? `<div class="attn-item b-warn mt3">⚠ Rain expected around ${String(c.weather.rainStartHour).padStart(2, "0")}:00</div>` : ""}
        </div>
      </div>

      <div class="grid grid-3 mt5">
        <div class="card">
          <span class="label">Needs Attention</span>
          ${attn.map(a => `<div class="attn-item ${a[0]}">${esc(a[1])}</div>`).join("")}
        </div>
        <div class="card">
          <span class="label">Today</span>
          <div class="two mt3" style="grid-template-columns:repeat(3,1fr)">
            ${stat(c.counts.tasks, "Tasks")}${stat(c.counts.delayed, "Delayed", c.counts.delayed > 0 ? "t-warn" : "")}${stat(c.counts.safetyEvents, "Safety", c.counts.safetyEvents > 0 ? "t-danger" : "")}
          </div>
          <a href="/shift" class="btn btn-ghost mt4" style="width:100%">Open Shift Log</a>
        </div>
      </div>`;
  }
  function stat(n, l, tone) { return `<div class="stat"><div class="n ${tone || ""}">${n}</div><div class="l">${l}</div></div>`; }

  // ================= TASKS =================
  async function renderTasks() {
    root().innerHTML = `
      <div class="between"><h1 class="title">Today’s Tasks</h1>
        <div class="row"><button id="opt-btn" class="btn btn-primary">⚡ Optimize My Day</button>
          <button id="wi-btn" class="btn btn-ghost">🌧 What-If</button></div></div>
      <div id="wi-panel" class="hidden"></div>
      <div id="opt-panel" class="mt5"></div>
      <div id="task-grid" class="task-grid mt5"></div>`;

    const d = await api("/api/tasks?" + qs());
    $("#task-grid").innerHTML = d.tasks.map(t => {
      const p = t.prediction, wet = t.rain_probability > 50;
      return `<div class="card">
        <div class="between"><div><h3 style="font-size:20px;margin:0">${esc(t.task_type)}</h3>
          <p class="muted">${esc(t.zone)} · Priority ${esc(t.priority)}</p></div>
          <span class="pill ${statusTone[t.task_status] || ""}">${esc(t.task_status)}</span></div>
        <p class="sub mt3" style="font-size:18px">${esc(t.scheduled_start)} → ${esc(t.scheduled_end)}</p>
        <div class="two mt3">
          <div class="card2"><div class="label">Predicted</div><div style="font-size:20px;font-weight:800">${p.predicted} min</div>
            <div style="font-size:12px" class="${p.difference > 0 ? "t-warn" : "t-ok"}">${p.difference >= 0 ? "+" : ""}${p.difference} vs expected ${p.expected}</div></div>
          <div class="card2"><div class="label">Weather</div><div style="font-size:20px;font-weight:800">${weatherIcon[t.weather_condition]} ${esc(t.temperature)}°</div>
            <div style="font-size:12px" class="muted">Rain ${esc(t.rain_probability)}% · wind ${esc(t.wind_speed)}</div></div>
        </div>
        <p class="muted mt3" style="font-size:12px">Reason: ${esc(p.reason)}.</p>
        ${wet ? `<div class="attn-item b-warn mt3">⚠ Weather may increase task duration</div>` : ""}
      </div>`;
    }).join("");

    $("#opt-btn").addEventListener("click", optimize);
    $("#wi-btn").addEventListener("click", toggleWhatIf);
  }

  async function optimize() {
    const panel = $("#opt-panel");
    panel.innerHTML = `<div class="loading">Optimizing…</div>`;
    const o = await api("/api/optimize?" + qs());
    if (!o.changes.length) {
      panel.innerHTML = `<div class="card"><h2 style="margin:0 0 8px">⚡ Recommended Schedule</h2><p class="t-ok" style="font-weight:600">Your current order already handles the weather well — no changes recommended.</p></div>`;
      return;
    }
    panel.innerHTML = `<div class="card">
      <div class="between"><h2 style="margin:0">⚡ Recommended Schedule</h2></div>
      <div class="two mt4">
        ${schedBlock("Current order", o.original, "cur")}
        ${schedBlock("Recommended order", o.optimized, "rec")}
      </div>
      <div class="card2 mt4"><span class="label">Why these changes</span>
        ${o.changes.map(c => `<p class="sub" style="font-size:14px;margin:6px 0 0"><b class="yellow">${esc(c.task)}</b>: ${esc(c.from)} → ${esc(c.to)}. ${esc(c.reason)}</p>`).join("")}
        ${o.completionOriginal !== o.completionOptimized
          ? `<p class="mt3" style="font-size:14px">Estimated completion: <b class="muted" style="text-decoration:line-through">${esc(o.completionOriginal)}</b> → <b class="t-ok">${esc(o.completionOptimized)}</b></p>`
          : `<p class="mt3" style="font-size:14px">Completion time unchanged (~${esc(o.completionOptimized)}), but weather exposure drops from <b class="t-warn">${o.weatherPenaltyOriginal}</b> to <b class="t-ok">${o.weatherPenaltyOptimized}</b> — sensitive work moves out of the rain window.</p>`}
      </div></div>`;
  }
  function schedBlock(title, slots, cls) {
    return `<div class="sched ${cls}"><div class="label">${title}</div><ol>${slots.map(s =>
      `<li><span style="font-weight:600">${esc(s.start)} ${esc(s.task_type)}</span><span class="muted">${esc(s.zone)} · ${s.predicted_min}m</span></li>`).join("")}</ol></div>`;
  }

  function toggleWhatIf() {
    const panel = $("#wi-panel");
    if (!panel.classList.contains("hidden")) { panel.classList.add("hidden"); return; }
    panel.classList.remove("hidden");
    const opts = [];
    for (let h = 12; h <= 17; h++) opts.push(`<option value="${h}"${h === 13 ? " selected" : ""}>${String(h).padStart(2, "0")}:00</option>`);
    panel.innerHTML = `<div class="card mt5"><div class="row" style="align-items:center">
      <span class="label">What if rain begins at</span>
      <select id="wi-hour" class="select" style="width:auto">${opts.join("")}</select>
      <button id="wi-run" class="btn btn-primary" style="padding:8px 20px">Simulate</button></div>
      <div id="wi-result" class="mt4"></div></div>`;
    $("#wi-run").addEventListener("click", async () => {
      const h = $("#wi-hour").value;
      const r = await api("/api/optimize?" + qs() + "&rainHour=" + h);
      $("#wi-result").innerHTML = `<div class="grid" style="grid-template-columns:1fr 1fr 1fr;gap:12px">
        ${compare("Without rain", r.completionNoRain, "t-ok")}
        ${compare("With rain", r.completionWithRain, "t-danger", "Affected: " + (r.affected.join(", ") || "none"))}
        ${compare("Optimized plan", r.completionOptimized, "yellow")}</div>`;
    });
  }
  function compare(title, time, tone, note) {
    return `<div class="compare"><div class="label">${title}</div><div class="time ${tone}">${esc(time)}</div>${note ? `<div class="muted" style="font-size:12px;margin-top:4px">${esc(note)}</div>` : ""}</div>`;
  }

  // ================= SHIFT =================
  const statusIcon = { Completed: "✓", Delayed: "⚠", "In Progress": "▶", Scheduled: "○", Cancelled: "✕" };
  async function renderShift() {
    const d = await api("/api/shift?" + qs());
    const m = d.metrics, notes = d.runtimeNotes || [];
    const closed = d.runtimeState === "Closed";
    root().innerHTML = `
      <div class="between">
        <div><h1 class="title">My Shift</h1>
          <p class="muted">${esc(d.operator && d.operator.operator_name)} · ${esc(d.machine && d.machine.machine_model)} (${esc(d.machine && d.machine.machine_id)}) · ${esc(d.shift && d.shift.shift_date)}</p></div>
        <div class="row" style="align-items:center">
          <span class="pill ${closed ? "" : "b-ok"}">${closed ? "● Closed" : "● Active"}</span>
          ${closed ? "" : `<button id="end-shift" class="btn btn-primary">End Shift</button>`}</div>
      </div>

      <div class="metrics mt5">
        ${metric("Fuel Used", m.fuel + " L")}${metric("Idle Time", m.idle + " min")}${metric("Load Cycles", m.loadCycles)}
        ${metric("Safety Alerts", m.safetyAlerts, m.safetyAlerts > 0 ? "t-danger" : "")}${metric("Seatbelt Viol.", m.seatbeltViolations, m.seatbeltViolations > 0 ? "t-warn" : "")}
      </div>

      <div class="grid grid-2 mt5">
        <div class="card"><span class="label">Task Timeline</span><ol class="timeline">
          ${d.tasks.map(t => `<li><span class="tl-ico ${t.task_status === "Completed" ? "b-ok" : t.task_status === "Delayed" ? "b-warn" : t.task_status === "In Progress" ? "b-info" : ""}">${statusIcon[t.task_status] || "○"}</span>
            <span style="flex:1"><b>${esc(t.task_type)}</b> <span class="muted">· ${esc(t.zone)}</span></span>
            <span class="muted" style="font-size:14px">${esc(t.scheduled_start)}</span></li>`).join("")}</ol></div>

        <div class="card" style="border-color:rgba(255,205,17,.4)">
          <div class="between"><span class="label">AI-Generated Handover</span><span class="pill" style="background:rgba(255,205,17,.15);color:var(--cat-yellow)">Insight</span></div>
          <p class="sub mt3" id="handover-text" style="line-height:1.6">${esc(d.handover)}</p>
          <p class="muted mt3" style="font-size:11px">Generated from tasks, safety events, weather and operator notes — distinct from the raw metrics above.</p>
        </div>
      </div>

      <div class="card mt5"><span class="label">Operator Notes</span>
        <div class="row mt3" style="flex-wrap:nowrap">
          <input id="note-input" class="input" placeholder='e.g. "Trenching in Zone B was slower because of wet ground."' />
          <button id="note-voice" class="btn btn-ghost">🎙</button>
          <button id="note-add" class="btn btn-primary">Add</button></div>
        <div id="notes-list" class="mt4">${renderNotes(notes)}</div>
      </div>
      <div id="end-msg"></div>`;

    const addNote = async (source) => {
      const inp = $("#note-input"); const text = inp.value.trim(); if (!text) return;
      const body = { action: "note", text, language: session.language, source };
      inp.value = "";
      if (isOffline()) {
        // Queue locally; sync automatically when connectivity returns.
        enqueue({ url: "/api/shift", body });
        const list = $("#notes-list");
        list.insertAdjacentHTML("afterbegin", `<div class="note"><p style="margin:0">${esc(text)}</p><div class="tags"><span class="pill b-warn">queued · will sync</span></div></div>`);
        return;
      }
      try {
        await fetch("/api/shift", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
        renderShift();
      } catch (e) { enqueue({ url: "/api/shift", body }); renderShift(); }
    };
    $("#note-add").addEventListener("click", () => addNote("text"));
    $("#note-input").addEventListener("keydown", e => { if (e.key === "Enter") addNote("text"); });
    $("#note-voice").addEventListener("click", () => {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) { alert("Speech recognition unavailable — type the note instead."); return; }
      const rec = new SR(); rec.lang = session.language; rec.interimResults = false;
      rec.onresult = e => { $("#note-input").value = e.results[0][0].transcript; addNote("voice"); };
      rec.start();
    });
    const endBtn = $("#end-shift");
    if (endBtn) endBtn.addEventListener("click", async () => {
      const r = await api("/api/shift", { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ action: "end", operatorId: session.operatorId, machineId: session.machineId }) });
      $("#handover-text").textContent = r.handover;
      $("#end-msg").innerHTML = `<div class="attn-item b-ok mt5">✓ Shift ended. Handover summary generated above — ready for the next operator.</div>`;
      endBtn.remove();
    });
  }
  function metric(l, v, tone) { return `<div class="metric"><div class="v ${tone || ""}">${v}</div><div class="l">${l}</div></div>`; }
  function renderNotes(notes) {
    if (!notes.length) return `<p class="muted" style="font-size:14px">No notes yet. Add one by voice or text — it will feed the handover.</p>`;
    return notes.map(n => `<div class="note"><p style="margin:0">${esc(n.note)}</p><div class="tags">
      <span class="pill">${esc(n.source)}</span>${n.category ? `<span class="pill">${esc(n.category)}</span>` : ""}
      ${n.task ? `<span class="pill yellow">${esc(n.task)}</span>` : ""}${n.reason ? `<span class="pill">${esc(n.reason)}</span>` : ""}
      ${n.duration_minutes ? `<span class="pill">${n.duration_minutes} min</span>` : ""}</div></div>`).join("");
  }

  // ================= SAFETY =================
  const sevTone = { High: "b-danger", Medium: "b-warn", Low: "" };
  async function renderSafety() {
    const d = await api("/api/safety?" + qs());
    const s = d.status;
    const level = s.level === "attention" ? ["Needs Attention", "t-danger", "b-danger"] : s.level === "caution" ? ["Caution", "t-warn", "b-warn"] : ["All Clear", "t-ok", "b-ok"];
    root().innerHTML = `<h1 class="title">Safety</h1>
      <div class="grid mt5" style="grid-template-columns:1fr 1fr 1fr;gap:16px">
        <div class="card ${level[2]}"><span class="label">Overall Status</span><div class="${level[1]}" style="font-size:22px;font-weight:800;margin-top:4px">${level[0]}</div></div>
        <div class="card"><span class="label">Seatbelt (latest)</span><div class="${s.seatbeltStatus === "Fastened" ? "t-ok" : "t-danger"}" style="font-size:22px;font-weight:800;margin-top:4px">${esc(s.seatbeltStatus)}</div></div>
        <div class="card"><span class="label">Today’s Alerts</span><div class="${s.todayAlerts > 0 ? "t-danger" : "t-ok"}" style="font-size:22px;font-weight:800;margin-top:4px">${s.todayAlerts}</div></div>
      </div>
      <div class="card mt5"><span class="label">Potential Unusual Patterns</span>
        ${d.insights.length === 0 ? `<p class="t-ok" style="font-weight:600">No unusual patterns detected against this operator’s baseline.</p>`
          : d.insights.map(i => `<div class="badge-ins ${i.severity === "attention" ? "b-danger" : i.severity === "caution" ? "b-warn" : "b-info"}"><b>${esc(i.type)}:</b> ${esc(i.message)}</div>`).join("")}
        <p class="muted mt3" style="font-size:11px">Transparent rule-based baselines over synthetic telemetry. Flags indicate potential patterns for review, not confirmed unsafe behaviour.</p>
      </div>
      <div class="card mt5"><span class="label">Recent Incidents</span>
        ${d.incidents.length === 0 ? `<p class="muted">No incidents recorded.</p>` : d.incidents.map(inc => `<div class="inc">
          <span class="pill ${sevTone[inc.severity] || ""}">${esc(inc.severity)}</span>
          <span style="font-weight:600">${esc(inc.incident_type)}</span>
          <span class="muted" style="font-size:14px;flex:1">${esc(inc.description)}</span>
          <span class="muted" style="font-size:12px">${esc((inc.timestamp || "").slice(5, 16).replace("T", " "))}</span>
          <span class="pill ${inc.status === "Resolved" ? "b-ok" : "b-warn"}" style="font-size:12px">${esc(inc.status)}</span></div>`).join("")}
      </div>`;
  }

  // ================= TRAINING =================
  const MODULES = [
    { title: "Pre-Start Walkaround", mins: 6, level: "Basic", desc: "General checks before beginning a shift. Always follow the official machine manual." },
    { title: "Working in Wet Conditions", mins: 8, level: "Standard", desc: "How rain and muddy ground affect trenching, grading and excavation timing and traction." },
    { title: "Efficient Load Cycles", mins: 10, level: "Standard", desc: "Reducing idle time and improving cycle consistency for loading and movement tasks." },
    { title: "Seatbelt & Cab Safety", mins: 4, level: "Basic", desc: "Why seatbelt use is recorded and reviewed every shift." },
    { title: "Reading Weather-Aware Plans", mins: 7, level: "Advanced", desc: "Interpreting the Copilot's optimized schedule and what-if simulations." },
  ];
  async function renderTraining() {
    const c = await api("/api/context?" + qs());
    const rec = c.operator.skill_level === "Beginner" ? "Basic" : c.operator.skill_level === "Expert" ? "Advanced" : "Standard";
    root().innerHTML = `<h1 class="title">Training</h1>
      <div class="card2 ctx-bar mt4"><span class="label">Personalised for</span>
        <span><b class="yellow">${esc(c.operator.operator_name)}</b></span><span>Skill: ${esc(c.operator.skill_level)}</span>
        <span>Training level: ${esc(c.operator.training_level)}</span><span>Recommended track: <b>${rec}</b></span></div>
      <div class="mods mt5">${MODULES.map(m => `<div class="card" ${m.level === rec ? 'style="border-color:rgba(255,205,17,.5)"' : ""}>
        <div class="between"><h3 style="font-size:18px;margin:0">${esc(m.title)}</h3><span class="pill">${m.level}</span></div>
        <p class="muted mt3" style="font-size:14px">${esc(m.desc)}</p>
        <div class="between mt4"><span class="muted" style="font-size:14px">⏱ ${m.mins} min</span>${m.level === rec ? `<span class="yellow" style="font-size:14px;font-weight:600">Recommended</span>` : ""}</div></div>`).join("")}</div>
      <div class="card mt5"><span class="label">Coaching</span>
        <p class="sub mt3">Have a question during a task? The Operator Assistant can explain procedures conservatively and always defers safety-critical steps to the official manual and your supervisor.</p>
        <a href="/assistant" class="btn btn-primary mt3">🎙 Ask the Assistant</a></div>`;
  }

  // ================= ASSISTANT =================
  const SUGGESTIONS = ["What do I have to do today?", "What's my next task?", "Will the weather affect my work?", "Optimize my day", "Do I have any safety issues?", "Will I finish on time?"];
  let assistantState = { msgs: [], state: "idle", rec: null };

  async function renderAssistant() {
    const langOpts = Object.keys(LANG_LABEL).map(k => `<option value="${k}"${k === session.language ? " selected" : ""}>${LANG_LABEL[k]}</option>`).join("");
    root().outerHTML = `<div id="page-root" class="assistant-wrap">
      <div class="between" style="margin-bottom:12px"><h1 style="font-size:24px;font-weight:800;margin:0">Operator Assistant</h1>
        <div class="row" style="align-items:center"><span class="label">Language</span>
          <select id="lang-sel" class="select" style="width:auto">${langOpts}</select></div></div>
      <div id="ctx-bar" class="card2 ctx-bar" style="margin-bottom:12px"></div>
      <div id="conv" class="conv"></div>
      <div id="voice-info" class="t-warn" style="font-size:14px;margin-bottom:8px"></div>
      <div id="chips" class="chips"></div>
      <div class="row" style="align-items:center;flex-wrap:nowrap;padding-top:8px">
        <button id="mic" class="mic"><span id="mic-glyph">🎙</span></button>
        <div style="flex:1">
          <div id="state-label" style="font-size:12px;font-weight:600;color:var(--gray);margin-bottom:4px;height:16px">Tap to speak</div>
          <form id="chat-form" class="row" style="flex-wrap:nowrap"><input id="chat-input" class="input" placeholder="Type a message…" /><button type="submit" class="btn btn-primary">Send</button></form>
        </div>
      </div>
      <p class="muted" style="font-size:11px;margin-top:8px">Voice uses your backend Voice API abstraction (Google Cloud STT/TTS when configured; browser speech as fallback). Answers are grounded in synthetic operational data.</p>
    </div>`;

    const c = await api("/api/context?" + qs());
    $("#ctx-bar").innerHTML = `<span class="label">Context</span><span><b class="yellow">${esc(c.machine.machine_model)} · ${esc(c.machine.machine_id)}</b></span>
      <span>${c.currentTask ? esc(c.currentTask.task_type + " (" + c.currentTask.zone + ")") : "Between tasks"}</span><span>${esc(c.site.name)}</span><span>Shift: ${esc(c.operator.shift_type)}</span>`;
    $("#chips").innerHTML = SUGGESTIONS.map(s => `<button class="chip">${esc(s)}</button>`).join("");
    $("#chips").querySelectorAll(".chip").forEach(ch => ch.addEventListener("click", () => sendMsg(ch.textContent)));
    $("#lang-sel").addEventListener("change", e => { session.language = e.target.value; saveSession(); try { localStorage.setItem("cat-lang-set", "1"); } catch (x) {} });
    $("#chat-form").addEventListener("submit", e => { e.preventDefault(); const v = $("#chat-input").value; $("#chat-input").value = ""; sendMsg(v); });
    $("#mic").addEventListener("click", micClick);
    drawConv();
  }

  function setState(s) {
    assistantState.state = s;
    const map = { idle: "Tap to speak", listening: "Listening…", processing: "Understanding…", responding: "Speaking…" };
    const lbl = $("#state-label"); if (lbl) lbl.textContent = map[s];
    const mic = $("#mic"), glyph = $("#mic-glyph");
    if (!mic) return;
    mic.querySelectorAll(".ring").forEach(r => r.remove());
    if (s === "listening") { const r = document.createElement("span"); r.className = "ring"; mic.prepend(r); }
    if (glyph) glyph.textContent = s === "responding" ? "⏹" : "🎙";
  }

  function drawConv() {
    const conv = $("#conv"); if (!conv) return;
    if (assistantState.msgs.length === 0) {
      conv.innerHTML = `<div style="text-align:center;color:var(--gray);padding:40px 0"><div style="font-size:48px;margin-bottom:12px">🎙</div><p class="sub" style="font-size:18px;font-weight:600">How can I help?</p><p style="font-size:14px">Tap the mic or pick a question below.</p></div>`;
      return;
    }
    conv.innerHTML = assistantState.msgs.map(m => {
      if (m.role === "operator") { const sttTag = m.stt ? `<span style="opacity:.6"> · 🎙 on-device</span>` : ""; return `<div class="msg op"><div class="bubble op"><div class="who">You${sttTag}</div><p style="margin:0">${esc(m.text)}</p></div></div>`; }
      const cls = m.safety ? "safety" : "as";
      const tag = m.safety ? `<span class="t-danger"> ⚠ Safety guidance</span>`
        : m.source === "llm" ? `<span style="opacity:.6"> · cloud AI</span>`
        : `<span style="opacity:.6"> · on-device${m.offline ? " · offline" : ""}</span>`;
      return `<div class="msg"><div class="bubble ${cls}"><div class="who">Assistant${tag}</div><p style="margin:0">${esc(m.text)}</p></div></div>`;
    }).join("");
    conv.scrollTop = conv.scrollHeight;
  }

  async function sendMsg(text, meta) {
    if (!text || !text.trim()) return;
    assistantState.msgs.push({ role: "operator", text, stt: meta && meta.onDeviceStt ? "on-device" : null });
    drawConv(); setState("processing");
    try {
      const d = await api("/api/assistant", { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ text, language: session.language, offline: isOffline() }) });
      assistantState.msgs.push({ role: "assistant", text: d.answer, source: d.source, safety: d.safetyCritical, offline: d.offline });
      drawConv();
      speak(d.answer, session.language);
    } catch (e) {
      assistantState.msgs.push({ role: "assistant", text: "Sorry, I couldn't process that. Please try again." });
      drawConv(); setState("idle");
    }
  }

  function speak(text, lang) {
    try {
      if (!window.speechSynthesis) { setState("idle"); return; }
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text); u.lang = lang;
      u.onstart = () => setState("responding"); u.onend = () => setState("idle");
      window.speechSynthesis.speak(u);
    } catch (e) { setState("idle"); }
  }

  function micClick() {
    // Stop if already active.
    if (assistantState.state === "listening") { return stopListening(); }
    if (assistantState.state === "responding") { try { window.speechSynthesis.cancel(); } catch (e) {} setState("idle"); return; }

    const hasVosk = conn.voice && conn.voice.offlineAvailable;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

    // Offline (or no browser STT): use the on-device Vosk pipeline via the backend.
    if ((isOffline() || !SR) && hasVosk) { return startOnDeviceRecording(); }
    // Offline with no engine at all: text only.
    if (isOffline() && !hasVosk) { $("#voice-info").textContent = "Offline and no on-device voice model available — use the text box below."; return; }
    // Online: browser Web Speech API (best accuracy).
    if (!SR) { if (hasVosk) return startOnDeviceRecording(); $("#voice-info").textContent = "Speech recognition isn't available — use the text box below."; return; }
    const rec = new SR(); assistantState.rec = rec; assistantState.mode = "browser";
    rec.lang = session.language; rec.interimResults = false; rec.continuous = false;
    setState("listening");
    rec.onresult = e => { let t = ""; for (let i = 0; i < e.results.length; i++) t += e.results[i][0].transcript; sendMsg(t); };
    rec.onerror = () => { setState("idle"); $("#voice-info").textContent = "Microphone error — use the text box below."; };
    rec.onend = () => { if (assistantState.state === "listening") setState("idle"); };
    rec.start();
  }

  async function startOnDeviceRecording() {
    try {
      const recorder = new VoiceRecorder();
      assistantState.recorder = recorder; assistantState.mode = "vosk";
      await recorder.start();
      setState("listening");
      $("#voice-info").textContent = "On-device recognition — recording… tap the mic again to stop.";
      // Safety auto-stop after 10s.
      assistantState.autostop = setTimeout(() => { if (assistantState.state === "listening") stopListening(); }, 10000);
    } catch (e) {
      setState("idle"); $("#voice-info").textContent = "Microphone unavailable — use the text box below.";
    }
  }

  async function stopListening() {
    clearTimeout(assistantState.autostop);
    if (assistantState.mode === "browser") { try { assistantState.rec.stop(); } catch (e) {} setState("idle"); return; }
    // Vosk path: encode + send to backend for on-device transcription.
    setState("processing");
    $("#voice-info").textContent = "";
    let wavB64;
    try { wavB64 = assistantState.recorder.stop(); } catch (e) { setState("idle"); return; }
    try {
      const d = await api("/api/voice/transcribe", { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ audio: wavB64, language: session.language }) });
      if (d.transcript && d.transcript.trim()) { sendMsg(d.transcript, { onDeviceStt: true }); }
      else { setState("idle"); $("#voice-info").textContent = "Didn't catch that — try again or type your question."; }
    } catch (e) { setState("idle"); $("#voice-info").textContent = "Transcription failed — use the text box."; }
  }

  // ---- router ----
  function renderPage() {
    const page = document.body.dataset.page;
    const r = { home: renderHome, tasks: renderTasks, shift: renderShift, safety: renderSafety, training: renderTraining, assistant: renderAssistant }[page];
    if (r) r();
  }

  initIdentity();
  initConnectivity();
  flushQueue();
  renderPage();
})();
