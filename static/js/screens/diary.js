// Дневник: записи по дням, новые сверху; фильтр по квадранту и метке.
import { api } from '../api.js';
import { emotions, GROUPS, tags as loadTags } from '../store.js';
import { mediaPreview } from '../media.js';
import { add, h, fmtDayShort, fmtHours } from '../ui.js';

const FILTER_KEY = 'feel.diary.filter';
const SHORT = { red: '↑ неприятно', yellow: '↑ приятно', blue: '↓ неприятно', green: '↓ приятно' };

export function entryRow(c) {
  const tagText = c.tags.map((t) => t.name).join(' · ');
  return h('a', { class: 'entry', href: `#/checkin?edit=${c.id}` },
    h('span', { class: 'dot', style: { background: `var(--q-${c.emotion.quadrant})` } }),
    h('div', { class: 'body' },
      h('div', {},
        h('span', { class: 'w' }, c.emotion.name),
        h('span', { class: 't' }, c.local_time),
        c.source === 'evening' ? h('span', { class: 't' }, '· вечер') : null),
      tagText ? h('div', { class: 'tags' }, tagText) : null,
      c.note ? h('div', { class: 'note' }, c.note) : null,
      mediaPreview(c.media)));
}

export function dayMeta(log) {
  if (!log) return '';
  const parts = [];
  if (log.plan_status === 'yes') parts.push('план ✓');
  if (log.plan_status === 'no') parts.push('без плана');
  if (log.sleep_hours != null) parts.push(`сон ${fmtHours(log.sleep_hours)}`);
  if (log.sport_type) parts.push(log.sport_minutes ? `${log.sport_type} ${log.sport_minutes} мин` : log.sport_type);
  return parts.join(' · ');
}

function loadFilter() {
  try { return JSON.parse(sessionStorage.getItem(FILTER_KEY)) || {}; } catch (e) { return {}; }
}

function saveFilter(f) {
  try { sessionStorage.setItem(FILTER_KEY, JSON.stringify(f)); } catch (e) { /* нет хранилища */ }
}

export default async function diary(view) {
  const [emo, allTags] = await Promise.all([emotions(), loadTags()]);
  const filter = loadFilter();
  const list = h('div');
  const more = h('button', { class: 'btn block', hidden: true, style: { marginTop: '16px' } }, 'Показать ещё');
  let nextBefore = null;

  const quadChips = h('div', { class: 'filters' });
  const drawQuadChips = () => {
    quadChips.replaceChildren(
      h('button', { class: 'chip', 'aria-pressed': String(!filter.quadrant), onclick: () => setFilter({ quadrant: null }) }, 'Все'),
      ...['red', 'yellow', 'blue', 'green'].map((q) => h('button', {
        class: 'chip', 'aria-pressed': String(filter.quadrant === q),
        'aria-label': emo.quadrants.get(q).title,
        onclick: () => setFilter({ quadrant: filter.quadrant === q ? null : q }),
      }, h('span', { class: 'dot s', style: { background: `var(--q-${q})` } }), SHORT[q])),
      tagSelect);
  };

  const tagSelect = h('select', { class: 'chip', 'aria-label': 'Метка', style: { paddingRight: '16px' } },
    h('option', { value: '' }, 'Все метки'),
    GROUPS.map((g) => h('optgroup', { label: g.title },
      allTags.filter((t) => t.group === g.id).map((t) => h('option', { value: String(t.id) }, t.name)))));
  tagSelect.value = filter.tag_id ? String(filter.tag_id) : '';
  tagSelect.addEventListener('change', () => setFilter({ tag_id: tagSelect.value ? Number(tagSelect.value) : null }));

  function setFilter(patch) {
    Object.assign(filter, patch);
    saveFilter(filter);
    drawQuadChips();
    list.replaceChildren();
    nextBefore = null;
    load();
  }

  async function load() {
    more.disabled = true;
    const q = new URLSearchParams({ days: '14' });
    if (nextBefore) q.set('before', nextBefore);
    if (filter.quadrant) q.set('quadrant', filter.quadrant);
    if (filter.tag_id) q.set('tag_id', String(filter.tag_id));
    const data = await api.get(`/api/diary?${q}`);
    for (const d of data.days) {
      const meta = dayMeta(d.day_log);
      add(list,
        h('a', { class: 'day-head', href: `#/day/${d.date}` },
          h('span', { class: 'dot m', style: d.quadrant ? { background: `var(--q-${d.quadrant})` } : null }),
          h('span', { class: 'name' }, fmtDayShort(d.date)),
          h('span', { class: 'chev' })),
        meta ? h('div', { class: 'muted small', style: { margin: '-6px 4px 10px' } }, meta) : null,
        d.checkins.map(entryRow));
    }
    if (!list.childElementCount) {
      list.append(h('div', { class: 'empty' }, filter.quadrant || filter.tag_id ? 'Ничего не найдено' : 'Записей пока нет. Отметься на главном экране.'));
    }
    nextBefore = data.next_before;
    more.hidden = !nextBefore;
    more.disabled = false;
  }
  more.addEventListener('click', load);

  drawQuadChips();
  add(view, h('h1', {}, 'Дневник'), quadChips, list, more);
  await load();
}
