/* app.js - logged-out 3-card grid, logged-in dice-5 grid, Bot Actions fixed */
(() => {
  'use strict';

  const qs = (s, el=document) => el.querySelector(s);
  const qsa = (s, el=document) => [...el.querySelectorAll(s)];
  const sleep = (ms)=>new Promise(r=>setTimeout(r,ms));

  const state = {
    admin:false,
    theme: localStorage.getItem('wc:theme') || 'dark',
    currentPage: localStorage.getItem('wc:lastPage') || 'dashboard',
    pollingId: null,
    logsKind: 'bot',
    logsInit: false,
  };

  const $menu = qs('#main-menu');
  const $notify = qs('#notify');
  const $fab = qs('#fab-auth');
  const $fabIcon = qs('#fab-icon');
  const $backdrop = qs('#auth-backdrop');
  const $btnCancel = qs('#auth-cancel');
  const $btnSubmit = qs('#auth-submit');
  const $themeToggle = qs('#theme-toggle');
  const $themeIcon = qs('#theme-icon');

  function notify(msg, ok=true){
    const div = document.createElement('div');
    div.className = `notice ${ok?'ok':'err'}`;
    div.textContent = msg;
    $notify.appendChild(div);
    setTimeout(()=>div.remove(), 2200);
  }

  async function fetchJSON(url, opts={}, {timeoutMs=10000, retries=1}={}){
    const ctrl = new AbortController();
    const to = setTimeout(()=>ctrl.abort(), timeoutMs);
    try{
      const res = await fetch(url, {
        ...opts,
        headers: {'Content-Type':'application/json', ...(opts.headers||{})},
        signal: ctrl.signal,
        credentials: 'include'
      });
      if(!res.ok){
        let msg = `${res.status}`;
        try{ const j = await res.json(); msg = j.error || j.message || JSON.stringify(j); }catch{}
        throw new Error(msg);
      }
      const ct = res.headers.get('content-type')||'';
      return ct.includes('application/json') ? await res.json() : {};
    }catch(e){
      if(retries>0){ await sleep(300); return fetchJSON(url, opts, {timeoutMs, retries:retries-1}); }
      throw e;
    }finally{ clearTimeout(to); }
  }

    async function getJSON(url, opts = {}) {
      const res = await fetch(url, { cache: 'no-store', ...opts });
      if (res.status === 401) {
        // Public side hitting an admin route - fail quietly
        return { __unauthorized: true };
      }
      if (!res.ok) throw new Error(`${url} ${res.status}`);
      return res.json();
    }

    async function postJSON(url, body) {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {})
      });
      if (!res.ok) throw new Error(`${url} ${res.status}`);
      return res.json().catch(() => ({}));
    }


  function setTheme(t){
    state.theme = t;
    document.body.classList.toggle('light', t==='light');
    localStorage.setItem('wc:theme', t);
    $themeIcon.textContent = t==='light' ? '🌞' : '🌙';
  }
  function wireTheme(){ $themeToggle.addEventListener('click', ()=>setTheme(state.theme==='light'?'dark':'light')); }

  function setAdminMode(on){
    state.admin = on;
    document.body.classList.toggle('admin', on);
    $fabIcon.textContent = on ? '⚙️' : '🔑';
    const title = qs('#modal-title');
    const body = qs('#modal-body');
    const btn = $btnSubmit;
    if(on){
      title.textContent = 'Admin';
      body.innerHTML = '<p>You are logged in.</p>';
      btn.textContent = 'Logout'; btn.dataset.action='logout';
    }else{
      title.textContent = 'Admin login';
      body.innerHTML = '<label for="admin-password">Password</label><input type="password" id="admin-password" placeholder="Enter admin password">';
      btn.textContent = 'Unlock'; btn.dataset.action='login';
    }
  }

  function openModal(){ $backdrop.style.display='flex'; if(!state.admin){ const i=qs('#admin-password'); i&&setTimeout(()=>i.focus(),50);} }
  function closeModal(){ $backdrop.style.display='none'; }
  function wireAuth(){
    $fab.addEventListener('click', openModal);
    $btnCancel.addEventListener('click', closeModal);
    document.addEventListener('keydown', e=>{ if(e.key==='Escape' && $backdrop.style.display==='flex') closeModal(); });
    $backdrop.addEventListener('click', e=>{ if(!e.target.closest('.modal')) closeModal(); });
    $btnSubmit.addEventListener('click', async ()=>{
      try{
        if($btnSubmit.dataset.action==='logout'){
          await fetchJSON('/admin/auth/logout',{method:'POST',body:JSON.stringify({})});
          setAdminMode(false); closeModal(); notify('Logged out'); routePage(); return;
        }
        const pw = (qs('#admin-password')||{}).value||'';
        const r = await fetchJSON('/admin/auth/login',{method:'POST',body:JSON.stringify({password:pw})});
        if(r && (r.ok || r.unlocked)){ setAdminMode(true); closeModal(); notify('Admin unlocked'); routePage(); }
        else notify('Login failed', false);
      }catch(e){ notify(`Login error: ${e.message}`, false); }
    });
  }

  function setPage(p) {
      // Resolve target element
    let target = document.getElementById(p);
    if (!target) return;

      // Admin gate: if target is admin-only but user isn't admin, fall back
    if (target.classList.contains('admin-only') && !state.admin) {
      p = 'dashboard';
      target = document.getElementById(p);
      if (!target) return;
    }

      // Persist
    state.currentPage = p;
    localStorage.setItem('wc:lastPage', p);

      // Nav highlight
    qsa('#main-menu a').forEach(a => {
      a.classList.toggle('active', a.dataset.page === p);
    });

      // Clear any legacy inline styles (from earlier patches) once
    qsa('section.page-section').forEach(sec => sec.removeAttribute('style'));

      // Show exactly one section
    qsa('section.page-section').forEach(sec => sec.classList.remove('active-section'));
    target.classList.add('active-section');
  }



  function wireNav(){
    $menu.addEventListener('click', e=>{
      const a = e.target.closest('a[data-page]'); if(!a) return;
      e.preventDefault();
      const p = a.dataset.page;
      const sec = qs(`#${p}`);
      if(sec && sec.classList.contains('admin-only') && !state.admin){ notify('Admin required', false); return; }
      setPage(p); routePage();
    });
  }


    // ===== Admin state (single source of truth) =====
    window.adminUnlocked = false;

    function setAdminUI(unlocked) {
      window.adminUnlocked = !!unlocked;
      document.body.classList.toggle('admin', window.adminUnlocked);
      // If on Ownership, re-render so admin-only bits refresh
      if (document.querySelector('#ownership')?.classList.contains('active-section') && window.sortMerged) {
        sortMerged((window.ownershipState && ownershipState.lastSort) || 'country');
      }
    }

    async function fetchAdminStatus() {
      try {
        const r = await fetch('/admin/auth/status', { credentials: 'include' });
        const j = await r.json();
        setAdminUI(!!j.unlocked);
        return !!j.unlocked;
      } catch {
        setAdminUI(false);
        return false;
      }
    }

    // keep session in sync after refresh
    document.addEventListener('DOMContentLoaded', fetchAdminStatus);

    // Existing UI elements (works with your current modal + buttons)
    const loginBtn  = document.querySelector('#admin-button');          // login/open modal button
    const logoutBtn = document.querySelector('#admin-logout');          // logout button
    const modal     = document.querySelector('#admin-login-backdrop');  // login modal backdrop
    const submit    = document.querySelector('#admin-submit');          // login submit
    const cancel    = document.querySelector('#admin-cancel');          // login cancel
    const pw        = document.querySelector('#admin-password');        // password input

    // open login modal
    loginBtn?.addEventListener('click', () => {
      modal.style.display = 'flex';
      pw.value = '';
      pw.focus();
    });

    // cancel login
    cancel?.addEventListener('click', () => {
      modal.style.display = 'none';
    });

    // submit login
    submit?.addEventListener('click', async () => {
      try {
        const r = await fetch('/admin/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ password: pw.value || '' })
        });
        const j = await r.json().catch(() => ({}));
        if (r.ok && j.ok) {
          setAdminUI(true);
          notify('Admin unlocked', true);
          modal.style.display = 'none';
          if (logoutBtn) logoutBtn.style.display = 'inline-block';
          if (loginBtn)  loginBtn.style.display  = 'none';
        } else {
          notify(j.error || 'Invalid password', false);
        }
      } catch {
        notify('Network error', false);
      }
    });

    // logout
    logoutBtn?.addEventListener('click', async () => {
      try {
        const r = await fetch('/admin/auth/logout', { method: 'POST', credentials: 'include' });
        if (r.ok) {
          setAdminUI(false);
          notify('Locked', true);
          if (loginBtn)  loginBtn.style.display  = 'inline-block';
          if (logoutBtn) logoutBtn.style.display = 'none';
        } else {
          notify('Logout failed', false);
        }
      } catch {
        notify('Network error', false);
      }
    });

    // sync on load so refresh keeps your admin state
    document.addEventListener('DOMContentLoaded', fetchAdminStatus);


    async function fetchVerifiedMap() {
      try {
        const res = await fetch('/api/verified', { cache: 'no-store' });
        if (!res.ok) throw new Error(`verified ${res.status}`);
        const data = await res.json();

        // Support array or object forms
        const arr = Array.isArray(data)
          ? data
          : (Array.isArray(data.users) ? data.users : []);

        const map = new Map();
        for (const u of arr) {
          const id = String(u.discord_id ?? u.id ?? '');
          const name = (u.display_name && String(u.display_name).trim())
                    || (u.username && String(u.username).trim())
                    || '';
          if (id) map.set(id, name || id);
        }
        return map;
      } catch (e) {
        console.error('[bets] verified map error:', e);
        return new Map();
      }
    }

    // 2) Resolve display name (prefer nickname)
    function resolveDisplayName(map, userId, fallbackUserString) {
      const id = userId ? String(userId) : '';
      const name = (id && map.get(id)) || '';
      if (name) return name;
      if (fallbackUserString) return fallbackUserString;
      if (id) return `User ${id}`;
      return 'Unknown';
    }

    function setOptionTooltip(el, claimedByText) {
      if (!el) return;
      el.title = claimedByText || 'Unclaimed';
    }

  // --- DASHBOARD ---
  async function loadDash(){
    try{
      const upP = fetchJSON('/api/uptime');
      const t0 = performance.now();
      const pingP = fetchJSON('/api/ping');
      const sysP = state.admin ? fetchJSON('/api/system') : Promise.resolve(null);

      const [up, ping, sys] = await Promise.all([upP, pingP, sysP]);
      const latency = Math.max(0, Math.round(performance.now() - t0));

      const running = (up && typeof up.bot_running === 'boolean')
        ? up.bot_running
        : !!(sys && sys.bot && typeof sys.bot.running === 'boolean' && sys.bot.running);

      renderUptime(up, running);
      renderPing(ping, latency);
      if(state.admin && sys) renderSystem(sys); else clearSystem();

      // Bot Actions (admin only). Buttons are not admin-gated, so JS fully controls them
      const $actions = qs('#bot-actions');
      const $start = qs('#start-bot');
      const $stop = qs('#stop-bot');
      const $restart = qs('#restart-bot');
      if(state.admin && $actions && $start && $stop && $restart){
        if(running){
          // online → Restart + Stop, 2 equal columns
          $start.style.display='none';
          $restart.style.display='block';
          $stop.style.display='block';
          $actions.style.gridTemplateColumns = '1fr 1fr';
        }else{
          // offline → Start only, full width
          $start.style.display='block';
          $restart.style.display='none';
          $stop.style.display='none';
          $actions.style.gridTemplateColumns = '1fr';
        }
      }
    }catch(e){ notify(`Dashboard error: ${e.message}`, false); }
  }

  function semicircleDash(pct){
    const total = 125.66;
    const c = Math.max(0, Math.min(100, Number(pct)||0));
    return `${(c/100)*total},${total}`;
  }
  function clearSystem(){
    ['mem-bar','cpu-bar','disk-bar'].forEach(id=>{
      const el = qs('#'+id); if(el) el.setAttribute('stroke-dasharray','0,125.66');
    });
    ['mem-text','cpu-text','disk-text'].forEach(id=>{ const el=qs('#'+id); if(el) el.textContent='--%'; });
    ['mem-extra','cpu-extra','disk-extra'].forEach(id=>{ const el=qs('#'+id); if(el) el.textContent=''; });
  }
    function renderSystem(sys){
      const s = sys?.system || {};

      const memPct = Number(s.mem_percent || 0);
      const cpuPct = Number(s.cpu_percent || 0);
      const diskPct = Number(s.disk_percent || 0);

      // Animate arcs
      const semicircleDash = (pct) => {
        const total = 125.66;                // arc length for our semicircle
        const c = Math.max(0, Math.min(100, Number(pct) || 0));
        return `${(c/100) * total},${total}`;
      };

      // Memory
      const memBar = document.getElementById('mem-bar');
      if (memBar) memBar.setAttribute('stroke-dasharray', semicircleDash(memPct));
      const memText = document.getElementById('mem-text');
      if (memText) memText.textContent = `${memPct.toFixed(0)}%`;
      const memExtra = document.getElementById('mem-extra');
      if (memExtra) memExtra.textContent =
        `Used ${Number(s.mem_used_mb||0).toFixed(0)} MB of ${Number(s.mem_total_mb||0).toFixed(0)} MB`;
      const memLegend = document.getElementById('mem-legend');
      if (memLegend) memLegend.textContent = `${memPct.toFixed(0)}%`;

      // CPU
      const cpuBar = document.getElementById('cpu-bar');
      if (cpuBar) cpuBar.setAttribute('stroke-dasharray', semicircleDash(cpuPct));
      const cpuText = document.getElementById('cpu-text');
      if (cpuText) cpuText.textContent = `${cpuPct.toFixed(0)}%`;
      const cpuExtra = document.getElementById('cpu-extra');
      if (cpuExtra) cpuExtra.textContent = `CPU ${cpuPct.toFixed(1)}%`;
      const cpuLegend = document.getElementById('cpu-legend');
      if (cpuLegend) cpuLegend.textContent = `${cpuPct.toFixed(0)}%`;

      // Disk
      const diskBar = document.getElementById('disk-bar');
      if (diskBar) diskBar.setAttribute('stroke-dasharray', semicircleDash(diskPct));
      const diskText = document.getElementById('disk-text');
      if (diskText) diskText.textContent = `${diskPct.toFixed(0)}%`;
      const diskExtra = document.getElementById('disk-extra');
      if (diskExtra) diskExtra.textContent =
        `Used ${Number(s.disk_used_mb||0).toFixed(0)} MB of ${Number(s.disk_total_mb||0).toFixed(0)} MB`;
      const diskLegend = document.getElementById('disk-legend');
      if (diskLegend) diskLegend.textContent = `${diskPct.toFixed(0)}%`;
    }
  function renderUptime(up, running){
    qs('#uptime-label').textContent = running ? 'Uptime' : 'Downtime';
    qs('#uptime-value').textContent = running ? (up?.uptime_hms || '--:--:--') : (up?.downtime_hms || '--:--:--');
    const statusEl = qs('#bot-status');
    if(statusEl){
      statusEl.textContent = running ? 'Online' : 'Offline';
      statusEl.style.color = running ? 'var(--accent)' : 'var(--danger)';
    }
  }
  function renderPing(ping, latencyMs){
    const ms = typeof ping?.latency_ms === 'number' ? Math.max(0, Math.round(ping.latency_ms)) : latencyMs;
    qs('#ping-value').textContent = isFinite(ms) ? `${ms} ms` : '-- ms';
  }

  // --- OWNERSHIP ---
    // ===== Verified picker (lazy-open; opens only on click) =====
    async function setupVerifiedPicker(preload = false) {
      const picker = document.getElementById('reassign-picker');
      const list   = document.getElementById('reassign-options');
      const idBox  = document.getElementById('reassign-id');
      if (!picker || !list || !idBox) return;

      async function populate() {
        // fetch /api/verified (preferred)
        let entries = [];
        try {
          const r = await fetch('/api/verified', { credentials: 'include' });
          const raw = await r.json();
          const arr = Array.isArray(raw) ? raw :
                      (Array.isArray(raw.verified_users) ? raw.verified_users : []);
          entries = arr.map(v => {
            const id = String(v.discord_id || v.id || v.user_id || '');
            const name = String(v.habbo_name || v.username || v.display_name || v.name || id);
            return id ? { id, name } : null;
          }).filter(Boolean);
        } catch {}

        // fallback /api/player_names
        if (entries.length === 0) {
          try {
            const r = await fetch('/api/player_names', { credentials: 'include' });
            const map = await r.json();
            entries = Object.keys(map).map(id => ({ id, name: map[id] || id }));
          } catch {}
        }

        // render
        entries.sort((a,b) => a.name.localeCompare(b.name));
        list.innerHTML = '';
        entries.forEach(({ id, name }) => {
          const li = document.createElement('li');
          li.setAttribute('role', 'option');
          li.dataset.id = id;
          li.dataset.label = `${name} (${id})`;
          li.textContent = li.dataset.label;
          list.appendChild(li);
        });
      }

      // Wire once
      if (!picker.dataset.wired) {
        picker.dataset.wired = '1';

        // Toggle on click; if empty, populate first
        picker.addEventListener('click', async () => {
          if (list.childElementCount === 0) {
            await populate();            // fill silently first time
            if (list.childElementCount === 0) return; // nothing to show
          }
          const open = list.hidden;
          list.hidden = !open;
          picker.setAttribute('aria-expanded', String(open));
        });

        // Select an option
        list.addEventListener('click', (e) => {
          const li = e.target.closest('li');
          if (!li) return;
          picker.textContent = li.dataset.label;
          idBox.value = li.dataset.id;
          list.hidden = true;
          picker.setAttribute('aria-expanded', 'false');
        });

        // Close when clicking outside
        document.addEventListener('click', (e) => {
          if (e.target === picker || e.target.closest('#verified-select')) return;
          if (!list.hidden) {
            list.hidden = true;
            picker.setAttribute('aria-expanded', 'false');
          }
        });
      }

      // Optional preload (keeps list hidden)
      if (preload && list.childElementCount === 0) {
        try { await populate(); } catch {}
      }
    }





  function escapeHtml(v){ return String(v==null?'':v).replace(/[&<>"']/g, s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s])); }
  function ensureSectionCard(id, title, controls){
    const sec = qs(`#${id}`); sec.innerHTML='';
    const wrap = document.createElement('div'); wrap.className='table-wrap';
    const head = document.createElement('div'); head.className='table-head';
    head.innerHTML = `<div class="table-title">${title}</div><div class="table-actions"></div>`;
    const actions = head.querySelector('.table-actions');
    (controls||[]).forEach(([label, meta])=>{
      if(meta && meta.kind==='input'){
        const inp = document.createElement('input'); inp.type='text'; inp.id=meta.id; inp.placeholder=meta.placeholder||'';
        actions.appendChild(inp);
      }else if(meta && meta.kind==='select'){
        const sel=document.createElement('select'); sel.id=meta.id;
        (meta.items||[]).forEach(v=>{ const o=document.createElement('option'); o.value=v; o.textContent=v; sel.appendChild(o); });
        actions.appendChild(sel);
      }else{
        const btn = document.createElement('button'); btn.className='btn'; if(meta?.id) btn.id=meta.id; btn.textContent=label; actions.appendChild(btn);
      }
    });
    const scroll = document.createElement('div'); scroll.className='table-scroll';
    wrap.appendChild(head); wrap.appendChild(scroll); sec.appendChild(wrap);
    return wrap;
  }

    // ===== Verified users loader (from /api/verified) =====
    function parseVerifiedPayload(payload) {
      if (!payload) return [];
      if (Array.isArray(payload)) return payload;
      if (payload.verified_users && Array.isArray(payload.verified_users)) return payload.verified_users;
      return [];
    }
    function normalizeVerifiedItem(item) {
      const id = item.discord_id || item.id || item.user_id || item.discordId || item.uid || '';
      const nm = item.habbo_name || item.username || item.display_name || item.name || String(id);
      return id ? { id: String(id), name: String(nm) } : null;
    }

// -------------------- OWNERSHIP (teams.json + players.json) --------------------

// ===== Flags helpers =====
window.TEAM_ISO = null;

async function ensureTeamIsoLoaded(force = false) {
  if (window.TEAM_ISO && !force) return window.TEAM_ISO;
  try {
    const r = await fetch('/api/team_iso', { credentials: 'include' });
    window.TEAM_ISO = r.ok ? (await r.json()) : {};
  } catch {
    window.TEAM_ISO = {};
  }
  return window.TEAM_ISO;
}

// Optional aliases for common naming differences
const ISO_ALIASES = {
  'USA': 'us', 'United States': 'uS',
  'England': 'gb-eng', 'Scotland': 'gb-sct', 'Wales': 'gb-wls', 'Northern Ireland': 'gb-nir',
  'South Korea': 'kr', 'Ivory Coast': 'ci', "Côte d’Ivoire": 'ci', "Cote d'Ivoire": 'ci'
};

// Find the ISO code for a given country name
function resolveIsoCode(country) {
  if (!country) return '';
  const c = String(country).trim();

  // direct match
  if (window.TEAM_ISO && window.TEAM_ISO[c]) return window.TEAM_ISO[c];
  // alias match
  if (ISO_ALIASES[c]) return ISO_ALIASES[c];

  // relaxed match (case/space-insensitive)
  const norm = c.toLowerCase().replace(/\s+/g, ' ');
  for (const k in (window.TEAM_ISO || {})) {
    if (k.toLowerCase().replace(/\s+/g, ' ') === norm) return window.TEAM_ISO[k];
  }
  return '';
}

// Safe emoji from alpha-2 code
function codeToEmoji(cc) {
  if (!/^[A-Za-z]{2}$/.test(cc)) return '🏳️';
  const up = cc.toUpperCase();
  const base = 127397;
  return String.fromCodePoint(base + up.charCodeAt(0), base + up.charCodeAt(1));
}

// Build the flag HTML (img with emoji fallback)
function flagHTML(country) {
  const code = resolveIsoCode(country);
  if (!code) return '';
  const emoji = codeToEmoji(code);
  const src = `https://flagcdn.com/24x18/${code}.png`; // switch to /static/flags/${code}.svg if you host locally
  const fallback = emoji !== '🏳️' ? emoji : '';
  return `<img class="flag-img" src="${src}" alt="${country}"
          onerror="this.replaceWith(document.createTextNode('${fallback}'));">`;
}

var ownershipState = { teams: [], rows: [], merged: [], loaded: false, lastSort: 'country' };
var playerNames = {}; // id -> username

function renderOwnershipTable(list) {
  var tbody = document.querySelector('#ownership-tbody');
  if (!tbody) return;
  tbody.innerHTML = '';

  list.forEach(function (row) {
    var tr = document.createElement('tr');
    if (!row.main_owner) tr.classList.add('row-unassigned');
    else tr.classList.add('row-assigned');

    // Prefer username; only show numeric ID when logged in as admin
    var label = (row.main_owner && (row.main_owner.username || row.main_owner.id)) || '';
    var idVal = row.main_owner ? row.main_owner.id : '';
    var showId = !!(window.adminUnlocked && idVal && label !== idVal);

    var ownerCell = '';
    if (row.main_owner) {
      ownerCell =
        '<span class="owner-name" title="' + idVal + '">' + label + '</span>' +
        (showId ? ' <span class="muted">(' + idVal + ')</span>' : '');
    } else {
      ownerCell = 'Unassigned <span class="warn-icon" title="No owner">⚠️</span>';
    }

    var splitStr = '—';
    if (row.split_with && row.split_with.length) {
      splitStr = row.split_with.map(function (s) {
        return s.username || s.id;
      }).join(', ');
    }

    tr.innerHTML = `
       <td>
         ${flagHTML(row.country)}
         <span class="country-name">${row.country}</span>
       </td>
      <td>${ownerCell}</td>
      <td>${splitStr}</td>
      <td class="admin-col" data-admin="true">
        <button class="btn btn-outline xs reassign-btn" data-team="${row.country}">Reassign</button>
      </td>
    `;


    tbody.appendChild(tr);
  });
}

function sortMerged(by) {
  ownershipState.lastSort = by;
  var list = ownershipState.merged.slice();
  if (by === 'country') {
    list.sort(function (a, b) { return a.country.localeCompare(b.country); });
  } else if (by === 'player') {
    var name = function (r) {
      var n = (r.main_owner && (r.main_owner.username || r.main_owner.id)) || 'zzzz~unassigned';
      return n.toLowerCase();
    };
    list.sort(function (a, b) { return name(a).localeCompare(name(b)); });
  }
  renderOwnershipTable(list);
}

function fetchOwnershipRows() {
  return fetch('/api/ownership_from_players').then(function (r) {
    if (!r.ok) throw new Error('GET /api/ownership_from_players ' + r.status);
    return r.json();
  });
}

function fetchTeamsList() {
  return fetch('/api/teams').then(function (r) {
    if (!r.ok) return null;
    return r.json();
  }).then(function (j) {
    if (!j) {
      if (ownershipState.rows && ownershipState.rows.length) {
        return ownershipState.rows.map(function (r) { return r.country; })
          .sort(function (a, b) { return a.localeCompare(b); });
      }
      return [];
    }
    return Array.isArray(j) ? j : (Array.isArray(j.teams) ? j.teams : []);
  }).catch(function () {
    if (ownershipState.rows && ownershipState.rows.length) {
      return ownershipState.rows.map(function (r) { return r.country; })
        .sort(function (a, b) { return a.localeCompare(b); });
    }
    return [];
  });
}

function mergeTeamsWithOwnership(teams, rows) {
  var byTeam = {};
  rows.forEach(function (r) { byTeam[String(r.country).toLowerCase()] = r; });

  return teams.map(function (team) {
    var key = String(team).toLowerCase();
    var m = byTeam[key];
    if (!m) return { country: team, main_owner: null, split_with: [], owners_count: 0 };

    var main = (m.main_owner && m.main_owner.id)
      ? { id: String(m.main_owner.id), username: m.main_owner.username || null }
      : null;

    var splits = (m.split_with || []).map(function (s) {
      return { id: String(s.id), username: s.username || null };
    });

    var ownersCnt = (main ? 1 : 0) + splits.filter(function (s) { return s.id !== (main ? main.id : ''); }).length;

    return { country: team, main_owner: main, split_with: splits, owners_count: ownersCnt };
  });
}

// REPLACE your whole initOwnership with this async version
async function initOwnership() {
  try {
    // 1) Try merged endpoint
    let list = null;
    try {
      const r = await fetch('/api/ownership_merged', { credentials: 'include' });
      if (r.ok) {
        const j = await r.json();
        if (j && Array.isArray(j.rows)) list = j.rows;
      }
    } catch { /* fall through to fallback */ }

    // 2) Fallback: ownership_from_players + teams
    if (!list) {
      const [rowsObj, teams] = await Promise.all([
        (async () => {
          const r = await fetch('/api/ownership_from_players', { credentials: 'include' });
          if (!r.ok) throw new Error('GET /api/ownership_from_players ' + r.status);
          return (await r.json()) || {};
        })(),
        (async () => {
          try {
            const r = await fetch('/api/teams', { credentials: 'include' });
            const j = r.ok ? await r.json() : [];
            return Array.isArray(j) ? j : (Array.isArray(j.teams) ? j.teams : []);
          } catch { return []; }
        })()
      ]);

      ownershipState.rows  = rowsObj.rows || [];
      ownershipState.teams = teams || [];
      list = mergeTeamsWithOwnership(ownershipState.teams, ownershipState.rows);
    }

    // 3) Hydrate usernames
    let names = {};
    try {
      const r = await fetch('/api/player_names', { credentials: 'include' });
      names = r.ok ? (await r.json()) : {};
    } catch { names = {}; }

    playerNames = names || {};
    list.forEach(row => {
      if (row.main_owner) {
        const id = row.main_owner.id;
        row.main_owner.username = row.main_owner.username || playerNames[id] || id;
      }
      (row.split_with || []).forEach(s => {
        const sid = s.id;
        s.username = s.username || playerNames[sid] || sid;
      });
    });

    // 4) Ensure flag map is loaded BEFORE rendering
    await ensureTeamIsoLoaded();

    // 5) Render
    ownershipState.merged = list;
    ownershipState.loaded = true;
    sortMerged(ownershipState.lastSort || 'country');
  } catch (e) {
    console.error('[ownership:init]', e);
    notify('Failed to load ownership data', false);
  }
}


// Sort buttons
var sortCountryBtn = document.querySelector('#sort-country');
var sortPlayerBtn = document.querySelector('#sort-player');
if (sortCountryBtn) sortCountryBtn.addEventListener('click', function () { sortMerged('country'); });
if (sortPlayerBtn) sortPlayerBtn.addEventListener('click', function () { sortMerged('player'); });

// Delegated Reassign button
document.addEventListener('click', function (e) {
  var btn = e.target.closest ? e.target.closest('.reassign-btn') : null;
  if (!btn) return;
  if (!window.adminUnlocked) return notify('Admin required', false);
  var team = btn.getAttribute('data-team') || '';
  if (!team) return;
  document.getElementById('reassign-team').value = team;
  document.getElementById('reassign-select').value = '';
  document.getElementById('reassign-id').value = '';
  document.getElementById('reassign-backdrop').style.display = 'flex';
});

    // ===== Reassign flow (custom dropdown version - no native <select>) =====
    const reassignBackdrop = document.getElementById('reassign-backdrop');
    const reassignTeamInp  = document.getElementById('reassign-team');
    const reassignIdInp    = document.getElementById('reassign-id');
    const pickerBtn        = document.getElementById('reassign-picker');   // button label of custom dropdown

    // Open modal (ensure admin first)
    document.addEventListener('click', async (e) => {
      const btn = e.target.closest?.('.reassign-btn');
      if (!btn) return;

      const unlocked = await fetchAdminStatus();
      if (!unlocked) return notify('Admin required', false);

      // Prefill + reset
      const team = btn.getAttribute('data-team') || '';
      document.getElementById('reassign-team').value = team;
      document.getElementById('reassign-id').value = '';
      const pickerBtn = document.getElementById('reassign-picker');
      if (pickerBtn) pickerBtn.textContent = '-- Select a player --';

      // PRELOAD silently, do NOT open
      await setupVerifiedPicker(true);   // true = preload, still hidden

      document.getElementById('reassign-backdrop').style.display = 'flex';
    });

// Close/cancel
document.getElementById('reassign-close')?.addEventListener('click', () => {
  reassignBackdrop.style.display = 'none';
});
document.getElementById('reassign-cancel')?.addEventListener('click', () => {
  reassignBackdrop.style.display = 'none';
});

// Submit (no second-stage confirm)
document.getElementById('reassign-submit')?.addEventListener('click', async () => {
  const unlocked = await fetchAdminStatus();
  if (!unlocked) return notify('Admin required', false);

    const team  = (document.getElementById('reassign-team').value || '').trim();
    const newId = (document.getElementById('reassign-id').value || '').trim();
    const label = (document.getElementById('reassign-picker')?.textContent || '').trim();

  if (!team || !newId) return notify('Team and new owner ID required', false);

  try {
    const r = await fetch('/admin/ownership/reassign', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ team, new_owner_id: newId })
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.ok === false) return notify(j.error || 'Reassign failed', false);

    document.getElementById('reassign-backdrop').style.display = 'none';
    notify(`Reassigned ${team} to ${label || newId}`, true);
    await refreshOwnershipNow(); // hard refresh of the Ownership card
  } catch {
    notify('Network error', false);
  }
});

// ---- Ownership Table ----
async function refreshOwnershipNow() {
  try {
    // Disable buttons briefly to avoid double clicks
    document.querySelectorAll('.reassign-btn').forEach(b => b.disabled = true);

    // 1) Get merged rows (all countries, owners, splits)
    const r = await fetch('/api/ownership_merged', { credentials: 'include' });
    const merged = r.ok ? (await r.json()).rows : null;

    if (!Array.isArray(merged)) {
      // Fallback to old two-call path if merged endpoint is unavailable
      const [rowsObj, teamsResp] = await Promise.all([
        fetch('/api/ownership_from_players', { credentials: 'include' }).then(x => x.json()),
        fetch('/api/teams', { credentials: 'include' }).then(x => x.json())
      ]);
      const teams = Array.isArray(teamsResp) ? teamsResp : (Array.isArray(teamsResp?.teams) ? teamsResp.teams : []);
      // minimal merge
      const byTeam = {};
      (rowsObj.rows || []).forEach(row => { byTeam[String(row.country).toLowerCase()] = row; });
      ownershipState.merged = teams.map(team => {
        const m = byTeam[String(team).toLowerCase()];
        if (!m) return { country: team, main_owner: null, split_with: [], owners_count: 0 };
        return {
          country: team,
          main_owner: m.main_owner ? { id: String(m.main_owner.id), username: m.main_owner.username || null } : null,
          split_with: (m.split_with || []).map(s => ({ id: String(s.id), username: s.username || null })),
          owners_count: m.owners_count || 0
        };
      });
    } else {
      ownershipState.merged = merged;
    }

    // 2) Hydrate id->name map so we show names not raw IDs
    let names = {};
    try {
      const nr = await fetch('/api/player_names', { credentials: 'include' });
      if (nr.ok) names = await nr.json();
    } catch {}

    ownershipState.merged.forEach(row => {
      if (row.main_owner) {
        const id = row.main_owner.id;
        row.main_owner.username = row.main_owner.username || names[id] || id;
      }
      (row.split_with || []).forEach(s => {
        s.username = s.username || names[s.id] || s.id;
      });
    });

    // 3) Mark loaded and re-render using last sort
    ownershipState.loaded = true;
    sortMerged(ownershipState.lastSort || 'country');
  } catch (e) {
    console.error('[ownership:refresh]', e);
    notify('Failed to refresh ownership', false);
  } finally {
    document.querySelectorAll('.reassign-btn').forEach(b => b.disabled = false);
  }
}

// Buttons
document.querySelector('#sort-country')?.addEventListener('click', () => sortMerged('country'));
document.querySelector('#sort-player')?.addEventListener('click', () => sortMerged('player'));

// Make sure router triggers initialization on first show
const _origShowPage = typeof showPage === 'function' ? showPage : null;
window.showPage = function(id) {
  if (_origShowPage) _origShowPage(id);
  else {
    // simple fallback visibility if you don't have a router:
    document.querySelectorAll('section.page-section, section.dashboard')
      .forEach(s => s.classList.remove('active-section'));
    document.getElementById(id)?.classList.add('active-section');
  }
  if (id === 'ownership' && !ownershipState.loaded) initOwnership();
};

// Hard-init as a safety net (if router didn’t run yet)
document.addEventListener('DOMContentLoaded', () => {
  // If Ownership page is already visible, init immediately
  const visible = document.querySelector('#ownership.page-section.active-section');
  if (visible && !ownershipState.loaded) initOwnership();
  // Otherwise no-op; router will call it when you click the tab
});

// ---- Compatibility shim for existing router ----
async function loadOwnershipPage() {
  // If your router expects a Promise, keep this async
  if (!ownershipState.loaded) {
    await initOwnership();
  } else {
    // Re-render using last sort so the page updates on re-entry
    sortMerged(ownershipState.lastSort || 'country');
  }
}
// expose globally in case your router looks up window[loaderName]
window.loadOwnershipPage = loadOwnershipPage;

    // 1) Verified map loader: {id -> display_name}
    async function fetchVerifiedMap() {
      try {
        const res = await fetch('/api/verified', { cache: 'no-store' });
        if (!res.ok) throw new Error(`verified ${res.status}`);
        const data = await res.json();

        // Support array or object forms
        const arr = Array.isArray(data)
          ? data
          : (Array.isArray(data.users) ? data.users : []);

        const map = new Map();
        for (const u of arr) {
          const id = String(u.discord_id ?? u.id ?? '');
          const name = (u.display_name && String(u.display_name).trim())
                    || (u.username && String(u.username).trim())
                    || '';
          if (id) map.set(id, name || id);
        }
        return map;
      } catch (e) {
        console.error('[bets] verified map error:', e);
        return new Map();
      }
    }

    // 2) Resolve display name (prefer nickname)
    function resolveDisplayName(map, userId, fallbackUserString) {
      const id = userId ? String(userId) : '';
      const name = (id && map.get(id)) || '';
      if (name) return name;
      if (fallbackUserString) return fallbackUserString;
      if (id) return `User ${id}`;
      return 'Unknown';
    }

    async function loadAndRenderBets() {
      const host = document.getElementById('bets');
      if (!host) return;

      // header - no hover hint
      host.innerHTML = `
        <div class="table-wrap">
          <div class="table-head">
            <div class="table-title">Bets</div>
            <div class="table-actions">
              <button id="bets-refresh" class="btn small">Refresh</button>
            </div>
          </div>
          <div class="table-scroll"><div class="muted" style="padding:12px">Loading…</div></div>
        </div>
      `;

      const getJSON = async (url, opts={}) => {
        const res = await fetch(url, { cache: 'no-store', ...opts });
        if (!res.ok) throw new Error(`${url} ${res.status}`);
        return res.json();
      };
      const postJSON = async (url, body) => {
        const res = await fetch(url, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(body || {})
        });
        if (!res.ok) throw new Error(`${url} ${res.status}`);
        return res.json().catch(() => ({}));
      };

      // build verified map for fallbacks
      let verifiedMap = new Map();
      try {
        const verified = await getJSON('/api/verified');
        const arr = Array.isArray(verified) ? verified : (verified.users || []);
        verifiedMap = new Map(arr.map(u => [
          String(u.discord_id ?? u.id ?? ''),
          (u.display_name && String(u.display_name).trim()) ||
          (u.username && String(u.username).trim()) || ''
        ]));
      } catch { /* ok on public */ }

      // helper: prefer display_name from verified map, fall back to provided username
      const resolveDisplayName = (id, fallbackUsername) => {
        const key = id ? String(id) : '';
        return (key && verifiedMap.get(key)) || fallbackUsername || (key ? `User ${key}` : 'Unknown');
      };

      // fetch bets (enriched by backend if you used the latest routes_public.py)
      let bets = [];
      try {
        const raw = await getJSON('/api/bets');
        bets = Array.isArray(raw) ? raw : (raw.bets || []);
      } catch (e) {
        console.error('[bets] load failed:', e);
      }

      const scroller = host.querySelector('.table-scroll');
      scroller.innerHTML = '';

      const table = document.createElement('table');
      table.className = 'table';
      table.innerHTML = `
        <thead>
          <tr>
            <th>ID</th>
            <th>Title</th>
            <th>Wager</th>
            <th>Option 1</th>
            <th>Option 2</th>
            <th>Winner</th>
          </tr>
        </thead>
        <tbody></tbody>
      `;
      const tbody = table.querySelector('tbody');

      for (const bet of bets) {
        const tr = document.createElement('tr');

        const tdId = document.createElement('td');
        tdId.textContent = bet.bet_id ?? '-';

        const tdTitle = document.createElement('td');
        tdTitle.textContent = bet.bet_title ?? '-';

        const tdWager = document.createElement('td');
        tdWager.textContent = bet.wager ?? '-';

        // Compute display names ONCE and reuse everywhere
        const o1Name = (bet.option1_display_name ??
                       resolveDisplayName(bet.option1_user_id, bet.option1_user_name)) || '';
        const o2Name = (bet.option2_display_name ??
                       resolveDisplayName(bet.option2_user_id, bet.option2_user_name)) || '';

        // Option 1 cell with tooltip on text
        const tdO1 = document.createElement('td');
        tdO1.className = 'bet-opt bet-opt1';
        const s1 = document.createElement('span');
        s1.textContent = bet.option1 ?? '-';
        s1.dataset.tip = (bet.option1_user_id || bet.option1_user_name)
          ? `Claimed by: ${o1Name}`
          : 'Unclaimed';
        tdO1.appendChild(s1);

        // Option 2 cell with tooltip on text
        const tdO2 = document.createElement('td');
        tdO2.className = 'bet-opt bet-opt2';
        const s2 = document.createElement('span');
        s2.textContent = bet.option2 ?? '-';
        s2.dataset.tip = (bet.option2_user_id || bet.option2_user_name)
          ? `Claimed by: ${o2Name}`
          : 'Unclaimed';
        tdO2.appendChild(s2);

        // Winner column
        const tdWin = document.createElement('td');
        tdWin.className = 'bet-winner';
        const winner = bet.winner === 'option1' || bet.winner === 'option2' ? bet.winner : null;

        if (window.state && state.admin === true) {
          // ADMIN: show Set O1 / Set O2 buttons
          const box = document.createElement('div');
          box.className = 'win-controls';

          const b1 = document.createElement('button');
          b1.className = 'btn xs' + (winner === 'option1' ? ' active' : '');
          b1.textContent = 'Set O1';
          b1.disabled = winner === 'option1';
          b1.onclick = async () => {
            try {
              await postJSON(`/admin/bets/${encodeURIComponent(bet.bet_id)}/winner`, { winner: 'option1' });
              loadAndRenderBets();
            } catch (e) {
              console.error('declare winner o1:', e);
              if (typeof notify === 'function') notify('Failed to set winner', false);
            }
          };

          const b2 = document.createElement('button');
          b2.className = 'btn xs' + (winner === 'option2' ? ' active' : '');
          b2.textContent = 'Set O2';
          b2.disabled = winner === 'option2';
          b2.onclick = async () => {
            try {
              await postJSON(`/admin/bets/${encodeURIComponent(bet.bet_id)}/winner`, { winner: 'option2' });
              loadAndRenderBets();
            } catch (e) {
              console.error('declare winner o2:', e);
              if (typeof notify === 'function') notify('Failed to set winner', false);
            }
          };

          box.append(b1, b2);
          tdWin.appendChild(box);
        } else {
          // PUBLIC: show the claimant's display name
          const pill = document.createElement('span');
          pill.className = 'pill ' + (winner ? 'pill-winner' : 'pill-tbd');
          if (winner === 'option1') pill.textContent = o1Name || 'Option 1';
          else if (winner === 'option2') pill.textContent = o2Name || 'Option 2';
          else pill.textContent = 'TBD';
          tdWin.appendChild(pill);
        }

        tr.append(tdId, tdTitle, tdWager, tdO1, tdO2, tdWin);
        tbody.appendChild(tr);
      }

      scroller.appendChild(table);

      const btn = document.getElementById('bets-refresh');
      if (btn) btn.onclick = () => loadAndRenderBets();

      if (typeof enableHoverTips === 'function') enableHoverTips();
    }


