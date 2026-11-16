/* Nuevo en gvoice (no copiado de gimg) (F5.5; la comparación de gimg es de imágenes: aquí se oyen dos tomas de la misma
   frase y el cambio entre ellas sigue en el mismo punto). Dos paneles (A y B), cada uno con su toma (un `<select>` la
   cambia sin repintar), su forma de onda y su tiempo, y un único transporte: reproducir/pausa, «Cambiar A↔B» y «Elegir».
   Solo suena el lado activo. Al cambiar de lado se toma el `currentTime` del activo, se lleva el otro a ese punto
   (`switchPoint`: recortado a su duración) y, si sonaba, suena el otro desde ahí; en pausa se queda en pausa en ese punto.
   Un clic en una onda mueve la posición de los dos audios. Teclado y mando: shortcuts.js (`keyAction`, `padActions`).
   GET …/orders/{key}, audio y picos como la tarjeta de toma; elegir recarga el pedido.
   Devuelve {node, cleanup}: cleanup revoca las URL de audio, quita las escuchas y para la animación. */

import { h, mmss, replace, closest } from '../dom.js';
import { t } from '../i18n.js';
import { api, describeError } from '../api.js';
import { to, replaceHash } from '../router.js';
import { busy, latest, lifetime, STALE } from '../async-guard.js';
import { bucketsFor, canChoose, hasAudio, takeState } from '../take-model.js';
import { otherSide, pickPair, switchPoint } from '../compare-model.js';
import { icon } from './icons.js';
import { createWaveform } from './waveform.js';
import { isQueueOpen } from './queue-bar.js';
import { helpOpen, isTyping, keyAction, mergeSources, oneKeyEnabled, openHelp, startGamepad } from './shortcuts.js';
import { toast, toastError, toastOk } from './toast.js';

const loading = () => h('p.empty', {}, h('span.spin', { aria: { hidden: true } }), ' ', t('ui.loading'));
const LETTER = { a: 'A', b: 'B' };
const VIEW_ACTIONS = new Set(['toggle', 'prev', 'next', 'swap', 'choose', 'pause']);   // the rest (U, C, D, G, pad Y) do nothing here

