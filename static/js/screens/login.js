import { api } from '../api.js';
import { onLoggedIn } from '../app.js';
import { add, h } from '../ui.js';

export default function login(view) {
  const email = h('input', { class: 'input', type: 'email', autocomplete: 'username', inputmode: 'email', required: true, autocapitalize: 'none' });
  const password = h('input', { class: 'input', type: 'password', autocomplete: 'current-password', required: true });
  const error = h('div', { class: 'error', role: 'alert' });
  const submit = h('button', { class: 'btn primary block big', type: 'submit' }, 'Войти');

  const form = h('form', {
    onsubmit: async (ev) => {
      ev.preventDefault();
      error.textContent = '';
      submit.disabled = true;
      try {
        const user = await api.post('/api/auth/login', { email: email.value, password: password.value });
        onLoggedIn(user);
      } catch (e) {
        error.textContent = e.message;
      } finally {
        submit.disabled = false;
      }
    },
  },
  h('label', { class: 'field' }, h('span', {}, 'Email'), email),
  h('label', { class: 'field' }, h('span', {}, 'Пароль'), password),
  error,
  h('div', { style: { marginTop: '24px' } }, submit));

  add(view,
    h('div', { class: 'logo', 'aria-hidden': 'true' },
      ['red', 'yellow', 'blue', 'green'].map((q) => h('i', { style: { background: `var(--q-${q})` } }))),
    h('h1', {}, 'Feel'),
    h('p', { class: 'subtitle' }, 'Дневник эмоций'),
    form);
}
