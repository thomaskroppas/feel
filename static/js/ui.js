// Мелкие помощники для интерфейса. Текст пользователя вставляется только как текст.

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v === null || v === undefined) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'html') el.innerHTML = v; // только для своих статичных SVG
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  append(el, children);
  return el;
}

// Как replaceChildren/append, но понимают вложенные массивы и пропускают null/false.
export function fill(el, ...children) {
  el.replaceChildren();
  append(el, children);
  return el;
}

export function add(el, ...children) {
  append(el, children);
  return el;
}

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

let toastTimer;
export function toast(message, ms = 2200) {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, ms);
}

export function showError(e) {
  toast(e && e.message ? e.message : 'Что-то пошло не так', 3200);
}

const THEME_KEY = 'feel.theme';

export function getTheme() {
  try { return localStorage.getItem(THEME_KEY) || 'system'; } catch (e) { return 'system'; }
}

export function applyTheme(theme = getTheme()) {
  const root = document.documentElement;
  if (theme === 'light' || theme === 'dark') root.dataset.theme = theme;
  else delete root.dataset.theme;
  window.dispatchEvent(new Event('feel-theme'));
}

export function setTheme(theme) {
  try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* нет хранилища */ }
  applyTheme(theme);
}

export const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export function isStandalone() {
  return window.navigator.standalone === true || window.matchMedia('(display-mode: standalone)').matches;
}

export function isIOS() {
  return /iphone|ipad|ipod/i.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
}

// ---------- Даты ----------
const WEEKDAYS = ['воскресенье', 'понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота'];
const WEEKDAYS_SHORT = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
const MONTHS_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа',
  'сентября', 'октября', 'ноября', 'декабря'];

export function parseDate(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}

export function fmtDayLong(iso) {
  const d = parseDate(iso);
  const wd = WEEKDAYS[d.getDay()];
  return `${wd[0].toUpperCase()}${wd.slice(1)}, ${d.getDate()} ${MONTHS_GEN[d.getMonth()]}`;
}

export function fmtDayShort(iso) {
  const d = parseDate(iso);
  return `${WEEKDAYS_SHORT[d.getDay()]}, ${d.getDate()} ${MONTHS_GEN[d.getMonth()]}`;
}

export function weekdayShort(iso) {
  return WEEKDAYS_SHORT[parseDate(iso).getDay()];
}

export function fmtHours(v) {
  return `${String(v).replace('.', ',')} ч`;
}

export function plural(n, one, few, many) {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

// ---------- Элементы форм ----------
export function switchRow(label, checked, onchange) {
  const input = h('input', { type: 'checkbox', role: 'switch', 'aria-label': label });
  input.checked = !!checked;
  input.addEventListener('change', () => onchange(input.checked));
  return h('label', { class: 'switch-row' }, h('span', {}, label), h('span', { class: 'switch' }, input, h('i')));
}

export function topbar(title, backHref) {
  return h('div', { class: 'topbar' },
    backHref
      ? h('button', { class: 'icon-btn', 'aria-label': 'Назад', onclick: () => history.length > 1 ? history.back() : (location.hash = backHref) }, '‹')
      : h('span', { class: 'spacer' }),
    h('div', { class: 'title' }, title),
    h('span', { class: 'spacer' }));
}

export function confirmSheet({ title, text, confirmLabel, danger, withPassword }) {
  return new Promise((resolve) => {
    const pwd = withPassword ? h('input', { class: 'input', type: 'password', placeholder: 'Пароль', autocomplete: 'current-password' }) : null;
    const close = (value) => {
      sheet.classList.remove('open');
      backdrop.remove();
      setTimeout(() => sheet.remove(), 300);
      resolve(value);
    };
    const backdrop = h('div', { class: 'backdrop', onclick: () => close(null) });
    const sheet = h('div', { class: 'sheet', role: 'dialog', 'aria-modal': 'true' },
      h('h2', {}, title),
      text ? h('p', { class: 'muted' }, text) : null,
      pwd ? h('div', { class: 'field' }, pwd) : null,
      h('div', { class: 'btn-row' },
        h('button', { class: 'btn', onclick: () => close(null) }, 'Отмена'),
        h('button', { class: 'btn primary', style: danger ? { background: 'var(--danger)', color: '#fff' } : null,
          onclick: () => close(pwd ? pwd.value : true) }, confirmLabel)));
    document.body.append(backdrop, sheet);
    requestAnimationFrame(() => sheet.classList.add('open'));
    if (pwd) setTimeout(() => pwd.focus(), 300);
  });
}
