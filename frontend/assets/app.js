'use strict';

const $ = (selector, parent = document) => parent.querySelector(selector);
const isTools = $('meta[name="tinytune-surface"]').content === 'tools';
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const e = escapeHTML;
const number = (value, digits = 0) => value == null ? '—' : Number(value).toLocaleString(undefined, {maximumFractionDigits: digits});
const state = {user:null, config:null, playlists:[], view:'library', query:'', filter:'all', playlist:null, stats:null,
  console:null, run:null, history:[], monitorSamples:[], pollBusy:false, authMode:'signin', selectedCover:0};
const iconPaths = {
  music:'<path d="M9 18V5l12-2v13M9 9l12-2"/><ellipse cx="5" cy="18" rx="4" ry="3"/><ellipse cx="17" cy="16" rx="4" ry="3"/>',
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  heart:'<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/>',
  chart:'<path d="M3 3v18h18M7 14l4-5 4 3 5-8"/>',
  arrow:'<path d="M5 12h14m-6-6 6 6-6 6"/>',
  back:'<path d="M19 12H5m6-6-6 6 6 6"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  chevron:'<path d="m8 10 4 4 4-4"/>',
  external:'<path d="M14 3h7v7m0-7L10 14M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"/>',
  code:'<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18"/>',
  play:'<path d="m8 4 13 8-13 8Z"/>',
  share:'<path d="M12 16V3m-5 5 5-5 5 5M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>',
  check:'<path d="m5 12 4 4 10-10"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  logout:'<path d="M9 5H4v14h5m5-14 7 7-7 7M8 12h13"/>',
  download:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  stop:'<rect x="5" y="5" width="14" height="14" rx="2"/>',
  pulse:'<path d="M2 12h5l3-8 4 16 3-8h5"/>',
  server:'<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.01M7 17.5h.01"/>',
};
const icon = (name, small = false) => `<svg class="icon${small?' small':''}" viewBox="0 0 24 24" aria-hidden="true">${iconPaths[name] || iconPaths.music}</svg>`;
const brand = () => `<a href="/" class="brand" aria-label="TinyTune home"><span class="brand-mark">♫</span><span>tiny<em>tune</em></span></a>`;

function cover(value) {
  const variant = Math.abs(Number(value) || 0) % 6;
  const art = [
    `<rect width="300" height="300" fill="#233e43"/><circle cx="221" cy="71" r="48" fill="#e9d1a8"/><path d="M-30 210Q80 60 180 160T340 110V320H-30Z" fill="#476a68"/><path d="M-20 265Q95 120 220 230T340 190V320H-20Z" fill="#6c8b79"/><path d="M-20 300Q100 200 310 290V320H-20Z" fill="#a0b292"/><path d="M27 25h28m-28 0v28m246 221h-28m28 0v-28" stroke="#dbdcb455" fill="none"/>`,
    `<rect width="300" height="300" fill="#d5d9b4"/><circle cx="150" cy="150" r="102" fill="#7f9067"/><path d="M48 150h204M60 101h180M60 199h180M92 63h116M92 237h116" stroke="#dce0c0" stroke-width="17"/><path d="m50 280 200-260" stroke="#bdad6c" stroke-width="31"/><circle cx="150" cy="150" r="21" fill="#f0e6bb"/>`,
    `<rect width="300" height="300" fill="#e9b3a1"/><circle cx="150" cy="139" r="85" fill="#ba6b51"/><path d="M0 202h300v98H0Z" fill="#eac9b2"/><path d="M0 218h300M0 245h300M0 277h300M75 202 23 300m95-98-18 98m82-98 18 98m42-98 52 98" stroke="#ca9279" fill="none"/><path d="M25 29h37m-37 7h22" stroke="#b7775d"/>`,
    `<rect width="300" height="300" fill="#718bba"/><circle cx="220" cy="80" r="45" fill="#e5e1a6"/><path d="M0 175Q80 122 150 180T300 142V300H0Z" fill="#c6d0a8"/><path d="M0 231Q70 174 159 240T300 206V300H0Z" fill="#436a5e"/><path d="M156 300Q242 205 150 179" fill="none" stroke="#e8dfb8" stroke-width="23"/>`,
    `<rect width="300" height="300" fill="#b7a7c9"/><path d="M40 260V131a110 110 0 0 1 220 0v129" stroke="#776386" stroke-width="40" fill="none"/><path d="M102 260V139a48 48 0 0 1 96 0v121" fill="#e1cdb6"/><circle cx="150" cy="148" r="23" fill="#ad826b"/>`,
    `<rect width="300" height="300" fill="#d5b879"/><path d="m0 100 150-80 150 80-150 80Z" fill="#f0dfad"/><path d="m0 170 150-80 150 80-150 80Z" fill="#90794c"/><path d="m0 240 150-80 150 80-150 80Z" fill="#405a4a"/><circle cx="150" cy="230" r="23" fill="#dfbc7e"/>`,
  ][variant];
  return `<svg class="cover-svg" viewBox="0 0 300 300" preserveAspectRatio="xMidYMid slice" aria-hidden="true">${art}<text x="23" y="281" fill="#fff8ddaa" font-family="sans-serif" font-size="8" letter-spacing="3">TINY TUNE / VOL. 0${variant+1}</text></svg>`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {credentials:isTools?'omit':'same-origin', ...options,
    headers:{'Content-Type':'application/json','X-TinyTune-Request':'1', ...options.headers}});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map(v => v.msg).join('. ') : data.detail;
    const error = new Error(detail || `Request failed (${response.status})`);
    error.status = response.status;
    if(response.status===401 && !isTools && state.user && !path.startsWith('/auth/')) {
      state.user=null; state.playlists=[]; state.playlist=null; if($('#modal').open)closeModal(); renderAuth();
    }
    throw error;
  }
  return data;
}
const post = (path, data = {}) => api(path, {method:'POST', body:JSON.stringify(data)});
let toastTimer;
function toast(message, error = false) {
  const element = $('#toast'); element.textContent = message; element.className = `visible${error?' error':''}`;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => {element.className = '';}, 5000);
}
function showModal(title, content) {
  const modal = $('#modal');
  modal.innerHTML = `<div class="modal-heading"><h2 id="modal-title">${e(title)}</h2><button class="icon-button" data-action="close-modal" aria-label="Close dialog">${icon('close')}</button></div>${content}`;
  modal.showModal();
}
function closeModal() { $('#modal').close(); }

