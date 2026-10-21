// Фото и голос: сжатие фото на устройстве, запись голоса, редактор вложений записи.
import { api, upload } from './api.js';
import { h, showError } from './ui.js';

const MAX_SIDE = 1600;
const JPEG_QUALITY = 0.8;
const MAX_PHOTOS = 4;
export const MAX_VOICE_SECONDS = 180;

export function fmtDuration(s) {
  const n = Math.round(s || 0);
  return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, '0')}`;
}

// Фото → JPEG не больше 1600 px по длинной стороне, качество 0,8.
export async function compressImage(file) {
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    const k = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(img.naturalWidth * k);
    canvas.height = Math.round(img.naturalHeight * k);
    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
    return await new Promise((resolve, reject) => canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error('Не удалось обработать фото'))), 'image/jpeg', JPEG_QUALITY));
  } finally {
    URL.revokeObjectURL(url);
  }
}

function audioDuration(blob) {
  return new Promise((resolve) => {
    const a = new Audio();
    const url = URL.createObjectURL(blob);
    a.preload = 'metadata';
    a.onloadedmetadata = () => { URL.revokeObjectURL(url); resolve(Number.isFinite(a.duration) ? a.duration : null); };
    a.onerror = () => { URL.revokeObjectURL(url); resolve(null); };
    a.src = url;
  });
}

function recorderMime() {
  if (typeof MediaRecorder === 'undefined') return null;
  for (const t of ['audio/mp4', 'audio/aac', 'audio/webm;codecs=opus', 'audio/webm']) {
    if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) return t;
  }
  return '';
}

// Запись голоса. После остановки обязательно гасим все дорожки — иначе в PWA на iOS
// повторная запись может не начаться.
export class VoiceRecorder {
  async start(onTick, onAutoStop) {
    if (!navigator.mediaDevices || recorderMime() === null) throw new Error('Запись голоса здесь недоступна — прикрепите аудиофайл');
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mime = recorderMime();
    this.rec = new MediaRecorder(this.stream, mime ? { mimeType: mime } : undefined);
    this.chunks = [];
    this.rec.ondataavailable = (e) => { if (e.data && e.data.size) this.chunks.push(e.data); };
    this.started = Date.now();
    this.rec.start(1000);
    this.timer = setInterval(() => {
      const s = (Date.now() - this.started) / 1000;
      onTick(s);
      if (s >= MAX_VOICE_SECONDS) onAutoStop();
    }, 250);
  }

  stop() {
    clearInterval(this.timer);
    return new Promise((resolve) => {
      const finish = () => {
        this.stream.getTracks().forEach((t) => t.stop());
        const type = (this.rec.mimeType || 'audio/mp4').split(';')[0];
        resolve({ blob: new Blob(this.chunks, { type }), duration: Math.min(MAX_VOICE_SECONDS, (Date.now() - this.started) / 1000) });
      };
      if (this.rec.state === 'inactive') finish();
      else { this.rec.onstop = finish; this.rec.stop(); }
    });
  }

  cancel() {
    clearInterval(this.timer);
    try { if (this.rec && this.rec.state !== 'inactive') this.rec.stop(); } catch (e) { /* уже остановлен */ }
    if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
  }
}

/**
 * Редактор вложений записи или дня. Файлы загружаются в commit(), после сохранения записи.
 * opts: { existing: [], photos: bool, voice: bool, voiceLabel }
 */
export function mediaEditor(opts) {
  const existing = [...(opts.existing || [])];
  const removed = new Set();
  const pendingPhotos = [];        // { blob, url }
  let pendingVoice = null;         // { blob, duration, url }
  let recorder = null;

  const el = h('div', { class: 'media-editor' });
  const fileInput = h('input', { type: 'file', accept: 'image/*', multiple: true, hidden: true });
  const audioInput = h('input', { type: 'file', accept: 'audio/*', hidden: true });

  const photoCount = () => existing.filter((m) => m.kind === 'photo' && !removed.has(m.id)).length + pendingPhotos.length;
  const currentVoice = () => pendingVoice || existing.find((m) => m.kind === 'audio' && !removed.has(m.id));

  fileInput.addEventListener('change', async () => {
    const files = [...fileInput.files].slice(0, MAX_PHOTOS - photoCount());
    fileInput.value = '';
    for (const f of files) {
      try {
        const blob = await compressImage(f);
        pendingPhotos.push({ blob, url: URL.createObjectURL(blob) });
      } catch (e) { showError(e); }
    }
    draw();
  });

  audioInput.addEventListener('change', async () => {
    const f = audioInput.files[0];
    audioInput.value = '';
    if (!f) return;
    const duration = await audioDuration(f);
    if (duration && duration > MAX_VOICE_SECONDS + 1) { showError(new Error('Голосовая заметка — до 3 минут')); return; }
    setVoice({ blob: f, duration: duration || null });
  });

  function setVoice(v) {
    if (pendingVoice) URL.revokeObjectURL(pendingVoice.url);
    pendingVoice = v ? { ...v, url: URL.createObjectURL(v.blob) } : null;
    draw();
  }

  function removeVoice() {
    if (pendingVoice) setVoice(null);
    const ex = existing.find((m) => m.kind === 'audio' && !removed.has(m.id));
    if (ex) removed.add(ex.id);
    draw();
  }

  async function toggleRecord(btn, timeEl) {
    if (recorder) {
      const r = recorder;
      recorder = null;
      const res = await r.stop();
      if (res.blob.size) setVoice(res); else draw();
      return;
    }
    recorder = new VoiceRecorder();
    try {
      await recorder.start((s) => { timeEl.textContent = `${fmtDuration(s)} / 3:00`; },
        () => toggleRecord(btn, timeEl));
      btn.textContent = '■ Остановить';
      btn.classList.add('recording');
    } catch (e) {
      recorder.cancel();
      recorder = null;
      showError(e.name === 'NotAllowedError' ? new Error('Нет доступа к микрофону — разрешите его в настройках iPhone') : e);
    }
  }

  function draw() {
    const blocks = [];
    if (opts.photos) {
      const thumbs = [
        ...existing.filter((m) => m.kind === 'photo' && !removed.has(m.id)).map((m) => ({ url: m.url, drop: () => { removed.add(m.id); draw(); } })),
        ...pendingPhotos.map((p) => ({ url: p.url, drop: () => { pendingPhotos.splice(pendingPhotos.indexOf(p), 1); URL.revokeObjectURL(p.url); draw(); } })),
      ];
      blocks.push(h('div', { class: 'thumbs' },
        thumbs.map((t) => h('div', { class: 'thumb' },
          h('img', { src: t.url, alt: 'Фото' }),
          h('button', { class: 'thumb-del', 'aria-label': 'Убрать фото', onclick: t.drop }, '×'))),
        photoCount() < MAX_PHOTOS
          ? h('button', { class: 'thumb add', 'aria-label': 'Добавить фото', onclick: () => fileInput.click() }, '+ фото')
          : null));
    }
    if (opts.voice) {
      const v = currentVoice();
      if (recorder) {
        // идёт запись — кнопку не перерисовываем
      } else if (v) {
        blocks.push(h('div', { class: 'voice' },
          h('audio', { controls: true, preload: 'metadata', src: v.url }),
          h('div', { class: 'btn-row', style: { marginTop: '8px' } },
            h('button', { class: 'btn small', onclick: removeVoice }, 'Удалить голос'))));
      } else {
        const timeEl = h('span', { class: 'muted small' });
        const btn = h('button', { class: 'btn small' }, `🎙 ${opts.voiceLabel || 'Записать голос'}`);
        btn.addEventListener('click', () => toggleRecord(btn, timeEl));
        blocks.push(h('div', { class: 'voice' },
          h('div', { class: 'btn-row', style: { alignItems: 'center' } }, btn, timeEl),
          h('button', { class: 'link-btn', onclick: () => audioInput.click() }, 'или прикрепить аудиофайл')));
      }
    }
    if (!recorder) el.replaceChildren(...blocks, fileInput, audioInput);
  }
  draw();

  return {
    el,
    // Загружает новые файлы и удаляет убранные. target: { checkin_id } или { day_log_date }.
    async commit(target) {
      if (recorder) { const r = recorder; recorder = null; const res = await r.stop(); if (res.blob.size) setVoice(res); }
      for (const id of removed) {
        try { await api.del(`/api/media/${id}`); } catch (e) { if (e.status !== 404) throw e; }
      }
      removed.clear();
      for (const p of pendingPhotos.splice(0)) {
        const fd = new FormData();
        fd.append('kind', 'photo');
        Object.entries(target).forEach(([k, v]) => fd.append(k, v));
        fd.append('file', p.blob, 'photo.jpg');
        existing.push(await upload('/api/media', fd));
        URL.revokeObjectURL(p.url);
      }
      if (pendingVoice) {
        const v = pendingVoice;
        const fd = new FormData();
        fd.append('kind', 'audio');
        Object.entries(target).forEach(([k, val]) => fd.append(k, val));
        if (v.duration) fd.append('duration_s', String(v.duration));
        const ext = (v.blob.type || '').includes('webm') ? 'webm' : 'm4a';
        fd.append('file', v.blob, `voice.${ext}`);
        existing.push(await upload('/api/media', fd));
        pendingVoice = null;
      }
      draw();
    },
    hasChanges() { return removed.size > 0 || pendingPhotos.length > 0 || !!pendingVoice; },
    dispose() { if (recorder) recorder.cancel(); recorder = null; },
  };
}

// Превью вложений в дневнике.
export function mediaPreview(media, { large = false } = {}) {
  if (!media || !media.length) return null;
  const photos = media.filter((m) => m.kind === 'photo');
  const audio = media.filter((m) => m.kind === 'audio');
  return h('div', { class: large ? 'media-large' : 'media-preview' },
    photos.length ? h('div', { class: large ? 'photos' : 'mini-thumbs' },
      photos.map((m) => (large
        ? h('a', { href: m.url, target: '_blank', rel: 'noopener' }, h('img', { src: m.url, alt: 'Фото', loading: 'lazy' }))
        : h('img', { src: m.url, alt: 'Фото', loading: 'lazy' })))) : null,
    audio.map((m) => (large
      ? h('audio', { controls: true, preload: 'none', src: m.url })
      : h('span', { class: 'voice-chip' }, `🎙 ${m.duration_s ? fmtDuration(m.duration_s) : 'голос'}`))));
}