/* -----------------------------
   Splits page (Requests + History)
   Reads:
     /admin/splits                 -> JSON/split_requests.json normalized
     /admin/splits/history?limit=N -> JSON/split_requests_log.json normalized
   ----------------------------- */

// ensure we have a state bag
window.state = window.state || {};

// stop any prior poller when we re-enter the page
if (state.splitsHistoryTimer) {
  clearInterval(state.splitsHistoryTimer);
  state.splitsHistoryTimer = null;
}

async function loadSplits() {
  try {
    const data = await fetchJSON('/admin/splits'); // { pending: [] }

    const wrap = ensureSectionCard('splits', 'Split Requests', [
      ['Refresh', { id: 'splits-refresh' }]
    ]);

    const scroller = wrap.querySelector('.table-scroll');
    scroller.innerHTML = '';

    const container = document.createElement('div');
    container.className = 'split-wrap';

    const pending = Array.isArray(data?.pending) ? data.pending : [];
    container.appendChild(buildPendingSplits(pending));

    // history section (from log file)
    const historyBox = document.createElement('div');
    historyBox.className = 'split-section';
    historyBox.innerHTML = `
      <div class="split-head">
        <div class="split-title">History</div>
        <div class="split-count badge" id="split-hist-count">0</div>
      </div>
      <div id="split-history-body"></div>
    `;
    container.appendChild(historyBox);

    scroller.appendChild(container);

    // refresh and polling
    const btn = document.getElementById('splits-refresh');
    if (btn) btn.onclick = () => { clearInterval(state.splitsHistoryTimer); loadSplits(); };
    await loadSplitHistoryOnce();
    clearInterval(state.splitsHistoryTimer);
    state.splitsHistoryTimer = setInterval(loadSplitHistoryOnce, 10000);

  } catch (e) {
    notify(`Failed to fetch splits: ${e.message || e}`, false);
  }
}