function renderAuth() {
  $('#app').innerHTML = `<div class="auth-shell"><section class="auth-story">${brand()}
    <div class="auth-headline"><div class="eyebrow" style="color:#a5bb94">SMALL PLAYLISTS. BIG FEELINGS.</div><h1>Good music.<br>Better <em>company.</em></h1><p>A little space for the songs that mean something. Make a playlist, pass it around, find your people.</p></div>
    <div class="auth-art" aria-hidden="true"><div class="record"></div></div><div class="auth-footer"><span>Made for the love of a good playlist.</span><span>EST. 2026</span></div></section>
    <section class="auth-form-side"><div class="auth-box"><div class="auth-tabs" role="tablist" aria-label="Account access"><button class="auth-tab ${state.authMode==='signin'?'active':''}" role="tab" aria-selected="${state.authMode==='signin'}" data-action="auth-tab" data-mode="signin">Sign in</button><button class="auth-tab ${state.authMode==='signup'?'active':''}" role="tab" aria-selected="${state.authMode==='signup'}" data-action="auth-tab" data-mode="signup">Create an account</button></div>
    <div class="eyebrow">YOUR SOUNDTRACK STARTS HERE</div><h2>${state.authMode==='signin'?'Welcome to your rhythm.':'Make yourself at home.'}</h2><p class="intro">${state.authMode==='signin'?'Sign in to your private library and the playlists shared with you.':'Create your account. Your playlists stay private until you choose who to share with.'}</p>
    <form id="auth-form" class="customer-auth-form">
      ${state.authMode==='signup'?'<label for="account-name">Your name</label><input id="account-name" name="name" autocomplete="name" required maxlength="80" placeholder="What should we call you?">':''}
      <label for="account-username">Username</label><input id="account-username" name="username" autocomplete="username" autocapitalize="none" spellcheck="false" required minlength="3" maxlength="32" pattern="[A-Za-z][A-Za-z0-9_]{2,31}" placeholder="your_username">
      ${state.authMode==='signup'?'<p class="field-hint">3–32 characters. Letters, numbers and underscores. Friends use this to share with you.</p>':''}
      <label for="account-password">Password</label><div class="password-field"><input id="account-password" name="password" type="password" autocomplete="${state.authMode==='signup'?'new-password':'current-password'}" required minlength="${state.authMode==='signup'?12:1}" maxlength="128" placeholder="${state.authMode==='signup'?'At least 12 characters':'Your password'}"><button class="text-button" type="button" data-action="toggle-password" aria-label="Show password">Show</button></div>
      <div id="auth-error" class="auth-error" role="alert"></div><button class="button primary" type="submit">${state.authMode==='signup'?'Create account':'Sign in'} ${icon('arrow',true)}</button>
    </form><div class="divider">or use Google</div>
    <div id="google-button" class="google-slot">${!state.config?.google_client_id?`<button class="google-disabled" data-action="google-help"><span class="google-logo" aria-hidden="true">G</span>Continue with Google</button>`:''}</div>
    <p id="google-hint" class="google-hint">${state.config?.google_client_id?'Secure sign-in, powered by Google.':'Google sign-in awaits a client ID. View setup ↗'}</p>
    <div class="auth-fineprint">${icon('check',true)} Private by default. Shared only with the people you choose.</div></div></section></div>`;
  mountGoogle();
}

let googleScript;
async function mountGoogle() {
  if (!state.config?.google_client_id) return;
  try {
    if (!googleScript) googleScript = new Promise((resolve, reject) => {
      const script = document.createElement('script'); script.src = 'https://accounts.google.com/gsi/client'; script.async = true;
      script.onload = resolve; script.onerror = () => reject(new Error('Google could not load. Check your connection.')); document.head.appendChild(script);
    });
    await googleScript;
    if (state.user || !$('#google-button')) return;
    window.google.accounts.id.initialize({client_id:state.config.google_client_id, nonce:state.config.nonce, ux_mode:'popup',
      callback:async result => {
        try {
          const data = await post('/auth/google', {credential:result.credential}); state.user = data.user; await enterApp();
        } catch (error) {
          toast(error.message, true);
          state.config = await api('/auth/config'); renderAuth();
        }
      }});
    window.google.accounts.id.renderButton($('#google-button'), {type:'standard', theme:'outline', size:'large',
      shape:'rectangular', text:state.authMode==='signup'?'signup_with':'signin_with', width:Math.min(350, $('.auth-box').clientWidth)});
  } catch(error) { $('#google-hint').textContent = error.message; }
}

function googleHelp() {
  showModal('Connect Google', `<div class="help-box"><p>Google sign-in and sign-up use the same verified identity flow. A new account is created automatically on the first sign-in.</p><ol><li>Create an OAuth client of type <strong>Web application</strong> in <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener noreferrer">Google Cloud Console ↗</a>.</li><li>Add <code>http://localhost</code> and <code>http://localhost:8080</code> as authorized JavaScript origins. If the consent screen is in testing, add your Google account as a test user.</li><li>Set <code>GOOGLE_CLIENT_ID</code> in TinyTune’s <code>.env</code>. No client secret is needed for this flow.</li><li>Run <code>docker compose up -d --force-recreate api</code>, then refresh this page.</li></ol><p>The app verifies Google's token on the server and uses an HttpOnly session cookie. Google requires an internet connection; the local demo runs without one.</p></div><div class="form-actions"><button class="button primary" data-action="close-modal">Got it</button></div>`);
}

function renderShell() {
  const name = state.user.name || 'Listener';
  const initials = name.split(' ').slice(0,2).map(word => word[0]).join('').toUpperCase();
  $('#app').innerHTML = `<div class="layout"><aside class="sidebar">${brand()}<nav aria-label="Main navigation"><div class="nav-caption">YOUR SPACE</div>
    <button class="nav-item" data-action="nav" data-view="library">${icon('grid')}<span>Your library</span><span class="count" id="library-count">${state.playlists.length}</span></button>
    <button class="nav-item" data-action="nav" data-view="shared">${icon('share')}<span>Shared with me</span></button><button class="nav-item" data-action="nav" data-view="favorites">${icon('heart')}<span>Favorites</span></button></nav>
    <div class="sidebar-bottom"><div class="local-card"><strong>${icon('check',true)} Yours, until you share it.</strong>Your library is private. Invite a friend by username to let them in.</div><div class="sidebar-footer"><span>TinyTune v1.2</span><span>@${e(state.user.username)}</span></div></div></aside>
    <main class="main"><header class="topbar"><div class="mobile-brand">${brand()}</div><label class="search">${icon('search')}<input id="search" type="search" placeholder="Find a playlist, find a feeling…" aria-label="Search your playlists"><kbd>/</kbd></label><div class="top-actions"><span class="environment">${icon('check',true)}Private library</span><button class="user-menu" data-action="account" aria-label="Account menu for ${e(name)}"><span class="avatar">${e(initials)}</span><span class="user-name">${e(name.split(' ')[0])}</span>${icon('chevron',true)}</button></div></header><div id="content" class="content"></div></main></div>`;
}

