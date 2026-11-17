/* Copiado de gimg@46248251 (D7); adaptado a gvoice: sin mover, sin pausar, sin miniaturas ni progreso (la API no los da).
   Barra de cola persistente: pastilla en la cabecera («1 en marcha · 2 en cola») y cajón #queue-drawer con las entradas
   (filtro todas / pendientes / terminadas / fallidas), cancelar las que esperan o corren (POST /api/queue/{id}/cancel)
   y «Vaciar cola» (POST /api/queue/clear, con confirmación; nunca toca lo que corre). Se alimenta de store.queue
   (queue-poll.js) y tras cada acción se vuelve a sondear. La lógica pura vive en queue-model.js. */

import { h, mmss, replace } from '../dom.js';
import * as i18n from '../i18n.js';
import { t } from '../i18n.js';
import { api, describeError } from '../api.js';
import * as store from '../store.js';
import * as router from '../router.js';
import { to } from '../router.js';
import { toast, toastError } from './toast.js';
import { confirmAction } from './confirm.js';
import { refreshNow } from '../queue-poll.js';
import { FILTERS, pillParts, canCancel, clearable, visible, errorOf } from '../queue-model.js';

let filter = 'all';
let open = false;
let hosts = null;
let lastSig = null;
let focusables = new Map(); // data-fid -> nodo del último pintado (para devolver el foco tras repintar)
const inFlight = new Set(); // ids de entradas con su POST de cancelar en curso (hasta que acaba el refresco)

function reg(fid, node) { focusables.set(fid, node); return node; }

export function initQueueBar(pillHost, drawerHost) {
  hosts = { pillHost, drawerHost };
  store.subscribe('queue', render);
  i18n.onChange(() => render());     // la píldora y el cajón cambian de idioma al momento
  router.onChange(() => render());   // «Vaciar cola de <proyecto>» sigue al proyecto actual
  render();
}

/** Para el gancho de cierre de `initShortcuts` (Esc): cierra el cajón si está abierto y devuelve si lo cerró. El foco
    vuelve a la píldora solo si estaba dentro del cajón. */
export function closeQueue() {
  if (!open) return false;
  const inside = hosts && within(document.activeElement, hosts.drawerHost);
  open = false;
  render();
  if (inside) { const pill = focusables.get('pill'); if (pill) pill.focus(); }
  return true;
}

function within(node, root) {
  for (let n = node; n; n = n.parentNode) if (n === root) return true;
  return false;
}

/** Pone el foco en el primer control de la entrada siguiente a `fid` (en el orden del último pintado) o, si no hay, en cerrar. */
function refocusAfter(order, fid) {
  const usable = (id) => { const n = focusables.get(id); return n && !n.disabled ? n : null; };
  const rest = order.slice(order.indexOf(fid) + 1).filter((id) => /^(cancel|go)-/.test(id));
  const seen = new Set();
  for (const id of rest) {
    const entryId = id.replace(/^(cancel|go)-/, '');
    if (seen.has(entryId)) continue;
    seen.add(entryId);
    const n = usable(`cancel-${entryId}`) || usable(`go-${entryId}`);
    if (n) { n.focus(); return; }
  }
  const close = usable('close');
  if (close) close.focus();
}

export function toggleQueue(force) {
  open = force === undefined ? !open : Boolean(force);
  render();
  const target = focusables.get(open ? 'close' : 'pill');
  if (target) target.focus();
}

export function isQueueOpen() { return open; }

function pillLabel(entries) {
  const p = pillParts(entries);
  if (p.idle) return t('ui.queue.empty');
  return [p.running ? t('ui.queue.running', { n: p.running }) : null, p.queued ? t('ui.queue.queued', { n: p.queued }) : null].filter(Boolean).join(' · ');
}

function render() {
  if (!hosts) return;
  const entries = store.get('queue');
  // Solo se repinta si cambia lo que se ve (cada sondeo vuelve a llamar aquí).
  const sig = JSON.stringify([i18n.lang(), open, filter, entries, router.parse().project || null, [...inFlight]]);
  if (sig === lastSig) return;
  lastSig = sig;
  const active = document.activeElement;
  const order = [...focusables.keys()];
  const fid = [...focusables].find(([, n]) => n === active);
  paint(entries);
  if (!fid) return;
  const again = focusables.get(fid[0]);
  const pending = /^cancel-(.+)$/.exec(fid[0]);
  // el botón de la entrada desapareció o quedó deshabilitado (cancelada): el foco pasa a la siguiente entrada o a «cerrar»
  // (mientras su POST va en curso se queda donde está: si falla, el botón sigue ahí)
  if (!again || (again.disabled && !(pending && inFlight.has(Number(pending[1]))))) {
    if (open && /^(cancel|go)-/.test(fid[0])) refocusAfter(order, fid[0]);
    return;
  }
  if (again !== document.activeElement) again.focus();
}

