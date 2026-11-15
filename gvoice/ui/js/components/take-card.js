/* Nuevo en gvoice (no copiado de gimg) (F5.4; la tarjeta de intento de gimg es de imágenes). Una toma de un pedido:
   reproductor (`<audio>` nativo, sin controles propios del navegador: el botón y la forma de onda lo manejan), forma de
   onda, estado (nueva, candidata, descartada), nota, huellas (solo en `voice`) y «Elegir». La toma elegida lleva visto y
   texto («✓ Elegida») y un subrayado, nunca solo color. La tarjeta se crea una vez y `update()` repinta lo que cambia sin
   tocar el audio ni la nota que se está escribiendo. Las acciones (`mark`, `note`, `choose`) las pone la vista. */

import { h, mmss, replace } from '../dom.js';
import { t } from '../i18n.js';
import { api } from '../api.js';
import { busy } from '../async-guard.js';
import { icon } from './icons.js';
import { createWaveform } from './waveform.js';
import { bucketsFor, canChoose, hasAudio, printStates, takeState } from '../take-model.js';

const PRINT_KEY = { done: 'ui.take.print.done', running: 'ui.take.print.running', queued: 'ui.take.print.queued', pending: 'ui.take.print.pending' };
const PRINT_MARK = { done: '✓', running: '…', queued: '…', pending: '○' };

/** takeCard({project, key, type, models, actions: {mark, note, choose}, onPlay, alive}) → {node, id, update, load, toggle,
    pause, focus, destroy, audio}. `onPlay(card)` avisa de que esta toma empieza a sonar (la vista pausa las demás). */