function renderToolsShell() {
  $('#app').innerHTML = `<div class="layout"><aside class="sidebar">${brand()}<nav aria-label="Local tools"><div class="nav-caption">LOCAL OPERATIONS</div><a class="nav-item active" href="/">${icon('chart')}<span>Load lab</span></a><a class="nav-item" href="http://localhost:3000/d/tinytune-system/tinytune-system" target="_blank" rel="noopener">${icon('pulse')}<span>Grafana</span></a><a class="nav-item" href="http://localhost:8082/docs" target="_blank" rel="noopener">${icon('code')}<span>API reference</span></a></nav><div class="sidebar-bottom"><div class="local-card"><strong><span class="status-dot"></span>Local dashboard</strong>Separate from the customer app. Tests create their own private fixture accounts.</div><a class="text-button" href="http://localhost:8080" target="_blank" rel="noopener">Open TinyTune ${icon('external',true)}</a></div></aside><main class="main"><header class="topbar"><span class="tiny-label muted">TINYTUNE / LOAD LAB</span><span class="pill"><span class="status-dot"></span>Local dashboard · no account required</span></header><div id="content" class="content"></div></main></div>`;
}

async function enterApp() {
  renderShell();
  $('#content').innerHTML = '<div class="loading-placeholder">Making room for your favorites…</div>';
  await refreshLibrary();
  const shared = new URLSearchParams(location.search).get('playlist');
  if (shared) {
    try { await openPlaylist(shared); } catch(error) { renderDenied(error.message); }
  } else await navigate('library');
}
async function refreshLibrary() {
  state.playlists = (await api('/api/v1/library')).playlists;
  if ($('#library-count')) $('#library-count').textContent = state.playlists.filter(p=>p.role==='owner').length;
}
function setActiveNav() {
  document.querySelectorAll('[data-action="nav"]').forEach(button => {
    const active = button.dataset.view === state.view || state.view === 'detail' && button.dataset.view === 'library';
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
  });
}
async function navigate(view) {
  if (!isTools && view==='console') return;
  state.view = view; state.query = ''; if ($('#search')) $('#search').value = '';
  history.replaceState(null, '', view === 'console' ? '/console' : '/');
  setActiveNav(); document.title = view === 'console' ? 'Load lab — TinyTune' : 'Your library — TinyTune';
  if (view === 'console') { renderConsole(); await pollConsole(); }
  else { await refreshLibrary(); renderLibrary(); }
}

function renderLibrary() {
  const favorites = state.view === 'favorites';
  const shared = state.view === 'shared';
  $('#content').innerHTML = `<div class="page-heading"><div><div class="eyebrow">YOUR LITTLE CORNER OF SOUND</div><h1>${shared?'Good taste travels.':favorites?'Close to the heart.':'A soundtrack for every day.'}</h1><p>${shared?'A few good playlists, shared with you by name.':favorites?'The playlists you keep coming back to.':'Collect the songs. Keep the feeling. Share the good stuff.'}</p></div><button class="button primary" data-action="create-playlist">${icon('plus',true)}New playlist</button></div>
    ${!favorites&&!shared?`<section class="hero"><div class="hero-copy"><div class="eyebrow">A MIXTAPE, JUST BECAUSE</div><h2>Some things sound<br>better together.</h2><p>For late nights, long drives, and the people you’d share your headphones with.</p><button class="button primary" data-action="featured">Find your next listen ${icon('arrow',true)}</button></div><div class="hero-art" aria-hidden="true"><div class="record"></div><span class="record-note">SIDE A / GOOD COMPANY</span></div></section>`:''}
    <div class="section-top"><h2>${shared?'Shared with you':favorites?'Your favorites':'Made by you'}</h2><div class="tabs" aria-label="Playlist filters"><button class="tab ${state.filter==='all'?'active':''}" data-action="filter" data-filter="all">All playlists</button><button class="tab ${state.filter==='recent'?'active':''}" data-action="filter" data-filter="recent">Newest first</button></div></div>
    <div id="playlist-grid" class="playlist-grid"></div><footer class="library-foot"><span>${icon('music',true)} A good playlist is a little piece of you.</span><span>Made locally. Shared freely. Played on repeat.</span></footer>`;
  renderCards();
}
function renderCards() {
  let playlists = state.playlists.filter(p => (state.view==='shared'?p.role!=='owner':state.view==='favorites'?p.favorite:p.role==='owner') && `${p.name} ${p.description}`.toLowerCase().includes(state.query.toLowerCase()));
  if (state.filter === 'all') playlists = [...playlists].sort((a,b) => a.cover-b.cover);
  $('#playlist-grid').innerHTML = playlists.length ? playlists.map(p => `<article class="playlist-card">
    <button class="card-art" data-action="open-playlist" data-id="${e(p.id)}" aria-label="Open ${e(p.name)}">${cover(p.cover)}<span class="card-open">${icon('arrow',true)}</span></button>
    <div class="card-caption"><div><h3><button data-action="open-playlist" data-id="${e(p.id)}">${e(p.name)}</button></h3>
    <p>${p.track_count} ${p.track_count===1?'track':'tracks'} · ${number(p.play_count)} ${p.play_count===1?'play':'plays'}</p></div>
    <button class="icon-button ${p.favorite?'favorite-on':''}" data-action="favorite" data-id="${e(p.id)}" aria-label="${p.favorite?'Unfavorite':'Favorite'} ${e(p.name)}" aria-pressed="${p.favorite}">${icon('heart',true)}</button></div>
    ${p.role!=='owner'?`<p class="shared-by">By @${e(p.owner_username)} <span class="permission-badge">${e(p.role)}</span></p>`:''}<p class="card-description">${e(p.description || 'A fresh mix. A feeling all your own.')}</p></article>`).join('') : `<div class="empty"><h3>${state.query?'Nothing on this frequency.':state.view==='shared'?'Good company is on its way.':state.view==='favorites'?'Keep your favorites close.':'Every good mix starts somewhere.'}</h3>
    <p>${state.query?'Try a different playlist name.':state.view==='shared'?`Ask a friend to share with @${e(state.user.username)}.`:state.view==='favorites'?'Tap the heart on a playlist to save it here.':'Create your first private playlist and add a few songs.'}</p>${!state.query&&state.view==='library'?'<button class="button primary" data-action="create-playlist">Create a playlist</button>':''}</div>`;
}

