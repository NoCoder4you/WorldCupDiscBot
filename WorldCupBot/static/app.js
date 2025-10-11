
// ======================= SPA NAVIGATION =======================
document.querySelectorAll('.menu li a').forEach(link => {
    link.addEventListener('click', function (e) {
        e.preventDefault();
        document.querySelectorAll('section').forEach(s => s.classList.remove('active-section'));
        let page = this.dataset.page;
        if (page) {
            document.getElementById(page).classList.add('active-section');
        }
        document.querySelectorAll('.menu li a').forEach(a => a.classList.remove('active'));
        this.classList.add('active');
        document.getElementById('menu-toggle').checked = false;

        // lazy load per section
        if (page === 'cogs') loadCogs();
        if (page === 'ownership') loadOwnerships();
        if (page === 'bets') loadBets();
        if (page === 'splits') loadSplitRequests();
        if (page === 'backups') loadBackupsPane();
        if (page === 'log') {
          let filterVal = document.getElementById('log-filter').value;
          if (filterVal === 'custom') filterVal = document.getElementById('log-search').value;
          loadLogLines(currentLogType, filterVal);
        }
    });
});

// ======================= THEME TOGGLE =======================
let darkMode = !document.body.classList.contains('light-theme');
const themeBtn = document.getElementById('theme-toggle');
const themeIcon = document.getElementById('theme-icon');
if (themeBtn && themeIcon) {
  themeBtn.addEventListener('click', () => {
      darkMode = !darkMode;
      document.body.classList.toggle('light-theme', !darkMode);
      themeIcon.textContent = darkMode ? "🌙" : "☀️";
  });
  themeIcon.textContent = darkMode ? "🌙" : "☀️";
}

// ======================= NOTIFY BAR =======================
function showNotify(msg, type = 'success') {
    const notify = document.getElementById('notify-bar');
    if (!notify) { console.log(type, msg); return; }
    notify.innerHTML = "";
    const div = document.createElement('div');
    div.className = `notify-${type}`;
    div.textContent = msg;
    notify.appendChild(div);
    setTimeout(() => { if (notify.contains(div)) notify.removeChild(div); }, 2300);
}

// ======================= DASHBOARD LOGIC =======================
function setGauge(barId, textId, percent, textValue) {
    const arcLen = 125.66;
    let value = Math.max(0, Math.min(100, percent));
    let len = (arcLen * value) / 100;
    const bar = document.getElementById(barId);
    const text = document.getElementById(textId);
    if (bar) bar.setAttribute("stroke-dasharray", `${len},${arcLen - len}`);
    if (text) text.textContent = textValue;
}
function formatBytesMB(valMb) {
    if (valMb >= 1024*1024) return (valMb / 1024 / 1024).toFixed(2) + " TB";
    if (valMb >= 1024) return (valMb / 1024).toFixed(2) + " GB";
    return Math.round(valMb) + " MB";
}

