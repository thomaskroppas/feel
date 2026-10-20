// Вечер: утренний план, отметка эмоции, итоги дня, спорт.
import { api } from '../api.js';
import { go } from '../app.js';
import { add, h, fmtDayLong, showError, toast, topbar } from '../ui.js';

const SPORT_PRESETS = ['Бег', 'Зал', 'Ходьба', 'Йога', 'Велосипед', 'Плавание', 'Растяжка'];

export default async function evening(view, params) {
  const todayData = await api.get('/api/today');
  const date = params.d || todayData.date;
  const late = date !== todayData.date;
  const day = await api.get(`/api/days/${date}`);
  const log = day.day_log || {};
  const eveningCheckin = day.checkins.filter((c) => c.source === 'evening').pop();

  const state = {
    day_summary: log.day_summary || '',
    // sport: null — не заполнено, 'yes' — был, 'no' — не было.
    sport: log.sport_type == null ? null : (log.sport_type === '' ? 'no' : 'yes'),
    sport_type: log.sport_type || '',
    sport_minutes: log.sport_minutes ?? null,
  };

  // ---------- План ----------
  let planCard = null;
  if (log.plan_text) {
    planCard = h('div', { class: 'card' }, h('h3', {}, 'План на день'), h('div', { class: 'pre' }, log.plan_text));
  } else if (log.plan_status) {
    planCard = h('div', { class: 'card' }, h('h3', {}, 'План на день'),
      h('p', { class: 'muted', style: { margin: 0 } }, log.plan_status === 'yes' ? 'План был, но не записан' : 'Плана не было'));
  }

  // ---------- Эмоция ----------
  const checkinHref = `#/checkin?src=evening&d=${date}${late ? '&late=1' : ''}`;
  const emotionCard = eveningCheckin
    ? h('a', { class: 'card tap card-row', href: `#/checkin?edit=${eveningCheckin.id}` },
      h('div', {}, h('h3', {}, 'Как ты сейчас'),
        h('span', { class: 'status-pill' },
          h('span', { class: 'dot m', style: { background: `var(--q-${eveningCheckin.emotion.quadrant})` } }),
          eveningCheckin.emotion.name)),
      h('span', { class: 'chev' }))
    : h('div', { class: 'card' },
      h('h3', {}, 'Как ты сейчас?'),
      h('p', { class: 'muted' }, 'Отметь эмоцию — это главное за вечер'),
      h('button', {
        class: 'btn primary block big',
        onclick: async () => {
          // Уже написанные итоги не должны пропасть при переходе к отметке.
          const body = buildBody(true);
          if (body && (body.day_summary || 'sport_type' in body)) {
            try { await api.put(`/api/days/${date}`, body); } catch (e) { /* сохранится позже */ }
          }
          go(checkinHref);
        },
      }, 'Отметить эмоцию'));

  // ---------- Итоги ----------
  const summary = h('textarea', { class: 'input', placeholder: 'Как прошёл день? Что запомнилось?', maxlength: '20000' });
  summary.value = state.day_summary;
  summary.addEventListener('input', () => { state.day_summary = summary.value; });

  // ---------- Спорт ----------
  const was = h('button', { class: 'btn' }, 'Был');
  const wasnt = h('button', { class: 'btn' }, 'Не было');
  const type = h('input', { class: 'input', placeholder: 'Вид спорта', maxlength: '100' });
  type.value = state.sport_type;
  type.addEventListener('input', () => { state.sport_type = type.value; drawPresets(); });
  const minutes = h('input', { class: 'input', type: 'number', inputmode: 'numeric', min: '0', max: '1440', placeholder: 'Минут' });
  minutes.value = state.sport_minutes ?? '';
  minutes.addEventListener('input', () => { state.sport_minutes = minutes.value === '' ? null : Number(minutes.value); });
  const presets = h('div', { class: 'chips', style: { margin: '12px 0' } });
  const drawPresets = () => presets.replaceChildren(...SPORT_PRESETS.map((p) => h('button', {
    class: 'chip', 'aria-pressed': String(state.sport_type.trim() === p),
    onclick: () => { state.sport_type = p; type.value = p; drawPresets(); },
  }, p)));
  const sportDetails = h('div', { style: { marginTop: '14px' } }, type, presets, minutes);

  const drawSport = () => {
    was.setAttribute('aria-pressed', String(state.sport === 'yes'));
    wasnt.setAttribute('aria-pressed', String(state.sport === 'no'));
    sportDetails.hidden = state.sport !== 'yes';
    drawPresets();
  };
  was.addEventListener('click', () => { state.sport = 'yes'; drawSport(); });
  wasnt.addEventListener('click', () => { state.sport = 'no'; drawSport(); });
  drawSport();

  function buildBody(quiet) {
    const body = { day_summary: state.day_summary };
    if (state.sport === 'yes') {
      const t = state.sport_type.trim();
      if (!t) {
        if (!quiet) { toast('Укажи вид спорта или выбери «Не было»'); return null; }
        return body;
      }
      body.sport_type = t;
      body.sport_minutes = state.sport_minutes;
    } else if (state.sport === 'no') {
      body.sport_type = '';
      body.sport_minutes = null;
    }
    return body;
  }

  const saveBtn = h('button', {
    class: 'btn primary block big',
    onclick: async () => {
      const body = buildBody(false);
      if (!body) return;
      saveBtn.disabled = true;
      try {
        await api.put(`/api/days/${date}`, body);
        toast('Сохранено');
        go('#/', true);
      } catch (e) { showError(e); saveBtn.disabled = false; }
    },
  }, 'Сохранить');

  add(view,
    topbar('Вечер', '#/'),
    h('h1', {}, 'Итоги дня'),
    h('p', { class: 'subtitle' }, fmtDayLong(date)),
    planCard,
    emotionCard,
    h('div', { class: 'card' }, h('h3', {}, 'Итоги дня'), summary),
    h('div', { class: 'card' }, h('h3', {}, 'Спорт'), h('div', { class: 'choice' }, was, wasnt), sportDetails),
    h('div', { class: 'sticky-bottom' }, saveBtn));
}
