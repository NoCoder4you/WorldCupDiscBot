/* ======================= SPA NAV + THEME ======================= */
document.addEventListener('DOMContentLoaded', () => {
  // SPA navigation
  document.querySelectorAll('.menu li a').forEach(link => {
    link.addEventListener('click', function (e) {
      e.preventDefault();
      document.querySelectorAll('section').forEach(s => s.classList.remove('active-section'));
      const page = this.dataset.page;
      if (page) document.getElementById(page).classList.add('active-section');
      document.querySelectorAll('.menu li a').forEach(a => a.classList.remove('active'));
      this.classList.add('active');
      document.getElementById('menu-toggle').checked = false;

      // Lazy-load data per page
      if (page === 'cogs') loadCogs();
      if (page === 'log')  initLogsView();
      if (page === 'ownership') loadOwnerships();
      if (page === 'splits') loadSplitRequests();
      if (page === 'bets') { setupBetsRefreshButton(); loadBets(); }
      if (page === 'backups') initBackupsView();
    });
  });

  // Theme toggle
  let darkMode = !document.body.classList.contains('light-theme');
  const themeBtn = document.getElementById('theme-toggle');
  const themeIcon = document.getElementById('theme-icon');
  if (themeBtn) themeBtn.addEventListener('click', () => {
    darkMode = !darkMode;
    document.body.classList.toggle('light-theme', !darkMode);
    if (themeIcon) themeIcon.textContent = darkMode ? "🌙" : "☀️";
  });

  // Init
  initAdminAuth();
  wireBotButtons();
  fetchDashboard();
  setInterval(fetchDashboard, 6000);
});

/* ======================= NOTIFY BAR ======================= */
function showNotify(msg, type = 'success') {
  const notify = document.getElementById('notify-bar');
  if (!notify) return;
  notify.innerHTML = "";
  const div = document.createElement('div');
  div.className = `notify-${type}`;
  div.textContent = msg;
  notify.appendChild(div);
  setTimeout(() => { if (notify.contains(div)) notify.removeChild(div); }, 2300);
}

/* ======================= ADMIN AUTH ======================= */
let ADMIN_UNLOCKED = false;

async function refreshAdminUI() {
  document.querySelectorAll('[data-admin="true"]').forEach(el => {
    el.style.display = ADMIN_UNLOCKED ? '' : 'none';
  });

  const badge = document.getElementById('admin-status');
  const loginBtn = document.getElementById('admin-button');
  const logoutBtn = document.getElementById('admin-logout');

  if (badge) {
    if (ADMIN_UNLOCKED) {
      badge.textContent = "🔓 Admin";
      badge.classList.remove('admin-locked');
      badge.classList.add('admin-unlocked');
    } else {
      badge.textContent = "🔒 Admin";
      badge.classList.add('admin-locked');
      badge.classList.remove('admin-unlocked');
    }
  }
  if (loginBtn) loginBtn.style.display = ADMIN_UNLOCKED ? 'none' : '';
  if (logoutBtn) logoutBtn.style.display = ADMIN_UNLOCKED ? '' : 'none';
}

function initAdminAuth() {
  // Session check
  fetch('/admin/auth/status')
    .then(r => r.ok ? r.json() : { ok:false })
    .then(d => { ADMIN_UNLOCKED = !!(d && d.ok && d.authenticated); refreshAdminUI(); })
    .catch(() => refreshAdminUI());

  const openBtn = document.getElementById('admin-button');
  const backdrop = document.getElementById('admin-login-backdrop');
  const cancelBtn = document.getElementById('admin-cancel');
  const submitBtn = document.getElementById('admin-submit');
  const input = document.getElementById('admin-password');
  const logoutBtn = document.getElementById('admin-logout');

  if (openBtn) openBtn.onclick = () => {
    if (input) input.value = "";
    if (backdrop) { backdrop.style.display = 'flex'; setTimeout(() => input && input.focus(), 50); }
  };
  if (cancelBtn) cancelBtn.onclick = () => { if (backdrop) backdrop.style.display = 'none'; };
  if (submitBtn) submitBtn.onclick = loginAdmin;
  if (input) input.addEventListener('keydown', (e) => { if (e.key === 'Enter') loginAdmin(); });
  if (logoutBtn) logoutBtn.onclick = async () => {
    try {
      const r = await fetch('/admin/auth/logout', { method:'POST' });
      const d = await r.json();
      if (d.ok) { ADMIN_UNLOCKED = false; showNotify('Admin locked','success'); refreshAdminUI(); }
      else showNotify('Failed to logout','error');
    } catch { showNotify('Failed to logout','error'); }
  };

  async function loginAdmin() {
    if (!submitBtn || !input || !backdrop) return;
    const pw = input.value;
    submitBtn.disabled = true;
    try {
      const r = await fetch('/admin/auth/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ password: pw })
      });
      const d = await r.json();
      if (d.ok) {
        ADMIN_UNLOCKED = true;
        backdrop.style.display = 'none';
        showNotify('Admin unlocked','success');
        refreshAdminUI();
      } else {
        showNotify(d.error || 'Invalid password','error');
      }
    } catch {
      showNotify('Network error','error');
    } finally {
      submitBtn.disabled = false;
    }
  }
}

