// Редактирование меток: добавить, переименовать, упорядочить, скрыть.
import { api } from '../api.js';
import { GROUPS, invalidateTags, tags as loadTags } from '../store.js';
import { add, h, showError, topbar } from '../ui.js';

export default async function tags(view) {
  const tagsBox = h('div');
  async function drawTags(force) {
    const all = await loadTags(force);
    tagsBox.replaceChildren(...GROUPS.map((g) => {
      const items = all.filter((t) => t.group === g.id);
      const move = async (idx, delta) => {
        const ids = items.map((t) => t.id);
        const j = idx + delta;
        if (j < 0 || j >= ids.length) return;
        [ids[idx], ids[j]] = [ids[j], ids[idx]];
        try { await api.put('/api/tags/order', { group: g.id, ids }); invalidateTags(); drawTags(true); } catch (e) { showError(e); }
      };
      const newTag = h('input', { class: 'input', placeholder: 'Новая метка', maxlength: '60', enterkeyhint: 'done' });
      newTag.addEventListener('keydown', async (ev) => {
        if (ev.key !== 'Enter' || !newTag.value.trim()) return;
        ev.preventDefault();
        try { await api.post('/api/tags', { group: g.id, name: newTag.value }); invalidateTags(); drawTags(true); } catch (e) { showError(e); }
      });
      return h('div', { class: 'card' },
        h('h3', {}, g.title),
        items.map((t, i) => h('div', { class: 'list-row' },
          h('span', { class: `name${t.hidden ? ' hidden-tag' : ''}` }, t.name),
          h('button', { class: 'icon-btn', 'aria-label': `Переименовать ${t.name}`, onclick: async () => {
            const name = prompt('Новое название', t.name);
            if (!name || !name.trim() || name === t.name) return;
            try { await api.patch(`/api/tags/${t.id}`, { name }); invalidateTags(); drawTags(true); } catch (e) { showError(e); }
          } }, '✎'),
          h('button', { class: 'icon-btn', 'aria-label': 'Выше', disabled: i === 0, onclick: () => move(i, -1) }, '↑'),
          h('button', { class: 'icon-btn', 'aria-label': 'Ниже', disabled: i === items.length - 1, onclick: () => move(i, 1) }, '↓'),
          h('button', { class: 'icon-btn', 'aria-label': t.hidden ? `Показать ${t.name}` : `Скрыть ${t.name}`, onclick: async () => {
            try { await api.patch(`/api/tags/${t.id}`, { hidden: !t.hidden }); invalidateTags(); drawTags(true); } catch (e) { showError(e); }
          } }, t.hidden ? '◌' : '●'))),
        h('div', { style: { marginTop: '12px' } }, newTag));
    }));
  }

  add(view, topbar('Метки', '#/settings'), h('h1', {}, 'Метки'),
    h('p', { class: 'subtitle' }, 'Скрытые метки не предлагаются при новой отметке, но остаются в старых записях.'),
    tagsBox);
  await drawTags(false);
}
