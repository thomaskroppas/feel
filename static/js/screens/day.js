// День целиком: утро, отметки, вечер, сон, спорт.
import { api } from '../api.js';
import { add, h, fmtDayLong, fmtHours, topbar } from '../ui.js';
import { mediaPreview } from '../media.js';
import { entryRow } from './diary.js';

function kv(k, v) {
  return h('div', { class: 'kv' }, h('span', { class: 'k' }, k), h('span', {}, v));
}

export default async function day(view, params, match) {
  const date = match[1];
  const d = await api.get(`/api/days/${date}`);
  const log = d.day_log || {};

  const planText = log.plan_status === 'yes' ? 'есть' : log.plan_status === 'no' ? 'нет' : 'не отмечено';
  const sleep = log.sleep_hours != null
    ? `${fmtHours(log.sleep_hours)}${log.sleep_quality ? `, качество ${log.sleep_quality} из 5` : ''}`
    : (log.sleep_quality ? `качество ${log.sleep_quality} из 5` : '—');
  const sport = log.sport_type == null ? '—'
    : log.sport_type === '' ? 'не было'
      : `${log.sport_type}${log.sport_minutes ? `, ${log.sport_minutes} мин` : ''}`;

  add(view,
    topbar('День', '#/diary'),
    h('h1', {}, fmtDayLong(date)),
    d.quadrant ? h('p', { class: 'subtitle' }, h('span', { class: 'status-pill' },
      h('span', { class: 'dot s', style: { background: `var(--q-${d.quadrant})` } }), 'цвет дня')) : h('p', { class: 'subtitle' }),

    h('div', { class: 'section-title' }, 'Утро'),
    h('a', { class: 'card tap', href: `#/morning?d=${date}` },
      kv('План', planText),
      log.plan_text ? h('div', { class: 'pre', style: { padding: '10px 0' } }, log.plan_text) : null,
      kv('Сон', sleep)),

    h('div', { class: 'section-title', style: { marginTop: '24px' } }, 'Отметки'),
    d.checkins.length ? [...d.checkins].reverse().map(entryRow) : h('div', { class: 'card muted' }, 'Отметок нет'),

    h('div', { class: 'section-title', style: { marginTop: '24px' } }, 'Вечер'),
    h('a', { class: 'card tap', href: `#/evening?d=${date}` },
      h('div', { class: 'k muted', style: { marginBottom: '6px' } }, 'Итоги дня'),
      h('div', { class: 'pre', style: { marginBottom: '10px' } }, log.day_summary || '—'),
      kv('Спорт', sport)),
    d.media && d.media.length ? h('div', { class: 'card' }, mediaPreview(d.media, { large: true })) : null,

    h('a', { class: 'btn block', href: `#/checkin`, style: { marginTop: '12px' } }, 'Отметиться сейчас'));
}