/* ======================= DASHBOARD ======================= */
function setGauge(barId, textId, percent, textValue) {
  const arcLen = 125.66;
  let value = Math.max(0, Math.min(100, Number(percent) || 0));
  let len = (arcLen * value) / 100;
  const bar = document.getElementById(barId);
  const text = document.getElementById(textId);
  if (bar) bar.setAttribute("stroke-dasharray", `${len},${arcLen - len}`);
  if (text) text.textContent = textValue;
}
function formatBytesMB(valMb) {
  const mb = Number(valMb) || 0;
  if (mb >= 1024*1024) return (mb / 1024 / 1024).toFixed(2) + " TB";
  if (mb >= 1024) return (mb / 1024).toFixed(2) + " GB";
  return Math.round(mb) + " MB";
}
async function fetchDashboard() {
  try {
    // Ping
    const pingStart = Date.now();
    const pingResp = await fetch('/api/ping');
    const pingData = await pingResp.json();
    const pingMs = Date.now() - pingStart;
    const pv = document.getElementById('ping-value');
    if (pv) pv.innerHTML = pingData.bot_running ? `${pingMs} ms` : `${pingMs} ms<br><span class='bot-down'>(Bot Down)</span>`;

    // Show correct start/stop/restart
    const startBtn = document.getElementById('start-bot');
    const stopBtn  = document.getElementById('stop-bot');
    const restartBtn = document.getElementById('restart-bot');
    if (startBtn && stopBtn && restartBtn) {
      startBtn.style.display = pingData.bot_running ? "none" : "";
      stopBtn.style.display  = pingData.bot_running ? "" : "none";
      restartBtn.style.display = pingData.bot_running ? "" : "none";
    }

    // Uptime
    const up = await (await fetch('/api/uptime')).json();
    const ul = document.getElementById('uptime-label');
    const uv = document.getElementById('uptime-value');
    if (ul && uv) {
      ul.textContent = up.bot_running ? "Uptime" : "Downtime";
      uv.textContent = up.bot_running ? (up.uptime_hms || '--:--:--') : (up.downtime_hms || '--:--:--');
    }

    // Guilds
    const g = await (await fetch('/api/guilds')).json();
    const gc = document.getElementById('guild-count');
    const gl = document.getElementById('guild-list');
    if (gc) gc.textContent = g.guild_count || '0';
    if (gl) gl.innerHTML = (g.guilds || []).map(x => x.name).join('<br>');

    // System
    const s = await (await fetch('/api/system')).json();
    const b = s.bot || {}, S = s.system || {};
    const bs = document.getElementById('botstats-value');
    if (bs) bs.innerHTML = (b.mem_mb != null) ? `${Number(b.mem_mb).toFixed(1)} MB<br>${Number(b.cpu_percent).toFixed(1)}% CPU` : "Not running";

    const memPercent = Math.round(S.mem_percent || 0);
    const memLabel = formatBytesMB(S.mem_used_mb) + " / " + formatBytesMB(S.mem_total_mb);
    const memExtra = document.getElementById('mem-extra'); if (memExtra) memExtra.textContent = memLabel;
    setGauge("mem-bar", "mem-text", memPercent, memPercent + "%");

    const cpuPercent = Math.round(S.cpu_percent || 0);
    const cpuExtra = document.getElementById('cpu-extra'); if (cpuExtra) cpuExtra.textContent = `${cpuPercent}%`;
    setGauge("cpu-bar", "cpu-text", cpuPercent, cpuPercent + "%");

    if ('disk_total_mb' in S) {
      const du = S.disk_used_mb || 0, dt = S.disk_total_mb || 1;
      const dp = dt ? Math.round((du / dt) * 100) : 0;
      const dx = document.getElementById('disk-extra'); if (dx) dx.textContent = `${formatBytesMB(du)} / ${formatBytesMB(dt)}`;
      setGauge("disk-bar", "disk-text", dp, dp + "%");
    }
  } catch (e) {
    const pv = document.getElementById('ping-value'); if (pv) pv.textContent = "Error";
    const uv = document.getElementById('uptime-value'); if (uv) uv.textContent = "Error";
  }
}
function wireBotButtons() {
  const restartBtn = document.getElementById('restart-bot');
  if (restartBtn) restartBtn.addEventListener('click', async () => {
    restartBtn.disabled = true; restartBtn.textContent = "Restarting...";
    try { await fetch('/api/bot/restart', { method: 'POST' }); showNotify("Bot restarted!", "success"); }
    catch { showNotify("Failed to restart bot.", "error"); }
    finally { restartBtn.disabled = false; restartBtn.textContent = "Restart Bot"; fetchDashboard(); }
  });

  const stopBtn = document.getElementById('stop-bot');
  if (stopBtn) stopBtn.addEventListener('click', async () => {
    stopBtn.disabled = true; stopBtn.textContent = "Stopping...";
    try { await fetch('/api/bot/stop', { method: 'POST' }); showNotify("Bot stopped!", "success"); }
    catch { showNotify("Failed to stop bot.", "error"); }
    finally { stopBtn.disabled = false; stopBtn.textContent = "Stop Bot"; fetchDashboard(); }
  });

  const startBtn = document.getElementById('start-bot');
  if (startBtn) startBtn.addEventListener('click', async () => {
    startBtn.disabled = true; startBtn.textContent = "Starting...";
    try { await fetch('/api/bot/start', { method: 'POST' }); showNotify("Bot started!", "success"); }
    catch { showNotify("Failed to start bot.", "error"); }
    finally { startBtn.disabled = false; startBtn.textContent = "Start Bot"; fetchDashboard(); }
  });
}

