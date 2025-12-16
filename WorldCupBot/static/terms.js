(async () => {
  'use strict';

  /* ========= Helpers ========= */
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));

  async function fx(url, opts) {
    const r = await fetch(
      url,
      Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts || {})
    );
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }

  /* ========= Elements ========= */
  const ver = $('#ver');
  const msg = $('#msg');
  const btnAccept = $('#btn-accept');
  const chkAccept = $('#chk-accept');

  const content = $('#terms-content');
  const tocLinks = $$('.terms-toc .toc-link');

  const welcome = $('#welcome-overlay');
  const btnWelcome = $('#btn-welcome-continue');

  if (!msg || !btnAccept || !chkAccept || !content || !tocLinks.length) return;

  /* ========= Welcome Overlay ========= */
  if (welcome && btnWelcome) {
    btnWelcome.addEventListener('click', () => {
      welcome.style.display = 'none';
      content.focus();
    });
  }

  /* ========= Build Sections from TOC ========= */
  const sectionIds = tocLinks
    .map(a => (a.getAttribute('href') || '').trim())
    .filter(h => h.startsWith('#'))
    .map(h => h.slice(1));

  const sections = sectionIds
    .map(id => ({ id, el: document.getElementById(id) }))
    .filter(x => x.el);

  if (!sections.length) return;

  /* ========= State ========= */
  const state = {};
  sections.forEach(s => {
    state[s.id] = {
      opened: false,
      read: false,
      gesturePx: 0
    };
  });

  let currentIndex = 0;

  const MIN_GESTURE_PX = 120; // required scroll input for short sections
  const BOTTOM_TOL = 10;

  /* ========= Helpers ========= */
  function allRead() {
    return sections.every(s => state[s.id].read);
  }

  function gateIndex() {
    for (let i = 0; i < sections.length; i++) {
      if (!state[sections[i].id].read) return i;
    }
    return sections.length;
  }

  function needsScroll() {
    return content.scrollHeight > (content.clientHeight + 2);
  }

  function atBottom() {
    return (content.scrollTop + content.clientHeight) >= (content.scrollHeight - BOTTOM_TOL);
  }

  function updateTocUI() {
    const gate = gateIndex();

    tocLinks.forEach((a, i) => {
      const id = sectionIds[i];
      const st = state[id];

      const locked = i > gate;
      const current = i === currentIndex;

      a.classList.toggle('toc-locked', locked);
      a.classList.toggle('toc-current', current);
      a.classList.toggle('toc-read', st.read);

      a.style.pointerEvents = locked ? 'none' : '';
      a.style.opacity = locked ? '0.45' : '';
      a.setAttribute('aria-disabled', locked ? 'true' : 'false');
    });
  }

  function updateUI() {
    const done = sections.filter(s => state[s.id].read).length;
    const total = sections.length;

    if (!allRead()) {
      btnAccept.disabled = true;

      const cur = sections[currentIndex];
      const st = state[cur.id];

      if (!st.opened) {
        msg.textContent = `Click this section to begin. (${done}/${total})`;
      } else {
        msg.textContent = `Scroll to the bottom to complete this section. (${done}/${total})`;
      }
      return;
    }

    if (!chkAccept.checked) {
      btnAccept.disabled = true;
      msg.textContent = 'Please tick the box to continue.';
      return;
    }

    msg.textContent = '';
    btnAccept.disabled = false;
  }

  function showOnly(index) {
    currentIndex = Math.max(0, Math.min(index, sections.length - 1));

    sections.forEach((s, i) => {
      s.el.style.display = (i === currentIndex) ? '' : 'none';
    });

    const st = state[sections[currentIndex].id];
    st.gesturePx = 0;

    requestAnimationFrame(() => {
      content.scrollTop = 0;
      updateTocUI();
      updateUI();
    });
  }

  function markCurrentRead() {
    const s = sections[currentIndex];
    const st = state[s.id];

    if (st.read) return;
    if (!st.opened) return;

    st.read = true;
    updateTocUI();
    updateUI();

    const gate = gateIndex();
    if (gate < sections.length) {
      msg.textContent =
        `Section completed. Click the next section. (${sections.filter(x => state[x.id].read).length}/${sections.length})`;
    }
  }

  function maybeCompleteByScroll() {
    const s = sections[currentIndex];
    const st = state[s.id];

    if (st.read || !st.opened) return;

    if (needsScroll()) {
      if (atBottom()) markCurrentRead();
    } else {
      if (st.gesturePx >= MIN_GESTURE_PX) markCurrentRead();
    }
  }

  /* ========= Scroll / Gesture Tracking ========= */
  content.addEventListener('scroll', () => {
    maybeCompleteByScroll();
  }, { passive: true });

  content.addEventListener('wheel', (e) => {
    state[sections[currentIndex].id].gesturePx += Math.abs(e.deltaY || 0);
    maybeCompleteByScroll();
  }, { passive: true });

  let touchY = null;
  content.addEventListener('touchstart', (e) => {
    if (e.touches && e.touches.length) {
      touchY = e.touches[0].clientY;
    }
  }, { passive: true });

  content.addEventListener('touchmove', (e) => {
    if (!touchY || !e.touches || !e.touches.length) return;
    const y = e.touches[0].clientY;
    state[sections[currentIndex].id].gesturePx += Math.abs(y - touchY);
    touchY = y;
    maybeCompleteByScroll();
  }, { passive: true });

  /* ========= TOC Clicks ========= */
  tocLinks.forEach((a, i) => {
    a.addEventListener('click', (e) => {
      e.preventDefault();
      const gate = gateIndex();
      if (i > gate) return;

      const id = sectionIds[i];
      state[id].opened = true;
      showOnly(i);
    });
  });

  /* ========= Checkbox ========= */
  chkAccept.addEventListener('change', () => updateUI());

  /* ========= Version ========= */
  try {
    const st = await fx('/api/me/tos');
    if (ver) ver.textContent = 'v' + (st.version || '?');
  } catch (e) { /* ignore */ }

  /* ========= Accept ========= */
  btnAccept.addEventListener('click', async () => {
    updateUI();
    if (btnAccept.disabled) return;

    btnAccept.disabled = true;
    try {
      await fx('/api/me/tos/accept', {
        method: 'POST',
        body: JSON.stringify({})
      });
      window.location.href = '/';
    } catch (e) {
      msg.textContent =
        'Could not record acceptance. Make sure you are logged in with Discord.';
      btnAccept.disabled = false;
    }
  });

  /* ========= Init ========= */
  btnAccept.disabled = true;
  showOnly(0);
  updateUI();
})();
