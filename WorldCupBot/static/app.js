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
  const $backdrop = qs('#auth-backdrop');
  const $btnCancel = qs('#auth-cancel');
  const $btnSubmit = qs('#auth-submit');
  const $themeToggle = qs('#theme-toggle');
  const $themeIcon = qs('#theme-icon');
  const STAGE_OPTIONS = [
  "Eliminated",
  "Group Stage",
  "Round of 32",
  "Round of 16",
  "Quarter Final",
  "Semi Final",
  "Final",
  "Winner"
];

// === Global Admin View toggle (persists) ===
const ADMIN_VIEW_KEY = 'wc:adminView';
const getAdminView = () => localStorage.getItem(ADMIN_VIEW_KEY) === '1';
function setAdminView(on){
  localStorage.setItem(ADMIN_VIEW_KEY, on ? '1' : '0');
  document.body.classList.toggle('admin-view', !!on);
  applyAdminView();
}

// admin UI = (admin session unlocked) AND (admin view enabled)
function isAdminUI(){ return !!(state.admin && getAdminView()); }

function applyAdminView(){
  const enabled = isAdminUI();
  // show/hide all admin-only bits
  document.querySelectorAll('.admin-only,[data-admin]').forEach(el=>{
    el.style.display = enabled ? '' : 'none';
  });
  // keep a class for CSS if you want it
  document.body.classList.toggle('user-admin-view', enabled);
}

function ensureAdminToggleButton(){
  document.querySelectorAll('.admin-toggle, #admin-toggle-btn').forEach(el => el.remove());
  if (document.getElementById('user-admin-toggle')) return;

  const btn = document.createElement('button');
  btn.id = 'user-admin-toggle';
  btn.className = 'fab-admin';
  btn.type = 'button';
  btn.textContent = getAdminView() ? 'Public View' : 'Admin View';
  btn.onclick = () => {
    const next = !getAdminView();
    setAdminView(next);
    btn.textContent = next ? 'Public View' : 'Admin View';
    routePage();
  };
  document.body.appendChild(btn);
}


// keep views in sync if localStorage changes (other tab / module)
window.addEventListener('storage', (e)=>{
  if (e.key === ADMIN_VIEW_KEY) { applyAdminView(); routePage(); }
});



function normalizeStage(label){
  const s = String(label || '').trim();
  const map = {
    "Group":"Group Stage",
    "R32":"Round of 32",
    "R16":"Round of 16",
    "QF":"Quarter Final",
    "SF":"Semi Final",
    "F":"Final"
  };
  return map[s] || s;
}

function stagePill(stage){
  const s = stage || 'Group';
  const cls = (s === 'Winner') ? 'pill-ok'
            : (s === 'Eliminated') ? 'pill-off'
            : 'pill';
  return `<span class="${cls}">${s}</span>`;
}

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
  function wireTheme(){ $themeToggle.addEventListener('click', ()=>setTheme(state.theme==='light'?'dark':'light'));
  }

  // === PAGE SWITCHER ===
    function showPage(page) {
      // admin-only pages
      const adminPages = new Set(['splits','backups','log','cogs']);

      // block admin pages when not logged in
      if (adminPages.has(page) && !isAdminUI()) {
        notify('That page requires admin login.', false);
        return;
      }

      // show the chosen section
      document.querySelectorAll('section.page-section').forEach(s => s.classList.remove('active-section'));
      const sec = document.getElementById(page);
      if (sec) sec.classList.add('active-section');

      // load data for that page
      if (page === 'dashboard') loadDashboard().catch(()=>{});
      if (page === 'ownership') loadOwnership().catch(()=>{});
      if (page === 'bets') loadBets().catch(()=>{});
      if (page === 'log' && state.admin) loadLogs().catch(()=>{});
      if (page === 'cogs' && state.admin) loadCogs().catch(()=>{});
      if (page === 'backups' && state.admin) loadBackups().catch(()=>{});
      if (page === 'splits' && state.admin) loadSplits().catch(()=>{});
    }