/* ======================= COGS PAGE ======================= */
async function loadCogs() {
  try {
    const resp = await fetch('/api/cogs');
    const data = await resp.json();
    const cogs = data.cogs || [];
    ensureCogsTable();
    const tbody = document.querySelector("#cogs-table tbody");
    tbody.innerHTML = "";
    for (let cog of cogs) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${cog.name}</td>
        <td><span class="${cog.loaded ? "cog-ok" : "cog-error"}">${cog.loaded ? "Loaded" : "Not loaded"}</span></td>
        <td>
          <button class="btn btn-restart" data-action="reload" data-cog="${cog.name}">Reload</button>
          <button class="btn btn-stop" data-action="unload" data-cog="${cog.name}">Unload</button>
          <button class="btn btn-restart" data-action="load" data-cog="${cog.name}">Load</button>
        </td>
        <td><span class="cog-error">${cog.last_error || ""}</span></td>
      `;
      tbody.appendChild(tr);
    }
    setTimeout(() => {
      document.querySelectorAll('#cogs-table .btn').forEach(btn =>
        btn.onclick = async () => {
          const action = btn.dataset.action, cog = btn.dataset.cog;
          btn.disabled = true;
          const resp = await fetch('/api/cogs/action', {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({cog, action})
          });
          btn.disabled = false;
          if (resp.ok) showNotify(`Sent ${action} for ${cog}`, "success");
          else showNotify(`Failed ${action} for ${cog}`, "error");
        });
    }, 0);
  } catch {
    showNotify("Failed to load cogs", "error");
  }
}
function ensureCogsTable() {
  const section = document.getElementById('cogs');
  if (!section) return;
  if (section.innerHTML.trim()) return;
  section.innerHTML = `
    <div class="card cogs-card">
      <div class="cogs-header"><span class="cogs-title">Loaded Cogs</span></div>
      <div class="cogs-table-scroll">
        <table class="cogs-table" id="cogs-table">
          <thead>
            <tr><th>Cog</th><th>Status</th><th>Actions</th><th>Last Error</th></tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  `;
}

/* ======================= LOG PAGE ======================= */
let currentLogType = 'bot';
let logLinesCache = [];
let logRefreshInterval = null;

function initLogsView() {
  const section = document.getElementById('log');
  if (!section) return;
  if (!section.innerHTML.trim()) {
    section.innerHTML = `
      <div class="card log-card">
        <div class="log-header">
          <div class="log-tabs">
            <button class="log-tab active" data-log="bot">WC.log</button>
            <button class="log-tab" data-log="health">health.log</button>
          </div>
          <div class="log-actions">
            <select id="log-filter">
              <option value="">All</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
              <option value="CRITICAL">CRITICAL</option>
              <option value="DEBUG">DEBUG</option>
              <option value="custom">Custom…</option>
            </select>
            <input type="text" id="log-search" placeholder="Custom filter..." style="display:none; width:120px;">
            <button id="log-download" class="btn btn-restart" title="Download Log">Download</button>
            <button id="log-clear" class="btn btn-stop" title="Clear Log">Clear</button>
            <button id="log-refresh" class="btn" title="Refresh">⟳</button>
          </div>
        </div>
        <div class="log-window" id="log-window"></div>
      </div>
    `;
  }
  bindLogEvents();
  loadLogLines(currentLogType);
  if (!logRefreshInterval) {
    logRefreshInterval = setInterval(() => {
      const dropdown = document.getElementById('log-filter');
      const filterVal = dropdown && dropdown.value === 'custom'
        ? (document.getElementById('log-search')?.value || "")
        : (dropdown?.value || "");
      loadLogLines(currentLogType, filterVal);
    }, 10000);
  }
}
function bindLogEvents() {
  document.querySelectorAll('.log-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.log-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      currentLogType = tab.dataset.log;
      const lf = document.getElementById('log-filter'); if (lf) lf.value = '';
      const ls = document.getElementById('log-search'); if (ls) { ls.value = ''; ls.style.display = 'none'; }
      loadLogLines(currentLogType);
    });
  });
  const lf = document.getElementById('log-filter');
  if (lf) lf.addEventListener('change', (e) => {
    const val = e.target.value;
    const searchBox = document.getElementById('log-search');
    if (val === 'custom') {
      if (searchBox) { searchBox.style.display = ''; searchBox.focus(); }
      filterLogLines(searchBox ? searchBox.value : "");
    } else {
      if (searchBox) searchBox.style.display = 'none';
      filterLogLines(val);
    }
  });
  const ls = document.getElementById('log-search');
  if (ls) ls.addEventListener('input', (e) => filterLogLines(e.target.value));
  const dl = document.getElementById('log-download');
  if (dl) dl.addEventListener('click', () => window.open(`/api/log/${currentLogType}/download`, '_blank'));
  const clr = document.getElementById('log-clear');
  if (clr) clr.addEventListener('click', async () => {
    try {
      const resp = await fetch(`/api/log/${currentLogType}/clear`, { method: 'POST' });
      if (resp.ok) showNotify("Log cleared.", "success");
      else showNotify("Failed to clear log.", "error");
      loadLogLines(currentLogType);
    } catch { showNotify("Failed to clear log.", "error"); }
  });
  const rf = document.getElementById('log-refresh');
  if (rf) rf.addEventListener('click', () => {
    const dropdown = document.getElementById('log-filter');
    const filterVal = dropdown && dropdown.value === 'custom'
      ? (document.getElementById('log-search')?.value || "")
      : (dropdown?.value || "");
    loadLogLines(currentLogType, filterVal);
  });
}
function logLevelClass(line) {
  if (line.includes('CRITICAL')) return 'log-level-CRITICAL';
  if (line.includes('ERROR')) return 'log-level-ERROR';
  if (line.includes('WARNING')) return 'log-level-WARNING';
  if (line.includes('INFO')) return 'log-level-INFO';
  if (line.includes('DEBUG')) return 'log-level-DEBUG';
  return '';
}
function filterLogLines(filterVal = "") {
  let lines = logLinesCache || [];
  if (filterVal && filterVal !== "") {
    const fil = String(filterVal).trim().toUpperCase();
    lines = lines.filter(l => l.toUpperCase().includes(fil));
  }
  const win = document.getElementById('log-window');
  if (!win) return;
  win.innerHTML = lines.map(line => {
    let levelClass = logLevelClass(line);
    return `<span class="log-line ${levelClass}">${line.replace(/[<>&]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))}</span>`;
  }).join('');
  win.scrollTop = win.scrollHeight;
}
function loadLogLines(logType, filterVal = "") {
  fetch(`/api/log/${logType}`)
    .then(resp => resp.json())
    .then(data => { logLinesCache = data.lines || []; filterLogLines(filterVal); })
    .catch(() => showNotify('Failed to load logs','error'));
}

/* ======================= TEAM OWNERSHIP ======================= */
let ownershipData = [];
let verifiedNames = [];
let countrySortAsc = true;

async function loadOwnerships() {
  ensureOwnershipView();
  try {
    const resp = await fetch('/api/ownerships');
    const data = await resp.json();
    ownershipData = data.ownerships || [];
    verifiedNames = data.verified_users || [];
    renderOwnershipTable();
  } catch {
    showNotify("Failed to load ownerships","error");
  }
}
function ensureOwnershipView() {
  const section = document.getElementById('ownership');
  if (!section) return;
  if (!section.innerHTML.trim()) {
    section.innerHTML = `
      <div class="card ownership-card">
        <div class="ownership-header">
          <span class="ownership-title">Team Ownership</span>
          <div class="ownership-actions">
            <button id="sort-abc" class="btn btn-restart">Sort A→Z</button>
            <button id="sort-cba" class="btn btn-restart">Sort Z→A</button>
            <input type="text" id="player-filter" placeholder="Filter player(s)">
            <button id="add-ownership" class="btn btn-restart">Add Ownership</button>
          </div>
        </div>
        <div class="ownership-table-scroll">
          <table class="ownership-table" id="ownership-table">
            <thead><tr><th>Country</th><th>Owner(s)</th><th>Actions</th></tr></thead>
            <tbody></tbody>
          </table>
        </div>
      </div>
      <div id="ownership-modal" class="ownership-modal" style="display:none;"></div>
    `;
    document.getElementById('sort-abc').addEventListener('click', () => { countrySortAsc = true; renderOwnershipTable(); });
    document.getElementById('sort-cba').addEventListener('click', () => { countrySortAsc = false; renderOwnershipTable(); });
    document.getElementById('player-filter').addEventListener('input', () => renderOwnershipTable());
    document.getElementById('add-ownership').addEventListener('click', () => showOwnershipModal('add'));
  }
}
function renderOwnershipTable() {
  const tbody = document.querySelector("#ownership-table tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  const filter = (document.getElementById('player-filter')?.value || "").trim().toLowerCase();
  let rows = ownershipData.filter(row => {
    if (!filter) return true;
    return row.owners.some(o => o.toLowerCase().includes(filter));
  });

  rows = rows.sort((a, b) =>
    countrySortAsc ? a.country.localeCompare(b.country) : b.country.localeCompare(a.country)
  );

  for (let row of rows) {
    const tr = document.createElement("tr");
    const hasOwner = row.owners.length > 0;
    const allVerified = row.owners.every(o => verifiedNames.includes(o));
    const isUnassigned = !hasOwner || !allVerified;

    const tdCountry = document.createElement("td");
    tdCountry.textContent = row.country + " ";
    if (isUnassigned) {
      tdCountry.innerHTML += `<span class="unassigned-icon" title="No owner assigned">⚠️</span>`;
      tr.classList.add("row-unassigned");
    }
    tr.appendChild(tdCountry);

    const tdOwners = document.createElement("td");
    tdOwners.className = "owners";
    tdOwners.textContent = row.owners.join(", ");
    tr.appendChild(tdOwners);

    const tdActions = document.createElement("td");
    tdActions.innerHTML =
      `<button class="btn btn-reassign" data-country="${row.country}">Reassign</button>
       <button class="btn btn-split" data-country="${row.country}">Split</button>
       <button class="btn btn-remove" data-country="${row.country}">Remove</button>`;
    tr.appendChild(tdActions);

    tbody.appendChild(tr);
  }

  setTimeout(() => {
    document.querySelectorAll('.btn-reassign').forEach(btn =>
      btn.onclick = () => showOwnershipModal('reassign', btn.dataset.country));
    document.querySelectorAll('.btn-split').forEach(btn =>
      btn.onclick = () => showOwnershipModal('split', btn.dataset.country));
    document.querySelectorAll('.btn-remove').forEach(btn =>
      btn.onclick = () => showOwnershipModal('remove', btn.dataset.country));
  }, 0);
}
function showOwnershipModal(action, country = null) {
  const modal = document.getElementById('ownership-modal');
  if (!modal) return;
  let html = '';
  let currentOwners = [];
  if (country) {
    const row = ownershipData.find(r => r.country === country);
    if (row) currentOwners = row.owners.filter(o => verifiedNames.includes(o));
  }
  function optionsHTML(selected) {
    return verifiedNames.map(name =>
      `<option value="${name}"${selected.includes(name) ? ' selected' : ''}>${name}</option>`
    ).join('');
  }
  if (action === 'add') {
    html = `
      <div class="ownership-modal-content">
        <h3>Add Ownership</h3>
        <label>Country</label>
        <input type="text" id="modal-country" placeholder="Country">
        <label>Owner(s)</label>
        <select id="modal-owners" multiple>${optionsHTML([])}</select>
        <div class="modal-btn-row">
          <button class="modal-save">Add</button>
          <button class="modal-cancel">Cancel</button>
        </div>
      </div>
    `;
  }
  if (action === 'reassign' || action === 'split') {
    html = `
      <div class="ownership-modal-content">
        <h3>${action === 'reassign' ? "Reassign" : "Add Co-Owners"} for ${country}</h3>
        <label>${action === 'reassign' ? "New Owner(s)" : "Co-Owners to Add"}</label>
        <select id="modal-owners" multiple>${optionsHTML(action === 'reassign' ? currentOwners : [])}</select>
        <div class="modal-btn-row">
          <button class="modal-save">Save</button>
          <button class="modal-cancel">Cancel</button>
        </div>
      </div>
    `;
  }
  if (action === 'remove') {
    html = `
      <div class="ownership-modal-content">
        <h3>Remove Ownership for ${country}</h3>
        <p>Are you sure you want to remove all owners for <b>${country}</b>?</p>
        <div class="modal-btn-row">
          <button class="modal-save modal-cancel">Yes, Remove</button>
          <button class="modal-cancel">Cancel</button>
        </div>
      </div>
    `;
  }
  modal.innerHTML = html;
  modal.style.display = "flex";
  modal.querySelectorAll('.modal-cancel').forEach(btn =>
    btn.onclick = () => { modal.style.display = "none"; });

  if (modal.querySelector('.modal-save')) {
    modal.querySelector('.modal-save').onclick = async () => {
      if (action === 'add') {
        const ctry = modal.querySelector('#modal-country').value.trim();
        const owners = Array.from(modal.querySelector('#modal-owners').selectedOptions).map(o => o.value);
        if (!ctry || owners.length === 0) { showNotify("Country and at least one owner required.", "error"); return; }
        await saveOwnership(ctry, owners, "reassign");
      }
      if (action === 'reassign') {
        const owners = Array.from(modal.querySelector('#modal-owners').selectedOptions).map(o => o.value);
        if (!owners.length) { showNotify("At least one owner required.", "error"); return; }
        await saveOwnership(country, owners, "reassign");
      }
      if (action === 'split') {
        const owners = Array.from(modal.querySelector('#modal-owners').selectedOptions).map(o => o.value);
        if (!owners.length) { showNotify("Select at least one co-owner to add.", "error"); return; }
        await saveOwnership(country, owners, "split");
      }
      if (action === 'remove') {
        await saveOwnership(country, [], "reassign");
      }
      modal.style.display = "none";
    };
  }
}
async function saveOwnership(country, owners, actionType = "reassign") {
  try {
    const resp = await fetch('/api/ownership/update', {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({country, owners, action: actionType})
    });
    const data = await resp.json();
    if (data.ok) { showNotify("Ownership updated.", "success"); await loadOwnerships(); }
    else showNotify(data.error || "Failed to update.", "error");
  } catch { showNotify("Failed to update.", "error"); }
}

/* ======================= BETTING PAGE ======================= */
let verifiedMap = {};
let verifiedSet = new Set();

async function loadVerified() {
  const res = await fetch("/api/verified");
  const users = await res.json();
  verifiedMap = {};
  verifiedSet = new Set();
  for (const u of users) {
    verifiedMap[String(u.discord_id)] = u.habbo_name;
    verifiedSet.add(String(u.discord_id));
  }
}
function ensureBetsView() {
  const section = document.getElementById('bets');
  if (!section) return;
  if (!section.innerHTML.trim()) {
    section.innerHTML = `
      <div class="card betting-card">
        <div class="betting-header"><span class="betting-title">Open Bets</span></div>
        <div class="betting-table-scroll">
          <table class="betting-table">
            <thead><tr><th>Bet</th><th>Wager</th><th>Player 1</th><th>Player 2</th><th>Settle</th></tr></thead>
            <tbody id="betting-table-body"></tbody>
          </table>
        </div>
      </div>
      <div id="settle-modal" class="settle-modal" style="display:none;"></div>
    `;
  }
}
async function loadBets() {
  ensureBetsView();
  await loadVerified();
  const res = await fetch("/api/bets");
  const bets = await res.json();
  const tbody = document.getElementById("betting-table-body");
  if (!tbody) return;
  tbody.innerHTML = "";

  for (const bet of bets) {
    const player1Id = String(bet.option1_user_id || "");
    const player2Id = String(bet.option2_user_id || "");

    const player1Verified = verifiedSet.has(player1Id);
    const player2Verified = verifiedSet.has(player2Id);

    const player1Name = player1Verified ? verifiedMap[player1Id] : (bet.option1_user_name || "?");
    const player2Name = player2Verified ? verifiedMap[player2Id] : (bet.option2_user_name || "?");

    const player1 = bet.option1_user_id
      ? `<span>${player1Name}${!player1Verified ? ' <span class="not-verified">(Not Verified)</span>' : ''}</span>`
      : `<span class="unclaimed">Unclaimed</span>`;
    const player2 = bet.option2_user_id
      ? `<span>${player2Name}${!player2Verified ? ' <span class="not-verified">(Not Verified)</span>' : ''}</span>`
      : `<span class="unclaimed">Unclaimed</span>`;

    const bothClaimed = bet.option1_user_id && bet.option2_user_id;
    const disableSettle = bet.settled === true;

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${bet.bet_title || ''}</td>
      <td>${bet.wager || ''}</td>
      <td>${player1}</td>
      <td>${player2}</td>
      <td>
        ${bothClaimed && !disableSettle
          ? `<button class="settle-btn"
                data-bet="${bet.bet_id}"
                data-opt1="${player1Id}"
                data-opt2="${player2Id}"
                data-option1="${bet.option1 || ''}"
                data-option2="${bet.option2 || ''}"
                data-p1name="${player1Name}"
                data-p2name="${player2Name}"
            >Settle</button>`
          : `<button disabled class="settle-btn-dsb">Settle</button>`
        }
      </td>
    `;
    tbody.appendChild(tr);
  }

  // Settle button logic with modal
  tbody.querySelectorAll(".settle-btn").forEach(btn => {
    btn.onclick = () => {
      const betId = btn.dataset.bet;
      const betTitle = btn.closest('tr').children[0].textContent;
      const option1 = btn.dataset.option1 || "";
      const option2 = btn.dataset.option2 || "";
      const player1Id = btn.dataset.opt1;
      const player2Id = btn.dataset.opt2;
      const player1Name = btn.dataset.p1name || "Unknown";
      const player2Name = btn.dataset.p2name || "Unknown";
      showSettleModal(
        betId, betTitle,
        option1, option2,
        player1Name, player2Name,
        player1Id, player2Id
      );
    };
  });
}
function setupBetsRefreshButton() {
  const header = document.querySelector('.betting-header');
  if (!header) return;
  if (!document.getElementById('bets-refresh-btn')) {
    const btn = document.createElement('button');
    btn.id = 'bets-refresh-btn';
    btn.textContent = '⟳';
    btn.className = 'btn btn-restart';
    btn.style.marginLeft = '1.2em';
    btn.onclick = () => { loadBets(); showNotify("Bets refreshed!", "success"); };
    header.appendChild(btn);
  }
}
function showSettleModal(
  betId, betTitle, option1, option2,
  player1Name, player2Name, player1Id, player2Id
) {
  const modal = document.getElementById('settle-modal');
  if (!modal) return;
  modal.innerHTML = `
    <div class="settle-modal-content">
      <button class="settle-modal-close" title="Close">&times;</button>
      <h3>${betTitle}</h3>
      <div class="settle-modal-btn-row" style="gap:3.5em;">
        <div>
          <div style="margin-bottom:0.6em; font-weight:700; text-align:center;">${option1}</div>
          <button class="settle-btn-choice" data-winner="${player1Id}">${player1Name}</button>
        </div>
        <div>
          <div style="margin-bottom:0.6em; font-weight:700; text-align:center;">${option2}</div>
          <button class="settle-btn-choice" data-winner="${player2Id}">${player2Name}</button>
        </div>
      </div>
    </div>
  `;
  modal.style.display = "flex";
  modal.querySelector('.settle-modal-close').onclick = () => { modal.style.display = "none"; };
  modal.onclick = e => { if (e.target === modal) modal.style.display = "none"; };
  modal.querySelectorAll('.settle-btn-choice').forEach(btn => {
    btn.onclick = async () => {
      const winnerId = btn.dataset.winner;
      const resp = await fetch("/api/bets/settle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bet_id: betId, winner_id: winnerId })
      });
      const data = await resp.json();
      if (data.ok) showNotify("Settle command sent to Discord!", "success");
      else showNotify(data.error || "Failed to send settle.", "error");
      modal.style.display = "none";
      loadBets();
    };
  });
}