function renderDenied(message) {
  if(!state.user)return;
  state.playlist=null; state.stats=null; state.view='denied';
  if($('#modal').open)closeModal();
  $('#content').innerHTML=`<div class="empty access-denied"><div class="eyebrow">PRIVATE PLAYLIST</div><h2>This mix is invite-only.</h2><p>${e(message || 'Ask the owner to share this playlist with your username.')}</p><p>You’re signed in as <strong>@${e(state.user.username)}</strong>. A link alone doesn’t grant access.</p><button class="button primary" data-action="nav" data-view="library">Back to your library ${icon('arrow',true)}</button></div>`;
}

async function openPlaylist(id) {
  const [playlist, stats] = await Promise.all([api(`/api/v1/playlists/${encodeURIComponent(id)}`),api(`/api/v1/playlists/${encodeURIComponent(id)}/stats`)]);
  state.playlist = playlist; state.stats = stats; state.view = 'detail'; setActiveNav();
  history.replaceState(null, '', `/?playlist=${encodeURIComponent(id)}`);
  document.title = `${playlist.name} — TinyTune`;
  const owner = playlist.owner_id === state.user.id;
  $('#content').innerHTML = `<button class="back" data-action="nav" data-view="library">${icon('back',true)}Back to your library</button><section class="detail-hero"><div class="detail-cover">${cover(playlist.cover)}</div><div class="detail-copy"><div class="eyebrow">${owner?'YOUR PLAYLIST':'SHARED PLAYLIST'}</div><h1>${e(playlist.name)}</h1><p>${e(playlist.description || 'A collection of songs worth sharing.')}</p><div class="detail-meta">${playlist.tracks.length} ${playlist.tracks.length===1?'track':'tracks'} <span aria-hidden="true">·</span> <span id="total-plays">${number(stats.tracks.reduce((sum,t) => sum+t.play_count,0))}</span> recorded plays <span aria-hidden="true">·</span> ${stats.consistency==='eventual'?'Updates asynchronously':'Updates synchronously'}</div><div class="detail-actions">${owner?`<button class="button primary" data-action="add-track">${icon('plus',true)}Add a track</button>`:''}<button class="button secondary" data-action="share">${icon('share',true)}Share playlist</button></div></div></section><div class="section-top"><h2>The tracklist</h2><small>A little something for every mood.</small></div><div class="track-table"><div class="track-row head"><span>#</span><span>Track</span><span class="track-artist">Artist</span><span class="track-count">Plays</span><span>Listen history</span></div><div id="tracks"></div></div><p class="detail-note">${icon('info',true)}TinyTune tracks listening events; it doesn’t stream audio. Record a play to see your stats update.</p>`;
  if(playlist.role==='editor')$('.detail-actions').insertAdjacentHTML('afterbegin',`<button class="button primary" data-action="add-track">${icon('plus',true)}Add a track</button>`);
  $('.detail-copy .eyebrow').textContent=owner?'YOUR PRIVATE PLAYLIST':`${playlist.role.toUpperCase()} ACCESS · SHARED WITH YOU`;
  if(!owner)$('[data-action="share"]').innerHTML=`${icon('share',true)}Copy link`;
  renderTracks();
}

async function sharingModal() {
  const data=await api(`/api/v1/playlists/${state.playlist.id}/sharing`);
  showModal('Good music. Chosen company.',`<p>This playlist is private. Only you and the people below can open it.</p>
    <form id="share-form"><label for="share-username">Share with a registered username</label><div class="share-invite"><input id="share-username" name="username" placeholder="friend_username" required maxlength="64" autocapitalize="none" spellcheck="false"><select name="role" aria-label="Permission for invited person"><option value="viewer">Can view</option><option value="editor">Can edit</option></select></div><p class="field-hint">Viewers can view and log plays. Editors can also add tracks. Only you manage access.</p><button class="button primary" type="submit">${icon('plus',true)}Grant access</button><div id="share-error" class="auth-error" role="alert"></div></form>
    <div class="sharing-members"><div class="sharing-person"><div><strong>${e(state.user.name)}</strong><small>@${e(state.user.username)} · You</small></div><span class="permission-badge">Owner</span></div>
    ${data.members.map(m=>`<div class="sharing-person"><div><strong>${e(m.name)}</strong><small>@${e(m.username)}</small></div><select class="sharing-role" data-username="${e(m.username)}" aria-label="Permission for ${e(m.username)}"><option value="viewer" ${m.role==='viewer'?'selected':''}>Can view</option><option value="editor" ${m.role==='editor'?'selected':''}>Can edit</option></select><button class="icon-button" data-action="revoke" data-id="${e(m.user_id)}" aria-label="Remove access for ${e(m.username)}">${icon('close',true)}</button></div>`).join('')}</div>
    <div class="share-link-section"><label for="share-link">Playlist link</label><input id="share-link" readonly value="${e(`${location.origin}/?playlist=${state.playlist.id}`)}"><p class="field-hint">Copying the link doesn’t grant access. Invite the recipient above first.</p></div><div class="form-actions"><button class="button secondary" data-action="copy-link">${icon('share',true)}Copy link</button><button class="button primary" data-action="close-modal">Done</button></div>`);
}
function renderTracks() {
  if (!$('#tracks') || !state.playlist) return;
  const counts = new Map((state.stats?.tracks || []).map(t => [t.track_id,t.play_count]));
  $('#tracks').innerHTML = state.playlist.tracks.length ? state.playlist.tracks.map((t,index) => `<div class="track-row"><span class="track-number">${String(index+1).padStart(2,'0')}</span><span class="track-title">${e(t.title)}</span><span class="track-artist">${e(t.artist)}</span><span class="track-count" data-track-count="${e(t.id)}">${number(counts.get(t.id)||0)}</span><button class="button secondary" data-action="record-play" data-id="${e(t.id)}" aria-label="Record play for ${e(t.title)}">${icon('plus',true)}Log play</button></div>`).join('') : '<div class="empty"><h3>A blank side A.</h3><p>Add your first track to get this mix started.</p></div>';
  if ($('#total-plays')) $('#total-plays').textContent = number((state.stats?.tracks || []).reduce((sum,t) => sum+t.play_count,0));
}

