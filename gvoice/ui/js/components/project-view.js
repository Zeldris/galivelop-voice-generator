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

const loading = () => h('p.empty', {}, h('span.spin', { aria: { hidden: true } }), ' ', t('ui.loading'));

export function projectView(route) {
  const { project } = route;
  let alive = true;
  let seq = 0;
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
  let opening = false; // guarda: mientras se abre o está abierto, otro clic no abre otro (ids duplicados)
  async function openDialog() {
    if (opening) return;
    opening = true;
    const dlg = await openNewOrder(project, { opener: newBtn, onCreated: () => { if (alive) load(); }, onClose: () => { dialog = null; opening = false; } });
    if (!dlg) { opening = false; return; }
    dialog = dlg;
    if (!alive) closeDialog(); // la ruta cambió mientras se abría
  }
  function closeDialog() {
    if (!dialog) return;
    const dlg = dialog;
    dialog = null;
    dlg.close();
    dlg.remove(); // el `close` async quitaría también el diálogo, pero no hay que esperarlo
    opening = false;
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
    const mine = ++seq; // dos cambios seguidos de filtro: solo vale la respuesta del último
    const query = filtersToQuery({ type: typeSel.value, chosen: chosenSel.value });
    list.setAttribute('aria-busy', 'true');
    replace(list, loading());
    try {
      const res = await api.orders(project, query);
      if (!alive || mine !== seq) return;
      const orders = ordersOf(res).map(orderSummary);
      count.textContent = t('ui.project.orderCount', { n: orders.length });
      replace(list, orders.length ? orders.map((o) => row(project, o)) : h('div.empty', {}, h('p', {}, t(Object.keys(query).length ? 'ui.project.noMatch' : 'ui.project.noOrders'))));
    } catch (e) {
      if (!alive || mine !== seq) return;
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
      if (!alive) return;
      head.append(h('span.path.hint', { title: info.root || '' }, info.root || ''));
    } catch (e) {
      if (!alive) return;
      replace(node, h('div.page-head', {}, h('h1', {}, project)), h('p.notice.notice-bad', { role: 'alert' }, '✗ ', describeError(e, t)),
        h('a.btn', { href: to.projects() }, t('ui.nav.projects')));
      seq++; // la lista no se pide
      return;
    }
    load();
  })();
  return { node, cleanup: () => { alive = false; closeDialog(); } };
}

function row(project, o) {
  const text = o.text ? h('div.text', { title: o.text }, o.text) : null;
  return h('a.card.order-row', { href: to.order(project, o.key), aria: { label: o.key } },
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
}
