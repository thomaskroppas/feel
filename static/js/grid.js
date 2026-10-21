// Сетка 12×12: прокрутка во все стороны, приближение щипком, карточка выбранного слова.
import { emotions } from './store.js';
import { h, reducedMotion } from './ui.js';

const MIN_CELL = 64;
const MAX_CELL = 150;
const QUAD_CENTER = { red: [3, 3], yellow: [9, 3], blue: [3, 9], green: [9, 9] };
let lastCell = 96;

function rgb(hex) {
  const v = hex.trim().replace('#', '');
  const n = parseInt(v.length === 3 ? v.replace(/./g, '$&$&') : v, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function luminance([r, g, b]) {
  const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

function contrast(a, b) {
  const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

// Насыщенность растёт от центра сетки к углам: intensity 1 — бледный, 6 — полный цвет.
export function wordColors(quadrant, intensity) {
  const css = getComputedStyle(document.documentElement);
  const base = rgb(css.getPropertyValue(`--q-${quadrant}`));
  const bg = rgb(css.getPropertyValue('--bg'));
  const t = 0.3 + (intensity - 1) * 0.14;
  const mix = base.map((c, i) => Math.round(bg[i] * (1 - t) + c * t));
  // Белый текст, если он читается как крупный жирный (контраст от 3:1), иначе тёмный.
  const fg = contrast(mix, [255, 255, 255]) >= 3 ? '#FFFFFF' : '#1C1B1A';
  return { bg: `rgb(${mix.join(',')})`, fg };
}

// Переносы в длинных словах. Браузерные словари переносов есть не везде,
// поэтому мягкие переносы (U+00AD) расставляем сами по простым правилам слогов.
const VOWELS = 'аеёиоуыэюя';
const SIGNS = 'ьъй';

export function hyphenate(word, minPart = 3) {
  if (word.length < 9) return word;
  const w = word.toLowerCase();
  const isV = (c) => VOWELS.includes(c);
  const points = [];
  for (let i = minPart; i <= w.length - minPart; i++) {
    const prev = w[i - 1];
    const next = w[i];
    if (SIGNS.includes(next)) continue; // ь, ъ, й не начинают строку
    const leftHasV = [...w.slice(0, i)].some(isV);
    const rightHasV = [...w.slice(i)].some(isV);
    if (!leftHasV || !rightHasV) continue;
    if (isV(prev) && !isV(next) && isV(w[i + 1] || '')) points.push(i); // ма-ма
    else if (!isV(prev) && !isV(next) && !SIGNS.includes(prev) && [...w.slice(i, i + 3)].some(isV) && isV(w[i - 2] || '')) points.push(i); // вос-торг
    else if (SIGNS.includes(prev) && !isV(next)) points.push(i); // боль-ше
    else if (isV(prev) && isV(next)) points.push(i); // ти-ар
  }
  let out = '';
  let last = 0;
  for (const p of points) { out += word.slice(last, p) + '\u00AD'; last = p; }
  return out + word.slice(last);
}

function lengthClass(name) {
  if (name.length >= 15) return 'word xlong';
  if (name.length >= 12) return 'word long';
  return 'word';
}

/**
 * Открывает сетку поверх экрана.
 * opts: { quadrant, selectedId, primaryLabel, onPrimary(emotion), secondaryLabel, onSecondary(emotion), onClose() }
 */
export async function openPicker(opts) {
  const emo = await emotions();
  const cells = new Map();
  let selected = null;

  const scroller = h('div', { class: 'grid-scroller' });
  const grid = h('div', { class: 'grid', role: 'listbox', 'aria-label': 'Эмоции' });
  grid.style.setProperty('--cell', `${lastCell}px`);
  const title = h('div', { class: 'title' });

  const sorted = [...emo.list].filter((e) => !e.hidden || e.id === opts.selectedId);
  for (let row = 12; row >= 1; row--) {
    for (let col = 1; col <= 12; col++) {
      const e = sorted.find((x) => x.energy === row && x.pleasantness === col);
      if (!e) { grid.append(h('span')); continue; }
      const btn = h('button', {
        class: lengthClass(e.name), role: 'option', lang: 'ru', 'aria-selected': 'false',
        'data-id': e.id, onclick: () => select(e),
      }, hyphenate(e.name));
      btn.setAttribute('aria-label', e.name);
      cells.set(e.id, btn);
      grid.append(btn);
    }
  }
  scroller.append(grid);

  function paint() {
    for (const e of sorted) {
      const btn = cells.get(e.id);
      if (!btn) continue;
      const c = wordColors(e.quadrant, e.intensity);
      btn.style.background = c.bg;
      btn.style.color = c.fg;
    }
  }
  paint();
  const scheme = window.matchMedia('(prefers-color-scheme: dark)');
  scheme.addEventListener('change', paint);
  window.addEventListener('feel-theme', paint);

  // ---------- Карточка ----------
  const wordTitle = h('div', { class: 'word-title' });
  const desc = h('div', { class: 'desc' });
  const buttons = h('div', { class: 'btn-row' });
  const sheet = h('div', { class: 'sheet', role: 'dialog', 'aria-live': 'polite' }, wordTitle, desc, buttons);
  if (opts.secondaryLabel) {
    buttons.append(h('button', { class: 'btn', onclick: () => opts.onSecondary(selected) }, opts.secondaryLabel));
  }
  const primary = h('button', { class: 'btn primary', onclick: () => { primary.disabled = true; Promise.resolve(opts.onPrimary(selected)).finally(() => { primary.disabled = false; }); } }, opts.primaryLabel);
  buttons.append(primary);

  function select(e) {
    if (selected) {
      const prev = cells.get(selected.id);
      prev.classList.remove('selected');
      prev.setAttribute('aria-selected', 'false');
    }
    selected = e;
    const btn = cells.get(e.id);
    btn.classList.add('selected');
    btn.setAttribute('aria-selected', 'true');
    // Цвет — кружком рядом со словом: жёлтый текст на светлом фоне плохо читается.
    wordTitle.replaceChildren(
      h('span', { class: 'dot m', style: { background: `var(--q-${e.quadrant})`, display: 'inline-block', verticalAlign: '-2px', marginRight: '10px' } }),
      e.name);
    desc.textContent = e.description;
    sheet.classList.add('open');
    // Держим выбранное слово выше карточки.
    requestAnimationFrame(() => {
      const r = btn.getBoundingClientRect();
      const limit = window.innerHeight - sheet.offsetHeight - 24;
      if (r.bottom > limit) scroller.scrollBy({ top: r.bottom - limit, behavior: reducedMotion() ? 'auto' : 'smooth' });
    });
  }

  // ---------- Приближение ----------
  const cellSize = () => parseFloat(grid.style.getPropertyValue('--cell')) || lastCell;
  const pad = () => {
    const cs = getComputedStyle(grid);
    return [parseFloat(cs.paddingLeft), parseFloat(cs.paddingTop)];
  };

  function zoomTo(next, cx, cy) {
    const cur = cellSize();
    next = Math.max(MIN_CELL, Math.min(MAX_CELL, next));
    if (Math.abs(next - cur) < 0.5) return;
    const [px, py] = pad();
    const gx = scroller.scrollLeft + cx - px;
    const gy = scroller.scrollTop + cy - py;
    const k = next / cur;
    grid.style.setProperty('--cell', `${next}px`);
    scroller.scrollLeft = px + gx * k - cx;
    scroller.scrollTop = py + gy * k - cy;
    lastCell = next;
  }

  let pinch = null;
  const dist = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
  scroller.addEventListener('touchstart', (ev) => {
    if (ev.touches.length === 2) {
      const r = scroller.getBoundingClientRect();
      pinch = {
        d0: dist(ev.touches), c0: cellSize(),
        cx: (ev.touches[0].clientX + ev.touches[1].clientX) / 2 - r.left,
        cy: (ev.touches[0].clientY + ev.touches[1].clientY) / 2 - r.top,
      };
    }
  }, { passive: true });
  let raf = 0;
  scroller.addEventListener('touchmove', (ev) => {
    if (!pinch || ev.touches.length !== 2) return;
    ev.preventDefault();
    const d = dist(ev.touches);
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => zoomTo(pinch.c0 * (d / pinch.d0), pinch.cx, pinch.cy));
  }, { passive: false });
  scroller.addEventListener('touchend', (ev) => { if (ev.touches.length < 2) pinch = null; });
  // Safari: не даём приближать всю страницу.
  const stopGesture = (ev) => ev.preventDefault();
  document.addEventListener('gesturestart', stopGesture);

  const zoomBtn = (label, k) => h('button', {
    class: 'icon-btn', 'aria-label': label,
    onclick: () => zoomTo(cellSize() * k, scroller.clientWidth / 2, scroller.clientHeight / 2),
  }, k > 1 ? '+' : '−');

  // ---------- Название квадранта по центру экрана ----------
  function updateTitle() {
    const [px, py] = pad();
    const c = cellSize();
    const col = (scroller.scrollLeft + scroller.clientWidth / 2 - px) / c;
    const row = (scroller.scrollTop + scroller.clientHeight / 2 - py) / c;
    const q = row < 6 ? (col < 6 ? 'red' : 'yellow') : (col < 6 ? 'blue' : 'green');
    const meta = emo.quadrants.get(q);
    if (meta && title.textContent !== meta.title) title.textContent = meta.title;
  }
  let titleRaf = 0;
  scroller.addEventListener('scroll', () => {
    cancelAnimationFrame(titleRaf);
    titleRaf = requestAnimationFrame(updateTitle);
  }, { passive: true });

  // ---------- Экран ----------
  const screen = h('div', { class: 'grid-screen' },
    h('div', { class: 'grid-top' },
      h('button', { class: 'icon-btn', 'aria-label': 'Назад', onclick: () => close(true) }, '‹'),
      title,
      h('span', { class: 'spacer', style: { width: '44px' } })),
    scroller,
    h('div', { class: 'zoom' }, zoomBtn('Приблизить', 1.2), zoomBtn('Отдалить', 1 / 1.2)),
    sheet);
  document.body.append(screen);
  document.getElementById('tabbar').hidden = true;

  // Открываем на выбранном квадранте (или на выбранном слове).
  const [px, py] = pad();
  const c = cellSize();
  let target = QUAD_CENTER[opts.quadrant] || [6, 6];
  const preselected = opts.selectedId && emo.byId.get(opts.selectedId);
  if (preselected) target = [preselected.pleasantness - 0.5, 12.5 - preselected.energy];
  scroller.scrollLeft = px + target[0] * c - scroller.clientWidth / 2;
  scroller.scrollTop = py + target[1] * c - scroller.clientHeight / 2 + (preselected ? 80 : 0);
  updateTitle();
  if (preselected) select(preselected);

  function close(viaBack) {
    document.removeEventListener('gesturestart', stopGesture);
    scheme.removeEventListener('change', paint);
    window.removeEventListener('feel-theme', paint);
    screen.remove();
    if (viaBack && opts.onClose) opts.onClose();
  }

  return { close };
}