async function fetchDashboard() {
    try {
        // 1. Ping
        let pingStart = Date.now();
        let pingResp = await fetch('/api/ping');
        let pingData = await pingResp.json();
        let pingMs = Date.now() - pingStart;
        const pv = document.getElementById('ping-value');
        if (pv) {
          pv.innerHTML = pingData.bot_running
              ? `${pingMs} ms`
              : `${pingMs} ms<br><span class='bot-down'>(Bot Down)</span>`;
        }

        const bStart = document.getElementById('start-bot');
        const bStop = document.getElementById('stop-bot');
        const bRestart = document.getElementById('restart-bot');
        if (bStart && bStop && bRestart) {
          bRestart.style.display = pingData.bot_running ? "" : "none";
          bStop.style.display = pingData.bot_running ? "" : "none";
          bStart.style.display = pingData.bot_running ? "none" : "";
        }

        // 2. Uptime
        let uptimeResp = await fetch('/api/uptime');
        let uptimeData = await uptimeResp.json();
        const ul = document.getElementById('uptime-label');
        const uv = document.getElementById('uptime-value');
        if (ul) ul.textContent = uptimeData.bot_running ? "Uptime" : "Downtime";
        if (uv) uv.textContent = uptimeData.bot_running ? (uptimeData.uptime_hms || '--:--:--') : (uptimeData.downtime_hms || '--:--:--');

        // 3. Guilds
        let guildsResp = await fetch('/api/guilds');
        let guildsData = await guildsResp.json();
        const gc = document.getElementById('guild-count');
        const gl = document.getElementById('guild-list');
        if (gc) gc.textContent = guildsData.guild_count || guildsData.guilds?.length || '0';
        if (gl) gl.innerHTML = (guildsData.guilds || []).map(g => g.name || g).join('<br>');

        // 4. Bot Process & 5. System Usage
        let sysResp = await fetch('/api/system');
        let sysData = await sysResp.json();
        let b = sysData.bot || {}, s = sysData.system || {};
        const bs = document.getElementById('botstats-value');
        if (bs) bs.innerHTML = (b.mem_mb != null)
            ? `PID ${pingData.pid || '-'}<br>${(b.mem_mb||0).toFixed(1)} MB<br>${(b.cpu_percent||0).toFixed(1)}% CPU`
            : "Not running";

        // Memory
        let memPercent = Math.round(s.mem_percent || 0);
        let memLabel = formatBytesMB(s.mem_used_mb || 0) + " / " + formatBytesMB(s.mem_total_mb || 0);
        const me = document.getElementById("mem-extra");
        if (me) me.textContent = memLabel;
        setGauge("mem-bar", "mem-text", memPercent, memPercent + "%");

        // CPU
        let cpuPercent = Math.round(s.cpu_percent || 0);
        setGauge("cpu-bar", "cpu-text", cpuPercent, cpuPercent + "%");
        const ce = document.getElementById("cpu-extra");
        if (ce) ce.textContent = `${cpuPercent}%`;

        // Disk (optional if provided)
        if ('disk_total_mb' in s) {
            let diskUsed = s.disk_used_mb || 0;
            let diskTotal = s.disk_total_mb || 1;
            let diskPercent = diskTotal ? Math.round((diskUsed / diskTotal) * 100) : 0;
            const de = document.getElementById("disk-extra");
            if (de) de.textContent = `${formatBytesMB(diskUsed)} / ${formatBytesMB(diskTotal)}`;
            setGauge("disk-bar", "disk-text", diskPercent, diskPercent + "%");
        }
    } catch (err) {
        const pv = document.getElementById('ping-value'); if (pv) pv.innerText = "Error";
        const uv = document.getElementById('uptime-value'); if (uv) uv.innerText = "Error";
    }
}

const btnRestart = document.getElementById('restart-bot');
if (btnRestart) btnRestart.addEventListener('click', async () => {
    btnRestart.disabled = true; btnRestart.innerText = "Restarting...";
    try { await fetch('/api/bot/restart', { method: 'POST' }); showNotify("Bot restarted!", "success"); }
    catch { showNotify("Failed to restart bot.", "error"); }
    finally { setTimeout(() => { btnRestart.disabled = false; btnRestart.innerText = "Restart Bot"; fetchDashboard(); }, 1200); }
});

const btnStop = document.getElementById('stop-bot');
if (btnStop) btnStop.addEventListener('click', async () => {
    btnStop.disabled = True; btnStop.innerText = "Stopping...";
    try { await fetch('/api/bot/stop', { method: 'POST' }); showNotify("Bot stopped!", "success"); }
    catch { showNotify("Failed to stop bot.", "error"); }
    finally { btnStop.disabled = false; btnStop.innerText = "Stop Bot"; fetchDashboard(); }
});

const btnStart = document.getElementById('start-bot');
if (btnStart) btnStart.addEventListener('click', async () => {
    btnStart.disabled = true; btnStart.innerText = "Starting...";
    try { await fetch('/api/bot/start', { method: 'POST' }); showNotify("Bot started!", "success"); }
    catch { showNotify("Failed to start bot.", "error"); }
    finally { setTimeout(() => { btnStart.disabled = false; btnStart.innerText = "Start Bot"; fetchDashboard(); }, 1200); }
});

fetchDashboard();
setInterval(fetchDashboard, 6000);

// ======================= COGS PAGE =======================
async function loadCogs() {
    const resp = await fetch('/api/cogs');
    const data = await resp.json();
    const cogs = data.cogs || [];
    const tbody = document.querySelector("#cogs-table tbody");
    if (!tbody) return;
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
                try {
                  const resp = await fetch('/api/cogs/action', {
                      method: "POST",
                      headers: {"Content-Type": "application/json"},
                      body: JSON.stringify({cog, action})
                  });
                  if (!resp.ok) throw new Error();
                  showNotify(`Sent ${action} for ${cog}`, "success");
                } catch {
                  showNotify(`Failed ${action} for ${cog}`, "error");
                } finally {
                  btn.disabled = false;
                }
            });
    }, 0);
}
document.querySelector('[data-page="cogs"]')?.addEventListener('click', loadCogs);

