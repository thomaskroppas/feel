// Открыто в Safari, а не с экрана «Домой»: показываем, как установить.
import { render, setInstallSkipped } from '../app.js';
import { add, h } from '../ui.js';

const SHARE_SVG = `<svg viewBox="0 0 64 64" aria-hidden="true"><rect x="2" y="2" width="60" height="60" rx="16" fill="var(--surface-2)"/>
<path d="M32 14v24M24 21l8-8 8 8" fill="none" stroke="#3E7BFA" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M24 28h-4v22h24V28h-4" fill="none" stroke="#3E7BFA" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

const ADD_SVG = `<svg viewBox="0 0 64 64" aria-hidden="true"><rect x="2" y="2" width="60" height="60" rx="16" fill="var(--surface-2)"/>
<rect x="18" y="18" width="28" height="28" rx="7" fill="none" stroke="var(--text)" stroke-width="3"/>
<path d="M32 25v14M25 32h14" stroke="var(--text)" stroke-width="3" stroke-linecap="round"/></svg>`;

const DONE_SVG = `<svg viewBox="0 0 64 64" aria-hidden="true"><rect x="2" y="2" width="60" height="60" rx="16" fill="var(--surface-2)"/>
<circle cx="25" cy="25" r="8" fill="#E5484D"/><circle cx="39" cy="25" r="8" fill="#F5B83D"/>
<circle cx="25" cy="39" r="8" fill="#3E7BFA"/><circle cx="39" cy="39" r="8" fill="#30A46C"/></svg>`;

export default function install(view) {
  add(view,
    h('div', { class: 'logo', 'aria-hidden': 'true' },
      ['red', 'yellow', 'blue', 'green'].map((q) => h('i', { style: { background: `var(--q-${q})` } }))),
    h('h1', {}, 'Установите feel'),
    h('p', { class: 'subtitle' }, 'Приложение работает с экрана «Домой»: так приходят уведомления и нет панелей Safari.'),
    h('ol', { class: 'steps' },
      h('li', {}, h('span', { class: 'txt' }, 'Нажмите «Поделиться» внизу экрана Safari'), h('span', { html: SHARE_SVG })),
      h('li', {}, h('span', { class: 'txt' }, 'Прокрутите список и выберите «На экран „Домой“»'), h('span', { html: ADD_SVG })),
      h('li', {}, h('span', { class: 'txt' }, 'Нажмите «Добавить» и откройте feel с экрана «Домой»'), h('span', { html: DONE_SVG }))),
    h('p', { class: 'muted small' }, 'Уведомления на iPhone работают с iOS 16.4.'),
    h('button', { class: 'link-btn', onclick: () => { setInstallSkipped(); render(); } }, 'Продолжить в браузере'),
  );
}