function setPage(p) {
  const adminPages = new Set(['splits','backups','log','cogs']);
  if (adminPages.has(p) && !isAdminUI()) {
    notify('That page requires admin login.', false);
    p = 'dashboard';
  }

  // remember
  state.currentPage = p;
  localStorage.setItem('wc:lastPage', p);

  // nav highlight
  document.querySelectorAll('#main-menu a').forEach(a => {
    a.classList.toggle('active', a.dataset.page === p);
  });

  // show one section
  document.querySelectorAll('section.page-section, section.dashboard')
    .forEach(s => s.classList.remove('active-section'));
  document.getElementById(p)?.classList.add('active-section');
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

    function setAdminUI(unlocked){
      state.admin = !!unlocked;
      document.body.classList.toggle('admin', state.admin);
      applyAdminView();
      }

    function setUserUI(user){
      const loggedIn = !!(user && (user.discord_id || user.id));
      const fabIcon = document.getElementById('fab-icon');
      const btnLogin = document.getElementById('btn-discord-login');
      const btnLogout = document.getElementById('btn-discord-logout');

      if (btnLogin)  btnLogin.style.display  = loggedIn ? 'none' : '';
      if (btnLogout) btnLogout.style.display = loggedIn ? '' : 'none';
    }

    async function refreshAuth(){
      try{
        const r = await fetch('/admin/auth/status', { credentials:'include' });
        if(r.ok){
          const j = await r.json();
          setAdminUI(!!j.unlocked);
          setUserUI(j.user || null);
          return;
        }
      }catch(_){}
      try{
        const m = await fetch('/api/me', { credentials:'include' });
        if(m.ok){
          const j = await m.json();
          setAdminUI(false);
          setUserUI(j.user || null);
          return;
        }
      }catch(_){}
      setAdminUI(false);
      setUserUI(null);
    }

    function wireAuthButtons(){
      const fab = document.getElementById('fab-auth');
      const btnLogin = document.getElementById('btn-discord-login');
      const btnLogout = document.getElementById('btn-discord-logout');

      if(btnLogin){
        btnLogin.addEventListener('click', () => window.location.href = '/auth/discord/login');
      }
      if(btnLogout){
        btnLogout.addEventListener('click', async () => {
          try{ await fetch('/auth/discord/logout', { method:'POST' }); }catch(_){}
          location.reload();
        });
      }
    }


    // === AUTH BOOTSTRAP ===
    async function initAuth() {
      try {
        const r = await fetch('/admin/auth/status', { credentials: 'same-origin' });
        const j = await r.json().catch(() => ({}));
        state.admin = !!j.unlocked;
      } catch (_) {
        state.admin = false;
      }
      document.body.classList.toggle('admin', state.admin);
      return state.admin;
    }

    // keep session in sync after refresh
    document.addEventListener('DOMContentLoaded', initAuth);

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
    document.addEventListener('DOMContentLoaded', initAuth);


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
      const sysP = isAdminUI() ? fetchJSON('/api/system') : Promise.resolve(null);
      const [up, ping, sys] = await Promise.all([upP, pingP, sysP]);
      const latency = Math.max(0, Math.round(performance.now() - t0));

      const running = (up && typeof up.bot_running === 'boolean')
        ? up.bot_running
        : !!(sys && sys.bot && typeof sys.bot.running === 'boolean' && sys.bot.running);

      renderUptime(up, running);
      renderPing(ping, latency);
      if(isAdminUI() && sys) renderSystem(sys); else clearSystem();

      // Bot Actions (admin only). Buttons are not admin-gated, so JS fully controls them
      const $actions = qs('#bot-actions');
      const $start = qs('#start-bot');
      const $stop = qs('#stop-bot');
      const $restart = qs('#restart-bot');
      if(isAdminUI() && $actions && $start && $stop && $restart){
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
      const tbody = document.querySelector('#ownership-tbody');
      if (!tbody) return;
      tbody.innerHTML = '';

      list.forEach(function (row) {
        const tr = document.createElement('tr');
        tr.className = row.main_owner ? 'row-assigned' : 'row-unassigned';

        // Owner cell
        const idVal = row.main_owner ? row.main_owner.id : '';
        const label = (row.main_owner && (row.main_owner.username || row.main_owner.id)) || '';
        const showId = !!(window.adminUnlocked && idVal && label !== idVal);
        const ownerCell = row.main_owner
          ? `<span class="owner-name" title="${idVal}">${label}</span>${showId ? ' <span class="muted">(' + idVal + ')</span>' : ''}`
          : 'Unassigned <span class="warn-icon" title="No owner">⚠️</span>';

        // Split cell
        const splitStr = (row.split_with && row.split_with.length)
          ? row.split_with.map(s => s.username || s.id).join(', ')
          : '—';

        // Stage cell
        const current = (ownershipState.stages && ownershipState.stages[row.country]) || 'Group';
        let stageCell = '';
        if (isAdminUI()) {
          // editable select for admins
          const opts = STAGE_OPTIONS.map(v =>
            `<option value="${v}" ${v===current?'selected':''}>${v}</option>`
          ).join('');
          stageCell = `
            <select class="stage-select" data-team="${row.country}">
              ${opts}
            </select>
          `;
        } else {
          // read-only pill for public
          stageCell = stagePill(current);
        }

        tr.innerHTML = `
          <td>${flagHTML(row.country)} <span class="country-name">${row.country}</span></td>
          <td>${ownerCell}</td>
          <td>${splitStr}</td>
          <td>${stageCell}</td>
          <td class="admin-col" data-admin="true">
            <button class="btn btn-outline xs reassign-btn" data-team="${row.country}">Reassign</button>
          </td>
        `;

        tbody.appendChild(tr);
      });

    document.querySelectorAll('.admin-col,[data-admin]').forEach(el => {
      el.style.display = isAdminUI() ? '' : 'none';
    });

    const tbl = tbody.closest('table');
    if (tbl) {
      const headAdmin = tbl.querySelector('thead th.admin-col, thead th[data-admin]');
      if (headAdmin) headAdmin.style.display = isAdminUI() ? '' : 'none';
    }

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

    // 5) Load current stages map
    let stages = {};
    try {
      // admin route returns { ok, stages: { Team: Stage } }
      if (isAdminUI()) {
        const r = await fetch('/admin/teams/stage', { credentials: 'include' });
        if (r.ok) {
          const j = await r.json();
          stages = (j && j.stages) || {};
        }
      } else {
        // public route returns { Team: Stage }
        const r = await fetch('/api/team_stage', { credentials: 'include' });        if (r.ok) stages = await r.json();
      }
    } catch { stages = {}; }
    ownershipState.stages = stages || {};

    // 6) Render
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

document.addEventListener('click', async (ev) => {
  const btn = ev.target.closest('.reassign-btn');
  if (!btn) return;

  // Always sync admin status before gating UI
  try {
    const s = await fetch('/admin/auth/status', { credentials: 'include' }).then(r => r.json());
    const isAdmin = !!(s && s.unlocked);
    state.admin = isAdmin;
    document.body.classList.toggle('admin', isAdmin);
  } catch (_) {
    state.admin = false;
    document.body.classList.remove('admin');
  }

  if (!state.admin) {
    notify('Admin required', false);
    return;
  }

  // Open the modal
  const team = btn.getAttribute('data-team') || btn.dataset.team || '';
  openReassignModal(team.trim());
});

document.addEventListener('change', async (e) => {
  const sel = e.target.closest && e.target.closest('.stage-select');
  if (!sel) return;
  if (!isAdminUI()) return notify('Admin required', false);

  const team  = sel.getAttribute('data-team') || '';
  const stage = sel.value || 'Group';
  if (!team) return;

  try {
    console.log('Stage updated, refreshing User page...');
    const r = await fetch('/admin/teams/stage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ team, stage })
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.ok === false) throw new Error(j.error || 'save failed');

    ownershipState.stages = ownershipState.stages || {};
    ownershipState.stages[team] = stage;
    notify(`Stage updated: ${team} → ${stage}`, true);

    if (location.hash === '#user' || state.currentPage === 'user') {
      try { await refreshUser(); } catch (_) {}
    }

  } catch (err) {
    notify(`Failed to update stage: ${err.message || err}`, false);
    const prev = (ownershipState.stages && ownershipState.stages[team]) || 'Group Stage';
    sel.value = prev;
  }
});

    function openReassignModal(teamName) {
      const backdrop = document.getElementById('reassign-backdrop');
      const modal    = document.getElementById('reassign-modal');
      const inputT   = document.getElementById('reassign-team');
      const inputId  = document.getElementById('reassign-id');
      const picker   = document.getElementById('reassign-picker');
      const listbox  = document.getElementById('reassign-options');

      if (!backdrop || !modal) return;

      // never show a toast here — the gate lives in the click handler
      inputT.value = teamName || '';

      // populate verified users for the picker (best-effort)
      (async () => {
        try {
          const users = await fetchJSON('/api/verified'); // public route
          listbox.innerHTML = '';
          (users || []).forEach(u => {
            const li = document.createElement('li');
            li.role = 'option';
            li.tabIndex = -1;
            li.textContent = (u.display_name || u.username || u.discord_id || '').trim();
            li.dataset.id = String(u.discord_id || '').trim();
            li.addEventListener('click', () => {
              picker.textContent = li.textContent;
              picker.dataset.id = li.dataset.id;
              listbox.hidden = true;
            });
            listbox.appendChild(li);
          });
          picker.onclick = () => { listbox.hidden = !listbox.hidden; };
          document.addEventListener('click', (e) => {
            if (!picker.contains(e.target) && !listbox.contains(e.target)) listbox.hidden = true;
          }, { once: true });
        } catch (_) {}
      })();

      backdrop.style.display = 'flex';
      modal.focus();
    }

document.getElementById('reassign-cancel')?.addEventListener('click', () => {
  document.getElementById('reassign-backdrop').style.display = 'none';
});

document.getElementById('reassign-close')?.addEventListener('click', () => {
  document.getElementById('reassign-backdrop').style.display = 'none';
});

document.getElementById('reassign-submit')?.addEventListener('click', async () => {
  const team = (document.getElementById('reassign-team')?.value || '').trim();
  const pickedId = (document.getElementById('reassign-picker')?.dataset.id || '').trim();
  const typedId  = (document.getElementById('reassign-id')?.value || '').trim();
  const newOwner = pickedId || typedId;

  if (!team || !newOwner) return notify('Team and new owner required', false);

  try {
    const res = await fetch('/admin/ownership/reassign', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ team, new_owner_id: newOwner })
    });

    if (res.status === 401) {
      state.admin = false;
      document.body.classList.remove('admin');
      notify('Admin required', false);
      return; // do not keep the modal open pretending it worked
    }

    const data = await res.json();
    if (!data.ok) {
      notify(data.error || 'Failed to reassign', false);
      return;
    }

    // success: close modal, toast, and refresh the row if you keep a table renderer
    document.getElementById('reassign-backdrop').style.display = 'none';
    notify('Team reassigned', true);

    try { await refreshOwnershipOnce?.(data.row); } catch (_) {}
  } catch (e) {
    notify('Failed to reassign', false);
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
      const showAdmin = (typeof isAdminUI === 'function')
      ? isAdminUI()
      : (window.state && state.admin === true);
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

          if (showAdmin) {
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
state.splitsBuilt = false;

// entry point called by router
async function loadSplits(){
  if (!state.admin) { notify('Admin required', false); return; }
  try {
    if (!state.splitsBuilt) buildSplitsShell();

    // GET pending requests
    const data = await fetchJSON('/admin/splits'); // { pending:[...] } or []
    const pending = Array.isArray(data) ? data : (data.pending || []);
    renderPendingSplits(pending);

    // load history below
    await loadSplitHistoryOnce();
  } catch(e){
    notify(`Splits error: ${e.message || e}`, false);
  }
}
window.loadSplits = loadSplits;

// build two stacked cards inside #splits
function buildSplitsShell(){
  const sec = document.getElementById('splits');
  if (!sec) return;

  sec.innerHTML = `
    <div class="table-wrap" id="splits-requests-card">
      <div class="table-head">
        <div class="table-title">Split Requests</div>
        <div class="table-actions">
          <button id="splits-refresh" class="btn">Refresh</button>
        </div>
      </div>
      <div class="table-scroll" id="splits-pending-body">
        <div class="split-empty">Loading…</div>
      </div>
    </div>

    <div class="table-wrap" id="splits-history-card" style="margin-top:16px">
      <div class="table-head">
        <div class="table-title">
          History
        </div>
        <div class="table-actions">
          <button id="splits-history-refresh" class="btn">Refresh</button>
        </div>
      </div>
      <div class="table-scroll" id="split-history-body">
        <div class="split-empty">Loading…</div>
      </div>
    </div>
  `;

  // wire refresh buttons
  const btnReq = document.getElementById('splits-refresh');
  if (btnReq && !btnReq._wired) {
    btnReq._wired = true;
    btnReq.addEventListener('click', loadSplits);
  }
  const btnHist = document.getElementById('splits-history-refresh');
  if (btnHist && !btnHist._wired) {
    btnHist._wired = true;
    btnHist.addEventListener('click', loadSplitHistoryOnce);
  }

  state.splitsBuilt = true;
}

// short utilities
function escapeHTML(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function fmtDateTime(x) {
  let t = x;
  if (typeof t === 'string' && /^\d+(\.\d+)?$/.test(t)) t = Number(t);
  if (typeof t === 'number' && t < 1e12) t = t * 1000; // seconds -> ms
  const d = new Date(t);
  if (Number.isNaN(d.getTime())) return '-';
  const pad = n => String(n).padStart(2,'0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
function shortId(id) {
  if (!id) return '-';
  const str = String(id);
  let hash = 0;
  for (let i = 0; i < str.length; i++) hash = (hash * 31 + str.charCodeAt(i)) >>> 0;
  return '#' + (hash % 90000 + 10000); // 5 digits
}
function splitStatusPill(status) {
  const map = { pending:'pill-warn', approved:'pill-ok', accepted:'pill-ok', resolved:'pill-ok', denied:'pill-off', rejected:'pill-off' };
  const cls = map[status] || 'pill-off';
  const label = status ? status[0].toUpperCase() + status.slice(1) : 'Unknown';
  return `<span class="pill ${cls}">${label}</span>`;
}

/* Requests table */
function renderPendingSplits(rows){
  const body = document.getElementById('splits-pending-body');
  if (!body) return;
  body.innerHTML = '';

  if (!Array.isArray(rows) || rows.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'split-empty';
    empty.textContent = 'No pending split requests.';
    body.appendChild(empty);
    return;
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
    const ta = +new Date(a?.expires_at || a?.timestamp || 0);
    const tb = +new Date(b?.expires_at || b?.timestamp || 0);
    return tb - ta;
  });

  for (const r of sorted) {
    const realId = r.id ?? '-';
    const idShort = shortId(realId);
    const team = r.team ?? '-';
    const from = r.from_username ?? r.requester_id ?? '-';
    const to = r.to_username ?? r.main_owner_id ?? '-';
    const when = r.expires_at ?? r.timestamp ?? null;

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
              <button type="button" class="btn-split split-accept"  data-action="accept"  data-id="${escapeHTML(realId)}">Accept</button>
              <button type="button" class="btn-split split-decline" data-action="decline" data-id="${escapeHTML(realId)}">Decline</button>
            </div>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  }

  // interaction
  function collapseAll() {
    table.querySelectorAll('.action-cell').forEach(cell => {
      cell.querySelector('.pill-click')?.classList.remove('hidden');
      cell.querySelector('.chip-group--split')?.classList.add('hidden');
    });
  }
    // interaction (delegated so it survives re-renders)
    table.addEventListener('click', async (e) => {
      // expand pill
      const pill = e.target.closest('.pill-click');
      if (pill) {
        const cell = pill.closest('.action-cell');
        const chips = cell.querySelector('.chip-group--split');
        table.querySelectorAll('.action-cell').forEach(c => {
          c.querySelector('.pill-click')?.classList.remove('hidden');
          c.querySelector('.chip-group--split')?.classList.add('hidden');
        });
        pill.classList.add('hidden');
        chips.classList.remove('hidden');
        return;
      }

      // accept/decline chip
      const chip = e.target.closest('.btn-split[data-action][data-id]');
      if (!chip) return;

      const action = chip.getAttribute('data-action'); // accept | decline
      const sid = chip.getAttribute('data-id');        // real split id
      const row = chip.closest('tr');
      row.querySelectorAll('.btn-split').forEach(b => b.disabled = true);

      try {
        const res = await submitSplitAction(action, sid); // unified helper below
        if (!res || res.ok === false) throw new Error(res?.error || 'unknown error');

        // success path
        row.remove();
        if (!tbody.children.length) {
          body.innerHTML = '<div class="split-empty">No pending split requests.</div>';
        }
        // refresh both panels so UI is in sync with files
        await loadSplits();
        await loadSplitHistoryOnce();
        try { await loadOwnership(); } catch(_) {}
        notify(`Split ${action}ed`, true);
      } catch (err) {
        notify(`Failed to ${action} split: ${err.message || err}`, false);
        row.querySelectorAll('.btn-split').forEach(b => b.disabled = false);
      }
    });

  document.addEventListener('click', (ev) => {
    if (!table.contains(ev.target)) collapseAll();
  }, { once: true });

  body.appendChild(table);
}

async function submitSplitAction(action, requestId) {
  const url = action === 'accept'
    ? '/admin/splits/accept'
    : '/admin/splits/decline';

  const res = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: requestId })
  });
  return await res.json();
}

/* History table */
async function loadSplitHistoryOnce() {
  if (!state.admin) return;
  const body = document.getElementById('split-history-body');
  const countEl = document.getElementById('split-hist-count');
  if (!body) return;

  try {
    const { events = [] } = await fetchJSON('/admin/splits/history?limit=200');

    countEl && (countEl.textContent = events.length);

    if (!events.length) {
      body.innerHTML = `<div class="split-empty">No history recorded yet.</div>`;
      return;
    }

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
      const id = ev.id ?? ev.request_id ?? '';
      const team = ev.team || ev.country || ev.country_name || '-';
      const fromUser = ev.from_username || ev.requester_username || ev.from || ev.requester_id || '-';
      const toUser = ev.to_username || ev.receiver_username || ev.to || ev.main_owner_id || '-';
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
    notify(`History refresh failed: ${e.message || e}`, false);
  }
}

window.loadSplits = loadSplits;
window.loadSplitHistoryOnce = loadSplitHistoryOnce;


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
            a.className = 'download-link';
            a.innerHTML = `<span class="file-name">${escapeHtml(f.name)}</span>`;

            tr.innerHTML = `
              <td>${a.outerHTML}</td>
              <td>${Math.round(sizeBytes/1024/1024)} MB</td>
              <td>${escapeHtml(dt)}</td>
              <td><a href="${a.href}" class="download-link">Download</a></td>
            `;
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
          <th class="admin-col" data-admin="true">Action</th>
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
      case 'fanzone': await loadFanZone(); break;
      case 'fanpolls': if(isAdminUI()) await loadAdminPolls(); else setPage('dashboard'); break;
      case 'ownership': await loadOwnershipPage(); break;
      case 'splits': if(isAdminUI()) await loadSplits(); else setPage('dashboard'); break;
      case 'backups': if(isAdminUI()) await loadBackups(); else setPage('dashboard'); break;
      case 'log': if(isAdminUI()) await loadLogs('bot'); else setPage('dashboard'); break;
      case 'cogs': if(isAdminUI()) await loadCogs(); else setPage('dashboard'); break;
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
      await refreshAuth();
      ensureAdminToggleButton();
      applyAdminView();
      setTheme(state.theme);
      wireTheme();
      wireAuthButtons();
      wireNav();
      wireBotButtons();
      setPage(state.currentPage);
      await routePage();
      startPolling();
    }
  window.addEventListener('load', init);

