// Данные, которые нужны многим экранам: справочник эмоций, метки, настройки.
import { api } from './api.js';

const EMO_KEY = 'feel.emotions.v1';
let emotionsPromise = null;
let tagsCache = null;

export async function emotions() {
  if (!emotionsPromise) {
    emotionsPromise = (async () => {
      try {
        const data = await api.get('/api/emotions');
        try { localStorage.setItem(EMO_KEY, JSON.stringify(data)); } catch (e) { /* приватный режим */ }
        return index(data);
      } catch (e) {
        let cached = null;
        try { cached = JSON.parse(localStorage.getItem(EMO_KEY)); } catch (_) { /* нет кэша */ }
        if (cached) return index(cached);
        emotionsPromise = null;
        throw e;
      }
    })();
  }
  return emotionsPromise;
}

function index(data) {
  const byId = new Map(data.emotions.map((e) => [e.id, e]));
  const quadrants = new Map(data.quadrants.map((q) => [q.id, q]));
  return { list: data.emotions, byId, quadrants };
}

export async function tags(force = false) {
  if (!tagsCache || force) tagsCache = await api.get('/api/tags');
  return tagsCache;
}

export function invalidateTags() { tagsCache = null; }

export const GROUPS = [
  { id: 'with', title: 'С кем' },
  { id: 'where', title: 'Где' },
  { id: 'doing', title: 'Чем занят' },
];

export function quadColor(q) {
  return `var(--q-${q})`;
}

export function clearAll() {
  emotionsPromise = null;
  tagsCache = null;
}
