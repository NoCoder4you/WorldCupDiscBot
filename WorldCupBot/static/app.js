
async function fetchJSON(url, opts={}){
  const r = await fetch(url, Object.assign({headers: {"Content-Type":"application/json"}}, opts));
  let data = null;
  try { data = await r.json(); } catch(e){}
  return {ok: r.ok, status: r.status, data};
}
function show(el){ el.style.display = ''; }
function hide(el){ el.style.display = 'none'; }
const VISIBILITY_KEY = 'wc.adminVisible';
const getAdminVisible = () => localStorage.getItem(VISIBILITY_KEY) === 'true';
const setAdminVisible = (v) => localStorage.setItem(VISIBILITY_KEY, v ? 'true' : 'false');

function setAdminVisibilityOnPage(shouldShow){
  document.querySelectorAll('[data-admin="true"]').forEach(el => shouldShow ? show(el) : hide(el));
  const btnToggle = document.getElementById('btn-admin-toggle');
  btnToggle.textContent = shouldShow ? 'Exit Admin Mode' : 'Admin view';
}

async function refreshAuth(){
  const {data} = await fetchJSON('/admin/auth/status');
  const authed = data && data.authed;
  const wantVisible = getAdminVisible();
  const btnLogout = document.getElementById('btn-logout');

  if(authed){
    setAdminVisibilityOnPage(wantVisible);
    show(btnLogout);
  }else{
    setAdminVisible(false);
    setAdminVisibilityOnPage(false);
    hide(btnLogout);
  }
  return authed;
}

async function loadPublic(){
  const ping = await fetchJSON('/api/ping');
  document.getElementById('ping').textContent = JSON.stringify(ping.data, null, 2);
  const sys = await fetchJSON('/api/system');
  document.getElementById('sys').textContent = JSON.stringify(sys.data, null, 2);
  const bets = await fetchJSON('/api/bets');
  document.getElementById('bets').textContent = JSON.stringify(bets.data, null, 2);
}

async function loadCogs(){
  const {data} = await fetchJSON('/admin/cogs');
  const wrap = document.getElementById('cogs-list');
  if(!data || !data.cogs){ wrap.textContent = 'No data'; return; }
  wrap.innerHTML = '';
  data.cogs.forEach(c => {
    const row = document.createElement('div');
    row.className = 'row';
    row.innerHTML = `
      <code>${c.name}</code>
      <span style="margin:0 8px">${c.loaded ? 'loaded' : 'unloaded'}</span>
      <button data-action="load" data-cog="${c.name}">Load</button>
      <button data-action="unload" data-cog="${c.name}">Unload</button>
      <button data-action="reload" data-cog="${c.name}">Reload</button>
    `;
    wrap.appendChild(row);
  });
  wrap.querySelectorAll('button').forEach(b => {
    b.addEventListener('click', async () => {
      const cog = b.getAttribute('data-cog');
      const action = b.getAttribute('data-action');
      await fetchJSON('/admin/cogs/action', {method:'POST', body: JSON.stringify({cog, action})});
      await loadCogs();
    });
  });
}

async function init(){
  await loadPublic();
  document.getElementById('refresh-system').addEventListener('click', loadPublic);
  document.getElementById('refresh-bets').addEventListener('click', loadPublic);

  let authed = await refreshAuth();

  const btnToggle = document.getElementById('btn-admin-toggle');
  const btnLogout = document.getElementById('btn-logout');

  btnToggle.addEventListener('click', async ()=>{
    const {data} = await fetchJSON('/admin/auth/status');
    authed = data && data.authed;
    const isVisible = getAdminVisible();

    if(!authed){
      const modal = document.getElementById('password-modal');
      show(modal);
      document.getElementById('admin-password').value = '';
      document.getElementById('login-error').textContent = '';
      return;
    }

    if(isVisible){
      setAdminVisible(false);
    }else{
      setAdminVisible(true);
      await loadCogs();
    }
    await refreshAuth();
  });

  // Modal actions
  document.getElementById('cancel-password').addEventListener('click', ()=>{
    hide(document.getElementById('password-modal'));
  });
  document.getElementById('submit-password').addEventListener('click', async ()=>{
    const pwd = document.getElementById('admin-password').value;
    const {ok, data} = await fetchJSON('/admin/login', {method:'POST', body: JSON.stringify({password: pwd})});
    if(ok && data && data.ok){
      hide(document.getElementById('password-modal'));
      setAdminVisible(true);
      await refreshAuth();
      await loadCogs();
    }else{
      document.getElementById('login-error').textContent = (data && data.error) || 'Login failed';
    }
  });

  btnLogout.addEventListener('click', async ()=>{
    await fetchJSON('/admin/logout', {method:'POST'});
    setAdminVisible(false);
    await refreshAuth();
  });

  // Admin actions
  document.getElementById('start-bot').addEventListener('click', async ()=>{
    await fetchJSON('/admin/bot/start', {method:'POST'});
  });
  document.getElementById('stop-bot').addEventListener('click', async ()=>{
    await fetchJSON('/admin/bot/stop', {method:'POST'});
  });
  document.getElementById('restart-bot').addEventListener('click', async ()=>{
    await fetchJSON('/admin/bot/restart', {method:'POST'});
  });

  document.querySelectorAll('.btn-log').forEach(btn=>{
    btn.addEventListener('click', async ()=>{
      const logtype = btn.getAttribute('data-log');
      const {data} = await fetchJSON(`/admin/log/${logtype}`);
      document.getElementById('log-output').textContent = (data && data.lines ? data.lines.join('') : 'No data');
    });
  });
  document.querySelectorAll('.btn-log-clear').forEach(btn=>{
    btn.addEventListener('click', async ()=>{
      const logtype = btn.getAttribute('data-log');
      await fetchJSON(`/admin/log/${logtype}/clear`, {method:'POST'});
      document.getElementById('log-output').textContent = '';
    });
  });

  // If reloaded and session still valid, restore last visibility preference
  if(authed && getAdminVisible()){
    await loadCogs();
    setAdminVisibilityOnPage(true);
  }
}

document.addEventListener('DOMContentLoaded', init);