function buildPendingSplits(rows) {
  const box = document.createElement('div');
  box.className = 'split-section';

  const head = document.createElement('div');
  head.className = 'split-head';
  head.innerHTML = `
    <div class="split-title">Pending</div>
    <div class="split-count badge" id="pending-count">${rows.length}</div>
  `;
  box.appendChild(head);

  if (!rows.length) {
    const empty = document.createElement('div');
    empty.className = 'split-empty';
    empty.textContent = 'No pending requests.';
    box.appendChild(empty);
    return box;
  }

  const table = document.createElement('table');
  table.className = 'table splits';
  table.innerHTML = `
    <thead>
      <tr>
        <th class="col-id">ID</th>
        <th class="col-team">TEAM</th>
        <th class="col-user">FROM</th>
        <th class="col-user">TO</th>
        <th class="col-when">EXPIRES</th>
        <th class="col-status">ACTION</th>
      </tr>
    </thead>
    <tbody></tbody>
  `;
  const tbody = table.querySelector('tbody');

  const sorted = rows.slice().sort((a, b) => {
    const ta = +new Date(a?.expires_at || 0);
    const tb = +new Date(b?.expires_at || 0);
    return tb - ta;
  });

  for (const r of sorted) {
    const realId = r.id ?? '-';
    const idShort = shortId(realId);
    const team = r.team ?? '-';
    const from = r.from_username ?? r.requester_id ?? '-';
    const to = r.to_username ?? r.main_owner_id ?? '-';
    const when = r.expires_at ?? null;

    const tr = document.createElement('tr');
    tr.dataset.sid = realId;
    tr.innerHTML = `
      <td class="col-id" title="${escapeHTML(realId)}">${idShort}</td>
      <td class="col-team"><span class="clip" title="${escapeHTML(team)}">${escapeHTML(team)}</span></td>
      <td class="col-user"><span class="clip" title="${escapeHTML(String(from))}">${escapeHTML(String(from))}</span></td>
      <td class="col-user"><span class="clip" title="${escapeHTML(String(to))}">${escapeHTML(String(to))}</span></td>
      <td class="col-when mono">${when ? fmtDateTime(when) : '-'}</td>
      <td class="col-status">
        <div class="action-cell">
          <button type="button" class="pill pill-warn pill-click">Pending</button>
          <div class="chip-group--split hidden">
            <button class="btn-split split-accept" data-action="accept" data-id="${escapeHTML(realId)}">Accept</button>
            <button class="btn-split split-decline" data-action="decline" data-id="${escapeHTML(realId)}">Decline</button>
          </div>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  }

  // collapse any open chip groups
  function collapseAll() {
    table.querySelectorAll('.action-cell').forEach(cell => {
      cell.querySelector('.pill-click')?.classList.remove('hidden');
      cell.querySelector('.chip-group--split')?.classList.add('hidden');
    });
  }

  // delegate clicks
  table.addEventListener('click', async (e) => {
    const pill = e.target.closest('.pill-click');
    if (pill) {
      const cell = pill.closest('.action-cell');
      const chips = cell.querySelector('.chip-group--split');
      const isOpen = !chips.classList.contains('hidden');
      collapseAll();
      if (!isOpen) {
        pill.classList.add('hidden');
        chips.classList.remove('hidden');
      }
      return;
    }

    const chip = e.target.closest('.btn-split[data-action]');
    if (chip) {
      const action = chip.getAttribute('data-action');   // "accept" | "decline"
      const sid = chip.getAttribute('data-id');
      const row = chip.closest('tr');

      row.querySelectorAll('.btn-split').forEach(b => b.disabled = true);

      try {
        const res = await submitSplitAction(action, sid); // { ok, pending_count, history_count, event }
        if (!res || res.ok === false) throw new Error(res?.error || 'unknown error');

        // remove row; update counter
        row.remove();
        const countEl = document.getElementById('pending-count');
        if (countEl && typeof res.pending_count === 'number') countEl.textContent = res.pending_count;

        if (!tbody.children.length) {
          const empty = document.createElement('div');
          empty.className = 'split-empty';
          empty.textContent = 'No pending requests.';
          table.replaceWith(empty);
        }

        loadSplitHistoryOnce(); // refresh history to show event
        notify(`Split ${action}ed`, true);
      } catch (err) {
        notify(`Failed to ${action} split: ${err.message || err}`, false);
        row.querySelectorAll('.btn-split').forEach(b => b.disabled = false);
      }
    }
  });

  document.addEventListener('click', (ev) => {
    if (!table.contains(ev.target)) collapseAll();
  }, { once: true });

  box.appendChild(table);
  return box;
}

/* POST helper for force accept/decline – matches routes_admin.py */
async function submitSplitAction(action, id) {
  const url = action === 'accept' ? '/admin/splits/accept' : '/admin/splits/decline';
  const res = await fetchJSON(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id })
  });
  return res; // { ok, pending_count, history_count, event }
}


// History loader - simplified columns (When, Action, Team, From, To)
// Reads /admin/splits/history -> JSON/split_requests_log.json
async function loadSplitHistoryOnce() {
  try {
    const { events = [] } = await fetchJSON('/admin/splits/history?limit=200');

    const body = document.getElementById('split-history-body');
    const count = document.getElementById('split-hist-count');
    if (!body) return;

    count && (count.textContent = events.length);

    if (!events.length) {
      body.innerHTML = `<div class="split-empty">No history recorded yet.</div>`;
      return;
    }

    // newest first
    const sorted = events.slice().sort((a, b) => {
      const ta = +new Date(a?.created_at || a?.time || a?.timestamp || 0);
      const tb = +new Date(b?.created_at || b?.time || b?.timestamp || 0);
      return tb - ta;
    });

    const table = document.createElement('table');
    table.className = 'table splits';
    table.innerHTML = `
      <thead>
        <tr>
          <th class="col-id">ID</th>
          <th class="col-team">TEAM</th>
          <th class="col-user">FROM</th>
          <th class="col-user">TO</th>
          <th class="col-when">WHEN</th>
          <th class="col-status">ACTION</th>
        </tr>
      </thead>
      <tbody></tbody>
    `;
    const tbody = table.querySelector('tbody');

    for (const ev of sorted) {
      const id = ev.id ?? ev.request_id ?? ''; // history may not have an ID; blank keeps alignment
      const team = ev.team || ev.country || ev.country_name || '-';
      const fromUser =
        ev.from_username || ev.requester_username || ev.from || ev.requester_id || '-';
      const toUser =
        ev.to_username || ev.receiver_username || ev.to || ev.main_owner_id || '-';
      const when = ev.created_at || ev.time || ev.timestamp || null;
      const actionRaw = (ev.action || ev.status || '').toString().toLowerCase();

      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="col-id" title="${escapeHTML(String(id))}">${shortId(id)}</td>
        <td class="col-team"><span class="clip" title="${escapeHTML(team)}">${escapeHTML(team)}</span></td>
        <td class="col-user"><span class="clip" title="${escapeHTML(String(fromUser))}">${escapeHTML(String(fromUser))}</span></td>
        <td class="col-user"><span class="clip" title="${escapeHTML(String(toUser))}">${escapeHTML(String(toUser))}</span></td>
        <td class="col-when mono">${when ? fmtDateTime(when) : '-'}</td>
        <td class="col-status">${splitStatusPill(actionRaw)}</td>
      `;
      tbody.appendChild(tr);
    }

    body.innerHTML = '';
    body.appendChild(table);

  } catch (e) {
    // Non-fatal; keep last known history
    notify(`History refresh failed: ${e.status || ''} ${e.message}`, false);
  }
}