function updateTrackCounts() {
  const counts = new Map((state.stats?.tracks || []).map(t => [t.track_id,t.play_count]));
  document.querySelectorAll('[data-track-count]').forEach(element => {
    element.textContent = number(counts.get(element.dataset.trackCount) || 0);
  });
  if ($('#total-plays')) $('#total-plays').textContent = number((state.stats?.tracks || []).reduce((sum,t) => sum+t.play_count,0));
}

function createPlaylistModal() {
  state.selectedCover = 0;
  showModal('Start a new feeling.', `<p>Give your mix a name. The rest will follow.</p><form id="playlist-form"><label for="playlist-name">Playlist name</label><input id="playlist-name" name="name" required maxlength="120" placeholder="Something worth coming back to" autofocus><label for="playlist-description">A few words about it</label><textarea id="playlist-description" name="description" maxlength="500" placeholder="The mood, the moment, the reason…"></textarea><label>Choose your cover</label><div class="cover-picker" role="group" aria-label="Playlist cover">${[0,1,2,3,4,5].map(i => `<button type="button" class="cover-option ${i===0?'selected':''}" data-action="cover" data-cover="${i}" aria-label="Cover ${i+1}" aria-pressed="${i===0}">${cover(i)}</button>`).join('')}</div><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button primary" type="submit">Create playlist ${icon('arrow',true)}</button></div></form>`);
}
function addTrackModal() {
  showModal('One more good song.', `<p>Add a track to ${e(state.playlist.name)}.</p><form id="track-form"><label for="track-title">Track title</label><input id="track-title" name="title" required maxlength="200" placeholder="The song you can’t get out of your head" autofocus><label for="track-artist">Artist</label><input id="track-artist" name="artist" required maxlength="200" placeholder="Who’s behind the sound?"><div class="form-actions"><button type="button" class="button secondary" data-action="close-modal">Cancel</button><button class="button primary" type="submit">Add track ${icon('plus',true)}</button></div></form>`);
}