/* ======================= SPLIT REQUESTS ======================= */
function ensureSplitsView() {
  const section = document.getElementById('splits');
  if (!section) return;
  if (!section.innerHTML.trim()) {
    section.innerHTML = `
      <div class="card split-requests-card">
        <div class="split-requests-header"><span class="split-requests-title">Split Ownership Requests</span></div>
        <div class="split-requests-table-scroll">
          <table class="split-requests-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Team</th>
                <th>Main Owner</th>
                <th>Requester</th>
                <th>Ownership %</th>
                <th>Timestamp</th>
                <th></th>
              </tr>
            </thead>
            <tbody id="split-requests-table-body"></tbody>
          </table>
        </div>
      </div>
      <div id="split-modal" class="split-modal" style="display:none;"></div>
    `;
  }
}
async function loadSplitRequests() {
  ensureSplitsView();
  try {
    const res = await fetch("/api/split_requests");
    const data = await res.json();
    const tbody = document.getElementById("split-requests-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    function row(req, pending) {
      const statusColor = req.status === "pending"
        ? "#f7c942"
        : req.status === "accepted"
        ? "#27c46a"
        : req.status === "declined"
        ? "#e6505c"
        : "#888";
      const dotBtn = pending ? `<button class="split-dotmenu-btn" data-id="${req.request_id}" title="Actions">⋮</button>` : "";
      return `<tr>
        <td><span style="color:${statusColor};font-weight:800">${(req.status || '').toUpperCase()}</span></td>
        <td>${req.team || ''}</td>
        <td>${req.main_owner_name || ''}</td>
        <td>${req.requester_name || ''}</td>
        <td>${req.ownership_percentage || 0}%</td>
        <td>${req.timestamp ? new Date(req.timestamp*1000).toLocaleString() : ""}</td>
        <td style="position:relative;">${dotBtn}</td>
      </tr>`;
    }

    for (const req of (data.pending || [])) tbody.innerHTML += row(req, true);
    for (const req of (data.resolved || [])) tbody.innerHTML += row(req, false);

    document.querySelectorAll(".split-dotmenu-btn").forEach(btn => {
      btn.onclick = function(e) {
        document.querySelectorAll('.split-dotmenu').forEach(el => el.remove());
        const rect = btn.getBoundingClientRect();
        const menu = document.createElement("div");
        menu.className = "split-dotmenu";
        menu.style.position = "fixed";
        menu.style.top = (rect.bottom + 2) + "px";
        menu.style.left = (rect.left - 10) + "px";
        menu.innerHTML = `
          <button class="split-dotmenu-action" data-act="forceaccept">Force Accept</button>
          <button class="split-dotmenu-action" data-act="forcedecline">Force Decline</button>
          <button class="split-dotmenu-action" data-act="delete">Delete</button>
        `;
        document.body.appendChild(menu);
        menu.querySelectorAll('.split-dotmenu-action').forEach(actionBtn => {
          actionBtn.onclick = () => { menu.remove(); showSplitModal(btn.dataset.id, actionBtn.dataset.act); };
        });
        setTimeout(() => {
          window.addEventListener("click", function clickAway(ev) {
            if (!menu.contains(ev.target) && ev.target !== btn) {
              menu.remove();
              window.removeEventListener("click", clickAway);
            }
          });
        }, 30);
        e.stopPropagation();
      };
    });
  } catch {
    showNotify("Failed to load split requests","error");
  }
}
function showSplitModal(requestId, action) {
  const modal = document.getElementById('split-modal');
  if (!modal) return;
  modal.innerHTML = `
    <div class="split-modal-content">
      <h3>Confirm Action</h3>
      <p>Are you sure you want to <b>${(action || '').replace("force","").toUpperCase()}</b> this split request?</p>
      <div class="split-modal-btn-row">
        <button id="split-modal-confirm">Yes</button>
        <button id="split-modal-cancel">Cancel</button>
      </div>
    </div>
  `;
  modal.style.display = "flex";
  document.getElementById('split-modal-cancel').onclick = () => { modal.style.display = "none"; };
  document.getElementById('split-modal-confirm').onclick = async () => {
    try {
      const resp = await fetch("/api/split_requests/force", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ request_id: requestId, action })
      });
      const result = await resp.json();
      if (result.ok) showNotify(result.msg || "Success!", "success");
      else showNotify(result.error || "Failed.", "error");
      modal.style.display = "none";
      loadSplitRequests();
    } catch {
      showNotify("Failed (network error)", "error");
      modal.style.display = "none";
    }
  };
  modal.onclick = (e) => { if (e.target === modal) modal.style.display = "none"; };
}

