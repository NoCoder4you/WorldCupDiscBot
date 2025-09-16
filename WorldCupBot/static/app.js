/* World Cup 2026 Panel - public by default with admin toggle
   Notes:
   - Client-side password gate is NOT real security. Protect your backend separately.
   - Replace window.__ADMIN_PASS_HASH__ in index.html with your SHA-256 hex.
*/
(function(){
  const qs = (s,root=document)=>root.querySelector(s);
  const qsa = (s,root=document)=>Array.from(root.querySelectorAll(s));

  const state = {
    admin: false,
    data: { overview: null, teams: [], bets: [], users: [], cogs: [], backups: [] }
  };

  const el = {
    panel: qs('#panelContent'),
    tabs: qsa('.tab'),
    badge: qs('#viewBadge'),
    adminBtn: qs('#adminToggleBtn'),
    logoutBtn: qs('#logoutAdminBtn'),
    refreshBtn: qs('#refreshBtn'),
    modal: qs('#adminModal'),
    adminForm: qs('#adminForm'),
    adminError: qs('#adminError'),
    adminPassword: qs('#adminPassword'),
  };

  // ----- Utilities -----
  async function sha256Hex(text){
    const enc = new TextEncoder().encode(text);
    const hash = await crypto.subtle.digest('SHA-256', enc);
    return Array.from(new Uint8Array(hash)).map(b=>b.toString(16).padStart(2,'0')).join('');
  }

  function setAdminMode(on){
    state.admin = !!on;
    document.body.classList.toggle('is-admin', state.admin);
    el.badge.textContent = state.admin ? 'Admin' : 'Public';
    el.adminBtn.classList.toggle('hidden', state.admin);
    el.logoutBtn.classList.toggle('hidden', !state.admin);
    // show/hide admin tabs
    qsa('.admin-only').forEach(x=> x.classList.toggle('hidden', !state.admin));
    localStorage.setItem('wc_admin', state.admin ? '1' : '0');
  }

  function setActiveTab(name){
    qsa('.tab').forEach(t=> t.classList.toggle('active', t.dataset.tab === name));
    renderTab(name);
  }

  function skeleton(rows=5){
    const tpl = qs('#row-skeleton');
    const wrap = document.createElement('div');
    wrap.className = 'grid';
    for(let i=0;i<rows;i++) wrap.appendChild(tpl.content.cloneNode(true));
    return wrap;
  }

  // ----- Data fetching with graceful fallback -----
  async function apiGet(path){
    try{
      const r = await fetch(path, { headers: { 'Accept':'application/json' } });
      if(!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      return await r.json();
    }catch(err){
      console.warn('GET failed', path, err);
      return null;
    }
  }

  async function loadData(){
    el.panel.replaceChildren(skeleton(6));
    // Public endpoints
    const [overview, teams, bets] = await Promise.all([
      apiGet('/api/overview'),
      apiGet('/api/teams'),
      apiGet('/api/bets')
    ]);
    state.data.overview = overview || { uptime: 'unknown', version: 'n/a', guilds: 1, members: 0 };
    state.data.teams = Array.isArray(teams) ? teams : [];
    state.data.bets = Array.isArray(bets) ? bets : [];

    if(state.admin){
      const [users, cogs, backups] = await Promise.all([
        apiGet('/api/users'),
        apiGet('/api/cogs'),
        apiGet('/api/backups')
      ]);
      state.data.users = Array.isArray(users) ? users : [];
      state.data.cogs = Array.isArray(cogs) ? cogs : [];
      state.data.backups = Array.isArray(backups) ? backups : [];
    }
    // re-render current tab
    const current = qs('.tab.active')?.dataset.tab || 'overview';
    renderTab(current);
  }

  // ----- Renderers -----
  function renderTab(name){
    el.panel.innerHTML = '';
    switch(name){
      case 'overview': return renderOverview();
      case 'teams': return renderTeams();
      case 'bets': return renderBets();
      case 'users': return requireAdmin(renderUsers);
      case 'cogs': return requireAdmin(renderCogs);
      case 'backups': return requireAdmin(renderBackups);
      case 'messages': return requireAdmin(renderMessages);
      default: el.panel.textContent = 'Unknown tab';
    }
  }

  function requireAdmin(fn){
    if(!state.admin){
      const div = document.createElement('div');
      div.className = 'card';
      div.innerHTML = `<h3>Admin only</h3><p class="muted">Unlock admin to view this section.</p>`;
      el.panel.appendChild(div);
      return;
    }
    fn();
  }

  function renderOverview(){
    const wrap = document.createElement('div');
    wrap.className = 'grid';
    const cards = [
      ['Uptime', state.data.overview?.uptime || 'unknown'],
      ['Version', state.data.overview?.version || 'n/a'],
      ['Guilds', String(state.data.overview?.guilds ?? '1')],
      ['Members', String(state.data.overview?.members ?? '0')],
    ];
    cards.forEach(([k,v])=>{
      const c = document.createElement('div'); c.className = 'card';
      c.innerHTML = `<h3>${k}</h3><div class="kv"><span class="muted">${k}</span><strong>${v}</strong></div>`;
      wrap.appendChild(c);
    });
    el.panel.appendChild(wrap);
  }

  function renderTeams(){
    const table = document.createElement('table'); table.className = 'table';
    table.innerHTML = `<thead><tr>
      <th>Country</th><th>Owner</th><th>Split</th></tr></thead><tbody></tbody>`;
    const tb = table.querySelector('tbody');
    if(!state.data.teams.length){
      const tr = document.createElement('tr');
      tr.innerHTML = `<td colspan="3"><span class="muted">No teams yet</span></td>`;
      tb.appendChild(tr);
    }else{
      state.data.teams.forEach(t=>{
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${escapeHtml(t.country || '')}</td>
                        <td>${escapeHtml(t.owner || 'Unowned')}</td>
                        <td>${escapeHtml(t.split || '-')}</td>`;
        tb.appendChild(tr);
      });
    }
    el.panel.appendChild(table);
  }

  function renderBets(){
    const table = document.createElement('table'); table.className = 'table';
    table.innerHTML = `<thead><tr>
      <th>From</th><th>To</th><th>Stake</th><th>Status</th></tr></thead><tbody></tbody>`;
    const tb = table.querySelector('tbody');
    if(!state.data.bets.length){
      const tr = document.createElement('tr');
      tr.innerHTML = `<td colspan="4"><span class="muted">No bets found</span></td>`;
      tb.appendChild(tr);
    }else{
      state.data.bets.forEach(b=>{
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${escapeHtml(b.from || '')}</td>
                        <td>${escapeHtml(b.to || '')}</td>
                        <td>${escapeHtml(String(b.stake ?? ''))}</td>
                        <td>${escapeHtml(b.status || '')}</td>`;
        tb.appendChild(tr);
      });
    }
    el.panel.appendChild(table);
  }

  function renderUsers(){
    const table = document.createElement('table'); table.className = 'table';
    table.innerHTML = `<thead><tr>
      <th>User</th><th>Roles</th><th>Joined</th></tr></thead><tbody></tbody>`;
    const tb = table.querySelector('tbody');
    if(!state.data.users.length){
      const tr = document.createElement('tr');
      tr.innerHTML = `<td colspan="3"><span class="muted">No users</span></td>`;
      tb.appendChild(tr);
    }else{
      state.data.users.forEach(u=>{
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${escapeHtml(u.name || '')}</td>
                        <td>${escapeHtml((u.roles||[]).join(', '))}</td>
                        <td>${escapeHtml(u.joined || '')}</td>`;
        tb.appendChild(tr);
      });
    }
    el.panel.appendChild(table);
  }

  function renderCogs(){
    const wrap = document.createElement('div'); wrap.className = 'grid';
    if(!state.data.cogs.length){
      const c = document.createElement('div'); c.className='card';
      c.innerHTML = `<h3>No cogs reported</h3>`;
      wrap.appendChild(c);
    }else{
      state.data.cogs.forEach(cg=>{
        const c = document.createElement('div'); c.className='card';
        c.innerHTML = `<h3>${escapeHtml(cg.name||'Cog')}</h3>
          <div class="kv"><span class="muted">Status</span><strong>${cg.enabled?'Enabled':'Disabled'}</strong></div>
          <div style="display:flex; gap:8px; margin-top:10px;">
            <button class="btn" data-action="reload" data-cog="${escapeAttr(cg.name)}">Reload</button>
            <button class="btn ghost" data-action="${cg.enabled?'disable':'enable'}" data-cog="${escapeAttr(cg.name)}">${cg.enabled?'Disable':'Enable'}</button>
          </div>`;
        wrap.appendChild(c);
      });
    }
    // delegate actions
    wrap.addEventListener('click', async (e)=>{
      const btn = e.target.closest('button[data-action]'); if(!btn) return;
      const action = btn.dataset.action, cog = btn.dataset.cog;
      btn.disabled = true;
      await fetch(`/api/cogs/${encodeURIComponent(cog)}/${action}`, { method:'POST' }).catch(()=>{});
      btn.disabled = false;
      loadData();
    });
    el.panel.appendChild(wrap);
  }

  function renderBackups(){
    const wrap = document.createElement('div'); wrap.className='grid';
    const make = document.createElement('div'); make.className='card';
    make.innerHTML = `<h3>Backups</h3>
      <div style="display:flex; gap:8px; margin-top:6px;">
        <button class="btn" id="backupAllBtn">Backup all JSON</button>
      </div>`;
    wrap.appendChild(make);

    const list = document.createElement('div'); list.className='card';
    list.innerHTML = `<h3>Available files</h3>`;
    const ul = document.createElement('ul'); ul.style.listStyle='none'; ul.style.padding='0';
    (state.data.backups||[]).forEach(b=>{
      const li = document.createElement('li');
      li.innerHTML = `<a href="/api/backups/download/${encodeURIComponent(b)}">${escapeHtml(b)}</a>`;
      ul.appendChild(li);
    });
    list.appendChild(ul);
    wrap.appendChild(list);

    wrap.addEventListener('click', async (e)=>{
      if(e.target.id === 'backupAllBtn'){
        const btn = e.target; btn.disabled = true;
        await fetch('/api/backups/run', { method:'POST' }).catch(()=>{});
        btn.disabled = false; loadData();
      }
    });
    el.panel.appendChild(wrap);
  }

  function renderMessages(){
    const card = document.createElement('div'); card.className='card';
    card.innerHTML = `<h3>Direct message a user</h3>
      <label class="input-label" for="dmUser">User ID</label>
      <input id="dmUser" class="input" placeholder="Discord User ID">
      <label class="input-label" for="dmText">Message</label>
      <textarea id="dmText" class="input" rows="4" placeholder="Your message"></textarea>
      <div style="display:flex; gap:8px; margin-top:10px;">
        <button class="btn" id="dmSend">Send</button>
      </div>
      <p id="dmStatus" class="muted"></p>`;
    card.addEventListener('click', async (e)=>{
      if(e.target.id === 'dmSend'){
        const uid = qs('#dmUser', card).value.trim();
        const msg = qs('#dmText', card).value.trim();
        if(!uid || !msg) return;
        qs('#dmStatus', card).textContent = 'Sending...';
        await fetch('/api/message', {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ user_id: uid, message: msg })
        }).catch(()=>{});
        qs('#dmStatus', card).textContent = 'Done';
      }
    });
    el.panel.appendChild(card);
  }

  // ----- Events -----
  el.tabs.forEach(t => t.addEventListener('click', ()=> setActiveTab(t.dataset.tab)));
  el.refreshBtn.addEventListener('click', loadData);

  el.adminBtn.addEventListener('click', ()=> {
    if(typeof el.modal.showModal === 'function'){ el.modal.showModal(); }
    else alert('Your browser does not support modals.');
    el.adminPassword.value = '';
    el.adminError.classList.add('hidden');
    setTimeout(()=> el.adminPassword.focus(), 20);
  });
  el.logoutBtn.addEventListener('click', ()=> setAdminMode(false));

  el.adminForm.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const input = el.adminPassword.value;
    const digest = await sha256Hex(input);
    if(digest === (window.__ADMIN_PASS_HASH__||'')){
      el.modal.close();
      setAdminMode(true);
      loadData();
    }else{
      el.adminError.classList.remove('hidden');
    }
  });

  // Helpers
  function escapeHtml(s){ return String(s).replace(/[&<>"']/g, m=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[m])); }
  function escapeAttr(s){ return String(s).replace(/"/g, '&quot;'); }

  // ----- Init -----
  (function init(){
    const was = localStorage.getItem('wc_admin') === '1';
    setAdminMode(was);
    // ensure tab visibility is correct on load
    qsa('.admin-only').forEach(x=> x.classList.toggle('hidden', !state.admin));
    setActiveTab('overview');
    loadData();
  })();
})();