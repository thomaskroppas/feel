// Аналитика: семь отчётов с переключателем периода. Данные считает сервер.
import { api } from '../api.js';
import { wordColors } from '../grid.js';
import { emotions } from '../store.js';
import { add, fill, h, parseDate, plural } from '../ui.js';

const PERIODS = [['week', 'Неделя'], ['month', 'Месяц'], ['3months', '3 месяца'], ['year', 'Год'], ['all', 'Всё']];
const QUADS = ['red', 'yellow', 'blue', 'green'];
const MONTHS = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь',
  'Октябрь', 'Ноябрь', 'Декабрь'];
const MONTHS_GEN = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const PERIOD_KEY = 'feel.analytics.period';
const SVG = 'http://www.w3.org/2000/svg';

const num = (x) => x.toFixed(1).replace('.', ',');
const shortDate = (iso) => { const d = parseDate(iso); return `${d.getDate()} ${MONTHS_GEN[d.getMonth()]}`; };
const pct = (n, total) => (total ? Math.round((n / total) * 100) : 0);

function svg(tag, attrs = {}, ...children) {
  const el = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined) el.setAttribute(k, v);
  children.flat().forEach((c) => c && el.append(c));
  return el;
}

function card(title, ...body) {
  return h('section', { class: 'card report' }, h('h2', {}, title), ...body);
}

function lowData(n, unit) {
  return h('span', { class: 'muted' }, `мало данных (${n} ${unit(n)})`);
}

const records = (n) => plural(n, 'запись', 'записи', 'записей');
const daysWord = (n) => plural(n, 'день', 'дня', 'дней');

// Сравнение «в среднем выше/ниже на» — без слов о причине.
function compare(prefix, diff) {
  if (Math.abs(diff) < 0.05) return `${prefix} приятность в среднем такая же`;
  return `${prefix} приятность в среднем ${diff > 0 ? 'выше' : 'ниже'} на ${num(Math.abs(diff))}`;
}

// ---------- Полоса долей квадрантов ----------
function quadBar(counts, total) {
  const bar = h('div', { class: 'qbar', role: 'img', 'aria-label': QUADS.map((q) => `${q}: ${pct(counts[q], total)}%`).join(', ') });
  QUADS.forEach((q) => {
    if (!counts[q]) return;
    bar.append(h('span', { style: { flexGrow: String(counts[q]), background: `var(--q-${q})` }, title: `${counts[q]} · ${pct(counts[q], total)}%` }));
  });
  return bar;
}

function quadLegend(emo, counts, total) {
  return h('div', { class: 'legend' }, QUADS.map((q) => h('span', { class: 'legend-item' },
    h('span', { class: 'dot s', style: { background: `var(--q-${q})` } }),
    emo.quadrants.get(q).title.replace('Высокая энергия', '↑').replace('Низкая энергия', '↓'),
    counts ? h('b', {}, ` ${pct(counts[q], total)}%`) : null)));
}

