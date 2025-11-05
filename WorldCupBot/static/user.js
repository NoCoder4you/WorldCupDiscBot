(() => {
  'use strict';
  const qs = (s, el=document) => el.querySelector(s);
  const $userPage = qs('#user');
  const $btnLogin = qs('#btn-discord-login');
  const $btnLogout = qs('#btn-discord-logout');
  const $body = qs('#user-body');
const STAGE_PROGRESS = {
  "Eliminated": 0,
  "Group Stage": 15,
  "Round of 32": 25,
  "Round of 16": 35,
  "Quarter Final": 55,
  "Semi Final": 70,
  "Final": 90,
  "Winner": 100
};

function normalizeStage(label){
  const s = String(label || '').trim();
  const map = {
    "Group": "Group Stage",
    "R32": "Round of 32",
    "R16": "Round of 16",
    "QF": "Quarter Final",
    "SF": "Semi Final",
    "F": "Final",
    "Second Place": "Final" // or remove if you bring it back later
  };
  return map[s] || s;
}

// Map common team-name variants to your JSON keys
const TEAM_ALIASES = {
  'USA': 'United States',
  'U.S.A.': 'United States',
  'United States of America': 'United States',
  'South Korea': 'Korea Republic',   // use this if your JSON uses "Korea Republic"; otherwise set to "South Korea"
  'Cote d\'Ivoire': 'Ivory Coast',
  'Côte d’Ivoire': 'Ivory Coast',
  'Cape Verde': 'Cape Verde',        // keep if your JSON key is "Cape Verde"
  'DR Congo': 'Congo DR',
  'Iran': 'Iran',                    // adjust if your JSON uses "IR Iran"
  'UAE': 'United Arab Emirates'      // example if it appears later
};

// simplify string for fuzzy match
function canon(s){
  return String(s||'')
    .normalize('NFD').replace(/[\u0300-\u036f]/g,'') // strip accents
    .toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
}

// Find the stage value in a tolerant way: exact → alias → fuzzy key match
function resolveStageFor(stages, name){
  if (!stages || !name) return undefined;

  // 1) exact
  if (Object.prototype.hasOwnProperty.call(stages, name)) return stages[name];

  // 2) alias
  const alias = TEAM_ALIASES[name];
  if (alias && Object.prototype.hasOwnProperty.call(stages, alias)) return stages[alias];

  // 3) fuzzy: case/space/diacritic-insensitive
  const want = canon(name);
  for (const k of Object.keys(stages)) {
    if (canon(k) === want) return stages[k];
  }

  return undefined;
}


    async function fetchTeamStagesFresh(){
      const url = `/api/team_stage?t=${Date.now()}`;
      const r = await fetch(url, { cache: 'no-store' });
      if (!r.ok) return {};
      return r.json();
    }


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
    function makeStageRing(stage, color) {
      const p = STAGE_PROGRESS[stage] ?? 0;
      const r = 52;
      const C = 2 * Math.PI * r;
      const off = C * (1 - p / 100);
      const label = String(stage || 'Group');
      const fontSize = (label.length > 10) ? 10 : 12;
      const track = 'rgba(255,255,255,.08)';

      return `
        <svg class="stage-ring stage-ring--lg" width="120" height="120" viewBox="0 0 120 120" aria-label="Stage ${label}">
          <!-- track -->
          <circle cx="60" cy="60" r="${r}" stroke="${track}" stroke-width="10" fill="none"></circle>
          <!-- progress; rotate -90deg so 0% is at 12 o'clock -->
          <circle cx="60" cy="60" r="${r}" stroke="${color}" stroke-width="10"
            stroke-dasharray="${C}" stroke-dashoffset="${off}" stroke-linecap="round" fill="none"
            transform="rotate(-90 60 60)"></circle>
          <text x="60" y="64" text-anchor="middle" fill="#fff" font-size="${fontSize}" font-weight="700">${label}</text>
        </svg>
      `;
    }

    async function renderTeamsProgressMerged(ownedTeams, splitTeams){
      const body = document.getElementById('user-body');
      if(!body) return;

      const stages = await fetchTeamStagesFresh();
      const MAIN_COLOR  = '#22c55e';
      const SPLIT_COLOR = '#00b8ff';

      const makeTile = (t, isMain) => {
        const name = t.team || t.name || String(t);
        const color = isMain ? MAIN_COLOR : SPLIT_COLOR;
        const raw = resolveStageFor(stages, name);
        const stage = normalizeStage(raw) || 'Group Stage';
        const ring  = makeStageRing(stage, color);
        const flag  = t.flag ? `<img class="flag-img" src="${t.flag}" alt="" />` : '';
        const badge = isMain ? '<span class="owner-pill owner-pill--main">Main</span>'
                             : '<span class="owner-pill owner-pill--split">Co-owner</span>';
        return `
          <div class="team-tile ${isMain ? 'is-main' : 'is-split'}" title="${name} - ${stage}">
            <div class="ring-wrap">${ring}</div>
            <div class="team-caption">${flag}<span>${name}</span>${badge}</div>
          </div>
        `;
      };

      const mainTiles  = (ownedTeams||[]).map(t => makeTile(t, true)).join('');
      const splitTiles = (splitTeams||[]).map(t => makeTile(t, false)).join('');
      const tiles = mainTiles + splitTiles;

      const card = `
        <div class="card" style="height:auto; margin-top:12px">
          <div class="card-title">Your Teams</div>
          ${tiles ? `<div class="teams-grid">${tiles}</div>` : `<p class="muted">No teams yet.</p>`}
        </div>
      `;

      // Append under your profile card (do not overwrite)
      body.insertAdjacentHTML('beforeend', card);
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
        <div class="card-title">Upcoming Matches</div>
        ${matchRows ? `<table class="table"><thead><tr><th>When (UTC)</th><th>Home</th><th>Away</th><th>Stadium</th></tr></thead><tbody>${matchRows}</tbody></table>`
                     : `<p class="muted">No upcoming matches found for your teams.</p>`}
      </div>
    `;
    renderTeamsProgressMerged(owned || [], split || []);

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
