(() => {
  'use strict';
  const qs = (s, el=document) => el.querySelector(s);
  const $userPage = qs('#user');
  const $btnLogin = qs('#btn-discord-login');
  const $btnLogout = qs('#btn-discord-logout');
  const $body = qs('#user-body');
  const STAGE_PROGRESS = {
  "Eliminated": 0,
  "Group": 15,
  "R16": 35,
  "QF": 55,
  "SF": 70,
  "F": 90,
  "Second Place": 95,
  "Winner": 100
};

  async function jget(url){
    const r = await fetch(url, {credentials:'include'});
    return r.json().catch(()=>({}));
  }
  async function jpost(url, data){
    const r = await fetch(url, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      credentials:'include',
      body: JSON.stringify(data||{})
    });
    return r.json().catch(()=>({}));
  }

  function renderSignedOut(){
    if($btnLogin) $btnLogin.style.display = '';
    if($btnLogout) $btnLogout.style.display = 'none';
    if($body) $body.innerHTML = `
      <div class="card" style="height:auto">
        <div class="card-title">Not signed in</div>
        <p>Connect your Discord account to see your teams and upcoming matches.</p>
      </div>`;
  }

// === SVG progress ring ===
    function makeStageRing(stage) {
      const p = STAGE_PROGRESS[stage] ?? 0;
      const r = 18;
      const C = 2 * Math.PI * r;
      const off = C * (1 - p / 100);
      const color = p === 100 ? '#ffd700' : '#00aaff';
      return `
        <svg class="stage-ring" width="48" height="48" viewBox="0 0 48 48" aria-label="Stage ${stage}">
          <circle cx="24" cy="24" r="${r}" stroke="#222" stroke-width="5" fill="none"></circle>
          <circle cx="24" cy="24" r="${r}" stroke="${color}" stroke-width="5"
            stroke-dasharray="${C}" stroke-dashoffset="${off}" stroke-linecap="round" fill="none"></circle>
          <text x="24" y="28" text-anchor="middle" fill="#fff" font-size="9">${p}%</text>
        </svg>
      `;
    }

    // === Render stage progress rings ===
    async function renderUserTeamsWithStages(ownedTeams, title = 'Your Teams (Progress)') {
      const stages = await jget('/team_stage');   // { "France": "Winner", ... }
      const body = document.getElementById('user-body');
      if (!body) return;

      const stageData = stages || {};
      const html = `
        <div class="card" style="height:auto; margin-top:12px">
          <div class="card-title">${title}</div>
          ${
            (ownedTeams && ownedTeams.length)
              ? ownedTeams.map(team => {
                  const name = team.team || team.name || String(team);
                  const stage = stageData[name] || 'Group';
                  const ring = makeStageRing(stage);
                  const flag = team.flag ? `<img class="flag-img" src="${team.flag}" alt="">` : '';
                  return `
                    <div class="user-team-row" title="${stage}">
                      <span class="user-team-name">${flag}${name}</span>
                      <span class="user-team-ring">${ring}</span>
                    </div>`;
                }).join('')
              : '<p class="muted">No teams yet.</p>'
          }
        </div>
      `;

      // APPEND instead of replace
      body.insertAdjacentHTML('beforeend', html);
    }


  function teamChip(t){
    const img = t.flag ? `<img class="flag-img" src="${t.flag}" alt="">` : '';
    return `<span class="pill pill-off" style="margin:2px 6px 2px 0">${img}${t.team}</span>`;
  }

  function renderSignedIn(user, owned, split, matches){
    if($btnLogin) $btnLogin.style.display = 'none';
    if($btnLogout) $btnLogout.style.display = '';
    const avatar = user.avatar ? `<img src="${user.avatar}" style="width:56px;height:56px;border-radius:12px;vertical-align:middle;margin-right:10px">` : '';
    const title = `<div style="display:flex;align-items:center;gap:10px">
        ${avatar}
        <div>
          <div style="font-weight:900;font-size:1.1rem">${user.global_name || user.username}</div>
          <div class="muted mono">${user.username}</div>
        </div>
      </div>`;

    const ownRow = (owned||[]).length ? owned.map(teamChip).join(' ') : '<span class="muted">None yet</span>';
    const splitRow = (split||[]).length ? split.map(teamChip).join(' ') : '<span class="muted">None</span>';
    const matchRows = (matches||[]).map(m=>{
      const when = (m.utc||'').replace('T',' ').replace('Z',' UTC');
      return `<tr><td>${when}</td><td>${m.home}</td><td>${m.away}</td><td>${m.stadium||''}</td></tr>`;
    }).join('');

    if($body) $body.innerHTML = `
      <div class="card" style="height:auto">
        <div class="card-title">Profile</div>
        ${title}
      </div>

      <div class="card" style="height:auto; margin-top:12px">
        <div class="card-title">Your Teams</div>
        <div><strong>Main owner</strong></div>
        <div style="margin:6px 0 10px">${ownRow}</div>
        <div><strong>Co-owner</strong></div>
        <div style="margin-top:6px">${splitRow}</div>
      </div>

      <div class="card" style="height:auto; margin-top:12px">
        <div class="card-title">Upcoming Matches</div>
        ${matchRows ? `<table class="table"><thead><tr><th>When (UTC)</th><th>Home</th><th>Away</th><th>Stadium</th></tr></thead><tbody>${matchRows}</tbody></table>`
                     : `<p class="muted">No upcoming matches found for your teams.</p>`}
      </div>
    `;
    renderUserTeamsWithStages(owned || [], 'Your Teams (Progress)');
    if (split && split.length) {
      renderUserTeamsWithStages(split || [], 'Co-owned Teams (Progress)');
    }

  async function refreshUser(){
    try{
      const me = await jget('/api/me');
      if(!me?.user){ renderSignedOut(); return; }
      const [own, games] = await Promise.all([
        jget('/api/me/ownership'),
        jget('/api/me/matches')
      ]);
      renderSignedIn(me.user, own.owned||[], own.split||[], games.matches||[]);
    }catch(e){
      renderSignedOut();
    }
  }

  function wire(){
    if(!$userPage) return;
    setTimeout(refreshUser, 0);
    if($btnLogin) $btnLogin.onclick = ()=> window.location.href = '/auth/discord/login';
    if($btnLogout) $btnLogout.onclick = async ()=>{ await jpost('/auth/discord/logout',{}); refreshUser(); };
    document.addEventListener('click', (e)=>{
      const a = e.target.closest('a[data-page="user"]');
      if(a){ setTimeout(refreshUser, 50); }
    });
    if($userPage.classList.contains('active-section')){
      refreshUser();
    }
  }

  wire();
})();