/* ======================= BACKUPS (two-pane) ======================= */
let backupsState = { folders: [], selectedIndex: 0 };
function ensureBackupsView() {
  const section = document.getElementById('backups');
  if (!section) return;
  if (!section.innerHTML.trim()) {
    section.innerHTML = `
      <div class="card backups-card">
        <div class="backups-header"><span class="backups-title">Backups</span></div>
        <div class="backups-body">
          <div class="backups-layout">
            <div class="backups-left" id="backups-left"></div>
            <div class="backups-right">
              <div class="right-head">
                <div class="right-title" id="right-title"></div>
                <div class="right-subtle" id="right-count"></div>
              </div>
              <div class="right-list" id="right-list"></div>
            </div>
          </div>
        </div>
      </div>
    `;
  }
}
function initBackupsView() {
  ensureBackupsView();
  loadBackups();
}
function humanBytes(b) {
  let x = Number(b) || 0;
  if (x < 1024) return x + ' B';
  const u = ['KB','MB','GB','TB'];
  let i = -1; do { x = x / 1024; i++; } while (x >= 1024 && i < u.length - 1);
  return x.toFixed(x >= 10 ? 0 : 1) + ' ' + u[i];
}
function fmtTime(epoch) {
  return epoch ? new Date(epoch * 1000).toLocaleString() : '';
}
function renderBackups() {
  const section = document.getElementById('backups');
  if (!section) return;
  const left = section.querySelector('#backups-left');
  const title = section.querySelector('#right-title');
  const count = section.querySelector('#right-count');
  const list = section.querySelector('#right-list');

  left.innerHTML = '';
  backupsState.folders.forEach((f, idx) => {
    const item = document.createElement('div');
    item.className = 'folder-item' + (idx === backupsState.selectedIndex ? ' active' : '');
    item.innerHTML = `<div class="folder-name">${f.display}</div><div class="folder-count">${f.count}</div>`;
    item.addEventListener('click', () => { backupsState.selectedIndex = idx; renderBackups(); });
    left.appendChild(item);
  });

  const folder = backupsState.folders[backupsState.selectedIndex] || { display: '—', files: [], count: 0 };
  title.textContent = folder.display;
  count.textContent = `${folder.count} backup${folder.count === 1 ? '' : 's'}`;

  if (!folder.files || folder.files.length === 0) {
    list.innerHTML = `<div class="right-empty">No backups yet.</div>`;
  } else {
    list.innerHTML = folder.files.map(file => `
      <div class="file-row">
        <div class="file-meta">${file.name} • ${humanBytes(file.bytes)} • ${fmtTime(file.mtime)}</div>
        <a class="file-download" href="/api/backups/download?rel=${encodeURIComponent(file.rel)}">Download</a>
      </div>
    `).join('');
  }
}
async function loadBackups() {
  try {
    const res = await fetch('/api/backups');
    const data = await res.json();
    backupsState.folders = (data.folders || []);
    const idx = backupsState.folders.findIndex(f => (f.files || []).length > 0);
    backupsState.selectedIndex = idx >= 0 ? idx : 0;
    renderBackups();
  } catch {
    const section = document.getElementById('backups');
    if (section) section.innerHTML = `<div class="card backups-card">
      <div class="backups-header"><span class="backups-title">Backups</span></div>
      <div class="backups-body" style="padding:1em;">Failed to load backups.</div>
    </div>`;
  }
}