/* ---------- small utils ---------- */
function splitStatusPill(status) {
  const map = { pending:'pill-warn', approved:'pill-ok', accepted:'pill-ok', resolved:'pill-ok', denied:'pill-off', rejected:'pill-off' };
  const cls = map[status] || 'pill-off';
  const label = status ? status[0].toUpperCase() + status.slice(1) : 'Unknown';
  return `<span class="pill ${cls}">${label}</span>`;
}
function escapeHTML(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function fmtDateTime(x) {
  let t = x;
  if (typeof t === 'string' && /^\d+(\.\d+)?$/.test(t)) t = Number(t);
  if (typeof t === 'number') {
    // if it's likely seconds (<= 10^12), convert to ms
    if (t < 1e12) t = t * 1000;
  }
  const d = new Date(t);
  if (Number.isNaN(d.getTime())) return '-';
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function shortId(id) {
  if (!id) return '-';
  const str = String(id);
  // simple deterministic hash
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash * 31 + str.charCodeAt(i)) >>> 0;
  }
  return '#' + (hash % 90000 + 10000); // always 5 digits, range 10000–99999
}


    async function loadBackups(){
      try{
        // 1) get list from the API
        const d = await fetchJSON('/api/backups');

        // 2) build the section header WITHOUT a prune button
        const w = ensureSectionCard('backups', 'Backups', [
          ['Backup All',      { id: 'backup-all' }],
          ['Restore Latest',  { id: 'restore-latest' }]
        ]);

        // 3) render the table
        const s = w.querySelector('.table-scroll');
        s.innerHTML = '';

        const files = (d?.backups) || (d?.folders?.[0]?.files) || [];
        if (!files.length){
          const p = document.createElement('p');
          p.textContent = 'No backups yet.';
          s.appendChild(p);
        } else {
          const t = document.createElement('table');
          t.className = 'table';
          t.innerHTML = '<thead><tr><th>Name</th><th>Size</th><th>Modified</th><th></th></tr></thead><tbody></tbody>';
          const tb = t.querySelector('tbody');

          files.forEach(f => {
            const tr  = document.createElement('tr');
            const sizeBytes = (f.bytes || f.size) || 0;
            const ts   = f.mtime || f.ts;
            const dt   = ts ? new Date(ts * 1000).toLocaleString() : '';

            const a = document.createElement('a');
            a.href = `/api/backups/download?rel=${encodeURIComponent(f.rel || f.name)}`;
            a.textContent = 'Download';

            tr.innerHTML = `
              <td>${escapeHtml(f.name)}</td>
              <td>${Math.round(sizeBytes/1024/1024)} MB</td>
              <td>${escapeHtml(dt)}</td>
              <td></td>
            `;
            tr.children[3].appendChild(a);
            tb.appendChild(tr);
          });

          s.appendChild(t);
        }

        // 4) hook up the two remaining actions
        qs('#backup-all').onclick = async () => {
          try{
            await fetchJSON('/api/backups/create', { method:'POST', body: JSON.stringify({}) });
            notify('Backup created');
            await loadBackups();
          }catch(e){
            notify(`Backup failed: ${e.message}`, false);
          }
        };

        qs('#restore-latest').onclick = async () => {
          try{
            if (!files[0]) return notify('No backups to restore', false);
            const latest = [...files].sort((a,b) => (b.mtime||b.ts||0) - (a.mtime||a.ts||0))[0];
            await fetchJSON('/api/backups/restore', { method:'POST', body: JSON.stringify({ name: latest.name }) });
            notify('Restored latest backup');
          }catch(e){
            notify(`Restore failed: ${e.message}`, false);
          }
        };

      }catch(e){
        notify(`Backups error: ${e.message}`, false);
      }
    }

