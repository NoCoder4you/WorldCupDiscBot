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

  if (!msg || !btn || !chk || !content || !tocLinks.length) return;

  // ---- Build ordered section list from TOC ----
  const sectionIds = tocLinks
    .map(a => (a.getAttribute('href') || '').trim())
    .filter(h => h.startsWith('#'))
    .map(h => h.slice(1));

  const sections = sectionIds
    .map(id => ({ id, el: document.getElementById(id) }))
    .filter(x => x.el);

  if (!sections.length) return;

  // ---- State ----
  const state = {};
  sections.forEach(s => state[s.id] = { read: false });

  let currentIndex = 0; // only one section visible at a time

  // ---- Helpers ----
  function showOnly(index) {
    currentIndex = Math.max(0, Math.min(index, sections.length - 1));

    sections.forEach((s, i) => {
      s.el.style.display = (i === currentIndex) ? '' : 'none';
    });

    // ensure the visible section starts at the top of scroll pane
    content.scrollTop = 0;

    updateTocUI();
    updateUI();
  }

  function unlockableIndex() {
    // first unread section index is the next one they must read
    for (let i = 0; i < sections.length; i++) {
      if (!state[sections[i].id].read) return i;
    }
    return sections.length; // all read
  }

  function updateTocUI() {
    const gate = unlockableIndex();

    tocLinks.forEach((a, i) => {
      const id = sectionIds[i];
      const isCurrent = (i === currentIndex);
      const isRead = !!state[id]?.read;

      // lock anything beyond the next required section
      const locked = i > gate;

      a.classList.toggle('toc-current', isCurrent);
      a.classList.toggle('toc-read', isRead);
      a.classList.toggle('toc-locked', locked);

      a.setAttribute('aria-disabled', locked ? 'true' : 'false');
      a.style.pointerEvents = locked ? 'none' : '';
      a.style.opacity = locked ? '0.45' : '';
    });
  }

  function allRead() {
    return sections.every(s => state[s.id]?.read);
  }

  function updateUI() {
    const done = sections.filter(s => state[s.id]?.read).length;

    if (!allRead()) {
      btn.disabled = true;
      msg.textContent = `Read each section to unlock the next: ${done}/${sections.length}`;
      return;
    }

    if (!chk.checked) {
      btn.disabled = true;
      msg.textContent = 'Please tick the box to continue.';
      return;
    }

    msg.textContent = '';
    btn.disabled = false;
  }

  function maybeMarkCurrentRead() {
    const s = sections[currentIndex];
    if (!s) return;

    // already marked
    if (state[s.id].read) return;

    // user must scroll to bottom of the scroll pane (since only one section is visible)
    const tolerance = 8;
    const atBottom = (content.scrollTop + content.clientHeight) >= (content.scrollHeight - tolerance);

    if (atBottom) {
      state[s.id].read = true;

      // auto-advance to next section if any
      if (currentIndex < sections.length - 1) {
        showOnly(currentIndex + 1);
      } else {
        // last section read
        updateTocUI();
        updateUI();
      }
    }
  }

  // ---- Wire scrolling: scrolling to bottom marks current section read ----
  content.addEventListener('scroll', () => {
    maybeMarkCurrentRead();
  }, { passive: true });

  // ---- Wire TOC clicks: can only open up to the current gate ----
  tocLinks.forEach((a, i) => {
    a.addEventListener('click', (e) => {
      e.preventDefault();
      const gate = unlockableIndex();
      if (i > gate) return; // locked
      showOnly(i);
    });
  });

  // ---- Checkbox controls final accept ----
  chk.addEventListener('change', () => updateUI());

  // ---- Version fetch (existing behavior) ----
  try {
    const st = await fx('/api/me/tos');
    if (ver) ver.textContent = 'v' + (st.version || '?');
  } catch (e) { /* ignore */ }

  // ---- Accept (existing behavior) ----
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

  // ---- Init: show first section only; lock the rest until read ----
  btn.disabled = true;
  showOnly(0);
})();
