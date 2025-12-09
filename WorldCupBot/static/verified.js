(() => {
  'use strict';

  const qs  = (s, el = document) => el.querySelector(s);

  const section = qs('#verified-log');
  if (!section) return;

  // Basic skeleton (same table layout style as bets / ownership)
  section.innerHTML = `
    <div class="table-wrap">
      <div class="table-head">
        <div class="table-title">Verified users</div>
        <div class="table-actions">
          <button id="verified-refresh" class="btn small">Refresh</button>
        </div>
      </div>
      <div class="table-scroll" id="verified-body">
        <div class="muted" style="padding:12px">Loading…</div>
      </div>
    </div>
  `;

  const body = qs('#verified-body', section);
  const btnRefresh = qs('#verified-refresh', section);

  async function getJSON(url) {
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) throw new Error(`${url} ${res.status}`);
    return res.json();
  }

  function renderRows(list) {
    if (!list || !list.length) {
      body.innerHTML = `<div class="muted" style="padding:12px">No verified users yet.</div>`;
      return;
    }

    // Sort by display_name then discord_id
    list.sort((a, b) => {
      const ad = (a.display_name || a.username || '').toLowerCase();
      const bd = (b.display_name || b.username || '').toLowerCase();
      if (ad < bd) return -1;
      if (ad > bd) return 1;
      const aid = (a.discord_id || '').toString();
      const bid = (b.discord_id || '').toString();
      return aid.localeCompare(bid);
    });

    const rows = list.map(v => {
      const discordName = v.display_name || v.username || '(unknown)';
      const discordId   = v.discord_id || '';
      const habbo       = v.habbo_name || '';
      const ip          = v.ip || '';

      return `
        <tr>
          <td>${discordName}</td>
          <td>${discordId}</td>
          <td>${habbo}</td>
          <td>${ip}</td>
        </tr>
      `;
    }).join('');

    body.innerHTML = `
      <table class="table">
        <thead>
          <tr>
            <th>Discord</th>
            <th>Discord ID</th>
            <th>Habbo</th>
            <th>IP</th>
          </tr>
        </thead>
        <tbody>
          ${rows}
        </tbody>
      </table>
    `;
  }

  async function loadVerified() {
    body.innerHTML = `<div class="muted" style="padding:12px">Loading…</div>`;
    try {
      const data = await getJSON('/api/verified');
      renderRows(data || []);
    } catch (e) {
      console.error(e);
      body.innerHTML = `<div class="muted" style="padding:12px">Could not load verified users.</div>`;
    }
  }

  if (btnRefresh) {
    btnRefresh.addEventListener('click', e => {
      e.preventDefault();
      loadVerified();
    });
  }

  // Initial load
  loadVerified();
})();
