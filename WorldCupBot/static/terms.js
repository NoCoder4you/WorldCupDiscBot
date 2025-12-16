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

  // State: must click each section + scroll (gesture) + bottom reached
  const state = {};
  sections.forEach(s => state[s.id] = { opened: false, scrolled: false, read: false });

  let currentIndex = 0;

  function allRead() {
    return sections.every(s => state[s.id]?.read);
  }

  // The next section they’re allowed to open (first unread)
  function gateIndex() {
    for (let i = 0; i < sections.length; i++) {
      if (!state[sections[i].id].read) return i;
    }
    return sections.length;
  }

  function updateTocUI() {
    const gate = gateIndex();

    tocLinks.forEach((a, i) => {
      const id = sectionIds[i];
      const st = state[id];
      if (!st) return;

      const locked = i > gate;
      const current = i === currentIndex;

      a.classList.toggle('toc-locked', locked);
      a.classList.toggle('toc-current', current);
      a.classList.toggle('toc-read', !!st.read);

      a.setAttribute('aria-disabled', locked ? 'true' : 'false');
      a.style.pointerEvents = locked ? 'none' : '';
      a.style.opacity = locked ? '0.45' : '';
    });
  }

  function updateUI() {
    if (!allRead()) {
      const done = sections.filter(s => state[s.id]?.read).length;
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

  function showOnly(index) {
    currentIndex = Math.max(0, Math.min(index, sections.length - 1));

    sections.forEach((s, i) => {
      s.el.style.display = (i === currentIndex) ? '' : 'none';
    });

    const id = sections[currentIndex].id;
    state[id].opened = true;

    // Reset scroll to top and reset "scrolled" requirement for this section
    content.scrollTop = 0;
    state[id].scrolled = false;

    updateTocUI();
    updateUI();
  }

  function markScrolledForCurrent() {
    const id = sections[currentIndex].id;
    if (!state[id]) return;
    state[id].scrolled = true;
  }

  function atBottom() {
    const tol = 12;
    return (content.scrollTop + content.clientHeight) >= (content.scrollHeight - tol);
  }

  function tryCompleteCurrent() {
    const id = sections[currentIndex].id;
    const st = state[id];
    if (!st || st.read) return;

    // Must have clicked/opened this section
    if (!st.opened) return;

    // Must have performed a downward scroll gesture on this section
    if (!st.scrolled) return;

    // Must be at bottom (or content fits; still requires scroll gesture)
    if (!atBottom()) return;

    st.read = true;

    // Auto-advance to next section if any
    if (currentIndex < sections.length - 1) {
      showOnly(currentIndex + 1);
    } else {
      updateTocUI();
      updateUI();
    }
  }

  // TOC click: only allow up to gate
  tocLinks.forEach((a, i) => {
    a.addEventListener('click', (e) => {
      e.preventDefault();
      const gate = gateIndex();
      if (i > gate) return;
      showOnly(i);
    });
  });

  // Scroll events inside the terms pane
  content.addEventListener('scroll', () => {
    // If they actually moved down, that counts as a scroll gesture
    if (content.scrollTop > 0) markScrolledForCurrent();
    tryCompleteCurrent();
  }, { passive: true });

  // Wheel/trackpad scroll gesture (counts even if section doesn't overflow)
  content.addEventListener('wheel', (e) => {
    if (e.deltaY > 0) {
      markScrolledForCurrent();
      // If section fits (no scroll), scroll event won't fire - so attempt completion here
      tryCompleteCurrent();
    }
  }, { passive: true });

  // Touch scroll gesture (mobile)
  let touchStartY = null;
  content.addEventListener('touchstart', (e) => {
    const t = e.touches && e.touches[0];
    touchStartY = t ? t.clientY : null;
  }, { passive: true });

  content.addEventListener('touchmove', (e) => {
    const t = e.touches && e.touches[0];
    if (touchStartY != null && t && (touchStartY - t.clientY) > 4) {
      // finger moved up = content scroll down
      markScrolledForCurrent();
      tryCompleteCurrent();
    }
  }, { passive: true });

  chk.addEventListener('change', () => updateUI());

  // Version fetch (unchanged)
  try {
    const st = await fx('/api/me/tos');
    if (ver) ver.textContent = 'v' + (st.version || '?');
  } catch (e) { /* ignore */ }

  // Accept (unchanged)
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

  // Init
  btn.disabled = true;
  showOnly(0);
})();