// ---------- 1. Календарь ----------
function calendarCard(data, emo, onMonth) {
  const [y, m] = data.calendar.month.split('-').map(Number);
  const first = new Date(y, m - 1, 1);
  const offset = (first.getDay() + 6) % 7; // понедельник — первый
  const t = new Date();
  const today = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
  const grid = h('div', { class: 'cal' },
    ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map((d) => h('span', { class: 'cal-wd' }, d)),
    Array.from({ length: offset }, () => h('span')),
    data.calendar.days.map((d) => {
      const n = Number(d.date.slice(8));
      const c = d.quadrant ? wordColors(d.quadrant, 6) : null;
      return h('a', {
        class: `cal-day${d.date === today ? ' today' : ''}`, href: `#/day/${d.date}`,
        style: c ? { background: c.bg, color: c.fg } : null,
        'aria-label': `${n}: ${d.count} ${records(d.count)}`,
      }, String(n));
    }));
  const shift = (k) => {
    const d = new Date(y, m - 1 + k, 1);
    onMonth(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
  };
  return card('Календарь настроения',
    h('div', { class: 'cal-nav' },
      h('button', { class: 'icon-btn', 'aria-label': 'Предыдущий месяц', onclick: () => shift(-1) }, '‹'),
      h('b', {}, `${MONTHS[m - 1]} ${y}`),
      h('button', { class: 'icon-btn', 'aria-label': 'Следующий месяц', onclick: () => shift(1) }, '›')),
    grid, quadLegend(emo));
}

// ---------- 2. Динамика ----------
function dynamicsCard(data) {
  const days = data.dynamics.days;
  const W = 340, H = 190, L = 26, R = 8, T = 10, B = 24;
  const x = (i) => L + (days.length === 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (days.length - 1));
  const y = (v) => T + ((12 - v) * (H - T - B)) / 11;
  const index = new Map(days.map((d, i) => [d.date, i]));

  const line = (key, cls) => {
    const parts = [];
    let cur = '';
    days.forEach((d, i) => {
      if (d[key] == null) { if (cur) parts.push(cur); cur = ''; return; }
      cur += `${cur ? 'L' : 'M'}${x(i).toFixed(1)},${y(d[key]).toFixed(1)}`;
    });
    if (cur) parts.push(cur);
    return parts.map((p) => svg('path', { d: p, class: cls }));
  };
  const single = (key, cls) => days.map((d, i) => {
    const prevGap = i === 0 || days[i - 1][key] == null;
    const nextGap = i === days.length - 1 || days[i + 1][key] == null;
    return d[key] != null && prevGap && nextGap ? svg('circle', { cx: x(i), cy: y(d[key]), r: 3, class: cls }) : null;
  });

  const chart = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'chart', role: 'img',
    'aria-label': 'Средние приятность и энергия по дням' },
  [1, 6.5, 12].map((v) => svg('line', { x1: L, x2: W - R, y1: y(v), y2: y(v), class: 'grid-line' })),
  [1, 12].map((v) => svg('text', { x: L - 6, y: y(v) + 4, class: 'axis', 'text-anchor': 'end' }, String(v))),
  svg('text', { x: L, y: H - 6, class: 'axis' }, shortDate(days[0].date)),
  svg('text', { x: W - R, y: H - 6, class: 'axis', 'text-anchor': 'end' }, shortDate(days[days.length - 1].date)),
  data.dynamics.points.map((p) => svg('circle', {
    cx: x(index.get(p.date)), cy: y(p.pleasantness), r: 4, class: 'pt', fill: `var(--q-${p.quadrant})`,
  })),
  line('energy', 'ln-energy'), single('energy', 'dot-energy'),
  line('pleasantness', 'ln-pleasant'), single('pleasantness', 'dot-pleasant'));

  // Подсказка по касанию: ближайший день.
  const tip = h('p', { class: 'muted small tip' }, 'Коснитесь графика, чтобы увидеть значения дня');
  const cursor = svg('line', { y1: T, y2: H - B, class: 'cursor', visibility: 'hidden' });
  chart.append(cursor);
  const showAt = (clientX) => {
    const r = chart.getBoundingClientRect();
    const vx = ((clientX - r.left) / r.width) * W;
    const i = Math.max(0, Math.min(days.length - 1, Math.round(((vx - L) / (W - L - R)) * (days.length - 1))));
    const d = days[i];
    cursor.setAttribute('x1', x(i)); cursor.setAttribute('x2', x(i)); cursor.setAttribute('visibility', 'visible');
    const n = data.dynamics.points.filter((p) => p.date === d.date).length;
    tip.textContent = d.pleasantness == null
      ? `${shortDate(d.date)}: нет отметок`
      : `${shortDate(d.date)}: приятность ${num(d.pleasantness)}, энергия ${num(d.energy)} · ${n} ${plural(n, 'отметка', 'отметки', 'отметок')}`;
  };
  chart.addEventListener('pointerdown', (e) => showAt(e.clientX));
  chart.addEventListener('pointermove', (e) => { if (e.buttons || e.pointerType === 'mouse') showAt(e.clientX); });

  return card('Динамика',
    h('div', { class: 'legend' },
      h('span', { class: 'legend-item' }, h('span', { class: 'swatch-line' }), 'Приятность'),
      h('span', { class: 'legend-item' }, h('span', { class: 'swatch-line dashed' }), 'Энергия'),
      h('span', { class: 'legend-item' }, h('span', { class: 'dot s', style: { background: 'var(--text-2)' } }), 'Отметки (приятность)')),
    chart, tip,
    h('p', { class: 'muted small' }, 'Шкала от 1 до 12: внизу — неприятно и мало энергии, вверху — приятно и много энергии.'));
}

// ---------- 3. Частые эмоции ----------
function topCard(data, emo) {
  const max = Math.max(1, ...data.top.emotions.map((e) => e.count));
  return card('Частые эмоции',
    h('div', { class: 'bars' }, data.top.emotions.map((e) => h('div', { class: 'bar-row' },
      h('span', { class: 'bar-label' }, e.name),
      h('span', { class: 'bar-track' }, h('span', { class: 'bar', style: { width: `${(e.count / max) * 100}%`, background: `var(--q-${e.quadrant})` } })),
      h('span', { class: 'bar-value' }, String(e.count))))),
    h('h3', { style: { marginTop: '18px' } }, 'Доли квадрантов'),
    quadBar(data.top.quadrants, data.total), quadLegend(emo, data.top.quadrants, data.total));
}

