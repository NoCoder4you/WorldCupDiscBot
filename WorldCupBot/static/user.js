(() => {
  'use strict';
  const qs = (s, el=document) => el.querySelector(s);
  const $userPage = qs('#user');
  const $btnLogin = qs('#btn-discord-login');
  const $btnLogout = qs('#btn-discord-logout');
  const $body = qs('#user-body');
  const $notify = qs('#notify');

    function notify(msg, ok = true) {
        const div = document.createElement('div');
        div.className = `notice ${ok ? 'ok' : 'err'}`;
        div.textContent = msg;
    if ($notify) {
      $notify.appendChild(div);
      setTimeout(() => div.remove(), 2200);
    }
    }

    function cleanTag(tag){
    if (!tag) return '';
    const s = String(tag);
    return s.endsWith('#0') ? s.slice(0, -2) : s;
  }


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
    return map[s] || s || "Group Stage";
  }

  // Map common team-name variants to your JSON keys
  const TEAM_ALIASES = {
    'USA': 'United States',
    'U.S.A.': 'United States',
    'United States of America': 'United States',
    'South Korea': 'Korea Republic',
    'Cote d\'Ivoire': 'Ivory Coast',
    'Côte d’Ivoire': 'Ivory Coast',
    'Cape Verde': 'Cape Verde',
    'DR Congo': 'Congo DR',
    'Iran': 'Iran',
    'UAE': 'United Arab Emirates'
  };

  function canon(s){
    return String(s||'')
      .normalize('NFD').replace(/[\u0300-\u036f]/g,'')
      .toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  }

  function resolveStageFor(stages, name){
    if (!stages || !name) return undefined;

    if (Object.prototype.hasOwnProperty.call(stages, name)) return stages[name];

    const alias = TEAM_ALIASES[name];
    if (alias && Object.prototype.hasOwnProperty.call(stages, alias)) return stages[alias];

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
    if ($notify) $notify.textContent = '';
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
        <circle cx="60" cy="60" r="${r}" stroke="${track}" stroke-width="10" fill="none"></circle>
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
    const MAIN_COLOR  = '#00F8FF';
    const SPLIT_COLOR = '#2aa8ff';

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

    body.insertAdjacentHTML('beforeend', card);
  }

  function teamChip(t){
    const img = t.flag ? `<img class="flag-img" src="${t.flag}" alt="">` : '';
    return `<span class="pill pill-off" style="margin:2px 6px 2px 0">${img}${t.team}</span>`;
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
        label = 'Won';  cls = 'pill-win-UP';
      } else {
        label = 'Lost'; cls = 'pill-loss-UP';
      }
    }

    const statusPill = `<span class="pill-UP ${cls}">${label}</span>`;

    return `
      <tr>
        <td class="col-id mono">${b.id || ''}</td>
        <td class="col-title">${b.title || ''}</td>
        <td class="col-roles">${choice}</td>
        <td class="col-status">${statusPill}</td>
      </tr>`;
  }

  async function renderUserBetsCard(user){
    const body = document.getElementById('user-body');
    if(!body || !user) return;

    let data = { bets: [] };
    try{
      data = await fetchMyBets(user.discord_id || user.id);
    }catch(_){}

    const rows = (data.bets||[]).map(betRowHTML).join('');
    const table = rows
      ? `<div class="table-scroll">
           <table class="table">
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
         </div>`
      : `<p class="muted">No bets found for your account.</p>`;

    body.insertAdjacentHTML('beforeend', `
      <div class="card" style="height:auto; margin-top:12px">
        <div class="card-title">Your Bets</div>
        ${table}
      </div>
    `);
  }

    async function renderSignedIn(user, owned, split, matches, isAdmin, masqueradingAs, verified){
  if ($btnLogin) $btnLogin.style.display = 'none';
  if ($btnLogout) $btnLogout.style.display = '';

  const inAdminView = localStorage.getItem('wc:adminView') === '1';

  const tidyTag = (s) => {
    if (!s) return '';
    const v = String(s);
    return v.endsWith('#0') ? v.slice(0, -2) : v;
  };

  // ---------- base identity - real logged-in user ----------
  const baseUserName =
    user.discord_username || user.username || user.tag || user.name || '';

  let viewName =
    user.discord_display_name ||
    user.discord_global_name ||
    user.global_name ||
    user.display_name ||
    tidyTag(baseUserName);

  let viewTag    = tidyTag(baseUserName);
  let viewId     = user.discord_id || user.id || '';
  let viewAvatar =
    user.discord_avatar || user.avatar_url || user.avatar || '';

  let masqDisplay = '';

  // ---------- override with masqueraded target from verified.json ----------
  if (masqueradingAs) {
    const list   = Array.isArray(verified) ? verified : [];
    const target = list.find(v => String(v.discord_id || v.id || '') === String(masqueradingAs));

    if (target) {
        const tId = String(target.discord_id || target.id || '');

        const tUserName =
          target.discord_username ||
          target.username ||
          target.discord_display_name ||
          target.display_name ||
          '';

        const tGlobal = target.discord_global_name || target.global_name || '';

        const tDisp =
          target.discord_display_name ||
          target.display_name ||
          tGlobal ||
          tUserName;

      const tAvatar   =
        target.discord_avatar || target.avatar_url || target.avatar || '';

      masqDisplay = tDisp || tidyTag(tUserName) || tId;

      viewName   = tDisp || viewName;
      viewTag    = tidyTag(tUserName) || viewTag;
      viewId     = tId || viewId;
      viewAvatar = tAvatar || viewAvatar;
    } else {
      masqDisplay = String(masqueradingAs);
    }
  }

  const avatarHtml = `<img id="user-avatar" src="${viewAvatar || ''}" style="width:56px;height:56px;border-radius:12px;vertical-align:middle;margin-right:10px">`;

  const adminLine = inAdminView
    ? `<div class="muted mono">ID: ${viewId}</div>`
    : '';

  const title = `<div style="display:flex;align-items:center;gap:10px">
      ${avatarHtml}
      <div>
        <div style="font-weight:900;font-size:1.1rem">${viewName}</div>
        <div class="muted mono">${viewTag}</div>
        ${adminLine}
      </div>
    </div>`;

  // ---------- admin-only masquerade controls ----------
  let masqControls = '';
  if (isAdmin && inAdminView) {
    const list = Array.isArray(verified) ? verified : [];
    const options = list.map(v => {
      const id = String(v.discord_id || v.id || '');
      if (!id) return '';
      const label =
        v.discord_display_name ||
        v.discord_global_name ||
        v.display_name ||
        v.discord_username ||
        v.username ||
        id;
      const selected =
        masqueradingAs && String(masqueradingAs) === id ? ' selected' : '';
      return `<option value="${id}"${selected}>${label}</option>`;
    }).join('');

    const bannerText = masqDisplay
      ? `Now Showing as: ${masqDisplay}`
      : 'Viewing as yourself';

    masqControls = `
      <div class="user-masq-wrap">
        <div class="user-masq-banner muted" id="masq-banner">${bannerText}</div>
        <div class="user-masq-row">
          <label for="masq-select" class="muted user-masq-label">View as</label>
          <select id="masq-select" class="select">
            <option value="">-- Choose user --</option>
            ${options}
          </select>
          <div class="user-masq-buttons">
            <button id="masq-apply" class="btn small">Apply</button>
            <button id="masq-clear" class="btn small secondary">Back to self</button>
          </div>
        </div>
      </div>
    `;
  }

  const matchRows = (matches || []).map(m => {
    const when = (m.utc || '').replace('T', ' ').replace('Z', ' UTC');
    return `<tr><td>${when}</td><td>${m.home || ''}</td><td>${m.away || ''}</td><td>${m.stadium || ''}</td></tr>`;
  }).join('');

  if ($body) {
    $body.innerHTML = `
      <div class="card user-profile-card" style="height:auto">
        <div class="card-title">Profile</div>
        <div class="user-profile-layout">
          <div class="user-profile-main">
            ${title}
          </div>
          ${masqControls}
        </div>
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

    // Optional safety if you still have upgradeAvatar in the file
    if (typeof upgradeAvatar === 'function' && viewId) {
      upgradeAvatar(viewId);
    }
  }

  // ---------- wire masquerade controls + notify ----------
  if (isAdmin && inAdminView) {
    const banner   = document.getElementById('masq-banner');
    const sel      = document.getElementById('masq-select');
    const btnApply = document.getElementById('masq-apply');
    const btnClear = document.getElementById('masq-clear');

    const updateBanner = (name, selfLabel) => {
      if (banner) {
        banner.textContent = name
          ? `Now Showing as: ${name}`
          : (selfLabel || 'Viewing as yourself');
      }
      if (typeof notify === 'function' && name) {
        notify(`Now Showing as: ${name}`, true);
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
        const label = sel.options[sel.selectedIndex]?.text || id;
        updateBanner(label);
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
        if (banner) banner.textContent = 'Viewing as yourself';
        refreshUser();
      };
    }

    if (masqDisplay) {
      updateBanner(masqDisplay);
    } else if (banner) {
      banner.textContent = 'Viewing as yourself';
    }
  }

  // teams + bets unchanged
  renderTeamsProgressMerged(owned || [], split || []);
  const betsUser = { discord_id: masqueradingAs || user.discord_id || user.id };
  await renderUserBetsCard(betsUser);
}

    async function jgetAuth(url){
        const r = await fetch(url, { credentials: 'include', cache: 'no-store' });
        if(!r.ok) throw new Error(`GET ${url} ${r.status}`);
     return r.json();
    }

    async function upgradeAvatar(discordId){
    try{
      const id = discordId ? String(discordId) : '';
      if (!id) return;

      const img = document.getElementById('user-avatar');
      if (!img) return;

      const data = await jgetAuth(`/api/avatars?ids=${encodeURIComponent(id)}`);
      if (!data || !data.avatars) return;

      const url = data.avatars[id];
      if (url && typeof url === 'string') {
        img.src = url;
      }
    }catch(e){
      console.error('upgradeAvatar failed', e);
    }
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