// ===== Fan Zone utilities =====
async function fetchJSON(url, opts){
  const r = await fetch(url, opts);
  if(!r.ok) throw new Error(await r.text().catch(()=>r.statusText));
  return r.json();
}

function clamp(n){ return Math.max(0, Math.min(100, Number.isFinite(n)?n:0)); }

function fanBarsApply(card, percents) {
  const rows = card.querySelectorAll('.poll-bar');
  rows.forEach(row => {
    const oid = row.dataset.oid;
    const target = clamp(percents[oid] || 0);
    const bar = row.querySelector('.pb-fill');
    const label = row.querySelector('.pb-pct');

    let w = parseFloat(bar.style.width || '0') || 0;
    const step = () => {
      const d = target - w;
      if (Math.abs(d) < 0.3) {
        w = target;
      } else {
        w += d * 0.12;
        requestAnimationFrame(step);
      }
      bar.style.width = w.toFixed(1) + '%';
      label.textContent = w.toFixed(1) + '%';
    };
    requestAnimationFrame(step);
  });
}

async function fetchFanStats(pollId) {
  const d = await fetchJSON(`/api/fan_votes/${encodeURIComponent(pollId)}`);
  return { counts: d.counts || {}, perc: d.percent || {}, total: d.total || 0 };
}

async function submitFanVote(pollId, optionId) {
  return fetchJSON('/api/fan_votes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ poll_id: pollId, option_id: optionId })
  });
}

function pollCardHTML(p) {
  const opts = (p.options || []).map(o => `
    <div class="fan-option">
      <div class="fan-name">${o.label}</div>
      <button class="btn fz-vote" data-poll="${p.id}" data-opt="${o.id}">Vote</button>
    </div>
  `).join('');

  const bars = (p.options || []).map(o => `
    <div class="poll-bar" data-oid="${o.id}">
      <div class="pb-track"><div class="pb-fill" style="width:0%"></div></div>
      <div class="pb-meta"><span class="pb-label">${o.label}</span><span class="pb-pct">0.0%</span></div>
    </div>
  `).join('');

  return `
    <div class="fan-card" data-poll="${p.id}">
      <div class="fan-head">
        <div class="fan-title">${p.title}</div>
        <div class="fan-meta"><span class="pill ${p.status === 'open' ? 'pill-ok' : 'pill-off'}">${p.status}</span></div>
      </div>

      <div class="fan-options">${opts}</div>

      <div class="fan-bars" style="margin-top:12px">${bars}</div>

      <div class="fan-foot">
        <span class="fz-total" data-poll="${p.id}">Total votes: 0</span>
      </div>
    </div>
  `;
}

// --- Fan Zone dialog helpers ---
function fzDialogOpen(msg, pollId = null) {
  const wrap = document.getElementById('fz-dialog');
  if (!wrap) return window.alert(msg);
  const msgEl = document.getElementById('fz-dialog-msg');
  msgEl.textContent = msg;

  wrap.dataset.poll = pollId || '';
  wrap.classList.remove('hidden');
  document.body.classList.add('modal-open');
  document.body.style.overflow = 'hidden';

  const close = () => fzDialogClose();

  document.getElementById('fz-dialog-ok')?.addEventListener('click', close, { once: true });
  document.getElementById('fz-dialog-close')?.addEventListener('click', close, { once: true });
  wrap.querySelector('.wc-modal-backdrop')?.addEventListener('click', close, { once: true });

  const remBtn = document.getElementById('fz-dialog-remove');
  if (remBtn) {
    remBtn.onclick = async () => {
      const pollId = wrap.dataset.poll;
      if (!pollId) return fzDialogClose();
      try {
        const res = await fetch('/api/fan_votes/remove', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ poll_id: pollId })
        });
        if (!res.ok) throw new Error(await res.text());
        await res.json();
        fzDialogClose();
        if (typeof notify === 'function') notify('Vote removed', true);
        renderFanZone();
      } catch (_) {
        fzDialogClose();
        if (typeof notify === 'function') notify('Failed to remove vote', false);
      }
    };
  }

  wrap._esc = (e) => { if (e.key === 'Escape') close(); };
  document.addEventListener('keydown', wrap._esc);
}