// ======================= LOG PAGE LOGIC =======================
let currentLogType = 'bot';
let logLinesCache = [];
let logRefreshInterval = null;

function logLevelClass(line) {
    if (line.includes('ERROR')) return 'log-level-ERROR';
    if (line.includes('CRITICAL')) return 'log-level-CRITICAL';
    if (line.includes('WARNING')) return 'log-level-WARNING';
    if (line.includes('INFO')) return 'log-level-INFO';
    if (line.includes('DEBUG')) return 'log-level-DEBUG';
    return '';
}
function filterLogLines(filterVal) {
    let lines = logLinesCache;
    if (filterVal && filterVal !== "") {
        const fil = filterVal.trim().toUpperCase();
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
    fetch(`/api/log/${logType}`).then(resp => resp.json()).then(data => {
        let lines = data.lines || [];
        logLinesCache = lines;
        filterLogLines(filterVal);
    });
}
document.querySelectorAll('.log-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.log-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        currentLogType = tab.dataset.log;
        document.getElementById('log-filter').value = "";
        document.getElementById('log-search').value = "";
        document.getElementById('log-search').style.display = 'none';
        loadLogLines(currentLogType);
    });
});
document.getElementById('log-filter')?.addEventListener('change', (e) => {
    const val = e.target.value;
    const searchBox = document.getElementById('log-search');
    if (val === 'custom') {
        searchBox.style.display = '';
        searchBox.focus();
        filterLogLines(searchBox.value);
    } else {
        searchBox.style.display = 'none';
        filterLogLines(val);
    }
});
document.getElementById('log-search')?.addEventListener('input', (e) => {
    filterLogLines(e.target.value);
});
document.getElementById('log-download')?.addEventListener('click', () => {
    window.open(`/api/log/${currentLogType}/download`, '_blank');
});
document.getElementById('log-clear')?.addEventListener('click', async () => {
    try {
        const resp = await fetch(`/api/log/${currentLogType}/clear`, { method: 'POST' });
        if (resp.ok) showNotify("Log cleared.", "success");
        else showNotify("Failed to clear log.", "error");
        loadLogLines(currentLogType);
    } catch {
        showNotify("Failed to clear log.", "error");
    }
});
document.getElementById('log-refresh')?.addEventListener('click', () => {
    let filterVal = "";
    const dropdown = document.getElementById('log-filter');
    if (dropdown.value === 'custom') filterVal = document.getElementById('log-search').value;
    else filterVal = dropdown.value;
    loadLogLines(currentLogType, filterVal);
});
document.querySelector('[data-page="log"]')?.addEventListener('click', () => {
    let filterVal = "";
    const dropdown = document.getElementById('log-filter');
    if (dropdown.value === 'custom') filterVal = document.getElementById('log-search').value;
    else filterVal = dropdown.value;
    loadLogLines(currentLogType, filterVal);
    if (!logRefreshInterval) {
        logRefreshInterval = setInterval(() => {
            let fval = "";
            const dropdown = document.getElementById('log-filter');
            if (dropdown.value === 'custom') fval = document.getElementById('log-search').value;
            else fval = dropdown.value;
            loadLogLines(currentLogType, fval);
        }, 10000);
    }
});

// ======================= TEAM OWNERSHIP (compat) =======================
let ownershipData = [];
let verifiedNames = [];
let countrySortAsc = true;

async function loadOwnerships() {
    const resp = await fetch('/api/ownerships');
    const data = await resp.json();
    ownershipData = data.ownerships || [];
    verifiedNames = (data.verified_users || []).map(u => u.habbo_name || u); // compatible
    renderOwnershipTable();
}

