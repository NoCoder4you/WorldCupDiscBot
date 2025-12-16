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

  const sectionIds = tocLinks
    .map(a => (a.getAttribute('href') || '').trim())
    .filter(h => h.startsWith('#'))
    .map(h => h.slice(1));

  const sections = sectionIds
    .map(id => ({ id, el: document.getElementById(id) }))
    .filter(x => x.el);

  if (!sections.length) return;

  const state = {};
  sections.forEach(s => state[s.id] = { opened: false, read: false });

  let currentIndex = 0;

  // For short sections: require a real scroll gesture (wheel/touch) while on that section
  let gestureScrollPx = 0;

  const MIN_GESTURE_PX = 120; // must actually scroll input a bit
  const BOTTOM_TOL = 10;

  function allRead() {
    return sections.every(s => state[s.id]?.read);
  }

  function gateIndex() {
    for (let i = 0; i < sections.length; i++) {
      if (!state[sections[i].id]?.read) return i;
    }
    return sections.length;
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
      msg.textContent = `Complete each section: ${done}/${total}`;
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
    gestureScrollPx = 0;

    sections.forEach((s, i) => {
      s.el.style.display = (i === currentIndex) ? '' : 'none';
    });

    requestAnimationFrame(() => {
      content.scrollTop = 0;
      updateTocUI();
      updateUI();
    });
  }

  function markCurrentRead() {
    const s = sections[currentIndex];
    if (!s) return;
    const st = state[s.id];
    if (!st || st.read) return;
    if (!st.opened) return;

    st.read = true;
    updateTocUI();
    updateUI();

    const gate = gateIndex();
    if (gate < sections.length) {
      msg.textContent = `Section completed. Click the next section. (${sections.filter(x => state[x.id].read).length}/${sections.length})`;
    }
  }

  function currentNeedsScroll() {
    // If scrollHeight > clientHeight, there is content to scroll
    return content.scrollHeight > (content.clientHeight + 2);
  }

  function isAtBottom() {
    return (content.scrollTop + content.clientHeight) >= (content.scrollHeight - BOTTOM_TOL);
  }

  function maybeCompleteByScroll() {
    const s = sections[currentIndex];
    if (!s) return;
    const st = state[s.id];
    if (!st || st.read || !st.opened) return;

    if (currentNeedsScroll()) {
      // Normal case: must scroll to bottom
      if (isAtBottom()) markCurrentRead();
    } else {
      // Short section: no bottom to reach, so require real scroll gesture input
      if (gestureScrollPx >= MIN_GESTURE_PX) markCurrentRead();
    }
  }

  // Track scroll gestures (no time, no whitespace)
  content.addEventListener('wheel', (e) => {
    gestureScrollPx += Math.abs(e.deltaY || 0);
    maybeCompleteByScroll();
  }, { passive: true });

  let touchY = null;
  content.addEventListener('touchstart', (e) => {
    if (!e.touches || !e.touches.length) return;
    touchY = e.touches[0].clientY;
  }, { passive: true });

  content.addEventListener('touchmove', (e) => {
    if (touchY == null || !e.touches || !e.touches.length) return;
    const y = e.touches[0].clientY;
    gestureScrollPx += Math.abs(y - touchY);
    touchY = y;
    maybeCompleteByScroll();
  }, { passive: true });

  // Also react to actual scroll position for long sections
  content.addEventListener('scroll', () => {
    maybeCompleteByScroll();
  }, { passive: true });

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

  chk.addEventListener('change', () => updateUI());

  try {
    const st = await fx('/api/me/tos');
    if (ver) ver.textContent = 'v' + (st.version || '?');
  } catch (e) { /* ignore */ }

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

  btn.disabled = true;
  showOnly(0);
  updateUI();
})();