/* ======= BEGIN LOGS MODULE ======= */
    async function loadLogs(){
      // Build the card once
      if (!state.logsInit){
        buildLogsCard();
        state.logsInit = true;
      }
      await fetchAndRenderLogs();
    }

    function buildLogsCard(){
      const sec = document.querySelector('#log');
      if (!sec) return;

      // wipe the body area, keep your header if you have one
      // if your section already has a wrapper, target its body element instead
      sec.innerHTML = '';

      const wrap = document.createElement('div');
      wrap.className = 'table-wrap';

      // header bar
      const head = document.createElement('div');
      head.className = 'table-head';
      head.innerHTML = `
        <div class="table-title">Logs</div>
        <div class="table-actions">
          <div class="chip-group" role="tablist" aria-label="Log kind">
            <button id="log-kind-bot" class="btn btn-chip" data-kind="bot">Bot</button>
            <button id="log-kind-health" class="btn btn-chip" data-kind="health">Health</button>
          </div>
          <button id="log-refresh" class="btn">Refresh</button>
          <button id="log-clear" class="btn">Clear</button>
          <a id="log-download" class="btn" href="/api/log/bot/download">Download</a>
          <input id="log-search" type="text" placeholder="Search">
        </div>
      `;
      wrap.appendChild(head);

      // table
      const body = document.createElement('div');
      body.className = 'table-scroll';
      body.innerHTML = `
        <table class="table">
          <thead>
            <tr><th style="width:120px">Time</th><th>Line</th></tr>
          </thead>
          <tbody id="log-tbody"></tbody>
        </table>
      `;
      wrap.appendChild(body);
      sec.appendChild(wrap);

      // wire controls
      head.querySelectorAll('[data-kind]').forEach(btn=>{
        btn.addEventListener('click', () => {
          state.logsKind = btn.dataset.kind;
          head.querySelectorAll('[data-kind]').forEach(b=>b.classList.remove('pill-ok'));
          btn.classList.add('pill-ok');
          const a = document.getElementById('log-download');
          if (a) a.href = `/admin/log/${state.logsKind}/download`;
          fetchAndRenderLogs();
        });
      });
      const active = head.querySelector(`#log-kind-${state.logsKind}`);
      if (active) active.classList.add('pill-ok');

      document.getElementById('log-refresh').addEventListener('click', fetchAndRenderLogs);

      document.getElementById('log-clear').addEventListener('click', async ()=>{
        try{
          await fetch(`/admin/log/${state.logsKind}/clear`, { method: 'POST' });
        }catch{}
        fetchAndRenderLogs();
      });

      document.getElementById('log-search').addEventListener('input', filterLogs);
    }

    async function fetchAndRenderLogs(){
      const tb = document.getElementById('log-tbody');
      if (!tb) return;
      try{
        const lines = await fetchLogs(state.logsKind);
        renderLogLines(lines);
        filterLogs();
      }catch(e){
        tb.innerHTML = `<tr><td colspan="2" class="muted">Failed to load logs.</td></tr>`;
      }
    }

    async function fetchLogs(kind){
      const r = await fetch(`/admin/log/${kind}`);
      const j = await r.json();
      return Array.isArray(j.lines) ? j.lines : [];
    }

    // Split a log line into [time, message] for common formats
    function splitTimeMsg(line){
      // 1) "YYYY-MM-DD HH:MM:SS,mmm rest..."
      const re1 = /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:[,\.]\d{3})?)(?:\s+|\s*\|\s*)(.*)$/;
      let m = line.match(re1);
      if (m) return [m[1], m[2]];

      // 2) ISO "YYYY-MM-DDTHH:MM:SS.mmmZ | rest"
      const re2 = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)(?:\s+|\s*\|\s*)(.*)$/;
      m = line.match(re2);
      if (m) return [m[1], m[2]];

      // 3) Fallback split on first pipe if present
      const i = line.indexOf('|');
      if (i > 0) return [line.slice(0, i).trim(), line.slice(i + 1).trim()];

      // 4) No detectable time
      return ['', line];
    }


    function renderLogLines(lines){
      const tb = document.getElementById('log-tbody');
      tb.innerHTML = '';
      if (!lines.length){
        tb.innerHTML = `<tr><td colspan="2" class="muted">No log lines yet.</td></tr>`;
        return;
      }
      for (const raw of lines){
        const [time, msg] = splitTimeMsg(raw);
        const tr = document.createElement('tr');
        tr.dataset.text = raw.toLowerCase();
        tr.innerHTML = `
          <td class="mono">${escapeHTML(time)}</td>
          <td class="mono">${escapeHTML(msg)}</td>
        `;
        tb.appendChild(tr);
      }
    }

    function filterLogs(){
      const q = (document.getElementById('log-search')?.value || '').trim().toLowerCase();
      document.querySelectorAll('#log-tbody tr').forEach(tr=>{
        const match = !q || (tr.dataset.text || '').includes(q);
        tr.style.display = match ? '' : 'none';
      });
    }

    function escapeHTML(s){
      return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
    }