function paint(entries) {
  focusables = new Map();
  const label = pillLabel(entries);
  const running = pillParts(entries).running > 0;
  replace(hosts.pillHost, reg('pill', h('button.queue-pill', {
    type: 'button', class: running ? 'is-running' : '', data: { fid: 'pill' },
    aria: { expanded: open, controls: 'queue-drawer', label: `${t('ui.queue.label')}: ${label}` },
    onclick: () => toggleQueue(),
  }, h('span.dot', { aria: { hidden: true } }), h('span', {}, label))));

  const drawer = hosts.drawerHost;
  drawer.hidden = !open;
  if (!open) return;
  const shown = visible(entries, filter);
  const waiting = clearable(entries);
  const current = router.parse().project;
  const inProject = current ? clearable(entries, current).length : 0;
  replace(drawer,
    h('div.row-between', {}, h('h2', {}, t('ui.queue.label')),
      reg('close', h('button.btn.btn-icon.btn-ghost', { type: 'button', data: { fid: 'close' }, aria: { label: t('ui.queue.close') }, onclick: () => toggleQueue(false) }, '✕'))),
    h('div.row', { role: 'group', aria: { label: t('ui.queue.filterLabel') } }, FILTERS.map((f) =>
      reg(`filter-${f}`, h('button.btn.btn-toggle', { type: 'button', data: { fid: `filter-${f}` }, aria: { pressed: filter === f }, onclick: () => { filter = f; render(); } }, t(`ui.queue.filter.${f}`))))),
    shown.length ? h('div.stack', {}, shown.map(entry)) : h('p.empty', {}, t(filter === 'all' || filter === 'pending' ? 'ui.queue.empty' : 'ui.queue.nothing')),
    waiting.length ? h('div.row', { role: 'group', aria: { label: t('ui.queue.clear') } },
      reg('clear-all', h('button.btn.btn-danger', { type: 'button', data: { fid: 'clear-all' }, onclick: () => clearQueue(null, waiting.length) }, t('ui.queue.clear'), ` (${waiting.length})`)),
      inProject && inProject < waiting.length
        ? reg('clear-project', h('button.btn.btn-danger', { type: 'button', data: { fid: 'clear-project' }, onclick: () => clearQueue(current, inProject) }, t('ui.queue.clearProject', { project: current }), ` (${inProject})`))
        : null) : null,
    h('p.hint', {}, t('ui.queue.idle')));
}

function entry(e) {
  const who = `${e.project} · ${e.key}`;
  const word = (group, value) => (i18n.has(`ui.queue.${group}.${value}`) ? t(`ui.queue.${group}.${value}`) : String(value));   // unknown value: show it raw
  const what = [`${e.state === 'failed' ? '✗ ' : ''}${word('state', e.state)}`, word('kind', e.kind)];
  if (e.seed !== null && e.seed !== undefined) what.push(`${t('ui.queue.seed')} ${e.seed}`);
  if (e.state === 'running' && e.cancelRequested) what.push(t('ui.queue.cancelling'));
  if (e.startedAt && e.finishedAt) what.push(mmss(Date.parse(e.finishedAt) - Date.parse(e.startedAt)));
  const problem = errorOf(e, (key, params) => (i18n.has(key) ? t(key, params) : null));
  const actions = [];
  if (canCancel(e)) {
    actions.push(reg(`cancel-${e.id}`, h('button.btn.btn-danger', { type: 'button', disabled: e.cancelRequested === true || inFlight.has(e.id), data: { fid: `cancel-${e.id}` }, aria: { label: `${t('ui.queue.cancel')}: ${who}` }, onclick: () => cancel(e) }, t('ui.queue.cancel'))));
  } else if (e.project && e.key && e.kind !== 'prints') {
    actions.push(reg(`go-${e.id}`, h('a.btn', { href: to.order(e.project, e.key), data: { fid: `go-${e.id}` }, onclick: () => toggleQueue(false) }, t('ui.queue.goToOrder'))));
  }
  return h('div.queue-entry', { role: 'group', class: `is-${e.state}`, data: { entry: e.id }, aria: { label: `${who}: ${what.join(', ')}` } },
    h('div', {}, h('div.who', {}, who), h('div.what', {}, what.join(' · ')),
      problem ? h('div.what.mono.queue-error', { role: 'note' }, `✗ ${problem}`) : null),
    h('div.stack', {}, actions));
}

async function cancel(e) {
  if (inFlight.has(e.id)) return;
  inFlight.add(e.id);
  render();
  try {
    await api.cancel(e.id);
    toast(t(e.state === 'running' ? 'ui.queue.cancelRequested' : 'ui.queue.cancelled', { id: e.id }));
  } catch (err) { toastError(describeError(err, t)); }
  try { await refreshNow(); } finally { inFlight.delete(e.id); render(); }
}

// claves literales (el test de textos las busca así): singular con n === 1, plural en lo demás
const plural = (one, other, n) => t(n === 1 ? one : other, { n });

/** «Vaciar cola»: confirma y cancela todo lo que espera (de un proyecto, si se da). Lo que corre no se toca. */
async function clearQueue(project, n) {
  const fid = project ? 'clear-project' : 'clear-all';
  const ok = await confirmAction({
    title: t('ui.queue.clearTitle'), message: plural('ui.queue.clearMessage.one', 'ui.queue.clearMessage.other', n), confirmLabel: t('ui.queue.clearConfirm'),
    opener: () => focusables.get(fid) || focusables.get('pill'),
  });
  if (!ok) return;
  try {
    const cancelled = await api.clearQueue(project);
    toast(plural('ui.queue.cleared.one', 'ui.queue.cleared.other', Array.isArray(cancelled) ? cancelled.length : n));
    await refreshNow();
  } catch (err) { toastError(describeError(err, t)); await refreshNow(); }
}