export function compareView(route) {
  const { project, key } = route;
  const life = lifetime();
  const alive = life.alive;
  const loads = latest();
  const exclusive = busy(async (fn) => fn());   // elegir: una petición a la vez
  let order = null; let sides = null; let active = 'a'; let mounted = false; let raf = null;

  const head = h('div.order-head');
  const node = h('section.compare', {}, head, h('div.compare-body', {}, loading()));
  const bodyHost = node.children[1];
  const backLink = () => h('a.btn', { href: to.order(project, key) }, icon('back'), ' ', t('ui.compare.back'));

  const playLabel = h('span');
  const playIcon = h('span.btn-icon-slot');
  const playBtn = h('button.btn.btn-primary.compare-play', { type: 'button', onclick: () => togglePlay() }, playIcon, playLabel);
  const swapBtn = h('button.btn', { type: 'button', onclick: () => activate(otherSide(active)) }, icon('swap'), ' ', t('ui.compare.swap'));
  const chooseBtns = { a: h('button.btn', { type: 'button', onclick: () => chooseSide('a') }, icon('check'), ' ', t('ui.compare.choose', { side: 'A' })),
    b: h('button.btn', { type: 'button', onclick: () => chooseSide('b') }, icon('check'), ' ', t('ui.compare.choose', { side: 'B' })) };
  const helpBtn = h('button.btn.btn-ghost', { type: 'button', onclick: () => openHelp(helpBtn) }, icon('keys'), ' ', t('ui.shortcuts.open'), ' ', h('kbd.kbd', {}, '?'));
  const hint = h('p.hint.compare-hint', { aria: { live: 'polite' } });

  /* ---- un lado (A o B): su toma, su `<audio>`, su onda ---- */
  function makeSide(name, id) {
    const s = { name, id, audio: null, url: null, srcReady: null, pendingAt: null, want: false, destroyed: false, durationMs: 0 };
    const selId = `compare-take-${name}`;
    s.select = h('select', { id: selId, onchange: () => changeTake(s, Number(s.select.value)) });
    s.wave = createWaveform({ label: '', onSeek: (f) => seekShared(f * duration(s), s), valueText: (f) => `${mmss(f * duration(s) * 1000)} / ${mmss(duration(s) * 1000)}` });
    s.title = h('h2.compare-title');
    s.activeSlot = h('span'); s.stateSlot = h('span.row');
    s.chips = h('span.row.compare-chips', {}, s.activeSlot, s.stateSlot);
    s.meta = h('p.hint.take-meta');
    s.time = h('span.take-time.mono', { aria: { hidden: true } }, '0:00 / —');
    s.status = h('div.take-status', { aria: { live: 'polite' } });
    s.audioHost = h('div.compare-audio');
    s.node = h('article.compare-side', { data: { side: name } },
      h('div.row-between', {}, s.title, s.chips),
      h('div.field', {}, h('label', { for: selId }, t('ui.compare.take', { side: LETTER[name] })), s.select),
      s.meta, s.wave.node, s.time, s.status, s.audioHost);
    return s;   // its audio is attached once the panel is in the document (the waveform needs its width)
  }

  function attachAudio(s) {
    const audio = h('audio', { preload: 'auto' });
    replace(s.status);
    s.audio = audio; s.url = null; s.srcReady = null; s.pendingAt = null;
    const alivePlayer = () => s.audio === audio && !s.destroyed && alive();
    audio.addEventListener('play', () => { paintTransport(); startTick(); });
    const stopped = () => { if (!alivePlayer()) return; paintTransport(); paintSide(s); };
    audio.addEventListener('pause', stopped);
    audio.addEventListener('ended', stopped);
    // a position asked for before the audio had its source is applied once it knows its duration
    audio.addEventListener('loadedmetadata', () => { if (s.pendingAt !== null) { const at = s.pendingAt; s.pendingAt = null; audio.currentTime = at; } });
    for (const ev of ['timeupdate', 'loadedmetadata', 'durationchange', 'seeked']) audio.addEventListener(ev, () => { if (alivePlayer()) paintSide(s); });
    audio.addEventListener('error', () => { if (alivePlayer() && audio.getAttribute('src')) showError(s, t('ui.take.audioError')); });
    replace(s.audioHost, audio);
    // the audio URL and the peaks (the node is already in the document: the width is known)
    s.srcReady = api.audioUrl(project, key, s.id).then((u) => {
      if (!alivePlayer()) { api.revokeAudioUrl(u); return null; }
      s.url = u; audio.src = u;
      return u;
    }).catch(() => { if (alivePlayer()) showError(s, t('ui.take.audioError')); return null; });
    const id = s.id;
    api.peaks(project, key, id, bucketsFor(s.wave.width())).then((r) => {
      if (!alivePlayer() || s.id !== id) return;
      s.durationMs = r.audioMs || s.durationMs;
      s.wave.setPeaks(r.peaks);
      paintSide(s);
    }).catch(() => { if (alivePlayer() && !s.status.firstChild) replace(s.status, h('p.field-error', {}, '✗ ', t('ui.take.peaksError'))); });
  }

  function releaseAudio(s) {
    const audio = s.audio;
    if (!audio) return;
    try { audio.pause(); } catch { /* sin reproductor real */ }
    audio.removeAttribute('src');
    if (s.url) api.revokeAudioUrl(s.url);
    s.url = null; s.audio = null;
  }

  const isPlaying = (s) => Boolean(s.audio) && !s.audio.paused;
  const takeOf = (s) => (order && order.attempts.find((a) => a.id === s.id)) || null;
  const duration = (s) => {
    if (s.audio && Number.isFinite(s.audio.duration) && s.audio.duration > 0) return s.audio.duration;
    const take = takeOf(s);
    return (s.durationMs || (take && take.audioMs) || 0) / 1000;
  };
  const timeOf = (s) => (s.pendingAt !== null ? s.pendingAt : (s.audio && s.audio.currentTime) || 0);
  function setTime(s, sec) {
    // without `src` the browser forgets a position set now when the source arrives: remember it
    if (!s.audio.src) s.pendingAt = sec; else { s.pendingAt = null; s.audio.currentTime = sec; }   // the latest value always wins
    paintSide(s);
  }
  function showError(s, msg) { replace(s.status, h('p.field-error', { role: 'alert' }, '✗ ', msg)); }

  /* ---- pintura ---- */
  function paintSide(s) {
    if (!s.audio) return;
    const cur = timeOf(s) * 1000; const total = duration(s) * 1000;
    s.time.textContent = `${mmss(cur)} / ${total ? mmss(total) : '—'}`;
    s.wave.setProgress(total ? cur / total : 0);
  }
    function paintTransport() {
    if (!sides || !alive()) return;
    const on = isPlaying(sides[active]);
    replace(playIcon, icon(on ? 'pause' : 'play'));
    playLabel.textContent = t(on ? 'ui.take.pause' : 'ui.take.play');
    playBtn.setAttribute('aria-label', `${t(on ? 'ui.take.pause' : 'ui.take.play')} · ${LETTER[active]}`);
  }
  function startTick() {
    if (typeof requestAnimationFrame !== 'function' || raf !== null) return;
    const tick = () => {
      raf = null;
      if (!alive() || !sides) return;
      paintSide(sides[active]);
      if (isPlaying(sides[active])) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
  }
  function paintSides() {
    const takes = [...order.attempts].filter(hasAudio).sort((x, y) => x.id - y.id);
    for (const s of Object.values(sides)) {
      const take = takeOf(s);
      const other = sides[otherSide(s.name)];
      const chosen = take && takeState(order, take) === 'chosen';
      s.node.classList.toggle('is-chosen', Boolean(chosen));
      s.node.setAttribute('aria-label', t('ui.compare.sideLabel', { side: LETTER[s.name], id: s.id }));
      replace(s.title, h('span.compare-letter', {}, LETTER[s.name]), ' ', h('span.compare-take', {}, t('ui.take.title', { id: s.id })));
      replace(s.stateSlot,
        chosen ? h('span.chip.chip-fill-ok', {}, h('span', { aria: { hidden: true } }, '✓ '), t('ui.take.chosen')) : null,
        take && take.state === 'discarded' ? h('span.chip.chip-bad', {}, '✗ ', t('ui.take.state.discarded')) : null);
      replace(s.meta, [take && take.seed !== undefined && take.seed !== null ? t('ui.take.seed', { seed: take.seed }) : null, take ? mmss(take.audioMs) : null].filter(Boolean).join(' · '));
      s.wave.node.setAttribute('aria-label', t('ui.take.seek', { id: s.id }));
      replace(s.select, takes.map((x) => h('option', { value: x.id, disabled: x.id === other.id },
        t('ui.take.title', { id: x.id }) + (takeState(order, x) === 'chosen' ? ` · ✓ ${t('ui.take.chosen')}` : ''))));
      s.select.value = s.id;
      chooseBtns[s.name].disabled = !take || !canChoose(order, take);
      paintSide(s);
    }
    paintActive();
    paintTransport();
  }
  /** The side switch only changes classes, the «plays this side» chip and `aria-current` (no `<select>` rebuilt). */
  function paintActive() {
    for (const s of Object.values(sides)) {
      const on = s.name === active;
      s.node.classList.toggle('is-active', on);
      if (on) s.node.setAttribute('aria-current', 'true'); else s.node.removeAttribute('aria-current');
      replace(s.activeSlot, on ? h('span.chip.chip-accent', {}, h('span', { aria: { hidden: true } }, '▶ '), t('ui.compare.active')) : null);
    }
  }

  /* ---- cambio de toma de un lado, reproducción y cambio de lado ---- */
  const syncHash = () => replaceHash(to.compare(project, key, sides.a.id, sides.b.id));
  function changeTake(s, id) {
    const other = sides[otherSide(s.name)];
    if (!Number.isInteger(id) || id === s.id) { s.select.value = s.id; return; }
    if (id === other.id) { s.select.value = s.id; return; }   // the two sides always hold different takes
    const ref = timeOf(sides[active]);
    const wasPlaying = s.name === active && (isPlaying(s) || s.want);
    releaseAudio(s);
    s.want = false;
    s.id = id; s.durationMs = 0;
    s.wave.setPeaks([]);
    attachAudio(s);
    const sp = switchPoint(ref, duration(s));   // the new take may be shorter than the position: it stays at its end
    setTime(s, sp.pos);
    hintEnd(sp.atEnd ? s : null);
    syncHash();
    paintSides();
    if (wasPlaying && !sp.atEnd) play(s);
  }

  async function play(s) {
    const audio = s.audio; const ready = s.srcReady;
    s.want = true;   // asked to play, the source may not be here yet: a switch meanwhile carries it to the other side
    if (!(await ready) || s.audio !== audio || s.destroyed || !alive() || !s.want || !sides || sides[active] !== s) return;
    s.want = false;
    replace(s.status);
    try { await audio.play(); } catch { s.want = false; if (alive() && s.audio === audio) showError(s, t('ui.take.audioError')); }
  }
  function togglePlay() {
    if (!sides) return;
    const s = sides[active];
    if (isPlaying(s)) s.audio.pause(); else if (s.want) s.want = false; else play(s);
  }
  function pause() {
    if (!sides) return;
    const s = sides[active];
    s.want = false;
    if (isPlaying(s)) s.audio.pause();
  }

  /** The shared position moves to `sec` in `from` and, clipped to its duration, in the other audio. */
  function seekShared(sec, from) {
    const o = sides[otherSide(from.name)];
    setTime(from, sec);
    const sp = switchPoint(sec, duration(o));
    setTime(o, sp.pos);
    hintEnd(sp.atEnd ? o : null);
  }
  const hintEnd = (s) => { hint.textContent = s ? t('ui.compare.endHint', { side: LETTER[s.name] }) : ''; };

  /** THE SWITCH: the other side takes the position of the active one and, if it was playing, plays from there. */
  function activate(name) {
    if (!sides || name === active) return;
    const from = sides[active]; const dst = sides[name];
    const wasPlaying = isPlaying(from) || from.want;
    const sp = switchPoint(timeOf(from), duration(dst));
    setTime(dst, sp.pos);
    active = name;
    from.want = false;
    if (wasPlaying) { if (isPlaying(from)) from.audio.pause(); if (!sp.atEnd) play(dst); }
    hintEnd(sp.atEnd ? dst : null);
    paintActive();
    paintTransport();
  }

  /* ---- elegir ---- */
  const chooseSide = (name) => exclusive(async () => {
    const s = sides && sides[name];
    const take = s && takeOf(s);
    if (!take || !canChoose(order, take)) return;
    try {
      const res = await api.choose(project, key, take.id);
      if (!alive()) return;
      toastOk(t('ui.order.chosenToast', { id: take.id }));
      if (res && Array.isArray(res.entries) && res.entries.length) toast(t('ui.order.printsQueued', { id: res.new }));
    } catch (e) { if (alive()) toastError(describeError(e, t)); }
    await refresh();   // also after a failure: the server may have changed (a 409 is usually stale data)
  });

  /* ---- carga ---- */
  function paintHead() {
    const isLine = order.type === 'line';
    replace(head,
      h('div.page-head', {}, h('h1', {}, t('ui.compare.title')), h('span.chip', {}, key), backLink()),
      isLine ? h('blockquote.order-text', {}, order.text || '') : h('blockquote.order-text', {}, order.testText || ''));
  }

  async function refresh() {
    try {
      const res = await loads.run(api.order(project, key));
      if (res === STALE || !alive()) return;
      order = res;
      if (!mounted) {
        paintHead();
        const pair = pickPair(order, route.query);
        if (!pair) { replace(bodyHost, h('p.notice.notice-warn', { role: 'status' }, t('ui.compare.needTwo'))); mounted = true; return; }
        sides = { a: makeSide('a', pair.a), b: makeSide('b', pair.b) };
        replace(bodyHost,
          h('div.row.compare-transport', {}, playBtn, swapBtn, chooseBtns.a, chooseBtns.b, helpBtn), hint,
          h('div.compare-sides', {}, sides.a.node, sides.b.node));
        mounted = true;
        for (const s of Object.values(sides)) attachAudio(s);
        syncHash();
      }
      if (sides) paintSides();
    } catch (e) {
      if (!alive()) return;
      if (!mounted) { replace(bodyHost, h('p.notice.notice-bad', { role: 'alert' }, '✗ ', describeError(e, t)), backLink()); return; }
      toastError(describeError(e, t));
    }
  }

  /* ---- teclado y mando: los mismos filtros que la galería ---- */
  function perform(action) {
    if (!sides) return;
    if (action === 'toggle') togglePlay();
    else if (action === 'prev') activate('a');
    else if (action === 'next') activate('b');
    else if (action === 'swap') activate(otherSide(active));
    else if (action === 'choose') chooseSide(active);
    else if (action === 'pause') pause();
  }
  const merged = mergeSources(perform);   // Steam Input sends the pad as keys too: one press, one action
  const onKey = (e) => {
    if (isQueueOpen() || e.defaultPrevented) return;   // el cajón de la cola está encima: la vista de debajo no actúa
    if (isTyping(e.target) || e.ctrlKey || e.metaKey || e.altKey) return;
    const action = keyAction(e, oneKeyEnabled());
    if (!action || !VIEW_ACTIONS.has(action)) return;   // a key that does nothing here is not blocked
    if ((e.key === 'Enter' || e.key === ' ') && closest(e.target, 'button, a, [role="slider"], summary, dialog')) return;
    e.preventDefault();
    merged.key(action);
  };
  document.addEventListener('keydown', onKey);
  const stopPad = startGamepad((action) => {
    const a = document.activeElement;
    if (isQueueOpen() || isTyping(a) || helpOpen() || closest(a, 'dialog')) return;
    merged.pad(action);
  });

  refresh();
  return {
    node,
    cleanup() {
      life.end();
      loads.invalidate();
      if (raf !== null && typeof cancelAnimationFrame === 'function') cancelAnimationFrame(raf);
      raf = null;
      document.removeEventListener('keydown', onKey);
      stopPad();
      if (sides) for (const s of Object.values(sides)) { s.destroyed = true; releaseAudio(s); s.wave.destroy(); }
    },
  };
}