// --- helpers (keep once in your file) ---
let _wcWebhookUrl = null;

async function resolveWebhook() {
  if (_wcWebhookUrl !== null) return _wcWebhookUrl;
  try {
    const cfg = await fetchJSON('/admin/config');
    _wcWebhookUrl = cfg?.DISCORD_WEBHOOK_URL || null;
  } catch {
    _wcWebhookUrl = null;
  }
  return _wcWebhookUrl;
}

async function postWebhookMessage(text){
  try{
    const url = await resolveWebhook();
    if(!url) return; // silently skip if not exposed
    await fetch(url, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ content: text }) });
  }catch{/* non-fatal */}
}

async function loadCogs(){
  try{
    let data;
    try { data = await fetchJSON('/admin/cogs'); }
    catch { data = await fetchJSON('/api/cogs'); }

    const wrap = ensureSectionCard('cogs','Cogs',[
      ['Refresh',{id:'cogs-refresh'}]
    ]);
    const scroll = wrap.querySelector('.table-scroll'); scroll.innerHTML='';

    const table = document.createElement('table'); table.className='table';
    table.innerHTML = `
      <thead>
        <tr>
          <th>Name</th>
          <th>Status</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody></tbody>`;
    const tbody = table.querySelector('tbody');
    scroll.appendChild(table);

    const rows = data?.cogs || [];

    const buildRow = async (name, loadedHint) => {
      const tr = document.createElement('tr');
      const tdN = document.createElement('td'); tdN.textContent = name;
      const tdS = document.createElement('td');
      const tdA = document.createElement('td');

      // status pill
      const pill = document.createElement('span');
      pill.className = 'pill pill-wait';
      pill.textContent = '…';
      tdS.appendChild(pill);

      const setPill = (loaded) => {
        pill.className = 'pill ' + (loaded ? 'pill-ok' : 'pill-off');
        pill.textContent = loaded ? 'Loaded' : 'Unloaded';
      };

      // resolve status (fast path: use hint if provided)
      if (typeof loadedHint === 'boolean') setPill(loadedHint);
      else {
        getCogStatus(name).then(v => {
          if (typeof v === 'boolean') setPill(v);
          else { pill.className='pill pill-off'; pill.textContent='Unknown'; }
        });
      }

        // actions
        const group = document.createElement('div');
        group.className = 'chip-group--cog';

        const mk = (label, cls, action) => {
          const b = document.createElement('button');
          b.className = `btn-cog ${cls}`;
          b.textContent = label;
          b.onclick = async () => {
            try{
              pill.className = 'pill pill-wait';
              pill.textContent = 'Applying…';
              await fetchJSON(`/admin/cogs/${encodeURIComponent(name)}/${action}`, {
                method:'POST', body: JSON.stringify({})
              });
              notify(`${action} queued for ${name}`);
              postWebhookMessage(`wc ${action} ${name}`);
              setTimeout(async () => {
                const v = await getCogStatus(name);
                if (typeof v === 'boolean') setPill(v);
                else { pill.className='pill pill-off'; pill.textContent='Unknown'; }
              }, 800);
            }catch(e){
              notify(`Cog ${action} failed: ${e.message}`, false);
              const v = await getCogStatus(name);
              if (typeof v === 'boolean') setPill(v);
              else { pill.className='pill pill-off'; pill.textContent='Unknown'; }
            }
          };
          return b;
        };

        group.appendChild(mk('reload','cog-reload','reload'));
        group.appendChild(mk('load','cog-load','load'));
        group.appendChild(mk('unload','cog-unload','unload'));
        tdA.appendChild(group);
      tr.appendChild(tdN); tr.appendChild(tdS); tr.appendChild(tdA);
      tbody.appendChild(tr);
    };

    for (const cog of rows) {
      await buildRow(cog.name || '', typeof cog.loaded === 'boolean' ? cog.loaded : undefined);
    }

    const r = document.getElementById('cogs-refresh');
    if (r) r.onclick = loadCogs;

  }catch(e){
    notify(`Cogs error: ${e.message}`, false);
  }
}


