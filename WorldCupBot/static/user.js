(() => {
  'use strict';

  const qs = (s, el=document) => el.querySelector(s);
  const $userPage = qs('#user');
  const $btnLogin = qs('#btn-discord-login');
  const $btnLogout = qs('#btn-discord-logout');
  const $body = qs('#user-body');
  const $notify = qs('#notify');

  // local copy of notify helper (matches app.js behaviour)
  function notify(msg, ok=true){
    if (!$notify) return;
    const div = document.createElement('div');
    div.className = `notice ${ok ? 'ok' : 'err'}`;
    div.textContent = msg;
    $notify.appendChild(div);
    setTimeout(()=>div.remove(), 2200);
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

  function cleanTag(tag){
    if (!tag) return '';
    const s = String(tag);
    return s.endsWith('#0') ? s.slice(0, -2) : s;
  }

  function normalizeStage(label){
    const s = String(label || '').trim();
    const map = {
      "Group": "Group Stage",
      "R32": "Round of 32",
      "R16": "Round of 16",
      "QF": "Quarter Final",
      "SF": "Semi Final",
      "F": "Final"
    };
    return map[s] || s || "Group Stage";
  }

  async function fetchMyBets(uid){
    const r = await fetch(`/api/my_bets?uid=${encodeURIComponent(uid)}&t=${ Date.now() }`, { cache:'no-store' });
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
        <circle cx="60" cy="60" r="${r}" stroke="${track}" stroke-width="10" fill="none"></circle>
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

  function ownerPill(text, isMain){
    const cls = isMain ? 'pill-on' : 'pill-off';
    return `<span class="pill ${cls}" style="margin:2px 4px 2px 0">${text}</span>`;
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
      const flag = t.flag
        ? `<img src="${t.flag}" alt="${name} flag" style="width:28px;height:20px;border-radius:3px;margin-right:6px;vertical-align:middle">`
        : '';
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
    const tidy = (s) => cleanTag(s || '');

    // base identity from /api/me
    const baseUserName =
      user.discord_username || user.username || user.tag || user.name || '';

    let viewName =
      user.discord_display_name ||
      user.discord_global_name ||
      user.global_name ||
      user.display_name ||
      tidy(baseUserName);

    let viewTag    = tidy(baseUserName);
    let viewId     = user.discord_id || user.id || '';
    let viewAvatar =
      user.discord_avatar || user.avatar_url || user.avatar || '';

    let masqDisplay = '';

    // override with masquerade target if present
    if (masqueradingAs) {
      const list   = Array.isArray(verified) ? verified : [];
      const target = list.find(
        v => String(v.discord_id || v.id || '') === String(masqueradingAs)
      );

      if (target) {
        const tId       = String(target.discord_id || target.id || '');
        const tUserName = target.discord_username || target.username || '';
        const tGlob     = target.discord_global_name || target.global_name || '';
        const tDisp     =
          target.discord_display_name ||
          target.display_name ||
          tGlob ||
          tUserName;
        const tAvatar   =
          target.discord_avatar || target.avatar_url || target.avatar || '';

        masqDisplay = tDisp || tidy(tUserName) || tId;

        viewName   = tDisp || viewName;
        viewTag    = tidy(tUserName) || viewTag;
        viewId     = tId || viewId;
        viewAvatar = tAvatar || viewAvatar;
      } else {
        masqDisplay = String(masqueradingAs);
      }
    }

    const avatarHtml = viewAvatar
      ? `<img src="${viewAvatar}" style="width:56px;height:56px;border-radius:12px;vertical-align:middle;margin-right:10px">`
      : '';

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

    // admin masquerade controls
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
        <div class="muted" id="masq-banner" style="margin-top:8px;font-size:12px">${bannerText}</div>
        <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:6px;align-items:center">
          <label for="masq-select" class="muted" style="font-size:12px">View as</label>
          <select id="masq-select" class="select"
                  style="min-width:220px;padding:6px 12px;border-radius:999px;">
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

    if($body){
      $body.innerHTML = `
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
    }

    // wire masquerade controls + notify popup
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
        if (name) notify(`Now Showing as: ${name}`, true);
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

    // Teams grid and Bets card
    renderTeamsProgressMerged(owned || [], split || []);
    const betsUser = { discord_id: masqueradingAs || user.discord_id || user.id };
    await renderUserBetsCard(betsUser);
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
    if($btnLogout) $btnLogout.onclick = async ()=>{
      await jpost('/auth/discord/logout',{});
      refreshUser();
    };
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