function fzDialogClose() {
  const wrap = document.getElementById('fz-dialog');
  if (!wrap) return;
  wrap.classList.add('hidden');
  document.body.classList.remove('modal-open');
  document.body.style.overflow = '';
  if (wrap._esc) {
    document.removeEventListener('keydown', wrap._esc);
    wrap._esc = null;
  }
}

async function renderFanZone() {
  const host = document.getElementById('fanzone-body');
  if (!host) return;
  host.innerHTML = `<p class="muted">Loading polls…</p>`;

  let data = {};
  try {
    data = await fetchJSON('/api/fan_polls');
  } catch (e) {
    host.innerHTML = `<p class="muted">Failed to load polls.</p>`;
    return;
  }

  const polls = (data.polls || []).filter(p => p.status === 'open');
  if (!polls.length) {
    host.innerHTML = `<p class="muted">No open polls right now.</p>`;
    return;
  }

  host.innerHTML = polls.map(pollCardHTML).join('');

  // Hydrate bars
  for (const p of polls) {
    try {
      const d = await fetchFanStats(p.id);
      const card = host.querySelector(`.fan-card[data-poll="${p.id}"]`);
      if (card) {
        fanBarsApply(card, d.perc);
        const tz = card.querySelector(`.fz-total[data-poll="${p.id}"]`);
        if (tz) tz.textContent = `Total votes: ${d.total}`;
      }
    } catch (_) {}
  }
}

async function handleFanZoneClick(ev) {
  const btn = ev.target.closest('.fz-vote');
  if (!btn) return;
  const betId = btn.dataset.bet;
  const opt = btn.dataset.opt;

  // Disable the clicked button briefly to avoid spam
  btn.disabled = true;

  try {
    const d = await submitFanVote(betId, opt);

    const card = btn.closest('.fan-card');
    if (card) {
      const p1 = d?.percent?.option1 || 0;
      const p2 = d?.percent?.option2 || 0;
      const tz = card.querySelector(`.fz-total[data-bet="${betId}"]`);
      fanBar(card, p1, p2);
      if (tz) tz.textContent = `Total votes: ${d?.total || 0}`;
    }

    // optional subtle notification
    if (typeof notify === 'function') notify('Vote recorded', true);

  } catch (e) {
    // 409 → already voted, anything else → error
    const msg = (String(e.message || '').includes('409') || String(e).includes('already_voted'))
      ? 'You have already voted!'
      : 'Vote failed. Please try again.';

    // Styled modal instead of browser alert
    if (typeof fzDialogOpen === 'function') {
      fzDialogOpen(msg, betId);
    } else {
      alert(msg); // fallback if dialog helper missing
    }

  } finally {
    btn.disabled = false;
  }
}

function loadFanZone() {
  renderFanZone();
  const host = document.getElementById('fanzone-body');
  if (host && !host._fz_wired) {
    host.addEventListener('click', handleFanZoneClick);
    host._fz_wired = true;
  }
  const rf = document.getElementById('fz-refresh');
  if (rf && !rf._fz_wired) {
    rf.addEventListener('click', () => renderFanZone());
    rf._fz_wired = true;
  }
}

document.addEventListener('click', (e)=>{
  const a = e.target.closest('a[data-page]');
  if(!a) return;
  const page = a.getAttribute('data-page');
  if(page === 'fanzone'){
    // make this page active in your existing router if needed
    const id = 'fanzone';
    document.querySelectorAll('section.page-section').forEach(s=>s.classList.toggle('active-section', s.id===id));
    document.querySelectorAll('#main-menu a').forEach(x=>x.classList.toggle('active', x===a));
    loadFanZone();
    e.preventDefault();
  }
});

// ===== Admin: Fan Polls =====
function fpOpen(){ document.getElementById('fp-modal')?.classList.remove('hidden'); document.body.classList.add('modal-open'); }
function fpClose(){ document.getElementById('fp-modal')?.classList.add('hidden'); document.body.classList.remove('modal-open'); }
function fpAddOptRow(label=''){
  const wrap = document.getElementById('fp-opts');
  const div = document.createElement('div');
  div.className = 'fp-opt';
  div.innerHTML = `<input type="text" placeholder="Option label" value="${label.replace(/"/g,'&quot;')}"><button class="btn sm fp-del">✕</button>`;
  wrap.appendChild(div);
  div.querySelector('.fp-del').onclick = ()=> div.remove();
}

async function loadAdminPolls(){
  const host = document.getElementById('fanpolls-body');
  if(!host) return;
  host.innerHTML = `<p class="muted">Loading polls…</p>`;
  let data = {};
  try{ data = await fetchJSON('/admin/fan_polls'); }catch(_){ host.innerHTML = `<p class="muted">Failed to load.</p>`; return; }
  const rows = (data.polls||[]).reverse().map(p=>`
    <div class="fp-row" data-id="${p.id}">
      <div class="fp-title">${p.title}</div>
      <div class="fp-status">${p.status}</div>
      <div class="fp-actions">
        <button class="btn sm fp-toggle" data-status="${p.status==='open'?'closed':'open'}">${p.status==='open'?'Close':'Open'}</button>
        <button class="btn sm fp-delete">Delete</button>
      </div>
    </div>
  `).join('');
  host.innerHTML = rows || `<p class="muted">No polls yet.</p>`;

  host.onclick = async (e)=>{
    const row = e.target.closest('.fp-row'); if(!row) return;
    const id = row.dataset.id;
    if(e.target.classList.contains('fp-toggle')){
      const ns = e.target.dataset.status;
      try{ await fetchJSON(`/admin/fan_polls/${id}`, { method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({status:ns}) }); loadAdminPolls(); notify('Poll updated', true);}catch(_){ notify('Update failed', false); }
    }
    if(e.target.classList.contains('fp-delete')){
      if(!confirm('Delete this poll?')) return;
      try{ await fetchJSON(`/admin/fan_polls/${id}`, { method:'DELETE' }); loadAdminPolls(); notify('Poll deleted', true);}catch(_){ notify('Delete failed', false); }
    }
  };

  const btn = document.getElementById('fp-new');
  if(btn && !btn._wired){
    btn._wired = true;
    btn.onclick = ()=>{
      document.getElementById('fp-title-input').value = '';
      document.getElementById('fp-opts').innerHTML = '';
      fpAddOptRow(); fpAddOptRow(); // start with 2 rows
      fpOpen();
    };
  }

  const addBtn = document.getElementById('fp-addopt'); if(addBtn && !addBtn._wired){ addBtn._wired=true; addBtn.onclick=()=>fpAddOptRow(); }
  const closeBtn = document.getElementById('fp-close'); if(closeBtn && !closeBtn._wired){ closeBtn._wired=true; closeBtn.onclick=fpClose; }
  document.getElementById('fp-modal')?.querySelector('.wc-modal-backdrop')?.addEventListener('click', fpClose);

  const save = document.getElementById('fp-save');
  if(save && !save._wired){
    save._wired = true;
    save.onclick = async ()=>{
      const title = document.getElementById('fp-title-input').value.trim();
      const opts = [...document.querySelectorAll('#fp-opts input')].map(i=>i.value.trim()).filter(Boolean);
      if(!title || opts.length<2){ notify('Title and 2+ options required', false); return; }
      try{
        await fetchJSON('/admin/fan_polls', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ title, options: opts }) });
        fpClose(); loadAdminPolls(); notify('Poll created', true);
      }catch(_){ notify('Create failed', false); }
    };
  }
}


// === Auto redirect new Discord-linked users to /terms ===
async function checkUserTOS() {
  try {
    const res = await fetch('/api/me/tos', { credentials: 'include' });
    const data = await res.json();
    if (data.connected && (!data.accepted || !data.in_players)) {
      console.log('[WorldCupBot] redirecting first-time user to /terms');
      window.location.href = data.url || '/terms';
    }
  } catch (err) {
    console.warn('TOS check failed:', err);
  }
}

