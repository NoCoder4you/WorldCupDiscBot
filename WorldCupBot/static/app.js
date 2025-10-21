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
  async function loadOwnershipPage(){
    try{
      const d = await fetchJSON('/api/ownerships');
      const wrap = ensureSectionCard('ownership','Ownership',[
        ['Filter',{kind:'input',id:'own-filter',placeholder:'Search name, id, country'}],
      ]);
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

  // --- BETS + Admin pages unchanged (same as previous message) ---
  async function loadBets(){
    try{
      const d = await fetchJSON('/api/bets');
      const items = Array.isArray(d) ? d : (d.bets||[]);
      const wrap = ensureSectionCard('bets','Bets',[
        ['Refresh',{id:'bets-refresh-btn'}],
        ['Rows',{kind:'select',id:'bets-rows',items:[10,25,50,100]}],
        ['Search',{kind:'input',id:'bets-search',placeholder:'Search'}],
      ]);
      const scroll = wrap.querySelector('.table-scroll'); scroll.innerHTML='';
      const table = document.createElement('table'); table.className='table';
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

  // newest expiry first
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
          <div class="chip-group hidden">
            <button class="btn-chip chip-accept" data-action="accept" data-id="${escapeHTML(realId)}">Accept</button>
            <button class="btn-chip chip-decline" data-action="decline" data-id="${escapeHTML(realId)}">Decline</button>
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
      cell.querySelector('.chip-group')?.classList.add('hidden');
    });
  }

  // delegate clicks
  table.addEventListener('click', async (e) => {
    const pill = e.target.closest('.pill-click');
    if (pill) {
      // toggle current row, collapse others
      const cell = pill.closest('.action-cell');
      const chips = cell.querySelector('.chip-group');
      const isOpen = !chips.classList.contains('hidden');
      collapseAll();
      if (!isOpen) {
        pill.classList.add('hidden');
        chips.classList.remove('hidden');
      }
      return;
    }

    const chip = e.target.closest('.btn-chip[data-action]');
    if (chip) {
      const action = chip.getAttribute('data-action');   // "accept" | "decline"
      const sid = chip.getAttribute('data-id');
      const row = chip.closest('tr');

      // disable buttons during request
      row.querySelectorAll('.btn-chip').forEach(b => b.disabled = true);

      try {
        const res = await submitSplitAction(action, sid); // { ok, pending_count, history_count, event }
        if (!res || res.ok === false) {
          throw new Error(res?.error || 'unknown error');
        }

        // remove row for snappy feel
        row.remove();

        // update counter
        const countEl = document.getElementById('pending-count');
        if (countEl && typeof res.pending_count === 'number') {
          countEl.textContent = res.pending_count;
        }

        // show empty state if none left
        if (!tbody.children.length) {
          const empty = document.createElement('div');
          empty.className = 'split-empty';
          empty.textContent = 'No pending requests.';
          table.replaceWith(empty);
        }

        // refresh history so the new event appears
        loadSplitHistoryOnce();

        notify(`Split ${action}ed`, true);
      } catch (err) {
        notify(`Failed to ${action} split: ${err.message || err}`, false);
        row.querySelectorAll('.btn-chip').forEach(b => b.disabled = false);
      }
    }
  });

  // click-away to collapse
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


  async function loadBackups(){ /* unchanged */ try{ const d=await fetchJSON('/api/backups'); const w=ensureSectionCard('backups','Backups',[['Backup All',{id:'bk-create'}],['Restore Latest',{id:'bk-restore'}],['Prune',{id:'bk-prune'}]]); const s=w.querySelector('.table-scroll'); s.innerHTML=''; const files=(d?.backups)||(d?.folders?.[0]?.files)||[]; if(!files.length){ const p=document.createElement('p'); p.textContent='No backups yet.'; s.appendChild(p);} else{ const t=document.createElement('table'); t.className='table'; t.innerHTML='<thead><tr><th>Name</th><th>Size</th><th>Modified</th><th></th></tr></thead><tbody></tbody>'; const tb=t.querySelector('tbody'); files.forEach(f=>{ const tr=document.createElement('tr'); const size=(f.bytes||f.size)||0; const ts=f.mtime||f.ts; const dt=ts?new Date(ts*1000).toLocaleString():''; const a=document.createElement('a'); a.href=`/api/backups/download?rel=${encodeURIComponent(f.rel||f.name)}`; a.textContent='Download'; tr.innerHTML=`<td>${escapeHtml(f.name)}</td><td>${Math.round(size/1024/1024)} MB</td><td>${escapeHtml(dt)}</td><td></td>`; tr.children[3].appendChild(a); tb.appendChild(tr); }); s.appendChild(t);} qs('#bk-create').onclick=async()=>{ try{ await fetchJSON('/api/backups/create',{method:'POST',body:JSON.stringify({})}); notify('Backup created'); await loadBackups(); }catch(e){ notify(`Backup failed: ${e.message}`, false);} }; qs('#bk-restore').onclick=async()=>{ try{ if(!files[0]) return notify('No backups to restore', false); await fetchJSON('/api/backups/restore',{method:'POST',body:JSON.stringify({name:files[0].name})}); notify('Restored latest backup'); }catch(e){ notify(`Restore failed: ${e.message}`, false);} }; qs('#bk-prune').onclick=async()=>{ try{ const r=await fetchJSON('/admin/backups/prune',{method:'POST',body:JSON.stringify({keep:10})}); if(r&&r.ok) notify(`Pruned ${r.pruned} backups`); else notify('Prune failed', false); await loadBackups(); }catch(e){ notify(`Prune error: ${e.message}`, false);} }; }catch(e){ notify(`Backups error: ${e.message}`, false); } }
  async function loadLogs(kind='bot'){ /* unchanged */ try{ const d=await fetchJSON(`/api/log/${kind}`); const w=ensureSectionCard('log','Logs',[['Bot',{id:'log-kind-bot'}],['Health',{id:'log-kind-health'}],['Refresh',{id:'log-refresh'}],['Clear',{id:'log-clear'}],['Download',{id:'log-download'}],['Filter',{kind:'input',id:'log-q',placeholder:'Search'}]]); const s=w.querySelector('.table-scroll'); s.innerHTML=''; const box=document.createElement('div'); box.className='log-window'; const q=(qs('#log-q').value||'').toLowerCase(); (d.lines||[]).forEach(line=>{ if(q && !line.toLowerCase().includes(q)) return; const div=document.createElement('div'); div.textContent=line; box.appendChild(div); }); s.appendChild(box); qs('#log-kind-bot').onclick=()=>loadLogs('bot'); qs('#log-kind-health').onclick=()=>loadLogs('health'); qs('#log-refresh').onclick=()=>loadLogs(kind); qs('#log-clear').onclick=async()=>{ try{ await fetchJSON(`/api/log/${kind}/clear`,{method:'POST',body:JSON.stringify({})}); await loadLogs(kind);}catch(e){ notify(`Clear failed: ${e.message}`, false);} }; qs('#log-download').onclick=()=>{ window.location.href=`/api/log/${kind}/download`; }; qs('#log-q').oninput=()=>loadLogs(kind); }catch(e){ notify(`Logs error: ${e.message}`, false); } }

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
      const group = document.createElement('div'); group.className = 'chip-group';
      const mk = (label, cls, action) => {
        const b = document.createElement('button');
        b.className = `btn-chip ${cls}`;
        b.textContent = label;
        b.onclick = async () => {
          try{
            // show pending state
            pill.className = 'pill pill-wait';
            pill.textContent = 'Applying…';

            await fetchJSON(`/admin/cogs/${encodeURIComponent(name)}/${action}`, {
              method:'POST', body: JSON.stringify({})
            });
            notify(`${action} queued for ${name}`);
            postWebhookMessage(`wc ${action} ${name}`);

            // small delay then re-check status
            setTimeout(async () => {
              const v = await getCogStatus(name);
              if (typeof v === 'boolean') setPill(v);
              else { pill.className='pill pill-off'; pill.textContent='Unknown'; }
            }, 800);
          }catch(e){
            notify(`Cog ${action} failed: ${e.message}`, false);
            // revert to a safe state read
            const v = await getCogStatus(name);
            if (typeof v === 'boolean') setPill(v);
            else { pill.className='pill pill-off'; pill.textContent='Unknown'; }
          }
        };
        return b;
      };

      group.appendChild(mk('reload','chip-reload','reload'));
      group.appendChild(mk('load','chip-load','load'));
      group.appendChild(mk('unload','chip-unload','unload'));

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