function renderOwnershipTable() {
    let tbody = document.querySelector("#ownership-table tbody");
    if (!tbody) return;
    tbody.innerHTML = "";

    const filter = (document.getElementById('player-filter')?.value || '').trim().toLowerCase();
    let rows = ownershipData.filter(row => {
        if (!filter) return True;
        return (row.owners || []).some(o => (o||'').toLowerCase().includes(filter));
    });

    rows = rows.sort((a, b) =>
        countrySortAsc ? a.country.localeCompare(b.country) : b.country.localeCompare(a.country)
    );

    for (let row of rows) {
        const tr = document.createElement("tr");
        const hasOwner = (row.owners || []).length > 0;
        const allVerified = (row.owners || []).every(o => verifiedNames.includes(o));
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
        tdOwners.textContent = (row.owners || []).join(", ");
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

document.getElementById('sort-abc')?.addEventListener('click', () => { countrySortAsc = true; renderOwnershipTable(); });
document.getElementById('sort-cba')?.addEventListener('click', () => { countrySortAsc = false; renderOwnershipTable(); });
document.getElementById('player-filter')?.addEventListener('input', () => renderOwnershipTable());
document.getElementById('add-ownership')?.addEventListener('click', () => { showOwnershipModal('add'); });

function showOwnershipModal(action, country = null) {
    const modal = document.getElementById('ownership-modal');
    if (!modal) return;
    let html = '';
    let currentOwners = [];
    if (country) {
        const row = ownershipData.find(r => r.country === country);
        if (row) currentOwners = row.owners || [];
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
            </div>`;
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
            </div>`;
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
            </div>`;
    }
    modal.innerHTML = html;
    modal.style.display = "flex";
    modal.querySelectorAll('.modal-cancel').forEach(btn => btn.onclick = () => { modal.style.display = "none"; });

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
    } catch {
        showNotify("Failed to update.", "error");
    }
}

document.querySelector('[data-page="ownership"]')?.addEventListener('click', () => { loadOwnerships(); });

// =============== BETTING PAGE LOGIC ===============
let verifiedMap = {};
let verifiedSet = new Set();

async function loadVerified() {
    const res = await fetch("/api/verified");
    const users = await res.json();
    verifiedMap = {}; verifiedSet = new Set();
    for (const u of users) {
        const id = String(u.discord_id || u.id || "");
        const name = u.habbo_name || u.name || "";
        if (!id) continue;
        verifiedMap[id] = name; verifiedSet.add(id);
    }
}

async function loadBets() {
    await loadVerified();
    const res = await fetch("/api/bets");
    const data = await res.json();
    const bets = Array.isArray(data) ? data : (data.bets || []);
    const tbody = document.getElementById("betting-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    for (const bet of bets) {
        const player1Id = String(bet.option1_user_id || "");
        const player2Id = String(bet.option2_user_id || "");
        const player1Name = verifiedMap[player1Id] || (bet.option1_user_name || "?");
        const player2Name = verifiedMap[player2Id] || (bet.option2_user_name || "?");

        const player1 = bet.option1_user_id ? `<span>${player1Name}${verifiedSet.has(player1Id) ? "" : ' <span class="not-verified">(Not Verified)</span>'}</span>` : `<span class="unclaimed">Unclaimed</span>`;
        const player2 = bet.option2_user_id ? `<span>${player2Name}${verifiedSet.has(player2Id) ? "" : ' <span class="not-verified">(Not Verified)</span>'}</span>` : `<span class="unclaimed">Unclaimed</span>`;

        const bothClaimed = bet.option1_user_id && bet.option2_user_id;
        const disableSettle = bet.settled === True;

        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${bet.bet_title || ''}</td>
            <td>${bet.wager || ''}</td>
            <td>${player1}</td>
            <td>${player2}</td>
            <td>
                ${bothClaimed && !disableSettle
                    ? `<button class="settle-btn" data-bet="${bet.bet_id}" data-opt1="${player1Id}" data-opt2="${player2Id}" data-option1="${bet.option1 || ''}" data-option2="${bet.option2 || ''}" data-p1name="${player1Name}" data-p2name="${player2Name}">Settle</button>`
                    : `<button disabled class="settle-btn-dsb">Settle</button>`}
            </td>`;
        tbody.appendChild(tr);
    }

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
            showSettleModal(betId, betTitle, option1, option2, player1Name, player2Name, player1Id, player2Id);
        };
    });
}

// === Add a refresh button for the bets table ===
function setupBetsRefreshButton() {
    let betsHeader = document.querySelector('.betting-header');
    if (betsHeader && !document.getElementById('bets-refresh-btn')) {
        let btn = document.createElement('button');
        btn.id = 'bets-refresh-btn';
        btn.textContent = '⟳';
        btn.className = 'btn btn-restart';
        btn.style.marginLeft = '1.2em';
        btn.onclick = () => { loadBets(); showNotify("Bets refreshed!", "success"); };
        betsHeader.appendChild(btn);
    }
}

