/* app.js - logged-out 3-card grid, logged-in dice-5 grid, Bot Actions fixed */
(() => {
  'use strict';

  const qs = (s, el=document) => el.querySelector(s);
  const qsa = (s, el=document) => [...el.querySelectorAll(s)];
  const sleep = (ms)=>new Promise(r=>setTimeout(r,ms));

  const state = {
    admin:false,
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
  const existing = document.getElementById('user-admin-toggle');
  const shouldShow = !!state.admin; // only show when admin session is unlocked

  // If admin is not unlocked, remove the button if it exists
  if (!shouldShow) {
    if (existing) existing.remove();
    return;
  }

  // If it already exists, just sync the label and exit
  if (existing) {
    existing.textContent = getAdminView() ? 'Public View' : 'Admin View';
    return;
  }

  // Otherwise create it
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

  window.notify = notify;

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

    function esc(s){
      return String(s ?? '').replace(/[&<>"']/g, c => ({
        '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
      }[c]));
    }

    function notifDismissKey(id){ return `wc:notif:dismiss:${id}`; }
    function isDismissed(id){ return localStorage.getItem(notifDismissKey(id)) === '1'; }
    function dismissNotif(id){ localStorage.setItem(notifDismissKey(id), '1'); }

    async function loadNotifications(){
      try{
        const res = await fetch('/api/me/notifications', { cache:'no-store', credentials:'include' });
        if(!res.ok) return [];
        const data = await res.json();
        const items = Array.isArray(data?.items) ? data.items : [];
        return items.filter(it => it && it.id && !it.read && !isDismissed(it.id));
      }catch{
        return [];
      }
    }

    function renderNotifications(items){
      const fab = document.getElementById('notify-fab');
      const panel = document.getElementById('notify-panel');
      const body = document.getElementById('notify-body');
      const close = document.getElementById('notify-close');
      if (!fab || !panel || !body || !close) return;

      // Glow if any
      fab.classList.toggle('has-new', items.length > 0);

      if (!items.length){
        body.innerHTML = `<div class="notify-empty">No New Notifications</div>`;
        return;
      }

      body.innerHTML = items.map(it => {
        const title = esc(it.title || 'Notification');
        const text  = esc(it.body || '');
        const id    = esc(it.id);

        let actionHtml = '';
        const action = it.action || {};

        if (action.kind === 'url' && action.url){
          actionHtml = `<a class="btn small" href="${esc(action.url)}">Open</a>`;
        } else if (action.kind === 'page' && action.page){
          actionHtml = `<button class="btn small" data-open-page="${esc(action.page)}">Open</button>`;
        }

        return `
          <div class="notify-item" data-id="${id}">
            <div class="t">${title}</div>
            <div class="b">${text}</div>
            <div class="a" style="gap:10px; display:flex; justify-content:flex-end;">
              ${actionHtml}
              <button class="btn small" data-dismiss="${id}">Dismiss</button>
            </div>
          </div>
        `;
      }).join('');

      // Wire buttons
      body.querySelectorAll('button[data-dismiss]').forEach(btn=>{
        btn.addEventListener('click', async ()=>{
          const id = btn.getAttribute('data-dismiss');
          if (!id) return;

          // Persist read state on the server (fixes "comes back after refresh" + multi-device)
          try{
            await fetch('/api/me/notifications/read', {
              method: 'POST',
              headers: {'Content-Type':'application/json'},
              credentials: 'include',
              body: JSON.stringify({ id })
            });
          }catch{}

          // keep local dismissal too (fast UI + offline fallback)
          dismissNotif(id);
          btn.closest('.notify-item')?.remove();

          // refresh glow state
          const remaining = body.querySelectorAll('.notify-item').length;
          fab.classList.toggle('has-new', remaining > 0);
          if (remaining === 0) body.innerHTML = `<div class="notify-empty">No New Notifications</div>`;
        });
      });

      body.querySelectorAll('button[data-open-page]').forEach(btn=>{
        btn.addEventListener('click', async ()=>{
          const page = btn.getAttribute('data-open-page');

          try{
            const item = btn.closest('.notify-item');
            const id = item?.getAttribute('data-id');
            if (id){
              await fetch('/api/me/notifications/read', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                credentials: 'include',
                body: JSON.stringify({ id })
              });
              dismissNotif(id);
            }
          }catch{}

          // close panel
          panel.classList.remove('open');
          panel.setAttribute('aria-hidden', 'true');
          fab.setAttribute('aria-expanded', 'false');

          // navigate
          setPage(page);
          await routePage();
        });
      });
    }

    function wireNotifyUIOnce(){
      const fab = document.getElementById('notify-fab');
      const panel = document.getElementById('notify-panel');
      const close = document.getElementById('notify-close');
      if (!fab || !panel || !close) return;
      if (fab._wiredNotify) return;
      fab._wiredNotify = true;

      const openPanel = ()=> {
        panel.classList.add('open');
        panel.setAttribute('aria-hidden','false');
        fab.setAttribute('aria-expanded','true');
      };
      const closePanel = ()=> {
        panel.classList.remove('open');
        panel.setAttribute('aria-hidden','true');
        fab.setAttribute('aria-expanded','false');
      };

      fab.addEventListener('click', async ()=>{
        if (panel.classList.contains('open')){
          closePanel();
          return;
        }
        const items = await loadNotifications();
        renderNotifications(items);
        openPanel();
      });

      close.addEventListener('click', closePanel);

      document.addEventListener('click', (e)=>{
        if (!panel.classList.contains('open')) return;
        const inside = panel.contains(e.target) || fab.contains(e.target);
        if (!inside) closePanel();
      });
    }

    // Notifications polling - drives dot + bell animation
    let _notifPollTimer = null;
    let _lastNotifSig = '';

    async function startNotifPolling(){
      if (_notifPollTimer) return;
      const tick = async () => {
        try {
          const items = await loadNotifications();
          const fab = document.getElementById('notify-fab');
          if (!fab) return;

          const sig = (items || []).map(it => String(it.id || '')).join('|');
          const hasNew = (items || []).length > 0;
          fab.classList.toggle('has-new', hasNew);

          if (sig && sig != _lastNotifSig) {
            // ring only when something changed
            fab.classList.add('ring');
            setTimeout(() => fab.classList.remove('ring'), 1400);
          }
          _lastNotifSig = sig;

          const panel = document.getElementById('notify-panel');
          if (panel && panel.classList.contains('open')) {
            renderNotifications(items || []);
          }
        } catch (e) {
          // ignore
        }
      };

      await tick();
      _notifPollTimer = setInterval(tick, 10000);
    }


    // Real test command that uses the same rendering path
    window.wcTestNotify = async function(){
      wireNotifyUIOnce();
      startNotifPolling();
      const fake = [{
        id: `test:${Date.now()}`,
        type: 'test',
        severity: 'info',
        title: 'Test Notification',
        body: 'This is a manual test notification to confirm the system is working.',
        action: { kind:'page', page:'dashboard' },
        ts: Date.now()
      }];
      renderNotifications(fake);
      document.getElementById('notify-panel')?.classList.add('open');
      document.getElementById('notify-panel')?.setAttribute('aria-hidden','false');
      document.getElementById('notify-fab')?.setAttribute('aria-expanded','true');
    };

    function showTestNotice(text = 'Test notification - everything is alive ✅') {
      const bar = document.getElementById('global-notify');
      const txt = document.getElementById('global-notify-text');
      const link = document.getElementById('global-notify-link');
      const dismiss = document.getElementById('global-notify-dismiss');
      if (!bar || !txt || !link || !dismiss) {
        console.warn('global-notify elements not found in index.html');
        return;
      }

      txt.textContent = text;
      link.textContent = 'Open Terms';
      link.href = '/terms';

      bar.style.display = '';

      dismiss.onclick = () => {
        bar.style.display = 'none';
      };
    }

    window.wcTestNotice = showTestNotice;

    function wireNav(){
      $menu.addEventListener('click', async e=>{
        const a = e.target.closest('a[data-page]'); if(!a) return;
        e.preventDefault();
        const p = a.dataset.page;
        const sec = qs(`#${p}`);
        if(sec && sec.classList.contains('admin-only') && !state.admin){
          notify('Admin required', false);
          return;
        }
        setPage(p);
        await routePage();
      });
    }


    // ===== Admin state (single source of truth) =====
    window.adminUnlocked = false;

    function setAdminUI(unlocked){
      state.admin = !!unlocked;
      document.body.classList.toggle('admin', state.admin);
      applyAdminView();
      ensureAdminToggleButton(); // create/remove FAB based on admin state
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
      const sec = qs(`#${id}`);
      if (!sec) return null;

      sec.innerHTML = '';

      const wrap = document.createElement('div');
      wrap.className = 'table-wrap';

      const head = document.createElement('div');
      head.className = 'table-head';
      head.innerHTML = `<div class="table-title">${title}</div><div class="table-actions"></div>`;

      // Defensive: if something ever nukes the innerHTML, rebuild the actions container
      let actions = head.querySelector('.table-actions');
      if (!actions){
        actions = document.createElement('div');
        actions.className = 'table-actions';
        head.appendChild(actions);
      }

      (controls || []).forEach(([label, meta]) => {
        if (meta && meta.kind === 'input'){
          const inp = document.createElement('input');
          inp.type = 'text';
          inp.id = meta.id;
          inp.placeholder = meta.placeholder || '';
          actions.appendChild(inp);
        } else if (meta && meta.kind === 'select'){
          const sel = document.createElement('select');
          sel.id = meta.id;
          (meta.items || []).forEach(v => {
            const o = document.createElement('option');
            o.value = v;
            o.textContent = v;
            sel.appendChild(o);
          });
          actions.appendChild(sel);
        } else {
          const btn = document.createElement('button');
          btn.className = 'btn';
          if (meta?.id) btn.id = meta.id;
          btn.textContent = label;
          actions.appendChild(btn);
        }
      });

      const scroll = document.createElement('div');
      scroll.className = 'table-scroll';

      wrap.appendChild(head);
      wrap.appendChild(scroll);
      sec.appendChild(wrap);
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
        const current = (ownershipState.stages && ownershipState.stages[row.country]) || '';
        let stageCell = '';
        if (isAdminUI()) {
          // editable select for admins (this is what gets enhanced into the custom dropdown)
          const opts = STAGE_OPTIONS.map(v =>
            `<option value="${v}" ${v === current ? 'selected' : ''}>${v}</option>`
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

      // After all rows are in the DOM, enhance the selects into custom dropdowns
      if (isAdminUI()) {
        enhanceStageSelects();
      }

      // Show/hide admin-only column based on admin view
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
  initStageDropdowns();
}

function enhanceStageSelects() {
  const selects = document.querySelectorAll('#ownership select.stage-select');

  // clean up any old wrappers so re-rendering is safe
  selects.forEach(sel => {
    const wrap = sel.closest('.stage-select-wrap');
    if (wrap) {
      wrap.parentNode.insertBefore(sel, wrap);
      wrap.remove();
    }
  });

  const closeAll = () => {
    document.querySelectorAll('.stage-select-display.open')
      .forEach(btn => btn.classList.remove('open'));
    document.querySelectorAll('.stage-select-list.open')
      .forEach(list => list.classList.remove('open'));
  };

  selects.forEach(sel => {
    const wrap = document.createElement('div');
    wrap.className = 'stage-select-wrap';

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'stage-select-display';
    btn.textContent = sel.options[sel.selectedIndex]?.text || 'Stage';

    const list = document.createElement('ul');
    list.className = 'stage-select-list';

    Array.from(sel.options).forEach(opt => {
      const li = document.createElement('li');
      li.className = 'stage-select-option';
      li.dataset.value = opt.value;
      li.textContent = opt.textContent;
      if (opt.selected) li.classList.add('selected');

      li.addEventListener('click', () => {
        // update select
        sel.value = opt.value;
        sel.dispatchEvent(new Event('change', { bubbles: true }));

        // update button text
        btn.textContent = opt.textContent;

        // update selected state
        list.querySelectorAll('.stage-select-option.selected')
            .forEach(x => x.classList.remove('selected'));
        li.classList.add('selected');

        closeAll();
      });

      list.appendChild(li);
    });

    // insert wrapper before select
    sel.parentNode.insertBefore(wrap, sel);
    wrap.appendChild(btn);
    wrap.appendChild(list);
    wrap.appendChild(sel);
  });

  // global click handler to toggle / close
  document.addEventListener('click', (evt) => {
    const wrap = evt.target.closest('.stage-select-wrap');

    // click outside → close everything
    if (!wrap) {
      closeAll();
      return;
    }

    // click on the button → toggle that one
    const btn = evt.target.closest('.stage-select-display');
    if (btn) {
      const list = wrap.querySelector('.stage-select-list');
      const isOpen = btn.classList.contains('open');
      closeAll();
      if (!isOpen) {
        btn.classList.add('open');
        list.classList.add('open');
      }
    }
  });
}

function initStageDropdowns() {
  const wraps = document.querySelectorAll('#ownership .stage-select-wrap');

  wraps.forEach(wrap => {
    const btn  = wrap.querySelector('.stage-select-display');
    const list = wrap.querySelector('.stage-select-list');
    if (!btn || !list) return;

    btn.addEventListener('click', ev => {
      ev.stopPropagation();

      // close any other open dropdowns
      document.querySelectorAll('#ownership .stage-select-list.open').forEach(ul => {
        if (ul !== list) {
          ul.classList.remove('open');
          ul.closest('.stage-select-wrap')?.classList.remove('drop-up');
        }
      });

      // toggle off if already open
      if (list.classList.contains('open')) {
        list.classList.remove('open');
        wrap.classList.remove('drop-up');
        return;
      }

      // temporarily open to measure height
      list.classList.add('open');
      const listRect = list.getBoundingClientRect();
      const btnRect  = btn.getBoundingClientRect();
      const vh       = window.innerHeight || document.documentElement.clientHeight;

      const spaceBelow = vh - btnRect.bottom;
      const spaceAbove = btnRect.top;
      const needed     = Math.min(listRect.height, 240) + 8; // list + small margin

      // decide direction
      if (spaceBelow < needed && spaceAbove > spaceBelow) {
        wrap.classList.add('drop-up');   // open above
      } else {
        wrap.classList.remove('drop-up'); // open below
      }
    });

    // keep clicks inside from bubbling/closing
    list.addEventListener('click', ev => ev.stopPropagation());
  });

  // click anywhere else closes everything
  document.addEventListener('click', () => {
    document.querySelectorAll('#ownership .stage-select-list.open').forEach(ul => {
      ul.classList.remove('open');
      ul.closest('.stage-select-wrap')?.classList.remove('drop-up');
    });
  });
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
      wireAuthButtons();
      wireNav();
      wireNotifyUIOnce();
      startNotifPolling();
      wireBotButtons();
      setPage(state.currentPage);
      await routePage();
      startPolling();
    }
  window.addEventListener('load', init);

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
  const host       = document.getElementById('map-svg-host');
  const tip        = document.getElementById('map-tip');
  const btnRefresh = document.getElementById('worldmap-refresh');

  if (!host || !tip) return;

  const CACHE_TTL_MS = 60 * 1000; // 60s cache

  function now(){ return Date.now(); }

  function getCache(key){
    try{
      const blob = JSON.parse(localStorage.getItem(key) || 'null');
      if (!blob) return null;
      if ((now() - (blob.ts || 0)) > CACHE_TTL_MS) return null;
      return blob.data;
    }catch(e){
      return null;
    }
  }

  function setCache(key, data){
    try{
      localStorage.setItem(key, JSON.stringify({ ts: now(), data }));
    }catch(e){}
  }

  const fetchJSON = window.fetchJSON || (async function(url){
    const r = await fetch(url, { cache:'no-store' });
    if (!r.ok){
      let body = '';
      try { body = await r.text(); } catch(_){}
      const err = new Error(`HTTP ${r.status} @ ${url}${body ? ` — ${body.slice(0,200)}` : ''}`);
      err.status = r.status;
      err.url = url;
      throw err;
    }
    return await r.json();
  });

    function formatMatchDateShort(isoString){
    if (!isoString) return '';
    const d = new Date(isoString);
    if (Number.isNaN(d.getTime())) return '';
    const day = d.getUTCDate();
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const mon = months[d.getUTCMonth()];
    return `${day} ${mon}`;
  }


  function escapeHtml(str){
    return String(str || '')
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;')
      .replace(/'/g,'&#39;');
  }

  function isoToFlag(iso) {
    if (!iso) return '';
    const code = String(iso).trim().toLowerCase();
    if (!code) return '';

    const safe = code.replace(/[^a-z0-9-]/g, '');
    const url  = `https://flagcdn.com/48x36/${safe}.png`;

    return `<img class="flag-img" src="${url}" alt="${safe} flag" loading="lazy"
            onerror="this.style.display='none';">`;
  }

  // 24h meta cache
  async function loadTeamMeta(){
    const CK  = 'wc:team_meta';
    const TTL = 24 * 60 * 60 * 1000; // 24 hours

    try{
      const blob = JSON.parse(localStorage.getItem(CK) || 'null');
      if (blob && blob.ts && (Date.now() - blob.ts) < TTL && blob.data) {
        return blob.data;
      }
    }catch(e){
      console.warn('team_meta cache parse failed, resetting:', e);
      localStorage.removeItem(CK);
    }

    try{
      const data = await fetchJSON('/api/team_meta');
      localStorage.setItem(CK, JSON.stringify({ ts: Date.now(), data }));
      return data;
    }catch(e){
      console.warn('loadTeamMeta failed:', e);
      return null;
    }
  }

    async function loadTeamStages(){
    const CK = 'wc:team_stage';
    const cached = getCache(CK);
    if (cached) return cached;
    try {
      const data = await fetchJSON('/api/team_stage');
      setCache(CK, data);
      return data || {};
    } catch (e) {
      console.warn('loadTeamStages failed:', e);
      return {};
    }
  }

  async function loadFixtures(){
    try {
      const data = await fetchJSON('/api/fixtures');
      return (data && data.fixtures) || [];
    } catch (e) {
      console.warn('loadFixtures failed:', e);
      return [];
    }
  }


  async function loadTeamIso(){
    const CK = 'wc:team_iso';
    const cached = getCache(CK);
    if (cached) return cached;
    const data = await fetchJSON('/api/team_iso');
    setCache(CK, data);
    return data;
  }

  async function loadOwnership(){
    const CK = 'wc:ownership_merged';
    const cached = getCache(CK);
    if (cached) return cached;
    const data = await fetchJSON('/api/ownership_merged');
    setCache(CK, data);
    return data;
  }

  async function inlineSVG(path){
    const txt = await fetch(path, { cache:'no-store' }).then(r=>{
      if(!r.ok) throw new Error('map svg not found');
      return r.text();
    });
    host.innerHTML = txt;
    const svg = host.querySelector('svg');
    if (!svg) throw new Error('SVG root missing');

    const nodes = svg.querySelectorAll('path[id], polygon[id], rect[id], g[id], [data-iso]');
    let tagged = 0;

    nodes.forEach(el => {
      const raw = (el.getAttribute('data-iso') || el.id || '').trim();
      if (!raw) return;

      let iso = '';

      // GB, FR, etc.
      const m1 = raw.match(/^[A-Za-z]{2}$/);

      // iso-GB, iso_fr, etc.
      const m2 = raw.match(/^iso[-_ ]?([A-Za-z]{2})$/);

      // Subdivisions like gb-eng, gb-sct, gb-wls, gb-nir
      const m3 = raw.match(/^([A-Za-z]{2}[-_][A-Za-z]{2,3})$/);

      if (m1) {
        iso = m1[0].toLowerCase();
      } else if (m2) {
        iso = m2[1].toLowerCase();
      } else if (m3) {
        iso = m3[1].toLowerCase();
      } else {
        return; // ignore non-country shapes
      }

      el.classList.add('country', 'free');
      el.setAttribute('data-iso', iso);
      el.setAttribute('tabindex', '0');
      el.setAttribute('role', 'button');
      el.setAttribute('aria-label', iso.toUpperCase());
      tagged++;
    });

    console.debug('world.svg tagged countries:', tagged);

    ensurePanRoot(svg);
    return svg;
  }

  function normalizeTeamName(name){
    return (name || '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')   // strip accents
      .replace(/['’]/g, '')              // strip apostrophes
      .replace(/\s+/g, ' ')              // collapse spaces
      .trim()
      .toLowerCase();
  }

  function isoToNormTeam(isoToTeam, iso, fallbackTeam){
    const fromIso = isoToTeam[iso] || fallbackTeam || '';
    return normalizeTeamName(fromIso);
  }

  function classifyCountries(svg, teamIso, merged, teamMeta, selfTeams, teamStages, fixtures){
    const rows       = (merged && merged.rows) || [];
    const teamIsoMap = teamIso || {};
    const selfSet    = (selfTeams && typeof selfTeams.has === 'function')
      ? selfTeams
      : new Set();
    const stageMap   = teamStages || {};
    const fixturesList = Array.isArray(fixtures) ? fixtures : [];

    // map normalized team name -> iso from /api/team_iso
    const nameToIso = {};
    Object.entries(teamIsoMap).forEach(([name, iso]) => {
      const norm   = normalizeTeamName(name);
      const lowIso = String(iso || '').toLowerCase();
      if (!norm || !lowIso) return;
      nameToIso[norm] = lowIso;
    });

    const ISO_OVERRIDES = {
      'cote divoire'     : 'ci',
      'cote d ivoire'    : 'ci',
      "cote d'ivoire"    : 'ci',
      'curacao'          : 'cw',
      'curaçao'          : 'cw',
      'england'          : 'gb-eng',
      'scotland'         : 'gb-sct',
      'wales'            : 'gb-wls',
      'northern ireland' : 'gb-nir'
    };

    function inferIsoFromName(name){
      const norm = normalizeTeamName(name);
      return (nameToIso[norm] || ISO_OVERRIDES[norm] || '').toLowerCase();
    }

    // 0) Precompute "next match" per ISO from fixtures
    const nextMatchByIso = {};
    const nowMs = Date.now();

    function considerNext(iso, opponentName, whenStr){
      if (!iso || !opponentName) return;
      iso = String(iso).toLowerCase();

      let whenMs = null;
      if (whenStr) {
        const d = new Date(whenStr);
        if (!Number.isNaN(d.getTime())) whenMs = d.getTime();
      }

      const isFuture = whenMs != null ? (whenMs >= nowMs) : false;
      const labelDate = formatMatchDateShort(whenStr);
      const label = `vs ${opponentName}${labelDate ? ` (${labelDate})` : ''}`;

      const prev = nextMatchByIso[iso];
      if (!prev) {
        nextMatchByIso[iso] = { label, whenMs: whenMs ?? 0, isFuture };
        return;
      }

      // Prefer future over past, then earlier time
      if (isFuture && !prev.isFuture) {
        nextMatchByIso[iso] = { label, whenMs: whenMs ?? 0, isFuture };
        return;
      }
      if (isFuture === prev.isFuture && whenMs != null && whenMs < prev.whenMs) {
        nextMatchByIso[iso] = { label, whenMs: whenMs ?? 0, isFuture };
      }
    }

    fixturesList.forEach(f => {
      if (!f) return;
      const whenStr = f.utc || f.kickoff || f.time || '';
      const homeIso = (f.home_iso || '').toLowerCase();
      const awayIso = (f.away_iso || '').toLowerCase();
      if (homeIso && f.away) considerNext(homeIso, f.away, whenStr);
      if (awayIso && f.home) considerNext(awayIso, f.home, whenStr);
    });

    // 1) team -> ownership state (store both raw and normalized keys)
    const teamState = {};
    for (const row of rows) {
      const team = row.country;
      if (!team) continue;

      const ownersCount = row.owners_count || 0;
      const splits      = row.split_with || [];

      const norm   = normalizeTeamName(team);
      const isSelf = selfSet.has(norm);

      let status = 'free';
      if (ownersCount > 0 && (!splits || splits.length === 0)) status = 'owned';
      if (splits && splits.length > 0) status = 'split';

      // if you are the main owner of this team, mark as self
      if (isSelf && status === 'owned') status = 'self';

      const stateObj = { status, main: row.main_owner, splits: row.split_with };

      if (!teamState[team]) teamState[team] = stateObj;
      if (!teamState[norm]) teamState[norm] = stateObj;
    }

    // 2) build meta lookups (qualified, group) keyed by team name or iso
    const teamQual  = {};
    const teamGroup = {};
    const isoQual   = {};
    const isoGroup  = {};

    if (teamMeta) {
      if (teamMeta.groups) {
        // grouped style: { groups:{A:[...strings or objects...]}, not_qualified:[...optional...] }
        Object.entries(teamMeta.groups).forEach(([g, arr]) => {
          (arr || []).forEach(entry => {
            let tName = '';
            let iso   = '';
            let q     = true; // everything listed in groups is qualified

            if (typeof entry === 'string') {
              tName = entry;
              iso   = inferIsoFromName(tName);
            } else if (entry && typeof entry === 'object') {
              tName = entry.team || entry.name || '';
              iso   = String(entry.iso || '').toLowerCase();
              if (entry.hasOwnProperty('qualified')) {
                q = entry.qualified === true;
              }
            }

            const norm = normalizeTeamName(tName);

            if (tName) {
              teamQual[tName]  = q;
              teamGroup[tName] = g;
            }
            if (norm) {
              teamQual[norm]   = q;
              teamGroup[norm]  = g;
            }
            if (iso) {
              isoQual[iso]  = q;
              isoGroup[iso] = g;
            }
          });
        });

        // optional explicit not_qualified list (strings or objects)
        (teamMeta.not_qualified || []).forEach(entry => {
          let tName = '';
          let iso   = '';

          if (typeof entry === 'string') {
            tName = entry;
            iso   = inferIsoFromName(tName);
          } else if (entry && typeof entry === 'object') {
            tName = entry.team || entry.name || '';
            iso   = String(entry.iso || '').toLowerCase();
          }

          const norm = normalizeTeamName(tName);

          if (tName) {
            teamQual[tName]  = false;
          }
          if (norm) {
            teamQual[norm]   = false;
          }
          if (iso) {
            isoQual[iso]     = false;
          }
        });
      } else {
        // flat object keyed by team / iso, entries can be {team, iso, group, qualified}
        Object.values(teamMeta).forEach(item => {
          if (!item) return;
          const tName = item.team || item.name || '';
          const iso   = String(item.iso || '').toLowerCase();
          const q     = item.qualified !== false; // default true
          const g     = item.group || '';

          const norm = normalizeTeamName(tName);

          if (tName) {
            teamQual[tName]  = q;
            teamGroup[tName] = g;
          }
          if (norm) {
            teamQual[norm]   = q;
            teamGroup[norm]  = g;
          }
          if (iso) {
            isoQual[iso]     = q;
            isoGroup[iso]    = g;
          }
        });
      }
    }

    // iso -> team label from /api/team_iso
    const isoToTeam = {};
    Object.entries(teamIsoMap).forEach(([name, iso]) => {
      const norm   = normalizeTeamName(name);
      const lowIso = String(iso || '').toLowerCase();
      if (!norm || !lowIso) return;
      isoToTeam[lowIso] = name;
    });

    svg.querySelectorAll('.country').forEach(el => {
      const isoRaw = (el.getAttribute('data-iso') || '').toLowerCase();
      if (!isoRaw) return;

      const iso   = isoRaw;
      const isoUp = iso.toUpperCase();

      // from ISO to team name
      const team     = isoToTeam[iso] || isoUp;
      const normTeam = normalizeTeamName(team);

      // derive iso from name when needed
      const inferIso = inferIsoFromName(team) || iso;

      const teamLabel = team;

      // default: mark as not qualified when meta exists and does not say otherwise
      let status = 'nq';

      let qualified = true;
      if (teamMeta) {
        qualified = (
          teamQual[team]     === true ||
          teamQual[normTeam] === true ||
          isoQual[iso]       === true
        );
      }

      // ownership by name
      let ownership = null;
      if (team || normTeam) {
        ownership = teamState[team] || teamState[normTeam] || null;
      }

      if (qualified) {
        status = 'free';
        if (ownership) status = ownership.status;
      } else if (!teamMeta) {
        // if no meta at all, fall back to ownership only
        status = ownership ? ownership.status : 'free';
      }

      // owners list for tooltip + details
      const ownerNames = [];
      let mainName = '';
      let coNames  = '';

      if (ownership) {
        const main   = ownership.main;
        const splits = ownership.splits || [];
        if (main && main.username) {
          mainName = main.username;
          ownerNames.push(main.username);
        }
        if (splits && splits.length) {
          const sNames = splits.map(s => s && s.username).filter(Boolean);
          if (sNames.length) {
            coNames = sNames.join(', ');
            ownerNames.push(...sNames);
          }
        }
      }

      const ownersText  = ownerNames.length ? ownerNames.join(', ') : 'Unassigned';
      const ownersCount = ownerNames.length;

      // equal-split prize share text (only if there are owners)
      let prizeShare = '';
      if (ownersCount > 0) {
        const base = Math.floor(100 / ownersCount);
        const rem  = 100 - base * ownersCount;
        const parts = [];
        for (let i = 0; i < ownersCount; i++) {
          const v = base + (i < rem ? 1 : 0);
          parts.push(`${v}%`);
        }
        prizeShare = parts.join(' / ');
      }

      const flag  = isoToFlag(inferIso || iso);
      const group = (teamGroup[team] || teamGroup[normTeam] || isoGroup[iso] || '') || '';

      // tournament stage
      let stage = (stageMap[team] || stageMap[normTeam]) || '—';

      // map fixtures to this ISO
      const matchObj = nextMatchByIso[iso] || nextMatchByIso[inferIso] || null;
      const nextMatch = matchObj ? matchObj.label : '';

      // apply base status classes (self/owned/split/free/nq)
      el.classList.remove('owned','split','free','nq','dim','self');
      el.classList.add(status);

      // datasets for tooltip + group filter + self-owner overlay + info card
      el.dataset.owners      = ownersText;
      el.dataset.team        = teamLabel;
      el.dataset.group       = group;
      el.dataset.iso         = isoUp;
      el.dataset.flag        = flag;
      el.dataset.stage       = stage || '';
      el.dataset.mainOwner   = mainName || '';
      el.dataset.coOwners    = coNames || '';
      el.dataset.ownersCount = String(ownersCount);
      el.dataset.prizeShare  = prizeShare || '';
      el.dataset.nextMatch   = nextMatch || '';

      // tooltip handlers
      el.onmouseenter = ev => {
        const flagPrefix = flag ? flag + ' ' : '';
        const teamLine   = `${flagPrefix}<strong>${escapeHtml(teamLabel)}</strong>`;
        const ownerLine  = ownersText ? `Owners: ${escapeHtml(ownersText)}` : 'Owners: Unassigned';

        tip.innerHTML = `
          <div class="map-info">
            <h3>${teamLine}</h3>
            <p>${ownerLine}</p>
            ${group ? `<p>Group: ${escapeHtml(group)}</p>` : ''}
          </div>`;
        tip.style.opacity = '1';
        positionTip(ev);
      };
      el.onmousemove  = ev => positionTip(ev);
      el.onmouseleave = () => { tip.style.opacity = '0'; };
    });
  }

  let currentGroup = 'ALL';

  function populateGroupSelector(teamMeta){
    const sel = document.getElementById('map-group');
    if (!sel) return;

    if (!teamMeta) {
      sel.innerHTML = '<option value="ALL" selected>All</option>';
      return;
    }

    const groups = new Set();
    if (teamMeta.groups){
      Object.keys(teamMeta.groups).forEach(g => groups.add(g));
    } else {
      Object.values(teamMeta).forEach(m => { if (m.group) groups.add(m.group); });
    }

    const sorted = [...groups].sort();
    sel.innerHTML = '<option value="ALL" selected>All</option>' +
      sorted.map(g => `<option value="${g}">Group ${g}</option>`).join('');
  }

  function applyGroupFilter(svg){
    svg.querySelectorAll('.country').forEach(el=>{
      const g = (el.dataset.group || '').toUpperCase();
      if (currentGroup === 'ALL' || (g && g === currentGroup.toUpperCase())){
        el.classList.remove('dim');
      } else {
        el.classList.add('dim');
      }
    });
  }

  // Tooltip positioning - relative to #map-wrap
  const wrap = document.getElementById('map-wrap');

  function positionTip(ev) {
    if (!wrap || !tip) return;

    const r       = wrap.getBoundingClientRect();
    const tipRect = tip.getBoundingClientRect();

    let x = ev.clientX - r.left + 6;
    let y = ev.clientY - r.top  - tipRect.height - 2;

    if (y < 2) y = ev.clientY - r.top + 10;

    if (x + tipRect.width > r.width - 4) {
      x = r.width - tipRect.width - 4;
    }
    if (x < 4) x = 4;

    tip.style.left = `${x}px`;
    tip.style.top  = `${y}px`;
  }

  function ensurePanRoot(svg){
    const existing = svg.querySelector('#wc-panroot');
    if (existing) return existing;

    const panRoot = document.createElementNS('http://www.w3.org/2000/svg','g');
    panRoot.setAttribute('id','wc-panroot');

    const keep   = new Set(['defs','title','desc','metadata']);
    const toMove = [];
    [...svg.childNodes].forEach(n=>{
      if (n.nodeType === 1 && keep.has(n.nodeName.toLowerCase())) return;
      toMove.push(n);
    });
    toMove.forEach(n => panRoot.appendChild(n));
    svg.appendChild(panRoot);
    return panRoot;
  }

  function enableClickZoom(svg){
    const infoBox = document.getElementById('map-country-info');

    let origViewBox = svg.getAttribute('viewBox');
    if (!origViewBox) {
      const r = svg.getBBox();
      origViewBox = `${r.x} ${r.y} ${r.width} ${r.height}`;
      svg.setAttribute('viewBox', origViewBox);
    }

    let currentCountry = null;
    let animating      = false;

    function lerp(a, b, t){ return a + (b - a) * t; }

    function parseViewBox(vb){
      const [x, y, w, h] = vb.split(/\s+/).map(Number);
      return { x, y, w, h };
    }

    function viewBoxToString({x, y, w, h}){
      return `${x} ${y} ${w} ${h}`;
    }

    function animateViewBox(start, end, duration){
      if (animating) return;
      let startTime = null;
      animating = true;
      svg.classList.add('zooming');

      function step(ts){
        if (!startTime) startTime = ts;
        const t    = Math.min(1, (ts - startTime) / duration);
        const ease = t < 0.5
          ? 4 * t * t * t
          : 1 - Math.pow(-2 * t + 2, 3) / 2;

        const cur = {
          x: lerp(start.x, end.x, ease),
          y: lerp(start.y, end.y, ease),
          w: lerp(start.w, end.w, ease),
          h: lerp(start.h, end.h, ease)
        };
        svg.setAttribute('viewBox', viewBoxToString(cur));

        if (t < 1) {
          requestAnimationFrame(step);
        } else {
          animating = false;
          svg.classList.remove('zooming');
        }
      }

      requestAnimationFrame(step);
    }

    function zoomToElement(el, zoomFactor = 1.75){
      const bbox = el.getBBox();
      if (!bbox || !isFinite(bbox.x)) return;

      const targetW = bbox.width  * zoomFactor;
      const targetH = bbox.height * zoomFactor;
      const targetX = bbox.x + bbox.width  / 2 - targetW / 2;
      const targetY = bbox.y + bbox.height / 2 - targetH / 2;

      const start = parseViewBox(svg.getAttribute('viewBox'));
      const end   = { x: targetX, y: targetY, w: targetW, h: targetH };

      animateViewBox(start, end, 400);
    }

    function resetZoom(){
      const start = parseViewBox(svg.getAttribute('viewBox'));
      const end   = parseViewBox(origViewBox);
      animateViewBox(start, end, 350);
    }

    svg.addEventListener('click', (ev)=>{
      const el = ev.target.closest('.country');
      if (!el) {
        if (currentCountry) {
          currentCountry.classList.remove('active');
          currentCountry = null;
          infoBox && infoBox.classList.add('hidden');
        }
        resetZoom();
        return;
      }

      if (currentCountry === el) {
        currentCountry.classList.remove('active');
        currentCountry = null;
        infoBox && infoBox.classList.add('hidden');
        resetZoom();
        return;
      }

      if (currentCountry) {
        currentCountry.classList.remove('active');
      }
      el.classList.add('active');
      currentCountry = el;

      const name        = el.dataset.team   || el.dataset.iso || 'Unknown';
      const flag        = el.dataset.flag   || '';
      const group       = el.dataset.group  || '—';
      const owners      = el.dataset.owners || 'Unassigned';
      const stage       = el.dataset.stage  || '';
      const mainOwner   = el.dataset.mainOwner   || '';
      const coOwners    = el.dataset.coOwners    || '';
      const ownersCount = el.dataset.ownersCount || '';
      const nextMatch   = el.dataset.nextMatch   || '';
      const prizeShare  = el.dataset.prizeShare  || '';

      const isSplit =
        el.classList.contains('split') ||
        (ownersCount && parseInt(ownersCount, 10) > 1);

      const status =
        el.classList.contains('self')  ? 'Owned (Self)'   :
        el.classList.contains('owned') ? 'Owned (Other)'  :
        el.classList.contains('split') ? 'Split'          :
        el.classList.contains('nq')    ? 'Not Qualified'  :
                                         'Unassigned';

      const nameEl   = document.getElementById('map-info-name');
      const flagEl   = document.getElementById('map-info-flag');
      const groupEl  = document.getElementById('map-info-group');
      const stageEl  = document.getElementById('map-info-stage');
      const mainEl   = document.getElementById('map-info-main');
      const coEl     = document.getElementById('map-info-coowners');
      const nextEl   = document.getElementById('map-info-next');
      const shareEl  = document.getElementById('map-info-share');
      const statusEl = document.getElementById('map-info-status');

      if (nameEl)   nameEl.textContent   = name;
      if (flagEl)   flagEl.innerHTML     = flag;
      if (groupEl)  groupEl.textContent  = 'Group: ' + (group || '—');
      if (stageEl)  stageEl.textContent  = 'Stage: ' + (stage || '—');
      if (mainEl)   mainEl.textContent   = 'Main Owner: ' + (mainOwner || (owners !== 'Unassigned' ? owners : '—'));
      if (nextEl)   nextEl.textContent   = 'Next Match: ' + (nextMatch || '—');
      if (statusEl) statusEl.textContent = 'Status: ' + status;

      if (coEl) {
        if (isSplit) {
          coEl.style.display = '';
          coEl.textContent = 'Co-Owners: ' + (coOwners || '—');
        } else {
          coEl.style.display = 'none';
        }
      }

      // Prize Share — only visible for split teams
      if (shareEl) {
        if (isSplit && prizeShare) {
          shareEl.style.display = '';
          shareEl.textContent = 'Prize Share: ' + prizeShare;
        } else {
          shareEl.style.display = 'none';
        }
      }

      if (infoBox) infoBox.classList.remove('hidden');

      zoomToElement(el, 1.75);
    });
  }

  async function loadSelfOwnership(){
    try {
      const data   = await fetchJSON('/api/me/ownership');
      const selfSet = new Set();

      if (data && Array.isArray(data.owned)) {
        for (const row of data.owned) {
          if (row && row.team) {
            selfSet.add(normalizeTeamName(row.team));
          }
        }
      }
      return selfSet;
    } catch (e) {
      console.warn('loadSelfOwnership failed:', e);
      return new Set();
    }
  }

  async function render(){
    try {
      console.time('worldmap:fetch');
      const [iso, merged, meta, selfTeams, stages, fixtures] = await Promise.all([
        loadTeamIso(),
        loadOwnership(),
        loadTeamMeta(),
        loadSelfOwnership(),
        loadTeamStages(),
        loadFixtures()
      ]);
      console.debug('team_iso ok:', Object.keys(iso || {}).length, 'entries');
      console.debug('ownership_merged ok:', (merged?.rows?.length || 0), 'rows');
      console.debug('team_meta:', meta ? 'loaded' : 'absent');
      console.debug('self ownership:', selfTeams ? selfTeams.size : 0, 'teams');
      console.debug('team_stage entries:', stages ? Object.keys(stages).length : 0);
      console.debug('fixtures count:', fixtures ? fixtures.length : 0);
      console.timeEnd('worldmap:fetch');

      const svg = await inlineSVG('world.svg');

      classifyCountries(svg, iso, merged, meta, selfTeams, stages, fixtures);
      populateGroupSelector(meta);
      applyGroupFilter(svg);

      const sel = document.getElementById('map-group');
      if (sel){
        sel.onchange = ()=>{
          currentGroup = sel.value || 'ALL';
          applyGroupFilter(svg);
        };
      }

      enableClickZoom(svg);

    } catch (e) {
      console.error('Map render error:', e);
      host.innerHTML = `
        <div class="muted" style="padding:10px;">
          Failed to load map. Ensure world.svg and API endpoints exist.
        </div>`;
    }
  }

  if (btnRefresh){
    btnRefresh.addEventListener('click', ()=>{
      localStorage.removeItem('wc:ownership_merged');
      localStorage.removeItem('wc:team_iso');
      localStorage.removeItem('wc:team_meta');
      localStorage.removeItem('wc:team_stage');
      render();
    });
  }

  const menu = document.getElementById('main-menu');
  if (menu){
    menu.addEventListener('click', (e)=>{
      const a = e.target.closest('a[data-page]');
      if (!a) return;
      if (a.getAttribute('data-page') === 'worldmap'){
        setTimeout(render, 10);
      }
    });
  }

  if (document.querySelector('#worldmap.active-section')){
    render();
  }

  // Daily silent refresh of team_meta (and re-render if on World Map)
  (function setupDailyMetaRefresh(){
    const DAY = 24 * 60 * 60 * 1000;
    setInterval(async ()=>{
      try{
        const blob = JSON.parse(localStorage.getItem('wc:team_meta') || 'null');
        if (!blob || (Date.now() - (blob.ts || 0)) >= DAY) {
          localStorage.removeItem('wc:team_meta');
          const isActive = document.querySelector('#worldmap.active-section');
          if (isActive) render();
        }
      }catch{
        localStorage.removeItem('wc:team_meta');
      }
    }, DAY);
  })();
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

// ---------------- Fan Zone (fixtures + voting) ----------------
(() => {
  const $ = (sel) => document.querySelector(sel);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const notify = window.notify || ((msg) => console.log('[notify]', msg));
  const fetchJSON = window.fetchJSON || (async (url, opts) => {
    const r = await fetch(url, { cache: 'no-store', ...opts });
    if (!r.ok) throw new Error(await r.text().catch(() => r.statusText));
    return r.json();
  });

  const normalize = (s) => {
    return String(s || '')
      .trim()
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '');
  };

  async function loadTeamMetaFast(){
    const CK  = 'wc:team_meta';
    const TTL = 24 * 60 * 60 * 1000;

    try {
      const blob = JSON.parse(localStorage.getItem(CK) || 'null');
      if (blob && blob.ts && (Date.now() - blob.ts) < TTL && blob.data) return blob.data;
    } catch {
      try { localStorage.removeItem(CK); } catch {}
    }

    try {
      const data = await fetchJSON('/api/team_meta');
      try { localStorage.setItem(CK, JSON.stringify({ ts: Date.now(), data })); } catch {}
      return data;
    } catch {
      return null;
    }
  }

  function buildTeamToGroup(teamMeta){
    const out = new Map();
    if (!teamMeta) return out;

    // Preferred: { groups: { A:[...teams], B:[...teams] } }
    if (teamMeta.groups && typeof teamMeta.groups === 'object') {
      for (const [g, arr] of Object.entries(teamMeta.groups)) {
        if (!Array.isArray(arr)) continue;
        arr.forEach(t => {
          const k = normalize(t);
          if (k) out.set(k, String(g || '').toUpperCase());
        });
      }
      return out;
    }

    // Fallback: { "Argentina": { group:"A", ... }, ... }
    if (typeof teamMeta === 'object') {
      for (const [team, meta] of Object.entries(teamMeta)) {
        const g = meta && typeof meta === 'object' ? meta.group : null;
        const k = normalize(team);
        if (k && g) out.set(k, String(g).toUpperCase());
      }
    }
    return out;
  }

  function populateFanZoneGroupSelector(teamMeta){
    const sel = document.getElementById('fanzone-group');
    if (!sel) return;

    const prev = String(sel.value || 'ALL').toUpperCase();

    const groups = new Set();
    if (teamMeta && teamMeta.groups) {
      Object.keys(teamMeta.groups).forEach(g => groups.add(String(g).toUpperCase()));
    } else if (teamMeta && typeof teamMeta === 'object') {
      Object.values(teamMeta).forEach(m => { if (m && m.group) groups.add(String(m.group).toUpperCase()); });
    }

    const sorted = [...groups].sort();
    sel.innerHTML = '<option value="ALL">All groups</option>' +
      sorted.map(g => `<option value="${g}">Group ${g}</option>`).join('');

    // restore selection if still valid
    const wanted = prev && (prev === 'ALL' || groups.has(prev)) ? prev : 'ALL';
    sel.value = wanted;
  }

    function getFanFilterEls(){
      return {
        sel: document.getElementById('fanzone-group'),
        inp: document.getElementById('fanzone-country'),
      };
    }

    function resetFanZoneFilters(){
      const { sel, inp } = getFanFilterEls();
      if (sel) sel.value = 'ALL';
      if (inp) inp.value = '';
    }

    function applyFanZoneFilters(){
      const { sel, inp } = getFanFilterEls();

      const group = String(sel?.value || 'ALL').toUpperCase();
      const q = normalize(inp?.value || '');

      const cards = Array.from(document.querySelectorAll('#fanzone-list .fan-card'));
      for (const card of cards) {
        const g = String(card.dataset.group || '').toUpperCase();
        const teams = normalize(card.dataset.teams || '');

        const okGroup = (group === 'ALL') || (g && g === group);
        const okCountry = !q || teams.includes(q);

        card.style.display = (okGroup && okCountry) ? '' : 'none';
      }
    }

  // If you already have isAdminUI() elsewhere, we use it.
  // Fallback: treat body.admin as admin.
  const isAdminUI = (typeof window.isAdminUI === 'function')
    ? window.isAdminUI
    : (() => document.body.classList.contains('admin'));

  async function getFixtures() {
    const d = await fetchJSON('/api/fixtures');
    return (d && d.fixtures) || [];
  }

  async function getStats(fid) {
    const d = await fetchJSON(`/api/fanzone/${encodeURIComponent(fid)}`);
    return d || { ok: false };
  }

    async function sendVote(fid, choice) {
      const res = await fetch('/api/fanzone/vote', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fixture_id: fid, choice })
      });

      if (res.status === 409) {
        throw new Error('voting_closed');
      }

      if (!res.ok) {
        throw new Error('vote_failed');
      }

      return res.json();
    }

  function flagImg(iso) {
    if (!iso) return '';
    return `<img class="fan-flag" alt="${iso}" src="https://flagcdn.com/w40/${iso}.png" loading="lazy">`;
  }

  function pct(n) {
    return Math.max(0, Math.min(100, Number.isFinite(n) ? n : 0)).toFixed(0);
  }

  function escAttr(s){
    return String(s || '')
      .replace(/&/g,'&amp;')
      .replace(/</g,'&lt;')
      .replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;')
      .replace(/'/g,'&#39;');
  }

  function cardHTML(f, stats) {
    const hp = pct(stats?.home_pct || 0);
    const ap = pct(stats?.away_pct || 0);
    const total = stats?.total || 0;
    const last = stats?.last_choice;

    const votedHome = last === 'home';
    const votedAway = last === 'away';
    const votedClass = votedHome ? 'voted-home' : votedAway ? 'voted-away' : '';

    const adminControls = (isAdminUI()) ? `
      <span class="fan-win-wrap" data-admin="true">
        <button class="btn xs fan-win" type="button" data-side="home" data-team="${f.home}" data-iso="${f.home_iso || ''}">
          Declare ${f.home}
        </button>
        <button class="btn xs fan-win" type="button" data-side="away" data-team="${f.away}" data-iso="${f.away_iso || ''}">
          Declare ${f.away}
        </button>
      </span>
    ` : '';

    return `
      <div class="fan-card ${votedClass}" data-fid="${f.id}" data-group="${escAttr(f._group || '')}" data-teams="${escAttr(`${f.home} ${f.away}`)}">
        <div class="fan-head">
          <div class="fan-team">
            ${flagImg(f.home_iso)} <span class="fan-team-name">${f.home}</span>
          </div>
          <div class="fan-vs">vs</div>
          <div class="fan-team">
            ${flagImg(f.away_iso)} <span class="fan-team-name">${f.away}</span>
          </div>
        </div>

        <div class="fan-time">${(f.utc || '').replace('T',' ').replace('Z',' UTC')}</div>

        <div class="fan-bars">
          <div class="fan-bar-row">
            <div class="fan-bar fan-bar-home" style="width:${hp}%">
              <span>${hp}%</span>
            </div>
          </div>
          <div class="fan-bar-row">
            <div class="fan-bar fan-bar-away" style="width:${ap}%">
              <span>${ap}%</span>
            </div>
          </div>
        </div>

        <div class="fan-actions">
          <button class="btn fan-vote home ${votedHome ? 'active' : ''}" data-choice="home" ${last ? 'disabled' : ''}>
            Vote ${f.home}
          </button>
          <button class="btn fan-vote away ${votedAway ? 'active' : ''}" data-choice="away" ${last ? 'disabled' : ''}>
            Vote ${f.away}
          </button>
        </div>

        <div class="fan-foot">
          <span class="muted">Total votes: <strong class="fan-total">${total}</strong></span>
          ${last ? `<span class="pill pill-ok">You voted: ${last}</span>` : ''}
          ${adminControls}
        </div>
      </div>
    `;
  }

    function applyStatsToCard(card, stats) {
  if (!card || !stats) return;

  // Vote buttons
  const btnHome = card.querySelector('.fan-vote[data-choice="home"]');
  const btnAway = card.querySelector('.fan-vote[data-choice="away"]');

  // Percent bars (matches cardHTML markup: .fan-bar-home/.fan-bar-away each contains a <span>)
  const barHome = card.querySelector('.fan-bar-home');
  const barAway = card.querySelector('.fan-bar-away');
  const barHomePct = barHome ? barHome.querySelector('span') : null;
  const barAwayPct = barAway ? barAway.querySelector('span') : null;

  // Totals
  const totalEl = card.querySelector('.fan-total');

  const hp = Math.max(0, Math.min(100, Number(stats.home_pct || 0)));
  const ap = Math.max(0, Math.min(100, Number(stats.away_pct || 0)));

  if (barHome) barHome.style.width = `${hp}%`;
  if (barAway) barAway.style.width = `${ap}%`;
  if (barHomePct) barHomePct.textContent = `${hp.toFixed(0)}%`;
  if (barAwayPct) barAwayPct.textContent = `${ap.toFixed(0)}%`;

  if (totalEl) totalEl.textContent = String(Number(stats.total || 0));

  // "You voted" state (this is what brings the outline back)
  const last = String(stats.last_choice || stats.last || '').toLowerCase(); // "home"|"away"|""
  if (btnHome) btnHome.classList.toggle('active', last === 'home');
  if (btnAway) btnAway.classList.toggle('active', last === 'away');
  card.classList.toggle('voted-home', last === 'home');
  card.classList.toggle('voted-away', last === 'away');

    const winner = String(stats.winner || stats.winner_side || '').toLowerCase();
    const isLocked = (winner === 'home' || winner === 'away');

    if (isLocked) {
      card.classList.add('locked');
      card.dataset.winner = winner;

      card.querySelectorAll('.fan-vote, .fan-win').forEach(b => {
        b.disabled = true;
      });
    } else {
      card.classList.remove('locked');
      delete card.dataset.winner;
    }

  if (btnHome) btnHome.disabled = isLocked || !!last;
  if (btnAway) btnAway.disabled = isLocked || !!last;

  // Lock visuals + disable Admin "Declare" buttons too
  card.classList.toggle('locked', isLocked);
  card.dataset.winner = isLocked ? winner : '';

  const declareBtns = card.querySelectorAll('.fan-win');
  declareBtns.forEach(b => { b.disabled = isLocked; });

  // Optional winner highlight classes if you want them
  card.classList.toggle('winner-home', isLocked && winner === 'home');
  card.classList.toggle('winner-away', isLocked && winner === 'away');

  // Update the little pill if present
  const pill = card.querySelector('.pill.pill-ok');
  if (pill) pill.textContent = last ? `You voted: ${last}` : '';
}

    async function refreshVisibleCards() {
    const cards = Array.from(document.querySelectorAll('#fanzone-list .fan-card'));
    if (!cards.length) return;

    for (const card of cards) {
      const fid = card.dataset.fid;
      try {
        const stats = await getStats(fid);
        if (stats?.ok) applyStatsToCard(card, stats);
      } catch { /* ignore */ }
    }
    }

    async function declareFanZoneWinner(matchId, side) {
      const res = await fetch('/admin/fanzone/declare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          match_id: String(matchId),
          winner: String(side) // "home" or "away" (or "" to clear)
        })
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) {
        throw new Error(data?.error || `declare_failed_${res.status}`);
      }
      return data;
    }

  async function renderFanZone() {
    const host = $('#fanzone-list');
    if (!host) return;

    const teamMeta = await loadTeamMetaFast();
    populateFanZoneGroupSelector(teamMeta);
        if (host.dataset.fanFiltersInit !== '1') {
        resetFanZoneFilters();
        host.dataset.fanFiltersInit = '1';
        }
    const teamToGroup = buildTeamToGroup(teamMeta);

    host.innerHTML = `<div class="muted" style="padding:12px">Loading fixtures…</div>`;

    let fixtures = [];
    try {
      fixtures = await getFixtures();
    } catch {
      host.innerHTML = `<div class="muted" style="padding:12px">No fixtures available.</div>`;
      return;
    }

    // decorate fixtures with group so we can filter
    fixtures.forEach(f => {
      const gh = teamToGroup.get(normalize(f?.home)) || '';
      const ga = teamToGroup.get(normalize(f?.away)) || '';
      f._group = gh || ga || '';
    });

    if (!fixtures.length) {
      host.innerHTML = `<div class="muted" style="padding:12px">No fixtures available.</div>`;
      return;
    }

    host.innerHTML = fixtures.map(f => `
      <div class="fan-card" data-fid="${f.id}" data-group="${escAttr(f._group || '')}" data-teams="${escAttr(`${f.home} ${f.away}`)}">
        <div class="muted" style="padding:12px">Loading…</div>
      </div>
    `).join('');

    for (const f of fixtures) {
      const stats = await getStats(f.id).catch(() => null);
      const card = host.querySelector(`.fan-card[data-fid="${CSS.escape(f.id)}"]`);
      if (card) card.outerHTML = cardHTML(f, stats);
    }

    applyFanZoneFilters();

    // One click handler for both vote + declare winner
    if (host.dataset.fanWired === '1') return;
    host.dataset.fanWired = '1';
    host.addEventListener('click', async (ev) => {

      // --- Admin declare winner ---
      const winBtn = ev.target.closest('.fan-win');
      if (winBtn) {
        if (!isAdminUI()) {
          notify('Admin required', false);
          return;
        }

        const card = winBtn.closest('.fan-card');
        if (!card) return;

          if (card.dataset.winner === 'home' || card.dataset.winner === 'away') {
            notify('This match has already been declared and is locked.', false);
            return;
  }

        const fid = card.dataset.fid;
        if (!fid) return;

        const side = String(winBtn.dataset.side || '').toLowerCase();
        if (side !== 'home' && side !== 'away') return;

        const winnerTeam = String(winBtn.dataset.team || '').trim();

        try {
          const r = await declareFanZoneWinner(fid, side);
          if (r && r.ok) {
            notify(`Winner declared: ${winnerTeam || side}`, true);
          } else {
            notify('Failed to declare winner', false);
          }
          await refreshVisibleCards();
        } catch (e) {
          console.error(e);
          notify('Failed to declare winner', false);
        }

        return;
      }

    // --- Public vote ---
    const voteBtn = ev.target.closest('.fan-vote');
    if (!voteBtn) return;

    const card = voteBtn.closest('.fan-card');
    const fid = card?.dataset?.fid;
    const choice = voteBtn?.dataset?.choice;
    if (!fid || !choice) return;

    // If already locked (winner declared), do not even try
    if (card?.dataset?.winner) {
      notify('Voting is locked for this match', false);
      return;
    }

    // Disable immediately to prevent spam clicks
    card.querySelectorAll('.fan-vote').forEach(b => b.disabled = true);

    try {
      await sendVote(fid, choice);
    } catch (err) {
      if (String(err?.message).includes('voting_closed')) {
        // HARD LOCK from server (winner declared between refresh + click)
        card.dataset.winner = 'locked';
        card.classList.add('locked');
        card.querySelectorAll('.fan-vote').forEach(b => b.disabled = true);
        notify('Voting is locked for this match', false);
        return;
      }
      await sleep(400);
    } finally {
      const stats = await getStats(fid).catch(() => null);
      if (stats?.ok) applyStatsToCard(card, stats);
    }
    }, { once: false });
  }

  // Public loader (call when entering the page)
  window.loadFanZone = async function loadFanZone() {
    await renderFanZone();
  };

  // Auto-refresh while the Fan Zone section is visible
  let fanTimer = null;
  function ensureFanRefresh() {
    clearInterval(fanTimer);
    fanTimer = setInterval(async () => {
      const sec = document.querySelector('#fanzone.page-section.active-section');
      if (!sec) return;
      await refreshVisibleCards();
    }, 20000);
  }

    function ensureFanFilterWiring(){
      const { sel, inp } = getFanFilterEls();
      if (!sel && !inp) return;

      // prevent double-wiring
      const key = sel || inp;
      if (key && key.dataset.wired === '1') return;
      if (key) key.dataset.wired = '1';

      sel && sel.addEventListener('change', applyFanZoneFilters);
      inp && inp.addEventListener('input', applyFanZoneFilters);
    }

  // When Fan Zone is selected, load + start refresher
  document.addEventListener('click', (e) => {
    const a = e.target.closest('a[data-page="fanzone"]');
    if (!a) return;
    setTimeout(() => { ensureFanFilterWiring(); window.loadFanZone(); ensureFanRefresh(); }, 50);
  });

    document.addEventListener('click', (e) => {
      if (e.target.id === 'fanzone-refresh') {
        ensureFanFilterWiring();
        resetFanZoneFilters();
        window.loadFanZone();
      }
    });

  // If landing directly on Fan Zone
  window.addEventListener('DOMContentLoaded', () => {
    if (document.querySelector('#fanzone.page-section.active-section')) {
      ensureFanFilterWiring();
      window.loadFanZone();
      ensureFanRefresh();
    }
  });
})();
