// Отметка эмоции: квадрант → слово → «Сохранить» (три касания) или «Дальше» → контекст.
// Параметры: src=evening|push, d=YYYY-MM-DD (вечер прошлого дня), edit=ID (правка записи).
import { api } from '../api.js';
import { go } from '../app.js';
import { openPicker, wordColors } from '../grid.js';
import { emotions, GROUPS, invalidateTags, tags as loadTags } from '../store.js';
import { confirmSheet, fill, h, showError, toast, topbar } from '../ui.js';

const QUAD_ORDER = ['red', 'yellow', 'blue', 'green'];

function nowLocalInput() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

export default async function checkin(view, params) {
  const emo = await emotions();
  const editing = params.edit ? await api.get(`/api/checkins/${encodeURIComponent(params.edit)}`) : null;
  const source = editing ? editing.source : params.src === 'evening' ? 'evening' : params.src === 'push' ? 'notification' : 'manual';
  const returnTo = source === 'evening' ? `#/evening?d=${params.d || ''}` : '#/';

  const state = {
    emotionId: editing ? editing.emotion_id : null,
    // null — «сейчас»; иначе местное время в формате datetime-local.
    occurredAt: editing ? `${editing.local_date}T${editing.local_time}`
      : (source === 'evening' && params.late === '1' && params.d ? `${params.d}T23:59` : null),
    tagIds: new Set(editing ? editing.tags.map((t) => t.id) : []),
    note: editing ? editing.note : '',
  };
  let picker = null;

  async function save() {
    const body = { emotion_id: state.emotionId, note: state.note, tag_ids: [...state.tagIds] };
    if (state.occurredAt) body.occurred_at = state.occurredAt;
    try {
      if (editing) {
        await api.patch(`/api/checkins/${editing.id}`, body);
        toast('Сохранено');
        if (picker) picker.close();
        history.back();
      } else {
        await api.post('/api/checkins', { ...body, source });
        toast('Записано');
        if (picker) picker.close();
        go(returnTo, true);
      }
    } catch (e) { showError(e); }
  }

  function pick(quadrant) {
    picker = null;
    openPicker({
      quadrant,
      selectedId: state.emotionId,
      primaryLabel: editing ? 'Готово' : 'Сохранить',
      onPrimary: async (e) => {
        state.emotionId = e.id;
        if (editing) { picker.close(); picker = null; renderContext(); return; }
        await save();
      },
      secondaryLabel: editing ? null : 'Дальше',
      onSecondary: (e) => { state.emotionId = e.id; picker.close(); picker = null; renderContext(); },
      onClose: () => { picker = null; if (!state.emotionId) renderQuadrants(); else renderContext(); },
    }).then((p) => { picker = p; });
  }

  // ---------- Шаг 1: квадранты ----------
  function renderQuadrants() {
    fill(view,
      topbar(source === 'evening' ? 'Вечер' : 'Отметка', returnTo),
      h('h1', {}, 'Как ты сейчас?'),
      h('p', { class: 'subtitle' }, 'Выбери ближе всего к ощущению'),
      h('div', { class: 'axis-hint' }, h('span', {}, '↑ больше энергии')),
      h('div', { class: 'quads' }, QUAD_ORDER.map((q) => {
        const meta = emo.quadrants.get(q);
        const c = wordColors(q, 6);
        return h('button', { class: 'quad', style: { background: c.bg, color: c.fg }, onclick: () => pick(q) }, meta.title);
      })),
      h('div', { class: 'axis-hint' }, h('span', {}, '← неприятнее'), h('span', {}, 'приятнее →')),
      h('div', { class: 'axis-hint', style: { marginTop: '6px' } }, h('span', {}, '↓ меньше энергии')));
  }

  // ---------- Шаг 2: контекст и заметка ----------
  async function renderContext() {
    const e = emo.byId.get(state.emotionId);
    const allTags = await loadTags();
    const c = wordColors(e.quadrant, Math.max(4, e.intensity));

    const timeInput = h('input', { class: 'input', type: 'datetime-local', max: nowLocalInput(), value: state.occurredAt || nowLocalInput() });
    timeInput.addEventListener('change', () => { state.occurredAt = timeInput.value || null; });
    const timeField = h('label', { class: 'field', hidden: !state.occurredAt }, h('span', {}, 'Время записи'), timeInput);
    const timeToggle = h('button', {
      class: 'chip', hidden: !!state.occurredAt,
      onclick: () => { timeToggle.hidden = true; timeField.hidden = false; state.occurredAt = timeInput.value; },
    }, 'Время: сейчас · изменить');

    const note = h('textarea', { class: 'input', placeholder: 'Что происходит? Что повлияло?', maxlength: '10000' });
    note.value = state.note || '';
    note.addEventListener('input', () => { state.note = note.value; });

    const groups = GROUPS.map((g) => {
      const box = h('div', { class: 'chips' });
      const draw = () => {
        const list = allTags.filter((t) => t.group === g.id && (!t.hidden || state.tagIds.has(t.id)));
        box.replaceChildren(...list.map((t) => {
          const chip = h('button', { class: 'chip', 'aria-pressed': String(state.tagIds.has(t.id)) }, t.name);
          chip.addEventListener('click', () => {
            if (state.tagIds.has(t.id)) state.tagIds.delete(t.id); else state.tagIds.add(t.id);
            chip.setAttribute('aria-pressed', String(state.tagIds.has(t.id)));
          });
          return chip;
        }), addChip());
      };
      const addChip = () => {
        const btn = h('button', { class: 'chip add' }, '+ своя');
        btn.addEventListener('click', () => {
          const input = h('input', { class: 'chip-input', placeholder: 'Название', maxlength: '60', enterkeyhint: 'done' });
          let done = false;
          const commit = async () => {
            if (done) return;
            done = true;
            const name = input.value.trim();
            if (!name) { draw(); return; }
            try {
              const tag = await api.post('/api/tags', { group: g.id, name });
              invalidateTags();
              const idx = allTags.findIndex((t) => t.id === tag.id);
              if (idx >= 0) allTags[idx] = tag; else allTags.push(tag);
              state.tagIds.add(tag.id);
            } catch (err) { showError(err); }
            draw();
          };
          input.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') { ev.preventDefault(); commit(); } });
          input.addEventListener('blur', commit);
          btn.replaceWith(input);
          input.focus();
        });
        return btn;
      };
      draw();
      return h('div', { class: 'section' }, h('div', { class: 'section-title' }, g.title), box);
    });

    const saveBtn = h('button', { class: 'btn primary block big', onclick: async () => { saveBtn.disabled = true; await save(); saveBtn.disabled = false; } }, 'Сохранить');

    fill(view,
      topbar(editing ? 'Запись' : 'Контекст', returnTo),
      h('button', {
        class: 'card tap card-row', style: { width: '100%', border: 0, textAlign: 'left', background: c.bg, color: c.fg },
        onclick: () => pick(e.quadrant), 'aria-label': `${e.name}. Изменить эмоцию`,
      },
      h('div', {}, h('div', { style: { fontSize: '28px', fontWeight: 800 } }, e.name),
        h('div', { style: { opacity: 0.85 } }, e.description)),
      h('span', { style: { fontSize: '15px', fontWeight: 650, opacity: 0.85 } }, 'Изменить')),
      h('div', { style: { marginTop: '12px' } }, timeToggle, timeField),
      groups,
      h('div', { class: 'section' }, h('div', { class: 'section-title' }, 'Заметка'), note),
      h('div', { class: 'sticky-bottom' }, saveBtn),
      editing ? h('button', {
        class: 'btn danger block', style: { marginTop: '12px' },
        onclick: async () => {
          const ok = await confirmSheet({ title: 'Удалить запись?', text: 'Это действие нельзя отменить.', confirmLabel: 'Удалить', danger: true });
          if (!ok) return;
          try { await api.del(`/api/checkins/${editing.id}`); toast('Удалено'); history.back(); } catch (err) { showError(err); }
        },
      }, 'Удалить запись') : null);
  }

  if (editing) renderContext();
  else if (params.q && QUAD_ORDER.includes(params.q)) { renderQuadrants(); pick(params.q); }
  else renderQuadrants();

  return () => { if (picker) picker.close(); };
}
