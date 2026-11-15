/* Nuevo en gvoice (no copiado de gimg) (F5.4; la vista de pedido de gimg es de imágenes: aquí no hay lightbox, retoque
   ni plantillas). Un pedido: su cabecera (clave, tipo, texto; en `line` la voz y si está desfasada; en `voice` las frases
   desfasadas), la galería de tomas (una `takeCard` por toma, con reproductor, forma de onda, estado, nota y huellas) y un
   panel con la elegida, «Deshacer elección», más tomas y la ayuda de atajos. Teclado y mando de la Deck: shortcuts.js.
   GET …/orders/{key} y GET /api/queue (las huellas y las tomas pendientes); elegir y deshacer recargan el pedido.
   Devuelve {node, cleanup}: cleanup revoca las URL de audio, quita las escuchas y para el sondeo. */

import { h, replace, closest } from '../dom.js';
import { t } from '../i18n.js';
import { api, describeError } from '../api.js';
import { to } from '../router.js';
import { busy, latest, lifetime, STALE } from '../async-guard.js';
import { openEntries, pendingTakes, takeState, undoTarget } from '../take-model.js';
import { MAX_COUNT } from '../order-model.js';
import { takeCard } from './take-card.js';
import { icon } from './icons.js';
import { warningIcon } from './sheet-warnings.js';
import { isTyping, keyAction, oneKeyEnabled, openHelp, startGamepad } from './shortcuts.js';
import { toast, toastError, toastOk } from './toast.js';

export const POLL_MS = 3000;
const loading = () => h('p.empty', {}, h('span.spin', { aria: { hidden: true } }), ' ', t('ui.loading'));

