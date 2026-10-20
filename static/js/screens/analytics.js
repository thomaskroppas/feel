import { add, h } from '../ui.js';

export default function analytics(view) {
  add(view,
    h('h1', {}, 'Аналитика'),
    h('div', { class: 'card' },
      h('h3', {}, 'Скоро'),
      h('p', { class: 'muted', style: { margin: 0 } },
        'Календарь настроения, динамика, частые эмоции, метки, сон и спорт появятся на втором этапе. Записи уже копятся для отчётов.')));
}
