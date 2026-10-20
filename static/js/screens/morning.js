// Утро: план на день и сон.
import { api } from '../api.js';
import { go } from '../app.js';
import { add, h, fmtDayLong, fmtHours, showError, toast, topbar } from '../ui.js';

const QUALITY = ['Плохо', '', 'Нормально', '', 'Отлично'];

export function sleepFields(state) {
  const value = h('div', { class: 'stepper-value' });
  const draw = () => { value.textContent = state.sleep_hours == null ? '—' : fmtHours(state.sleep_hours); };
  const step = (delta) => {
    const base = state.sleep_hours == null ? (delta > 0 ? 7 : 7.5) : state.sleep_hours;
    state.sleep_hours = Math.max(0, Math.min(16, base + delta));
    draw();
  };
  draw();

  const scale = h('div', { class: 'scale', role: 'radiogroup', 'aria-label': 'Качество сна' });
  const drawScale = () => scale.replaceChildren(...[1, 2, 3, 4, 5].map((n) => h('button', {
    role: 'radio', 'aria-checked': String(state.sleep_quality === n), 'aria-pressed': String(state.sleep_quality === n),
    onclick: () => { state.sleep_quality = state.sleep_quality === n ? null : n; drawScale(); },
  }, String(n))));
  drawScale();

  return h('div', { class: 'card' },
    h('h3', {}, 'Сон'),
    h('div', { class: 'card-row', style: { margin: '6px 0 18px' } },
      h('span', { class: 'muted' }, 'Часов'),
      h('div', { class: 'stepper' },
        h('button', { class: 'icon-btn', 'aria-label': 'Меньше на полчаса', onclick: () => step(-0.5) }, '−'),
        value,
        h('button', { class: 'icon-btn', 'aria-label': 'Больше на полчаса', onclick: () => step(0.5) }, '+'))),
    h('div', { class: 'muted', style: { marginBottom: '8px' } }, 'Качество'),
    scale,
    h('div', { class: 'scale-labels' }, QUALITY.filter(Boolean).map((t) => h('span', {}, t))));
}

export default async function morning(view, params) {
  const todayData = await api.get('/api/today');
  const date = params.d || todayData.date;
  const day = await api.get(`/api/days/${date}`);
  const log = day.day_log || {};
  const state = {
    plan_status: log.plan_status || null,
    plan_text: log.plan_text || '',
    sleep_hours: log.sleep_hours ?? null,
    sleep_quality: log.sleep_quality ?? null,
  };

  const plan = h('textarea', { class: 'input', maxlength: '10000' });
  plan.value = state.plan_text;
  plan.addEventListener('input', () => { state.plan_text = plan.value; });

  const yes = h('button', { class: 'btn' }, 'Есть');
  const no = h('button', { class: 'btn' }, 'Нет');
  const hint = h('p', { class: 'muted' });
  const remindStatus = h('p', { class: 'muted small', style: { margin: '10px 0 0' } });
  const remindBtn = h('button', { class: 'btn block', style: { marginTop: '12px' } }, 'Напомнить через 30 минут');
  const planBlock = h('div', { style: { marginTop: '18px' } }, hint, plan, remindBtn, remindStatus);

  const showRemind = (iso) => {
    if (!iso) { remindStatus.textContent = ''; return; }
    const t = new Date(iso);
    remindStatus.textContent = `Напомню в ${t.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}`;
  };
  showRemind(log.plan_remind_at);

  const drawPlan = () => {
    yes.setAttribute('aria-pressed', String(state.plan_status === 'yes'));
    no.setAttribute('aria-pressed', String(state.plan_status === 'no'));
    planBlock.hidden = !state.plan_status;
    if (state.plan_status === 'no') {
      hint.textContent = 'Выдели 30 минут на план';
      plan.placeholder = 'План на день';
      remindBtn.hidden = false;
    } else {
      hint.textContent = 'Можно вписать план — вечером он будет перед глазами';
      plan.placeholder = 'План (необязательно)';
      remindBtn.hidden = true;
      remindStatus.textContent = '';
    }
  };
  yes.addEventListener('click', () => { state.plan_status = 'yes'; drawPlan(); });
  no.addEventListener('click', () => { state.plan_status = 'no'; drawPlan(); });
  drawPlan();

  const body = () => ({
    plan_status: state.plan_status, plan_text: state.plan_text,
    sleep_hours: state.sleep_hours, sleep_quality: state.sleep_quality,
  });

  remindBtn.addEventListener('click', async () => {
    remindBtn.disabled = true;
    try {
      await api.put(`/api/days/${date}`, body());
      const res = await api.post(`/api/days/${date}/plan-reminder`);
      showRemind(res.day_log.plan_remind_at);
      toast('Напомню через 30 минут');
    } catch (e) { showError(e); }
    remindBtn.disabled = false;
  });

  const saveBtn = h('button', {
    class: 'btn primary block big',
    onclick: async () => {
      if (!state.plan_status) { toast('Ответь, есть ли план на день'); return; }
      saveBtn.disabled = true;
      try {
        await api.put(`/api/days/${date}`, body());
        toast('Сохранено');
        go('#/', true);
      } catch (e) { showError(e); saveBtn.disabled = false; }
    },
  }, 'Готово');

  add(view,
    topbar('Утро', '#/'),
    h('h1', {}, 'Доброе утро'),
    h('p', { class: 'subtitle' }, fmtDayLong(date)),
    h('div', { class: 'card' },
      h('h2', {}, 'План на день есть?'),
      h('div', { class: 'choice' }, yes, no),
      planBlock),
    sleepFields(state),
    h('div', { class: 'sticky-bottom' }, saveBtn));
}
