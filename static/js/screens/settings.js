import { api } from '../api.js';
import { currentUser, onLoggedOut } from '../app.js';
import * as push from '../push.js';
import { invalidateTags } from '../store.js';
import { add, confirmSheet, getTheme, h, setTheme, showError, switchRow, toast } from '../ui.js';

const REPEAT_OPTIONS = [30, 45, 60, 90, 120];

export default async function settings(view) {
  const [st, tzList] = await Promise.all([api.get('/api/settings'), api.get('/api/timezones')]);
  push.preload();

  let saveTimer;
  let pending = null;
  const save = (patch, quiet = false) => {
    Object.assign(st, patch);
    return api.put('/api/settings', patch).then(() => { if (!quiet) toast('Сохранено'); }).catch(showError);
  };
  // Тексты уведомлений сохраняются после паузы в наборе.
  const saveLater = (patch) => {
    pending = { ...(pending || {}), ...patch };
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => { const p = pending; pending = null; save(p); }, 700);
  };

  // ---------- Уведомления ----------
  const pushStatus = h('p', { class: 'muted', style: { margin: '0 0 14px' } }, 'Проверяю…');
  const enableBtn = h('button', { class: 'btn primary block', hidden: true }, 'Включить уведомления');
  const testBtn = h('button', { class: 'btn block', hidden: true, style: { marginTop: '10px' } }, 'Отправить тестовое');

  async function refreshPush() {
    const reason = push.blockedReason();
    if (reason) {
      pushStatus.textContent = reason;
      enableBtn.hidden = true;
      testBtn.hidden = true;
      return;
    }
    try {
      const s = await push.status();
      if (s.subscribed && s.this_device) {
        pushStatus.textContent = `Включены на этом устройстве. Всего устройств: ${s.devices}.`;
        enableBtn.hidden = true;
      } else {
        pushStatus.textContent = s.devices ? `Не включены на этом устройстве (на других: ${s.devices}).` : 'Не включены.';
        enableBtn.hidden = false;
      }
      testBtn.hidden = !s.devices;
    } catch (e) { pushStatus.textContent = e.message; }
  }
  enableBtn.addEventListener('click', async () => {
    enableBtn.disabled = true;
    try { await push.enable(); toast('Уведомления включены'); } catch (e) { showError(e); }
    enableBtn.disabled = false;
    refreshPush();
  });
  testBtn.addEventListener('click', async () => {
    testBtn.disabled = true;
    try {
      const r = await api.post('/api/push/test');
      toast(r.sent ? 'Отправлено — уведомление придёт через несколько секунд' : 'Не удалось отправить');
    } catch (e) { showError(e); }
    testBtn.disabled = false;
    refreshPush();
  });
  refreshPush();

  // ---------- Утро и вечер ----------
  const timeBlock = (kind, title) => {
    const time = h('input', { class: 'input', type: 'time', value: st[`${kind}_time`] });
    time.addEventListener('change', () => { if (time.value) save({ [`${kind}_time`]: time.value }); });
    const text = h('textarea', { class: 'input', maxlength: '200', style: { minHeight: '80px' } });
    text.value = st[`${kind}_text`];
    text.addEventListener('input', () => { if (text.value.trim()) saveLater({ [`${kind}_text`]: text.value }); });
    const details = h('div', { hidden: !st[`${kind}_enabled`], style: { marginTop: '12px' } },
      h('label', { class: 'field' }, h('span', {}, 'Время'), time),
      h('label', { class: 'field', style: { marginBottom: 0 } }, h('span', {}, 'Текст уведомления'), text));
    return h('div', { class: 'card' },
      switchRow(title, st[`${kind}_enabled`], (v) => { details.hidden = !v; save({ [`${kind}_enabled`]: v }); }),
      details);
  };

  const repeatSelect = h('select', { class: 'input' },
    REPEAT_OPTIONS.map((m) => h('option', { value: String(m) }, `через ${m} минут`)));
  if (!REPEAT_OPTIONS.includes(st.repeat_after_min)) repeatSelect.append(h('option', { value: String(st.repeat_after_min) }, `через ${st.repeat_after_min} минут`));
  repeatSelect.value = String(st.repeat_after_min);
  repeatSelect.addEventListener('change', () => save({ repeat_after_min: Number(repeatSelect.value) }));
  const repeatDetails = h('div', { hidden: !st.repeat_enabled, style: { marginTop: '12px' } }, repeatSelect);

  // ---------- Часовой пояс ----------
  const tzSelect = h('select', { class: 'input' }, tzList.map((z) => h('option', { value: z }, z.replace(/_/g, ' '))));
  tzSelect.value = st.timezone;
  tzSelect.addEventListener('change', () => save({ timezone: tzSelect.value }));
  const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const detectBtn = h('button', {
    class: 'btn small', style: { marginTop: '10px' }, hidden: !detected || detected === st.timezone,
    onclick: () => { tzSelect.value = detected; save({ timezone: detected }); detectBtn.hidden = true; },
  }, `Определить автоматически: ${detected}`);

  // ---------- Аккаунт ----------
  const logout = async () => {
    try { await api.post('/api/auth/logout'); } catch (e) { /* всё равно выходим */ }
    onLoggedOut();
  };
  const wipe = async () => {
    const pwd = await confirmSheet({
      title: 'Удалить все данные?',
      text: 'Все отметки, дни, заметки, метки и файлы будут стёрты без возможности восстановления. Учётная запись останется.',
      confirmLabel: 'Удалить всё', danger: true, withPassword: true,
    });
    if (!pwd) return;
    try {
      await api.post('/api/account/wipe', { password: pwd });
      invalidateTags();
      toast('Все данные удалены');
      location.hash = '#/';
    } catch (e) { showError(e); }
  };

  // ---------- Выгрузка ----------
  const exportPeriod = h('select', { class: 'input', 'aria-label': 'Период выгрузки' },
    [['all', 'За всё время'], ['year', 'За год'], ['3months', 'За 3 месяца'], ['month', 'За месяц'], ['week', 'За неделю']]
      .map(([v, t]) => h('option', { value: v }, t)));
  const exportBtn = h('button', { class: 'btn block', style: { marginTop: '10px' } }, 'Скачать в Excel');
  exportBtn.addEventListener('click', async () => {
    exportBtn.disabled = true;
    try {
      const res = await fetch(`/api/export.xlsx?period=${exportPeriod.value}`, { credentials: 'same-origin' });
      if (!res.ok) throw new Error('Не удалось сформировать файл');
      const name = (res.headers.get('content-disposition') || '').match(/filename="([^"]+)"/)?.[1] || 'feel.xlsx';
      const blob = await res.blob();
      const file = new File([blob], name, { type: blob.type });
      // В приложении с экрана «Домой» скачивание неудобно — отдаём файл в меню «Поделиться».
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        try { await navigator.share({ files: [file] }); } catch (e) { if (e.name !== 'AbortError') throw e; }
      } else {
        const url = URL.createObjectURL(blob);
        const a = h('a', { href: url, download: name });
        document.body.append(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 10000);
      }
    } catch (e) { showError(e); }
    exportBtn.disabled = false;
  });
  const usageText = h('p', { class: 'muted small', style: { margin: '12px 0 0' } });
  api.get('/api/media-usage').then((u) => {
    const mb = (b) => (b / 1024 / 1024).toFixed(1).replace('.', ',');
    usageText.textContent = `Фото и голос занимают ${mb(u.used)} МБ из ${Math.round(u.quota / 1024 / 1024)} МБ.`;
  }).catch(() => {});

  // ---------- Оформление ----------
  const themes = [['system', 'Как в системе'], ['light', 'Светлая'], ['dark', 'Тёмная']];
  const themeBox = h('div', { class: 'segmented', role: 'radiogroup', 'aria-label': 'Тема' });
  const drawThemes = () => themeBox.replaceChildren(...themes.map(([key, label]) => h('button', {
    role: 'radio', 'aria-checked': String(getTheme() === key), 'aria-pressed': String(getTheme() === key),
    onclick: () => { setTheme(key); drawThemes(); },
  }, label)));
  drawThemes();

  const user = currentUser();
  add(view,
    h('h1', {}, 'Настройки'),
    h('div', { class: 'section-title', style: { marginTop: '24px' } }, 'Уведомления'),
    h('div', { class: 'card' }, pushStatus, enableBtn, testBtn),
    timeBlock('morning', 'Утро'),
    timeBlock('evening', 'Вечер'),
    h('div', { class: 'card' },
      switchRow('Повторить, если не отмечено', st.repeat_enabled, (v) => { repeatDetails.hidden = !v; save({ repeat_enabled: v }); }),
      repeatDetails),

    h('div', { class: 'section-title', style: { marginTop: '24px' } }, 'Оформление'),
    h('div', { class: 'card' }, themeBox),

    h('div', { class: 'section-title', style: { marginTop: '24px' } }, 'Часовой пояс'),
    h('div', { class: 'card' }, tzSelect, detectBtn),

    h('div', { class: 'section-title', style: { marginTop: '24px' } }, 'Метки'),
    h('a', { class: 'card tap card-row', href: '#/tags' },
      h('div', {}, h('h3', { style: { margin: 0 } }, 'Редактировать метки'),
        h('span', { class: 'muted small' }, 'С кем, где, чем занят')),
      h('span', { class: 'chev' })),

    h('div', { class: 'section-title', style: { marginTop: '24px' } }, 'Выгрузка'),
    h('div', { class: 'card' }, exportPeriod, exportBtn, usageText),

    h('div', { class: 'section-title', style: { marginTop: '24px' } }, 'Аккаунт'),
    h('div', { class: 'card' },
      h('p', { class: 'muted' }, user ? user.email : ''),
      h('button', { class: 'btn block', onclick: logout }, 'Выйти'),
      h('button', { class: 'btn danger block', style: { marginTop: '8px' }, onclick: wipe }, 'Удалить все данные')));

  return () => {
    clearTimeout(saveTimer);
    if (pending) save(pending, true);
  };
}