/* ======================= END ======================= */


// ===================== Admin FAB + Modal =====================
(function initAdminFab(){
  function safeInit(){
    try{
      const qs = s => document.querySelector(s);
      const qsa = s => Array.from(document.querySelectorAll(s));
      const modal = qs('#adminModal');
      const fab = qs('#adminFab');
      const pop = qs('#adminLoginPopover');
      if(!fab || !modal || !pop) return;

      const closeBtn = qs('#adminModalClose');
      const actions = qs('#adminActions');
      const fabPass = qs('#adminFabPassword');
      const fabLogin = qs('#adminFabLogin');
      const fabCancel = qs('#adminFabCancel');
      const fabError = qs('#adminFabError');

      const LS_KEY = 'wc_admin_enabled';

      function setAdminMode(enabled){
        document.body.classList.toggle('admin-mode', !!enabled);
        localStorage.setItem(LS_KEY, enabled ? '1' : '0');
      }

      async function serverAdminLogin(password){
        const res = await fetch('/admin/auth/login', {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          credentials: 'same-origin',
          body: JSON.stringify({ password })
        });
        if(!res.ok){
          let j = {}; try { j = await res.json(); } catch(e){}
          throw new Error((j && j.error) || 'Invalid password');
        }
        return true;
      }

      function openModal(){
        modal.classList.add('show');
        modal.setAttribute('aria-hidden','false');
      }
      function closeModal(){
        modal.classList.remove('show');
        modal.setAttribute('aria-hidden','true');
      }
      function showPopover(show){
        pop.classList.toggle('show', !!show);
        pop.setAttribute('aria-hidden', show ? 'false' : 'true');
        if(fabError) fabError.style.display = 'none';
        if(show && fabPass){
          fabPass.value='';
          fabPass.focus();
        }
      }

      fab.addEventListener('click', ()=>{
        const unlocked = localStorage.getItem(LS_KEY) === '1';
        if(unlocked){ openModal(); }
        else{ showPopover(true); }
      });

      document.addEventListener('click', (e)=>{
        if(!pop.classList.contains('show')) return;
        const within = pop.contains(e.target) || fab.contains(e.target);
        if(!within) showPopover(false);
      });

      fabCancel && fabCancel.addEventListener('click', ()=> showPopover(false));

      fabLogin && fabLogin.addEventListener('click', async ()=>{
        const pw = (fabPass && fabPass.value || '').trim();
        if(!pw){ if(fabError){ fabError.textContent = 'Please enter a password.'; fabError.style.display='block'; } return; }
        if(fabError) fabError.style.display='none';
        try{
          await serverAdminLogin(pw);
          setAdminMode(true);
          showPopover(false);
          openModal();
        }catch(err){
          if(fabError){ fabError.textContent = err.message || 'Login failed'; fabError.style.display='block'; }
        }
      });

      // Restore state
      if(localStorage.getItem(LS_KEY) === '1'){
        document.body.classList.add('admin-mode');
      }
    }catch(err){
      console.error('Admin FAB init error:', err);
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', safeInit);
  } else {
    safeInit();
  }
  window.addEventListener('pageshow', safeInit);
})();
