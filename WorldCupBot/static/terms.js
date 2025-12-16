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
  sections.forEach(s => state[s.id] = { read: false });

  let currentIndex = 0;
  let activeTimer = null;

  function allRead() {
    return sections.every(s => state[s.id]?.read);
  }

  function unlockableIndex() {
    for (let i = 0; i < sections.length; i++) {
      if (!state[sections[i].id].read) return i;
    }
    return sections.length;
  }

  function updateTocUI() {
    const gate = unlockableIndex();

    tocLinks.forEach((a, i) => {
      const id = sectionIds[i];
      const isCurrent = (i === currentIndex);
      const isRead = !!state[id]?.read;
      const locked = i > gate;

      a.classList.toggle('toc-current', isCurrent);
      a.classList.toggle('toc-read', isRead);
      a.classList.toggle('toc-locked', locked);

      a.setAttribute('aria-disabled', locked ? 'true' : 'false');
      a.style.pointerEvents = locked ? 'none' : '';
      a.style.opacity = locked ? '0.45' : '';
    });
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

  function clearActiveTimer() {
    if (activeTimer) {
      clearTimeout(activeTimer);
      activeTimer = null;
    }
  }

  function showOnly(index) {
    clearActiveTimer();

    currentIndex = Math.max(0, Math.min(index, sections.length - 1));

    sections.forEach((s, i) => {
      s.el.style.display = (i === currentIndex) ? '' : 'none';
    });

    // reset scroll to top (do after layout)
    requestAnimationFrame(() => {
      content.scrollTop = 0;
      setupShortSectionGuard();
    });

    updateTocUI();
    updateUI();
  }

  function markReadAndAdvance() {
    const s = sections[currentIndex];
    if (!s) return;
    if (state[s.id].read) return;

    state[s.id].read = true;

    if (currentIndex < sections.length - 1) {
      showOnly(currentIndex + 1);
    } else {
      updateTocUI();
      updateUI();
    }
  }

  // If a section fits without scrolling, don't insta-skip it.
  // Require a small "dwell time" before unlocking next.
  function setupShortSectionGuard() {
    const tolerance = 12;
    const maxScroll = content.scrollHeight - content.clientHeight;

    // Needs scrolling
    if (maxScroll > tolerance) return;

    // No scrolling possible - require time spent on section
    const minMs = 2500; // 2.5s per short section (tweak if you want)
    activeTimer = setTimeout(() => {
      markReadAndAdvance();
    }, minMs);
  }

  // Scroll-to-bottom detection for sections that do require scrolling
  function maybeMarkCurrentReadByScroll() {
    clearActiveTimer(); // if they can scroll, time guard no longer needed

    const tolerance = 12;
    const maxScroll = content.scrollHeight - content.clientHeight;

    // If there's nothing to scroll, do not mark read here (timer handles it)
    if (maxScroll <= tolerance) return;

    const atBottom = (content.scrollTop + content.clientHeight) >= (content.scrollHeight - tolerance);
    if (atBottom) markReadAndAdvance();
  }

  content.addEventListener('scroll', () => {
    maybeMarkCurrentReadByScroll();
  }, { passive: true });

  tocLinks.forEach((a, i) => {
    a.addEventListener('click', (e) => {
      e.preventDefault();
      const gate = unlockableIndex();
      if (i > gate) return;
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
})();
