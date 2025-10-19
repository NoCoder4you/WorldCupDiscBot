/* app.js - logged-out 3-card grid, logged-in dice-5 grid, Bot Process text only */
(() => {
  'use strict';

  const qs = (s, el=document) => el.querySelector(s);
  const qsa = (s, el=document) => [...el.querySelectorAll(s)];

  const state = {
    admin:false,
    theme: localStorage.getItem('wc:theme') || 'dark',
    currentPage: localStorage.getItem('wc:lastPage') || 'dashboard',
    pollingId: null,
    logsKind:'bot'
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

  function sleep(ms){ return new Promise(r=>setTimeout(r, ms)); }
  function notify(msg, ok=true){
    const div = document.createElement('div');
    div.className = `notice ${ok?'ok':'err'}`;
    div.textContent = msg;
    $notify.appendChild(div);
    setTimeout(()=>div.remove(), 2400);
  }
  async function fetchJSON(url, opts={}, {timeoutMs=10000, retries=1}={}){
    const ctrl = new AbortController();
    const to = setTimeout(()=>ctrl.abort(), timeoutMs);
    try{
      const res = await fetch(url, { ...opts, headers:{'Content-Type':'application/json', ...(opts.headers||{})}, signal:ctrl.signal, credentials:'include' });
      if(!res.ok){
        let m = `${res.status}`;
        try{ const ej = await res.json(); m = ej.error || ej.message || JSON.stringify(ej); }catch{}
        throw new Error(m);
      }
      const ct = res.headers.get('content-type')||'';
      return ct.includes('application/json') ? await res.json() : {};
    }catch(e){
      if(retries>0){ await sleep(300); return fetchJSON(url, opts, {timeoutMs, retries:retries-1}); }
      throw e;
    }finally{ clearTimeout(to); }
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

  function setPage(p){
    state.currentPage = p;
    localStorage.setItem('wc:lastPage', p);
    qsa('#main-menu a').forEach(a=>a.classList.toggle('active', a.dataset.page===p));
    qsa('section.page-section').forEach(s=>s.classList.toggle('active-section', s.id===p));
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

  async function loadDash(){
    try{
      const upP = fetchJSON('/api/uptime');

      // Measure ping latency in ms
      const t0 = performance.now();
      const pingP = fetchJSON('/api/ping');
      // Only fetch /api/system when admin to lighten logged-out view
      const sysP = state.admin ? fetchJSON('/api/system') : Promise.resolve(null);

      const [up, ping, sys] = await Promise.all([upP, pingP, sysP]);
      const latency = Math.max(0, Math.round(performance.now() - t0));

      renderUptime(up);
      renderPing(ping, latency);
      if(state.admin && sys) renderSystem(sys);
      else clearSystem(); // ensure gauges reset when logging out

      if(state.admin){
        const running = !!(up && up.bot_running);
        const $actions = qs('#bot-actions');
        const $start = qs('#start-bot');
        const $stop = qs('#stop-bot');
        const $restart = qs('#restart-bot');
        if($actions && $start && $stop && $restart){
          if(running){
            $start.style.display='none';
            $stop.style.display='inline-block';
            $restart.style.display='inline-block';
            $actions.style.gridTemplateColumns = '1fr 1fr';
          }else{
            $start.style.display='inline-block';
            $stop.style.display='none';
            $restart.style.display='none';
            $actions.style.gridTemplateColumns = '1fr';
          }
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
    const t = s => { const el=qs('#'+s); if(el) el.textContent='--'; };
    t('mem-text'); t('cpu-text'); t('disk-text');
    ['mem-extra','cpu-extra','disk-extra'].forEach(id=>{ const el=qs('#'+id); if(el) el.textContent=''; });
  }
  function renderSystem(sys){
    const s = sys?.system || {};
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
  function renderUptime(up){
    const running = !!(up && up.bot_running);
    qs('#uptime-label').textContent = running ? 'Uptime' : 'Downtime';
    qs('#uptime-value').textContent = running ? (up.uptime_hms || '--:--:--') : (up.downtime_hms || '--:--:--');
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

  function ensureSectionCard(id, title, controls){
    const sec = qs(`#${id}`);
    sec.innerHTML='';
    const wrap = document.createElement('div');
    wrap.className='table-wrap';
    const head = document.createElement('div');
    head.className='table-head';
    head.innerHTML = `<div class="table-title">${title}</div><div class="table-actions"></div>`;
    const actions = head.querySelector('.table-actions');
    (controls||[]).forEach(([label, meta])=>{
      if(meta && meta.kind==='input'){
        const inp = document.createElement('input');
        inp.type='text'; inp.id=meta.id; inp.placeholder=meta.placeholder||'';
        actions.appendChild(inp);
      }else if(meta && meta.kind==='select'){
        const sel = document.createElement('select'); sel.id=meta.id;
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
  function escapeHtml(v){ return String(v==null?'':v).replace(/[&<>"']/g, s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s])); }

  async function loadOwnershipPage(){
    try{
      const d = await fetchJSON('/api/ownerships');
      // Render with only filter (no export CSV)
      const wrap = ensureSectionCard('ownership','Ownership',[['Filter',{kind:'input',id:'own-filter',placeholder:'Search name, id, country'}]]);
      const scroll = wrap.querySelector('.table-scroll'); scroll.innerHTML='';
      const table=document.createElement('table'); table.className='table';
      table.innerHTML='<thead><tr><th>Country</th><th>Owners</th></tr></thead><tbody></tbody>';
      scroll.appendChild(table);
      const filter=qs('#own-filter'); filter.value = localStorage.getItem('wc:ownQ') || '';
      function draw(){
        const q=(filter.value||'').toLowerCase();
        localStorage.setItem('wc:ownQ', q);
        const tbody=table.querySelector('tbody'); tbody.innerHTML='';
        (d.ownerships||[]).forEach(r=>{
          const country=r.country||''; const owners=(r.owners||[]).join(', ');
          const hay=(country+' '+owners).toLowerCase(); if(q && !hay.includes(q)) return;
          const tr=document.createElement('tr'); tr.innerHTML=`<td>${escapeHtml(country)}</td><td>${escapeHtml(owners)}</td>`; tbody.appendChild(tr);
        });
      }
      filter.oninput=draw; draw();
    }catch(e){ notify(`Ownership error: ${e.message}`, false); }
  }

  async function loadBets(){
    try{
      const d = await fetchJSON('/api/bets');
      const items = Array.isArray(d) ? d : (d.bets||[]);
      const wrap = ensureSectionCard('bets','Bets',[
        ['Refresh',{id:'bets-refresh-btn'}],
        ['Rows',{kind:'select',id:'bets-rows',items:[10,25,50,100]}],
        ['Search',{kind:'input',id:'bets-search',placeholder:'Search'}],
      ]);
      const scroll = wrap.querySelector('.table-scroll');
      scroll.innerHTML='';
      const table = document.createElement('table');
      table.className='table';
      table.innerHTML = `<thead><tr>
        <th data-k="bet_id">ID</th><th data-k="bet_title">Title</th><th data-k="wager">Wager</th>
        <th data-k="option1">Option 1</th><th data-k="option2">Option 2</th><th data-k="settled">Status</th>
      </tr></thead><tbody></tbody>`;
      scroll.appendChild(table);

      let sortKey='bet_id', sortDir=1;
      table.querySelectorAll('th').forEach(th=>th.addEventListener('click',()=>{
        const k=th.dataset.k; if(sortKey===k) sortDir=-sortDir; else {sortKey=k; sortDir=1;} draw();
      }));
      const rowsSel = qs('#bets-rows'); const searchInp = qs('#bets-search');
      rowsSel.value = localStorage.getItem('wc:betsRows') || '25';
      searchInp.value = localStorage.getItem('wc:betsQ') || '';
      function draw(){
        const q=(searchInp.value||'').toLowerCase();
        const perPage=Number(rowsSel.value||25);
        localStorage.setItem('wc:betsRows', String(perPage));
        localStorage.setItem('wc:betsQ', q);
        const filtered = items.filter(b => JSON.stringify(b).toLowerCase().includes(q));
        const sorted = filtered.sort((a,b)=>{
          const av=a?.[sortKey], bv=b?.[sortKey];
          if(av==null && bv==null) return 0; if(av==null) return 1; if(bv==null) return -1;
          if(av<bv) return -1*sortDir; if(av>bv) return 1*sortDir; return 0;
        });
        const pageItems = sorted.slice(0, perPage);
        const tbody = table.querySelector('tbody'); tbody.innerHTML='';
        pageItems.forEach(b=>{
          const tr=document.createElement('tr');
          const status = b.settled ? 'Settled':'Open';
          tr.innerHTML = `<td>${escapeHtml(b.bet_id)}</td><td>${escapeHtml(b.bet_title)}</td><td>${escapeHtml(b.wager)}</td>
                          <td>${escapeHtml(b.option1)}${!b.option1_user_id?'<div class="unclaimed">Unclaimed</div>':''}</td>
                          <td>${escapeHtml(b.option2)}${!b.option2_user_id?'<div class="unclaimed">Unclaimed</div>':''}</td>
                          <td>${status}</td>`;
          tbody.appendChild(tr);
        });
      }
      draw();
      qs('#bets-refresh-btn').addEventListener('click', loadBets);
      rowsSel.addEventListener('change', draw);
      searchInp.addEventListener('input', draw);
    }catch(e){ notify(`Bets error: ${e.message}`, false); }
  }

  async function loadSplits(){
    try{
      let data; try{ data = await fetchJSON('/admin/splits'); }catch{ data = await fetchJSON('/api/split_requests'); }
      const wrap = ensureSectionCard('splits','Split Requests',[['Refresh',{id:'splits-refresh'}]]);
      const scroll = wrap.querySelector('.table-scroll'); scroll.innerHTML='';
      const pre=document.createElement('pre'); pre.textContent=JSON.stringify(data,null,2); scroll.appendChild(pre);
      qs('#splits-refresh').addEventListener('click', loadSplits);
    }catch(e){ notify(`Splits error: ${e.message}`, false); }
  }
  async function loadBackups(){
    try{
      const d = await fetchJSON('/api/backups');
      const wrap = ensureSectionCard('backups','Backups',[
        ['Backup All',{id:'bk-create'}],
        ['Restore Latest',{id:'bk-restore'}],
        ['Prune',{id:'bk-prune'}],
      ]);
      const scroll = wrap.querySelector('.table-scroll'); scroll.innerHTML='';
      const files = (d?.backups) || (d?.folders?.[0]?.files) || [];
      if(!files.length){ const p=document.createElement('p'); p.textContent='No backups yet.'; scroll.appendChild(p); }
      else{
        const table=document.createElement('table'); table.className='table';
        table.innerHTML='<thead><tr><th>Name</th><th>Size</th><th>Modified</th><th></th></tr></thead><tbody></tbody>';
        const tbody=table.querySelector('tbody');
        files.forEach(f=>{
          const tr=document.createElement('tr');
          const size = (f.bytes||f.size)||0;
          const ts = f.mtime||f.ts;
          const dt = ts ? new Date(ts*1000).toLocaleString() : '';
          const a=document.createElement('a'); a.href=`/api/backups/download?rel=${encodeURIComponent(f.rel||f.name)}`; a.textContent='Download';
          tr.innerHTML = `<td>${escapeHtml(f.name)}</td><td>${Math.round(size/1024/1024)} MB</td><td>${escapeHtml(dt)}</td><td></td>`;
          tr.children[3].appendChild(a); tbody.appendChild(tr);
        });
        scroll.appendChild(table);
      }
      qs('#bk-create').onclick = async ()=>{ try{ await fetchJSON('/api/backups/create',{method:'POST',body:JSON.stringify({})}); notify('Backup created'); await loadBackups(); }catch(e){ notify(`Backup failed: ${e.message}`, false);} };
      qs('#bk-restore').onclick = async ()=>{ try{ if(!files[0]) return notify('No backups to restore', false); await fetchJSON('/api/backups/restore',{method:'POST',body:JSON.stringify({name:files[0].name})}); notify('Restored latest backup'); }catch(e){ notify(`Restore failed: ${e.message}`, false);} };
      qs('#bk-prune').onclick = async ()=>{ try{ const r=await fetchJSON('/admin/backups/prune',{method:'POST',body:JSON.stringify({keep:10})}); if(r&&r.ok) notify(`Pruned ${r.pruned} backups`); else notify('Prune failed', false); await loadBackups(); }catch(e){ notify(`Prune error: ${e.message}`, false);} };
    }catch(e){ notify(`Backups error: ${e.message}`, false); }
  }
  async function loadLogs(kind='bot'){
    try{
      const d = await fetchJSON(`/api/log/${kind}`);
      const wrap = ensureSectionCard('log','Logs',[
        ['Bot',{id:'log-kind-bot'}],
        ['Health',{id:'log-kind-health'}],
        ['Refresh',{id:'log-refresh'}],
        ['Clear',{id:'log-clear'}],
        ['Download',{id:'log-download'}],
        ['Filter',{kind:'input',id:'log-q',placeholder:'Search'}],
      ]);
      const scroll = wrap.querySelector('.table-scroll'); scroll.innerHTML='';
      const box=document.createElement('div'); box.className='log-window';
      const q=(qs('#log-q').value||'').toLowerCase();
      (d.lines||[]).forEach(line=>{ if(q && !line.toLowerCase().includes(q)) return; const div=document.createElement('div'); div.textContent=line; box.appendChild(div); });
      scroll.appendChild(box);
      qs('#log-kind-bot').onclick=()=>loadLogs('bot');
      qs('#log-kind-health').onclick=()=>loadLogs('health');
      qs('#log-refresh').onclick=()=>loadLogs(kind);
      qs('#log-clear').onclick=async()=>{ try{ await fetchJSON(`/api/log/${kind}/clear`,{method:'POST',body:JSON.stringify({})}); await loadLogs(kind);}catch(e){ notify(`Clear failed: ${e.message}`, false);} };
      qs('#log-download').onclick=()=>{ window.location.href=`/api/log/${kind}/download`; };
      qs('#log-q').oninput=()=>loadLogs(kind);
    }catch(e){ notify(`Logs error: ${e.message}`, false); }
  }
  async function loadCogs(){
    try{
      let d; try{ d = await fetchJSON('/admin/cogs'); }catch{ d = await fetchJSON('/api/cogs'); }
      const wrap = ensureSectionCard('cogs','Cogs',[['Refresh',{id:'cogs-refresh'}]]);
      const scroll = wrap.querySelector('.table-scroll'); scroll.innerHTML='';
      const table=document.createElement('table'); table.className='table';
      table.innerHTML='<thead><tr><th>Name</th><th>Actions</th></tr></thead><tbody></tbody>';
      const tbody=table.querySelector('tbody');
      (d.cogs||[]).forEach(c=>{
        const tr=document.createElement('tr'); tr.innerHTML=`<td>${escapeHtml(c.name)}</td><td></td>`;
        ['reload','load','unload'].forEach(act=>{
          const b=document.createElement('button'); b.className='btn'; b.textContent=act;
          b.onclick=async()=>{ try{ await fetchJSON(`/admin/cogs/${encodeURIComponent(c.name)}/${act}`,{method:'POST',body:JSON.stringify({})}); notify(`${act} queued for ${c.name}`);}catch(e){ notify(`Cog ${act} failed: ${e.message}`, false);} };
          tr.children[1].appendChild(b);
        });
        tbody.appendChild(tr);
      });
      scroll.appendChild(table);
      qs('#cogs-refresh').onclick=loadCogs;
    }catch(e){ notify(`Cogs error: ${e.message}`, false); }
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
      case 'bets': await loadBets(); break;
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
      else if(state.currentPage==='bets') await loadBets();
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
