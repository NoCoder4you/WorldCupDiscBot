/* World Cup 2026 Panel - app.js
   Dice-5 dashboard layout, equal cards, dynamic bot controls, ping latency,
   Bot Process online/offline, Ownership without CSV.
   Vanilla JS, fetch with timeout + retry, admin gating via modal FAB.
*/
(() => {
  'use strict';

  // Helpers
  const qs = (s, el=document) => el.querySelector(s);
  const qsa = (s, el=document) => [...el.querySelectorAll(s)];
  const on = (el, ev, fn, opts) => el.addEventListener(ev, fn, opts);

  // State
  const state = {
    admin: false,
    theme: localStorage.getItem('wc:theme') || 'dark',
    currentPage: localStorage.getItem('wc:lastPage') || 'dashboard',
    pollingId: null,
    logsKind: 'bot',
  };

  const cacheKey = {
    theme:'wc:theme',
    lastPage:'wc:lastPage',
    betsRows:'wc:betsRows',
    betsQ:'wc:betsQ',
    ownQ:'wc:ownQ'
  };

  // Fixed nodes
  const $menu = qs('#main-menu');
  const $notify = qs('#notify');
  const $fab = qs('#fab-auth');
  const $fabIcon = qs('#fab-icon');
  const $backdrop = qs('#auth-backdrop');
  const $btnCancel = qs('#auth-cancel');
  const $btnSubmit = qs('#auth-submit');
  const $themeToggle = qs('#theme-toggle');
  const $themeIcon = qs('#theme-icon');

  // Utils
  function sleep(ms){ return new Promise(r=>setTimeout(r, ms)); }
  function notify(msg, ok=true){
    const div = document.createElement('div');
    div.className = `notice ${ok?'ok':'err'}`;
    div.textContent = msg;
    $notify.appendChild(div);
    setTimeout(()=>div.remove(), 2400);
  }
  function semicircleDash(p){ const total=125.66; p=Math.max(0,Math.min(100,Number(p)||0)); return `${(p/100)*total},${total}`; }
  function esc(v){
    return String(v==null? '': v).replace(/[&<>"']/g, s => (
      {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]
    ));
  }
  function setTheme(t){
    document.body.classList.toggle('light', t==='light');
    localStorage.setItem(cacheKey.theme, t);
    $themeIcon.textContent = t==='light' ? '🌞' : '🌙';
    state.theme = t;
  }

  async function fetchJSON(url, opts={}, {timeoutMs=10000, retries=1, delay=350}={}){
    const ctrl = new AbortController();
    const to = setTimeout(()=>ctrl.abort(), timeoutMs);
    try{
      const res = await fetch(url, {
        ...opts,
        headers: {'Content-Type':'application/json', ...(opts.headers||{})},
        signal: ctrl.signal,
        credentials: 'include',
      });
      if(!res.ok){
        let msg = `${res.status}`;
        try { const j = await res.json(); msg = j.error || j.message || JSON.stringify(j); } catch {}
        throw new Error(msg);
      }
      const ct = res.headers.get('content-type') || '';
      return ct.includes('application/json') ? await res.json() : {};
    }catch(e){
      if(retries>0){
        await sleep(delay);
        return fetchJSON(url, opts, {timeoutMs, retries:retries-1, delay:delay*1.5});
      }
      throw e;
    }finally{
      clearTimeout(to);
    }
  }

  // Theme and auth
  function wireTheme(){ on($themeToggle, 'click', () => setTheme(state.theme==='light' ? 'dark' : 'light')); }
  function setAdminMode(onMode){
    state.admin = onMode;
    document.body.classList.toggle('admin', onMode);
    $fabIcon.textContent = onMode ? '⚙️' : '🔑';
    $fab.title = onMode ? 'Settings' : 'Login';

    const title = qs('#modal-title');
    const body = qs('#modal-body');
    if(onMode){
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
  function openModal(){ $backdrop.style.display='flex'; if(!state.admin){ const i=qs('#admin-password'); if(i) setTimeout(()=>i.focus(),50); } }
  function closeModal(){ $backdrop.style.display='none'; }
  function wireAuth(){
    on($fab, 'click', openModal);
    on($btnCancel, 'click', closeModal);
    on($backdrop, 'click', e=>{ if(!e.target.closest('.modal')) closeModal(); });
    on(document, 'keydown', e=>{ if(e.key==='Escape' && $backdrop.style.display==='flex') closeModal(); });
    on($btnSubmit, 'click', async ()=>{
      try{
        if($btnSubmit.dataset.action==='logout'){
          await fetchJSON('/admin/auth/logout', {method:'POST', body:JSON.stringify({})});
          setAdminMode(false); notify('Logged out'); closeModal();
          if(qs(`#${state.currentPage}`).classList.contains('admin-only')){ setPage('dashboard'); routePage(); }
          return;
        }
        const pw = qs('#admin-password')?.value || '';
        const r = await fetchJSON('/admin/auth/login', {method:'POST', body:JSON.stringify({password:pw})});
        if(r && (r.ok || r.unlocked)){ setAdminMode(true); notify('Admin unlocked'); closeModal(); routePage(); }
        else notify('Login failed', false);
      }catch(e){ notify(`Login error: ${e.message}`, false); }
    });
  }

  // Routing
  function setPage(p){
    state.currentPage = p;
    localStorage.setItem(cacheKey.lastPage, p);
    qsa('#main-menu a').forEach(a => a.classList.toggle('active', a.dataset.page===p));
    qsa('section.page-section').forEach(s => s.classList.toggle('active-section', s.id===p));
  }
  function wireNav(){
    on($menu, 'click', ev => {
      const a = ev.target.closest('a[data-page]'); if(!a) return;
      ev.preventDefault();
      const page = a.dataset.page;
      const sec = qs('#'+page);
      if(sec.classList.contains('admin-only') && !state.admin){ notify('Admin required', false); return; }
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

  // Dashboard
  async function loadDashboard(){
    try{
      // Get system + uptime first
      const [sys, up] = await Promise.all([
        fetchJSON('/api/system'),
        fetchJSON('/api/uptime'),
      ]);

      // Measure latency just for /api/ping
      const t0 = performance.now();
      const ping = await fetchJSON('/api/ping');
      const latency = Math.max(0, Math.round(performance.now() - t0));

      renderDashboardSystem(sys);
      renderDashboardUptime(up);
      renderDashboardPing(ping, latency);
      renderBotProcess(up, ping);

      // Bot controls - show Start only when offline, Restart+Stop when online
      const running = !!(up && up.bot_running);
      const $start = qs('#start-bot');
      const $stop = qs('#stop-bot');
      const $restart = qs('#restart-bot');
      if($start && $stop && $restart){
        if(running){
          $start.style.display = 'none';
          $stop.style.display = 'inline-block';
          $restart.style.display = 'inline-block';
        }else{
          $start.style.display = 'inline-block';
          $stop.style.display = 'none';
          $restart.style.display = 'none';
        }
      }
    }catch(e){
      notify(`Dashboard error: ${e.message}`, false);
    }
  }

  function renderDashboardSystem(sys){
    const s = sys?.system || {};
    const memPct = Number(s.mem_percent||0);
    const cpuPct = Number(s.cpu_percent||0);
    const diskPct = Number(s.disk_percent||0);

    qs('#mem-bar')?.setAttribute('stroke-dasharray', semicircleDash(memPct));
    qs('#mem-text') && (qs('#mem-text').textContent = `${memPct.toFixed(0)}%`);
    qs('#mem-extra') && (qs('#mem-extra').textContent = `Used ${Number(s.mem_used_mb||0).toFixed(0)} MB of ${Number(s.mem_total_mb||0).toFixed(0)} MB`);

    qs('#cpu-bar')?.setAttribute('stroke-dasharray', semicircleDash(cpuPct));
    qs('#cpu-text') && (qs('#cpu-text').textContent = `${cpuPct.toFixed(0)}%`);
    qs('#cpu-extra') && (qs('#cpu-extra').textContent = `CPU ${cpuPct.toFixed(1)}%`);

    qs('#disk-bar')?.setAttribute('stroke-dasharray', semicircleDash(diskPct));
    qs('#disk-text') && (qs('#disk-text').textContent = `${diskPct.toFixed(0)}%`);
    qs('#disk-extra') && (qs('#disk-extra').textContent = `Used ${Number(s.disk_used_mb||0).toFixed(0)} MB of ${Number(s.disk_total_mb||0).toFixed(0)} MB`);
  }

  function renderDashboardUptime(up){
    const running = !!(up && up.bot_running);
    qs('#uptime-label').textContent = running ? 'Uptime' : 'Downtime';
    qs('#uptime-value').textContent = running ? (up.uptime_hms || '--:--:--') : (up.downtime_hms || '--:--:--');
  }

  function renderDashboardPing(ping, latencyMs){
    if(ping && ping.status==='ok'){
      qs('#ping-value').textContent = `${latencyMs} ms`;
    }else{
      qs('#ping-value').textContent = '-- ms';
    }
  }

  function renderBotProcess(up, ping){
    const running = !!(up && up.bot_running);
    const pid = ping?.pid ? ` pid ${ping.pid}` : '';
    qs('#botproc-value').textContent = running ? `Online${pid}` : 'Offline';
  }

  function wireDashButtons(){
    const postAdmin = (path) => fetchJSON(`/admin/bot/${path}`, {method:'POST', body:JSON.stringify({})});
    on(qs('#restart-bot'), 'click', async ()=>{ try{ await postAdmin('restart'); notify('Restart requested'); await loadDashboard(); }catch(e){ notify(`Restart failed: ${e.message}`, false); } });
    on(qs('#stop-bot'), 'click', async ()=>{ try{ await postAdmin('stop'); notify('Stop requested'); await loadDashboard(); }catch(e){ notify(`Stop failed: ${e.message}`, false); } });
    on(qs('#start-bot'), 'click', async ()=>{ try{ await postAdmin('start'); notify('Start requested'); await loadDashboard(); }catch(e){ notify(`Start failed: ${e.message}`, false); } });
  }

  // Bets
  async function loadBets(){
    try{
      const data = await fetchJSON('/api/bets');
      const items = Array.isArray(data) ? data : (data.bets||[]);
      renderBetsTable(items);
    }catch(e){ notify(`Bets error: ${e.message}`, false); }
  }
  function renderBetsTable(items){
    const wrap = ensureSectionCard('bets','Bets',[
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

    let sortKey='bet_id', sortDir=1;
    table.querySelectorAll('th').forEach(th=>{
      on(th,'click',()=>{
        const k=th.dataset.k;
        if(sortKey===k) sortDir=-sortDir; else { sortKey=k; sortDir=1; }
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
      const sorted = filtered.sort((a,b)=>{
        const av=a?.[sortKey], bv=b?.[sortKey];
        if(av==null && bv==null) return 0;
        if(av==null) return 1;
        if(bv==null) return -1;
        if(av<bv) return -1*sortDir;
        if(av>bv) return 1*sortDir;
        return 0;
      });

      const pageItems = sorted.slice(0, perPage);
      const tbody = table.querySelector('tbody');
      tbody.innerHTML = '';
      pageItems.forEach(b=>{
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
    on(qs('#bets-refresh-btn'),'click',loadBets);
    on(rowsSel,'change',draw);
    on(searchInp,'input',draw);
  }

  // Ownership (no Export CSV)
  async function loadOwnership(){
    try{
      const d = await fetchJSON('/api/ownerships');
      renderOwnership(d);
    }catch(e){ notify(`Ownership error: ${e.message}`, false); }
  }
  function renderOwnership(data){
    const wrap = ensureSectionCard('ownership','Ownership',[
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
      (data?.ownerships||[]).forEach(row=>{
        const country = row.country || '';
        const owners = (row.owners||[]).map(o=>String(o)).join(', ');
        const hay = `${country} ${owners}`.toLowerCase();
        if(q && !hay.includes(q)) return;
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${esc(country)}</td><td>${esc(owners)}</td>`;
        tbody.appendChild(tr);
      });
    }

    draw();
    on(filter,'input',draw);
  }

  // Splits
  async function loadSplits(){
    try{
      let data;
      try{ data = await fetchJSON('/admin/splits'); }
      catch{ data = await fetchJSON('/api/split_requests'); }

      const wrap = ensureSectionCard('splits','Split Requests',[['Refresh',{id:'splits-refresh'}]]);
      const scroll = wrap.querySelector('.table-scroll');
      scroll.innerHTML = '';
      const pre = document.createElement('pre');
      pre.textContent = JSON.stringify(data, null, 2);
      scroll.appendChild(pre);
      on(qs('#splits-refresh'),'click',loadSplits);
    }catch(e){ notify(`Splits error: ${e.message}`, false); }
  }

  // Backups
  async function loadBackups(){
    try{
      const d = await fetchJSON('/api/backups');
      const wrap = ensureSectionCard('backups','Backups',[
        ['Backup All',{id:'bk-create'}],
        ['Restore Latest',{id:'bk-restore'}],
        ['Prune',{id:'bk-prune'}],
      ]);
      const scroll = wrap.querySelector('.table-scroll');
      scroll.innerHTML = '';

      const files = (d?.backups) || (d?.folders?.[0]?.files) || [];
      if(!files.length){
        const p = document.createElement('p');
        p.textContent = 'No backups yet.';
        scroll.appendChild(p);
      }else{
        const table = document.createElement('table');
        table.className = 'table';
        table.innerHTML = `<thead><tr><th>Name</th><th>Size</th><th>Modified</th><th></th></tr></thead><tbody></tbody>`;
        const tbody = table.querySelector('tbody');
        files.forEach(f=>{
          const size = (n=>{n=Number(n||0);const u=['B','KB','MB','GB','TB'];let i=0;while(n>=1024 && i<u.length-1){n/=1024;i++;}return `${n.toFixed(n<10&&i>0?1:0)} ${u[i]}`})(f.bytes||f.size);
          const ts = f.mtime || f.ts;
          const dt = ts ? new Date(ts*1000).toLocaleString() : '';
          const tr = document.createElement('tr');
          tr.innerHTML = `<td>${esc(f.name)}</td><td>${esc(size)}</td><td>${esc(dt)}</td><td></td>`;
          const a = document.createElement('a'); a.href=`/api/backups/download?rel=${encodeURIComponent(f.rel||f.name)}`; a.textContent='Download';
          tr.children[3].appendChild(a);
          tbody.appendChild(tr);
        });
        scroll.appendChild(table);
      }

      on(qs('#bk-create'),'click', async()=>{ try{ await fetchJSON('/api/backups/create',{method:'POST',body:JSON.stringify({})}); notify('Backup created'); await loadBackups(); }catch(e){ notify(`Backup failed: ${e.message}`, false); } });
      on(qs('#bk-restore'),'click', async()=>{ try{ const latest=(files||[])[0]; if(!latest) return notify('No backups to restore',false); await fetchJSON('/api/backups/restore',{method:'POST',body:JSON.stringify({name:latest.name})}); notify('Restored latest backup'); }catch(e){ notify(`Restore failed: ${e.message}`, false); } });
      on(qs('#bk-prune'),'click', async()=>{ try{ const r=await fetchJSON('/admin/backups/prune',{method:'POST',body:JSON.stringify({keep:10})}); if(r && r.ok) notify(`Pruned ${r.pruned} backups`); else notify('Prune failed', false); await loadBackups(); }catch(e){ notify(`Prune error: ${e.message}`, false); } });

    }catch(e){ notify(`Backups error: ${e.message}`, false); }
  }

  // Logs
  async function loadLogs(kind='bot'){
    try{
      state.logsKind = kind;
      const d = await fetchJSON(`/api/log/${kind}`);
      const wrap = ensureSectionCard('log','Logs',[
        ['Bot',{id:'log-kind-bot'}],
        ['Health',{id:'log-kind-health'}],
        ['Refresh',{id:'log-refresh'}],
        ['Clear',{id:'log-clear'}],
        ['Download',{id:'log-download'}],
        ['Filter',{kind:'input', id:'log-q', placeholder:'Search'}],
      ]);
      const scroll = wrap.querySelector('.table-scroll');
      scroll.innerHTML = '';

      const box = document.createElement('div');
      box.className = 'log-window';
      const q = (qs('#log-q')?.value||'').toLowerCase();
      (d?.lines||[]).forEach(line=>{
        if(q && !line.toLowerCase().includes(q)) return;
        const div = document.createElement('div');
        div.textContent = line;
        box.appendChild(div);
      });
      scroll.appendChild(box);

      on(qs('#log-kind-bot'),'click',()=>loadLogs('bot'));
      on(qs('#log-kind-health'),'click',()=>loadLogs('health'));
      on(qs('#log-refresh'),'click',()=>loadLogs(kind));
      on(qs('#log-clear'),'click',async()=>{ try{ await fetchJSON(`/api/log/${kind}/clear`,{method:'POST',body:JSON.stringify({})}); await loadLogs(kind); }catch(e){ notify(`Clear failed: ${e.message}`, false); } });
      on(qs('#log-download'),'click',()=>{ window.location.href=`/api/log/${kind}/download`; });
      on(qs('#log-q'),'input',()=>loadLogs(kind));
    }catch(e){ notify(`Logs error: ${e.message}`, false); }
  }

  // Cogs
  async function loadCogs(){
    try{
      let d; try{ d = await fetchJSON('/admin/cogs'); } catch { d = await fetchJSON('/api/cogs'); }
      const wrap = ensureSectionCard('cogs','Cogs',[['Refresh',{id:'cogs-refresh'}]]);
      const scroll = wrap.querySelector('.table-scroll');
      scroll.innerHTML = '';

      const table = document.createElement('table');
      table.className = 'table cogs-table';
      table.innerHTML = `<thead><tr><th>Name</th><th>Actions</th></tr></thead><tbody></tbody>`;
      const tbody = table.querySelector('tbody');

      (d?.cogs||[]).forEach(c=>{
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${esc(c.name)}</td><td></td>`;
        const cell = tr.children[1];
        ['reload','load','unload'].forEach(act=>{
          const b = document.createElement('button');
          b.className = 'btn';
          b.textContent = act;
          on(b,'click', async()=>{
            try{ await fetchJSON(`/admin/cogs/${encodeURIComponent(c.name)}/${act}`,{method:'POST',body:JSON.stringify({})}); notify(`${act} queued for ${c.name}`); }
            catch(e){ notify(`Cog ${act} failed: ${e.message}`, false); }
          });
          cell.appendChild(b);
        });
        tbody.appendChild(tr);
      });

      scroll.appendChild(table);
      on(qs('#cogs-refresh'),'click',loadCogs);
    }catch(e){ notify(`Cogs error: ${e.message}`, false); }
  }

  // Section scaffolding
  function ensureSectionCard(id, title, controls){
    const sec = qs('#'+id); sec.innerHTML = '';
    const wrap = document.createElement('div'); wrap.className = 'table-wrap';
    const head = document.createElement('div'); head.className = 'table-head';
    head.innerHTML = `<div class="table-title">${title}</div><div class="table-actions"></div>`;
    const actions = head.querySelector('.table-actions');

    (controls||[]).forEach(([label, meta])=>{
      if(meta && meta.kind==='select'){
        const sel = document.createElement('select'); sel.id = meta.id;
        (meta.items||[]).forEach(v=>{ const o=document.createElement('option'); o.value=v; o.textContent=v; sel.appendChild(o); });
        actions.appendChild(sel);
      }else if(meta && meta.kind==='input'){
        const inp = document.createElement('input'); inp.type='text'; inp.id=meta.id; inp.placeholder=meta.placeholder||'';
        actions.appendChild(inp);
      }else{
        const btn = document.createElement('button'); btn.className='btn'; if(meta?.id) btn.id=meta.id; btn.textContent=label;
        actions.appendChild(btn);
      }
    });

    const scroll = document.createElement('div'); scroll.className='table-scroll';
    wrap.appendChild(head); wrap.appendChild(scroll); sec.appendChild(wrap);
    return wrap;
  }

  // Polling
  function startPolling(){
    if(state.pollingId) clearInterval(state.pollingId);
    state.pollingId = setInterval(async()=>{
      if(state.currentPage==='dashboard') await loadDashboard();
      else if(state.currentPage==='bets') await loadBets();
    }, 5000);
  }

  // Init
  async function init(){
    setTheme(state.theme);
    try{ const s = await fetchJSON('/admin/auth/status'); setAdminMode(!!(s && s.unlocked)); }
    catch{ setAdminMode(false); }

    wireTheme(); wireAuth(); wireNav(); wireDashButtons();
    setPage(state.currentPage);
    await routePage();
    startPolling();
  }
  on(window,'load',init);
})();