async function getCogStatus(name){
  // prefer a per-cog status endpoint; fall back to list that includes `loaded`
  try {
    const s = await fetchJSON(`/admin/cogs/${encodeURIComponent(name)}/status`);
    if (typeof s?.loaded === 'boolean') return s.loaded;
  } catch {}
  try {
    const list = await fetchJSON('/admin/cogs');
    const row = (list?.cogs || []).find(c => c.name === name);
    if (typeof row?.loaded === 'boolean') return row.loaded;
  } catch {}
  // public fallback (if exposed)
  try {
    const s = await fetchJSON(`/api/cogs/${encodeURIComponent(name)}/status`);
    if (typeof s?.loaded === 'boolean') return s.loaded;
  } catch {}
  return null; // unknown
}


  function wireBotButtons(){
    const postAdmin = (path)=>fetchJSON(`/admin/bot/${path}`,{method:'POST',body:JSON.stringify({})});
    const $restart=qs('#restart-bot'), $stop=qs('#stop-bot'), $start=qs('#start-bot');
    if($restart) $restart.onclick=async()=>{ try{ await postAdmin('restart'); notify('Restart requested'); await loadDash(); }catch(e){ notify(`Restart failed: ${e.message}`, false);} };
    if($stop) $stop.onclick=async()=>{ try{ await postAdmin('stop'); notify('Stop requested'); await loadDash(); }catch(e){ notify(`Stop failed: ${e.message}`, false);} };
    if($start) $start.onclick=async()=>{ try{ await postAdmin('start'); notify('Start requested'); await loadDash(); }catch(e){ notify(`Start failed: ${e.message}`, false);} };
  }

  async function routePage(){
    switch(state.currentPage){
      case 'dashboard': await loadDash(); break;
      case 'bets': await loadAndRenderBets(); break;
      case 'ownership': await loadOwnershipPage(); break;
      case 'splits': if(state.admin) await loadSplits(); else setPage('dashboard'); break;
      case 'backups': if(state.admin) await loadBackups(); else setPage('dashboard'); break;
      case 'log': if(state.admin) await loadLogs('bot'); else setPage('dashboard'); break;
      case 'cogs': if(state.admin) await loadCogs(); else setPage('dashboard'); break;
    }
  }

  function startPolling(){
    stopPolling();
    state.pollingId = setInterval(async ()=>{
      if(state.currentPage==='dashboard') await loadDash();
    }, 5000);
  }
  function stopPolling(){ if(state.pollingId) clearInterval(state.pollingId); state.pollingId=null; }

  async function init(){
    try{ const s = await fetchJSON('/admin/auth/status'); setAdminMode(!!(s && s.unlocked)); }catch{ setAdminMode(false); }
    setTheme(state.theme);
    wireTheme(); wireAuth(); wireNav(); wireBotButtons();
    setPage(state.currentPage);
    await routePage();
    startPolling();
  }
  window.addEventListener('load', init);
})();

