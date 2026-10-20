// После первого входа: включить уведомления и выбрать время утра и вечера.
import { api } from '../api.js';
import { go } from '../app.js';
import * as push from '../push.js';
import { add, h, showError, toast } from '../ui.js';

export default async function welcome(view) {
  const st = await api.get('/api/settings');
  push.preload();
  // Часовой пояс определяем автоматически, его можно поменять в настройках.
  const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
  if (detected && detected !== st.timezone) {
    try { await api.put('/api/settings', { timezone: detected }); } catch (e) { /* оставим как было */ }
  }

  const morning = h('input', { class: 'input', type: 'time', value: st.morning_time });
  const evening = h('input', { class: 'input', type: 'time', value: st.evening_time });
  const reason = push.blockedReason();
  const status = h('p', { class: 'muted small' }, reason || '');
  const enableBtn = h('button', {
    class: 'btn primary block big', disabled: !!reason,
    onclick: async () => {
      enableBtn.disabled = true;
      try {
        await push.enable();
        enableBtn.textContent = 'Уведомления включены';
        toast('Уведомления включены');
      } catch (e) {
        status.textContent = e.message;
        enableBtn.disabled = false;
      }
    },
  }, 'Включить уведомления');

  const finish = async () => {
    try {
      await api.put('/api/settings', { morning_time: morning.value || '08:30', evening_time: evening.value || '21:30' });
      try { localStorage.setItem('feel.onboarded', '1'); } catch (e) { /* нет хранилища */ }
      go('#/', true);
    } catch (e) { showError(e); }
  };

  add(view,
    h('h1', {}, 'Два напоминания в день'),
    h('p', { class: 'subtitle' }, 'Утром — про план на день, вечером — про итоги дня и настроение.'),
    h('div', { class: 'card' }, enableBtn, status),
    h('div', { class: 'card' },
      h('label', { class: 'field' }, h('span', {}, 'Утро'), morning),
      h('label', { class: 'field', style: { marginBottom: 0 } }, h('span', {}, 'Вечер'), evening)),
    h('div', { class: 'sticky-bottom' }, h('button', { class: 'btn block big', onclick: finish }, 'Готово')));
}
