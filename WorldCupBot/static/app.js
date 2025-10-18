/* World Cup 2026 Panel - app.js (full)
   Vanilla JS - no frameworks - admin gating via modal FAB
   Uses Flask public routes /api/* and admin routes /admin/*
   Includes: retry + timeout, polling, optional websocket hooks, CSV export,
   sortable tables, responsive nav, theme persistence, last-page persistence.
*/

(() => {
  'use strict';

  // =========================
  // DOM helpers
  // =========================
  const qs = (s, el=document) => el.querySelector(s);
  const qsa = (s, el=document) => [...el.querySelectorAll(s)];
  const on = (el, ev, fn, opts) => el.addEventListener(ev, fn, opts);
  const off = (el, ev, fn, opts) => el.removeEventListener(ev, fn, opts);

  // =========================
  // Global state
  // =========================
  const state = {
    admin: false,
    theme: localStorage.getItem('wc:theme') || 'dark',
    currentPage: localStorage.getItem('wc:lastPage') || 'dashboard',

    pollingId: null,
    ws: null,
    wsUrl: null,
    wsBackoffMs: 500,
    wsMaxBackoffMs: 8000,

    // cached data
    guilds: null,
    bets: null,
    ownerships: null,
    logsKind: 'bot',
  };

  // Cache key helpers
  const cacheKey = {
    theme: 'wc:theme',
    lastPage: 'wc:lastPage',
    betsRows: 'wc:betsRows',
    betsQ: 'wc:betsQ',
    ownQ: 'wc:ownQ',
  };

  // =========================
  // Fixed nodes
  // =========================
  const $menu = qs('#main-menu');
  const $notify = qs('#notify');
  const $fab = qs('#fab-auth');
  const $fabIcon = qs('#fab-icon');
  const $backdrop = qs('#auth-backdrop');
  const $btnCancel = qs('#auth-cancel');
  const $btnSubmit = qs('#auth-submit');
  const $themeToggle = qs('#theme-toggle');
  const $themeIcon = qs('#theme-icon');

  // =========================
  // Utilities
  // =========================
  function sleep(ms){ return new Promise(r=>setTimeout(r, ms)); }

  function esc(v){
    return String(v==null? '': v).replace(/[&<>"']/g, s => (
      {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]
    ));
  }

  function humanBytes(n){
    n = Number(n||0);
    const u = ['B','KB','MB','GB','TB'];
    let i=0;
    while(n>=1024 && i<u.length-1){ n/=1024; i++; }
    const digits = n<10 && i>0 ? 1 : 0;
    return `${n.toFixed(digits)} ${u[i]}`;
  }

  function fmtHMS(sec){
    if(typeof sec!=='number' || !isFinite(sec)) return '--:--:--';
    const s = Math.floor(sec%60);
    const m = Math.floor((sec/60)%60);
    const h = Math.floor(sec/3600);
    const pad = n => String(n).padStart(2,'0');
    return `${pad(h)}:${pad(m)}:${pad(s)}`;
  }

  function notify(msg, ok=true){
    const div = document.createElement('div');
    div.className = `notice ${ok?'ok':'err'}`;
    div.textContent = msg;
    $notify.appendChild(div);
    setTimeout(() => div.remove(), 2600);
  }

  // Rounded semicircle path dasharray
  function semicircleDash(percent){
    const clamped = Math.max(0, Math.min(100, percent||0));
    const total = 125.66;
    return `${(clamped/100)*total},${total}`;
  }

  // =========================
  // Theme
  // =========================
  function setTheme(theme){
    state.theme = theme;
    document.body.classList.toggle('light', theme==='light');
    localStorage.setItem(cacheKey.theme, theme);
    $themeIcon.textContent = theme==='light' ? '🌞' : '🌙';
  }

  function wireTheme(){
    on($themeToggle, 'click', () => {
      setTheme(state.theme==='light' ? 'dark' : 'light');
    });
  }

  // =========================
  // Modal auth
  // =========================
  function openModal(){
    $backdrop.style.display = 'flex';
    if(!state.admin){
      const input = qs('#admin-password');
      if(input) setTimeout(()=>input.focus(), 50);
    }
  }
  function closeModal(){ $backdrop.style.display = 'none'; }

  function setAdminMode(on){
    state.admin = on;
    document.body.classList.toggle('admin', on);
    $fabIcon.textContent = on ? '⚙️' : '🔑';
    $fab.title = on ? 'Settings' : 'Login';

    // Reset modal to correct content
    const title = qs('#modal-title');
    const body = qs('#modal-body');
    if(on){
      title.textContent = 'Admin';
      body.innerHTML = '<p>You are logged in.</p>';
      $btnSubmit.textContent = 'Logout';
      $btnSubmit.dataset.action = 'logout';
    }else{
      title.textContent = 'Admin login';
      body.innerHTML = '<label for="admin-password">Password</label><input type="password" id="admin-password" placeholder="Enter admin password">';
      $btnSubmit.textContent = 'Unlock';
      $btnSubmit.dataset.action = 'login';
    }
  }

  function wireAuth(){
    on($fab, 'click', openModal);
    on($btnCancel, 'click', closeModal);

    on(document, 'keydown', (e) => {
      if(e.key === 'Escape' && $backdrop.style.display === 'flex') closeModal();
    });
    on($backdrop, 'click', (e) => {
      // click outside modal closes
      const inModal = e.target.closest('.modal');
      if(!inModal) closeModal();
    });

    on($btnSubmit, 'click', async () => {
      const action = $btnSubmit.dataset.action;
      try{
        if(action === 'logout'){
          await fetchJSON('/admin/auth/logout', {method:'POST', body:JSON.stringify({})});
          setAdminMode(false);
          notify('Logged out');
          closeModal();
          // bounce away from admin-only page if visible
          const cur = state.currentPage;
          if(qs(`#${cur}`) && qs(`#${cur}`).classList.contains('admin-only')){
            setPage('dashboard');
            routePage();
          }else{
            // just rerender current
            routePage();
          }
          return;
        }
        // login
        const input = qs('#admin-password');
        const password = input ? input.value : '';
        const r = await fetchJSON('/admin/auth/login', {method:'POST', body:JSON.stringify({password})});
        if(r && (r.ok || r.unlocked)){
          setAdminMode(true);
          notify('Admin unlocked');
          closeModal();
          routePage();
        }else{
          notify('Login failed', false);
        }
      }catch(err){
        notify(`Login error: ${err.message}`, false);
      }
    });
  }

  // =========================
  // API client with timeout + retry
  // =========================
  async function fetchJSON(url, opts={}, {timeoutMs=12000, retries=1, retryDelayMs=400}={}){
    const ctrl = new AbortController();
    const to = setTimeout(() => ctrl.abort(), timeoutMs);
    try{
      const res = await fetch(url, {
        ...opts,
        headers: {'Content-Type':'application/json', ...(opts.headers||{})},
        signal: ctrl.signal,
        credentials: 'include',
      });
      if(!res.ok){
        // try read JSON error
        let errMsg = `${res.status}`;
        try{
          const ej = await res.json();
          errMsg = ej.error || ej.message || JSON.stringify(ej);
        }catch{}
        throw new Error(errMsg);
      }
      // handle json or empty
      const ct = res.headers.get('content-type')||'';
      if(ct.includes('application/json')) return await res.json();
      return {};
    }catch(err){
      if(retries>0){
        await sleep(retryDelayMs);
        return fetchJSON(url, opts, {timeoutMs, retries:retries-1, retryDelayMs:retryDelayMs*1.5});
      }
      throw err;
    }finally{
      clearTimeout(to);
    }
  }

  // =========================
  // Page routing
  // =========================
  function setPage(page){
    state.currentPage = page;
    localStorage.setItem(cacheKey.lastPage, page);

    // menu active state
    qsa('#main-menu a').forEach(a => a.classList.toggle('active', a.dataset.page===page));

    // hide all sections, show one
    qsa('section.page-section').forEach(sec => {
      sec.classList.toggle('active-section', sec.id===page);
    });
  }

  function wireNav(){
    on($menu, 'click', (ev) => {
      const a = ev.target.closest('a[data-page]');
      if(!a) return;
      ev.preventDefault();
      const page = a.dataset.page;
      // guard admin-only
      const sec = qs(`#${page}`);
      if(sec && sec.classList.contains('admin-only') && !state.admin){
        notify('Admin required', false);
        return;
      }
      setPage(page);
      routePage();
    });
  }

  async function routePage(){
    switch(state.currentPage){
      case 'dashboard': await loadDashboard(); break;
      case 'bets': await loadBets(); break;
      case 'ownership': await loadOwnership(); break;
      case 'splits': if(state.admin) await loadSplits(); else setPage('dashboard'); break;
      case 'backups': if(state.admin) await loadBackups(); else setPage('dashboard'); break;
      case 'log': if(state.admin) await loadLogs(state.logsKind||'bot'); else setPage('dashboard'); break;
      case 'cogs': if(state.admin) await loadCogs(); else setPage('dashboard'); break;
    }
  }

  // =========================
  // Section scaffolding
  // =========================
  function ensureSectionCard(id, title, controls){
    const sec = qs(`#${id}`);
    sec.innerHTML = '';
    const wrap = document.createElement('div');
    wrap.className = 'table-wrap';

    const head = document.createElement('div');
    head.className = 'table-head';
    head.innerHTML = `<div class="table-title">${title}</div><div class="table-actions"></div>`;
    const actions = head.querySelector('.table-actions');

    (controls||[]).forEach(([label, meta]) => {
      if(meta && meta.kind==='select'){
        const sel = document.createElement('select');
        sel.id = meta.id;
        (meta.items||[]).forEach(v => {
          const o = document.createElement('option');
          o.value = v; o.textContent = v;
          sel.appendChild(o);
        });
        actions.appendChild(sel);
      }else if(meta && meta.kind==='input'){
        const inp = document.createElement('input');
        inp.type='text'; inp.id = meta.id; inp.placeholder = meta.placeholder||'';
        actions.appendChild(inp);
      }else{
        const btn = document.createElement('button');
        btn.className='btn';
        if(meta?.id) btn.id = meta.id;
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

  // =========================
  // DASHBOARD
  // =========================
  async function loadDashboard(){
    try{
      const [sys, up, ping, guilds] = await Promise.all([
        fetchJSON('/api/system'),
        fetchJSON('/api/uptime'),
        fetchJSON('/api/ping'),
        fetchJSON('/api/guilds'),
      ]);
      renderDashboardSystem(sys);
      renderDashboardUptime(up);
      renderDashboardPing(ping);
      renderGuilds(guilds);

      // bot start-stop visibility
      const running = !!(up && up.bot_running);
      const $start = qs('#start-bot');
      const $stop = qs('#stop-bot');
      if($start && $stop){
        $start.style.display = running ? 'none' : 'inline-block';
        $stop.style.display = running ? 'inline-block' : 'none';
      }
    }catch(e){
      notify(`Dashboard error: ${e.message}`, false);
    }
  }

  function renderDashboardSystem(sys){
    const bot = sys?.bot || {};
    const s = sys?.system || {};

    const parts = [];
    if(typeof bot.cpu_percent === 'number') parts.push(`CPU ${bot.cpu_percent.toFixed(1)}%`);
    if(typeof bot.mem_mb === 'number') parts.push(`RAM ${bot.mem_mb.toFixed(0)} MB`);
    qs('#botstats-value').textContent = parts.length ? parts.join(' • ') : '---';

    const memPct = Number(s.mem_percent||0);
    qs('#mem-bar')?.setAttribute('stroke-dasharray', semicircleDash(memPct));
    if(qs('#mem-text')) qs('#mem-text').textContent = `${memPct.toFixed(0)}%`;
    if(qs('#mem-extra')) qs('#mem-extra').textContent = `Used ${Number(s.mem_used_mb||0).toFixed(0)} MB of ${Number(s.mem_total_mb||0).toFixed(0)} MB`;

    const cpuPct = Number(s.cpu_percent||0);
    qs('#cpu-bar')?.setAttribute('stroke-dasharray', semicircleDash(cpuPct));
    if(qs('#cpu-text')) qs('#cpu-text').textContent = `${cpuPct.toFixed(0)}%`;
    if(qs('#cpu-extra')) qs('#cpu-extra').textContent = `CPU ${cpuPct.toFixed(1)}%`;

    const diskPct = Number(s.disk_percent||0);
    qs('#disk-bar')?.setAttribute('stroke-dasharray', semicircleDash(diskPct));
    if(qs('#disk-text')) qs('#disk-text').textContent = `${diskPct.toFixed(0)}%`;
    if(qs('#disk-extra')) qs('#disk-extra').textContent = `Used ${Number(s.disk_used_mb||0).toFixed(0)} MB of ${Number(s.disk_total_mb||0).toFixed(0)} MB`;
  }

  function renderDashboardUptime(up){
    const running = !!(up && up.bot_running);
    qs('#uptime-label').textContent = running ? 'Uptime' : 'Downtime';
    qs('#uptime-value').textContent = running ? (up.uptime_hms || '--:--:--') : (up.downtime_hms || '--:--:--');
  }

  function renderDashboardPing(ping){
    const online = ping && ping.status==='ok';
    const txt = [];
    if(online){
      txt.push(ping.bot_running ? 'online' : 'offline');
      if(ping.pid) txt.push(`pid ${ping.pid}`);
      qs('#ping-value').textContent = txt.join(' ');
    }else{
      qs('#ping-value').textContent = '-- ms';
    }
  }

  function renderGuilds(g){
    const data = g || {guild_count:0, guilds:[]};
    const list = Array.isArray(data.guilds) ? data.guilds : [];
    qs('#guild-count').textContent = data.guild_count || list.length || 0;
    const gl = qs('#guild-list');
    if(!gl) return;
    gl.innerHTML = '';
    list.forEach(it => {
      const name = it.name || String(it);
      const id = it.id ? ` (${it.id})` : '';
      const div = document.createElement('div');
      div.textContent = `${name}${id}`;
      gl.appendChild(div);
    });
  }

  function wireDashButtons(){
    const postAdmin = (path) => fetchJSON(`/admin/bot/${path}`, {method:'POST', body:JSON.stringify({})});
    const $restart = qs('#restart-bot');
    const $stop = qs('#stop-bot');
    const $start = qs('#start-bot');

    if($restart){
      on($restart, 'click', async () => {
        try{ await postAdmin('restart'); notify('Restart requested'); await loadDashboard(); }catch(e){ notify(`Restart failed: ${e.message}`, false); }
      });
    }
    if($stop){
      on($stop, 'click', async () => {
        try{ await postAdmin('stop'); notify('Stop requested'); await loadDashboard(); }catch(e){ notify(`Stop failed: ${e.message}`, false); }
      });
    }
    if($start){
      on($start, 'click', async () => {
        try{ await postAdmin('start'); notify('Start requested'); await loadDashboard(); }catch(e){ notify(`Start failed: ${e.message}`, false); }
      });
    }
  }

  // =========================
  // BETS
  // =========================
  async function loadBets(){
    try{
      const data = await fetchJSON('/api/bets');
      const items = Array.isArray(data) ? data : (data.bets||[]);
      state.bets = items;
      renderBetsTable(items);
    }catch(e){
      notify(`Bets error: ${e.message}`, false);
    }
  }

  function renderBetsTable(items){
    const wrap = ensureSectionCard('bets', 'Bets', [
      ['Refresh', {id:'bets-refresh-btn'}],
      ['Rows', {kind:'select', id:'bets-rows', items:[10,25,50,100]}],
      ['Search', {kind:'input', id:'bets-search', placeholder:'Search'}],
    ]);

    const scroll = wrap.querySelector('.table-scroll');
    scroll.innerHTML = '';
    const table = document.createElement('table');
    table.className = 'table betting-table';
    table.innerHTML = `<thead><tr>
      <th data-k="bet_id">ID</th>
      <th data-k="bet_title">Title</th>
      <th data-k="wager">Wager</th>
      <th data-k="option1">Option 1</th>
      <th data-k="option2">Option 2</th>
      <th data-k="settled">Status</th>
    </tr></thead><tbody></tbody>`;
    scroll.appendChild(table);

    let sortKey = 'bet_id', sortDir = 1;
    table.querySelectorAll('th').forEach(th => {
      on(th, 'click', () => {
        const k = th.dataset.k;
        if(sortKey === k) sortDir = -sortDir; else { sortKey = k; sortDir = 1; }
        draw();
      });
    });

    const rowsSel = qs('#bets-rows');
    const searchInp = qs('#bets-search');
    rowsSel.value = localStorage.getItem(cacheKey.betsRows) || '25';
    searchInp.value = localStorage.getItem(cacheKey.betsQ) || '';

    function draw(){
      const q = (searchInp.value||'').toLowerCase();
      const perPage = Number(rowsSel.value||25);
      localStorage.setItem(cacheKey.betsRows, String(perPage));
      localStorage.setItem(cacheKey.betsQ, q);

      const filtered = items.filter(b => JSON.stringify(b).toLowerCase().includes(q));
      const sorted = filtered.sort((a,b) => {
        const av = a?.[sortKey]; const bv = b?.[sortKey];
        if(av==null && bv==null) return 0;
        if(av==null) return 1;
        if(bv==null) return -1;
        if(av<bv) return -1*sortDir;
        if(av>bv) return 1*sortDir;
        return 0;
      });

      // simple pagination just truncates to first N (explicit pager can be added later)
      const pageItems = sorted.slice(0, perPage);

      const tbody = table.querySelector('tbody');
      tbody.innerHTML = '';
      pageItems.forEach(b => {
        const tr = document.createElement('tr');
        const status = b.settled ? 'Settled' : 'Open';
        tr.innerHTML = `<td>${esc(b.bet_id)}</td>
                        <td>${esc(b.bet_title)}</td>
                        <td>${esc(b.wager)}</td>
                        <td>${esc(b.option1)}${!b.option1_user_id ? '<div class="unclaimed">Unclaimed</div>':''}</td>
                        <td>${esc(b.option2)}${!b.option2_user_id ? '<div class="unclaimed">Unclaimed</div>':''}</td>
                        <td>${status}</td>`;
        tbody.appendChild(tr);
      });
    }

    draw();
    on(qs('#bets-refresh-btn'), 'click', loadBets);
    on(rowsSel, 'change', draw);
    on(searchInp, 'input', draw);
  }

  // =========================
  // OWNERSHIP
  // =========================
  async function loadOwnership(){
    try{
      const d = await fetchJSON('/api/ownerships');
      state.ownerships = d;
      renderOwnership(d);
    }catch(e){
      notify(`Ownership error: ${e.message}`, false);
    }
  }

  function renderOwnership(data){
    const wrap = ensureSectionCard('ownership', 'Ownership', [
      ['Export CSV', {id:'own-export'}],
      ['Filter', {kind:'input', id:'own-filter', placeholder:'Search name, id, country'}],
    ]);

    const scroll = wrap.querySelector('.table-scroll');
    scroll.innerHTML = '';
    const table = document.createElement('table');
    table.className = 'table';
    table.innerHTML = `<thead><tr><th>Country</th><th>Owners</th></tr></thead><tbody></tbody>`;
    scroll.appendChild(table);

    const filter = qs('#own-filter');
    filter.value = localStorage.getItem(cacheKey.ownQ) || '';

    function draw(){
      const q = (filter.value||'').toLowerCase();
      localStorage.setItem(cacheKey.ownQ, q);
      const tbody = table.querySelector('tbody');
      tbody.innerHTML = '';
      const rows = data?.ownerships || [];
      rows.forEach(row => {
        const country = row.country || '';
        const owners = (row.owners||[]).map(o => String(o)).join(', ');
        const hay = `${country} ${owners}`.toLowerCase();
        if(q && !hay.includes(q)) return;
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${esc(country)}</td><td>${esc(owners)}</td>`;
        tbody.appendChild(tr);
      });
    }

    draw();

    on(qs('#own-export'), 'click', () => {
      const rows = [['Country','Owners']];
      (data?.ownerships||[]).forEach(r => rows.push([r.country, (r.owners||[]).join('; ')]));
      const csv = rows.map(r => r.map(v => `"${String(v).replace(/"/g,'""')}"`).join(',')).join('\n');
      const blob = new Blob([csv], {type:'text/csv'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'ownership.csv'; a.click();
      URL.revokeObjectURL(url);
    });

    on(filter, 'input', draw);
  }

  // =========================
  // SPLITS
  // =========================
  async function loadSplits(){
    try{
      let data;
      try{
        data = await fetchJSON('/admin/splits');
      }catch{
        data = await fetchJSON('/api/split_requests');
      }
      renderSplits(data);
    }catch(e){
      notify(`Splits error: ${e.message}`, false);
    }
  }

  function renderSplits(data){
    const wrap = ensureSectionCard('splits', 'Split Requests', [['Refresh', {id:'splits-refresh'}]]);
    const scroll = wrap.querySelector('.table-scroll');
    scroll.innerHTML = '';
    const pre = document.createElement('pre');
    pre.textContent = JSON.stringify(data, null, 2);
    scroll.appendChild(pre);
    on(qs('#splits-refresh'), 'click', loadSplits);
  }

  // =========================
  // BACKUPS
  // =========================
  async function loadBackups(){
    try{
      const d = await fetchJSON('/api/backups');
      renderBackups(d);
    }catch(e){
      notify(`Backups error: ${e.message}`, false);
    }
  }

  function renderBackups(listing){
    const wrap = ensureSectionCard('backups', 'Backups', [
      ['Backup All', {id:'bk-create'}],
      ['Restore Latest', {id:'bk-restore'}],
      ['Prune', {id:'bk-prune'}],
    ]);
    const scroll = wrap.querySelector('.table-scroll');
    scroll.innerHTML = '';

    const files = (listing?.backups)|| (listing?.folders?.[0]?.files) || [];
    if(!files.length){
      const p = document.createElement('p');
      p.textContent = 'No backups yet.';
      scroll.appendChild(p);
    }else{
      const table = document.createElement('table');
      table.className = 'table';
      table.innerHTML = `<thead><tr><th>Name</th><th>Size</th><th>Modified</th><th></th></tr></thead><tbody></tbody>`;
      const tbody = table.querySelector('tbody');
      files.forEach(f => {
        const tr = document.createElement('tr');
        const size = humanBytes(f.bytes || f.size);
        const ts = f.mtime || f.ts;
        const dt = ts ? new Date(ts*1000).toLocaleString() : '';
        const a = document.createElement('a');
        a.href = `/api/backups/download?rel=${encodeURIComponent(f.rel||f.name)}`;
        a.textContent = 'Download';
        a.className = 'file-download';
        tr.innerHTML = `<td>${esc(f.name)}</td><td>${esc(size)}</td><td>${esc(dt)}</td><td></td>`;
        tr.children[3].appendChild(a);
        tbody.appendChild(tr);
      });
      scroll.appendChild(table);
    }

    const btnCreate = qs('#bk-create');
    const btnRestore = qs('#bk-restore');
    const btnPrune = qs('#bk-prune');

    if(btnCreate){
      on(btnCreate, 'click', async () => {
        try{
          await fetchJSON('/api/backups/create', {method:'POST', body:JSON.stringify({})});
          notify('Backup created');
          await loadBackups();
        }catch(e){ notify(`Backup failed: ${e.message}`, false); }
      });
    }
    if(btnRestore){
      on(btnRestore, 'click', async () => {
        try{
          const latest = files[0];
          if(!latest) return notify('No backups to restore', false);
          await fetchJSON('/api/backups/restore', {method:'POST', body:JSON.stringify({name: latest.name})});
          notify('Restored latest backup');
        }catch(e){ notify(`Restore failed: ${e.message}`, false); }
      });
    }
    if(btnPrune){
      on(btnPrune, 'click', async () => {
        try{
          const r = await fetchJSON('/admin/backups/prune', {method:'POST', body:JSON.stringify({keep:10})});
          if(r && r.ok) notify(`Pruned ${r.pruned} backups`); else notify('Prune failed', false);
          await loadBackups();
        }catch(e){ notify(`Prune error: ${e.message}`, false); }
      });
    }
  }

  // =========================
  // LOGS
  // =========================
  async function loadLogs(kind='bot'){
    try{
      state.logsKind = kind;
      const d = await fetchJSON(`/api/log/${kind}`);
      renderLogs(kind, d?.lines || []);
    }catch(e){
      notify(`Logs error: ${e.message}`, false);
    }
  }

  function renderLogs(kind, lines){
    const wrap = ensureSectionCard('log', 'Logs', [
      ['Bot', {id:'log-kind-bot'}],
      ['Health', {id:'log-kind-health'}],
      ['Refresh', {id:'log-refresh'}],
      ['Clear', {id:'log-clear'}],
      ['Download', {id:'log-download'}],
      ['Filter', {kind:'input', id:'log-q', placeholder:'Search'}],
    ]);
    wrap.dataset.kind = kind;

    const scroll = wrap.querySelector('.table-scroll');
    scroll.innerHTML = '';

    const box = document.createElement('div');
    box.className = 'log-window';

    const q = (qs('#log-q')?.value||'').toLowerCase();
    lines.forEach(line => {
      if(q && !line.toLowerCase().includes(q)) return;
      const div = document.createElement('div');
      div.textContent = line;
      box.appendChild(div);
    });
    scroll.appendChild(box);

    on(qs('#log-kind-bot'), 'click', () => loadLogs('bot'));
    on(qs('#log-kind-health'), 'click', () => loadLogs('health'));
    on(qs('#log-refresh'), 'click', () => loadLogs(kind));
    on(qs('#log-clear'), 'click', async () => {
      try{
        await fetchJSON(`/api/log/${kind}/clear`, {method:'POST', body:JSON.stringify({})});
        await loadLogs(kind);
      }catch(e){ notify(`Clear failed: ${e.message}`, false); }
    });
    on(qs('#log-download'), 'click', () => {
      window.location.href = `/api/log/${kind}/download`;
    });
    on(qs('#log-q'), 'input', () => renderLogs(kind, lines));
  }

  // =========================
  // COGS
  // =========================
  async function loadCogs(){
    try{
      let d;
      try{
        d = await fetchJSON('/admin/cogs');
      }catch{
        d = await fetchJSON('/api/cogs');
      }
      renderCogs(d);
    }catch(e){
      notify(`Cogs error: ${e.message}`, false);
    }
  }

  function renderCogs(data){
    const wrap = ensureSectionCard('cogs', 'Cogs', [['Refresh', {id:'cogs-refresh'}]]);
    const scroll = wrap.querySelector('.table-scroll');
    scroll.innerHTML = '';
    const table = document.createElement('table');
    table.className = 'table cogs-table';
    table.innerHTML = `<thead><tr><th>Name</th><th>Actions</th></tr></thead><tbody></tbody>`;
    const tbody = table.querySelector('tbody');

    const cogs = data?.cogs || [];
    cogs.forEach(c => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${esc(c.name)}</td><td></td>`;
      const cell = tr.children[1];
      ['reload','load','unload'].forEach(act => {
        const b = document.createElement('button');
        b.className = 'btn';
        b.textContent = act;
        on(b, 'click', async () => {
          try{
            await fetchJSON(`/admin/cogs/${encodeURIComponent(c.name)}/${act}`, {method:'POST', body:JSON.stringify({})});
            notify(`${act} queued for ${c.name}`);
          }catch(e){ notify(`Cog ${act} failed: ${e.message}`, false); }
        });
        cell.appendChild(b);
      });
      tbody.appendChild(tr);
    });

    scroll.appendChild(table);
    on(qs('#cogs-refresh'), 'click', loadCogs);
  }

  // =========================
  // Polling + optional WS
  // =========================
  function startPolling(){
    stopPolling();
    state.pollingId = setInterval(async () => {
      const p = state.currentPage;
      if(p==='dashboard') await loadDashboard();
      else if(p==='bets') await loadBets();
    }, 5000);
  }
  function stopPolling(){
    if(state.pollingId) clearInterval(state.pollingId);
    state.pollingId = null;
  }

  // optional websocket scaffolding - not enabled by default
  function connectWS(url){
    if(!url) return;
    try{
      if(state.ws) state.ws.close();
    }catch{}
    const ws = new WebSocket(url);
    state.ws = ws;

    ws.onopen = () => {
      state.wsBackoffMs = 500;
    };
    ws.onmessage = (ev) => {
      try{
        const msg = JSON.parse(ev.data);
        if(msg.type==='bets:update') loadBets();
        if(msg.type==='logs:append' && state.currentPage==='log') loadLogs(state.logsKind||'bot');
      }catch{}
    };
    ws.onclose = async () => {
      // backoff reconnect
      await sleep(state.wsBackoffMs);
      state.wsBackoffMs = Math.min(state.wsBackoffMs*2, state.wsMaxBackoffMs);
      connectWS(url);
    };
    ws.onerror = () => { try{ ws.close(); }catch{} };
  }

  // =========================
  // Init
  // =========================
  async function init(){
    // Theme
    setTheme(state.theme);

    // Admin status
    try{
      const s = await fetchJSON('/admin/auth/status');
      setAdminMode(!!(s && s.unlocked));
    }catch{
      setAdminMode(false);
    }

    // Wire
    wireTheme();
    wireAuth();
    wireNav();
    wireDashButtons();

    // Restore page and route
    setPage(state.currentPage);
    await routePage();

    // Polling
    startPolling();

    // Optional WS - enable if your backend exposes it
    // state.wsUrl = (location.protocol==='https:'?'wss://':'ws://') + location.host + '/ws';
    // connectWS(state.wsUrl);
  }

  on(window, 'load', init);
})();
