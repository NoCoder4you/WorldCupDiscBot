(() => {
  'use strict';
  const qs = (s, el=document) => el.querySelector(s);
  const $userPage = qs('#user');
  const $btnLogin = qs('#btn-discord-login');
  const $btnLogout = qs('#btn-discord-logout');
  const $body = qs('#user-body');
  const MASQ_KEY = 'wc:masqUid';
  let currentMasqId = localStorage.getItem(MASQ_KEY) || '';

const STAGE_PROGRESS = {
  "Eliminated": 0,
  "Group Stage": 15,
  "Round of 32": 25,
  "Round of 16": 35,
  "Quarter Final": 55,
  "Semi Finals": 75,
  "Final": 95,
  "Champion": 100,
  "Winner": 100
};

const STAGE_ORDER = {
  "Eliminated": 0,
  "Group Stage": 1,
  "Round of 32": 2,
  "Round of 16": 3,
  "Quarter Final": 4,
  "Semi Final": 5,
  "Final": 6,
  "Champion": 7,
  "Winner": 7
};

const STAGE_BADGES = {
  "Winner": "Main",
  "Champion": "Main"
};

// Map short or variant stage labels to your canonical ones
function normalizeStageLabel(s){
  if(!s) return s;
  const map = {
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
  'Côte d\'Ivoire': 'Ivory Coast'
};

// Country name to ISO-2 or ISO-3 code if needed later
const COUNTRY_ISO = {
  "United States": "us",
  "Mexico": "mx",
  "Canada": "ca",
  "New Zealand": "nz",
  "Japan": "jp",
  "Iran": "ir"
};

function getStageProgress(stage){
  if(!stage) return 0;
  const norm = normalizeStageLabel(stage);
  return STAGE_PROGRESS[norm] ?? 0;
}

function getStageOrder(stage){
  if(!stage) return -1;
  const norm = normalizeStageLabel(stage);
  return STAGE_ORDER[norm] ?? -1;
}

function mergeTeamLists(owned, split){
  const map = new Map();

  (owned || []).forEach(t => {
    const keyName = TEAM_ALIASES[t.team] || t.team;
    if(!map.has(keyName)){
      map.set(keyName, {
        team: keyName,
        stage: normalizeStageLabel(t.stage),
        owners: [t.owner],
        splitOwners: []
      });
    }else{
      const existing = map.get(keyName);
      existing.stage = betterStage(existing.stage, t.stage);
      if(!existing.owners.includes(t.owner)) existing.owners.push(t.owner);
    }
  });

  (split || []).forEach(t => {
    const keyName = TEAM_ALIASES[t.team] || t.team;
    if(!map.has(keyName)){
      map.set(keyName, {
        team: keyName,
        stage: normalizeStageLabel(t.stage),
        owners: [],
        splitOwners: [t.owner]
      });
    }else{
      const existing = map.get(keyName);
      existing.stage = betterStage(existing.stage, t.stage);
      if(!existing.splitOwners.includes(t.owner)) existing.splitOwners.push(t.owner);
    }
  });

  return [...map.values()].sort((a, b) => {
    const ao = getStageOrder(a.stage);
    const bo = getStageOrder(b.stage);
    if(ao !== bo) return bo - ao;
    return (a.team || '').localeCompare(b.team || '');
  });
}

function betterStage(a, b){
  const ao = getStageOrder(a);
  const bo = getStageOrder(b);
  return bo > ao ? normalizeStageLabel(b) : normalizeStageLabel(a);
}

function formatStage(stage){
  const norm = normalizeStageLabel(stage);
  return norm || 'Unknown';
}

function teamFlag(teamName){
  const keyName = TEAM_ALIASES[teamName] || teamName;
  const iso = COUNTRY_ISO[keyName];
  if(!iso) return '';
  return `<img src="https://flagcdn.com/32x24/${iso}.png" alt="${keyName}" style="width:32px;height:24px;border-radius:3px;vertical-align:middle;margin-right:6px">`;
}

function teamChip(team){
  const stage = formatStage(team.stage);
  const progress = getStageProgress(team.stage);
  const badge = STAGE_BADGES[team.stage] || '';

  const circle = `
    <div class="stage-ring">
      <svg viewBox="0 0 36 36" class="ring-svg">
        <path
          class="ring-bg"
          d="M18 2.0845
             a 15.9155 15.9155 0 0 1 0 31.831
             a 15.9155 15.9155 0 0 1 0 -31.831"
        />
        <path
          class="ring-fg"
          stroke-dasharray="${progress}, 100"
          d="M18 2.0845
             a 15.9155 15.9155 0 0 1 0 31.831
             a 15.9155 15.9155 0 0 1 0 -31.831"
        />
        <text x="18" y="20.35" class="ring-text">WC</text>
      </svg>
      <div class="ring-label">${stage}</div>
    </div>
  `;

  const flag = teamFlag(team.team);

  const badgeHtml = badge
    ? `<span class="pill pill-main">${badge}</span>`
    : '';

  return `
    <div class="team-card">
      <div class="team-main">
        ${circle}
        <div class="team-info">
          <div class="team-name">
            ${flag}
            <span>${team.team}</span>
            ${badgeHtml}
          </div>
          <div class="team-owners muted">
            ${renderOwnersLine(team)}
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderOwnersLine(team){
  const mainOwners = team.owners || [];
  const splitOwners = team.splitOwners || [];

  if(!mainOwners.length && !splitOwners.length) return 'Unassigned';

  const mainStr = mainOwners.length
    ? `Main: ${mainOwners.join(', ')}`
    : '';

  const splitStr = splitOwners.length
    ? `Co-Owners: ${splitOwners.join(', ')}`
    : '';

  if(mainStr && splitStr) return `${mainStr} | ${splitStr}`;
  return mainStr || splitStr;
}

async function fetchMyBets(discordId){
  if(!discordId) return [];
  try{
    const res = await fetch(`/api/my_bets?uid=${encodeURIComponent(discordId)}`, { cache:'no-store' });
    if(!res.ok) throw new Error('bets ' + res.status);
    const data = await res.json();
    return Array.isArray(data.bets) ? data.bets : [];
  }catch(e){
    console.error('fetchMyBets error:', e);
    return [];
  }
}

async function renderUserBetsCard(user){
  if(!$body) return;
  const discordId = user && (user.discord_id || user.id);
  const bets = await fetchMyBets(discordId);

  const rows = bets.map(b => {
    const status = (b.status || '').toUpperCase();
    const choice = b.choice || '';
    const matchup = b.matchup || '';
    return `
      <tr>
        <td>${b.id || ''}</td>
        <td>${matchup}</td>
        <td>${choice}</td>
        <td><span class="pill pill-${status === 'PENDING' ? 'pending' : status.toLowerCase()}">${status}</span></td>
      </tr>
    `;
  }).join('');

  const table = rows
    ? `
      <table class="table small">
        <thead>
          <tr><th>ID</th><th>Bet</th><th>Your Choice</th><th>Status</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `
    : `<div class="muted">No bets found.</div>`;

  const wrap = document.createElement('div');
  wrap.className = 'card';
  wrap.innerHTML = `
    <div class="card-head">
      <div class="card-title">Your Bets</div>
    </div>
    <div class="card-body">
      ${table}
    </div>
  `;

  $body.appendChild(wrap);
}

async function renderTeamsProgressMerged(owned, split){
  if(!$body) return;

  const merged = mergeTeamLists(owned, split);

  const wrap = document.createElement('div');
  wrap.className = 'card';
  wrap.innerHTML = `
    <div class="card-head">
      <div class="card-title">Your Teams</div>
    </div>
    <div class="card-body">
      <div class="team-grid">
        ${merged.map(teamChip).join('') || '<div class="muted">You do not currently own any teams.</div>'}
      </div>
    </div>
  `;

  $body.appendChild(wrap);
}

function renderSignedOut(){
  if($btnLogin) $btnLogin.style.display = '';
  if($btnLogout) $btnLogout.style.display = 'none';
  if($body) $body.innerHTML = `
    <div class="muted">
      Connect your Discord account to see your World Cup profile, teams and bets.
    </div>
  `;
}

    async function fetchVerifiedList(){
      try{
        const res = await fetch('/api/verified', { cache: 'no-store' });
        if(!res.ok) throw new Error('verified ' + res.status);
        const data = await res.json();
        if(Array.isArray(data)) return data;
        if(Array.isArray(data.users)) return data.users;
        if(Array.isArray(data.verified_users)) return data.verified_users;
        return [];
      }catch(e){
        console.error('fetchVerifiedList failed:', e);
        return [];
      }
    }

    async function fetchAvatarMap(ids){
      if(!ids || !ids.length) return {};
      const qsIds = encodeURIComponent(ids.join(','));
      try{
        const res = await fetch(`/api/avatars?ids=${qsIds}`, { cache:'no-store' });
        if(!res.ok) throw new Error('avatars ' + res.status);
        const data = await res.json();
        const m = data && data.avatars;
        return m && typeof m === 'object' ? m : {};
      }catch(e){
        console.error('fetchAvatarMap failed:', e);
        return {};
      }
    }

    function findVerifiedById(list, uid){
      if(!uid) return null;
      const idStr = String(uid);
      return (list || []).find(v => String(v.discord_id || v.id || '') === idStr) || null;
    }

    function escapeHtml(str){
      return String(str || '')
        .replace(/&/g,'&amp;')
        .replace(/</g,'&lt;')
        .replace(/>/g,'&gt;')
        .replace(/"/g,'&quot;')
        .replace(/'/g,'&#39;');
    }

    async function renderSignedIn(user, owned, split, matches, isAdmin){
      if($btnLogin) $btnLogin.style.display = 'none';
      if($btnLogout) $btnLogout.style.display = '';

      const inAdminView = localStorage.getItem('wc:adminView') === '1';
      const $host = $body;
      if(!$host) return;

      const verified = await fetchVerifiedList();

      const selfId = String(user.discord_id || user.id || '');
      let masqId = currentMasqId && currentMasqId !== selfId ? currentMasqId : '';

      let target = null;
      if(isAdmin && inAdminView && masqId){
        target = findVerifiedById(verified, masqId);
        if(!target){
          masqId = '';
          currentMasqId = '';
          localStorage.removeItem(MASQ_KEY);
        }
      }

      const viewed = { ...user };
      if(target){
        viewed.discord_id = String(target.discord_id || target.id || viewed.discord_id || viewed.id || '');
        const displayName = target.display_name || target.username || viewed.global_name || viewed.username;
        viewed.global_name = displayName;
        viewed.username = target.username || target.display_name || viewed.username;
      }

      const niceTag = String(viewed.username || '')
        .replace(/#\d+$/, '');

      let avatarUrl = viewed.avatar || (target && target.avatar_url);
      if(!avatarUrl && viewed.discord_id){
        const amap = await fetchAvatarMap([viewed.discord_id]);
        avatarUrl = amap[viewed.discord_id] || avatarUrl;
      }

      const avatarHtml = avatarUrl
        ? `<img src="${avatarUrl}" style="width:56px;height:56px;border-radius:12px;vertical-align:middle;margin-right:10px">`
        : '';

      const adminLine = inAdminView
        ? `<div class="muted mono">ID: ${viewed.discord_id || viewed.id || ''}</div>`
        : '';

      const nowShowingText = target
        ? (target.display_name || target.username || `ID ${viewed.discord_id}`)
        : (viewed.global_name || niceTag || 'Yourself');

      let masqControls = '';
      if(isAdmin && inAdminView){
        const options = ['<option value="">-- Choose user --</option>'].concat(
          (verified || []).map(v=>{
            const vid = String(v.discord_id || v.id || '');
            const label = v.display_name || v.username || vid;
            const selected = vid === masqId ? ' selected' : '';
            return `<option value="${vid}"${selected}>${escapeHtml(label)}</option>`;
          })
        ).join('');
        masqControls = `
          <div style="margin-top:12px;display:flex;flex-wrap:wrap;align-items:center;gap:8px">
            <span class="muted">View as</span>
            <select id="masq-select" class="input" style="max-width:260px">${options}</select>
            <button id="masq-apply" class="btn small">Apply</button>
            <button id="masq-reset" class="btn small">Back to self</button>
          </div>
        `;
      }

      const upcomingRows = (matches || []).map(m=>{
        const when = (m.utc || '').replace('T',' ').replace('Z',' UTC');
        return `<tr><td>${escapeHtml(when)}</td><td>${escapeHtml(m.home||'')}</td><td>${escapeHtml(m.away||'')}</td><td>${escapeHtml(m.stadium||'')}</td></tr>`;
      }).join('');

      const upcomingTable = upcomingRows
        ? `<table class="table small"><thead><tr><th>When</th><th>Home</th><th>Away</th><th>Stadium</th></tr></thead><tbody>${upcomingRows}</tbody></table>`
        : `<div class="muted">No upcoming matches found for your teams.</div>`;

      $host.innerHTML = `
        <div class="card">
          <div class="card-head">
            <div class="card-title">Profile</div>
          </div>
          <div class="card-body">
            <div style="display:flex;align-items:flex-start;gap:16px;flex-wrap:wrap">
              ${avatarHtml}
              <div>
                <div style="font-weight:900;font-size:1.1rem">${escapeHtml(viewed.global_name || niceTag || '')}</div>
                <div class="muted mono">${escapeHtml(niceTag)}</div>
                ${adminLine}
                <div class="muted" style="margin-top:8px">Now Showing as: ${escapeHtml(nowShowingText)}</div>
                ${masqControls}
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <div class="card-title">Upcoming Matches</div>
          </div>
          <div class="card-body">
            ${upcomingTable}
          </div>
        </div>
      `;

      await renderTeamsProgressMerged(owned, split);
      await renderUserBetsCard(viewed);

      if(isAdmin && inAdminView){
        const sel = qs('#masq-select', $host);
        const btnApply = qs('#masq-apply', $host);
        const btnReset = qs('#masq-reset', $host);

        if(btnApply){
          btnApply.addEventListener('click', ()=>{
            const val = sel && sel.value ? sel.value.trim() : '';
            const newId = val && val !== selfId ? val : '';
            currentMasqId = newId;
            if(newId){
              localStorage.setItem(MASQ_KEY, newId);
            }else{
              localStorage.removeItem(MASQ_KEY);
            }

            if(typeof notify === 'function'){
              const tgt = findVerifiedById(verified, newId) || target;
              const name = newId
                ? (tgt && (tgt.display_name || tgt.username)) || newId
                : (user.global_name || user.username || 'Yourself');
              notify(`Now Showing as: ${name}`, true);
            }

            refreshUser();
          });
        }

        if(btnReset){
          btnReset.addEventListener('click', ()=>{
            currentMasqId = '';
            localStorage.removeItem(MASQ_KEY);
            if(typeof notify === 'function'){
              notify('Now Showing as: yourself', true);
            }
            refreshUser();
          });
        }
      }
    }

    async function refreshUser(){
      try{
        const me = await jgetAuth('/api/me');
        if(!me?.user){ renderSignedOut(); return; }

        const [own, games] = await Promise.all([
          jgetAuth('/api/me/ownership'),
          jgetAuth('/api/me/matches')
        ]);

        await renderSignedIn(
          me.user,
          own.owned || [],
          own.split || [],
          (games && games.matches) || [],
          !!me.is_admin
        );
      }catch(e){
        console.error('refreshUser failed:', e);
        renderSignedOut();
      }
    }

    async function jgetAuth(url){
      const r = await fetch(url, { credentials: 'include', cache: 'no-store' });
      if(!r.ok)
        throw new Error(`${url} ${r.status}`);
      return r.json();
    }

    if($userPage){
      refreshUser().catch(e=>{
        console.error('User page init failed:', e);
        renderSignedOut();
      });
    }
})();