export function orderView(route) {
  const { project, key } = route;
  const life = lifetime();
  const alive = life.alive;
  const loads = latest();
  const exclusive = busy(async (fn) => fn());   // elegir, deshacer y pedir tomas: uno a la vez
  const cards = new Map();                       // id de toma -> takeCard
  let order = null; let models = []; let entries = []; let current = null; let timer = null; let focusFirst = route.query && route.query.a ? Number(route.query.a) : null;

  const head = h('div.order-head');
  const gallery = h('div.gallery.take-list');
  const emptyNote = h('p.empty', { hidden: true }, t('ui.order.noTakes'));
  const chosenLine = h('p.order-chosen', { aria: { live: 'polite' } });
  const undoHint = h('p.hint');
  const undoBtn = h('button.btn', { type: 'button', disabled: true, onclick: () => undo() }, icon('undo'), ' ', t('ui.order.undo'));
  const printsNote = h('p.notice.notice-warn', { hidden: true }, t('ui.order.voiceNote'));
  const pending = h('p.hint', { aria: { live: 'polite' } });
  const count = h('input', { id: 'more-count', type: 'number', min: 1, max: MAX_COUNT, step: 1, value: 1 });
  const moreBtn = h('button.btn', { type: 'button', onclick: () => more() }, icon('plus'), ' ', t('ui.order.more'));
  const helpBtn = h('button.btn.btn-ghost', { type: 'button', onclick: () => openHelp(helpBtn) }, icon('keys'), ' ', t('ui.shortcuts.open'), ' ', h('kbd.kbd', {}, '?'));
  const panel = h('aside.order-panel', { aria: { label: t('ui.order.panel') } },
    h('div.card', {}, h('h2', {}, t('ui.order.election')), chosenLine, undoBtn, undoHint),
    printsNote,
    h('div.card', {}, h('h2', {}, t('ui.order.moreTitle')), h('div.field', {}, h('label', { for: 'more-count' }, t('ui.order.moreCount')), count), moreBtn, pending),
    helpBtn);
  const list = h('section', {}, h('h2', {}, t('ui.order.takes')), emptyNote, gallery);
  const body = h('div.order-layout', {}, panel, list);
  const node = h('section.order', {}, head, h('div.order-body', {}, loading()));
  const bodyHost = node.children[1];

  /* ---- carga ---- */
  async function refresh({ first = false } = {}) {
    try {
      const res = await loads.run(Promise.all([api.order(project, key), api.queue().catch(() => []), first ? api.project(project) : Promise.resolve(null)]));
      if (res === STALE || !alive()) return;
      order = res[0];
      entries = openEntries(res[1], project, key);
      if (res[2]) models = (res[2].config && res[2].config.printModels) || [];
      if (first) replace(bodyHost, body);
      paint();
    } catch (e) {
      if (!alive()) return;
      if (first) replace(bodyHost, h('p.notice.notice-bad', { role: 'alert' }, '✗ ', describeError(e, t)), h('a.btn', { href: to.project(project) }, project));
      else toastError(describeError(e, t));
    }
  }

  /* ---- pintura ---- */
  function paint() {
    paintHead();
    const takes = [...(order.attempts || [])].sort((a, b) => a.id - b.id);
    const ids = new Set(takes.map((a) => a.id));
    for (const [id, card] of cards) if (!ids.has(id)) { card.destroy(); card.node.remove(); cards.delete(id); }
    const fresh = [];
    for (const take of takes) {
      let card = cards.get(take.id);
      if (!card) {
        card = takeCard({ project, key, type: order.type, models, alive, actions: { mark, note, choose: (tk) => choose(tk) }, onPlay: pauseOthers });
        cards.set(take.id, card);
        fresh.push(card);
      }
      card.update(take, { order, entries });
    }
    const want = takes.map((a) => cards.get(a.id).node);
    const have = [...gallery.children];
    if (want.some((n, i) => have[i] !== n)) {  // normalmente solo se añaden al final; mover una tarjeta con audio sonando lo pararía
      const prefix = have.length <= want.length && have.every((n, i) => want[i] === n);
      if (prefix) gallery.append(...want.slice(have.length)); else gallery.replaceChildren(...want);
    }
    for (const c of fresh) c.load();
    emptyNote.hidden = takes.length > 0;
    if (!cards.has(current)) current = null;
    if (current === null && takes.length) current = (focusFirst !== null && ids.has(focusFirst)) ? focusFirst : (order.chosen !== null && ids.has(order.chosen) ? order.chosen : takes[0].id);
    setCurrent(current, focusFirst !== null && ids.has(focusFirst));
    focusFirst = null;
    paintPanel();
    clearTimeout(timer);
    if (entries.length) timer = setTimeout(() => { if (alive()) refresh(); }, POLL_MS);
  }

  function paintHead() {
    const isLine = order.type === 'line';
    replace(head,
      h('div.page-head', {}, h('h1', {}, key),
        h('span.chip', {}, t(isLine ? 'ui.project.type.line' : 'ui.project.type.voice')),
        isLine && order.voice ? h('a.chip', { href: to.order(project, order.voice) }, t('ui.project.voice', { voice: order.voice })) : null,
        isLine && order.stale ? h('span.chip.chip-warn', {}, t('ui.order.stale')) : null),
      isLine
        ? h('blockquote.order-text', {}, order.text || '')
        : h('div', {}, h('p.label', {}, t('ui.order.testText')), h('blockquote.order-text', {}, order.testText || '')),
      isLine && order.stale ? h('p.notice.notice-warn', { role: 'status' }, warningIcon('default'), h('span', {}, t('ui.order.staleHint'))) : null,
      !isLine && (order.staleLines || []).length
        ? h('div.notice.notice-warn', { role: 'status' }, warningIcon('default'),
          h('div', {}, h('p', {}, t('ui.order.staleLines', { n: order.staleLines.length })),
            h('ul.stale-lines', {}, order.staleLines.map((k) => h('li', {}, h('a', { href: to.order(project, k) }, k))))))
        : null);
  }

  function paintPanel() {
    const target = undoTarget(order);
    replace(chosenLine, order.chosen === null || order.chosen === undefined
      ? t('ui.order.noneChosen')
      : [icon('check', 'icon icon-s'), ' ', h('b', {}, t('ui.order.chosenNow', { id: order.chosen }))]);
    undoBtn.disabled = target === undefined;
    undoHint.textContent = target === undefined ? t('ui.order.undoEmpty') : target === null ? t('ui.order.undoToNone') : t('ui.order.undoTo', { id: target });
    printsNote.hidden = order.type !== 'voice';
    const n = pendingTakes(entries);
    pending.textContent = n ? t('ui.order.pending', { n }) : '';
  }

  /* ---- acciones (las tarjetas las llaman; cada fallo, con su aviso) ---- */
  async function mark(take, state) {
    try {
      const res = await api.mark(project, key, take.id, state);
      if (!alive()) return false;
      Object.assign(take, res && typeof res === 'object' ? res : { state });
      paint();
      return true;
    } catch (e) { if (alive()) toastError(describeError(e, t)); return false; }
  }
  async function note(take, text) {
    try {
      const res = await api.note(project, key, take.id, text);
      if (!alive()) return false;
      Object.assign(take, res && typeof res === 'object' ? res : { note: text });
      toastOk(t('ui.take.noteSaved', { id: take.id }), { timeout: 2500 });
      return true;
    } catch (e) { if (alive()) toastError(describeError(e, t)); return false; }
  }
  const afterChange = (res) => { if (res && Array.isArray(res.entries) && res.entries.length && alive()) toast(t('ui.order.printsQueued', { id: res.new })); };
  const choose = (take) => exclusive(async () => {
    try {
      const res = await api.choose(project, key, take.id);
      if (!alive()) return;
      toastOk(t('ui.order.chosenToast', { id: take.id }));
      afterChange(res);
    } catch (e) { if (alive()) toastError(describeError(e, t)); }
    await refresh();   // también tras un fallo: el servidor pudo cambiar (un 409 suele ser un dato viejo)
  });
  const undo = () => exclusive(async () => {
    try {
      const res = await api.undo(project, key);
      if (!alive()) return;
      toastOk(res.new === null || res.new === undefined ? t('ui.order.undoneNone') : t('ui.order.undoneTo', { id: res.new }));
      afterChange(res);
    } catch (e) { if (alive()) toastError(describeError(e, t)); }
    await refresh();
  });
  const more = () => exclusive(async () => {
    const n = Number(count.value);
    if (!Number.isInteger(n) || n < 1 || n > MAX_COUNT) { toastError(t('ui.newOrder.error.count', { max: MAX_COUNT })); count.focus(); return; }
    try {
      const res = await api.newTakes(project, key, { count: n });
      if (!alive()) return;
      toastOk(t('ui.order.moreSent', { n: Array.isArray(res) ? res.length : n }));
    } catch (e) { if (alive()) toastError(describeError(e, t)); return; }
    await refresh();
  });

  /* ---- reproducción y foco ---- */
  function pauseOthers(card) { for (const c of cards.values()) if (c !== card) c.pause(); }
  const takeIds = () => [...cards.keys()].sort((a, b) => a - b);
  function setCurrent(id, focus = false) {
    current = id;
    for (const [cid, c] of cards) c.node.setAttribute('tabindex', cid === id ? '0' : '-1');
    const c = cards.get(id);
    if (c && focus) { c.focus(); if (c.node.scrollIntoView) c.node.scrollIntoView({ block: 'nearest' }); }
  }
  function move(delta) {
    const ids = takeIds();
    if (!ids.length) return;
    const i = ids.indexOf(current);
    setCurrent(ids[Math.max(0, Math.min(ids.length - 1, i < 0 ? 0 : i + delta))], true);
  }
  function perform(action) {
    const card = cards.get(current);
    const take = card && order && order.attempts.find((a) => a.id === current);
    if (action === 'prev') move(-1);
    else if (action === 'next') move(1);
    else if (action === 'pause') { for (const c of cards.values()) c.pause(); }
    else if (action === 'undo') undo();
    else if (action === 'another') more();
    else if (!card || !take) return;
    else if (action === 'toggle') card.toggle();
    else if (action === 'choose') { if (takeState(order, take) !== 'chosen') choose(take); }
    else if (action === 'candidate') mark(take, take.state === 'candidate' ? 'new' : 'candidate');
    else if (action === 'discard') { if (order.chosen !== take.id) mark(take, take.state === 'discarded' ? 'new' : 'discarded'); }
  }
  const onKey = (e) => {
    if (isTyping(e.target) || e.ctrlKey || e.metaKey || e.altKey) return;
    const action = keyAction(e, oneKeyEnabled());
    if (!action) return;
    // Intro y espacio sobre un botón, un enlace o la forma de onda hacen lo suyo; en la tarjeta o en la página, reproducen
    if ((e.key === 'Enter' || e.key === ' ') && closest(e.target, 'button, a, [role="slider"], summary, dialog')) return;
    e.preventDefault();
    perform(action);
  };
  document.addEventListener('keydown', onKey);
  const stopPad = startGamepad(perform);
  gallery.addEventListener('focusin', (e) => {
    const c = closest(e.target, '.take-card');
    if (c && c.dataset.take && Number(c.dataset.take) !== current) setCurrent(Number(c.dataset.take));
  });

  refresh({ first: true });
  return {
    node,
    cleanup() {
      life.end();
      loads.invalidate();
      clearTimeout(timer);
      document.removeEventListener('keydown', onKey);
      stopPad();
      for (const c of cards.values()) c.destroy();
      cards.clear();
    },
  };
}
