(() => {
  'use strict';

  const qs = (s, el=document) => el.querySelector(s);
  const qsa = (s, el=document) => [...el.querySelectorAll(s)];
  const sleep = (ms)=>new Promise(r=>setTimeout(r,ms));

  const TIMEZONE_STORAGE_KEY = 'wc:timeZone';
  const DATE_FORMAT_STORAGE_KEY = 'wc:dateFormat';
  if (!window.TIMEZONE_STORAGE_KEY) window.TIMEZONE_STORAGE_KEY = TIMEZONE_STORAGE_KEY;
  if (!window.DATE_FORMAT_STORAGE_KEY) window.DATE_FORMAT_STORAGE_KEY = DATE_FORMAT_STORAGE_KEY;

  // Bootstrap shared stage constants in-app so the dashboard does not depend on
  // a separate stage.js request. This prevents a missing static asset from
  // breaking stage labels/progress in app.js and user.js.
  if (!window.WorldCupStages) {
    const STAGE_ORDER = [
      'Eliminated',
      'Group Stage',
      'Round of 32',
      'Round of 16',
      'Quarter-finals',
      'Semi-finals',
      'Third Place Play-off',
      'Final',
      'Winner',
    ];

    const STAGE_ALIASES = {
      Group: 'Group Stage',
      R32: 'Round of 32',
      R16: 'Round of 16',
      QF: 'Quarter-finals',
      SF: 'Semi-finals',
      F: 'Final',
      'Quarter Final': 'Quarter-finals',
      'Quarter Finals': 'Quarter-finals',
      'Semi Final': 'Semi-finals',
      'Semi Finals': 'Semi-finals',
      'Third Place': 'Third Place Play-off',
      'Third Place Play': 'Third Place Play-off',
      'Third Place Playoff': 'Third Place Play-off',
      '3rd Place Play-off': 'Third Place Play-off',
      'Second Place': 'Final',
    };

    const STAGE_PROGRESS = {
      Eliminated: 0,
      'Group Stage': 15,
      'Round of 32': 25,
      'Round of 16': 35,
      'Quarter-finals': 55,
      'Semi-finals': 70,
      'Third Place Play-off': 80,
      Final: 90,
      Winner: 100,
    };

    function normalizeStage(label) {
      const s = String(label || '').trim();
      return STAGE_ALIASES[s] || s;
    }

    window.WorldCupStages = {
      STAGE_ORDER,
      STAGE_ALIASES,
      STAGE_PROGRESS,
      normalizeStage,
    };
  }

  const state = {
    admin:false,
    currentPage: localStorage.getItem('wc:lastPage') || 'dashboard',
    pollingId: null,
    logsKind: 'bot',
    logsInit: false,
    userId: null,
    lastBotRunning: null,
    lastHealth: null,
    offlineMode: false,
  };

  const {
    STAGE_ORDER = [],
    normalizeStage = (label) => String(label || '').trim()
  } = window.WorldCupStages || {};

  const $menu = qs('#main-menu');
  const $notify = qs('#notify');
  const $backdrop = qs('#auth-backdrop');
  const $btnCancel = qs('#auth-cancel');
  const $btnSubmit = qs('#auth-submit');
  const $offlineBanner = qs('#offline-banner');
  const $offlineStatus = qs('#offline-status');
  const $offlineDetail = qs('#offline-detail');
  const $offlineSync = qs('#offline-sync');
  const $dashboardLinks = () => qsa('#dashboard-link, #main-menu a[data-page="dashboard"]');
  const $botStatusReason = qs('#bot-status-reason');

  const DASH_CACHE_KEY = 'wc:dashboardCache';

  function nowMs(){ return Date.now(); }

  function formatTime(ts){
    if (!ts) return 'unknown time';
    const num = Number(ts);
    const normalized = Number.isFinite(num) && num < 1000000000000 ? num * 1000 : ts;
    try{
      return new Date(normalized).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
    }catch{
      return 'unknown time';
    }
  }

  function formatDuration(seconds){
    const total = Math.max(0, Math.round(Number(seconds) || 0));
    const hrs = Math.floor(total / 3600);
    const mins = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    const parts = [];
    if (hrs) parts.push(`${hrs}h`);
    if (mins || (hrs && secs)) parts.push(`${mins}m`);
    if (!hrs && secs) parts.push(`${secs}s`);
    return parts.join(' ');
  }

  function buildBotOfflineReason(health){
    if (!health || typeof health !== 'object') return '';
    if (health.cooldown_active) {
      const remaining = formatDuration(health.seconds_until_restart);
      return remaining
        ? `Restart cooldown active. Next restart attempt in ${remaining}.`
        : 'Restart cooldown active.';
    }
    if (Number.isFinite(health.crash_count)
        && Number.isFinite(health.max_crashes)
        && health.max_crashes > 0
        && health.crash_count >= health.max_crashes) {
      const window = formatDuration(health.window_seconds);
      const windowText = window ? `within ${window}` : 'recently';
      return `Bot stopped after ${health.crash_count} crashes ${windowText}.`;
    }
    if (health.last_stop) {
      return `Bot stopped at ${formatTime(health.last_stop)}.`;
    }
    return '';
  }

  function readDashCache(){
    try{
      const raw = localStorage.getItem(DASH_CACHE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object') return null;
      return parsed;
    }catch{
      return null;
    }
  }

  function writeDashCache(payload){
    try{
      localStorage.setItem(DASH_CACHE_KEY, JSON.stringify({ ...payload, ts: nowMs() }));
    }catch{}
  }

  function setOfflineBanner({mode, detail, syncText} = {}){
    if (!$offlineBanner) return;
    if (mode === 'hidden') {
      $offlineBanner.classList.remove('is-visible', 'is-syncing');
      return;
    }
    $offlineBanner.classList.add('is-visible');
    $offlineBanner.classList.toggle('is-syncing', mode === 'syncing');
    if ($offlineStatus) {
      $offlineStatus.textContent = mode === 'syncing' ? 'Syncing data' : 'Offline mode';
    }
    if ($offlineDetail && detail) $offlineDetail.textContent = detail;
    if ($offlineSync && syncText) $offlineSync.textContent = syncText;
  }

  function setDashboardWarning(active){
    const links = $dashboardLinks();
    if (!links.length) return;
    links.forEach(link => {
      link.classList.toggle('offline-warning', !!active);
      link.parentElement?.classList.toggle('offline-warning', !!active);
    });
  }

  function setBotStatusReason(text){
    if (!$botStatusReason) return;
    $botStatusReason.textContent = text || '';
  }

  function applyDashboardWarningState(){
    if (!isAdminUI()) {
      setDashboardWarning(false);
      return;
    }
    if (state.lastBotRunning === false || state.offlineMode) {
      setDashboardWarning(true);
      return;
    }
    if (state.lastHealth) {
      const { cooldown_active, crash_count, max_crashes } = state.lastHealth;
      if (cooldown_active) {
        setDashboardWarning(true);
        return;
      }
      if (Number.isFinite(crash_count)
          && Number.isFinite(max_crashes)
          && max_crashes > 0
          && crash_count >= max_crashes) {
        setDashboardWarning(true);
        return;
      }
    }
    const cached = readDashCache();
    if (cached && cached.running === false) {
      setDashboardWarning(true);
      return;
    }
    setDashboardWarning(false);
  }


const ADMIN_VIEW_KEY = 'wc:adminView';
const getAdminView = () => localStorage.getItem(ADMIN_VIEW_KEY) === '1';
function setAdminView(on){
  localStorage.setItem(ADMIN_VIEW_KEY, on ? '1' : '0');
  document.body.classList.toggle('admin-view', !!on);
  applyAdminView();
}


function isAdminUI(){ return !!(state.admin && getAdminView()); }
window.isAdminUI = isAdminUI;

function applyAdminView(){
  const enabled = isAdminUI();
  
  document.querySelectorAll('.admin-only,[data-admin]').forEach(el=>{
    el.style.display = enabled ? '' : 'none';
  });
  
  document.body.classList.toggle('user-admin-view', enabled);
}

function ensureAdminToggleButton(){
  const existing = document.getElementById('user-admin-toggle');
  const shouldShow = !!state.admin; 

  
  if (!shouldShow) {
    if (existing) existing.remove();
    return;
  }

  
  if (existing) {
    existing.textContent = getAdminView() ? 'Public View' : 'Admin View';
    return;
  }

  
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




window.addEventListener('storage', (e)=>{
  if (e.key === ADMIN_VIEW_KEY) { applyAdminView(); routePage(); }
});



function stagePill(stage){
  const s = normalizeStage(stage) || 'Group Stage';
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

  
    function showPage(page) {
      
      const adminPages = new Set(['backups','log','cogs']);

      
      if (adminPages.has(page) && !isAdminUI()) {
        notify('That page requires admin login.', false);
        return;
      }

      
      document.querySelectorAll('section.page-section').forEach(s => s.classList.remove('active-section'));
      const sec = document.getElementById(page);
      if (sec) sec.classList.add('active-section');

      
      if (page === 'dashboard') loadDashboard().catch(()=>{});
      if (page === 'ownership') loadOwnership().catch(()=>{});
      if (page === 'bets') loadBets().catch(()=>{});
      if (page === 'log' && state.admin) loadLogs().catch(()=>{});
      if (page === 'cogs' && state.admin) loadCogs().catch(()=>{});
      if (page === 'backups' && state.admin) loadBackups().catch(()=>{});
      if (page === 'splits') loadSplits().catch(()=>{});
      if (page === 'settings') loadSettings().catch(()=>{});
    }

  function setPage(p) {
    const adminPages = new Set(['backups','log','cogs']);
    if (adminPages.has(p) && !isAdminUI()) {
      notify('That page requires admin login.', false);
      p = 'dashboard';
    }

    if (p !== 'dashboard') {
      setOfflineBanner({ mode: 'hidden' });
      applyDashboardWarningState();
    }

    
    state.currentPage = p;
  localStorage.setItem('wc:lastPage', p);

  
  document.querySelectorAll('#main-menu a').forEach(a => {
    a.classList.toggle('active', a.dataset.page === p);
  });

  
  document.querySelectorAll('section.page-section, section.dashboard')
    .forEach(s => s.classList.remove('active-section'));
  document.getElementById(p)?.classList.add('active-section');
}

    function esc(s){
      return String(s ?? '').replace(/[&<>"']/g, c => ({
        '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
      }[c]));
    }

    function notifDismissKey(id){
      const uid = state.userId ? String(state.userId) : 'anon';
      return `wc:notif:dismiss:${uid}:${id}`;
    }
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

      
      fab.classList.toggle('has-new', items.length > 0);

      if (!items.length){
        body.innerHTML = `<div class="notify-empty">No New Notifications</div>`;
        return;
      }

      body.innerHTML = items.map(it => {
        const title = esc(it.title || 'Notification');
        const text  = esc(it.body || '').replace(/\n/g, '<br>');
        const id    = esc(it.id);

        let actionHtml = '';
        const action = it.action || {};

        if (action.kind === 'url' && action.url){
          actionHtml = `<a class="btn small" href="${esc(action.url)}">Open</a>`;
        } else if (action.kind === 'page' && action.page){
          actionHtml = `<button class="btn small" data-open-page="${esc(action.page)}">Open</button>`;
        } else if (action.kind === 'dm' && (action.app_url || action.web_url)) {
          const appUrl = action.app_url ? esc(action.app_url) : '';
          const webUrl = action.web_url ? esc(action.web_url) : '';
          actionHtml = `<button class="btn small" data-open-dm data-app-url="${appUrl}" data-web-url="${webUrl}">Open DM</button>`;
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

      
      body.querySelectorAll('button[data-dismiss]').forEach(btn=>{
        btn.addEventListener('click', async ()=>{
          const id = btn.getAttribute('data-dismiss');
          if (!id) return;

          
          try{
            await fetch('/api/me/notifications/read', {
              method: 'POST',
              headers: {'Content-Type':'application/json'},
              credentials: 'include',
              body: JSON.stringify({ id })
            });
          }catch{}

          
          dismissNotif(id);
          btn.closest('.notify-item')?.remove();

          
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

          
          panel.classList.remove('open');
          panel.setAttribute('aria-hidden', 'true');
          fab.setAttribute('aria-expanded', 'false');

          
          setPage(page);
          await routePage();
        });
      });

      body.querySelectorAll('button[data-open-dm]').forEach(btn=>{
        btn.addEventListener('click', async ()=>{
          const appUrl = btn.getAttribute('data-app-url') || '';
          const webUrl = btn.getAttribute('data-web-url') || '';

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

          
          panel.classList.remove('open');
          panel.setAttribute('aria-hidden', 'true');
          fab.setAttribute('aria-expanded', 'false');

          if (appUrl) {
            window.location.href = appUrl;
            if (webUrl) {
              setTimeout(() => { window.location.href = webUrl; }, 1200);
            }
          } else if (webUrl) {
            window.location.href = webUrl;
          }
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
            
            fab.classList.add('bell-ring');
            setTimeout(() => fab.classList.remove('bell-ring'), 1400);
          }
          _lastNotifSig = sig;

          const panel = document.getElementById('notify-panel');
          if (panel && panel.classList.contains('open')) {
            renderNotifications(items || []);
          }
        } catch (e) {
          
        }
      };

      await tick();
      _notifPollTimer = setInterval(tick, 10000);
    }

    async function refreshNotificationsNow(forceRing = false){
      try{
        wireNotifyUIOnce();
        const items = await loadNotifications();

        const fab = document.getElementById('notify-fab');
        if (fab){
          const sig = (items || []).map(it => String(it.id || '')).join('|');
          const hasNew = (items || []).length > 0;
          fab.classList.toggle('has-new', hasNew);

          const changed = sig && sig !== _lastNotifSig;
          if (forceRing || changed){
            fab.classList.add('bell-ring');
            setTimeout(() => fab.classList.remove('bell-ring'), 1400);
          }
          _lastNotifSig = sig;
        }

        const panel = document.getElementById('notify-panel');
        if (panel && panel.classList.contains('open')){
          renderNotifications(items || []);
        }
      }catch{
        
      }
    }
    window.refreshNotificationsNow = refreshNotificationsNow;

    
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
        if (p === 'ownership') {
          try { await refreshOwnershipPage(); } catch (_) {}
        }
      });
    }


    
    window.adminUnlocked = false;

    function setAdminUI(unlocked){
      state.admin = !!unlocked;
      document.body.classList.toggle('admin', state.admin);
      applyAdminView();
      ensureAdminToggleButton(); 
    }

    function setUserUI(user){
      const loggedIn = !!(user && (user.discord_id || user.id));
      const nextUserId = loggedIn ? String(user.discord_id || user.id) : null;
      const userChanged = nextUserId !== state.userId;
      state.userId = nextUserId;
      const fabIcon = document.getElementById('fab-icon');
      const btnLogin = document.getElementById('btn-discord-login');
      const btnLogout = document.getElementById('btn-discord-logout');

      if (btnLogin)  btnLogin.style.display  = loggedIn ? 'none' : '';
      if (btnLogout) btnLogout.style.display = loggedIn ? '' : 'none';
      if (userChanged) {
        _lastNotifSig = '';
      }
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

    
    document.addEventListener('DOMContentLoaded', initAuth);

    
    const loginBtn  = document.querySelector('#admin-button');          
    const logoutBtn = document.querySelector('#admin-logout');          
    const modal     = document.querySelector('#admin-login-backdrop');  
    const submit    = document.querySelector('#admin-submit');          
    const cancel    = document.querySelector('#admin-cancel');          
    const pw        = document.querySelector('#admin-password');        

    
    loginBtn?.addEventListener('click', () => {
      modal.style.display = 'flex';
      pw.value = '';
      pw.focus();
    });

    
    cancel?.addEventListener('click', () => {
      modal.style.display = 'none';
    });

    
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

    
    document.addEventListener('DOMContentLoaded', initAuth);


  
  async function loadDash(){
    const cached = readDashCache();
    try{
      const upP = fetchJSON('/api/uptime');
      const t0 = performance.now();
      const pingP = fetchJSON('/api/ping');
      const sysP = isAdminUI() ? fetchJSON('/api/system') : Promise.resolve(null);
      const healthP = fetchJSON('/api/health').catch(() => null);
      const [up, ping, sys, health] = await Promise.all([upP, pingP, sysP, healthP]);
      const latency = Math.max(0, Math.round(performance.now() - t0));

      const running = (up && typeof up.bot_running === 'boolean')
        ? up.bot_running
        : !!(sys && sys.bot && typeof sys.bot.running === 'boolean' && sys.bot.running);

      state.lastHealth = health;
      renderUptime(up, running);
      renderPing(ping, latency);
      if(isAdminUI() && sys) renderSystem(sys); else clearSystem();
      writeDashCache({ up, ping, sys, health, running, latencyMs: latency });

      if (!running) {
        const cachedAt = cached?.ts ? formatTime(cached.ts) : formatTime(nowMs());
        const detail = `Bot is offline. Showing cached data from ${cachedAt}.`;
        const reason = buildBotOfflineReason(health) || detail;
        if (state.currentPage === 'dashboard') {
          setOfflineBanner({
            mode: 'offline',
            detail,
            syncText: 'Waiting for bot to start…'
          });
        } else {
          setOfflineBanner({ mode: 'hidden' });
        }
        state.offlineMode = true;
        applyDashboardWarningState();
        setBotStatusReason(reason);
      } else if (state.lastBotRunning === false) {
        if (state.currentPage === 'dashboard') {
          setOfflineBanner({
            mode: 'syncing',
            detail: 'Bot is back online. Syncing dashboard data…',
            syncText: 'Updating live data…'
          });
          setTimeout(() => setOfflineBanner({ mode: 'hidden' }), 3000);
        } else {
          setOfflineBanner({ mode: 'hidden' });
        }
        state.offlineMode = false;
        applyDashboardWarningState();
        setBotStatusReason('');
      } else {
        setOfflineBanner({ mode: 'hidden' });
        state.offlineMode = false;
        applyDashboardWarningState();
        setBotStatusReason('');
      }

      state.lastBotRunning = running;

      const $actions = qs('#bot-actions');
      const $start = qs('#start-bot');
      const $stop = qs('#stop-bot');
      const $restart = qs('#restart-bot');
      if(isAdminUI() && $actions && $start && $stop && $restart){
        if(running){
          
          $start.style.display='none';
          $restart.style.display='block';
          $stop.style.display='block';
          $actions.style.gridTemplateColumns = '1fr 1fr';
        }else{
          
          $start.style.display='block';
          $restart.style.display='none';
          $stop.style.display='none';
          $actions.style.gridTemplateColumns = '1fr';
        }
      }
    }catch(e){
      if (cached?.up) {
        renderUptime(cached.up, cached.running);
      }
      if (cached?.ping) {
        renderPing(cached.ping, cached.latencyMs || 0);
      }
      if (isAdminUI() && cached?.sys) {
        renderSystem(cached.sys);
      } else {
        clearSystem();
      }
      state.lastHealth = cached?.health || null;
      const cachedAt = cached?.ts ? formatTime(cached.ts) : 'unknown time';
      const detail = `Connection lost. Showing cached data from ${cachedAt}.`;
      const reason = buildBotOfflineReason(cached?.health) || detail;
      if (state.currentPage === 'dashboard') {
        setOfflineBanner({
          mode: 'offline',
          detail,
          syncText: 'Waiting for bot to start…'
        });
      } else {
        setOfflineBanner({ mode: 'hidden' });
      }
      state.offlineMode = true;
      applyDashboardWarningState();
      setBotStatusReason(reason);
      notify(`Dashboard error: ${e.message}`, false);
    }
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

      
      const semicircleDash = (pct) => {
        const total = 125.66;                
        const c = Math.max(0, Math.min(100, Number(pct) || 0));
        return `${(c/100) * total},${total}`;
      };

      
      const memBar = document.getElementById('mem-bar');
      if (memBar) memBar.setAttribute('stroke-dasharray', semicircleDash(memPct));
      const memText = document.getElementById('mem-text');
      if (memText) memText.textContent = `${memPct.toFixed(0)}%`;
      const memExtra = document.getElementById('mem-extra');
      if (memExtra) memExtra.textContent =
        `Used ${Number(s.mem_used_mb||0).toFixed(0)} MB of ${Number(s.mem_total_mb||0).toFixed(0)} MB`;
      const memLegend = document.getElementById('mem-legend');
      if (memLegend) memLegend.textContent = `${memPct.toFixed(0)}%`;

      
      const cpuBar = document.getElementById('cpu-bar');
      if (cpuBar) cpuBar.setAttribute('stroke-dasharray', semicircleDash(cpuPct));
      const cpuText = document.getElementById('cpu-text');
      if (cpuText) cpuText.textContent = `${cpuPct.toFixed(0)}%`;
      const cpuExtra = document.getElementById('cpu-extra');
      if (cpuExtra) cpuExtra.textContent = `CPU ${cpuPct.toFixed(1)}%`;
      const cpuLegend = document.getElementById('cpu-legend');
      if (cpuLegend) cpuLegend.textContent = `${cpuPct.toFixed(0)}%`;

      
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

  
    
    async function setupVerifiedPicker(preload = false) {
      const picker = document.getElementById('reassign-picker');
      const list   = document.getElementById('reassign-options');
      const idBox  = document.getElementById('reassign-id');
      if (!picker || !list || !idBox) return;

      async function populate() {
        
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

        
        if (entries.length === 0) {
          try {
            const r = await fetch('/api/player_names', { credentials: 'include' });
            const map = await r.json();
            entries = Object.keys(map).map(id => ({ id, name: map[id] || id }));
          } catch {}
        }

        
        entries.sort((a,b) => a.name.localeCompare(b.name));
        list.innerHTML = '';
        entries.forEach(({ id, name }) => {
          const li = document.createElement('li');
          li.setAttribute('role', 'option');
          li.dataset.id = id;
          li.dataset.label = name;
          li.textContent = name;
          list.appendChild(li);
        });
      }

      
      if (!picker.dataset.wired) {
        picker.dataset.wired = '1';

        
        picker.addEventListener('click', async () => {
          if (list.childElementCount === 0) {
            await populate();            
            if (list.childElementCount === 0) return; 
          }
          const open = list.hidden;
          list.hidden = !open;
          picker.setAttribute('aria-expanded', String(open));
        });

        
        list.addEventListener('click', (e) => {
          const li = e.target.closest('li');
          if (!li) return;
          picker.textContent = li.dataset.label;
          idBox.value = li.dataset.id;
          list.hidden = true;
          picker.setAttribute('aria-expanded', 'false');
        });

        
        document.addEventListener('click', (e) => {
          if (e.target === picker || e.target.closest('#verified-select')) return;
          if (!list.hidden) {
            list.hidden = true;
            picker.setAttribute('aria-expanded', 'false');
          }
        });
      }

      
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


const ISO_ALIASES = {
  'USA': 'us', 'United States': 'uS',
  'England': 'gb-eng', 'Scotland': 'gb-sct', 'Wales': 'gb-wls', 'Northern Ireland': 'gb-nir',
  'South Korea': 'kr', 'Ivory Coast': 'ci', "Côte d’Ivoire": 'ci', "Cote d'Ivoire": 'ci'
};


function resolveIsoCode(country) {
  if (!country) return '';
  const c = String(country).trim();

  
  if (window.TEAM_ISO && window.TEAM_ISO[c]) return window.TEAM_ISO[c];
  
  if (ISO_ALIASES[c]) return ISO_ALIASES[c];

  
  const norm = c.toLowerCase().replace(/\s+/g, ' ');
  for (const k in (window.TEAM_ISO || {})) {
    if (k.toLowerCase().replace(/\s+/g, ' ') === norm) return window.TEAM_ISO[k];
  }
  return '';
}


function codeToEmoji(cc) {
  if (!/^[A-Za-z]{2}$/.test(cc)) return '🏳️';
  const up = cc.toUpperCase();
  const base = 127397;
  return String.fromCodePoint(base + up.charCodeAt(0), base + up.charCodeAt(1));
}


function flagHTML(country) {
  const code = resolveIsoCode(country);
  if (!code) return '';
  const emoji = codeToEmoji(code);
  const src = `https://flagcdn.com/24x18/${code}.png`; 
  const fallback = emoji !== '🏳️' ? emoji : '';
  return `<img class="flag-img" src="${src}" alt="${country}"
          onerror="this.replaceWith(document.createTextNode('${fallback}'));">`;
}

var ownershipState = { teams: [], rows: [], merged: [], loaded: false, lastSort: 'country', groupMap: new Map(), groupFilter: 'ALL' };
var playerNames = {}; 

function normalizeOwnershipTeam(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
}

function buildOwnershipGroupMap(teamMeta) {
  var out = new Map();
  if (!teamMeta) return out;

  if (teamMeta.groups && typeof teamMeta.groups === 'object') {
    Object.entries(teamMeta.groups).forEach(function ([group, entries]) {
      (entries || []).forEach(function (entry) {
        var name = '';
        if (typeof entry === 'string') {
          name = entry;
        } else if (entry && typeof entry === 'object') {
          name = entry.team || entry.name || '';
        }
        var key = normalizeOwnershipTeam(name);
        if (key) out.set(key, String(group || '').toUpperCase());
      });
    });
    return out;
  }

  if (typeof teamMeta === 'object') {
    Object.entries(teamMeta).forEach(function ([team, meta]) {
      if (!meta || typeof meta !== 'object') return;
      var group = meta.group;
      var key = normalizeOwnershipTeam(team);
      if (key && group) out.set(key, String(group).toUpperCase());
    });
  }
  return out;
}

async function loadOwnershipTeamMeta() {
  var cacheKey = 'wc:team_meta';
  var ttl = 24 * 60 * 60 * 1000;
  try {
    var blob = JSON.parse(localStorage.getItem(cacheKey) || 'null');
    if (blob && blob.ts && (Date.now() - blob.ts) < ttl && blob.data) {
      return blob.data;
    }
  } catch (_) {
    try { localStorage.removeItem(cacheKey); } catch (_) {}
  }
  try {
    var res = await fetch('/api/team_meta', { credentials: 'include' });
    if (!res.ok) return null;
    var data = await res.json();
    try { localStorage.setItem(cacheKey, JSON.stringify({ ts: Date.now(), data: data })); } catch (_) {}
    return data;
  } catch (_) {
    return null;
  }
}

function formatOwnershipPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '';
  const num = Number(value);
  return Number.isInteger(num) ? `${num}%` : `${num.toFixed(1)}%`;
}

    function renderOwnershipTable(list) {
      const tbody = document.querySelector('#ownership-tbody');
      if (!tbody) return;
      tbody.innerHTML = '';

      list.forEach(function (row) {
        const tr = document.createElement('tr');
        tr.className = row.main_owner ? 'row-assigned' : 'row-unassigned';
        const groupKey = normalizeOwnershipTeam(row.country);
        const groupLabel = ownershipState.groupMap.get(groupKey) || '—';

        const ownersCount = row.owners_count || ((row.main_owner ? 1 : 0) + ((row.split_with && row.split_with.length) || 0));
        const shareValue = ownersCount > 0 ? (100 / ownersCount) : 0;
        const shareLabel = formatOwnershipPercent(shareValue);
        const percentages = row.percentages || {};
        const hasPercentages = Object.keys(percentages).length > 0;
        const getShareLabel = (ownerId) => {
          if (hasPercentages) {
            const val = percentages[String(ownerId)];
            return val === undefined ? '' : formatOwnershipPercent(val);
          }
          return ownersCount > 1 ? shareLabel : '';
        };

        
        const idVal = row.main_owner ? row.main_owner.id : '';
        const label = (row.main_owner && (row.main_owner.username || row.main_owner.id)) || '';
        const showId = !!(window.adminUnlocked && idVal && label !== idVal);
        const ownerShareLabel = getShareLabel(idVal);
        const ownerShare = ownerShareLabel ? ` <span class="muted">(${ownerShareLabel})</span>` : '';
        const ownerCell = row.main_owner
          ? `<span class="owner-name" title="${idVal}">${label}</span>${showId ? ' <span class="muted">(' + idVal + ')</span>' : ''}${ownerShare}`
          : 'Unassigned <span class="warn-icon" title="No owner">⚠️</span>';

        const splitStr = (row.split_with && row.split_with.length)
          ? row.split_with.map(s => {
              const splitShare = getShareLabel(s.id);
              return splitShare ? `${s.username || s.id} (${splitShare})` : `${s.username || s.id}`;
            }).join(', ')
          : '—';

        const current = normalizeStage(
          (ownershipState.stages && ownershipState.stages[row.country]) || ''
        );
        let stageCell = '';
        if (isAdminUI()) {
          const opts = STAGE_ORDER.map(v =>
            `<option value="${v}" ${v === current ? 'selected' : ''}>${v}</option>`
          ).join('');
          stageCell = `
            <select class="stage-select" data-team="${row.country}">
              ${opts}
            </select>
          `;
        } else {
          stageCell = stagePill(current);
        }

        tr.innerHTML = `
          <td id="country">${flagHTML(row.country)} <span class="country-name">${row.country}</span></td>
          <td><span class="ownership-group">${groupLabel}</span></td>
          <td>${ownerCell}</td>
          <td>${splitStr}</td>
          <td>${stageCell}</td>
          <td class="admin-col" data-admin="true">
            <button class="btn btn-outline xs reassign-btn" data-team="${row.country}">Reassign</button>
          </td>
        `;

        tbody.appendChild(tr);
      });

      if (isAdminUI()) {
        enhanceStageSelects();
      }

      
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
  } else if (by === 'group') {
    var groupKey = function (row) {
      var team = normalizeOwnershipTeam(row.country);
      var group = ownershipState.groupMap.get(team) || '';
      return group.toUpperCase();
    };
    list.sort(function (a, b) {
      var ga = groupKey(a) || 'ZZZ';
      var gb = groupKey(b) || 'ZZZ';
      if (ga !== gb) return ga.localeCompare(gb);
      return a.country.localeCompare(b.country);
    });
  }
  renderOwnershipTable(applyOwnershipGroupFilter(list));
  initStageDropdowns();
}

function applyOwnershipGroupFilter(list) {
  var filter = (ownershipState.groupFilter || 'ALL').toUpperCase();
  if (filter === 'ALL') return list;
  return list.filter(function (row) {
    var groupKey = normalizeOwnershipTeam(row.country);
    return (ownershipState.groupMap.get(groupKey) || '').toUpperCase() === filter;
  });
}

function setOwnershipGroupFilter(filter) {
  ownershipState.groupFilter = (filter || 'ALL').toUpperCase();
  document.querySelectorAll('.group-filter-btn').forEach(btn => {
    var btnGroup = (btn.getAttribute('data-group') || 'ALL').toUpperCase();
    btn.classList.toggle('active', btnGroup === ownershipState.groupFilter);
  });
  sortMerged(ownershipState.lastSort || 'country');
}

function enhanceStageSelects() {
  const selects = document.querySelectorAll('#ownership select.stage-select');

  
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
    document.querySelectorAll('.stage-select-wrap.is-open')
      .forEach(wrap => wrap.classList.remove('is-open'));
    document.querySelectorAll('#ownership .ownership-table tbody tr.stage-select-open')
      .forEach(row => row.classList.remove('stage-select-open'));
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
        
        sel.value = opt.value;
        sel.dispatchEvent(new Event('change', { bubbles: true }));

        
        btn.textContent = opt.textContent;

        
        list.querySelectorAll('.stage-select-option.selected')
            .forEach(x => x.classList.remove('selected'));
        li.classList.add('selected');

        closeAll();
      });

      list.appendChild(li);
    });

    
    sel.parentNode.insertBefore(wrap, sel);
    wrap.appendChild(btn);
    wrap.appendChild(list);
    wrap.appendChild(sel);
  });

  
  document.addEventListener('click', (evt) => {
    const wrap = evt.target.closest('.stage-select-wrap');

    
    if (!wrap) {
      closeAll();
      return;
    }

    
    const btn = evt.target.closest('.stage-select-display');
    if (btn) {
      const list = wrap.querySelector('.stage-select-list');
      const isOpen = btn.classList.contains('open');
      closeAll();
      if (!isOpen) {
        btn.classList.add('open');
        list.classList.add('open');
        wrap.classList.add('is-open');
        wrap.closest('tr')?.classList.add('stage-select-open');
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

      
      document.querySelectorAll('#ownership .stage-select-list.open').forEach(ul => {
        if (ul !== list) {
          ul.classList.remove('open');
          ul.closest('.stage-select-wrap')?.classList.remove('drop-up');
          ul.closest('.stage-select-wrap')?.classList.remove('is-open');
          ul.closest('tr')?.classList.remove('stage-select-open');
        }
      });

      
      if (list.classList.contains('open')) {
        list.classList.remove('open');
        wrap.classList.remove('drop-up');
        wrap.classList.remove('is-open');
        wrap.closest('tr')?.classList.remove('stage-select-open');
        return;
      }

      
      list.classList.add('open');
      wrap.classList.add('is-open');
      wrap.closest('tr')?.classList.add('stage-select-open');
      const listRect = list.getBoundingClientRect();
      const btnRect  = btn.getBoundingClientRect();
      const vh       = window.innerHeight || document.documentElement.clientHeight;

      const spaceBelow = vh - btnRect.bottom;
      const spaceAbove = btnRect.top;
      const needed     = Math.min(listRect.height, 240) + 8; 

      
      if (spaceBelow < needed && spaceAbove > spaceBelow) {
        wrap.classList.add('drop-up');   
      } else {
        wrap.classList.remove('drop-up'); 
      }
    });

    
    list.addEventListener('click', ev => ev.stopPropagation());
  });

  
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

