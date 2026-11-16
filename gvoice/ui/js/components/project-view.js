/* Copiado de gimg@46248251 (D7); adaptado a gvoice (F5.2): pedidos de un proyecto, con filtros `type` y `chosen` que
   quedan en la URL (`#/p/<proyecto>/orders?type=voice&chosen=true`), y el botón «Nuevo pedido».
   GET /api/projects/{p} (config: voces) y GET /api/projects/{p}/orders?type=&chosen=. Sin pestañas: las piezas y la marca
   son de imágenes. La lógica pura (filtros, resumen de fila) está en ../order-model.js. */

import { h, replace } from '../dom.js';
import { t } from '../i18n.js';
import { api, describeError } from '../api.js';
import { to, replaceHash } from '../router.js';
import { filtersFromQuery, filtersToQuery, orderSummary, ordersOf } from '../order-model.js';
import { openNewOrder } from './new-order.js';
import { openSheetDialog } from './sheet-dialog.js';
import { busy, latest, lifetime, STALE } from '../async-guard.js';

const loading = () => h('p.empty', {}, h('span.spin', { aria: { hidden: true } }), ' ', t('ui.loading'));

export function projectView(route) {
  const { project } = route;
  const life = lifetime();
  const alive = life.alive;
  const loads = latest(); // dos cambios seguidos de filtro: solo vale la respuesta del último
  const filters = filtersFromQuery(route.query);

  const typeSel = h('select', { id: 'f-type' },
    h('option', { value: '', selected: filters.type === '' }, t('ui.project.filter.all')),
    h('option', { value: 'voice', selected: filters.type === 'voice' }, t('ui.project.type.voice')),
    h('option', { value: 'line', selected: filters.type === 'line' }, t('ui.project.type.line')));
  const chosenSel = h('select', { id: 'f-chosen' },
    h('option', { value: '', selected: filters.chosen === '' }, t('ui.project.filter.all')),
    h('option', { value: 'true', selected: filters.chosen === 'true' }, t('ui.project.filter.chosen')),
    h('option', { value: 'false', selected: filters.chosen === 'false' }, t('ui.project.filter.unchosen')));
  const count = h('span.hint', { aria: { live: 'polite' } });
  const list = h('div.order-list', { aria: { live: 'polite', busy: 'true' } }, loading());
  let dialog = null;   // el diálogo abierto
  // guarda: mientras se abre o está abierto, otro clic no abre otro (ids duplicados); `release` al cerrarse
  const openDialog = busy(async () => {
    const dlg = await openNewOrder(project, { opener: newBtn, onCreated: () => { if (alive()) load(); }, onClose: () => { dialog = null; openDialog.release(); } });
    if (!dlg) return null;
    dialog = dlg;
    if (!alive()) closeDialog(); // la ruta cambió mientras se abría
    return dlg;
  }, { keep: (dlg) => Boolean(dlg) });
  function closeDialog() {
    if (!dialog) return;
    const dlg = dialog;
    dialog = null;
    dlg.close();
    dlg.remove(); // el `close` async quitaría también el diálogo, pero no hay que esperarlo
    openDialog.release();
  }
  let sheetDlg = null;  // el diálogo «Ficha» abierto (uno a la vez)
  const openSheet = busy(async (key, opener) => {
    const dlg = await openSheetDialog(project, key, { opener, isAlive: alive, onClose: () => { sheetDlg = null; openSheet.release(); } });
    if (!dlg) return null;
    sheetDlg = dlg;
    if (!alive()) closeSheet();
    return dlg;
  }, { keep: (dlg) => Boolean(dlg) });
  function closeSheet() {
    if (!sheetDlg) return;
    const dlg = sheetDlg;
    sheetDlg = null;
    dlg.close();
    dlg.remove();
    openSheet.release();
  }
  const newBtn = h('button.btn.btn-primary', { type: 'button', onclick: openDialog }, '+ ', t('ui.project.newOrder'));
  const head = h('div.page-head', {}, h('h1', {}, project));
  const node = h('section', {}, head,
    h('div.filters', {},
      h('div.field', {}, h('label', { for: 'f-type' }, t('ui.project.filter.type')), typeSel),
      h('div.field', {}, h('label', { for: 'f-chosen' }, t('ui.project.filter.chosenLabel')), chosenSel),
      count, h('span.grow'), newBtn),
    list);

  async function load() {
    const query = filtersToQuery({ type: typeSel.value, chosen: chosenSel.value });
    list.setAttribute('aria-busy', 'true');
    replace(list, loading());
    try {
      const res = await loads.run(api.orders(project, query));
      if (res === STALE || !alive()) return;
      const orders = ordersOf(res).map(orderSummary);
      count.textContent = t('ui.project.orderCount', { n: orders.length });
      replace(list, orders.length ? orders.map((o) => row(project, o, openSheet)) : h('div.empty', {}, h('p', {}, t(Object.keys(query).length ? 'ui.project.noMatch' : 'ui.project.noOrders'))));
    } catch (e) {
      if (!alive()) return;
      count.textContent = '';
      replace(list, h('p.notice.notice-bad', { role: 'alert' }, '✗ ', describeError(e, t)));
    }
    list.setAttribute('aria-busy', 'false');
  }
  const onFilter = () => { replaceHash(to.project(project, 'orders', filtersToQuery({ type: typeSel.value, chosen: chosenSel.value }))); load(); };
  typeSel.addEventListener('change', onFilter);
  chosenSel.addEventListener('change', onFilter);

  // primero el proyecto (su existencia y su carpeta), luego los pedidos
  (async () => {
    try {
      const info = await api.project(project);
      if (!alive()) return;
      head.append(h('span.path.hint', { title: info.root || '' }, info.root || ''));
    } catch (e) {
      if (!alive()) return;
      replace(node, h('div.page-head', {}, h('h1', {}, project)), h('p.notice.notice-bad', { role: 'alert' }, '✗ ', describeError(e, t)),
        h('a.btn', { href: to.projects() }, t('ui.nav.projects')));
      loads.invalidate(); // la lista no se pide
      return;
    }
    load();
  })();
  return { node, cleanup: () => { life.end(); closeDialog(); closeSheet(); } };
}

function row(project, o, openSheet) {
  const text = o.text ? h('div.text', { title: o.text }, o.text) : null;
  const link = h('a.card.order-row', { href: to.order(project, o.key), aria: { label: o.key } },
    h('div', {},
      h('div.key', {}, o.key),
      h('div.meta', {},
        h('span.chip', {}, t(o.type === 'line' ? 'ui.project.type.line' : 'ui.project.type.voice')),
        o.voice ? h('span', {}, t('ui.project.voice', { voice: o.voice })) : null,
        h('span', {}, t('ui.project.takes', { n: o.takes }))),
      text),
    o.chosen
      ? h('span.chip.chip-ok', {}, '✓ ', t('ui.project.chosen'), o.chosenId !== null ? ` · ${t('ui.project.takeN', { id: o.chosenId })}` : '')
      : h('span.chip', {}, t('ui.project.unchosen')));
  if (o.type !== 'voice') return link;
  // el botón no puede ir dentro del enlace: va al lado, en su propia línea
  const sheetBtn = h('button.btn', { type: 'button', aria: { label: `${t('ui.sheet.open')}: ${o.key}` }, onclick: () => openSheet(o.key, sheetBtn) }, t('ui.sheet.open'));
  return h('div.order-item', {}, link, h('div.row.order-actions', {}, sheetBtn));
}
