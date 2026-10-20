// Запросы к серверу. Сессия — в HttpOnly-cookie, CSRF-токен — из cookie feel_csrf.

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

let onUnauthorized = () => {};
export function setUnauthorizedHandler(fn) { onUnauthorized = fn; }

function csrfToken() {
  const row = document.cookie.split('; ').find((c) => c.startsWith('feel_csrf='));
  return row ? decodeURIComponent(row.slice('feel_csrf='.length)) : '';
}

function messageOf(data, status) {
  if (data && typeof data.detail === 'string') return data.detail;
  if (data && Array.isArray(data.detail) && data.detail.length) {
    return data.detail.map((d) => (d.msg || '').replace(/^Value error, /, '')).join('; ');
  }
  if (status >= 500) return 'Ошибка сервера, попробуйте позже';
  return 'Что-то пошло не так';
}

export async function request(method, url, body) {
  const headers = { 'X-Requested-With': 'feel' };
  if (method !== 'GET') headers['X-CSRF-Token'] = csrfToken();
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let res;
  try {
    res = await fetch(url, {
      method, headers, credentials: 'same-origin',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new ApiError(0, 'Нет связи с сервером');
  }
  const isJson = (res.headers.get('content-type') || '').includes('json');
  const data = isJson ? await res.json() : null;
  if (res.status === 401 && !url.startsWith('/api/auth/')) onUnauthorized();
  if (!res.ok) throw new ApiError(res.status, messageOf(data, res.status));
  return data;
}

export const api = {
  get: (url) => request('GET', url),
  post: (url, body = {}) => request('POST', url, body),
  put: (url, body = {}) => request('PUT', url, body),
  patch: (url, body = {}) => request('PATCH', url, body),
  del: (url) => request('DELETE', url),
};
