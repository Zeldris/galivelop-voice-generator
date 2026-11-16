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

function reg(fid, node) { focusables.set(fid, node); return node; }

export function initQueueBar(pillHost, drawerHost) {
  hosts = { pillHost, drawerHost };
  store.subscribe('queue', render);
  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape' && open) toggleQueue(false);
  });
  render();
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
  const sig = JSON.stringify([i18n.lang(), open, filter, entries, router.parse().project || null]);
  if (sig === lastSig) return;
  lastSig = sig;
  const active = document.activeElement;
  const fid = [...focusables].find(([, n]) => n === active);
  paint(entries);
  const again = fid && focusables.get(fid[0]);
  if (again && again !== document.activeElement) again.focus();
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
  const what = [`${e.state === 'failed' ? '✗ ' : ''}${t(`ui.queue.state.${e.state}`)}`, t(`ui.queue.kind.${e.kind}`)];
  if (e.seed !== null && e.seed !== undefined) what.push(`${t('ui.queue.seed')} ${e.seed}`);
  if (e.state === 'running' && e.cancelRequested) what.push(t('ui.queue.cancelling'));
  if (e.startedAt && e.finishedAt) what.push(mmss(Date.parse(e.finishedAt) - Date.parse(e.startedAt)));
  const problem = errorOf(e, (key, params) => (i18n.has(key) ? t(key, params) : null));
  const actions = [];
  if (canCancel(e)) {
    actions.push(reg(`cancel-${e.id}`, h('button.btn.btn-danger', { type: 'button', disabled: e.cancelRequested === true, data: { fid: `cancel-${e.id}` }, aria: { label: `${t('ui.queue.cancel')}: ${who}` }, onclick: () => cancel(e) }, t('ui.queue.cancel'))));
  } else if (e.project && e.key && e.kind !== 'prints') {
    actions.push(h('a.btn', { href: to.order(e.project, e.key), data: { fid: `go-${e.id}` }, onclick: () => toggleQueue(false) }, t('ui.queue.goToOrder')));
  }
  return h('div.queue-entry', { class: `is-${e.state}`, data: { entry: e.id }, aria: { label: `${who}: ${what.join(', ')}` } },
    h('div', {}, h('div.who', {}, who), h('div.what', {}, what.join(' · ')),
      problem ? h('div.what.mono.queue-error', { role: 'note' }, `✗ ${problem}`) : null),
    h('div.stack', {}, actions));
}

async function cancel(e) {
  try {
    await api.cancel(e.id);
    toast(t('ui.queue.cancelled', { id: e.id }));
    await refreshNow();
  } catch (err) { toastError(describeError(err, t)); await refreshNow(); }
}

/** «Vaciar cola»: confirma y cancela todo lo que espera (de un proyecto, si se da). Lo que corre no se toca. */
async function clearQueue(project, n) {
  const fid = project ? 'clear-project' : 'clear-all';
  const ok = await confirmAction({
    title: t('ui.queue.clearTitle'), message: t('ui.queue.clearMessage', { n }), confirmLabel: t('ui.queue.clearConfirm'),
    opener: () => focusables.get(fid) || focusables.get('pill'),
  });
  if (!ok) return;
  try {
    const cancelled = await api.clearQueue(project);
    toast(t('ui.queue.cleared', { n: Array.isArray(cancelled) ? cancelled.length : n }));
    await refreshNow();
  } catch (err) { toastError(describeError(err, t)); await refreshNow(); }
}