async function initOwnership() {
  try {
    
    let list = null;
    try {
      const r = await fetch('/api/ownership_merged', { credentials: 'include' });
      if (r.ok) {
        const j = await r.json();
        if (j && Array.isArray(j.rows)) list = j.rows;
      }
    } catch {  }

    
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

    
    await ensureTeamIsoLoaded();

    
    let stages = {};
    try {
      
      if (isAdminUI()) {
        const r = await fetch('/admin/teams/stage', { credentials: 'include' });
        if (r.ok) {
          const j = await r.json();
          stages = (j && j.stages) || {};
        }
      } else {
        
        const r = await fetch('/api/team_stage', { credentials: 'include' });        if (r.ok) stages = await r.json();
      }
    } catch { stages = {}; }
    ownershipState.stages = stages || {};

    
    let teamMeta = null;
    try {
      teamMeta = await loadOwnershipTeamMeta();
    } catch { teamMeta = null; }
    ownershipState.groupMap = buildOwnershipGroupMap(teamMeta);

    
    ownershipState.merged = list;
    ownershipState.loaded = true;
    setOwnershipGroupFilter(ownershipState.groupFilter || 'ALL');
  } catch (e) {
    console.error('[ownership:init]', e);
    notify('Failed to load ownership data', false);
  }
}



var sortCountryBtn = document.querySelector('#sort-country');
var sortGroupBtn = document.querySelector('#sort-group');
if (sortCountryBtn) sortCountryBtn.addEventListener('click', function () { sortMerged('country'); });
if (sortGroupBtn) sortGroupBtn.addEventListener('click', function () { sortMerged('group'); });
document.querySelectorAll('.group-filter-btn').forEach(btn => {
  btn.addEventListener('click', function () {
    var group = btn.getAttribute('data-group') || 'ALL';
    setOwnershipGroupFilter(group);
  });
});

document.addEventListener('click', async (ev) => {
  const btn = ev.target.closest('.reassign-btn');
  if (!btn) return;

  
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

      
      inputT.value = teamName || '';

      if (picker) {
        picker.textContent = '-- Select a player --';
        picker.dataset.id = '';
      }
      if (inputId) inputId.value = '';

      
      setupVerifiedPicker(true);
      if (listbox && picker) {
        listbox.hidden = true;
        picker.setAttribute('aria-expanded', 'false');
      }

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
      return; 
    }

    const data = await res.json();
    if (!data.ok) {
      notify(data.error || 'Failed to reassign', false);
      return;
    }

    
    document.getElementById('reassign-backdrop').style.display = 'none';
    notify('Team reassigned', true);

    try { await refreshOwnershipPage(); } catch (_) {}
  } catch (e) {
    notify('Failed to reassign', false);
  }
});


async function refreshOwnershipPage() {
  ownershipState.loaded = false;
  await initOwnership();
}

