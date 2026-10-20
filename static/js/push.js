// Подписка на Web Push. Разрешение запрашивается только по нажатию кнопки.
import { api } from './api.js';
import { isStandalone, isIOS } from './ui.js';

let publicKey = null;

export function supported() {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
}

export function blockedReason() {
  if (isIOS() && !isStandalone()) return 'Уведомления работают только в приложении, установленном на экран «Домой».';
  if (!supported()) return 'Этот браузер не поддерживает уведомления. Нужен iOS 16.4 или новее.';
  if (Notification.permission === 'denied') return 'Уведомления запрещены. Разрешите их в «Настройки» → «Уведомления» → feel.';
  return null;
}

// Ключ загружаем заранее, чтобы по нажатию сразу вызвать requestPermission:
// иначе iOS может посчитать, что запрос не связан с действием пользователя.
export async function preload() {
  if (publicKey || !supported()) return;
  try {
    const cfg = await api.get('/api/push/config');
    publicKey = cfg.public_key;
  } catch (e) { /* покажем ошибку при подписке */ }
}

function keyBytes(b64) {
  const pad = '='.repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

export async function enable() {
  const reason = blockedReason();
  if (reason) throw new Error(reason);
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') throw new Error('Без разрешения уведомления не придут');
  if (!publicKey) await preload();
  if (!publicKey) throw new Error('Сервер не настроен для уведомлений');
  const reg = await navigator.serviceWorker.ready;
  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(publicKey) });
  }
  await api.post('/api/push/subscriptions', sub.toJSON());
  return sub;
}

export async function currentSubscription() {
  if (!supported()) return null;
  const reg = await navigator.serviceWorker.getRegistration();
  return reg ? reg.pushManager.getSubscription() : null;
}

export async function status() {
  const sub = await currentSubscription();
  const res = await api.post('/api/push/status', { endpoint: sub ? sub.endpoint : 'https://none.invalid/' });
  return { ...res, subscribed: !!sub, permission: supported() ? Notification.permission : 'unsupported' };
}

// При каждом запуске: если подписка есть на устройстве, напоминаем о ней серверу.
export async function resync() {
  try {
    if (!supported() || Notification.permission !== 'granted') return;
    const sub = await currentSubscription();
    if (sub) await api.post('/api/push/subscriptions', sub.toJSON());
  } catch (e) { /* не критично */ }
}

export async function disable() {
  const sub = await currentSubscription();
  if (sub) {
    await api.post('/api/push/unsubscribe', { endpoint: sub.endpoint });
    await sub.unsubscribe();
  }
}
