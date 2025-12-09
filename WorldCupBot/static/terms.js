(async () => {
  'use strict';
  const $ = (s, el=document) => el.querySelector(s);
  async function fx(url, opts){ const r=await fetch(url, Object.assign({ headers:{'Content-Type':'application/json'}}, opts||{})); if(!r.ok) throw new Error(await r.text()); return r.json(); }

  const ver = $('#ver');
  const msg = $('#msg');
  const btn = $('#btn-accept');
  const chk = $('#chk-accept');

  try{
    const st = await fx('/api/me/tos');
    ver.textContent = 'v' + (st.version || '?');
  }catch(e){  }

  btn.addEventListener('click', async () => {
    msg.textContent = '';
    if(!chk.checked){ msg.textContent = 'Please tick the box to continue.'; return; }
    btn.disabled = true;
    try{
      await fx('/api/me/tos/accept', { method:'POST', body: JSON.stringify({}) });
      window.location.href = '/';
    }catch(e){
      msg.textContent = 'Could not record acceptance. Make sure you are logged in with Discord.';
      btn.disabled = false;
    }
  });
})();