function renderConsole() {
  $('#content').innerHTML = `<div class="page-heading console-heading"><div><div class="eyebrow">BEHIND THE SOUND</div><h1>A little pressure. A lot to learn.</h1><p>Watch the system breathe. Find out where it bends.</p></div><span class="pill" id="runner-pill"><span class="status-dot"></span>Checking runner</span></div><div id="console-error"></div><div id="metrics" class="metric-grid"></div>
    <div class="console-layout"><section class="panel"><div class="panel-pad"><h3>Your next experiment</h3><p class="panel-subtitle">Real traffic. Real responses. Your local system.</p><form id="load-form" class="config-form"><label for="run-name">EXPERIMENT NAME</label><input id="run-name" name="name" maxlength="80" required value="Finding the sweet spot"><label for="run-preset">START WITH A PRESET</label><select id="run-preset" name="preset"><option value="gentle">A gentle warm-up</option><option value="worker">Make the workers sweat</option><option value="boundary">Find the API boundary</option><option value="custom">Make it your own</option></select><label for="run-rates">ARRIVAL RATES · REQUESTS / SEC</label><input id="run-rates" name="rates" required value="50, 100, 200" pattern="[0-9, ]+" aria-describedby="rates-hint"><p class="field-hint" id="rates-hint">Comma-separated steps. Up to 5, each 1–3,000 RPS.</p><label for="run-duration">TIME AT EACH STEP</label><select id="run-duration" name="duration"><option value="5">5 seconds · quick look</option><option value="10" selected>10 seconds · standard</option><option value="20">20 seconds · closer look</option><option value="30">30 seconds · steady pressure</option><option value="60">60 seconds · extended</option></select><label>THE WORKLOAD</label><div class="mix-bar"><span></span><span></span></div><div class="mix-labels"><span>70% playlist reads</span><span>30% play events</span></div><button id="start-run" class="button primary" type="submit">${icon('play',true)}Run experiment</button></form></div><div class="safety-note">${icon('info',true)} Tests target TinyTune on this machine. One experiment runs at a time. Higher rates can briefly affect the playlist app.</div></section>
    <div class="console-right"><section class="panel"><div class="chart-head"><div><h3 id="chart-title">Waiting for the first beat</h3><p class="panel-subtitle" id="chart-subtitle">Run an experiment to see client-side throughput.</p></div><div class="chart-legend"><span><i class="legend-line"></i>Achieved</span><span><i class="legend-line peach"></i>Target</span></div></div><div id="throughput-chart" class="chart"></div><div class="progress-line"><span id="run-progress" style="width:0"></span></div><div id="run-footer" class="run-footer"></div></section>
    <section class="panel"><div class="chart-head"><h3>The system, right now</h3><span class="tiny-label muted">LIVE · 3 SEC</span></div><div id="topology" class="topology"></div><div class="topology-note">Acceptance and processing have separate capacity limits. A fast API can still hide a growing queue.</div></section>
    <section class="panel"><div class="chart-head"><h3>Processing backlog</h3><span class="tiny-label muted">EVENTS</span></div><div id="queue-chart" class="chart" style="min-height:170px"></div></section></div></div>
    <div id="health-strip" class="health-strip"></div><div id="run-results"></div><section class="run-history"><div class="section-top"><h2>The experiment notebook</h2><small>Last 30 runs · reports kept for 7 days</small></div><div id="history"></div></section><footer class="library-foot"><span>${icon('info',true)} Short tests reveal bottlenecks. Longer soaks establish sustainable capacity.</span><a href="http://localhost:3000/d/tinytune-system/tinytune-system" target="_blank" rel="noopener">Explore in Grafana ↗</a></footer>`;
  updateMetrics(); updateRun(); updateTopology(); updateHistory();
}
function metric(label, value, unit, note, name) {
  return `<div class="metric"><div class="metric-label">${label}${icon(name,true)}</div><div class="metric-value">${value}<small>${unit}</small></div><div class="metric-note">${note}</div></div>`;
}
function updateMetrics() {
  if (!$('#metrics')) return;
  const c = state.console || {};
  $('#metrics').innerHTML = metric('API request rate',number(c.request_rate,1),'req/s','Server-side · rolling 30 seconds','pulse') +
    metric('API p95 latency',number(c.p95_ms,1),'ms','Operating target: under 250 ms','clock') +
    metric('Processing backlog',number(c.queue_depth),'events','Accepted, awaiting processing','server') +
    metric('Worker throughput',number(c.worker_rate,1),'events/s','Completed aggregates · rolling 30s','chart');
  const online = c.runner_online;
  $('#runner-pill').innerHTML = `<span class="status-dot${online?'':' loading-dot'}"></span>${online?'Runner connected':'Runner offline'}`;
  $('#health-strip').innerHTML = `<span>${icon('server',true)}${number(c.api_replicas)} API replicas</span><span>${icon('pulse',true)}${number(c.worker_replicas)} workers</span><span>${icon('check',true)}${number(c.cache_hit_percent,1)}% cache hits</span><span>${icon('info',true)}${number(c.error_percent,2)}% API 5xx</span>`;
}
function updateTopology() {
  if (!$('#topology')) return;
  const c = state.console || {};
  $('#topology').innerHTML = `<div class="node"><strong>Nginx</strong><small>Gateway</small></div><span class="connector">→</span><div class="node"><strong>API × ${number(c.api_replicas)}</strong><small>Stateless</small></div><span class="connector">→</span><div class="node"><strong>Redis</strong><small>${number(c.queue_depth)} queued</small></div><span class="connector">→</span><div class="node"><strong>Worker × ${number(c.worker_replicas)}</strong><small>→ PostgreSQL</small></div>`;
  $('#queue-chart').innerHTML = chart(state.monitorSamples.map((p,i) => ({x:i,y:p.depth})), [], 'queue', 'No queue samples yet.', 140);
}
function chart(points, targets = [], type = 'requests', emptyText = 'Your experiment starts here.', height = 200) {
  const width = 650, pad = {left:43,right:12,top:12,bottom:25}, plotH = height-pad.top-pad.bottom, plotW = width-pad.left-pad.right;
  const maxX = Math.max(10,...points.map(p=>p.x),...targets.map(p=>p.x));
  const maxY = Math.max(type==='queue'?5:10,...points.map(p=>p.y),...targets.map(p=>p.y))*1.15;
  const x = value => pad.left+value/maxX*plotW, y = value => height-pad.bottom-value/maxY*plotH;
  const path = arr => arr.map((p,i)=>`${i?'L':'M'}${x(p.x).toFixed(1)},${y(p.y).toFixed(1)}`).join(' ');
  let markup = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${type==='queue'?'Processing backlog over time':'Achieved and target requests per second over time'}" style="height:${height}px">`;
  for(let i=0;i<=4;i++) {
    const value = maxY*i/4, lineY = y(value);
    markup += `<line x1="${pad.left}" x2="${width-pad.right}" y1="${lineY}" y2="${lineY}" stroke="#e8eddf" stroke-dasharray="3 4"/><text x="${pad.left-9}" y="${lineY+3}" text-anchor="end" font-family="sans-serif" font-size="9" fill="#9ba58d">${number(value)}</text>`;
  }
  if(points.length) {
    markup += `<path d="${path(points)} L${x(points.at(-1).x)},${y(0)} L${x(points[0].x)},${y(0)}Z" fill="#71966a0d"/><path d="${path(points)}" fill="none" stroke="#648866" stroke-width="2" stroke-linejoin="round"/>`;
    const last=points.at(-1); markup+=`<circle cx="${x(last.x)}" cy="${y(last.y)}" r="3" fill="#648866"/>`;
  }
  if(targets.length) markup += `<path d="${path(targets)}" fill="none" stroke="#c99d76" stroke-width="1.5" stroke-dasharray="5 4"/>`;
  markup += `<text x="${pad.left}" y="${height-4}" font-family="sans-serif" font-size="8" fill="#9ba58d">${type==='queue'?'Recent samples':'0s'}</text><text x="${width-pad.right}" y="${height-4}" text-anchor="end" font-family="sans-serif" font-size="8" fill="#9ba58d">${type==='queue'?'Now':`${number(maxX)}s`}</text></svg>`;
  return markup + (!points.length?`<div class="chart-empty"><strong>${e(emptyText)}</strong><span>${type==='queue'?'Live queue depth appears automatically.':'The chart fills with real k6 measurements.'}</span></div>`:'');
}
const isRunning = run => run && ['queued','running'].includes(run.status);
function updateRun() {
  if (!$('#throughput-chart')) return;
  const run = state.run, running = isRunning(run);
  $('#start-run').disabled = !!running || !!state.console?.active_job_id || !state.console?.runner_online;
  $('#start-run').innerHTML = running?`${icon('clock',true)}Experiment in progress`:`${icon('play',true)}Run experiment`;
  $('#chart-title').textContent = run?.name || 'Waiting for the first beat';
  $('#chart-subtitle').textContent = run?`${run.rates.join(' → ')} req/s · ${run.duration}s per step · ${run.status}`:'Run an experiment to see client-side throughput.';
  const samples = run?.samples || [];
  $('#throughput-chart').innerHTML = chart(samples.map(p=>({x:p.second,y:p.rps})), samples.map(p=>({x:p.second,y:p.target})), 'requests', running?'Warming up the system…':'Your experiment starts here.');
  $('#run-progress').style.width = `${!run?0:running?Math.min(96,100*(run.elapsed_seconds||0)/run.estimated_seconds):100}%`;
  const label = run?`${running?'Elapsed':'Duration'} ${number(run.elapsed_seconds||0)}s · ${run.status==='completed'?'Report ready':run.status==='cancelled'?'Stopped by you':run.status==='failed'?'Needs attention':run.status==='queued'?'Waiting for runner':'Sending traffic'}`:'Ready when you are. Each run creates its own test playlist.';
  $('#run-footer').innerHTML = `<span>${e(label)}</span>${running?`<button class="text-button" data-action="cancel-run">${icon('stop',true)}Stop run</button>`:run?.report?`<a class="text-button" href="/api/v1/load-tests/${e(run.id)}/download">${icon('download',true)}JSON report</a>`:''}`;
  const report = run?.report;
  $('#run-results').innerHTML = run?.error?`<div class="error-banner" style="margin-top:20px">${icon('info',true)}${e(run.error)}</div>`:report?`<section class="panel results-panel"><div class="results-head"><div><h3>${report.saturation_point?`API boundary observed at ${number(report.saturation_point.target_rps)} RPS`:'Inside the operating envelope'}</h3><p>Client measurements · p95 ≤ 250 ms · errors ≤ 1% · achieved ≥ 90% of target</p></div><a class="button secondary" href="/api/v1/load-tests/${e(run.id)}/download">${icon('download',true)}Export JSON</a></div><div class="table-scroll"><table class="results-table"><thead><tr><th>Target RPS</th><th>Achieved RPS</th><th>p95 latency</th><th>Errors</th><th>Envelope</th></tr></thead><tbody>${report.steps.map(step=>`<tr><td>${number(step.target_rps)}</td><td>${number(step.achieved_rps,1)}</td><td>${number(step.latency_ms.p95,1)} ms</td><td>${number(step.error_percent,2)}%</td><td><span class="${step.saturated?'result-bad':'result-good'}">${step.saturated?'Exceeded':'Within'}</span></td></tr>`).join('')}</tbody></table></div><div class="safety-note">This measures API acceptance, not sustainable analytics processing. Watch backlog growth alongside latency. Saturation uses consecutive violating steps, or a violating final step.</div></section>`:'';
}
function updateHistory() {
  if (!$('#history')) return;
  $('#history').innerHTML = state.history.length?state.history.map(run=>`<div class="history-row"><div><span class="history-title">${e(run.name)}</span><br><small>${e(run.rates.join(' → '))} RPS · ${run.duration}s per step</small></div><small>${new Date(run.created_at).toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})}</small><span class="history-status ${run.status==='failed'?'failed':''}">${e(run.status)}</span><button class="text-button" data-action="view-run" data-id="${e(run.id)}">View ${icon('arrow',true)}</button></div>`).join(''):'<p class="muted" style="font-size:11px;padding:15px 0">No experiments yet. There’s a first time for every bottleneck.</p>';
}
async function pollConsole() {
  if (state.pollBusy || state.view!=='console') return;
  state.pollBusy = true;
  try {
    const [data,history] = await Promise.all([api('/api/v1/console'),api('/api/v1/load-tests')]);
    if(state.view!=='console') return;
    state.console = data; state.history = history.runs;
    state.monitorSamples.push({depth:data.queue_depth}); state.monitorSamples = state.monitorSamples.slice(-60);
    if (!state.run && history.runs.length) state.run = history.runs[0];
    else if (state.run) state.run = history.runs.find(run=>run.id===state.run.id) || state.run;
    $('#console-error').innerHTML = '';
    updateMetrics(); updateTopology(); updateRun(); updateHistory();
  } catch(error) {
    if ($('#console-error')) $('#console-error').innerHTML = `<div class="error-banner">${icon('info',true)}${e(error.message)} · Retrying automatically.</div>`;
  } finally { state.pollBusy = false; }
}