// === Settle modal logic ===
function showSettleModal(betId, betTitle, option1, option2, player1Name, player2Name, player1Id, player2Id) {
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
        </div>`;
    modal.style.display = "flex";
    modal.querySelector('.settle-modal-close').onclick = () => { modal.style.display = "none"; };
    modal.onclick = e => { if (e.target === modal) modal.style.display = "none"; };
    modal.querySelectorAll('.settle-btn-choice').forEach(btn => {
        btn.onclick = async () => {
            const winnerId = btn.dataset.winner;
            try {
                const resp = await fetch("/api/bets/settle", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ bet_id: betId, winner_id: winnerId })
                });
                const data = await resp.json();
                if (data.ok) showNotify("Settle command sent to Discord!", "success");
                else showNotify(data.error || "Failed to send settle.", "error");
            } catch {
                showNotify("Failed to send settle.", "error");
            }
            modal.style.display = "none";
            loadBets();
        };
    });
}

document.querySelector('[data-page="bets"]')?.addEventListener('click', () => {
    setupBetsRefreshButton();
    loadBets();
});

// =============== SPLIT REQUESTS PAGE LOGIC ===============
async function loadSplitRequests() {
    const res = await fetch("/api/split_requests");
    const data = await res.json();
    const tbody = document.getElementById("split-requests-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    function row(req, pending) {
        const statusColor = req.status === "pending" ? "#f7c942"
                         : req.status === "accepted" ? "#27c46a"
                         : req.status === "declined" ? "#e6505c" : "#888";
        const dotBtn = pending ? `<button class="split-dotmenu-btn" data-id="${req.request_id}" title="Actions">⋮</button>` : "";
        return `<tr>
            <td><span style="color:${statusColor};font-weight:800">${(req.status||'').toUpperCase()}</span></td>
            <td>${req.team||""}</td>
            <td>${req.main_owner_name||""}</td>
            <td>${req.requester_name||""}</td>
            <td>${req.ownership_percentage||0}%</td>
            <td>${req.timestamp ? new Date(req.timestamp*1000).toLocaleString() : ""}</td>
            <td style="position:relative;">${dotBtn}</td>
        </tr>`;
    }

    for (const req of (data.pending||[])) tbody.innerHTML += row(req, true);
    for (const req of (data.resolved||[])) tbody.innerHTML += row(req, false);

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
                <button class="split-dotmenu-action" data-act="delete">Delete</button>`;
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
}

function showSplitModal(requestId, action) {
    const modal = document.getElementById('split-modal');
    if (!modal) return;
    modal.innerHTML = `
        <div class="split-modal-content">
            <h3>Confirm Action</h3>
            <p>Are you sure you want to <b>${action.replace("force","").toUpperCase()}</b> this split request?</p>
            <div class="split-modal-btn-row">
                <button id="split-modal-confirm">Yes</button>
                <button id="split-modal-cancel">Cancel</button>
            </div>
        </div>`;
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
        } catch (e) {
            showNotify("Failed (network error)", "error");
            modal.style.display = "none";
        }
    };
    modal.onclick = (e) => { if (e.target === modal) modal.style.display = "none"; };
}

document.querySelector('[data-page="splits"]')?.addEventListener('click', () => { loadSplitRequests(); });

// ====== BACKUPS PAGE (two-pane) ======
async function loadBackupsPane() {
  const section = document.getElementById('backups');
  if (!section) return;
  try {
    const res = await fetch('/api/backups');
    const data = await res.json();
    const folders = data.folders || [];
    const left = document.getElementById('backups-left');
    const rightList = document.getElementById('right-list');
    const rightTitle = document.getElementById('right-title');
    const rightCount = document.getElementById('right-count');
    if (!left || !rightList) return;
    left.innerHTML = '';
    folders.forEach((f, idx) => {
      const item = document.createElement('div');
      item.className = 'folder-item' + (idx === 0 ? ' active' : '');
      item.innerHTML = `<div class="folder-name">${f.display}</div><div class="folder-count">${f.count}</div>`;
      item.addEventListener('click', () => {
        left.querySelectorAll('.folder-item').forEach(x => x.classList.remove('active'));
        item.classList.add('active');
        drawRight(f);
      });
      left.appendChild(item);
    });
    function drawRight(folder) {
      rightTitle.textContent = folder.display || "";
      rightCount.textContent = `${folder.count||0} backup${(folder.count||0)===1?'':'s'}`;
      if (!folder.files || folder.files.length === 0) {
        rightList.innerHTML = `<div class="right-empty">No backups yet.</div>`;
      } else {
        rightList.innerHTML = folder.files.map(file => {
          return `<div class="file-row">
            <div class="file-meta">${file.name} • ${(file.bytes/1024).toFixed(1)} KB • ${new Date((file.mtime||0)*1000).toLocaleString()}</div>
            <a class="file-download" href="/api/backups/download?rel=${encodeURIComponent(file.rel)}">Download</a>
          </div>`;
        }).join('');
      }
    }
    if (folders[0]) drawRight(folders[0]);
  } catch {
    // leave silently
  }
}