// run this early after page load, before dashboard routing
document.addEventListener('DOMContentLoaded', () => {
  setTimeout(checkUserTOS, 1000);
});

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

    function isoToFlag(iso){
      if(!iso) return '';
      iso = iso.toUpperCase();
      // UK isn't a valid ISO-3166-1 alpha-2 flag, use GB
      if (iso === 'UK') iso = 'GB';
      // Must be A-Z chars
      if (!/^[A-Z]{2}$/.test(iso)) return '';
      return String.fromCodePoint(127397 + iso.charCodeAt(0))
           + String.fromCodePoint(127397 + iso.charCodeAt(1));
    }

    // 24h meta cache
    async function loadTeamMeta(){
      const CK = 'wc:team_meta';
      const TTL = 24 * 60 * 60 * 1000; // 24 hours

      // read cache
      try{
        const blob = JSON.parse(localStorage.getItem(CK) || 'null');
        if (blob && (Date.now() - (blob.ts || 0)) < TTL) {
          return blob.data;
        }
      }catch{}

      // fetch fresh
      try{
        const r = await fetch('/api/team_meta', {cache:'no-store'});
        if(!r.ok) throw new Error('meta missing');
        const data = await r.json();
        localStorage.setItem(CK, JSON.stringify({ ts: Date.now(), data }));
        return data;
      }catch(_){
        // gracefully run without meta
        return null;
      }
    }

    // -------------------------------
    // User Page
    // -------------------------------
    async function loadUser() {
      try {
        const section = ensureSectionCard('user', 'User', [
          ['Refresh', { id: 'user-refresh' }]
        ]);
        const scroller = section.querySelector('.table-scroll');
        scroller.innerHTML = '<div class="loading">Loading user data...</div>';

        // 1. Check if user has accepted T&Cs
        const tos = await fetchJSON('/api/me/tos');
        if (tos.connected && (!tos.accepted || !tos.in_players)) {
          console.log('[WorldCupBot] redirecting to /terms');
          window.location.href = tos.url || '/terms';
          return;
        }

        // 2. Get user info
        const { user } = await fetchJSON('/api/me');
        if (!user) {
          scroller.innerHTML = `
            <div class="user-guest">
              <p>You are not connected with Discord.</p>
              <button id="btn-discord-login" class="btn">Connect Discord</button>
            </div>`;
          const btn = document.getElementById('btn-discord-login');
          btn && (btn.onclick = () => (window.location.href = '/auth/discord/login'));
          return;
        }

        // 3. Render base profile layout
        scroller.innerHTML = `
          <div class="user-card">
            <div class="user-head">
              <img class="user-ava" src="${user.avatar || '/static/img/avatar.png'}" alt="">
              <div class="user-meta">
                <div class="user-name">${escapeHtml(user.global_name || user.username)}</div>
                <div class="user-id">${user.discord_id}</div>
              </div>
              <button id="btn-discord-logout" class="btn subtle">Sign out</button>
            </div>
            <div class="user-grids">
              <div class="user-col">
                <h3>Owned Teams</h3>
                <div id="owned" class="flag-grid"></div>
                <h3>Split Teams</h3>
                <div id="split" class="flag-grid"></div>
              </div>
              <div class="user-col">
                <h3>Upcoming Matches</h3>
                <div id="matches" class="match-list"></div>
              </div>
            </div>
          </div>
        `;

        // 4. Logout button
        const out = document.getElementById('btn-discord-logout');
        out && (out.onclick = async () => { await postJSON('/auth/discord/logout', {}); location.reload(); });

        // 5. Load owned teams & matches
        const [own, matches] = await Promise.all([
          fetchJSON('/api/me/ownership'),
          fetchJSON('/api/me/matches')
        ]);

        // Render owned/split teams
        function renderFlags(wrapId, items) {
          const wrap = document.getElementById(wrapId);
          if (!wrap) return;
          if (!items || !items.length) { wrap.innerHTML = `<div class="muted">None</div>`; return; }
          wrap.innerHTML = items.map(x => `
            <div class="flag-card" title="${escapeHtml(x.team)}">
              ${x.flag ? `<img src="${x.flag}" alt="">` : ''}
              <span>${escapeHtml(x.team)}</span>
            </div>`).join('');
        }
        renderFlags('owned', own?.owned || []);
        renderFlags('split', own?.split || []);

        // Render matches
        const mEl = document.getElementById('matches');
        if (mEl) {
          const list = (matches?.matches || []);
          if (!list.length) {
            mEl.innerHTML = `<div class="muted">No upcoming matches</div>`;
          } else {
            mEl.innerHTML = list.map(m => {
              const when = m.utc || m.time || '';
              const dt = when ? new Date(when).toLocaleString() : '';
              return `
                <div class="match-row">
                  <div class="match-when">${dt}</div>
                  <div class="match-vs"><strong>${escapeHtml(m.home)}</strong> vs <strong>${escapeHtml(m.away)}</strong></div>
                  ${m.group ? `<div class="match-group">${escapeHtml(m.group)}</div>` : ``}
                </div>`;
            }).join('');
          }
        }

      } catch (err) {
        console.error('loadUser error:', err);
        const section = ensureSectionCard('user', 'User');
        const scroller = section.querySelector('.table-scroll');
        scroller.innerHTML = `<div class="error">Failed to load user data.</div>`;
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

    function classifyCountries(svg, teamIso, merged, teamMeta){
      const rows = (merged && merged.rows) || [];

      // 1) team -> ownership state
      const teamState = {};
      for (const row of rows) {
        const team = row.country;
        const ownersCount = row.owners_count || 0;
        const splits = row.split_with || [];
        let status = 'free';
        if (ownersCount > 0 && (!splits || splits.length === 0)) status = 'owned';
        if (splits && splits.length > 0) status = 'split';
        teamState[team] = { status, main: row.main_owner, splits };
      }

      // 2) meta lookups (group, qualified)
      const teamGroup = {};
      const teamQual  = {};
      if (teamMeta) {
        if (teamMeta.groups) {
          // grouped style: { groups:{A:[...]}, not_qualified:[...] }
          Object.entries(teamMeta.groups).forEach(([g, list])=>{
            (list || []).forEach(t => { teamGroup[t] = g; teamQual[t] = true; });
          });
          (teamMeta.not_qualified || []).forEach(t => { teamQual[t] = false; });
        } else {
          // per-team style: { "England": {group:"C", qualified:true}, ... }
          Object.entries(teamMeta).forEach(([team, m])=>{
            teamGroup[team] = m.group || null;
            teamQual[team]  = (m.qualified === true); // only true counts as qualified
          });
        }
      }

      // 3) iso -> team map from /api/team_iso
      const isoToTeam = {};
      Object.keys(teamIso || {}).forEach(team=>{
        const iso = (teamIso[team] || '').toLowerCase();
        if (iso) isoToTeam[iso] = team;
      });

      // 4) paint countries, store datasets, wire tooltips
      svg.querySelectorAll('.country').forEach(el=>{
        const iso = (el.getAttribute('data-iso') || '').toLowerCase();
        const isoUp = iso.toUpperCase();
        const team = isoToTeam[iso];
        const teamLabel = team || isoUp;

        // default: Not Qualified (anything not specified in meta is NQ)
        let status = 'nq';

        // compute qualification only if we have a team name
        if (team) {
          // when teamMeta exists, only explicit true is qualified; if no meta, treat as qualified
          const qualified = teamMeta ? (teamQual[team] === true) : true;

          if (qualified) {
            status = 'free';
            if (teamState[team]) status = teamState[team].status;
          } else {
            status = 'nq';
          }
        }

        // owners list for tooltip/panel
        const ownerNames = [];
        if (team && teamState[team]) {
          const main = teamState[team].main;
          const splits = teamState[team].splits || [];
          if (main && main.username) ownerNames.push(main.username);
          if (splits && splits.length) {
            ownerNames.push(...splits.map(s => s.username).filter(Boolean));
          }
        }
        const ownersText = ownerNames.length ? ownerNames.join(', ') : 'Unassigned';

        // apply classes
        el.classList.remove('owned','split','free','nq','dim');
        el.classList.add(status);

        // datasets for click panel and filtering
        const flagEmoji = isoToFlag(isoUp);
        el.dataset.owners = ownersText;
        el.dataset.team   = teamLabel;
        el.dataset.group  = team ? (teamGroup[team] || '') : '';
        el.dataset.iso    = isoUp;
        el.dataset.flag   = flagEmoji;

        // tooltip
        el.onmouseenter = ev=>{
          tip.innerHTML =
            `<strong>${flagEmoji ? flagEmoji + ' ' : ''}${teamLabel}</strong>` +
            `<br><em>${isoUp}</em><br>${ownersText}`;
          tip.style.opacity = '1';
          positionTip(ev);
        };
        el.onmousemove = ev=> positionTip(ev);
        el.onmouseleave = ()=>{ tip.style.opacity = '0'; };
        el.onfocus = el.onmouseenter;
        el.onblur  = el.onmouseleave;
      });
    }

    let currentGroup = 'ALL';

    function populateGroupSelector(teamMeta){
      const sel = document.getElementById('map-group');
      if(!sel) return;
      // If no meta, keep only "All"
      if(!teamMeta) {
        sel.innerHTML = '<option value="ALL" selected>All</option>';
        return;
      }

      // Build group set
      const groups = new Set();
      if (teamMeta.groups){
        Object.keys(teamMeta.groups).forEach(g => groups.add(g));
      } else {
        Object.values(teamMeta).forEach(m => { if(m.group) groups.add(m.group); });
      }

      const sorted = [...groups].sort();
      sel.innerHTML = '<option value="ALL" selected>All</option>'
        + sorted.map(g => `<option value="${g}">Group ${g}</option>`).join('');
    }

    function applyGroupFilter(svg){
      svg.querySelectorAll('.country').forEach(el=>{
        const g = (el.dataset.group || '').toUpperCase();
        if (currentGroup === 'ALL' || (g && g.toUpperCase() === currentGroup.toUpperCase())){
          el.classList.remove('dim');
        } else {
          el.classList.add('dim');
        }
      });
    }


      // Helper to color both group and its shapes
      function setStatus(el, status) {
        el.classList.remove('owned', 'split', 'free');
        el.classList.add(status);
        el.querySelectorAll('path,polygon,rect,circle').forEach(sh => {
          sh.classList.remove('owned', 'split', 'free');
          sh.classList.add(status);
        });
      }

      // Tooltip positioning - relative to #map-wrap
      const wrap = document.getElementById('map-wrap');
      function positionTip(ev) {
        const r = wrap.getBoundingClientRect();
        const tipRect = tip.getBoundingClientRect();

        // tight offset near cursor
        let x = ev.clientX - r.left + 6;
        let y = ev.clientY - r.top - tipRect.height - 2;

        // if not enough room above, show below
        if (y < 2) y = ev.clientY - r.top + 10;

        // clamp inside map area
        const maxX = r.width - tipRect.width - 2;
        const maxY = r.height - tipRect.height - 2;
        if (x < 2) x = 2;
        if (y < 2) y = 2;
        if (x > maxX) x = maxX;
        if (y > maxY) y = maxY;

        tip.style.left = `${x}px`;
        tip.style.top = `${y}px`;
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

    function enableClickZoom(svg){
      const infoBox = document.getElementById('map-country-info');
      const titleEl = document.getElementById('map-info-title');
      const ownersEl = document.getElementById('map-info-owners');
      const statusEl = document.getElementById('map-info-status');

      // initial viewBox
      let origViewBox = svg.getAttribute('viewBox');
      if (!origViewBox) {
        const r = svg.getBBox();
        origViewBox = `${r.x} ${r.y} ${r.width} ${r.height}`;
        svg.setAttribute('viewBox', origViewBox);
      }

      let currentCountry = null;
      let animating = false;

      function lerp(a, b, t) { return a + (b - a) * t; }

      // Animate from current viewBox to target viewBox
      function animateViewBox(from, to, duration = 600){
        if (animating) return;
        animating = true;

        const start = performance.now();

        function step(now){
          const t = Math.min((now - start) / duration, 1);
          const x = lerp(from.x, to.x, t);
          const y = lerp(from.y, to.y, t);
          const w = lerp(from.w, to.w, t);
          const h = lerp(from.h, to.h, t);
          svg.setAttribute('viewBox', `${x} ${y} ${w} ${h}`);
          if (t < 1) requestAnimationFrame(step);
          else animating = false;
        }
        requestAnimationFrame(step);
      }

      // Read current viewBox as numbers
      function parseViewBox(vb){
        const [x, y, w, h] = vb.split(/\s+/).map(Number);
        return {x, y, w, h};
      }

      function zoomToElement(el, pad = 1.25){
        const b = el.getBBox();
        const w = b.width * pad;
        const h = b.height * pad;
        const x = b.x - (w - b.width)/2;
        const y = b.y - (h - b.height)/2;
        const from = parseViewBox(svg.getAttribute('viewBox'));
        const to = {x, y, w, h};
        animateViewBox(from, to);
      }

      function resetZoom(){
        const from = parseViewBox(svg.getAttribute('viewBox'));
        const to = parseViewBox(origViewBox);
        animateViewBox(from, to);
        infoBox.classList.add('hidden');
        currentCountry = null;
      }

        svg.querySelectorAll('.country').forEach(el=>{
            el.addEventListener('click', ()=>{
              if (currentCountry === el) { resetZoom(); return; }

              currentCountry = el;

              const name   = el.dataset.team || el.dataset.iso || 'Unknown';
              const flag   = el.dataset.flag || '';
              const group  = el.dataset.group || '—';
              const owners = el.dataset.owners || 'Unassigned';
              const status = el.classList.contains('owned') ? 'Owned'
                           : el.classList.contains('split') ? 'Split'
                           : el.classList.contains('nq')    ? 'Not Qualified'
                           : 'Unassigned';

              // Fill the info panel
              document.getElementById('map-info-name').textContent = name;
              document.getElementById('map-info-flag').textContent = flag;
              document.getElementById('map-info-group').textContent = 'Group: ' + group;
              document.getElementById('map-info-owners').textContent = 'Owners: ' + owners;
              document.getElementById('map-info-status').textContent = 'Status: ' + status;

              infoBox.classList.remove('hidden');

              // Zoom to the clicked country (uses your viewBox animation)
              zoomToElement(el, 1.3);
            });
        });
    }

    async function render(){
      try {
        console.time('worldmap:fetch');
        const [iso, merged, meta] = await Promise.all([
          loadTeamIso(),
          loadOwnership(),
          loadTeamMeta()
        ]);
        console.debug('team_iso ok:', Object.keys(iso).length, 'entries');
        console.debug('ownership_merged ok:', (merged?.rows?.length || 0), 'rows');
        console.debug('team_meta:', meta ? 'loaded' : 'absent');
        console.timeEnd('worldmap:fetch');

        const svg = await inlineSVG('world.svg');

        // Color, store data attributes, and init groups
        classifyCountries(svg, iso, merged, meta);
        populateGroupSelector(meta);
        applyGroupFilter(svg);

        // Hook group selector
        const sel = document.getElementById('map-group');
        if (sel){
          sel.onchange = ()=>{
            currentGroup = sel.value || 'ALL';
            applyGroupFilter(svg);
          };
        }

        // Keep your existing click-to-zoom
        enableClickZoom(svg);

      } catch (e) {
        console.error('Map render error:', e);
        host.innerHTML = `
          <div class="muted" style="padding:10px;">
            Failed to load map. Ensure world.svg exists and /api endpoints return valid JSON.<br>
            <small>${(e && e.message) ? e.message : e}</small>
          </div>`;
      }
    }


    if (btnRefresh){
      btnRefresh.addEventListener('click', ()=>{
        localStorage.removeItem('wc:ownership_merged');
        localStorage.removeItem('wc:team_iso');
        localStorage.removeItem('wc:team_meta');   // NEW: clear meta cache
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
// Daily silent refresh of team_meta (and re-render if on World Map)
(function setupDailyMetaRefresh(){
  const DAY = 24 * 60 * 60 * 1000;
  setInterval(async ()=>{
    // If meta is stale, clear it so next render fetches fresh
    try{
      const blob = JSON.parse(localStorage.getItem('wc:team_meta') || 'null');
      if (!blob || (Date.now() - (blob.ts || 0)) >= DAY) {
        localStorage.removeItem('wc:team_meta');
        // Only re-render if user is actually on the World Map section
        const isActive = document.querySelector('#worldmap.active-section');
        if (isActive) render();
      }
    }catch{
      localStorage.removeItem('wc:team_meta');
    }
  }, DAY);
})();

// --- Leaderboards add-on START (append-only) ---
(() => {
  'use strict';
  const qs = (s, el=document)=>el.querySelector(s);
  const qsa = (s, el=document)=>[...el.querySelectorAll(s)];
  const fetchJSON = (window.fetchJSON)?window.fetchJSON:async (u,o)=>{const r=await fetch(u,o);if(!r.ok) throw new Error(r.status);return r.json()};
  const debounce=(fn,ms=200)=>{let t;return(...a)=>{clearTimeout(t);t=setTimeout(()=>fn(...a),ms)}};
  const idHue = id => String(id||'').split('').reduce((h,ch)=>(h*31+ch.charCodeAt(0))%360,0);
  const initials = n => (n||'').trim().split(/\s+/).slice(0,2).map(p=>p[0]||'').join('').toUpperCase() || '??';

    // Build a Discord CDN avatar URL from id + avatar hash
    function discordAvatarUrl(id, avatarHash){
      if(!id || !avatarHash) return null;
      const ext = String(avatarHash).startsWith('a_') ? 'gif' : 'png';
      return `https://cdn.discordapp.com/avatars/${id}/${avatarHash}.${ext}?size=64`;
    }

    // Default avatar when the user has no custom avatar
    function discordDefaultAvatarUrl(id){
      try {
        const idx = Number(BigInt(String(id)) % 6n); // 0..5
        return `https://cdn.discordapp.com/embed/avatars/${idx}.png`;
      } catch {
        return `https://cdn.discordapp.com/embed/avatars/0.png`;
      }
    }

    function avatarEl(user){
      const dname = user.display_name || user.username || user.id || 'Unknown';
      const wrap = document.createElement('div');
      wrap.className = 'lb-ava';
      const img = document.createElement('img');
      img.alt = `${dname} avatar`;
      img.src = user.avatar_url;
      wrap.appendChild(img);
      return wrap;
    }

    function barEl(value, max) {
      const wrap = document.createElement('div');
      wrap.className = 'lb-bar';

      const fill = document.createElement('div');
      fill.className = 'lb-fill';

      // Clamp ratio between 0–1 and make top value exactly 100%
      const pct = (!max || max <= 0)
        ? 0
        : (value >= max ? 1 : Math.max(0, Math.min(1, value / max)));

      wrap.setAttribute('aria-label', `${value} of ${max}`);

      // Smooth animation, but keep full width perfectly aligned for max value
      requestAnimationFrame(() => {
        fill.style.width = (pct === 1 ? '100%' : `${(pct * 100).toFixed(1)}%`);
      });

      wrap.appendChild(fill);
      return wrap;
    }

    function flagChip(country, iso){
    const chip=document.createElement('span'); chip.className='lb-flag'; const code=iso[country]||'';
    if(code){ const img=document.createElement('img'); img.alt=`${country} flag`; img.src=`https://flagcdn.com/w20/${code}.png`; chip.appendChild(img); const t=document.createElement('span'); t.textContent=country; chip.appendChild(t); }
    else { chip.textContent=(country||'').slice(0,3).toUpperCase()||'N/A'; }
    chip.title=country; return chip;
    }

    const state = (window.state=window.state||{}); state.lb=state.lb||{loaded:false};

    async function fetchAll(){
    const [ownersResp,bets,iso,verified]=await Promise.all([
      fetchJSON('/api/ownership_from_players'),
      fetchJSON('/api/bets'),
      fetchJSON('/api/team_iso'),
      fetchJSON('/api/verified')
    ]);
    const vmap = {};
    (verified || []).forEach(v => {
      const id = String(v.discord_id || v.id || v.user_id || '').trim();
      if (!id) return;

      // Gather any avatar info we already have
      const raw = v.avatar_url || v.avatarUrl || v.avatar || v.avatar_hash || v.avatarHash || null;

      // If it's a URL, keep it. If it's a hash, build CDN URL. Else default avatar.
      let avatar_url = null;
      if (raw && /^https?:\/\//i.test(String(raw))) {
        avatar_url = raw;
      } else if (raw && /^[aA]?_?[0-9a-f]{6,}$/.test(String(raw))) {
        const ext = String(raw).startsWith('a_') ? 'gif' : 'png';
        avatar_url = `https://cdn.discordapp.com/avatars/${id}/${raw}.${ext}?size=64`;
      } else {
        // default avatar (coloured Discord silhouette)
        try {
          const idx = Number(BigInt(String(id)) % 6n);
          avatar_url = `https://cdn.discordapp.com/embed/avatars/${idx}.png`;
        } catch {
          avatar_url = `https://cdn.discordapp.com/embed/avatars/0.png`;
        }
      }

      vmap[id] = {
        id,
        username: v.username || '',
        display_name: v.display_name || v.username || id,
        avatar_url
      };
    });


    // ---- Live enrichment: replace defaults with real Discord avatars ----
    const missing = Object.values(vmap)
      .filter(v => !v.avatar_url || /\/embed\/avatars\//.test(String(v.avatar_url)))
      .map(v => v.id);

    if (missing.length) {
      const chunkSize = 50;
      for (let i = 0; i < missing.length; i += chunkSize) {
        const ids = missing.slice(i, i + chunkSize).join(',');
        try {
          const resp = await fetch(`/api/avatars?ids=${encodeURIComponent(ids)}`, {
            headers: { 'Accept': 'application/json' }
          });
          if (resp.ok) {
            const { avatars = {} } = await resp.json();
            for (const [uid, url] of Object.entries(avatars)) {
              if (vmap[uid]) vmap[uid].avatar_url = url;
            }
          }
        } catch (err) {
          console.warn('Avatar enrichment failed', err);
        }
      }
    }
    return { rows:(ownersResp&&ownersResp.rows)||[], bets:(bets||[]), iso:(iso||{}), vmap };
    }

    function aggregateOwners(rows, vmap){
      // Map id -> {id, name, teams:[], split_teams:[], count, split_count, avatar_url}
      const owners = new Map();
      for (const r of rows) {
        const main = r?.main_owner?.id ? String(r.main_owner.id) : null;
        if (main) {
          const prof = vmap[main] || { id:main, display_name:r.main_owner.username||main, username:r.main_owner.username||main };
          const rec = owners.get(main) || { id:main, name:prof.display_name||prof.username||main, teams:[], split_teams:[], split_count:0, avatar_url:prof.avatar_url||null };
          rec.teams.push(r.country);
          owners.set(main, rec);
        }
        if (Array.isArray(r.split_with)) {
          for (const sw of r.split_with) {
            const sid = sw?.id ? String(sw.id) : null;
            if (!sid) continue;
            const prof = vmap[sid] || { id:sid, display_name: sw.username||sid, username: sw.username||sid };
            const rec = owners.get(sid) || { id:sid, name:prof.display_name||prof.username||sid, teams:[], split_teams:[], split_count:0, avatar_url:prof.avatar_url||null };
            rec.split_teams.push(r.country);
            rec.split_count = rec.split_teams.length;
            owners.set(sid, rec);
          }
        }
      }
      const list = [...owners.values()].map(r => ({
        ...r,
        count: r.teams.length + r.split_teams.length
      }));
    list.sort((a, b) =>
      // 1) prioritize main-owned teams
      (b.teams.length - a.teams.length) ||
      // 2) then total count (main + split)
      (b.count - a.count) ||
      // 3) then name
      String(a.name).localeCompare(String(b.name))
    );
    return list;
    }

// Tries a few paths so you don't need backend changes if you already have one.
// Expected payload shape (any of these is fine):
//   [{ id, goals, name? }] OR { rows:[{ id, goals, name? }]} OR { players:[...] }
async function fetchGoalsData(){
  const tryPaths = ['/api/goals', '/api/stats/goals', '/api/leaderboards/scorers'];
  for(const path of tryPaths){
    try{
      const res = await fetch(path, { headers:{'Accept':'application/json'} });
      if(!res.ok) continue;
      const data = await res.json();
      if(Array.isArray(data)) return data;
      if(Array.isArray(data.rows)) return data.rows;
      if(Array.isArray(data.players)) return data.players;
    }catch(_) { /* keep trying */ }
  }
  return []; // nothing available
}

    function aggregateScorers(raw, vmap){
      const out = (raw||[]).map(p => {
        const id = String(p.id||p.discord_id||'').trim();
        const prof = vmap[id] || { id, display_name: p.name || p.username || id, username: p.username || '' };
        return {
          id,
          name: prof.display_name || prof.username || id,
          goals: Number(p.goals||0),
          avatar_url: prof.avatar_url || null
        };
      }).filter(x => x.id);
      out.sort((a,b) => (b.goals - a.goals) || String(a.name).localeCompare(String(b.name)));
      return out;
    }

    function scorersRowEl(rec){
      const row = document.createElement('div');
      row.className = 'lb-row';
      const left = document.createElement('div'); left.className='lb-left';
      left.appendChild(avatarEl({id:rec.id, display_name:rec.name, avatar_url:rec.avatar_url}));
      const t = document.createElement('div'); t.innerHTML = `<div class="lb-name">${rec.name}</div>`;
      left.appendChild(t);

      const right = document.createElement('div'); right.className='lb-right';
      right.appendChild(barEl(rec.goals, rec._max || rec.goals));
      const stats = document.createElement('div'); stats.className='lb-stats';
      const chip = document.createElement('span'); chip.className='lb-chip'; chip.textContent = `G: ${rec.goals}`;
      stats.appendChild(chip); right.appendChild(stats);

      row.appendChild(left); row.appendChild(right);
      return row;
    }


    function aggregateBettors(bets, vmap){
    const stats=new Map();
    for(const b of (bets||[])){
      const o1=String(b.option1_user_id||'').trim(), o2=String(b.option2_user_id||'').trim();
      const w=(b.winner||'').toLowerCase(); const wid=(w==='option1')?o1:(w==='option2')?o2:null; const lid=(w==='option1')?o2:(w==='option2')?o1:null;
      if(wid){ const p=vmap[wid]||{id:wid,display_name:b.option1_user_name||b.option2_user_name||wid,username:''};
        const r=stats.get(wid)||{id:wid,name:p.display_name||p.username||wid,wins:0,losses:0,avatar_url:p.avatar_url||null}; r.wins++; stats.set(wid,r); }
      if(lid){ const p=vmap[lid]||{id:lid,display_name:'',username:''};
        const r=stats.get(lid)||{id:lid,name:p.display_name||p.username||lid,wins:0,losses:0,avatar_url:p.avatar_url||null}; r.losses++; stats.set(lid,r); }
    }
    const list=[...stats.values()].map(r=>({...r, wr:r.wins+r.losses?Math.round(100*r.wins/(r.wins+r.losses)):null}));
    list.sort((a,b)=>(b.wins-a.wins)||String(a.name).localeCompare(String(b.name))); return list;
    }

    function ownersRowEl(rec, iso){
      const row = document.createElement('div');
      row.className = 'lb-row';

      const left = document.createElement('div');
      left.className = 'lb-left';
      left.appendChild(avatarEl({id:rec.id, display_name:rec.name, avatar_url:rec.avatar_url}));
      const txt = document.createElement('div');
      txt.innerHTML = `<div class="lb-name">${rec.name}</div>
                       <div class="lb-sub lb-muted">Teams: ${rec.teams.length}${rec.split_count?` • Split: ${rec.split_count}`:''}</div>`;
      left.appendChild(txt);

      const right = document.createElement('div');
      right.className = 'lb-right';
      right.appendChild(barEl(rec.count, rec._max || rec.count));

      const flags = document.createElement('div');
      flags.className = 'lb-flags';

      // combine main first, then splits; cap total chips to 6 for performance
      const main = (rec.teams || []).map(c => ({ c, cls: '' }));
      const split = (rec.split_teams || []).map(c => ({ c, cls: 'split' }));
      const combined = [...main, ...split];
      const show = combined.slice(0, 6);

      show.forEach(({c, cls}) => {
        const chip = flagChip(c, iso);
        if (cls) chip.classList.add(cls);
        flags.appendChild(chip);
      });

      // tooltip for the full list
      const allNames = [
        ...rec.teams.map(t=>`${t}`),
        ...rec.split_teams.map(t=>`${t} (split)`)
      ];
      if (combined.length > show.length) {
        const more = document.createElement('span');
        more.className = 'lb-chip';
        more.textContent = `+${combined.length - show.length} more`;
        more.title = allNames.join(', ');
        flags.appendChild(more);
      }

      right.appendChild(flags);
      row.appendChild(left);
      row.appendChild(right);
      return row;
    }
    function bettorsRowEl(rec){
    const row=document.createElement('div'); row.className='lb-row';
    const left=document.createElement('div'); left.className='lb-left';
    left.appendChild(avatarEl({id:rec.id,display_name:rec.name,avatar_url:rec.avatar_url}));
    const t=document.createElement('div'); t.innerHTML=`<div class="lb-name">${rec.name}</div>`; left.appendChild(t);
    const right=document.createElement('div'); right.className='lb-right';
    right.appendChild(barEl(rec.wins, rec._max||rec.wins));
    const stats=document.createElement('div'); stats.className='lb-stats';
    const chip=document.createElement('span'); chip.className='lb-chip'; chip.textContent=(rec.wr!=null)?`W: ${rec.wins} | L: ${rec.losses} | WR: ${rec.wr}%`:`W: ${rec.wins}`;
    stats.appendChild(chip); right.appendChild(stats);
    row.appendChild(left); row.appendChild(right); return row;
    }

    function filterByQuery(list,q){
    if(!q)
    return list; const s=q.toLowerCase();
    return list.filter(x=>String(x.name||'').toLowerCase().includes(s));
    }

    function paginate(list, page, per=50){
      const total=Math.max(1,Math.ceil(list.length/per));
      const p=Math.max(1,Math.min(total,page));
      const start=(p-1)*per;
      return {page:p,total,slice:list.slice(start,start+per)};
    }

    function paintScorers(page=1){
      const state=(window.state=window.state||{}); state.lb=state.lb||{};
      const body=document.querySelector('#lb-scorers-body'); if(!body) return;
      const q=document.querySelector('#lb-scorers-search')?.value||'';
      const list=filterByQuery(state.lb.scorersAll||[], q);
      const {page:cur,total,slice}=paginate(list,page,50);
      body.innerHTML='';
      if(!slice.length){ body.innerHTML='<div class="lb-empty">No goal data to show.</div>'; }
      else { slice.forEach(r=>body.appendChild(scorersRowEl(r))); }
      document.querySelector('#lb-scorers-page').textContent=`${cur}/${total}`;
      state.lb.scorersPage=cur;
      const s = (window.state=window.state||{}); s.lb=s.lb||{};
      if (s.lb.scorersDense) document.querySelector('#lb-scorers-body')?.classList.add('dense-mode');
    }

    function toggleDense(which){
      const body = document.querySelector(which);
      if(!body) return;
      body.classList.toggle('dense-mode');
    }

    async function renderLeaderboards(){
      const { rows, bets, iso, vmap } = await fetchAll();

      // Owners - splits always included inside aggregateOwners now
      let owners = aggregateOwners(rows, vmap);
      const maxOwn = owners[0]?.count || 0;
      owners.forEach(o => o._max = maxOwn);

      // Bettors
      let bettors = aggregateBettors(bets, vmap);
      const maxWin = bettors[0]?.wins || 0;
      bettors.forEach(b => b._max = maxWin);

      // Scorers (if you added Goals)
      const rawGoals = await fetchGoalsData();
      let scorers = aggregateScorers(rawGoals, vmap);
      const maxGoals = scorers[0]?.goals || 0;
      scorers.forEach(s => s._max = maxGoals);

      const state = (window.state = window.state || {}); state.lb = state.lb || {};
      state.lb.ownersAll = owners;
      state.lb.bettorsAll = bettors;
      state.lb.scorersAll = scorers;
      state.lb.iso = iso;

      paintOwners(); paintBettors(); paintScorers();
      wireControls();
    }

    function paintOwners(page=1){
    const state=(window.state=window.state||{}); state.lb=state.lb||{};
    const body=qs('#lb-owners-body'); if(!body) return;
    const q=qs('#lb-owners-search')?.value||'';
    const list=filterByQuery(state.lb.ownersAll||[], q);
    const {page:cur,total,slice}=paginate(list,page,50);
    body.innerHTML='';
    if(!slice.length){ body.innerHTML='<div class="lb-empty">No owners to show.</div>'; }
    else { slice.forEach(r=>body.appendChild(ownersRowEl(r, state.lb.iso||{}))); }
    qs('#lb-owners-page').textContent=`${cur}/${total}`; state.lb.ownersPage=cur;
    const s = (window.state=window.state||{}); s.lb=s.lb||{};
    if (s.lb.ownersDense) document.querySelector('#lb-owners-body')?.classList.add('dense-mode');

    }

    function paintBettors(page=1){
    const state=(window.state=window.state||{}); state.lb=state.lb||{};
    const body=qs('#lb-bettors-body'); if(!body) return;
    const q=qs('#lb-bettors-search')?.value||'';
    const list=filterByQuery(state.lb.bettorsAll||[], q);
    const {page:cur,total,slice}=paginate(list,page,50);
    body.innerHTML='';
    if(!slice.length){ body.innerHTML='<div class="lb-empty">No bettors to show.</div>'; }
    else { slice.forEach(r=>body.appendChild(bettorsRowEl(r))); }
    qs('#lb-bettors-page').textContent=`${cur}/${total}`; state.lb.bettorsPage=cur;
    const s = (window.state=window.state||{}); s.lb=s.lb||{};
    if (s.lb.bettorsDense) document.querySelector('#lb-bettors-body')?.classList.add('dense-mode');
    }

    function toggleDense(which){
    const body=qs(which); if(!body) return;
    [...body.querySelectorAll('.lb-row')].forEach(r=>r.classList.toggle('dense'));
    }
    function wireControls(){
    const state=(window.state=window.state||{}); state.lb=state.lb||{};
    qs('#lb-owners-search')?.addEventListener('input', debounce(()=>paintOwners(1),200));
    qs('#lb-bettors-search')?.addEventListener('input', debounce(()=>paintBettors(1),200));
    qs('#lb-owners-refresh')?.addEventListener('click', async ()=>{state.lb.loaded=false; await loadLeaderboardsOnce();});
    qs('#lb-bettors-refresh')?.addEventListener('click', async ()=>{state.lb.loaded=false; await loadLeaderboardsOnce();});
    qs('#lb-owners-toggle-splits')?.addEventListener('click', async (e)=>{
      const on=e.currentTarget.dataset.on==='1'?'0':'1';
      e.currentTarget.dataset.on=on;
      e.currentTarget.textContent=`include splits: ${on==='1'?'on':'off'}`;
      state.lb.loaded=false; await loadLeaderboardsOnce();
    });
    document.querySelector('#lb-owners-density')?.addEventListener('click', ()=>{
      toggleDense('#lb-owners-body');
      const s = (window.state=window.state||{}); s.lb=s.lb||{};
      s.lb.ownersDense = document.querySelector('#lb-owners-body')?.classList.contains('dense-mode');
    });
    document.querySelector('#lb-bettors-density')?.addEventListener('click', ()=>{
      toggleDense('#lb-bettors-body');
      const s = (window.state=window.state||{}); s.lb=s.lb||{};
      s.lb.bettorsDense = document.querySelector('#lb-bettors-body')?.classList.contains('dense-mode');
    });
    qs('#lb-owners-prev')?.addEventListener('click', ()=>paintOwners((state.lb.ownersPage||1)-1));
    qs('#lb-owners-next')?.addEventListener('click', ()=>paintOwners((state.lb.ownersPage||1)+1));
    qs('#lb-bettors-prev')?.addEventListener('click', ()=>paintBettors((state.lb.bettorsPage||1)-1));
    qs('#lb-bettors-next')?.addEventListener('click', ()=>paintBettors((state.lb.bettorsPage||1)+1));
    document.querySelector('#lb-scorers-search')?.addEventListener('input', debounce(()=>paintScorers(1),200));
    document.querySelector('#lb-scorers-density')?.addEventListener('click', ()=>{
      toggleDense('#lb-scorers-body');
      const s = (window.state=window.state||{}); s.lb=s.lb||{};
      s.lb.scorersDense = document.querySelector('#lb-scorers-body')?.classList.contains('dense-mode');
    });
    document.querySelector('#lb-scorers-refresh')?.addEventListener('click', async ()=>{
      const s=(window.state=window.state||{}); s.lb=s.lb||{}; s.lb.loaded=false; await loadLeaderboardsOnce();
    });
    document.querySelector('#lb-scorers-prev')?.addEventListener('click', ()=>paintScorers((window.state?.lb?.scorersPage||1)-1));
    document.querySelector('#lb-scorers-next')?.addEventListener('click', ()=>paintScorers((window.state?.lb?.scorersPage||1)+1));
    }

    async function loadLeaderboardsOnce(){
    const state=(window.state=window.state||{}); state.lb=state.lb||{};
    if(state.lb.loaded) return;
    try{ await renderLeaderboards(); state.lb.loaded=true; }catch(e){ console.error('Leaderboards error',e); }
    }

    // hook: first time Leaderboards is opened
    function hookNav(){
    const link=[...document.querySelectorAll('#main-menu a')].find(a=>a.dataset.page==='leaderboards');
    if(link){ link.addEventListener('click', ()=>loadLeaderboardsOnce(), {once:true}); }
    const sec=document.querySelector('#leaderboards');
    const obs=new IntersectionObserver((es)=>{ es.forEach(e=>{ if(e.isIntersecting) loadLeaderboardsOnce(); }); }, {root:document.querySelector('#app-main')||null, threshold:0.01});
    sec&&obs.observe(sec);
    }
    document.addEventListener('DOMContentLoaded', hookNav);
})();