document.addEventListener('click', async event => {
  const button = event.target.closest('[data-action]'); if (!button || button.disabled) return;
  const action = button.dataset.action;
  try {
    if(action==='close-modal') return closeModal();
    if(action==='auth-tab') { state.authMode=button.dataset.mode; return renderAuth(); }
    if(action==='google-help') return googleHelp();
    if(action==='toggle-password') { const input=$('#account-password');const show=input.type==='password';input.type=show?'text':'password';button.textContent=show?'Hide':'Show';button.setAttribute('aria-label',show?'Hide password':'Show password');return; }
    if(action==='nav') return await navigate(button.dataset.view);
    if(action==='create-playlist') return createPlaylistModal();
    if(action==='add-track') return addTrackModal();
    if(action==='cover') {
      state.selectedCover=Number(button.dataset.cover); document.querySelectorAll('.cover-option').forEach(option=>{const active=option===button;option.classList.toggle('selected',active);option.setAttribute('aria-pressed',active);});return;
    }
    if(action==='filter') { state.filter=button.dataset.filter;return renderLibrary(); }
    if(action==='featured') { const p=state.playlists.find(p=>p.role==='owner');return p?await openPlaylist(p.id):createPlaylistModal(); }
    if(action==='open-playlist') {try{return await openPlaylist(button.dataset.id);}catch(error){if([403,404].includes(error.status))return renderDenied(error.message);throw error;}}
    if(action==='favorite') {
      const playlist=state.playlists.find(p=>p.id===button.dataset.id);button.disabled=true;
      await api(`/api/v1/library/${playlist.id}`,{method:'PATCH',body:JSON.stringify({favorite:!playlist.favorite})});playlist.favorite=!playlist.favorite;renderCards();return;
    }
    if(action==='record-play') {
      button.disabled=true;
      await api(`/api/v1/playlists/${state.playlist.id}/plays`,{method:'POST',headers:{'Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({track_id:button.dataset.id})});
      toast('Play accepted. Your listening history will catch up in a moment.');return;
    }
    if(action==='share' && state.playlist.role==='owner')return await sharingModal();
    if(action==='share' || action==='copy-link') {
      const url=`${location.origin}/?playlist=${state.playlist.id}`;
      try { await navigator.clipboard.writeText(url);toast('Link copied. Only people granted access can open it.'); }
      catch { showModal('A link for your people.',`<p>Only people granted access by the owner can view this playlist.</p><label for="share-link" style="margin-top:20px">Playlist link</label><input id="share-link" value="${e(url)}" readonly><div class="form-actions"><button class="button primary" data-action="close-modal">Done</button></div>`); }return;
    }
    if(action==='revoke'){await api(`/api/v1/playlists/${state.playlist.id}/sharing/${button.dataset.id}`,{method:'DELETE'});await sharingModal();toast('Access removed. Their next request will be denied.');return;}
    if(action==='account') return showModal('Your little corner.',`<p>${e(state.user.name)}</p><div class="help-box" style="margin-top:15px"><p>Your username: <strong>@${e(state.user.username)}</strong></p><p>Friends can share playlists with this exact username.</p><p>${state.user.provider==='google'?'Signed in with Google.':'Signed in with your TinyTune account.'}</p></div><div class="form-actions"><button class="button primary" data-action="logout">${icon('logout',true)}Sign out</button></div>`);
    if(action==='logout') { await post('/auth/logout');window.google?.accounts.id.disableAutoSelect();closeModal();state.user=null;state.playlists=[];state.run=null;state.history=[];state.config=await api('/auth/config');history.replaceState(null,'','/');renderAuth();return; }
    if(action==='about') return showModal('Small app. Real systems.',`<div class="help-box"><p>TinyTune combines a playlist library with a distributed play-event pipeline: Nginx, stateless FastAPI replicas, PostgreSQL, Redis Streams, and independent workers.</p><p style="margin-top:15px">The load lab runs k6 against the local gateway. Prometheus supplies live metrics, and Grafana gives you the deeper view.</p></div><div class="form-actions"><button class="button primary" data-action="close-modal">Back to the music</button></div>`);
    if(action==='cancel-run') { button.disabled=true;await post(`/api/v1/load-tests/${state.run.id}/cancel`);toast('Stopping the experiment…');return; }
    if(action==='view-run') { state.run=state.history.find(run=>run.id===button.dataset.id);updateRun();$('#chart-title').scrollIntoView({behavior:'smooth',block:'center'});return; }
  } catch(error) { toast(error.message,true); }
  finally { if(button.isConnected) button.disabled=false; }
});

document.addEventListener('submit', async event => {
  const form=event.target;if(!['auth-form','share-form','playlist-form','track-form','load-form'].includes(form.id))return;
  event.preventDefault();const submit=$('[type="submit"]',form);submit.disabled=true;
  try {
    const data=Object.fromEntries(new FormData(form));
    if(form.id==='auth-form') {
      const result=await post(state.authMode==='signup'?'/auth/signup':'/auth/login',data);
      state.user=result.user;await enterApp();toast(state.authMode==='signup'?'Your space, ready to make your own.':'Welcome back.');
    } else if(form.id==='share-form') {
      await post(`/api/v1/playlists/${state.playlist.id}/sharing`,data);await sharingModal();toast('Playlist shared with the person you chose.');
    } else if(form.id==='playlist-form') {
      if(!data.name.trim())throw new Error('Give your playlist a name.');
      const playlist=await post('/api/v1/playlists',{name:data.name.trim(),description:data.description.trim(),cover:state.selectedCover});
      closeModal();await refreshLibrary();await openPlaylist(playlist.id);toast('A new playlist. A fresh start.');
    } else if(form.id==='track-form') {
      if(!data.title.trim()||!data.artist.trim())throw new Error('Add both a title and an artist.');
      await post(`/api/v1/playlists/${state.playlist.id}/tracks`,{title:data.title.trim(),artist:data.artist.trim()});
      closeModal();await openPlaylist(state.playlist.id);toast('One more good song in the mix.');
    } else {
      const parts=data.rates.split(',').map(v=>v.trim());
      if(parts.some(v=>!/^\d+$/.test(v))||parts.length>5||parts.some(v=>+v<1||+v>3000))throw new Error('Choose 1–5 comma-separated rates between 1 and 3,000 RPS.');
      const rates=parts.map(Number);
      if(rates.some((v,i)=>i>0&&v<=rates[i-1]))throw new Error('Use increasing arrival rates for the saturation ladder.');
      state.run=await post('/api/v1/load-tests',{name:data.name.trim(),rates,duration:Number(data.duration)});
      toast('Experiment queued. Let’s find the sweet spot.');await pollConsole();
    }
  } catch(error){const field=form.id==='auth-form'?$('#auth-error'):form.id==='share-form'?$('#share-error'):null;if(field)field.textContent=error.message;else toast(error.message,true);}
  finally{if(submit.isConnected)submit.disabled=false;if(form.id==='load-form')updateRun();}
});
document.addEventListener('input',event=>{
  if(event.target.id==='search'){state.query=event.target.value;if(['library','favorites','shared'].includes(state.view))renderCards();}
});
document.addEventListener('change',async event=>{
  if(event.target.matches('.sharing-role')) {
    try{await post(`/api/v1/playlists/${state.playlist.id}/sharing`,{username:event.target.dataset.username,role:event.target.value});await sharingModal();toast('Permission updated.');}catch(error){toast(error.message,true);}return;
  }
  if(event.target.id!=='run-preset')return;
  const presets={gentle:['50, 100, 200','10'],worker:['100, 200, 400','20'],boundary:['1600, 1800, 2000, 2200, 2400','10']};
  const preset=presets[event.target.value];if(preset){$('#run-rates').value=preset[0];$('#run-duration').value=preset[1];}
});
document.addEventListener('keydown',event=>{
  if(event.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)&&!$('#modal').open){event.preventDefault();$('#search')?.focus();}
});
$('#modal').addEventListener('click',event=>{if(event.target===$('#modal')){const rect=event.target.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)closeModal();}});
setInterval(async()=>{
  if((!state.user&&!isTools)||document.hidden)return;
  if(state.view==='console')await pollConsole();
  else if(state.view==='detail'&&state.playlist){
    const id=state.playlist.id;
    try{const stats=await api(`/api/v1/playlists/${id}/stats`);if(state.view==='detail'&&state.playlist?.id===id){state.stats=stats;updateTrackCounts();}}catch(error){if([403,404].includes(error.status))renderDenied('This playlist is no longer shared with you.');else toast(error.message,true);}
  }else if(['library','favorites','shared'].includes(state.view)&&!$('#modal').open){
    try{await refreshLibrary();if(['library','favorites','shared'].includes(state.view))renderCards();}catch(error){toast(error.message,true);}
  }
},3000);
async function boot(){
  try {
    if(isTools){state.view='console';renderToolsShell();renderConsole();document.title='Load lab — TinyTune';await pollConsole();return;}
    const [config,session]=await Promise.all([api('/auth/config'),api('/auth/me')]);state.config=config;state.user=session.user;
    if(state.user)await enterApp();else renderAuth();
  }catch(error){$('#app').innerHTML=`<div class="boot"><span class="brand-mark">♫</span><h2>A brief intermission.</h2><p class="muted">${e(error.message)}</p><button class="button primary" onclick="location.reload()">Try again</button></div>`;}
}
boot();