async function refreshOwnershipNow() {
  try {
    
    document.querySelectorAll('.reassign-btn').forEach(b => b.disabled = true);

    
    const r = await fetch('/api/ownership_merged', { credentials: 'include' });
    const merged = r.ok ? (await r.json()).rows : null;

    if (!Array.isArray(merged)) {
      
      const [rowsObj, teamsResp] = await Promise.all([
        fetch('/api/ownership_from_players', { credentials: 'include' }).then(x => x.json()),
        fetch('/api/teams', { credentials: 'include' }).then(x => x.json())
      ]);
      const teams = Array.isArray(teamsResp) ? teamsResp : (Array.isArray(teamsResp?.teams) ? teamsResp.teams : []);
      
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

    
    ownershipState.loaded = true;
    sortMerged(ownershipState.lastSort || 'country');
  } catch (e) {
    console.error('[ownership:refresh]', e);
    notify('Failed to refresh ownership', false);
  } finally {
    document.querySelectorAll('.reassign-btn').forEach(b => b.disabled = false);
  }
}


document.querySelector('#sort-country')?.addEventListener('click', () => sortMerged('country'));
document.querySelector('#sort-player')?.addEventListener('click', () => sortMerged('player'));


const _origShowPage = typeof showPage === 'function' ? showPage : null;
window.showPage = function(id) {
  if (_origShowPage) _origShowPage(id);
  else {
    
    document.querySelectorAll('section.page-section, section.dashboard')
      .forEach(s => s.classList.remove('active-section'));
    document.getElementById(id)?.classList.add('active-section');
  }
  if (id === 'ownership' && !ownershipState.loaded) initOwnership();
};


document.addEventListener('DOMContentLoaded', () => {
  
  const visible = document.querySelector('#ownership.page-section.active-section');
  if (visible && !ownershipState.loaded) initOwnership();
  
});


async function loadOwnershipPage() {
  
  if (!ownershipState.loaded) {
    await initOwnership();
  } else {
    
    sortMerged(ownershipState.lastSort || 'country');
  }
}

window.loadOwnershipPage = loadOwnershipPage;

    async function loadAndRenderBets() {
      const host = document.getElementById('bets');
      if (!host) return;

      
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

      
      let verifiedMap = new Map();
      try {
        const verified = await getJSON('/api/verified');
        const arr = Array.isArray(verified) ? verified : (verified.users || []);
        verifiedMap = new Map(arr.map(u => [
          String(u.discord_id ?? u.id ?? ''),
          (u.display_name && String(u.display_name).trim()) ||
          (u.username && String(u.username).trim()) || ''
        ]));
      } catch {  }

      
      const resolveDisplayName = (id, fallbackUsername) => {
        const key = id ? String(id) : '';
        return (key && verifiedMap.get(key)) || fallbackUsername || (key ? `User ${key}` : 'Unknown');
      };

      
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

        
        const o1Name = (bet.option1_display_name ??
                       resolveDisplayName(bet.option1_user_id, bet.option1_user_name)) || '';
        const o2Name = (bet.option2_display_name ??
                       resolveDisplayName(bet.option2_user_id, bet.option2_user_name)) || '';

        
        const tdO1 = document.createElement('td');
        tdO1.className = 'bet-opt bet-opt1';
        const s1 = document.createElement('span');
        s1.textContent = bet.option1 ?? '-';
        s1.dataset.tip = (bet.option1_user_id || bet.option1_user_name)
          ? `Claimed by: ${o1Name}`
          : 'Unclaimed';
        tdO1.appendChild(s1);

        
        const tdO2 = document.createElement('td');
        tdO2.className = 'bet-opt bet-opt2';
        const s2 = document.createElement('span');
        s2.textContent = bet.option2 ?? '-';
        s2.dataset.tip = (bet.option2_user_id || bet.option2_user_name)
          ? `Claimed by: ${o2Name}`
          : 'Unclaimed';
        tdO2.appendChild(s2);

        
        const tdWin = document.createElement('td');
        tdWin.className = 'bet-winner';
        const winner = bet.winner === 'option1' || bet.winner === 'option2' ? bet.winner : null;

          if (showAdmin) {
          
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












window.state = window.state || {};


if (state.splitsHistoryTimer) {
  clearInterval(state.splitsHistoryTimer);
  state.splitsHistoryTimer = null;
}
state.splitsBuilt = false;


async function loadSplits(){
  try {
    if (!state.splitsBuilt) buildSplitsShell();
    await loadPublicSplits();
  } catch(e){
    notify(`Splits error: ${e.message || e}`, false);
  }
}
window.loadSplits = loadSplits;


function buildSplitsShell(){
  const sec = document.getElementById('splits');
  if (!sec) return;

  sec.innerHTML = `
    <div class="splits-layout">
      <div class="splits-panel splits-public">
        <div class="table-wrap" id="splits-requests">
          <div class="table-head">
            <div class="table-title">Split Requests</div>
            <div class="table-actions">
              <button id="splits-create-open" class="btn">Create New</button>
              <button id="splits-public-refresh" class="btn">Refresh</button>
            </div>
          </div>
          <div class="table-scroll" id="splits-pending">
            <div class="split-empty">Loading…</div>
          </div>
        </div>

        <div class="table-wrap" id="splits-history" style="margin-top:16px">
          <div class="table-head">
            <div class="table-title">History</div>
            <div class="table-actions">
              <button id="splits-public-history-refresh" class="btn">Refresh</button>
            </div>
          </div>
          <div class="table-scroll" id="splits-history-body">
            <div class="split-empty">Loading…</div>
          </div>
        </div>
      </div>
    </div>
  `;

  
  const btnCreate = document.getElementById('splits-create-open');
  if (btnCreate && !btnCreate._wired) {
    btnCreate._wired = true;
    btnCreate.addEventListener('click', openSplitCreateModal);
  }
  const btnPublic = document.getElementById('splits-public-refresh');
  if (btnPublic && !btnPublic._wired) {
    btnPublic._wired = true;
    btnPublic.addEventListener('click', loadPublicSplits);
  }
  const btnPublicHist = document.getElementById('splits-public-history-refresh');
  if (btnPublicHist && !btnPublicHist._wired) {
    btnPublicHist._wired = true;
    btnPublicHist.addEventListener('click', loadPublicSplits);
  }

  state.splitsBuilt = true;
}




function deriveDefaultSplitPercentageByTeam(teamName) {
  const key = String(teamName || '').toLowerCase();
  const merged = Array.isArray(ownershipState.merged) ? ownershipState.merged : [];
  const row = merged.find(r => String(r.country || '').toLowerCase() === key);
  if (!row || !row.main_owner) return null;
  const splitCount = Array.isArray(row.split_with) ? row.split_with.length : 0;
  const mainOwnerShare = 100 / (1 + splitCount);
  return mainOwnerShare / 2;
}

async function openSplitCreateModal() {
  const backdrop = document.getElementById('split-create-backdrop');
  const modal = document.getElementById('split-create-modal');
  const closeBtn = document.getElementById('split-create-close');
  const cancelBtn = document.getElementById('split-create-cancel');
  const submitBtn = document.getElementById('split-create-submit');
  const countrySel = document.getElementById('split-create-country');
  const pctInput = document.getElementById('split-create-percentage');
  if (!backdrop || !modal || !countrySel || !pctInput || !submitBtn) return;

  // Reuse ownership cache so we can build a country dropdown from current owner data.
  await initOwnership();

  const currentUid = state.userId ? String(state.userId) : '';
  const teams = (ownershipState.merged || [])
    .filter(row => row && row.main_owner && String(row.main_owner.id || '') !== currentUid)
    .map(row => String(row.country || '').trim())
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b));

  countrySel.innerHTML = '<option value="">Select a country</option>';
  teams.forEach(team => {
    const opt = document.createElement('option');
    opt.value = team;
    opt.textContent = team;
    countrySel.appendChild(opt);
  });
  pctInput.value = '';

  const closeModal = () => {
    backdrop.style.display = 'none';
    document.removeEventListener('keydown', onEsc);
  };
  const onEsc = (ev) => {
    if (ev.key === 'Escape') closeModal();
  };

  if (closeBtn && !closeBtn._wired) {
    closeBtn._wired = true;
    closeBtn.addEventListener('click', closeModal);
  }
  if (cancelBtn && !cancelBtn._wired) {
    cancelBtn._wired = true;
    cancelBtn.addEventListener('click', closeModal);
  }
  if (!backdrop._wired) {
    backdrop._wired = true;
    backdrop.addEventListener('click', (ev) => {
      if (ev.target === backdrop) closeModal();
    });
  }

  if (!submitBtn._wired) {
    submitBtn._wired = true;
    submitBtn.addEventListener('click', async () => {
      const team = countrySel.value;
      const pctRaw = String(pctInput.value || '').trim();
      const body = { team };

      if (!team) {
        notify('Please select a country.', false);
        return;
      }
      if (pctRaw) {
        const pct = Number(pctRaw);
        if (!Number.isFinite(pct) || pct <= 0 || pct > 100) {
          notify('Percentage must be between 0 and 100.', false);
          return;
        }
        body.percentage = pct;
      }

      try {
        submitBtn.disabled = true;
        // Backend applies default percentage logic when this field is omitted.
        const result = await fetchJSON('/api/split_requests/create', {
          method: 'POST',
          body: JSON.stringify(body)
        });
        const usedPct = typeof result.requested_percentage === 'number'
          ? result.requested_percentage
          : deriveDefaultSplitPercentageByTeam(team);
        notify(`Split request created for ${team}${usedPct ? ` (${formatPercentage(usedPct)})` : ''}.`, true);
        closeModal();
        await loadPublicSplits();
      } catch (e) {
        notify(`Create split request failed: ${e.message || e}`, false);
      } finally {
        submitBtn.disabled = false;
      }
    });
  }

  backdrop.style.display = 'flex';
  modal.focus();
  document.addEventListener('keydown', onEsc);
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
  if (typeof t === 'number' && t < 1e12) t = t * 1000; 
  const d = new Date(t);
  if (Number.isNaN(d.getTime())) return '-';
  const pad = n => String(n).padStart(2,'0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
async function getVerifiedMap() {
  if (state.verifiedMap instanceof Map) return state.verifiedMap;
  try {
    const verified = await fetchJSON('/api/verified');
    const list = Array.isArray(verified) ? verified : (verified.users || verified.verified_users || []);
    state.verifiedMap = new Map(list.map(u => [
      String(u.discord_id ?? u.id ?? ''),
      (u.display_name && String(u.display_name).trim()) ||
      (u.username && String(u.username).trim()) ||
      (u.habbo_name && String(u.habbo_name).trim()) || ''
    ]));
  } catch {
    state.verifiedMap = new Map();
  }
  return state.verifiedMap;
}
async function getPlayerNamesMap() {
  if (state.playerNamesMap instanceof Map) return state.playerNamesMap;
  try {
    const names = await fetchJSON('/api/player_names');
    if (names && typeof names === 'object') {
      state.playerNamesMap = new Map(Object.entries(names));
    } else {
      state.playerNamesMap = new Map();
    }
  } catch {
    state.playerNamesMap = new Map();
  }
  return state.playerNamesMap;
}
function mergeNameMaps(primary, secondary) {
  const merged = new Map();
  if (secondary instanceof Map) {
    for (const [key, value] of secondary.entries()) merged.set(key, value);
  }
  if (primary instanceof Map) {
    for (const [key, value] of primary.entries()) merged.set(key, value);
  }
  return merged;
}
function normalizeNameFallback(value) {
  if (value == null) return '';
  const str = String(value).trim();
  return /^\d+$/.test(str) ? '' : str;
}
function resolveVerifiedName(id, fallback, verifiedMap) {
  const key = id ? String(id) : '';
  const mapped = key && verifiedMap ? verifiedMap.get(key) : '';
  return mapped || normalizeNameFallback(fallback) || '-';
}
function formatPercentage(value) {
  const num = typeof value === 'string' ? Number(value) : value;
  if (typeof num !== 'number' || Number.isNaN(num)) return '-';
  const fixed = Number.isInteger(num) ? num.toString() : num.toFixed(1);
  return `${fixed}%`;
}
function shortId(id) {
  if (!id) return '-';
  const str = String(id);
  let hash = 0;
  for (let i = 0; i < str.length; i++) hash = (hash * 31 + str.charCodeAt(i)) >>> 0;
  return '#' + (hash % 90000 + 10000); 
}
function splitStatusPill(status, variant = 'admin') {
  const pendingClass = variant === 'public' ? 'pill-pending-public' : 'pill-pending-admin';
  const map = {
    pending: pendingClass,
    approved: 'pill-ok',
    accepted: 'pill-ok',
    resolved: 'pill-ok',
    denied: 'pill-off',
    rejected: 'pill-off',
    declined: 'pill-off'
  };
  const cls = map[status] || 'pill-off';
  const label = status ? status[0].toUpperCase() + status.slice(1) : 'Unknown';
  return `<span class="pill ${cls}">${label}</span>`;
}

async function loadPublicSplits() {
  const pendingBody = document.getElementById('splits-pending');
  const historyBody = document.getElementById('splits-history-body');
  if (!pendingBody || !historyBody) return;

  try {
    const data = await fetchJSON('/api/split_requests');
    const pending = Array.isArray(data?.pending) ? data.pending : [];
    const resolved = Array.isArray(data?.resolved) ? data.resolved : [];
    const [verifiedMap, playerNamesMap] = await Promise.all([
      getVerifiedMap(),
      getPlayerNamesMap()
    ]);
    const nameMap = mergeNameMaps(verifiedMap, playerNamesMap);
    renderPublicPendingSplits(pending, nameMap);
    renderPublicSplitHistory(resolved, nameMap);
  } catch (e) {
    notify(`Public splits error: ${e.message || e}`, false);
  }
}


function renderPublicPendingSplits(rows, verifiedMap){
  const body = document.getElementById('splits-pending');
  if (!body) return;
  body.innerHTML = '';
  const isAdminView = typeof isAdminUI === 'function' ? isAdminUI() : !!state.admin;
  const currentUid = state.userId ? String(state.userId) : '';

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
        <th class="col-pct">%</th>
        <th class="col-when">EXPIRES</th>
        <th class="col-status">${isAdminView ? 'ACTION' : 'STATUS'}</th>
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
    const fromId = r.requester_id ?? r.from_id ?? r.from;
    const toId = r.main_owner_id ?? r.to_id ?? r.to;
    const fromFallback =
      r.from_username ?? r.requester_username ?? r.from_name ?? r.requester_name ?? r.from;
    const toFallback =
      r.main_owner_username ?? r.main_owner_name ?? r.main_owner_display_name ??
      r.to_username ?? r.to_name ?? r.to_display_name ?? r.to;
    const from = resolveVerifiedName(fromId, fromFallback, verifiedMap);
    const to = resolveVerifiedName(toId, toFallback, verifiedMap);
    const pct = r.requested_percentage ?? r.requested_percent ?? r.percentage ?? null;
    const when = r.expires_at ?? r.timestamp ?? null;

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="col-id" title="${escapeHTML(realId)}">${idShort}</td>
      <td class="col-team"><span class="clip" title="${escapeHTML(team)}">${escapeHTML(team)}</span></td>
      <td class="col-user"><span class="clip" title="${escapeHTML(String(from))}">${escapeHTML(String(from))}</span></td>
      <td class="col-user"><span class="clip" title="${escapeHTML(String(to))}">${escapeHTML(String(to))}</span></td>
      <td class="col-pct">${formatPercentage(pct)}</td>
      <td class="col-when mono">${when ? fmtDateTime(when) : '-'}</td>
      <td class="col-status">
        ${
          (() => {
            // Admins keep the existing action chip flow.
            if (isAdminView) {
              return `
                <div class="action-cell">
                  <button type="button" class="pill pill-pending-admin pill-click">Pending</button>
                  <div class="chip-group--split hidden">
                    <button type="button" class="btn-split split-accept" data-action="accept" data-id="${escapeHTML(realId)}">Accept</button>
                    <button type="button" class="btn-split split-decline" data-action="decline" data-id="${escapeHTML(realId)}">Decline</button>
                  </div>
                </div>
              `;
            }

            // If the signed-in user is the receiving/main owner, allow them to resolve on web.
            const isReceivingOwner = currentUid && String(toId || '') === currentUid;
            if (isReceivingOwner) {
              return `
                <div class="chip-group--split">
                  <button type="button" class="btn-split split-accept" data-action="accept" data-id="${escapeHTML(realId)}">Accept</button>
                  <button type="button" class="btn-split split-decline" data-action="decline" data-id="${escapeHTML(realId)}">Decline</button>
                </div>
              `;
            }

            return splitStatusPill('pending', 'public');
          })()
        }
      </td>
    `;
    tbody.appendChild(tr);
  }

  if (isAdminView) {
    function collapseAll() {
      table.querySelectorAll('.action-cell').forEach(cell => {
        cell.querySelector('.pill-click')?.classList.remove('hidden');
        cell.querySelector('.chip-group--split')?.classList.add('hidden');
      });
    }

    table.addEventListener('click', async (e) => {
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

      const chip = e.target.closest('.btn-split[data-action][data-id]');
      if (!chip) return;

      const action = chip.getAttribute('data-action');
      const sid = chip.getAttribute('data-id');
      const row = chip.closest('tr');
      row.querySelectorAll('.btn-split').forEach(b => b.disabled = true);

      try {
        const res = await submitSplitAction(action, sid);
        if (!res || res.ok === false) throw new Error(res?.error || 'unknown error');

        row.remove();
        if (!tbody.children.length) {
          body.innerHTML = '<div class="split-empty">No pending split requests.</div>';
        }
        await loadPublicSplits();
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
  }

  body.appendChild(table);
}


function renderPublicSplitHistory(rows, verifiedMap) {
  const body = document.getElementById('splits-history-body');
  if (!body) return;

  if (!Array.isArray(rows) || rows.length === 0) {
    body.innerHTML = `<div class="split-empty">No history recorded yet.</div>`;
    return;
  }

  const sorted = rows.slice().sort((a, b) => {
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
        <th class="col-status">STATUS</th>
      </tr>
    </thead>
    <tbody></tbody>
  `;
  const tbody = table.querySelector('tbody');

  const isAdminView = typeof isAdminUI === 'function' ? isAdminUI() : !!state.admin;

  for (const ev of sorted) {
    const id = ev.id ?? ev.request_id ?? '';
    const team = ev.team || ev.country || ev.country_name || '-';
    const fromId = ev.requester_id ?? ev.from_id ?? ev.from;
    const toId = ev.main_owner_id ?? ev.to_id ?? ev.to ?? ev.receiver_id;
    const fromFallback = ev.from_username || ev.requester_username || ev.from_name || ev.requester_name || ev.from;
    const toFallback = ev.main_owner_username || ev.main_owner_name || ev.main_owner_display_name ||
      ev.to_username || ev.receiver_username || ev.receiver_name || ev.to_name || ev.to_display_name || ev.to;
    const fromUser = resolveVerifiedName(fromId, fromFallback, verifiedMap);
    const toUser = resolveVerifiedName(toId, toFallback, verifiedMap);
    const when = ev.created_at || ev.time || ev.timestamp || null;
    const actionRaw = (ev.action || ev.status || 'resolved').toString().toLowerCase();

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="col-id" title="${escapeHTML(String(id))}">${shortId(id)}</td>
      <td class="col-team"><span class="clip" title="${escapeHTML(team)}">${escapeHTML(team)}</span></td>
      <td class="col-user"><span class="clip" title="${escapeHTML(String(fromUser))}">${escapeHTML(String(fromUser))}</span></td>
      <td class="col-user"><span class="clip" title="${escapeHTML(String(toUser))}">${escapeHTML(String(toUser))}</span></td>
      <td class="col-when mono">${when ? fmtDateTime(when) : '-'}</td>
      <td class="col-status">${splitStatusPill(actionRaw, isAdminView ? 'admin' : 'public')}</td>
    `;
    tbody.appendChild(tr);
  }

  body.innerHTML = '';
  body.appendChild(table);
}

async function submitSplitAction(action, requestId) {
  // Admin users keep using admin endpoints; regular users use the public response endpoint.
  const useAdminEndpoint = typeof isAdminUI === 'function' ? isAdminUI() : !!state.admin;
  const url = useAdminEndpoint
    ? (action === 'accept' ? '/admin/splits/accept' : '/admin/splits/decline')
    : '/api/split_requests/respond';

  const payload = useAdminEndpoint
    ? { id: requestId }
    : { id: requestId, action };

  const res = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  return await res.json();
}

window.loadSplits = loadSplits;


    async function loadBackups(){
      try{
        
        const d = await fetchJSON('/api/backups');

        
        const w = ensureSectionCard('backups', 'Backups', [
          ['Backup All',      { id: 'backup-all' }],
          ['Restore Latest',  { id: 'restore-latest' }]
        ]);

        
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
          t.innerHTML = '<thead><tr><th>Title</th><th>Size</th><th>Modified</th><th></th></tr></thead><tbody></tbody>';
          const tb = t.querySelector('tbody');

          files.forEach(f => {
            const tr  = document.createElement('tr');
            const sizeBytes = (f.bytes || f.size) || 0;
            const ts   = f.mtime || f.ts;
            const dt   = ts ? new Date(ts * 1000).toLocaleString() : '';
            const title = f.title || (f.name ? f.name.replace(/\.[^/.]+$/, '') : '');
            let sizeLabel = `${sizeBytes} B`;
            if (sizeBytes >= 1024 * 1024) {
              sizeLabel = `${(sizeBytes / 1024 / 1024).toFixed(1)} MB`;
            } else if (sizeBytes >= 1024) {
              sizeLabel = `${Math.round(sizeBytes / 1024)} KB`;
            }

            const a = document.createElement('a');
            a.href = `/api/backups/download?rel=${encodeURIComponent(f.rel || f.name)}`;
            a.className = 'download-link';
            a.title = f.name || '';
            a.innerHTML = `<span class="file-name">${escapeHtml(title || f.name)}</span>`;

            tr.innerHTML = `
              <td>${a.outerHTML}</td>
              <td>${sizeLabel}</td>
              <td>${escapeHtml(dt)}</td>
              <td><a href="${a.href}" class="download-link">Download</a></td>
            `;
            tb.appendChild(tr);
          });

          s.appendChild(t);
        }

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

    let settingsAutoSaveTimer;
    let autoBackupSaveTimer;

    async function loadSettings(){
      let sec;
      try{
        sec = document.getElementById('settings');
        if (!sec) return;
        sec.dataset.settingsHydrating = '1';
        const publicStatus = document.getElementById('settings-public-status');
        const publicGuild = document.getElementById('settings-public-guild');
        const publicChannel = document.getElementById('settings-public-channel');
        const notificationChannels = {
          dms: document.getElementById('settings-notify-dms'),
          bell: document.getElementById('settings-notify-bell')
        };
        const notificationStatus = document.getElementById('settings-notifications-status');
        const notificationChecks = {
          splits: document.getElementById('settings-notify-splits'),
          matches: document.getElementById('settings-notify-matches'),
          bets: document.getElementById('settings-notify-bets'),
          stages: document.getElementById('settings-notify-stages')
        };
        if (publicStatus) publicStatus.textContent = 'Loading settings...';
        const refreshBtn = document.getElementById('settings-refresh');
        if (refreshBtn && !refreshBtn.dataset.bound) {
          refreshBtn.dataset.bound = '1';
          refreshBtn.addEventListener('click', loadSettings);
        }
        try{
          const data = await fetchJSON('/api/settings');
          const effectiveGuild = data?.effective_guild_id
            || data?.selected_guild_id
            || data?.primary_guild_id
            || '';
          if (publicGuild) publicGuild.textContent = effectiveGuild || 'Not set';
          if (publicChannel) {
            publicChannel.textContent = data?.stage_announce_channel
              ? `#${data.stage_announce_channel}`
              : 'Not set';
          }
          if (publicStatus) publicStatus.textContent = '';
        }catch(e){
          if (publicStatus) publicStatus.textContent = `Failed to load settings: ${e.message}`;
        }

        const loadNotificationSettings = async () => {
          if (!notificationChannels.dms && !notificationChannels.bell) return;
          try {
            const data = await fetchJSON('/api/me/notification-settings');
            const pref = typeof data?.preference === 'string' ? data.preference : '';
            if (notificationChannels.dms && notificationChannels.bell) {
              if (pref === 'dms') {
                notificationChannels.dms.checked = true;
                notificationChannels.bell.checked = false;
              } else if (pref === 'bell') {
                notificationChannels.dms.checked = false;
                notificationChannels.bell.checked = true;
              } else if (pref === 'none') {
                notificationChannels.dms.checked = false;
                notificationChannels.bell.checked = false;
              } else {
                notificationChannels.dms.checked = true;
                notificationChannels.bell.checked = true;
              }
            }
            const categories = data?.categories || {};
            Object.keys(notificationChecks).forEach((key) => {
              if (notificationChecks[key]) {
                notificationChecks[key].checked = categories[key] !== false;
              }
            });
            const connected = data?.connected !== false;
            Object.values(notificationChannels).forEach((input) => {
              if (input) input.disabled = !connected;
            });
            Object.values(notificationChecks).forEach((input) => {
              if (input) input.disabled = !connected;
            });
            if (notificationStatus) {
              notificationStatus.textContent = connected ? '' : 'Connect Discord to update notification preferences.';
            }
          } catch (e) {
            if (notificationStatus) {
              notificationStatus.textContent = `Failed to load notification preferences: ${e.message}`;
            }
          }
        };

        const buildNotificationPayload = () => {
          const dmsEnabled = notificationChannels.dms?.checked;
          const bellEnabled = notificationChannels.bell?.checked;
          let preference = '';
          if (dmsEnabled && bellEnabled) preference = '';
          else if (dmsEnabled) preference = 'dms';
          else if (bellEnabled) preference = 'bell';
          else preference = 'none';
          return {
            preference,
            categories: Object.keys(notificationChecks).reduce((acc, key) => {
              const input = notificationChecks[key];
              acc[key] = input ? input.checked : true;
              return acc;
            }, {})
          };
        };

        const saveNotificationSettings = async () => {
          if (notificationStatus) notificationStatus.textContent = '';
          try {
            await fetchJSON('/api/me/notification-settings', {
              method: 'POST',
              body: JSON.stringify(buildNotificationPayload())
            });
            if (notificationStatus) notificationStatus.textContent = '';
            notify('Saved');
          } catch (e) {
            if (notificationStatus) notificationStatus.textContent = '';
            notify(`Failed to save preferences: ${e.message}`, false);
          }
        };

        Object.values(notificationChannels).forEach((input) => {
          if (input && !input.dataset.bound) {
            input.dataset.bound = '1';
            input.addEventListener('change', saveNotificationSettings);
          }
        });

        Object.values(notificationChecks).forEach((input) => {
          if (input && !input.dataset.bound) {
            input.dataset.bound = '1';
            input.addEventListener('change', saveNotificationSettings);
          }
        });

        await loadNotificationSettings();

        const setSelectOptions = (select, options, placeholder) => {
          if (!select) return;
          const frag = document.createDocumentFragment();
          if (placeholder) {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = placeholder;
            opt.disabled = true;
            frag.appendChild(opt);
          }
          options.forEach(({ value, label }) => {
            const opt = document.createElement('option');
            opt.value = value;
            opt.textContent = label;
            frag.appendChild(opt);
          });
          select.innerHTML = '';
          select.appendChild(frag);
        };

        const timezoneSelect = document.getElementById('settings-timezone-select');
        const dateFormatSelect = document.getElementById('settings-date-format-select');
        if (timezoneSelect && !timezoneSelect.dataset.bound) {
          timezoneSelect.dataset.bound = '1';
          const options = [];
          const offsets = new Set();
          const formatLabel = window.formatOffsetLabel || formatOffsetLabel;
          const localLabel = window.getLocalOffsetLabel ? window.getLocalOffsetLabel() : formatLabel(-new Date().getTimezoneOffset());
          for (let hour = 14; hour >= -11; hour -= 1) {
            offsets.add(hour * 60);
          }
          [
            750,  
            630,  
            570,  
            330,  
            270,  
            210,  
            -210, 
            -270, 
            -570, 
            -630  
          ].forEach((minutes) => offsets.add(minutes));
          [...offsets]
            .sort((a, b) => b - a)
            .forEach((minutes) => {
              const label = formatLabel(minutes);
              options.push({ value: label, label });
            });
          setSelectOptions(timezoneSelect, options, 'Select a timezone');
          const preferred = window.getPreferredTimeZone ? window.getPreferredTimeZone() : localLabel;
          if (options.some((opt) => opt.value === preferred)) {
            timezoneSelect.value = preferred;
          } else {
            timezoneSelect.value = options.some((opt) => opt.value === localLabel) ? localLabel : 'GMT+00';
          }
          timezoneSelect.addEventListener('change', () => {
            localStorage.setItem(window.TIMEZONE_STORAGE_KEY || TIMEZONE_STORAGE_KEY, timezoneSelect.value);
            if (dateFormatSelect && !localStorage.getItem(window.DATE_FORMAT_STORAGE_KEY || DATE_FORMAT_STORAGE_KEY)) {
              dateFormatSelect.value = window.getPreferredDateFormat ? window.getPreferredDateFormat() : dateFormatSelect.value;
            }
            routePage();
            window.dispatchEvent(new CustomEvent('timezonechange', { detail: { value: timezoneSelect.value } }));
            if (typeof window.updateFanZoneTimes === 'function') {
              window.updateFanZoneTimes();
            } else if (typeof window.loadFanZone === 'function') {
              window.loadFanZone();
            }
          });
        }
        if (dateFormatSelect && !dateFormatSelect.dataset.bound) {
          dateFormatSelect.dataset.bound = '1';
          dateFormatSelect.value = window.getPreferredDateFormat ? window.getPreferredDateFormat() : dateFormatSelect.value;
          dateFormatSelect.addEventListener('change', () => {
            localStorage.setItem(window.DATE_FORMAT_STORAGE_KEY || DATE_FORMAT_STORAGE_KEY, dateFormatSelect.value);
            routePage();
            window.dispatchEvent(new CustomEvent('dateformatchange', { detail: { value: dateFormatSelect.value } }));
            if (typeof window.updateFanZoneTimes === 'function') {
              window.updateFanZoneTimes();
            } else if (typeof window.loadFanZone === 'function') {
              window.loadFanZone();
            }
          });
        }

        const status = document.getElementById('settings-status');
        const channelStatus = document.getElementById('settings-channels-status');
        const guildSelect = document.getElementById('settings-guild-select');
        const categorySelect = document.getElementById('settings-category-select');
        const channelSelect = document.getElementById('settings-channel-select');
        if (status) status.textContent = '';

        const maintenanceToggle = document.getElementById('settings-maintenance-toggle');
        const maintenanceStatus = document.getElementById('settings-maintenance-status');
        const maintenanceBackdrop = document.getElementById('maintenance-backdrop');
        const maintenanceTitle = document.getElementById('maintenance-title');
        const maintenanceMessage = document.getElementById('maintenance-message');
        const maintenanceConfirm = document.getElementById('maintenance-confirm');
        const maintenanceCancel = document.getElementById('maintenance-cancel');
        const maintenanceClose = document.getElementById('maintenance-close');
        const autoBackupEnabled = document.getElementById('settings-auto-backup-enabled');
        const autoBackupInterval = document.getElementById('settings-auto-backup-interval');
        const autoBackupStatus = document.getElementById('settings-auto-backup-status');

        const setMaintenanceUnavailable = (message, buttonLabel = 'Unavailable') => {
          if (maintenanceStatus) maintenanceStatus.textContent = message;
          if (maintenanceToggle) {
            maintenanceToggle.disabled = true;
            maintenanceToggle.textContent = buttonLabel;
          }
        };

        if (!state.admin) {
          setMaintenanceUnavailable('Admin login required to change maintenance mode.', 'Admin only');
          if (autoBackupStatus) {
            autoBackupStatus.textContent = 'Admin login required to change auto backup settings.';
          }
          return;
        }
        if (!getAdminView()) {
          setMaintenanceUnavailable('Enable Admin View to edit maintenance mode.', 'Admin View required');
          if (autoBackupStatus) {
            autoBackupStatus.textContent = 'Enable Admin View to edit auto backup settings.';
          }
          return;
        }

        let data;
        try {
          data = await fetchJSON('/admin/settings');
        } catch (e) {
          setMaintenanceUnavailable(`Failed to load maintenance settings: ${e.message}`);
          if (status) status.textContent = '';
          return;
        }

        const setMaintenanceState = (enabled) => {
          if (maintenanceToggle) {
            maintenanceToggle.disabled = false;
            maintenanceToggle.dataset.enabled = enabled ? '1' : '0';
            maintenanceToggle.textContent = enabled ? 'Disable maintenance mode' : 'Enable maintenance mode';
            maintenanceToggle.classList.toggle('btn-stop', enabled);
            maintenanceToggle.classList.toggle('btn-outline', !enabled);
          }
          if (maintenanceStatus) {
            maintenanceStatus.textContent = enabled
              ? 'Enabled — non-admins will see the maintenance page.'
              : 'Disabled';
          }
        };

        const updateAutoBackupStatus = (enabled, intervalHours, lastTs) => {
          if (!autoBackupStatus) return;
          const label = Number.isFinite(intervalHours) ? `${intervalHours}h` : '—';
          if (!enabled) {
            autoBackupStatus.textContent = `Auto backups disabled · Interval: ${label}`;
            return;
          }
          const lastLabel = lastTs
            ? new Date(lastTs * 1000).toLocaleString()
            : 'No backups yet';
          autoBackupStatus.textContent = `Last backup: ${lastLabel} · Auto backups enabled`;
        };

        if (!isAdminUI()) return;

        const closeMaintenanceModal = () => {
          if (maintenanceBackdrop) maintenanceBackdrop.style.display = 'none';
        };

        const openMaintenanceModal = (enable) => {
          if (!maintenanceBackdrop) return;
          if (maintenanceTitle) {
            maintenanceTitle.textContent = enable ? 'Enable maintenance mode' : 'Disable maintenance mode';
          }
          if (maintenanceMessage) {
            maintenanceMessage.textContent = enable
              ? 'Enabling maintenance mode will make the site unavailable to everyone except admins. Visitors will see: "We\'re working on the site right now."'
              : 'Disabling maintenance mode will restore public access to the site.';
          }
          if (maintenanceConfirm) {
            maintenanceConfirm.textContent = enable ? 'Enable' : 'Disable';
            maintenanceConfirm.dataset.nextState = enable ? '1' : '0';
            maintenanceConfirm.classList.toggle('btn-stop', enable);
          }
          maintenanceBackdrop.style.display = 'flex';
        };

        setMaintenanceState(Boolean(data?.maintenance_mode));
        if (autoBackupEnabled) {
          autoBackupEnabled.checked = Boolean(data?.auto_backup_enabled);
        }
        if (autoBackupInterval) {
          autoBackupInterval.value = Number.isFinite(Number(data?.auto_backup_interval_hours))
            ? Number(data.auto_backup_interval_hours)
            : 6;
        }
        updateAutoBackupStatus(
          Boolean(data?.auto_backup_enabled),
          Number(data?.auto_backup_interval_hours),
          Number(data?.auto_backup_last_ts) || 0
        );
        const savedChannel = data?.stage_announce_channel || '';
        const primaryGuildId = data?.primary_guild_id || '';
        if (guildSelect) guildSelect.value = data?.selected_guild_id || '';
        if (guildSelect) {
          try{
            let guilds = [];
            try {
              const guildData = await fetchJSON('/admin/discord/guilds');
              guilds = Array.isArray(guildData?.guilds) ? guildData.guilds : [];
            } catch (e) {
              const guildData = await fetchJSON('/api/guilds');
              guilds = Array.isArray(guildData?.guilds) ? guildData.guilds : [];
            }
            const options = guilds
              .filter((g) => g?.id)
              .map((g) => ({
                value: String(g.id),
                label: g?.name ? `${g.name} (${g.id})` : String(g.id)
              }));
            setSelectOptions(guildSelect, options, 'Select a guild');
            const selectedId = data?.selected_guild_id || primaryGuildId || '';
            const match = options.find((opt) => opt.value === selectedId);
            guildSelect.value = match ? selectedId : '';
          }catch(e){
            guildSelect.innerHTML = '<option value="" disabled>Failed to load guilds</option>';
          }
        }
        const isHydrating = () => sec?.dataset.settingsHydrating === '1';
        const saveSettings = async ({ silent = false } = {}) => {
          try {
            const channel = (channelSelect?.value || '').trim();
            const selectedGuildId = (guildSelect?.value || '').trim();
            if (status) status.textContent = '';
            await fetchJSON('/admin/settings', {
              method: 'POST',
              body: JSON.stringify({
                stage_announce_channel: channel,
                selected_guild_id: selectedGuildId
              })
            });
            if (status) status.textContent = '';
            if (!silent) {
              notify('Saved');
              await loadSettings();
            }
          } catch (e) {
            if (status) status.textContent = '';
            if (!silent) {
              notify(`Failed to save settings: ${e.message}`, false);
            }
          }
        };

        const saveAutoBackupSettings = async ({ silent = false } = {}) => {
          if (!autoBackupEnabled || !autoBackupInterval) return;
          const hours = Number(autoBackupInterval.value);
          if (!Number.isFinite(hours) || hours <= 0) {
            if (autoBackupStatus) {
              autoBackupStatus.textContent = 'Enter a valid interval greater than 0 hours.';
            }
            return;
          }
          try {
            await fetchJSON('/admin/settings', {
              method: 'POST',
              body: JSON.stringify({
                auto_backup_enabled: autoBackupEnabled.checked,
                auto_backup_interval_hours: hours
              })
            });
            updateAutoBackupStatus(autoBackupEnabled.checked, hours, data?.auto_backup_last_ts || 0);
            if (!silent) {
              notify('Auto backup settings saved');
              await loadSettings();
            }
          } catch (e) {
            if (!silent) {
              notify(`Failed to save auto backup settings: ${e.message}`, false);
            }
          }
        };

        const scheduleAutoBackupSave = () => {
          if (isHydrating()) return;
          if (autoBackupSaveTimer) clearTimeout(autoBackupSaveTimer);
          autoBackupSaveTimer = setTimeout(() => {
            saveAutoBackupSettings({ silent: true });
          }, 500);
        };

        const scheduleAutoSave = () => {
          if (isHydrating()) return;
          if (settingsAutoSaveTimer) clearTimeout(settingsAutoSaveTimer);
          settingsAutoSaveTimer = setTimeout(() => {
            saveSettings({ silent: true });
          }, 500);
        };

        const loadChannelsForGuild = async (guildId, preferredChannel) => {
          if (!guildId) {
            setSelectOptions(categorySelect, [], 'Select a guild first');
            setSelectOptions(channelSelect, [], 'Select a guild first');
            if (channelStatus) channelStatus.textContent = 'Select a guild to load channels.';
            return;
          }
          if (channelStatus) channelStatus.textContent = 'Loading channels...';
          if (categorySelect) categorySelect.innerHTML = '';
          if (channelSelect) channelSelect.innerHTML = '';
          try{
            const url = guildId
              ? `/admin/discord/channels?guild_id=${encodeURIComponent(guildId)}`
              : '/admin/discord/channels';
            const channelData = await fetchJSON(url);
            const channels = Array.isArray(channelData?.channels) ? channelData.channels : [];
            if (!channels.length) {
              setSelectOptions(categorySelect, [], 'No categories found');
              setSelectOptions(channelSelect, [], 'No channels found');
              if (channelStatus) channelStatus.textContent = '';
              return;
            }

            const categories = [];
            const seen = new Set();
            let hasUncategorized = false;
            channels.forEach((row) => {
              const name = String(row?.category || '').trim();
              if (!name) {
                hasUncategorized = true;
                return;
              }
              if (!seen.has(name)) {
                seen.add(name);
                categories.push(name);
              }
            });

            const categoryOptions = categories.map((name) => ({ value: name, label: name }));
            if (hasUncategorized) {
              categoryOptions.unshift({ value: '', label: 'No category' });
            }
            const categoryPlaceholder = hasUncategorized ? '' : 'Select a category';
            setSelectOptions(categorySelect, categoryOptions, categoryPlaceholder);

            let selectedCategory = '';
            if (preferredChannel) {
              const match = channels.find((row) => (row?.channel || '') === preferredChannel);
              if (match) selectedCategory = match?.category || '';
            }
            if (!selectedCategory && categoryOptions.length) {
              selectedCategory = categoryOptions[0].value;
            }
            if (categorySelect) categorySelect.value = selectedCategory;

            const updateChannelOptions = () => {
              const activeCategory = categorySelect?.value || '';
              const channelOptions = channels
                .filter((row) => (row?.category || '') === activeCategory)
                .map((row) => ({
                  value: row?.channel || '',
                  label: row?.channel || ''
                }))
                .filter((opt) => opt.value);
              setSelectOptions(channelSelect, channelOptions, 'Select a channel');
              if (preferredChannel && channelOptions.some((opt) => opt.value === preferredChannel)) {
                channelSelect.value = preferredChannel;
              } else if (channelOptions.length) {
                channelSelect.value = channelOptions[0].value;
              }
            };

            if (categorySelect) {
              categorySelect.onchange = () => {
                updateChannelOptions();
                scheduleAutoSave();
              };
            }
            updateChannelOptions();
            if (channelStatus) channelStatus.textContent = '';
          }catch(e){
            if (channelStatus) channelStatus.textContent = `Failed to load channels: ${e.message}`;
          }
        };

        if (guildSelect && !guildSelect.dataset.bound) {
          guildSelect.dataset.bound = '1';
          guildSelect.addEventListener('change', async () => {
            await loadChannelsForGuild(guildSelect.value, channelSelect?.value || savedChannel);
            scheduleAutoSave();
          });
        }

        if (channelSelect && !channelSelect.dataset.bound) {
          channelSelect.dataset.bound = '1';
          channelSelect.addEventListener('change', scheduleAutoSave);
        }

        if (maintenanceToggle && !maintenanceToggle.dataset.bound) {
          maintenanceToggle.dataset.bound = '1';
          maintenanceToggle.addEventListener('click', () => {
            const enabled = maintenanceToggle.dataset.enabled === '1';
            openMaintenanceModal(!enabled);
          });
        }

        if (maintenanceConfirm && !maintenanceConfirm.dataset.bound) {
          maintenanceConfirm.dataset.bound = '1';
          maintenanceConfirm.addEventListener('click', async () => {
            const nextState = maintenanceConfirm.dataset.nextState === '1';
            try {
              await fetchJSON('/admin/settings', {
                method: 'POST',
                body: JSON.stringify({
                  maintenance_mode: nextState,
                  stage_announce_channel: (channelSelect?.value || '').trim(),
                  selected_guild_id: (guildSelect?.value || '').trim()
                })
              });
              setMaintenanceState(nextState);
              closeMaintenanceModal();
              notify(nextState ? 'Maintenance mode enabled' : 'Maintenance mode disabled');
            } catch (e) {
              notify(`Failed to update maintenance mode: ${e.message}`, false);
            }
          });
        }

        if (maintenanceCancel && !maintenanceCancel.dataset.bound) {
          maintenanceCancel.dataset.bound = '1';
          maintenanceCancel.addEventListener('click', closeMaintenanceModal);
        }

        if (maintenanceClose && !maintenanceClose.dataset.bound) {
          maintenanceClose.dataset.bound = '1';
          maintenanceClose.addEventListener('click', closeMaintenanceModal);
        }

        if (autoBackupEnabled && !autoBackupEnabled.dataset.bound) {
          autoBackupEnabled.dataset.bound = '1';
          autoBackupEnabled.addEventListener('change', scheduleAutoBackupSave);
        }

        if (autoBackupInterval && !autoBackupInterval.dataset.bound) {
          autoBackupInterval.dataset.bound = '1';
          autoBackupInterval.addEventListener('input', scheduleAutoBackupSave);
          autoBackupInterval.addEventListener('change', () => saveAutoBackupSettings({ silent: false }));
        }

        await loadChannelsForGuild(guildSelect?.value || '', savedChannel);

        const initEmbedMaker = async (settingsData) => {
          const embedGuildSelect = document.getElementById('embed-guild-select');
          const embedChannelSelect = document.getElementById('embed-channel-select');
          const embedSendBtn = document.getElementById('embed-send');
          const embedStatus = document.getElementById('embed-status');
          if (!embedGuildSelect || !embedChannelSelect || !embedSendBtn) return;

          const titleInput = document.getElementById('embed-title');
          const descriptionInput = document.getElementById('embed-description');
          const footerInput = document.getElementById('embed-footer');
          const footerIconInput = document.getElementById('embed-footer-icon');
          const authorInput = document.getElementById('embed-author');
          const authorIconInput = document.getElementById('embed-author-icon');
          const thumbnailInput = document.getElementById('embed-thumbnail');
          const imageInput = document.getElementById('embed-image');
          const colorInput = document.getElementById('embed-color');
          const contentInput = document.getElementById('embed-content');

          const setStatus = (msg) => {
            if (embedStatus) embedStatus.textContent = msg || '';
          };

          const loadEmbedGuilds = async () => {
            let guilds = [];
            try {
              const guildData = await fetchJSON('/admin/discord/guilds');
              guilds = Array.isArray(guildData?.guilds) ? guildData.guilds : [];
            } catch (e) {
              try {
                const guildData = await fetchJSON('/api/guilds');
                guilds = Array.isArray(guildData?.guilds) ? guildData.guilds : [];
              } catch (err) {
                guilds = [];
              }
            }
            const options = guilds
              .filter((g) => g?.id)
              .map((g) => ({
                value: String(g.id),
                label: g?.name ? `${g.name} (${g.id})` : String(g.id)
              }));
            setSelectOptions(embedGuildSelect, options, 'Select a guild');
            const preferredGuild = settingsData?.selected_guild_id || settingsData?.primary_guild_id || '';
            const selected = options.find((opt) => opt.value === preferredGuild);
            embedGuildSelect.value = selected ? preferredGuild : '';
          };

          const loadEmbedChannels = async (guildId, preferredChannelId) => {
            if (!guildId) {
              setSelectOptions(embedChannelSelect, [], 'Select a guild first');
              return;
            }
            setStatus('Loading channels...');
            try {
              const url = `/admin/discord/channels?guild_id=${encodeURIComponent(guildId)}`;
              const channelData = await fetchJSON(url);
              const channels = Array.isArray(channelData?.channels) ? channelData.channels : [];
              const options = channels
                .filter((row) => row?.id)
                .map((row) => {
                  const category = String(row?.category || '').trim();
                  const channel = String(row?.channel || '').trim();
                  const label = category ? `${category} / #${channel}` : `#${channel}`;
                  return { value: String(row.id), label };
                });
              setSelectOptions(embedChannelSelect, options, 'Select a channel');
              if (preferredChannelId && options.some((opt) => opt.value === preferredChannelId)) {
                embedChannelSelect.value = preferredChannelId;
              } else if (options.length) {
                embedChannelSelect.value = options[0].value;
              }
              setStatus('');
            } catch (e) {
              setStatus(`Failed to load channels: ${e.message}`);
            }
          };

          if (!embedGuildSelect.dataset.bound) {
            embedGuildSelect.dataset.bound = '1';
            embedGuildSelect.addEventListener('change', async () => {
              await loadEmbedChannels(embedGuildSelect.value, embedChannelSelect?.value || '');
            });
          }

          if (!embedSendBtn.dataset.bound) {
            embedSendBtn.dataset.bound = '1';
            embedSendBtn.addEventListener('click', async () => {
              const channelId = (embedChannelSelect?.value || '').trim();
              if (!channelId) {
                setStatus('Select a channel before sending.');
                return;
              }
              setStatus('');
              try {
                await fetchJSON('/admin/embed', {
                  method: 'POST',
                  body: JSON.stringify({
                    channel_id: channelId,
                    title: (titleInput?.value || '').trim(),
                    description: (descriptionInput?.value || '').trim(),
                    footer_text: (footerInput?.value || '').trim(),
                    footer_icon_url: (footerIconInput?.value || '').trim(),
                    author_name: (authorInput?.value || '').trim(),
                    author_icon_url: (authorIconInput?.value || '').trim(),
                    thumbnail_url: (thumbnailInput?.value || '').trim(),
                    image_url: (imageInput?.value || '').trim(),
                    color: (colorInput?.value || '').trim(),
                    content: (contentInput?.value || '').trim()
                  })
                });
                notify('Embed sent');
              } catch (e) {
                notify(`Failed to send embed: ${e.message}`, false);
              }
            });
          }

          await loadEmbedGuilds();
          await loadEmbedChannels(embedGuildSelect?.value || '', '');
        };

        await initEmbedMaker(data);
        await loadMatchTimings();
      }catch(e){
        notify(`Settings error: ${e.message}`, false);
      }finally{
        if (sec) sec.dataset.settingsHydrating = '0';
      }
    }

    async function loadLogs(){
      if (!state.logsInit){
        buildLogsCard();
        state.logsInit = true;
      }
      await fetchAndRenderLogs();
    }

    function buildLogsCard(){
      const sec = document.querySelector('#log');
      if (!sec) return;

      sec.innerHTML = '';

      const wrap = document.createElement('div');
      wrap.className = 'table-wrap';

      const head = document.createElement('div');
      head.className = 'table-head';
      head.innerHTML = `
        <div class="table-title">Logs</div>
        <div class="table-actions">
          <div class="chip-group" role="tablist" aria-label="Log kind">
            <button id="log-kind-bot" class="btn btn-chip" data-kind="bot">Bot</button>
            <button id="log-kind-health" class="btn btn-chip" data-kind="health">Health</button>
            <button id="log-kind-launcher" class="btn btn-chip" data-kind="launcher">Launcher</button>
          </div>
          <button id="log-refresh" class="btn">Refresh</button>
          <button id="log-clear" class="btn">Clear</button>
          <a id="log-download" class="btn" href="/api/log/bot/download">Download</a>
          <input id="log-search" type="text" placeholder="Search">
        </div>
      `;
      wrap.appendChild(head);

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

    
    function splitTimeMsg(line){
      
      const re1 = /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:[,\.]\d{3})?)(?:\s+|\s*\|\s*)(.*)$/;
      let m = line.match(re1);
      if (m) return [m[1], m[2]];

      
      const re2 = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)(?:\s+|\s*\|\s*)(.*)$/;
      m = line.match(re2);
      if (m) return [m[1], m[2]];

      
      const i = line.indexOf('|');
      if (i > 0) return [line.slice(0, i).trim(), line.slice(i + 1).trim()];

      
      return ['', line];
    }


    function orderLogLines(lines){
      if (!lines.length){
        return lines;
      }
      if (lines.length < 2){
        return [...lines].reverse();
      }
      const [firstTime] = splitTimeMsg(lines[0]);
      const [lastTime] = splitTimeMsg(lines[lines.length - 1]);
      if (firstTime && lastTime && firstTime > lastTime){
        return lines;
      }
      return [...lines].reverse();
    }

    function renderLogLines(lines){
      const tb = document.getElementById('log-tbody');
      tb.innerHTML = '';
      if (!lines.length){
        tb.innerHTML = `<tr><td colspan="2" class="muted">No log lines yet.</td></tr>`;
        return;
      }
      const ordered = orderLogLines(lines);
      for (const raw of ordered){
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
      return String(s ?? '').replace(/[&<>"']/g, (c) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      }[c]));
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

      
      const pill = document.createElement('span');
      pill.className = 'pill pill-wait';
      pill.textContent = '…';
      tdS.appendChild(pill);

      const setPill = (loaded) => {
        pill.className = 'pill ' + (loaded ? 'pill-ok' : 'pill-off');
        pill.textContent = loaded ? 'Loaded' : 'Unloaded';
      };

      
      if (typeof loadedHint === 'boolean') setPill(loadedHint);
      else {
        getCogStatus(name).then(v => {
          if (typeof v === 'boolean') setPill(v);
          else { pill.className='pill pill-off'; pill.textContent='Unknown'; }
        });
      }

        
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
  
  try {
    const s = await fetchJSON(`/admin/cogs/${encodeURIComponent(name)}/status`);
    if (typeof s?.loaded === 'boolean') return s.loaded;
  } catch {}
  try {
    const list = await fetchJSON('/admin/cogs');
    const row = (list?.cogs || []).find(c => c.name === name);
    if (typeof row?.loaded === 'boolean') return row.loaded;
  } catch {}
  
  try {
    const s = await fetchJSON(`/api/cogs/${encodeURIComponent(name)}/status`);
    if (typeof s?.loaded === 'boolean') return s.loaded;
  } catch {}
  return null; 
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
      case 'dashboard':
        await loadDash();
        break;
      case 'bets': await loadAndRenderBets(); break;
      case 'ownership': await loadOwnershipPage(); break;
      case 'settings': await loadSettings(); break;
      case 'splits': await loadSplits(); break;
      case 'backups': if(isAdminUI()) await loadBackups(); else setPage('dashboard'); break;
      case 'log': if(isAdminUI()) await loadLogs('bot'); else setPage('dashboard'); break;
      case 'cogs': if(isAdminUI()) await loadCogs(); else setPage('dashboard'); break;
    }
  }

  function startPolling(){
    stopPolling();
    state.pollingId = setInterval(async ()=>{
      await loadDash();
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
      applyDashboardWarningState();
      await routePage();
      if (state.currentPage !== 'dashboard') {
        await loadDash();
      }
      startPolling();
    }
  window.addEventListener('load', init);


async function checkUserTOS() {
  try {
    const res = await fetch('/api/me/tos', { credentials: 'include' });
    const data = await res.json();
    if (data.connected && !data.accepted) {
      console.log('[WorldCupBot] redirecting user to /terms');
      window.location.href = data.url || '/terms';
    }
  } catch (err) {
    console.warn('TOS check failed:', err);
  }
}


document.addEventListener('DOMContentLoaded', () => {
  setTimeout(checkUserTOS, 1000);
});

})();

(function(){
  const host       = document.getElementById('map-svg-host');
  const tip        = document.getElementById('map-tip');
  const btnRefresh = document.getElementById('worldmap-refresh');

  if (!host || !tip) return;

  const CACHE_TTL_MS = 60 * 1000; 

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

    function formatOffsetLabel(totalMinutes){
    const sign = totalMinutes >= 0 ? '+' : '-';
    const abs = Math.abs(totalMinutes);
    const hours = String(Math.floor(abs / 60)).padStart(2, '0');
    const minutes = abs % 60;
    if (minutes) {
      return `GMT${sign}${hours}:${String(minutes).padStart(2, '0')}`;
    }
    return `GMT${sign}${hours}`;
  }

    function parseOffsetLabel(label){
    const match = /^GMT([+-])(\d{2})(?::(\d{2}))?$/.exec(String(label || ''));
    if (!match) return 0;
    const sign = match[1] === '-' ? -1 : 1;
    const hours = Number(match[2] || 0);
    const minutes = Number(match[3] || 0);
    if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return 0;
    return sign * (hours * 60 + minutes);
  }

    function getLocalOffsetLabel(){
    const offsetMinutes = -new Date().getTimezoneOffset();
    return formatOffsetLabel(offsetMinutes);
  }

    function getPreferredTimeZone(){
    const stored = localStorage.getItem(TIMEZONE_STORAGE_KEY);
    if (stored) return stored;
    return getLocalOffsetLabel();
  }

    function isAmericanLocale(){
    return String(navigator.language || '').toLowerCase().startsWith('en-us');
  }

    function getPreferredDateFormat(){
    const stored = localStorage.getItem(DATE_FORMAT_STORAGE_KEY);
    if (stored === 'MD' || stored === 'DM') return stored;
    return isAmericanLocale() ? 'MD' : 'DM';
  }

    function getDateTimeParts(isoString, offsetLabel){
    if (!isoString) return null;
    const d = new Date(isoString);
    if (Number.isNaN(d.getTime())) return null;
    const offsetMinutes = parseOffsetLabel(offsetLabel);
    const localMs = d.getTime() + offsetMinutes * 60 * 1000;
    const localDate = new Date(localMs);
    return {
      year: String(localDate.getUTCFullYear()),
      month: String(localDate.getUTCMonth() + 1).padStart(2, '0'),
      day: String(localDate.getUTCDate()).padStart(2, '0'),
      hour: String(localDate.getUTCHours()).padStart(2, '0'),
      minute: String(localDate.getUTCMinutes()).padStart(2, '0'),
      timeZoneName: offsetLabel
    };
  }

    function formatFixtureDateTime(isoString, { includeTime = true, includeYear = false, includeTimeZone = true } = {}){
    const timeZone = getPreferredTimeZone();
    const parts = getDateTimeParts(isoString, timeZone);
    if (!parts) return isoString || '';
    const dateOrder = getPreferredDateFormat();
    const date = dateOrder === 'MD'
      ? `${parts.month}/${parts.day}`
      : `${parts.day}/${parts.month}`;
    const dateWithYear = includeYear ? `${date}/${parts.year}` : date;
    let out = dateWithYear;
    if (includeTime) {
      out = `${out} ${parts.hour}:${parts.minute}`;
    }
    const tzLabel = includeTimeZone ? (parts.timeZoneName || timeZone) : '';
    return tzLabel ? `${out} ${tzLabel}` : out;
  }

    function formatMatchDateShort(isoString){
    if (!isoString) return '';
    return formatFixtureDateTime(isoString, { includeTime: false, includeYear: false, includeTimeZone: false });
  }

    function formatFixtureDateTimeCompact(isoString){
    const parts = getDateTimeParts(isoString, getPreferredTimeZone());
    if (!parts) return '-';
    const dateOrder = getPreferredDateFormat();
    const date = dateOrder === 'MD'
      ? `${parts.month}/${parts.day}`
      : `${parts.day}/${parts.month}`;
    return `${date} - ${parts.hour}:${parts.minute}`;
  }

    window.getPreferredTimeZone = getPreferredTimeZone;
    window.getPreferredDateFormat = getPreferredDateFormat;
    window.formatFixtureDateTime = formatFixtureDateTime;
    window.formatFixtureDateTimeCompact = formatFixtureDateTimeCompact;
    window.formatOffsetLabel = formatOffsetLabel;
    window.getLocalOffsetLabel = getLocalOffsetLabel;
    if (!window.loadMatchTimings) {
      window.loadMatchTimings = () => {};
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

  
  async function loadTeamMeta(){
    const CK  = 'wc:team_meta';
    const TTL = 24 * 60 * 60 * 1000; 

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

      
      const m1 = raw.match(/^[A-Za-z]{2}$/);

      
      const m2 = raw.match(/^iso[-_ ]?([A-Za-z]{2})$/);

      
      const m3 = raw.match(/^([A-Za-z]{2}[-_][A-Za-z]{2,3})$/);

      if (m1) {
        iso = m1[0].toLowerCase();
      } else if (m2) {
        iso = m2[1].toLowerCase();
      } else if (m3) {
        iso = m3[1].toLowerCase();
      } else {
        return; 
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
      .replace(/[\u0300-\u036f]/g, '')   
      .replace(/['’]/g, '')              
      .replace(/\s+/g, ' ')              
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

      
      if (isSelf && status === 'owned') status = 'self';

      const stateObj = { status, main: row.main_owner, splits: row.split_with };

      if (!teamState[team]) teamState[team] = stateObj;
      if (!teamState[norm]) teamState[norm] = stateObj;
    }

    
    const teamQual  = {};
    const teamGroup = {};
    const isoQual   = {};
    const isoGroup  = {};

    if (teamMeta) {
      if (teamMeta.groups) {
        
        Object.entries(teamMeta.groups).forEach(([g, arr]) => {
          (arr || []).forEach(entry => {
            let tName = '';
            let iso   = '';
            let q     = true;

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
        Object.values(teamMeta).forEach(item => {
          if (!item) return;
          const tName = item.team || item.name || '';
          const iso   = String(item.iso || '').toLowerCase();
          const q     = item.qualified !== false;
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

      const team     = isoToTeam[iso] || isoUp;
      const normTeam = normalizeTeamName(team);

      const inferIso = inferIsoFromName(team) || iso;

      const teamLabel = team;

      let status = 'nq';

      let qualified = true;
      if (teamMeta) {
        qualified = (
          teamQual[team]     === true ||
          teamQual[normTeam] === true ||
          isoQual[iso]       === true
        );
      }

      
      let ownership = null;
      if (team || normTeam) {
        ownership = teamState[team] || teamState[normTeam] || null;
      }

      if (qualified) {
        status = 'free';
        if (ownership) status = ownership.status;
      } else if (!teamMeta) {
        
        status = ownership ? ownership.status : 'free';
      }

      
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

      let stage = (stageMap[team] || stageMap[normTeam]) || '—';

      const matchObj = nextMatchByIso[iso] || nextMatchByIso[inferIso] || null;
      const nextMatch = matchObj ? matchObj.label : '';

      el.classList.remove('owned','split','free','nq','dim','self');
      el.classList.add(status);

      
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

    // Create the pan container in the SVG namespace so wrapped nodes remain valid SVG.
    const panRoot = document.createElementNS('http://www.w3.org/2000/svg', 'g');
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
        el.classList.contains('self')  ? 'Self'   :
        el.classList.contains('owned') ? 'Other'  :
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
      if (stageEl)  stageEl.textContent  = 'Ownership: ' + (stage || '—');
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

  function refreshWorldMap(){
    localStorage.removeItem('wc:ownership_merged');
    localStorage.removeItem('wc:team_iso');
    localStorage.removeItem('wc:team_meta');
    localStorage.removeItem('wc:team_stage');
    render();
  }

  if (btnRefresh){
    btnRefresh.addEventListener('click', refreshWorldMap);
  }

  const menu = document.getElementById('main-menu');
  if (menu){
    menu.addEventListener('click', (e)=>{
      const a = e.target.closest('a[data-page]');
      if (!a) return;
      if (a.getAttribute('data-page') === 'worldmap'){
        setTimeout(refreshWorldMap, 10);
      }
    });
  }

  if (document.querySelector('#worldmap.active-section')){
    render();
  }

  
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


(() => {
  'use strict';
  const qs = (s, el=document)=>el.querySelector(s);
  const qsa = (s, el=document)=>[...el.querySelectorAll(s)];
  const fetchJSON = (window.fetchJSON)?window.fetchJSON:async (u,o)=>{const r=await fetch(u,o);if(!r.ok) throw new Error(r.status);return r.json()};
  const debounce=(fn,ms=200)=>{let t;return(...a)=>{clearTimeout(t);t=setTimeout(()=>fn(...a),ms)}};
  const idHue = id => String(id||'').split('').reduce((h,ch)=>(h*31+ch.charCodeAt(0))%360,0);
  const initials = n => (n||'').trim().split(/\s+/).slice(0,2).map(p=>p[0]||'').join('').toUpperCase() || '??';

    
    function discordAvatarUrl(id, avatarHash){
      if(!id || !avatarHash) return null;
      const ext = String(avatarHash).startsWith('a_') ? 'gif' : 'png';
      return `https://cdn.discordapp.com/avatars/${id}/${avatarHash}.${ext}?size=64`;
    }

    
    function discordDefaultAvatarUrl(id){
      try {
        const idx = Number(BigInt(String(id)) % 6n); 
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

      
      const pct = (!max || max <= 0)
        ? 0
        : (value >= max ? 1 : Math.max(0, Math.min(1, value / max)));

      wrap.setAttribute('aria-label', `${value} of ${max}`);

      
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

      
      const raw = v.avatar_url || v.avatarUrl || v.avatar || v.avatar_hash || v.avatarHash || null;

      
      let avatar_url = null;
      if (raw && /^https?:\/\//i.test(String(raw))) {
        avatar_url = String(raw);
      } else if (raw && /^[aA]?_?[0-9a-f]{6,}$/.test(String(raw))) {
        const ext = String(raw).startsWith('a_') ? 'gif' : 'png';
        avatar_url = `https://cdn.discordapp.com/avatars/${id}/${raw}.${ext}?size=64`;
      } else {
        
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


    
    const missing = Object.values(vmap)
      // Backfill only users still using Discord default avatars (or missing avatar URL).
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
      
      (b.teams.length - a.teams.length) ||
      
      (b.count - a.count) ||
      
      String(a.name).localeCompare(String(b.name))
    );
    return list;
    }

    async function fetchFanZoneWinsData(){
      try{
        const res = await fetch('/api/leaderboards/fanzone_wins', { headers:{'Accept':'application/json'} });
        if(!res.ok) return [];
        const data = await res.json();
        if(Array.isArray(data)) return data;
        if(Array.isArray(data.rows)) return data.rows;
      }catch(_) {  }
      return [];
    }

    async function fetchFanZoneLossesData(){
      try{
        const res = await fetch('/api/leaderboards/fanzone_losses', { headers:{'Accept':'application/json'} });
        if(!res.ok) return [];
        const data = await res.json();
        if(Array.isArray(data)) return data;
        if(Array.isArray(data.rows)) return data.rows;
      }catch(_) {  }
      return [];
    }

    function voteResultsRowEl(rec, label){
      const row = document.createElement('div');
      row.className = 'lb-row';

      const left = document.createElement('div');
      left.className = 'lb-left';
      left.appendChild(avatarEl({id:rec.id, display_name:rec.name, avatar_url:rec.avatar_url}));
      const t = document.createElement('div');
      t.innerHTML = `<div class="lb-name">${rec.name}</div>`;
      left.appendChild(t);

      const right = document.createElement('div');
      right.className = 'lb-right';
      right.appendChild(barEl(rec.count, rec._max || rec.count));
      const stats = document.createElement('div');
      stats.className = 'lb-stats';
      const chip = document.createElement('span');
      chip.className = 'lb-chip';
      chip.textContent = `${label}: ${rec.count}`;
      stats.appendChild(chip);
      right.appendChild(stats);

      row.appendChild(left);
      row.appendChild(right);
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

      
      const main = (rec.teams || []).map(c => ({ c, cls: '' }));
      const split = (rec.split_teams || []).map(c => ({ c, cls: 'split' }));
      const combined = [...main, ...split];
      const show = combined.slice(0, 6);

      show.forEach(({c, cls}) => {
        const chip = flagChip(c, iso);
        if (cls) chip.classList.add(cls);
        flags.appendChild(chip);
      });

      
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
    return list.filter(x=>String(x.name||x.team||'').toLowerCase().includes(s));
    }

    function paginate(list, page, per=50){
      const total=Math.max(1,Math.ceil(list.length/per));
      const p=Math.max(1,Math.min(total,page));
      const start=(p-1)*per;
      return {page:p,total,slice:list.slice(start,start+per)};
    }

    async function renderLeaderboards(){
      const { rows, bets, iso, vmap } = await fetchAll();

      
      let owners = aggregateOwners(rows, vmap);
      const maxOwn = owners[0]?.count || 0;
      owners.forEach(o => o._max = maxOwn);

      
      let bettors = aggregateBettors(bets, vmap);
      const maxWin = bettors[0]?.wins || 0;
      bettors.forEach(b => b._max = maxWin);

      
      const rawVoteWins = await fetchFanZoneWinsData();
      const rawVoteLosses = await fetchFanZoneLossesData();
      let voteWins = (rawVoteWins || []).map(r => {
        const id = String(r.id || r.discord_id || '').trim();
        const prof = vmap[id] || { id, display_name: r.name || r.username || id, username: r.username || '' };
        return {
          id,
          name: prof.display_name || prof.username || id,
          count: Number(r.wins || r.count || 0),
          avatar_url: prof.avatar_url || null
        };
      }).filter(r => r.id);
      voteWins.sort((a, b) => (b.count - a.count) || String(a.name).localeCompare(String(b.name)));
      const maxVoteWins = voteWins[0]?.count || 0;
      voteWins.forEach(v => v._max = maxVoteWins);

      let voteLosses = (rawVoteLosses || []).map(r => {
        const id = String(r.id || r.discord_id || '').trim();
        const prof = vmap[id] || { id, display_name: r.name || r.username || id, username: r.username || '' };
        return {
          id,
          name: prof.display_name || prof.username || id,
          count: Number(r.losses || r.count || 0),
          avatar_url: prof.avatar_url || null
        };
      }).filter(r => r.id);
      voteLosses.sort((a, b) => (b.count - a.count) || String(a.name).localeCompare(String(b.name)));
      const maxVoteLosses = voteLosses[0]?.count || 0;
      voteLosses.forEach(v => v._max = maxVoteLosses);

      const state = (window.state = window.state || {}); state.lb = state.lb || {};
      state.lb.ownersAll = owners;
      state.lb.bettorsAll = bettors;
      state.lb.voteWinsAll = voteWins;
      state.lb.voteLossesAll = voteLosses;
      state.lb.iso = iso;

      paintOwners(); paintBettors(); paintVoteWins(); paintVoteLosses();
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
    }

    function paintVoteWins(page=1){
      const state=(window.state=window.state||{}); state.lb=state.lb||{};
      const body=qs('#lb-vote-wins-body'); if(!body) return;
      const q=qs('#lb-vote-wins-search')?.value||'';
      const list=filterByQuery(state.lb.voteWinsAll||[], q);
      const {page:cur,total,slice}=paginate(list,page,50);
      body.innerHTML='';
      if(!slice.length){ body.innerHTML='<div class="lb-empty">No voting wins to show.</div>'; }
      else { slice.forEach(r=>body.appendChild(voteResultsRowEl(r, 'Wins'))); }
      qs('#lb-vote-wins-page').textContent=`${cur}/${total}`; state.lb.voteWinsPage=cur;
    }

    function paintVoteLosses(page=1){
      const state=(window.state=window.state||{}); state.lb=state.lb||{};
      const body=qs('#lb-vote-losses-body'); if(!body) return;
      const q=qs('#lb-vote-losses-search')?.value||'';
      const list=filterByQuery(state.lb.voteLossesAll||[], q);
      const {page:cur,total,slice}=paginate(list,page,50);
      body.innerHTML='';
      if(!slice.length){ body.innerHTML='<div class="lb-empty">No voting losses to show.</div>'; }
      else { slice.forEach(r=>body.appendChild(voteResultsRowEl(r, 'Losses'))); }
      qs('#lb-vote-losses-page').textContent=`${cur}/${total}`; state.lb.voteLossesPage=cur;
    }

    function wireControls(){
    const state=(window.state=window.state||{}); state.lb=state.lb||{};
    qs('#lb-owners-search')?.addEventListener('input', debounce(()=>paintOwners(1),200));
    qs('#lb-bettors-search')?.addEventListener('input', debounce(()=>paintBettors(1),200));
    qs('#lb-vote-wins-search')?.addEventListener('input', debounce(()=>paintVoteWins(1),200));
    qs('#lb-vote-losses-search')?.addEventListener('input', debounce(()=>paintVoteLosses(1),200));
    qs('#lb-owners-refresh')?.addEventListener('click', async ()=>{state.lb.loaded=false; await loadLeaderboardsOnce();});
    qs('#lb-bettors-refresh')?.addEventListener('click', async ()=>{state.lb.loaded=false; await loadLeaderboardsOnce();});
    qs('#lb-vote-wins-refresh')?.addEventListener('click', async ()=>{state.lb.loaded=false; await loadLeaderboardsOnce();});
    qs('#lb-vote-losses-refresh')?.addEventListener('click', async ()=>{state.lb.loaded=false; await loadLeaderboardsOnce();});
    qs('#lb-owners-toggle-splits')?.addEventListener('click', async (e)=>{
      const on=e.currentTarget.dataset.on==='1'?'0':'1';
      e.currentTarget.dataset.on=on;
      e.currentTarget.textContent=`include splits: ${on==='1'?'on':'off'}`;
      state.lb.loaded=false; await loadLeaderboardsOnce();
    });
    qs('#lb-owners-prev')?.addEventListener('click', ()=>paintOwners((state.lb.ownersPage||1)-1));
    qs('#lb-owners-next')?.addEventListener('click', ()=>paintOwners((state.lb.ownersPage||1)+1));
    qs('#lb-bettors-prev')?.addEventListener('click', ()=>paintBettors((state.lb.bettorsPage||1)-1));
    qs('#lb-bettors-next')?.addEventListener('click', ()=>paintBettors((state.lb.bettorsPage||1)+1));
    qs('#lb-vote-wins-prev')?.addEventListener('click', ()=>paintVoteWins((state.lb.voteWinsPage||1)-1));
    qs('#lb-vote-wins-next')?.addEventListener('click', ()=>paintVoteWins((state.lb.voteWinsPage||1)+1));
    qs('#lb-vote-losses-prev')?.addEventListener('click', ()=>paintVoteLosses((state.lb.voteLossesPage||1)-1));
    qs('#lb-vote-losses-next')?.addEventListener('click', ()=>paintVoteLosses((state.lb.voteLossesPage||1)+1));
    }

    async function loadLeaderboardsOnce(){
    const state=(window.state=window.state||{}); state.lb=state.lb||{};
    if(state.lb.loaded) return;
    try{ await renderLeaderboards(); state.lb.loaded=true; }catch(e){ console.error('Leaderboards error',e); }
    }

    
    function hookNav(){
    const link=[...document.querySelectorAll('#main-menu a')].find(a=>a.dataset.page==='leaderboards');
    if(link){ link.addEventListener('click', ()=>loadLeaderboardsOnce(), {once:true}); }
    const sec=document.querySelector('#leaderboards');
    const obs=new IntersectionObserver((es)=>{ es.forEach(e=>{ if(e.isIntersecting) loadLeaderboardsOnce(); }); }, {root:document.querySelector('#app-main')||null, threshold:0.01});
    sec&&obs.observe(sec);
    }
    document.addEventListener('DOMContentLoaded', hookNav);
})();


(() => {
  const $ = (sel) => document.querySelector(sel);
  const escAttr = (s) => String(s || '')
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;')
    .replace(/'/g,'&#39;');
  const notify = window.notify || ((msg) => console.log('[notify]', msg));

  const {
    STAGE_ORDER = [],
    normalizeStage = (label) => String(label || '').trim()
  } = window.WorldCupStages || {};

  const fetchJSON = window.fetchJSON || (async (url, opts) => {
    const r = await fetch(url, { cache: 'no-store', ...opts });
    if (!r.ok) throw new Error(await r.text().catch(() => r.statusText));
    return r.json();
  });

  function normalizeTeamName(name){
    return String(name || '').trim().toLowerCase();
  }

  function isoFlagImg(iso){
    if (!iso) return '';
    const code = String(iso).trim().toLowerCase();
    if (!code) return '';
    const safe = code.replace(/[^a-z0-9-]/g, '');
    return `<img class="flag-img fixtures-flag" src="https://flagcdn.com/24x18/${safe}.png" alt="${safe} flag" loading="lazy"
            onerror="this.style.display='none';">`;
  }

  function buildGroupMap(teamMeta){
    const out = new Map();
    if (!teamMeta || typeof teamMeta !== 'object') return out;

    if (teamMeta.groups && typeof teamMeta.groups === 'object') {
      Object.entries(teamMeta.groups).forEach(([group, entries]) => {
        if (!Array.isArray(entries)) return;
        entries.forEach((team) => {
          const key = normalizeTeamName(team);
          if (key) out.set(key, String(group || '').toUpperCase());
        });
      });
      return out;
    }

    Object.entries(teamMeta).forEach(([team, meta]) => {
      const group = meta && typeof meta === 'object' ? meta.group : null;
      const key = normalizeTeamName(team);
      if (key && group) out.set(key, String(group).toUpperCase());
    });
    return out;
  }

  function stageRank(stage){
    const label = normalizeStage(stage);
    if (Array.isArray(STAGE_ORDER) && STAGE_ORDER.length) {
      const idx = STAGE_ORDER.indexOf(label);
      return idx === -1 ? 999 : idx;
    }
    return 999;
  }

  function stageBadge(stage){
    const label = normalizeStage(stage) || 'Group Stage';
    const cls = label === 'Winner' ? 'pill-ok' : label === 'Eliminated' ? 'pill-off' : 'pill';
    return `<span class="${cls}">${escAttr(label)}</span>`;
  }

  function parseScore(val){
    const n = Number(val);
    return Number.isFinite(n) ? n : null;
  }

  function computeRecords(fixtures, winnersMap){
    const rec = new Map();
    let seq = 0;
    fixtures.forEach(f => {
      const home = String(f.home || '').trim();
      const away = String(f.away || '').trim();
      if (!home || !away) return;
      const winnerRec = winnersMap?.[f.id] || null;
      let winnerSide = String(winnerRec?.winner_side || winnerRec?.winner || '').toLowerCase();

      if (winnerSide !== 'home' && winnerSide !== 'away' && winnerSide !== 'draw') return;

      const homeRec = rec.get(home) || { w: 0, d: 0, l: 0, form: [] };
      const awayRec = rec.get(away) || { w: 0, d: 0, l: 0, form: [] };
      const stamp = Number.isFinite(Date.parse(f.utc)) ? Date.parse(f.utc) : null;
      const order = seq++;

      if (winnerSide === 'home') {
        homeRec.w += 1;
        awayRec.l += 1;
        homeRec.form.push({ result: 'win', stamp, order });
        awayRec.form.push({ result: 'loss', stamp, order });
      } else if (winnerSide === 'away') {
        homeRec.l += 1;
        awayRec.w += 1;
        homeRec.form.push({ result: 'loss', stamp, order });
        awayRec.form.push({ result: 'win', stamp, order });
      } else {
        homeRec.d += 1;
        awayRec.d += 1;
        homeRec.form.push({ result: 'draw', stamp, order });
        awayRec.form.push({ result: 'draw', stamp, order });
      }

      rec.set(home, homeRec);
      rec.set(away, awayRec);
    });
    rec.forEach((entry) => {
      if (!Array.isArray(entry.form)) entry.form = [];
      entry.form.sort((a, b) => {
        if (a.stamp !== null && b.stamp !== null && a.stamp !== b.stamp) {
          return a.stamp - b.stamp;
        }
        if (a.stamp !== null && b.stamp === null) return -1;
        if (a.stamp === null && b.stamp !== null) return 1;
        return a.order - b.order;
      });
      entry.form = entry.form.slice(-5);
    });
    return rec;
  }

  function recordBar(rec){
    const form = Array.isArray(rec.form) ? rec.form : [];
    const padded = Array.from({ length: 5 }, (_, i) => {
      const idx = form.length - 5 + i;
      return idx >= 0 ? form[idx] : null;
    });
    const label = padded.map(entry => {
      if (!entry) return '-';
      return entry.result === 'win' ? 'W' : entry.result === 'loss' ? 'L' : 'D';
    }).join(' ');
    return `
      <div class="wdl-form" role="img" aria-label="Last 5: ${escAttr(label)}">
        <span class="wdl-label">Last 5</span>
        <div class="wdl-dots">
          ${padded.map(entry => {
            const cls = entry?.result ? entry.result : 'empty';
            return `<span class="wdl-dot ${cls}"></span>`;
          }).join('')}
        </div>
      </div>
    `;
  }

  function renderTeamList(host, teams, records, emptyLabel, isoByName){
    if (!host) return;
    host.classList.remove('results-list');
    if (!teams.length) {
      host.innerHTML = `<div class="muted">${escAttr(emptyLabel)}</div>`;
      return;
    }

    host.innerHTML = teams.map(({ name, stage }) => {
      const rec = records.get(name) || { w: 0, d: 0, l: 0 };
      const flag = isoFlagImg(isoByName?.[normalizeTeamName(name)] || '');
      return `
        <div class="fixtures-team compact">
          <div class="fixtures-team-head">
            <div class="fixtures-team-meta">
              ${flag}
              <div class="fixtures-team-meta-text">
                <span class="fixtures-team-name">${escAttr(name)}</span>
                <span class="fixtures-team-stage">${stageBadge(stage)}</span>
              </div>
            </div>
          </div>
          <div class="fixtures-team-record">
            ${recordBar(rec)}
          </div>
        </div>
      `;
    }).join('');
  }

  function renderResultsList(host, fixtures, isoByName, groupByName, activeGroup, emptyLabel){
    if (!host) return;
    host.classList.add('results-list');
    if (!Array.isArray(fixtures) || !fixtures.length) {
      host.innerHTML = `
        <div class="muted">${escAttr(emptyLabel)}</div>
        <div class="fixtures-result is-demo">
          <div class="fixtures-result-team">
            ${isoFlagImg('us')}
            <span class="fixtures-result-name">Example A</span>
          </div>
          <div class="fixtures-result-score">2 - 1</div>
          <div class="fixtures-result-team away">
            <span class="fixtures-result-name">Example B</span>
            ${isoFlagImg('gb')}
          </div>
        </div>
        <div class="fixtures-result is-demo">
          <div class="fixtures-result-team">
            ${isoFlagImg('fr')}
            <span class="fixtures-result-name">Example C</span>
          </div>
          <div class="fixtures-result-score">0 - 0</div>
          <div class="fixtures-result-team away">
            <span class="fixtures-result-name">Example D</span>
            ${isoFlagImg('de')}
          </div>
        </div>
      `;
      return;
    }

    const filtered = fixtures.filter((fixture) => {
      const home = String(fixture.home || '').trim();
      const away = String(fixture.away || '').trim();
      if (!home || !away) return false;
      const hs = parseScore(fixture.home_score);
      const as = parseScore(fixture.away_score);
      if (hs === null || as === null) return false;
      if (!activeGroup || activeGroup === 'ALL') return true;
      const homeGroup = groupByName.get(normalizeTeamName(home)) || '';
      const awayGroup = groupByName.get(normalizeTeamName(away)) || '';
      return String(homeGroup).toUpperCase() === activeGroup || String(awayGroup).toUpperCase() === activeGroup;
    });

    const sorted = filtered.sort((a, b) => {
      const aStamp = Number.isFinite(Date.parse(a.utc)) ? Date.parse(a.utc) : -Infinity;
      const bStamp = Number.isFinite(Date.parse(b.utc)) ? Date.parse(b.utc) : -Infinity;
      if (aStamp !== bStamp) return bStamp - aStamp;
      return String(b.id || '').localeCompare(String(a.id || ''));
    });

    if (!sorted.length) {
      host.innerHTML = `
        <div class="muted">${escAttr(emptyLabel)}</div>
        <div class="fixtures-result is-demo">
          <div class="fixtures-result-team">
            ${isoFlagImg('us')}
            <span class="fixtures-result-name">Example A</span>
          </div>
          <div class="fixtures-result-score">2 - 1</div>
          <div class="fixtures-result-team away">
            <span class="fixtures-result-name">Example B</span>
            ${isoFlagImg('gb')}
          </div>
        </div>
        <div class="fixtures-result is-demo">
          <div class="fixtures-result-team">
            ${isoFlagImg('fr')}
            <span class="fixtures-result-name">Example C</span>
          </div>
          <div class="fixtures-result-score">0 - 0</div>
          <div class="fixtures-result-team away">
            <span class="fixtures-result-name">Example D</span>
            ${isoFlagImg('de')}
          </div>
        </div>
      `;
      return;
    }

    host.innerHTML = sorted.map((fixture) => {
      const home = String(fixture.home || '').trim();
      const away = String(fixture.away || '').trim();
      const hs = parseScore(fixture.home_score);
      const as = parseScore(fixture.away_score);
      const homeFlag = isoFlagImg(isoByName?.[normalizeTeamName(home)] || '');
      const awayFlag = isoFlagImg(isoByName?.[normalizeTeamName(away)] || '');
      return `
        <div class="fixtures-result">
          <div class="fixtures-result-team">
            ${homeFlag}
            <span class="fixtures-result-name">${escAttr(home)}</span>
          </div>
          <div class="fixtures-result-score">${hs} - ${as}</div>
          <div class="fixtures-result-team away">
            <span class="fixtures-result-name">${escAttr(away)}</span>
            ${awayFlag}
          </div>
        </div>
      `;
    }).join('');
  }

  function ensureSummaryToggle(){
    const wrap = document.querySelector('.fixtures-summary');
    const btn = document.getElementById('fixtures-summary-toggle');
    if (!wrap || !btn || btn.dataset.wired === '1') return;
    btn.dataset.wired = '1';

    const updateLabel = () => {
      const collapsed = wrap.classList.contains('is-collapsed');
      btn.textContent = collapsed ? 'Expand summaries' : 'Collapse summaries';
      btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    };

    btn.addEventListener('click', () => {
      wrap.classList.toggle('is-collapsed');
      updateLabel();
    });

    updateLabel();
  }

  const fixturesSummaryState = {
    showResults: false,
    data: null
  };

  function ensureResultsToggle(){
    const btn = document.getElementById('fixtures-results-toggle');
    if (!btn || btn.dataset.wired === '1') return;
    btn.dataset.wired = '1';
    btn.addEventListener('click', () => {
      fixturesSummaryState.showResults = !fixturesSummaryState.showResults;
      updateResultsView();
    });
  }

  function updateResultsView(){
    const host = document.getElementById('fixtures-knocked-out');
    const title = document.getElementById('fixtures-knocked-title');
    const btn = document.getElementById('fixtures-results-toggle');
    if (!fixturesSummaryState.data || !host || !title || !btn) return;
    const {
      fixtures,
      knockedTeams,
      records,
      knockedEmptyLabel,
      resultsEmptyLabel,
      isoByName,
      groupByName,
      activeGroup
    } = fixturesSummaryState.data;

    const showResults = fixturesSummaryState.showResults;
    title.textContent = showResults ? 'Results' : 'Knocked out';
    btn.textContent = showResults ? 'Show Knocked Out' : 'Show Results';
    btn.setAttribute('aria-pressed', showResults ? 'true' : 'false');
    if (showResults) {
      renderResultsList(host, fixtures, isoByName, groupByName, activeGroup, resultsEmptyLabel);
    } else {
      renderTeamList(host, knockedTeams, records, knockedEmptyLabel, isoByName);
    }
  }

  function makePlaceholderMatch(stage, home = 'TBD', away = 'TBD', matchId = '', slot = null){
    return {
      id: matchId || 'Match',
      home: home || 'TBD',
      away: away || 'TBD',
      utc: '',
      stadium: '',
      group: '',
      stage,
      bracket_slot: slot,
      _placeholder: true
    };
  }

  function stageMatches(fixtures, stage, expected, slotConfig, forceSlots = false){
    const list = fixtures.filter(f => normalizeStage(f.stage || '') === stage);
    const slots = slotConfig && typeof slotConfig === 'object' ? slotConfig : null;
    const slotKeys = slots ? Object.keys(slots).map((k) => Number(k)).filter(Number.isFinite).sort((a, b) => a - b) : [];

    if (slotKeys.length) {
      const byId = new Map(list.filter(f => f?.id).map(f => [String(f.id), f]));
      const out = [];
      const total = expected || slotKeys.length;
      for (let slot = 1; slot <= total; slot += 1) {
        const cfg = slots[String(slot)] || slots[slot] || {};
        const matchId = String(cfg.match_id || cfg.matchId || '').trim();
        const home = String(cfg.home || cfg.country_a || '').trim();
        const away = String(cfg.away || cfg.country_b || '').trim();
        let match = matchId ? byId.get(matchId) : null;
        if (!match) {
          match = makePlaceholderMatch(stage, home || 'TBD', away || 'TBD', matchId || `Slot ${slot}`, slot);
        }
        if (match && match.bracket_slot == null) match.bracket_slot = slot;
        if (match) {
          match.home = match.home || home || 'TBD';
          match.away = match.away || away || 'TBD';
        }
        out.push(match);
      }
      return out;
    }

    if (forceSlots) {
      const out = [];
      while (expected && out.length < expected) out.push(makePlaceholderMatch(stage));
      return out;
    }

    list.sort((a, b) => {
      const aSlot = Number(a.bracket_slot);
      const bSlot = Number(b.bracket_slot);
      if (Number.isFinite(aSlot) && Number.isFinite(bSlot) && aSlot !== bSlot) return aSlot - bSlot;
      if (Number.isFinite(aSlot) && !Number.isFinite(bSlot)) return -1;
      if (!Number.isFinite(aSlot) && Number.isFinite(bSlot)) return 1;
      return String(a.utc || '').localeCompare(String(b.utc || '')) || String(a.id || '').localeCompare(String(b.id || ''));
    });
    while (expected && list.length < expected) list.push(makePlaceholderMatch(stage));
    return list;
  }

  function matchCard(f, opts = {}){
    const formatter = window.formatFixtureDateTimeCompact || window.formatFixtureDateTime || ((v) => v);
    const utcLabel = f.utc ? formatter(f.utc) : 'TBD';
    const placeholderClass = f._placeholder ? ' is-placeholder' : '';
    const gridRow = opts.gridRow ? ` style="grid-row:${escAttr(opts.gridRow)}"` : '';
    const slotId = f._slot_id ? String(f._slot_id) : '';
    const slotAttr = slotId ? ` id="${escAttr(slotId)}" data-slot-id="${escAttr(slotId)}"` : '';
    return `
      <div class="bracket-match${placeholderClass}"${gridRow}${slotAttr}>
        <div class="bracket-team">${escAttr(f.home || 'TBD')}</div>
        <div class="bracket-team">${escAttr(f.away || 'TBD')}</div>
        <div class="bracket-foot">
          <span class="fixtures-time" data-utc="${escAttr(f.utc || '')}">${escAttr(utcLabel)}</span>
        </div>
      </div>
    `;
  }

  function renderBracketColumn(matches, span) {
    return matches.map((match, idx) => {
      const start = 1 + (idx * span);
      const gridRow = `${start} / span ${span}`;
      return matchCard(match, { gridRow });
    }).join('');
  }

  function buildSlotId(stage, side, slot) {
    const cfg = getStageConfig(stage);
    const slotNum = Number(slot);
    if (!cfg || !Number.isFinite(slotNum)) return '';
    const sideKey = (side || '').toString().charAt(0).toUpperCase();
    const suffix = sideKey ? `-${sideKey}` : '';
    return `${cfg.code}S${slotNum}${suffix}`;
  }

  function attachSlotIds(list, stage, side) {
    return list.map((match, idx) => {
      const slot = Number(match.bracket_slot) || (idx + 1);
      if (!match._slot_id) {
        match._slot_id = buildSlotId(stage, side, slot);
      }
      return match;
    });
  }

  let bracketLinesResizeBound = false;
  let bracketLinesData = null;

  function drawBracketLines(host, bracket) {
    if (!host || !bracket) return;
    const hostRect = host.getBoundingClientRect();
    if (!hostRect.width || !hostRect.height) return;
    const existing = host.querySelector('.bracket-lines');
    if (existing) existing.remove();
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.classList.add('bracket-lines');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('viewBox', `0 0 ${hostRect.width} ${hostRect.height}`);
    svg.setAttribute('width', hostRect.width);
    svg.setAttribute('height', hostRect.height);

    const getMatchEl = match => {
      const slotId = match?._slot_id ? String(match._slot_id) : '';
      if (!slotId) return null;
      return host.querySelector(`[data-slot-id="${slotId}"]`);
    };

    const addConnector = (fromMatch, toMatch) => {
      const fromEl = getMatchEl(fromMatch);
      const toEl = getMatchEl(toMatch);
      if (!fromEl || !toEl) return;
      const fromRect = fromEl.getBoundingClientRect();
      const toRect = toEl.getBoundingClientRect();
      const startX = fromRect.left + (fromRect.width / 2) - hostRect.left;
      const startY = fromRect.top + (fromRect.height / 2) - hostRect.top;
      const endX = toRect.left + (toRect.width / 2) - hostRect.left;
      const endY = toRect.top + (toRect.height / 2) - hostRect.top;
      const midX = (startX + endX) / 2;
      const polyline = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
      polyline.setAttribute('fill', 'none');
      polyline.setAttribute(
        'points',
        `${startX.toFixed(1)},${startY.toFixed(1)} ` +
        `${midX.toFixed(1)},${startY.toFixed(1)} ` +
        `${midX.toFixed(1)},${endY.toFixed(1)} ` +
        `${endX.toFixed(1)},${endY.toFixed(1)}`
      );
      svg.appendChild(polyline);
    };

    const connectPairs = (fromList, toList, groupSize) => {
      if (!fromList?.length || !toList?.length) return;
      fromList.forEach((match, idx) => {
        const target = toList[Math.floor(idx / groupSize)];
        if (target) addConnector(match, target);
      });
    };

    connectPairs(bracket.r32Left, bracket.r16Left, 2);
    connectPairs(bracket.r16Left, bracket.qfLeft, 2);
    connectPairs(bracket.qfLeft, bracket.sfLeft, 2);
    connectPairs(bracket.sfLeft, bracket.finalMatch, 1);
    connectPairs(bracket.r32Right, bracket.r16Right, 2);
    connectPairs(bracket.r16Right, bracket.qfRight, 2);
    connectPairs(bracket.qfRight, bracket.sfRight, 2);
    connectPairs(bracket.sfRight, bracket.finalMatch, 1);

    host.appendChild(svg);
  }

  function renderBracket(host, fixtures, slots){
    if (!host) return;
    const r32Slots = slots?.['Round of 32'];
    const r16Slots = slots?.['Round of 16'];
    const qfSlots = slots?.['Quarter-finals'];
    const sfSlots = slots?.['Semi-finals'];
    const finalSlots = slots?.Final;
    const thirdSlots = slots?.['Third Place Play-off'];
    const r32Left = attachSlotIds(stageMatches(fixtures, 'Round of 32', 8, r32Slots?.left, Boolean(r32Slots)), 'Round of 32', 'left');
    const r16Left = attachSlotIds(stageMatches(fixtures, 'Round of 16', 4, r16Slots?.left, Boolean(r16Slots)), 'Round of 16', 'left');
    const qfLeft = attachSlotIds(stageMatches(fixtures, 'Quarter-finals', 2, qfSlots?.left, Boolean(qfSlots)), 'Quarter-finals', 'left');
    const sfLeft = attachSlotIds(stageMatches(fixtures, 'Semi-finals', 1, sfSlots?.left, Boolean(sfSlots)), 'Semi-finals', 'left');
    const r32Right = attachSlotIds(stageMatches(fixtures, 'Round of 32', 8, r32Slots?.right, Boolean(r32Slots)), 'Round of 32', 'right');
    const r16Right = attachSlotIds(stageMatches(fixtures, 'Round of 16', 4, r16Slots?.right, Boolean(r16Slots)), 'Round of 16', 'right');
    const qfRight = attachSlotIds(stageMatches(fixtures, 'Quarter-finals', 2, qfSlots?.right, Boolean(qfSlots)), 'Quarter-finals', 'right');
    const sfRight = attachSlotIds(stageMatches(fixtures, 'Semi-finals', 1, sfSlots?.right, Boolean(sfSlots)), 'Semi-finals', 'right');
    const finalMatch = attachSlotIds(stageMatches(fixtures, 'Final', 1, finalSlots?.center, Boolean(finalSlots)), 'Final', 'center');
    const thirdPlace = attachSlotIds(stageMatches(fixtures, 'Third Place Play-off', 1, thirdSlots?.center, Boolean(thirdSlots)), 'Third Place Play-off', 'center');

    host.innerHTML = `
      <div class="bracket-column bracket-left">
        <div class="bracket-title">Round of 32</div>
        <div class="bracket-list">
          ${renderBracketColumn(r32Left, 1)}
        </div>
      </div>
      <div class="bracket-column bracket-left">
        <div class="bracket-title">Round of 16</div>
        <div class="bracket-list">
          ${renderBracketColumn(r16Left, 2)}
        </div>
      </div>
      <div class="bracket-column bracket-left">
        <div class="bracket-title">Quarter-finals</div>
        <div class="bracket-list">
          ${renderBracketColumn(qfLeft, 4)}
        </div>
      </div>
      <div class="bracket-column bracket-left">
        <div class="bracket-title">Semi-finals</div>
        <div class="bracket-list">
          ${renderBracketColumn(sfLeft, 8)}
        </div>
      </div>
      <div class="bracket-column bracket-center">
        <div class="bracket-title">Final</div>
        <div class="bracket-list">
          ${finalMatch.map(match => matchCard(match, { gridRow: '4 / span 2' })).join('')}
          <div class="bracket-subtitle" style="grid-row:6 / span 1">Third Place</div>
          ${thirdPlace.map(match => matchCard(match, { gridRow: '7 / span 2' })).join('')}
        </div>
      </div>
      <div class="bracket-column bracket-right">
        <div class="bracket-title">Semi-finals</div>
        <div class="bracket-list">
          ${renderBracketColumn(sfRight, 8)}
        </div>
      </div>
      <div class="bracket-column bracket-right">
        <div class="bracket-title">Quarter-finals</div>
        <div class="bracket-list">
          ${renderBracketColumn(qfRight, 4)}
        </div>
      </div>
      <div class="bracket-column bracket-right">
        <div class="bracket-title">Round of 16</div>
        <div class="bracket-list">
          ${renderBracketColumn(r16Right, 2)}
        </div>
      </div>
      <div class="bracket-column bracket-right">
        <div class="bracket-title">Round of 32</div>
        <div class="bracket-list">
          ${renderBracketColumn(r32Right, 1)}
        </div>
      </div>
    `;
    const bracketData = {
      r32Left,
      r16Left,
      qfLeft,
      sfLeft,
      r32Right,
      r16Right,
      qfRight,
      sfRight,
      finalMatch
    };
    bracketLinesData = bracketData;
    requestAnimationFrame(() => drawBracketLines(host, bracketData));
    if (!bracketLinesResizeBound) {
      bracketLinesResizeBound = true;
      window.addEventListener('resize', () => {
        const bracketHost = document.querySelector('#fixtures-bracket');
        if (bracketHost && bracketLinesData) drawBracketLines(bracketHost, bracketLinesData);
      });
    }
  }

  function updateFixturesTimes(){
    const formatter = window.formatFixtureDateTimeCompact || window.formatFixtureDateTime || ((v) => v);
    document.querySelectorAll('.fixtures-time').forEach(el => {
      const utc = el.dataset.utc || '';
      if (!utc) return;
      el.textContent = formatter(utc);
    });
  }

  async function loadFixtures(){
    const nextHost = $('#fixtures-next-stage');
    const knockedHost = $('#fixtures-knocked-out');
    const bracketHost = $('#fixtures-bracket');
    const groupSel = document.getElementById('fixtures-group');
    if (!bracketHost) return;

    if (nextHost) nextHost.innerHTML = `<div class="muted">Loading teams…</div>`;
    if (knockedHost) knockedHost.innerHTML = `<div class="muted">Loading teams…</div>`;
    bracketHost.innerHTML = `<div class="muted" style="padding:12px">Loading bracket…</div>`;

    let fixtures = [];
    let stages = {};
    let winners = {};
    let bracketSlots = {};
    let isoByName = {};
    let groupByName = new Map();
    let activeGroup = String(groupSel?.value || 'ALL').toUpperCase();
    try {
      const [fx, st, wn, bs, iso, meta] = await Promise.all([
        fetchJSON('/api/fixtures'),
        fetchJSON('/api/team_stage'),
        fetchJSON('/api/fanzone/winners'),
        fetchJSON('/api/bracket_slots'),
        fetchJSON('/api/team_iso'),
        fetchJSON('/api/team_meta')
      ]);
      fixtures = (fx && fx.fixtures) || [];
      stages = (st && typeof st === 'object') ? st : {};
      winners = (wn && wn.winners && typeof wn.winners === 'object') ? wn.winners : {};
      bracketSlots = (bs && bs.slots && typeof bs.slots === 'object') ? bs.slots : {};
      groupByName = buildGroupMap(meta);
      if (iso && typeof iso === 'object') {
        Object.entries(iso).forEach(([team, code]) => {
          const norm = normalizeTeamName(team);
          const value = String(code || '').trim().toLowerCase();
          if (norm && value) isoByName[norm] = value;
        });
      }
    } catch (err) {
      if (nextHost) nextHost.innerHTML = `<div class="muted">No team data available.</div>`;
      if (knockedHost) knockedHost.innerHTML = `<div class="muted">No team data available.</div>`;
      if (bracketHost) bracketHost.innerHTML = `<div class="muted" style="padding:12px">No fixtures available.</div>`;
      return;
    }

    const records = computeRecords(fixtures, winners);
    const entries = Object.entries(stages).map(([name, stage]) => ({
      name,
      stage: normalizeStage(stage) || stage || 'Group Stage'
    }));

    entries.sort((a, b) => {
      const diff = stageRank(a.stage) - stageRank(b.stage);
      if (diff !== 0) return diff;
      return a.name.localeCompare(b.name);
    });

    const withGroup = entries.map((entry) => ({
      ...entry,
      group: groupByName.get(normalizeTeamName(entry.name)) || ''
    }));
    const byGroup = (list) => {
      if (!activeGroup || activeGroup === 'ALL') return list;
      return list.filter((entry) => String(entry.group || '').toUpperCase() === activeGroup);
    };
    const nextStageTeams = byGroup(withGroup.filter(e => e.stage !== 'Eliminated'));
    const knockedTeams = byGroup(withGroup.filter(e => e.stage === 'Eliminated'));
    const nextEmptyLabel = activeGroup === 'ALL'
      ? 'No teams have advanced yet.'
      : `No teams in Group ${activeGroup}.`;
    const knockedEmptyLabel = activeGroup === 'ALL'
      ? 'No teams knocked out yet.'
      : `No knocked out teams in Group ${activeGroup}.`;
    const resultsEmptyLabel = activeGroup === 'ALL'
      ? 'No results available yet.'
      : `No results in Group ${activeGroup}.`;

    renderTeamList(nextHost, nextStageTeams, records, nextEmptyLabel, isoByName);
    fixturesSummaryState.data = {
      fixtures,
      knockedTeams,
      records,
      knockedEmptyLabel,
      resultsEmptyLabel,
      isoByName,
      groupByName,
      activeGroup
    };
    updateResultsView();
    ensureSummaryToggle();
    ensureResultsToggle();
    renderBracket(bracketHost, fixtures, bracketSlots);
    updateFixturesTimes();
  }

  document.addEventListener('click', (e) => {
    const link = e.target.closest('a[data-page=\"fixtures\"]');
    if (!link) return;
    setTimeout(() => loadFixtures(), 50);
  });

  document.addEventListener('click', (e) => {
    if (e.target.id === 'fixtures-refresh') {
      loadFixtures();
    }
  });

  document.getElementById('fixtures-group')?.addEventListener('change', () => {
    loadFixtures();
  });

  document.addEventListener('click', async (e) => {
    if (e.target.id !== 'fixtures-edit-slot') return;
    if (typeof window.isAdminUI === 'function' && !window.isAdminUI()) {
      notify('Admin required', false);
      return;
    }
    openSlotModal();
  });

  function openSlotModal() {
    const backdrop = document.getElementById('fixtures-slot-backdrop');
    const modal = document.getElementById('fixtures-slot-modal');
    if (!backdrop || !modal) return;
    backdrop.style.display = 'flex';
    modal.focus();
    updateSlotFormConstraints();
  }

  function closeSlotModal() {
    const backdrop = document.getElementById('fixtures-slot-backdrop');
    if (backdrop) backdrop.style.display = 'none';
  }

  function getStageConfig(stage) {
    const map = {
      'Round of 32': { max: 8, side: true, code: 'R32' },
      'Round of 16': { max: 4, side: true, code: 'R16' },
      'Quarter-finals': { max: 2, side: true, code: 'QF' },
      'Semi-finals': { max: 1, side: true, code: 'SF' },
      'Final': { max: 1, side: false, code: 'F' },
      'Third Place Play-off': { max: 1, side: false, code: '3P' },
    };
    return map[stage] || { max: 1, side: false, code: 'M' };
  }

  function updateSlotFormConstraints() {
    const stage = document.getElementById('fixtures-slot-stage')?.value || '';
    const sideEl = document.getElementById('fixtures-slot-side');
    const slotEl = document.getElementById('fixtures-slot-number');
    const cfg = getStageConfig(stage);
    if (slotEl) {
      slotEl.max = String(cfg.max);
      slotEl.min = '1';
    }
    if (sideEl) {
      const leftOpt = sideEl.querySelector('option[value="left"]');
      const rightOpt = sideEl.querySelector('option[value="right"]');
      const centerOpt = sideEl.querySelector('option[value="center"]');
      if (leftOpt) leftOpt.hidden = !cfg.side;
      if (rightOpt) rightOpt.hidden = !cfg.side;
      if (centerOpt) centerOpt.hidden = cfg.side;
      sideEl.disabled = !cfg.side;
      if (!cfg.side) sideEl.value = 'center';
    }
  }

  function readSlotForm() {
    const stage = document.getElementById('fixtures-slot-stage')?.value || '';
    const side = document.getElementById('fixtures-slot-side')?.value || 'center';
    const slot = document.getElementById('fixtures-slot-number')?.value || '';
    const countryA = document.getElementById('fixtures-slot-country-a')?.value || '';
    const countryB = document.getElementById('fixtures-slot-country-b')?.value || '';
    const date = document.getElementById('fixtures-slot-date')?.value || '';
    const time = document.getElementById('fixtures-slot-time')?.value || '';
    return { stage, side, slot, countryA, countryB, date, time };
  }

  function clearSlotForm() {
    const setVal = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.value = val;
    };
    setVal('fixtures-slot-number', '');
    setVal('fixtures-slot-country-a', '');
    setVal('fixtures-slot-country-b', '');
    setVal('fixtures-slot-date', '');
    setVal('fixtures-slot-time', '');
  }

  function makeInitials(name) {
    return String(name || '')
      .toUpperCase()
      .replace(/[^A-Z0-9\s]/g, '')
      .split(/\s+/)
      .filter(Boolean)
      .map(part => part.slice(0, 3))
      .join('');
  }

  function buildMatchId(stage, side, slot, countryA, countryB) {
    const cfg = getStageConfig(stage);
    const leftRight = cfg.side ? (side === 'right' ? 'R' : 'L') : 'C';
    const a = makeInitials(countryA) || 'TBD';
    const b = makeInitials(countryB) || 'TBD';
    return `BRKT-${cfg.code}-${leftRight}${slot}-${a}-${b}`;
  }

  function buildUtcValue(dateRaw, timeRaw) {
    const date = String(dateRaw || '').trim();
    const time = String(timeRaw || '').trim();
    if (!date && !time) return '';
    if (!date || !time) return null;
    const dateMatch = date.match(/^(\d{1,2})\/(\d{1,2})$/);
    const timeMatch = time.match(/^(\d{1,2})[:\/](\d{1,2})$/);
    if (!dateMatch || !timeMatch) return null;
    const day = Number(dateMatch[1]);
    const month = Number(dateMatch[2]);
    const hour = Number(timeMatch[1]);
    const minute = Number(timeMatch[2]);
    if (
      !Number.isFinite(day) || !Number.isFinite(month) ||
      !Number.isFinite(hour) || !Number.isFinite(minute) ||
      day < 1 || day > 31 ||
      month < 1 || month > 12 ||
      hour < 0 || hour > 23 ||
      minute < 0 || minute > 59
    ) {
      return null;
    }
    const year = new Date().getUTCFullYear();
    const pad = (num) => String(num).padStart(2, '0');
    return `${year}-${pad(month)}-${pad(day)}T${pad(hour)}:${pad(minute)}:00Z`;
  }

  document.getElementById('fixtures-slot-cancel')?.addEventListener('click', () => {
    closeSlotModal();
  });

  document.getElementById('fixtures-slot-close')?.addEventListener('click', () => {
    closeSlotModal();
  });

  document.getElementById('fixtures-slot-backdrop')?.addEventListener('click', (e) => {
    if (e.target?.id === 'fixtures-slot-backdrop') closeSlotModal();
  });

  document.getElementById('fixtures-slot-save')?.addEventListener('click', async () => {
    const { stage, side, slot, countryA, countryB, date, time } = readSlotForm();
    if (!stage || !slot) {
      notify('Stage and slot are required.', false);
      return;
    }
    const stageNorm = String(normalizeStage(stage) || '').trim();
    if (!stageNorm) {
      notify('Invalid stage selection.', false);
      return;
    }
    const cfg = getStageConfig(stageNorm);
    const slotNum = Number(slot);
    if (!Number.isFinite(slotNum) || slotNum < 1 || slotNum > cfg.max) {
      notify(`Slot must be between 1 and ${cfg.max}.`, false);
      return;
    }
    const home = String(countryA || '').trim();
    const away = String(countryB || '').trim();
    const utcValue = buildUtcValue(date, time);
    if (utcValue === null) {
      notify('Match date/time must be DD/MM and HH:MM (24h).', false);
      return;
    }
    const hasTeams = Boolean(home || away);
    const matchId = hasTeams ? buildMatchId(stageNorm, side, slotNum, home, away) : '';
    const payload = {
      stage: stageNorm,
      side: cfg.side ? side : 'center',
      slot: slotNum,
      match_id: matchId,
      home,
      away,
      utc: utcValue || '',
    };
    try {
      await fetchJSON('/admin/bracket_slots', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      notify('Bracket slot updated', true);
      closeSlotModal();
      clearSlotForm();
      loadFixtures();
    } catch (err) {
      notify(`Failed to update slot: ${err.message || err}`, false);
    }
  });

  document.getElementById('fixtures-slot-stage')?.addEventListener('change', updateSlotFormConstraints);
  document.addEventListener('DOMContentLoaded', updateSlotFormConstraints);

  window.addEventListener('timezonechange', updateFixturesTimes);
  window.addEventListener('dateformatchange', updateFixturesTimes);

  window.addEventListener('DOMContentLoaded', () => {
    if (document.querySelector('#fixtures.page-section.active-section')) {
      loadFixtures();
    }
  });
})();


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
    const safeIso = String(iso).trim().toLowerCase();
    // Render a compact country flag icon for Fan Zone cards.
    return `<img class="fan-flag" alt="${safeIso}" src="https://flagcdn.com/w20/${safeIso}.png" loading="lazy">`;
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
    const dp = pct(stats?.draw_pct || 0);
    const total = stats?.total || 0;
    const last = stats?.last_choice;
    const winner = String(stats?.winner || stats?.winner_side || '').toLowerCase();
    const isLocked = winner === 'home' || winner === 'away' || winner === 'draw';

    const votedHome = last === 'home';
    const votedAway = last === 'away';
    const votedDraw = last === 'draw';
    const votedClass = votedHome ? 'voted-home' : votedAway ? 'voted-away' : votedDraw ? 'voted-draw' : '';
    const lockedClass = isLocked ? 'locked' : '';
    const winnerClass = isLocked ? `winner-${winner}` : '';

    const adminControls = (isAdminUI()) ? `
      <span class="fan-win-wrap" data-admin="true">
        <button class="btn xs fan-win" type="button" data-side="home" data-team="${f.home}" data-iso="${f.home_iso || ''}">
          Declare ${f.home}
        </button>
        <button class="btn xs fan-win" type="button" data-side="draw">
          Declare Draw
        </button>
        <button class="btn xs fan-win" type="button" data-side="away" data-team="${f.away}" data-iso="${f.away_iso || ''}">
          Declare ${f.away}
        </button>
      </span>
    ` : '';

    return `
      <div class="fan-card ${votedClass} ${lockedClass} ${winnerClass}" data-fid="${f.id}" data-utc="${escAttr(f.utc || '')}" data-group="${escAttr(f._group || '')}" data-teams="${escAttr(`${f.home} ${f.away}`)}" data-home="${escAttr(f.home)}" data-away="${escAttr(f.away)}" data-winner="${isLocked ? winner : ''}">
        <div class="fan-head">
          <div class="fan-team">
            ${flagImg(f.home_iso)} <span class="fan-team-name">${f.home}</span>
          </div>
          <div class="fan-vs">vs</div>
          <div class="fan-team">
            ${flagImg(f.away_iso)} <span class="fan-team-name">${f.away}</span>
          </div>
        </div>

        <div class="fan-time">${escAttr((window.formatFixtureDateTimeCompact || formatFixtureDateTime)(f.utc || ''))}</div>

        <div class="fan-bars">
          <div class="fan-bar-row">
            <div class="fan-bar fan-bar-home" style="width:${hp}%">
              <span>${hp}%</span>
            </div>
          </div>
          <div class="fan-bar-row">
            <div class="fan-bar fan-bar-draw" style="width:${dp}%">
              <span>${dp}%</span>
            </div>
          </div>
          <div class="fan-bar-row">
            <div class="fan-bar fan-bar-away" style="width:${ap}%">
              <span>${ap}%</span>
            </div>
          </div>
        </div>

        <div class="fan-actions">
          <button class="btn fan-vote home ${votedHome ? 'active' : ''}" data-choice="home" ${isLocked || last ? 'disabled' : ''}>
            Vote ${f.home}
          </button>
          <button class="btn fan-vote draw ${votedDraw ? 'active' : ''}" data-choice="draw" ${isLocked || last ? 'disabled' : ''}>
            Vote Draw
          </button>
          <button class="btn fan-vote away ${votedAway ? 'active' : ''}" data-choice="away" ${isLocked || last ? 'disabled' : ''}>
            Vote ${f.away}
          </button>
        </div>

        <div class="fan-foot">
          <span class="muted">Total votes: <strong class="fan-total">${total}</strong></span>
          ${last ? `<span class="pill pill-ok">You voted: ${last === 'home' ? f.home : last === 'away' ? f.away : 'Draw'}</span>` : ''}
          ${adminControls}
        </div>
      </div>
    `;
  }

    function applyStatsToCard(card, stats) {
  if (!card || !stats) return;

  
  const btnHome = card.querySelector('.fan-vote[data-choice="home"]');
  const btnAway = card.querySelector('.fan-vote[data-choice="away"]');
  const btnDraw = card.querySelector('.fan-vote[data-choice="draw"]');

  
  const barHome = card.querySelector('.fan-bar-home');
  const barAway = card.querySelector('.fan-bar-away');
  const barDraw = card.querySelector('.fan-bar-draw');
  const barHomePct = barHome ? barHome.querySelector('span') : null;
  const barAwayPct = barAway ? barAway.querySelector('span') : null;
  const barDrawPct = barDraw ? barDraw.querySelector('span') : null;

  
  const totalEl = card.querySelector('.fan-total');

  const hp = Math.max(0, Math.min(100, Number(stats.home_pct || 0)));
  const ap = Math.max(0, Math.min(100, Number(stats.away_pct || 0)));
  const dp = Math.max(0, Math.min(100, Number(stats.draw_pct || 0)));

  if (barHome) barHome.style.width = `${hp}%`;
  if (barAway) barAway.style.width = `${ap}%`;
  if (barDraw) barDraw.style.width = `${dp}%`;
  if (barHomePct) barHomePct.textContent = `${hp.toFixed(0)}%`;
  if (barAwayPct) barAwayPct.textContent = `${ap.toFixed(0)}%`;
  if (barDrawPct) barDrawPct.textContent = `${dp.toFixed(0)}%`;

  if (totalEl) totalEl.textContent = String(Number(stats.total || 0));

  
  const last = String(stats.last_choice || stats.last || '').toLowerCase();
  const homeLabel = card.dataset.home || 'Home';
  const awayLabel = card.dataset.away || 'Away';
  if (btnHome) btnHome.classList.toggle('active', last === 'home');
  if (btnAway) btnAway.classList.toggle('active', last === 'away');
  if (btnDraw) btnDraw.classList.toggle('active', last === 'draw');
  card.classList.toggle('voted-home', last === 'home');
  card.classList.toggle('voted-away', last === 'away');
  card.classList.toggle('voted-draw', last === 'draw');

    const winner = String(stats.winner || stats.winner_side || '').toLowerCase();
    const isLocked = (winner === 'home' || winner === 'away' || winner === 'draw');

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
  if (btnDraw) btnDraw.disabled = isLocked || !!last;

  
  card.classList.toggle('locked', isLocked);
  card.dataset.winner = isLocked ? winner : '';

  const declareBtns = card.querySelectorAll('.fan-win');
  declareBtns.forEach(b => { b.disabled = isLocked; });

  
  card.classList.toggle('winner-home', isLocked && winner === 'home');
  card.classList.toggle('winner-away', isLocked && winner === 'away');
  card.classList.toggle('winner-draw', isLocked && winner === 'draw');

  
  const pill = card.querySelector('.pill.pill-ok');
  if (pill) {
    const votedLabel = last === 'home' ? homeLabel : last === 'away' ? awayLabel : last === 'draw' ? 'Draw' : '';
    pill.textContent = votedLabel ? `You voted: ${votedLabel}` : '';
  }
}

    async function refreshVisibleCards() {
    const cards = Array.from(document.querySelectorAll('#fanzone-list .fan-card'));
    if (!cards.length) return;

    for (const card of cards) {
      const fid = card.dataset.fid;
      try {
        const stats = await getStats(fid);
        if (stats?.ok) applyStatsToCard(card, stats);
      } catch {  }
    }
    }

    async function declareFanZoneWinner(matchId, side) {
      const res = await fetch('/admin/fanzone/declare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          match_id: String(matchId),
          winner: String(side) 
        })
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) {
        throw new Error(data?.error || `declare_failed_${res.status}`);
      }

      
      try {
        if (typeof window.refreshNotificationsNow === 'function') {
          await window.refreshNotificationsNow(true); 
        }
      } catch (e) {
        console.warn('refreshNotificationsNow failed', e);
      }

      return data;
    }

  function updateFanZoneTimes() {
    const cards = Array.from(document.querySelectorAll('#fanzone-list .fan-card'));
    if (!cards.length) return;
    const formatter = window.formatFixtureDateTimeCompact || formatFixtureDateTime;
    cards.forEach((card) => {
      const utc = card.dataset.utc || '';
      if (!utc) return;
      const timeEl = card.querySelector('.fan-time');
      if (timeEl) timeEl.textContent = formatter(utc);
    });
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
      <div class="fan-card" data-fid="${f.id}" data-utc="${escAttr(f.utc || '')}" data-group="${escAttr(f._group || '')}" data-teams="${escAttr(`${f.home} ${f.away}`)}" data-home="${escAttr(f.home)}" data-away="${escAttr(f.away)}">
        <div class="muted" style="padding:12px">Loading…</div>
      </div>
    `).join('');

    for (const f of fixtures) {
      const stats = await getStats(f.id).catch(() => null);
      const card = host.querySelector(`.fan-card[data-fid="${CSS.escape(f.id)}"]`);
      if (card) card.outerHTML = cardHTML(f, stats);
    }

    applyFanZoneFilters();

    if (host.dataset.fanWired === '1') return;
    host.dataset.fanWired = '1';
    host.addEventListener('click', async (ev) => {

      
      const winBtn = ev.target.closest('.fan-win');
      if (winBtn) {
        if (!isAdminUI()) {
          notify('Admin required', false);
          return;
        }

        const card = winBtn.closest('.fan-card');
        if (!card) return;

          if (card.dataset.winner === 'home' || card.dataset.winner === 'away' || card.dataset.winner === 'draw') {
            notify('This match has already been declared and is locked.', false);
            return;
  }

        const fid = card.dataset.fid;
        if (!fid) return;

        const side = String(winBtn.dataset.side || '').toLowerCase();
        if (side !== 'home' && side !== 'away' && side !== 'draw') return;

        const winnerTeam = String(winBtn.dataset.team || '').trim();

        try {
          const r = await declareFanZoneWinner(fid, side);
          if (r && r.ok) {
            const declaredLabel = winnerTeam || (side === 'draw' ? 'Draw' : side);
            notify(`Winner declared: ${declaredLabel}`, true);
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

    
    const voteBtn = ev.target.closest('.fan-vote');
    if (!voteBtn) return;

    const card = voteBtn.closest('.fan-card');
    const fid = card?.dataset?.fid;
    const choice = voteBtn?.dataset?.choice;
    if (!fid || !choice) return;

    
    if (card?.dataset?.winner) {
      notify('Voting is locked for this match', false);
      return;
    }

    
    card.querySelectorAll('.fan-vote').forEach(b => b.disabled = true);

    try {
      await sendVote(fid, choice);
    } catch (err) {
      if (String(err?.message).includes('voting_closed')) {
        
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

  
  window.loadFanZone = async function loadFanZone() {
    await renderFanZone();
  };

  window.updateFanZoneTimes = updateFanZoneTimes;
  window.addEventListener('timezonechange', updateFanZoneTimes);
  window.addEventListener('dateformatchange', updateFanZoneTimes);

  
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

      
      const key = sel || inp;
      if (key && key.dataset.wired === '1') return;
      if (key) key.dataset.wired = '1';

      sel && sel.addEventListener('change', applyFanZoneFilters);
      inp && inp.addEventListener('input', applyFanZoneFilters);
    }

  
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

  function initFooterRotator(){
    const el = document.getElementById('footer-rotator');
    if (!el) return;

    const messages = [
      { type: 'text', value: 'World Cup 2026 • Live updates roll in every few minutes.' },
      { type: 'text', value: 'Need help? DM a Referee for gameplay questions.' },
      { type: 'text', value: 'Use the dashboard to track ownership and bets.' },
      { type: 'text', value: 'Admin updates sync across tabs automatically.' },
      { type: 'link', value: 'Terms', href: '/terms', className: 'btn btn-outline sm footer-terms' }
    ];
    let idx = 0;

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const renderMessage = (message) => {
      el.textContent = '';
      if (message.type === 'link') {
        const link = document.createElement('a');
        link.href = message.href;
        link.textContent = message.value;
        link.className = message.className || '';
        el.appendChild(link);
        return;
      }
      const span = document.createElement('span');
      span.textContent = message.value;
      el.appendChild(span);
    };

    const setMessage = (nextIdx) => {
      idx = nextIdx % messages.length;
      if (reduceMotion) {
        renderMessage(messages[idx]);
        return;
      }
      el.classList.add('is-fading');
      setTimeout(() => {
        renderMessage(messages[idx]);
        el.classList.remove('is-fading');
      }, 200);
    };

    setMessage(idx);
    if (reduceMotion) return;
    setInterval(() => setMessage(idx + 1), 5000);
  }

  
  window.addEventListener('DOMContentLoaded', () => {
    if (document.querySelector('#fanzone.page-section.active-section')) {
      ensureFanFilterWiring();
      window.loadFanZone();
      ensureFanRefresh();
    }
  });

  window.addEventListener('DOMContentLoaded', initFooterRotator);
})();
