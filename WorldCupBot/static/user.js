(() => {
  'use strict';
  const qs = (s, el=document) => el.querySelector(s);
  const $userPage = qs('#user');
  const $btnLogin = qs('#btn-discord-login');
  const $btnLogout = qs('#btn-discord-logout');
  const $body = qs('#user-body');
  const $notify = qs('#notify');
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
    "Winner": "Winner"
  };
  return map[s] || s || "Group Stage";
}

function ownerPill(text, isMain){
  const cls = isMain ? 'pill-on' : 'pill-off';
  return `<span class="pill ${cls}" style="margin:2px 4px 2px 0">${text}</span>`;
}

function renderTeamTile(t, isMain){
  const name = t.team || t.name || String(t);
  const stage = normalizeStage(t.stage || '');
  const color = isMain ? '#00c896' : '#2aa8ff';
  const owners = (t.owners || []).map(o => ownerPill(o, o === t.main_owner)).join('');
  const flag = t.flag ? `<img src="${t.flag}" alt="${name} flag" style="width:28px;height:20px;border-radius:3px;margin-right:6px;vertical-align:middle">` : '';
  return `
    <div class="team-card">
      <div class="team-card-main">
        <div class="team-card-flag-name">
          ${flag}
          <span class="team-name">${name}</span>
        </div>
        <div class="team-card-stage">${stage}</div>
      </div>
      <div class="team-card-owners">${owners}</div>
      <div class="team-card-ring">
        ${makeStageRing(stage, color)}
      </div>
    </div>
  `;
}

function renderUnassignedTile(t){
  const flag = t.flag ? `<img src="${t.flag}" alt="${t.team} flag" style="width:26px;height:18px;border-radius:3px;margin-right:6px;vertical-align:middle">` : '';
  return `<span class="pill pill-off" style="margin:2px 6px 2px 0">${flag}${t.team}</span>`;
}

async function fetchMyBets(uid){
  const r = await fetch(`/api/my_bets?uid=${encodeURIComponent(uid)}&t=${Date.now()}`, { cache:'no-store' });
  if(!r.ok) throw new Error('Failed to load bets');
  return r.json();
}

function betRowHTML(b){
  const choice = b.your_choice || (b.roles||[]).join(', ') || '—';

  let label = 'Pending', cls = 'pill-wait-UP';
  if (b.winner_side) {
    if (b.your_side && b.your_side === b.winner_side) {
      label = 'Won';
      cls = 'pill-good-UP';
    } else if (b.winner_side) {
      label = 'Lost';
      cls = 'pill-bad-UP';
    }
  }

  return `
    <tr>
      <td class="mono">${b.id || ''}</td>
      <td>${b.title || ''}</td>
      <td>${choice}</td>
      <td><span class="pill ${cls}">${label}</span></td>
    </tr>
  `;
}