export function takeCard({ project, key, type, models = [], actions, onPlay = () => {}, alive = () => true }) {
  let take = null; let order = null; let entries = [];
  let url = null; let srcReady = null; let started = false; let destroyed = false; let dirty = false; let raf = null;
  let durationMs = 0;

  const audio = h('audio', { preload: 'none' });
  const status = h('div.take-status', { aria: { live: 'polite' } });
  const title = h('h3.take-title');
  const badges = h('span.row.take-badges');
  const meta = h('div.take-meta.hint');
  const time = h('span.take-time.mono', { aria: { hidden: true } }, '0:00 / —');
  const playLabel = h('span');
  const playIcon = h('span.btn-icon-slot');
  const play = h('button.btn.take-play', { type: 'button', onclick: () => toggle() }, playIcon, playLabel);
  const wave = createWaveform({
    label: '', onSeek: (f) => seek(f),
    valueText: (f) => `${mmss(f * totalMs())} / ${mmss(totalMs())}`,
  });
  const noAudio = h('p.hint.take-noaudio', {}, t('ui.take.noAudio'));
  const prints = type === 'voice' ? h('div.take-prints') : null;
  const candidateBtn = h('button.btn.btn-toggle', { type: 'button', onclick: () => mark(take.state === 'candidate' ? 'new' : 'candidate') }, t('ui.take.markCandidate'));
  const discardBtn = h('button.btn.btn-toggle.btn-danger-toggle', { type: 'button', onclick: () => mark(take.state === 'discarded' ? 'new' : 'discarded') }, h('span', { aria: { hidden: true } }, '✗ '), t('ui.take.markDiscard'));
  const chooseBtn = h('button.btn.btn-primary', { type: 'button', onclick: () => choose() }, icon('check'), ' ', t('ui.take.choose'));
  const why = h('p.hint.take-why');
  const noteId = `note-${Math.random().toString(36).slice(2, 8)}`;
  const noteBox = h('textarea', { id: noteId, rows: 2, maxlength: 2000, oninput: () => { dirty = true; saveBtn.disabled = false; } });
  const saveBtn = h('button.btn', { type: 'button', disabled: true, onclick: () => saveNote() }, t('ui.take.noteSave'));
  noteBox.addEventListener('change', () => { if (dirty) saveNote(); });
  const node = h('article.take-card', { tabindex: -1, data: { take: '' } },
    h('div.row-between', {}, title, badges), meta,
    h('div.take-player', {}, play, time), wave.node, noAudio, audio, status, prints,
    h('div.row.take-actions', {}, chooseBtn, candidateBtn, discardBtn), why,
    h('div.field.take-note', {}, h('label', { for: noteId }, t('ui.take.note')), noteBox, h('div.row', {}, saveBtn)));

  const mark = busy(async (state) => { await actions.mark(take, state); });
  const choose = busy(async () => { await actions.choose(take); });
  const saveNote = busy(async () => { if (await actions.note(take, noteBox.value)) { dirty = false; saveBtn.disabled = true; } });

  const totalMs = () => (Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration * 1000 : durationMs || (take && take.audioMs) || 0);
  function paintTime() {
    const cur = (audio.currentTime || 0) * 1000;
    const total = totalMs();
    time.textContent = `${mmss(cur)} / ${total ? mmss(total) : '—'}`;
    wave.setProgress(total ? cur / total : 0);
  }
  function setPlaying(on) {
    replace(playIcon, icon(on ? 'pause' : 'play'));
    playLabel.textContent = t(on ? 'ui.take.pause' : 'ui.take.play');
    play.setAttribute('aria-label', `${t(on ? 'ui.take.pause' : 'ui.take.play')} · ${t('ui.take.title', { id: take ? take.id : '' })}`);
    node.classList.toggle('is-playing', on);
  }
  function tick() {
    paintTime();
    raf = audio.paused || typeof requestAnimationFrame !== 'function' ? null : requestAnimationFrame(tick);
  }
  function showError(msg) { replace(status, h('p.field-error', { role: 'alert' }, '✗ ', msg)); }
  function clearError() { replace(status); }

  audio.addEventListener('play', () => { setPlaying(true); onPlay(card); if (typeof requestAnimationFrame === 'function' && raf === null) raf = requestAnimationFrame(tick); });
  const stopped = () => { setPlaying(false); paintTime(); if (raf !== null && typeof cancelAnimationFrame === 'function') cancelAnimationFrame(raf); raf = null; };
  audio.addEventListener('pause', stopped);
  audio.addEventListener('ended', () => { stopped(); });
  for (const ev of ['timeupdate', 'loadedmetadata', 'durationchange', 'seeked']) audio.addEventListener(ev, paintTime);
  audio.addEventListener('error', () => { if (audio.getAttribute('src')) showError(t('ui.take.audioError')); });

  function seek(f) {
    if (!hasAudio(take)) return;
    const total = totalMs();
    if (!total) return;
    audio.currentTime = f * total / 1000;
    paintTime();
  }

  async function toggle() {
    if (!take || !hasAudio(take) || destroyed) return;
    if (!audio.paused) { audio.pause(); return; }
    load();
    const ready = await srcReady;
    if (!ready || destroyed || !alive()) return;
    clearError();
    try { await audio.play(); } catch (e) { if (alive() && !destroyed) showError(t('ui.take.audioError')); }
  }

  /** Pide el audio (URL para el `<audio>`) y los picos; una sola vez, con la tarjeta ya en el documento (hace falta su ancho). */
  function load() {
    if (started || !take || !hasAudio(take) || destroyed) return;
    started = true;
    srcReady = api.audioUrl(project, key, take.id).then((u) => {
      if (destroyed || !alive()) { api.revokeAudioUrl(u); return null; }
      url = u; audio.src = u;
      return u;
    }).catch((e) => { if (alive() && !destroyed) showError(t('ui.take.audioError')); return null; });
    api.peaks(project, key, take.id, bucketsFor(wave.width())).then((r) => {
      if (destroyed || !alive()) return;
      durationMs = r.audioMs || durationMs;
      wave.setPeaks(r.peaks);
      paintTime();
    }).catch(() => { if (alive() && !destroyed) replace(status, h('p.field-error', {}, '✗ ', t('ui.take.peaksError'))); });
  }

  function update(nextTake, view = {}) {
    take = nextTake;
    order = view.order || order;
    entries = view.entries || entries;
    const state = takeState(order, take);
    const chosen = state === 'chosen';
    node.dataset.take = String(take.id);
    node.setAttribute('aria-label', t('ui.take.title', { id: take.id }));
    node.classList.toggle('is-chosen', chosen);
    node.classList.toggle('is-discarded', state === 'discarded');
    wave.node.setAttribute('aria-label', t('ui.take.seek', { id: take.id }));
    replace(title, t('ui.take.title', { id: take.id }));
    replace(badges,
      chosen ? h('span.chip.chip-fill-ok', {}, h('span', { aria: { hidden: true } }, '✓ '), t('ui.take.chosen')) : null,
      take.state === 'discarded' ? h('span.chip.chip-bad', {}, '✗ ', t('ui.take.state.discarded'))
        : h('span.chip' + (take.state === 'candidate' ? '.chip-accent' : ''), {}, t(take.state === 'candidate' ? 'ui.take.state.candidate' : 'ui.take.state.new')));
    replace(meta, [take.seed !== undefined && take.seed !== null ? t('ui.take.seed', { seed: take.seed }) : null,
      hasAudio(take) ? mmss(take.audioMs) : null, take.device || null].filter(Boolean).join(' · '));
    const audible = hasAudio(take);
    play.hidden = !audible; time.hidden = !audible; wave.node.hidden = !audible; noAudio.hidden = audible;
    setPlaying(!audio.paused);
    paintTime();
    candidateBtn.setAttribute('aria-pressed', String(take.state === 'candidate'));
    discardBtn.setAttribute('aria-pressed', String(take.state === 'discarded'));
    discardBtn.disabled = chosen;
    chooseBtn.hidden = chosen;
    chooseBtn.disabled = !canChoose(order, take);
    replace(why, chosen ? null : state === 'discarded' ? t('ui.take.chooseDiscarded') : !audible ? t('ui.take.chooseNoAudio') : null);
    why.hidden = !why.firstChild;
    if (prints) {
      replace(prints, h('b.label', {}, t('ui.take.prints')),
        h('ul.take-print-list', {}, printStates(take, models, entries).map((p) => h('li.print.print-' + p.status, {}, h('span', { aria: { hidden: true } }, PRINT_MARK[p.status] + ' '), t(PRINT_KEY[p.status], { model: p.model })))),
        chosen ? null : h('p.hint', {}, t('ui.take.printsHint')));
    }
    if (!dirty) noteBox.value = take.note || '';
  }

  function pause() { if (!audio.paused) audio.pause(); }
  function focus() { node.focus(); }
  function destroy() {
    destroyed = true;
    if (raf !== null && typeof cancelAnimationFrame === 'function') cancelAnimationFrame(raf);
    raf = null;
    try { audio.pause(); } catch { /* sin reproductor real */ }
    audio.removeAttribute('src');
    if (url) api.revokeAudioUrl(url);
    url = null;
    wave.destroy();
  }

  const card = { node, get id() { return take && take.id; }, audio, update, load, toggle, pause, focus, destroy, play: () => (audio.paused ? toggle() : undefined), seek };
  return card;
}