// ---------- 4. Время суток ----------
function daypartsCard(data, emo) {
  return card('Время суток',
    data.dayparts.map((p) => h('div', { class: 'part-row' },
      h('div', { class: 'part-head' }, h('b', {}, p.label), h('span', { class: 'muted small' }, `${p.total} ${records(p.total)}`)),
      p.total ? quadBar(p.quadrants, p.total) : h('div', { class: 'qbar qbar-none' }))),
    quadLegend(emo),
    h('p', { class: 'muted small' }, 'Утро 5–12, день 12–17, вечер 17–23, ночь 23–5.'));
}

// ---------- 5. Метки ----------
function tagsCard(data) {
  const enough = data.tags.filter((t) => t.diff != null);
  const few = data.tags.filter((t) => t.diff == null);
  const list = h('div', { class: 'facts' }, enough.slice(0, 15).map((t) => h('div', { class: 'fact' },
    h('div', {}, compare(`В записях с меткой «${t.name}»`, t.diff)),
    h('div', { class: 'muted small' }, `${num(t.with.avg)} с меткой (${t.with.n}) и ${num(t.without.avg)} без неё (${t.without.n})`))));
  if (!enough.length) list.append(h('p', { class: 'muted' }, `Для сравнения нужно минимум ${data.min_group} записей с меткой и без неё.`));
  return card('Метки', list,
    few.length ? h('details', { class: 'few' }, h('summary', {}, `Мало данных: ${few.length} ${plural(few.length, 'метка', 'метки', 'меток')}`),
      h('p', { class: 'muted small' }, few.map((t) => `«${t.name}» — ${t.with.n}`).join(', '))) : null);
}

// ---------- 6. Сон и спорт ----------
function sleepCard(data) {
  const sport = data.sport;
  return card('Сон и спорт',
    h('h3', {}, 'Средняя приятность дня по сну'),
    h('div', { class: 'facts' }, data.sleep.map((s) => h('div', { class: 'kv' },
      h('span', { class: 'k' }, `Сон ${s.label}`),
      s.avg != null ? h('span', {}, `${num(s.avg)} · ${s.n} ${daysWord(s.n)}`) : lowData(s.n, daysWord)))),
    h('h3', { style: { marginTop: '18px' } }, 'Спорт'),
    sport.diff != null
      ? h('div', { class: 'fact' }, h('div', {}, compare('В дни со спортом', sport.diff)),
        h('div', { class: 'muted small' }, `${num(sport.yes.avg)} со спортом (${sport.yes.n}) и ${num(sport.no.avg)} без (${sport.no.n})`))
      : h('p', { class: 'muted' }, `Мало данных: ${sport.yes.n} ${daysWord(sport.yes.n)} со спортом и ${sport.no.n} без. Нужно минимум ${data.min_group} в каждой группе.`));
}

// ---------- 7. План ----------
function planCard(data) {
  const p = data.plan;
  return card('План на день',
    p.diff != null
      ? h('div', { class: 'fact' }, h('div', {}, compare('Вечером в дни с планом', p.diff)),
        h('div', { class: 'muted small' }, `${num(p.yes.avg)} с планом (${p.yes.n}) и ${num(p.no.avg)} без (${p.no.n})`))
      : h('p', { class: 'muted' }, `Мало данных: ${p.yes.n} ${daysWord(p.yes.n)} с планом и ${p.no.n} без, у которых есть вечерняя отметка. Нужно минимум ${data.min_group} в каждой группе.`));
}

export default async function analytics(view) {
  const emo = await emotions();
  let period = 'month';
  try { period = localStorage.getItem(PERIOD_KEY) || 'month'; } catch (e) { /* нет хранилища */ }
  let month = null;
  const chips = h('div', { class: 'filters' });
  const body = h('div');

  async function load() {
    fill(chips, PERIODS.map(([key, label]) => h('button', {
      class: 'chip', 'aria-pressed': String(key === period),
      onclick: () => { period = key; try { localStorage.setItem(PERIOD_KEY, key); } catch (e) { /* ok */ } load(); },
    }, label)));
    const q = new URLSearchParams({ period });
    if (month) q.set('month', month);
    const data = await api.get(`/api/analytics?${q}`);
    const cal = calendarCard(data, emo, (m) => { month = m; load(); });
    if (!data.total) {
      fill(body, cal, h('div', { class: 'empty' }, 'За этот период записей нет'));
      return;
    }
    fill(body, cal, dynamicsCard(data), topCard(data, emo), daypartsCard(data, emo),
      tagsCard(data), sleepCard(data), planCard(data),
      h('p', { class: 'muted small', style: { textAlign: 'center' } },
        `${data.total} ${records(data.total)} с ${shortDate(data.start)} по ${shortDate(data.end)}. Сравнения показывают совпадения, а не причины.`));
  }

  add(view, h('h1', {}, 'Аналитика'), chips, body);
  await load();
}