async function renderUserBetsCard(user){
  const body = document.getElementById('user-body');
  if(!body || !user || !user.discord_id) return;

  let data;
  try{
    data = await fetchMyBets(user.discord_id);
  }catch(e){
    console.warn('Failed to load my bets', e);
    return;
  }
  const bets = (data && data.bets) || [];
  const rows = bets.map(betRowHTML).join('');
  const table = rows
    ? `
      <div class="table-wrap">
        <div class="table-scroll">
          <table class="table table-compact">
            <thead>
              <tr>
                <th>ID</th>
                <th>Bet</th>
                <th>Your Choice</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>`
    : `<p class="muted">No bets found for your account.</p>`;

  body.insertAdjacentHTML('beforeend', `
    <div class="card" style="height:auto; margin-top:12px">
      <div class="card-title">Your Bets</div>
      ${table}
    </div>
  `);
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

async function fetchTeamStagesFresh(){
  const r = await fetch('/api/team_stage?t=' + Date.now(), { cache: 'no-store' });
  if(!r.ok) throw new Error('team_stage fetch failed');
  return r.json();
}

async function renderTeamsProgressMerged(ownedTeams, splitTeams){
  const body = document.getElementById('user-body');
  if(!body) return;

  const stages = await fetchTeamStagesFresh();
  const MAIN_COLOR  = '#00F8FF';
  const SPLIT_COLOR = '#2aa8ff';

  const makeTile = (t, isMain) => {
    const name = t.team || t.name || String(t);
    const stage = normalizeStage(stages[name] || stages[t.team] || t.stage || '');
    const color = isMain ? MAIN_COLOR : SPLIT_COLOR;
    const owners = (t.owners || []).map(o => ownerPill(o, o === t.main_owner)).join('');
    const flag = t.flag ? `<img src="${t.flag}" alt="${name} flag" style="width:28px;height:20px;border-radius:3px;margin-right:6px;vertical-align:middle">` : '';
    return `
      <div class="team-card">
        <div class="team-card-main">
          <div class="team-card-flag-name">
            ${flag}
            <span class="team-name">${name}</span>
          </div>
          <div class="team-card-stage">${stage}</div>
        </div>
        <div class="team-card-owners">${owners}</div>
        <div class="team-card-ring">
          ${makeStageRing(stage, color)}
        </div>
      </div>
    `;
  };

  const makeUnassignedTile = (t) => {
    const flag = t.flag ? `<img src="${t.flag}" alt="${t.team} flag" style="width:26px;height:18px;border-radius:3px;margin-right:6px;vertical-align:middle">` : '';
    return `<span class="pill pill-off" style="margin:2px 6px 2px 0">${flag}${t.team}</span>`;
  };

  const mainTiles = (ownedTeams || []).map(t => makeTile(t, true)).join('');
  const splitTiles = (splitTeams || []).map(t => makeTile(t, false)).join('');

  body.insertAdjacentHTML('beforeend', `
    <div class="card" style="height:auto; margin-top:12px">
      <div class="card-title">Your Teams</div>
      ${
        mainTiles || splitTiles
          ? `<div class="teams-grid">${mainTiles}${splitTiles}</div>`
          : `<p class="muted">You do not own any teams yet.</p>`
      }
    </div>
  `);
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

async function renderSignedIn(user, owned, split, matches, isAdmin, masqueradingAs, verified){
  if($btnLogin) $btnLogin.style.display = 'none';
  if($btnLogout) $btnLogout.style.display = '';

  const inAdminView = localStorage.getItem('wc:adminView') === '1';

  const avatar = user.avatar
    ? `<img src="${user.avatar}" style="width:56px;height:56...px;border-radius:12px;vertical-align:middle;margin-right:10px">`
    : '';

  const adminLine = inAdminView
    ? `<div class="muted mono">ID: ${user.discord_id || user.id || ''}</div>`
    : '';

  // Work out masquerade display name (if any)
  let masqDisplay = '';
  if (masqueradingAs) {
    const list = Array.isArray(verified) ? verified : [];
    const target = list.find(v => String(v.discord_id || v.id || '') === String(masqueradingAs));
    if (target) {
      masqDisplay = target.display_name || target.username || String(masqueradingAs);
    } else {
      masqDisplay = String(masqueradingAs);
    }
  }

  const title = `<div style="display:flex;align-items:center;gap:10px">
      ${avatar}
      <div>
        <div style="font-weight:900;font-size:1.1rem">${user.global_name || user.username}</div>
        <div class="muted mono">${user.username}</div>
        ${adminLine}
      </div>
    </div>`;

  // Admin-only masquerade controls
  let masqControls = '';
  if (isAdmin && inAdminView) {
    const list = Array.isArray(verified) ? verified : [];
    const options = list.map(v => {
      const id = String(v.discord_id || v.id || '');
      if (!id) return '';
      const label = v.display_name || v.username || id;
      const selected = masqueradingAs && String(masqueradingAs) === id ? ' selected' : '';
      return `<option value="${id}"${selected}>${label}</option>`;
    }).join('');

    const bannerText = masqDisplay
      ? `Now Showing as: ${masqDisplay}`
      : 'Viewing as yourself';

    masqControls = `
      <div class="muted" id="masq-banner" style="margin-top:8px;font-size:12px">${bannerText}</div>
      <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:6px;align-items:center">
        <label for="masq-select" class="muted" style="font-size:12px">View as</label>
        <select id="masq-select" class="select" style="min-width:180px">
          <option value="">-- Choose user --</option>
          ${options}
        </select>
        <button id="masq-apply" class="btn small">Apply</button>
        <button id="masq-clear" class="btn small secondary">Back to self</button>
      </div>
    `;
  }

  const matchRows = (matches||[]).map(m=>{
    const when = (m.utc||'').replace('T',' ').replace('Z',' UTC');
    return `<tr><td>${when}</td><td>${m.home||''}</td><td>${m.away||''}</td><td>${m.stadium||''}</td></tr>`;
  }).join('');

  if($body) $body.innerHTML = `
    <div class="card" style="height:auto">
      <div class="card-title">Profile</div>
      ${title}
      ${masqControls}
    </div>

    <div class="card" style="height:auto; margin-top:12px">
      <div class="card-title">Upcoming Matches</div>
      ${
        matchRows
          ? `<table class="table"><thead><tr><th>When (UTC)</th><th>Home</th><th>Away</th><th>Stadium</th></tr></thead><tbody>${matchRows}</tbody></table>`
          : `<p class="muted">No upcoming matches found for your teams.</p>`
      }
    </div>
  `;

  // Wire up masquerade controls once DOM exists
  if (isAdmin && inAdminView) {
    const banner = document.getElementById('masq-banner');
    const sel = document.getElementById('masq-select');
    const btnApply = document.getElementById('masq-apply');
    const btnClear = document.getElementById('masq-clear');

    const updateBanner = (name, selfLabel) => {
      if (banner) {
        banner.textContent = name ? `Now Showing as: ${name}` : (selfLabel || 'Viewing as yourself');
      }
      if ($notify) {
        $notify.textContent = name ? `Now Showing as: ${name}` : '';
      }
    };

    if (btnApply && sel) {
      btnApply.onclick = async () => {
        const id = sel.value.trim();
        if (!id) return;
        try{
          await jpost('/admin/masquerade/start', { discord_id: id });
        }catch(e){
          console.error('masquerade start failed', e);
        }
        updateBanner(sel.options[sel.selectedIndex]?.text || id);
        refreshUser();
      };
    }

    if (btnClear) {
      btnClear.onclick = async () => {
        try{
          await jpost('/admin/masquerade/stop', {});
        }catch(e){
          console.error('masquerade stop failed', e);
        }
        updateBanner('', 'Viewing as yourself');
        refreshUser();
      };
    }

    if (masqDisplay) {
      updateBanner(masqDisplay);
    } else {
      updateBanner('', 'Viewing as yourself');
    }
  } else if ($notify) {
    // ensure notify bar is cleared when not in masquerade context
    $notify.textContent = '';
  }

  // Teams grid with big progress rings
  renderTeamsProgressMerged(owned || [], split || []);

  // Your Bets card
  await renderUserBetsCard(user);
}

async function jgetAuth(url){
  const r = await fetch(url, { credentials: 'include', cache: 'no-store' });
  if(!r.ok) throw new Error(`GET ${url} ${r.status}`);
  return r.json();
}

async function refreshUser(){
  try{
    const me = await jgetAuth('/api/me');
    if(!me?.user){ renderSignedOut(); return; }

    const inAdminView = localStorage.getItem('wc:adminView') === '1';
    const wantVerified = !!me.is_admin && inAdminView;

    const promises = [
      jgetAuth('/api/me/ownership'),
      jgetAuth('/api/me/matches')
    ];
    if (wantVerified) {
      promises.push(jgetAuth('/api/verified'));
    }

    const results = await Promise.all(promises);
    const own = results[0] || {};
    const games = results[1] || {};
    const verified = wantVerified ? (results[2] || []) : null;

    await renderSignedIn(
      me.user,
      own.owned || [],
      own.split || [],
      (games && games.matches) || [],
      !!me.is_admin,
      me.masquerading_as || null,
      Array.isArray(verified) ? verified : []
    );
  }catch(e){
    console.error('refreshUser failed:', e);
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
