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

  // Build ordered sections from TOC
  const sectionIds = tocLinks
    .map(a => (a.getAttribute('href') || '').trim())
    .filter(h => h.startsWith('#'))
    .map(h => h.slice(1));

  const sections = sectionIds
    .map(id => ({ id, el: document.getElementById(id) }))
    .filter(x => x.el);

  if (!sections.length) return;

  const state = {};
  sections.forEach(s => state[s.id] = { opened: false, read: false, maxScrollTop: 0 });

  let currentIndex = 0;
  const MIN_SCROLL_PX = 60;     // must actually scroll, not just "already at bottom"
  const BOTTOM_TOL = 12;

  // ---- helpers ----
  function allRead() {
    return sections.every(s => state[s.id]?.read);
  }

  function gateIndex() {
    for (let i = 0; i < sections.length; i++) {
      if (!state[sections[i].id]?.read) return i;
    }
    return sections.length;
  }

  function removeScrollPad() {
    const old = content.querySelector('.terms-scrollpad');
    if (old) old.remove();
  }

  function ensureScrollPad() {
    // Always ensure there is something to scroll through, even for short sections.
    removeScrollPad();
    const s = sections[currentIndex];
    if (!s) return;

    const pad = document.createElement('div');
    pad.className = 'terms-scrollpad';
    pad.setAttribute('aria-hidden', 'true');
    s.el.appendChild(pad);

    // Set height based on viewport so every section requires scrolling.
    requestAnimationFrame(() => {
      const h = Math.max(220, Math.floor(content.clientHeight * 0.8));
      pad.style.height = `${h}px`;
    });
  }

  function showOnly(index) {
    currentIndex = Math.max(0, Math.min(index, sections.length - 1));

    sections.forEach((s, i) => {
      s.el.style.display = (i === currentIndex) ? '' : 'none';
    });

    // reset scroll tracking for the newly opened section
    const sid = sections[currentIndex].id;
    state[sid].maxScrollTop = 0;

    requestAnimationFrame(() => {
      content.scrollTop = 0;
      ensureScrollPad();
      updateTocUI();
      updateUI();
    });
  }

  function updateTocUI() {
    const gate = gateIndex();

    tocLinks.forEach((a, i) => {
      const id = sectionIds[i];
      const st = state[id];

      const locked = i > gate;
      const cur = i === currentIndex;
      const read = !!st?.read;

      a.classList.toggle('toc-locked', locked);
      a.classList.toggle('toc-current', cur);
      a.classList.toggle('toc-read', read);

      a.style.pointerEvents = locked ? 'none' : '';
      a.style.opacity = locked ? '0.45' : '';
      a.setAttribute('aria-disabled', locked ? 'true' : 'false');
    });
  }

  function updateUI() {
    const done = sections.filter(s => state[s.id]?.read).length;
    const total = sections.length;

    if (!allRead()) {
      btn.disabled = true;

      const sid = sections[currentIndex]?.id;
      const st = sid ? state[sid] : null;

      if (st && !st.opened) {
        msg.textContent = `Click this section in the contents to begin. (${done}/${total})`;
      } else {
        msg.textContent = `Scroll to the bottom to mark this section as read. (${done}/${total})`;
      }
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

  function markCurrentReadIfEligible() {
    const s = sections[currentIndex];
    if (!s) return;

    const st = state[s.id];
    if (!st || st.read) return;

    // Must have opened via click
    if (!st.opened) return;

    // Must have scrolled a little
    st.maxScrollTop = Math.max(st.maxScrollTop, content.scrollTop);
    if (st.maxScrollTop < MIN_SCROLL_PX) return;

    // Must be at bottom of scroll pane
    const atBottom = (content.scrollTop + content.clientHeight) >= (content.scrollHeight - BOTTOM_TOL);
    if (!atBottom) return;

    st.read = true;
    updateTocUI();
    updateUI();

    // Do NOT auto-advance - they must click the next section.
    const gate = gateIndex();
    if (gate < sections.length) {
      msg.textContent = `Section completed. Click the next section in the contents. (${sections.filter(x => state[x.id].read).length}/${sections.length})`;
    }
  }

  // ---- TOC click behaviour: must click each section ----
  tocLinks.forEach((a, i) => {
    a.addEventListener('click', (e) => {
      e.preventDefault();
      const gate = gateIndex();
      if (i > gate) return;

      const id = sectionIds[i];
      if (!state[id]) return;

      state[id].opened = true;
      showOnly(i);
    });
  });

  // ---- Scroll behaviour: marks read only by scrolling to bottom ----
  content.addEventListener('scroll', () => {
    markCurrentReadIfEligible();
  }, { passive: true });

  // checkbox affects final accept
  chk.addEventListener('change', () => updateUI());

  // Version fetch unchanged
  try {
    const st = await fx('/api/me/tos');
    if (ver) ver.textContent = 'v' + (st.version || '?');
  } catch (e) { /* ignore */ }

  // Accept unchanged
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

  // Init: show first section, but it will not count unless they click it in TOC
  btn.disabled = true;
  showOnly(0);
  updateUI();
})();
