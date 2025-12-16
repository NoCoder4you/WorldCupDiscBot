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
      msg.textContent = `Scroll to the bottom of each section to unlock the next: ${done}/${sections.length}`;
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

  function removePads() {
    sections.forEach(s => {
      const pad = s.el.querySelector('.read-pad');
      if (pad) pad.remove();
    });
  }

  // Force scrolling even for short sections by adding an invisible pad at the end
  function ensurePadForCurrent() {
    const s = sections[currentIndex];
    if (!s) return;

    // remove pads from other sections
    removePads();

    // add pad only to visible section
    const pad = document.createElement('div');
    pad.className = 'read-pad';
    // Big enough to force scrolling but visually invisible
    pad.style.height = '70vh';
    pad.style.pointerEvents = 'none';
    pad.style.opacity = '0';
    s.el.appendChild(pad);
  }

  function showOnly(index) {
    currentIndex = Math.max(0, Math.min(index, sections.length - 1));

    sections.forEach((s, i) => {
      s.el.style.display = (i === currentIndex) ? '' : 'none';
    });

    // force scroll requirement
    ensurePadForCurrent();

    // reset scroll
    requestAnimationFrame(() => { content.scrollTop = 0; });

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

  function maybeMarkCurrentReadByScroll() {
    const tolerance = 12;
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
