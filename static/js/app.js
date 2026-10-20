// Оболочка приложения: маршруты по адресу после #, нижнее меню, вход.
import { api, setUnauthorizedHandler } from './api.js';
import * as push from './push.js';
import { clearAll } from './store.js';
import { isIOS, isStandalone } from './ui.js';

import analytics from './screens/analytics.js';
import checkin from './screens/checkin.js';
import day from './screens/day.js';
import diary from './screens/diary.js';
import evening from './screens/evening.js';
import install from './screens/install.js';
import login from './screens/login.js';
import morning from './screens/morning.js';
import settings from './screens/settings.js';
import today from './screens/today.js';
import welcome from './screens/welcome.js';

const ROUTES = [
  { re: /^\/$/, screen: today, tab: 'today' },
  { re: /^\/checkin$/, screen: checkin, full: true },
  { re: /^\/morning$/, screen: morning, tab: 'today' },
  { re: /^\/evening$/, screen: evening, tab: 'today' },
  { re: /^\/diary$/, screen: diary, tab: 'diary' },
  { re: /^\/day\/(\d{4}-\d{2}-\d{2})$/, screen: day, tab: 'diary' },
  { re: /^\/analytics$/, screen: analytics, tab: 'analytics' },
  { re: /^\/settings$/, screen: settings, tab: 'settings' },
  { re: /^\/welcome$/, screen: welcome, full: true },
];

const INSTALL_SKIP_KEY = 'feel.install.skip';
const root = document.getElementById('app');
const tabbar = document.getElementById('tabbar');
let me = null;
let cleanup = null;
let renderId = 0;

export function currentUser() { return me; }

export function parseHash() {
  const raw = location.hash.replace(/^#/, '') || '/';
  const [path, query = ''] = raw.split('?');
  return { path: path || '/', params: Object.fromEntries(new URLSearchParams(query)) };
}

export function go(hash, replace = false) {
  if (replace) history.replaceState(null, '', hash);
  else if (location.hash !== hash) { location.hash = hash; return; }
  render();
}

function removeOverlays() {
  document.querySelectorAll('.grid-screen, .sheet, .backdrop').forEach((el) => el.remove());
}

function skipInstall() {
  try { return localStorage.getItem(INSTALL_SKIP_KEY) === '1'; } catch (e) { return false; }
}

export function setInstallSkipped() {
  try { localStorage.setItem(INSTALL_SKIP_KEY, '1'); } catch (e) { /* приватный режим */ }
}

async function mount(screen, params, match, opts = {}) {
  const id = ++renderId;
  if (cleanup) { try { cleanup(); } catch (e) { /* ignore */ } cleanup = null; }
  removeOverlays();
  const view = document.createElement('div');
  view.className = 'screen-enter';
  root.replaceChildren(view);
  root.classList.toggle('fullscreen', !!opts.full);
  tabbar.hidden = !!opts.full || !opts.tab;
  tabbar.querySelectorAll('a').forEach((a) => a.classList.toggle('active', a.dataset.tab === opts.tab));
  try {
    const result = await screen(view, params, match);
    if (id === renderId && typeof result === 'function') cleanup = result;
  } catch (e) {
    if (id !== renderId) return;
    view.replaceChildren();
    const msg = document.createElement('div');
    msg.className = 'empty';
    msg.textContent = e && e.message ? e.message : 'Не удалось загрузить экран';
    view.append(msg);
  }
}

export async function render() {
  if (isIOS() && !isStandalone() && !skipInstall()) {
    return mount(install, {}, null, { full: true });
  }
  if (!me) {
    try { me = await api.get('/api/auth/me'); } catch (e) { me = null; }
  }
  if (!me) return mount(login, {}, null, { full: true });

  const { path, params } = parseHash();
  for (const r of ROUTES) {
    const m = path.match(r.re);
    if (m) return mount(r.screen, params, m, r);
  }
  go('#/', true);
}

export function onLoggedIn(user) {
  me = user;
  push.resync();
  let onboarded = false;
  try { onboarded = localStorage.getItem('feel.onboarded') === '1'; } catch (e) { /* нет хранилища */ }
  go(onboarded ? '#/' : '#/welcome', true);
}

export function onLoggedOut() {
  me = null;
  clearAll();
  go('#/', true);
}

setUnauthorizedHandler(() => {
  if (me) { me = null; render(); }
});

window.addEventListener('hashchange', render);

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
  // Тап по уведомлению при открытом приложении: service worker просит открыть экран.
  navigator.serviceWorker.addEventListener('message', (ev) => {
    if (ev.data && ev.data.type === 'navigate' && ev.data.url) {
      const url = new URL(ev.data.url, location.origin);
      if (url.origin === location.origin) go(url.hash || '#/');
    }
  });
}

// Вернулись в приложение после долгого перерыва — обновляем экран (например, сменилась дата).
let hiddenAt = 0;
document.addEventListener('visibilitychange', () => {
  if (document.hidden) { hiddenAt = Date.now(); return; }
  if (hiddenAt && Date.now() - hiddenAt > 10 * 60 * 1000 && !document.querySelector('.grid-screen')) {
    const { path } = parseHash();
    if (path === '/' || path === '/diary') render();
  }
});

render().then(() => { if (me) push.resync(); });