/* =========================
   WORLD MAP - interactive SVG
   ========================= */
(function(){
  const host = document.getElementById('map-svg-host');
  const tip  = document.getElementById('map-tip');
  const btnRefresh = document.getElementById('worldmap-refresh');

  const CACHE_TTL_MS = 60*1000; // 60s cache

  function now(){ return Date.now(); }
  function getCache(key){
    try{
      const blob = JSON.parse(localStorage.getItem(key) || 'null');
      if(!blob) return null;
      if((now() - (blob.ts||0)) > CACHE_TTL_MS) return null;
      return blob.data;
    }catch(e){ return null; }
  }
  function setCache(key, data){
    try{ localStorage.setItem(key, JSON.stringify({ts: now(), data})); }catch(e){}
  }

async function fetchJSON(url){
  try{
    const r = await fetch(url, {cache:'no-store'});
    if(!r.ok){
      let body = '';
      try { body = await r.text(); } catch(_){}
      const err = new Error(`HTTP ${r.status} @ ${url}${body ? ` — ${body.slice(0,200)}` : ''}`);
      err.status = r.status;
      err.url = url;
      throw err;
    }
    return await r.json();
  }catch(e){
    console.error('fetchJSON failed:', e);
    throw e;
  }
}


  async function loadTeamIso(){
    const CK = 'wc:team_iso';
    const cached = getCache(CK);
    if(cached) return cached;
    const data = await fetchJSON('/api/team_iso');
    setCache(CK, data);
    return data;
  }
  async function loadOwnership(){
    const CK = 'wc:ownership_merged';
    const cached = getCache(CK);
    if(cached) return cached;
    const data = await fetchJSON('/api/ownership_merged');
    setCache(CK, data);
    return data;
  }


    async function inlineSVG(path){
      const txt = await fetch(path, {cache:'no-store'}).then(r=>{
        if(!r.ok) throw new Error('map svg not found');
        return r.text();
      });
      host.innerHTML = txt;
      const svg = host.querySelector('svg');

      // Tag only real country shapes whose id is ISO-2 or "iso-xx"
      const nodes = svg.querySelectorAll('path[id], polygon[id], rect[id], g[id], [data-iso]');
      let tagged = 0;
      nodes.forEach(el=>{
        const raw = (el.getAttribute('data-iso') || el.id || '').trim();
        if(!raw) return;
        let iso = '';
        const m1 = raw.match(/^[A-Za-z]{2}$/);            // GB
        const m2 = raw.match(/^iso[-_ ]?([A-Za-z]{2})$/); // iso-GB
        if(m1) iso = m1[0].toLowerCase();
        else if(m2) iso = m2[1].toLowerCase();
        else return;

        el.classList.add('country','free');
        el.setAttribute('data-iso', iso);
        el.setAttribute('tabindex','0');
        el.setAttribute('role','button');
        el.setAttribute('aria-label', iso.toUpperCase());
        tagged++;
      });
      console.debug('world.svg tagged countries:', tagged);

      // Ensure a dedicated pan root that won't clobber existing transforms
      ensurePanRoot(svg);
      return svg;
    }

  function classifyCountries(svg, teamIso, merged){
    const rows = (merged && merged.rows) || [];
    // build: teamName -> {status, main, splits}
    const teamState = {};
    for(const row of rows){
      const team = row.country;
      const ownersCount = row.owners_count || 0;
      const main = row.main_owner;
      const splits = row.split_with || [];
      let status = 'free';
      if(ownersCount > 0 && (!splits || splits.length === 0)) status = 'owned';
      if(splits && splits.length > 0) status = 'split';
      teamState[team] = {status, main, splits};
    }

    // invert team_iso to iso->team
    const isoToTeam = {};
    Object.keys(teamIso||{}).forEach(team=>{
      const iso = (teamIso[team]||'').toLowerCase();
      if(iso) isoToTeam[iso] = team;
    });

    svg.querySelectorAll('.country').forEach(el=>{
      const iso = (el.getAttribute('data-iso')||'').toLowerCase();
      const team = isoToTeam[iso];
      el.classList.remove('owned','split','free');
      let status = 'free';
      let ownerNames = [];
      const teamLabel = team || iso.toUpperCase();

      if(team && teamState[team]){
        status = teamState[team].status;
        const main = teamState[team].main;
        const splits = teamState[team].splits || [];
        if(main && main.username){
          ownerNames.push(main.username);
        }
        if(splits && splits.length){
          ownerNames.push(...splits.map(s => s.username).filter(Boolean));
        }
      }
      el.classList.add(status);

      // tooltip
      el.onmouseenter = (ev)=>{
        const ownersText = ownerNames.length ? ownerNames.join(', ') : 'Unassigned';
        tip.innerHTML = `<strong>${teamLabel}</strong><br><em>${iso.toUpperCase()}</em><br>${ownersText}`;
        tip.style.opacity = '1';
        const r = host.getBoundingClientRect();
        tip.style.left = (ev.clientX - r.left + 12)+'px';
        tip.style.top  = (ev.clientY - r.top  + 12)+'px';
      };
      el.onmousemove = (ev)=>{
        const r = host.getBoundingClientRect();
        tip.style.left = (ev.clientX - r.left + 12)+'px';
        tip.style.top  = (ev.clientY - r.top  + 12)+'px';
      };
      el.onmouseleave = ()=>{ tip.style.opacity = '0'; };
      el.onfocus = el.onmouseenter;
      el.onblur  = el.onmouseleave;
    });
  }

    function ensurePanRoot(svg){
      if(svg.querySelector('#wc-panroot')) return svg.querySelector('#wc-panroot');
      const panRoot = document.createElementNS('http://www.w3.org/2000/svg','g');
      panRoot.setAttribute('id','wc-panroot');

      // move all visible graphics into panRoot, keep <defs> and <title>/<desc> at top
      const keep = new Set(['defs','title','desc','metadata']);
      const toMove = [];
      [...svg.childNodes].forEach(n=>{
        if(n.nodeType === 1 && keep.has(n.nodeName.toLowerCase())) return;
        toMove.push(n);
      });
      toMove.forEach(n=>panRoot.appendChild(n));
      svg.appendChild(panRoot);
      return panRoot;
    }


    function enablePanZoom(svg){
      const panRoot = ensurePanRoot(svg);
      const baseTransform = panRoot.getAttribute('transform') || ''; // preserve original
      let scale = 1, min=0.7, max=5;
      let originX=0, originY=0, startX=0, startY=0, panning=false;

      function apply(){
        // keep original transform, add our translate/scale afterwards
        panRoot.setAttribute('transform', `${baseTransform} translate(${originX},${originY}) scale(${scale})`.trim());
      }

      svg.classList.add('map-pannable');

      svg.addEventListener('wheel', (e)=>{
        e.preventDefault();
        const delta = Math.sign(e.deltaY);
        const factor = 1 - (delta * 0.08);
        const newScale = Math.min(max, Math.max(min, scale * factor));
        if(newScale === scale) return;

        // zoom towards cursor
        const pt = svg.createSVGPoint();
        pt.x = e.offsetX; pt.y = e.offsetY;
        try {
          const ctm = svg.getScreenCTM().inverse();
          const cursor = pt.matrixTransform(ctm);
          originX = cursor.x - (cursor.x - originX) * (newScale/scale);
          originY = cursor.y - (cursor.y - originY) * (newScale/scale);
        } catch(_){}

        scale = newScale;
        apply();
      }, {passive:false});

      svg.addEventListener('mousedown', (e)=>{
        panning = true; startX = e.clientX; startY = e.clientY; svg.classList.add('grabbing');
      });
      window.addEventListener('mousemove', (e)=>{
        if(!panning) return;
        originX += (e.clientX - startX)/scale;
        originY += (e.clientY - startY)/scale;
        startX = e.clientX; startY = e.clientY;
        apply();
      });
      window.addEventListener('mouseup', ()=>{ panning=false; svg.classList.remove('grabbing'); });

      apply();
    }

    async function render(){
      try{
        console.time('worldmap:fetch');
        // Fetch separately so the console shows exactly which one fails
        const iso = await loadTeamIso();               // /api/team_iso
        console.debug('team_iso ok:', Object.keys(iso).length, 'entries');
        const merged = await loadOwnership();          // /api/ownership_merged
        console.debug('ownership_merged ok:', (merged?.rows?.length||0), 'rows');
        console.timeEnd('worldmap:fetch');

        const svg = await inlineSVG('world.svg');      // local file beside index.html
        classifyCountries(svg, iso, merged);
        enablePanZoom(svg);
      }catch(e){
        console.error('Map render error:', e);
        host.innerHTML = `
          <div class="muted" style="padding:10px;">
            Failed to load map data.<br>
            <small>${(e && e.message) ? e.message : e}</small>
          </div>`;
      }
    }


  if(btnRefresh){
    btnRefresh.addEventListener('click', ()=>{
      // bust ownership cache only
      localStorage.removeItem('wc:ownership_merged');
      render();
    });
  }

  // Render when navigating to the World Map tab
  const menu = document.getElementById('main-menu');
  if(menu){
    menu.addEventListener('click', (e)=>{
      const a = e.target.closest('a[data-page]');
      if(!a) return;
      if(a.getAttribute('data-page') === 'worldmap'){
        setTimeout(render, 10);
      }
    });
  }
  // Or render immediately if the section is already visible on load
  if(document.querySelector('#worldmap.active-section')){
    render();
  }
})();
