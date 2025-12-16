(async () => {
  'use strict';

  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));

  async function fx(url, opts) {
    const r = await fetch(url, Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts || {}));
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }

  const ver = $('#ver');
  const msg = $('#msg');
  const btn = $('#btn-accept');
  const chk = $('#chk-accept');

  const content = $('#terms-content');
  const tocLinks = $$('.terms-toc .toc-link');

  // Guard: if the page structure changes, fail safely
  if (!msg || !btn || !chk || !content || !tocLinks.length) return;

  // Disable accept until requirements satisfied
  btn.disabled = true;

  // Track per-section “opened + read-to-bottom”
  const sectionIds = tocLinks
    .map(a => (a.getAttribute('href') || '').trim())
    .filter(h => h.startsWith('#'))
    .map(h => h.slice(1));

  const sections = sectionIds
    .map(id => ({ id, el: document.getElementById(id) }))
    .filter(x => x.el);

  const state = {};
  sections.forEach(s => { state[s.id] = { opened: false, read: false }; });

  let activeId = null;

  // Helpers
  function allRead() {
    return sections.every(s => state[s.id]?.read);
  }

  function updateTocUI() {
    tocLinks.forEach(a => {
      const id = (a.getAttribute('href') || '').slice(1);
      const st = state[id];
      if (!st) return;
      a.classList.toggle('toc-opened', !!st.opened);
      a.classList.toggle('toc-read', !!st.read);
      a.setAttribute('aria-pressed', st.opened ? 'true' : 'false');
    });
  }

  function updateUI() {
    const okRead = allRead();
    const okChk = !!chk.checked;

    // Button only enabled when both conditions met
    btn.disabled = !(okRead && okChk);

    if (!okRead) {
      const done = sections.filter(s => state[s.id]?.read).length;
      msg.textContent = `Read each section: ${done}/${sections.length}`;
      return;
    }

    if (!okChk) {
      msg.textContent = 'Please tick the box to continue.';
      return;
    }

    msg.textContent = '';
  }

  function markOpened(id) {
    if (!state[id]) return;
    state[id].opened = true;
    activeId = id;
    updateTocUI();
    updateUI();
  }

  function maybeMarkReadToBottom(id) {
    const s = sections.find(x => x.id === id);
    if (!s) return;

    const st = state[id];
    if (!st || st.read) return;

    // We require: user has clicked this section at least once
    if (!st.opened) return;

    // Detect if the scroll container has reached the bottom of this section
    // within the scrollable #terms-content pane.
    const scrollTop = content.scrollTop;
    const viewBottom = scrollTop + content.clientHeight;

    // offsetTop is relative to offsetParent; with our layout, this is fine.
    // Add a small tolerance so they don’t have to land on the exact pixel.
    const sectionBottom = s.el.offsetTop + s.el.offsetHeight;
    const tolerance = 12;

    if (viewBottom >= (sectionBottom - tolerance)) {
      st.read = true;
      updateTocUI();
      updateUI();
    }
  }

  // Wire TOC clicks: must click each section
  tocLinks.forEach(a => {
    a.addEventListener('click', (e) => {
      const href = (a.getAttribute('href') || '').trim();
      if (!href.startsWith('#')) return;

      const id = href.slice(1);
      if (!state[id]) return;

      // Let anchor navigation happen, but ensure “opened” is recorded
      markOpened(id);

      // Small delay so the scroll happens before we test “bottom reached”
      setTimeout(() => maybeMarkReadToBottom(id), 50);
    });
  });

  // Wire scrolling: only counts toward the currently opened section
  content.addEventListener('scroll', () => {
    if (!activeId) return;
    maybeMarkReadToBottom(activeId);
  }, { passive: true });

  // Checkbox changes affect button enablement
  chk.addEventListener('change', () => updateUI());

  // Pull current terms version (existing behavior)
  try {
    const st = await fx('/api/me/tos');
    if (ver) ver.textContent = 'v' + (st.version || '?');
  } catch (e) { /* ignore */ }

  // Accept handler (existing behavior)
  btn.addEventListener('click', async () => {
    updateUI();
    if (btn.disabled) return;

    btn.disabled = true;
    try {
      await fx('/api/me/tos/accept', { method: 'POST', body: JSON.stringify({}) });
      window.location.href = '/';
    } catch (e) {
      msg.textContent = 'Could not record acceptance. Make sure you are logged in with Discord.';
      btn.disabled = false;
    }
  });

  // Initial UI state
  updateTocUI();
  updateUI();
})();
