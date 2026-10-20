import { api } from '../api.js';
import * as push from '../push.js';
import { add, h, fmtDayLong, weekdayShort } from '../ui.js';

function morningStatus(log) {
  if (!log || !log.plan_status) return { text: 'Не отмечено', mark: '○' };
  return log.plan_status === 'yes' ? { text: 'План есть', mark: '✓' } : { text: 'Плана нет', mark: '—' };
}

export default async function today(view) {
  const data = await api.get('/api/today');
  const { day } = data;
  const ms = morningStatus(day.day_log);
  const evening = day.checkins.filter((c) => c.source === 'evening').pop();

  const dots = day.checkins.length
    ? h('div', { class: 'dots' }, day.checkins.map((c) =>
      h('a', { class: 'dot-item', href: `#/checkin?edit=${c.id}`, 'aria-label': `${c.emotion.name}, ${c.local_time}` },
        h('span', { class: 'dot', style: { background: `var(--q-${c.emotion.quadrant})` } }),
        h('small', {}, c.local_time))))
    : h('p', { class: 'muted', style: { margin: 0 } }, 'Пока нет отметок');

  const pushBanner = h('div');
  add(view,
    h('h1', {}, 'Сегодня'),
    h('p', { class: 'subtitle' }, fmtDayLong(data.date)),
    pushBanner,
    h('a', { class: 'card tap card-row', href: `#/morning?d=${data.date}` },
      h('div', {}, h('h3', {}, 'Утро'), h('span', { class: 'status-pill' }, ms.mark, ' ', ms.text)),
      h('span', { class: 'chev' })),
    h('div', { class: 'card' },
      h('h3', {}, 'Отметки за день'),
      dots,
      h('div', { style: { marginTop: '18px' } },
        h('a', { class: 'btn primary block big', href: '#/checkin' }, 'Отметиться'))),
    h('a', { class: 'card tap card-row', href: `#/evening?d=${data.date}` },
      h('div', {},
        h('h3', {}, 'Вечер'),
        evening
          ? h('span', { class: 'status-pill' },
            h('span', { class: 'dot s', style: { background: `var(--q-${evening.emotion.quadrant})` } }), evening.emotion.name)
          : h('span', { class: 'muted' }, 'Подвести итоги дня')),
      h('span', { class: 'chev' })),
    h('div', { class: 'section-title', style: { marginTop: '28px' } }, 'Неделя'),
    h('div', { class: 'card' },
      h('div', { class: 'week' }, data.week.map((d) =>
        h('a', { href: `#/day/${d.date}`, class: d.date === data.date ? 'today' : '', 'aria-label': `${fmtDayLong(d.date)}: ${d.count} отметок` },
          h('span', { class: 'dot', style: d.quadrant ? { background: `var(--q-${d.quadrant})` } : null }),
          h('small', {}, weekdayShort(d.date)))))));

  // Подсказка включить уведомления, если они ещё не включены на этом устройстве.
  if (!push.blockedReason()) {
    push.currentSubscription().then((sub) => {
      if (!sub) {
        pushBanner.append(h('a', { class: 'card tap card-row', href: '#/settings' },
          h('div', {}, h('h3', {}, 'Включите уведомления'), h('span', { class: 'muted small' }, 'Чтобы не пропустить утро и вечер')),
          h('span', { class: 'chev' })));
      }
    }).catch(() => {});
  }
}
