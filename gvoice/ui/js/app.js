/* Copiado de gimg@46248251 (D7); adaptado a gvoice: la carcasa (F5.1) y las vistas de proyectos (F5.2), de pedido (F5.4) y de comparación A/B (F5.5).
   Arranque de Galivelop Voice Generator: idioma, tema, textos estáticos, banda «sin servicio», rutas y avisos.
   Con `?mock=1` en la URL carga /ui/mock/api-mock.js y sustituye el transporte (prototipo sin API). */

import { h, el, replace } from './dom.js';
import * as i18n from './i18n.js';
import { t } from './i18n.js';
import { onOffline, setTransport, api } from './api.js';
import * as router from './router.js';
import { to } from './router.js';
import { initTheme } from './components/theme.js';
import { toastError } from './components/toast.js';
import { projectsView } from './components/projects-view.js';
import { projectView } from './components/project-view.js';
import { orderView } from './components/order-view.js';
import { compareView } from './components/compare-view.js';
import { initShortcuts } from './components/shortcuts.js';

async function boot() {
  const params = new URLSearchParams(location.search);
  if (params.get('mock') === '1') {
    const mock = await import('/ui/mock/api-mock.js');
    setTransport(mock.transport);
  }
  onOffline((off) => {
    const banner = el('banner');
    banner.hidden = !off;
    // con el diccionario aún vacío (el arranque ya encuentra la API caída) valen los textos de reserva, nunca las claves
    const text = (key, fallback) => (i18n.has(key) ? t(key) : fallback);
    replace(banner, h('span.dot', { aria: { hidden: true } }), h('b', {}, text('ui.offline.title', 'Sin servicio')),
      h('span', {}, text('ui.offline.hint', 'No responde la API local. Arranca el servidor con')), h('code.mono', {}, 'gvoice ui'),
      h('button.btn.btn-ghost', { type: 'button', onclick: () => location.reload() }, text('ui.offline.retry', 'Reintentar')));
  });

  try { await i18n.load(i18n.detect()); } catch { /* sin servicio: la banda lo avisa y los textos de reserva del HTML se quedan */ }
  applyStatic();
  const langSel = el('lang');
  langSel.value = i18n.lang();
  langSel.addEventListener('change', async () => {
    try { await i18n.load(langSel.value); } catch { langSel.value = i18n.lang(); return; } // sin servicio: se queda el idioma anterior
    applyStatic(); render(router.parse());
  });
  // «Saltar al contenido»: sin pasar por el router de hash (#main no es una ruta); la CSP prohíbe onclick en el HTML
  const skip = document.querySelector('a.skip');
  if (skip) skip.addEventListener('click', (e) => { e.preventDefault(); el('main').focus(); });
  initTheme(el('theme'));
  initShortcuts();

  router.onChange(render);
  router.start();
  try { await api.health(); } catch { /* sin API todavía (F4): la carcasa no la necesita; la banda avisa si no hay servidor */ }
}

/* Cada vista devuelve {node, cleanup?}: el nodo se pinta en #main y `cleanup` (si la vista la necesita) se llama
   al cambiar de ruta, antes de pintar la siguiente. */
let cleanup = null;
function render(route) {
  const main = el('main');
  if (cleanup) { try { cleanup(); } catch (e) { console.error(e); } cleanup = null; }
  const host = h('div');
  main.replaceChildren(host);
  crumbs(route);
  try {
    if (route.name === 'notfound') host.append(h('div.empty', {}, h('p', {}, t('ui.nav.notFound')), h('a.btn', { href: to.projects() }, t('ui.nav.projects'))));
    else {
      const view = route.name === 'projects' ? projectsView() : route.name === 'project' ? projectView(route) : route.name === 'compare' ? compareView(route) : orderView(route);
      host.append(view.node);
      cleanup = view.cleanup || null;
    }
  } catch (e) {
    console.error(e);
    toastError(t('ui.error.generic', { message: e.message || String(e) }));
  }
  document.title = `${titleOf(route)} · Galivelop Voice Generator`;
}

function titleOf(route) {
  if (route.name === 'compare') return `${t('ui.compare.title')} · ${route.key}`;
  if (route.name === 'order') return route.key;
  if (route.name === 'project') return route.project;
  return t('ui.projects.title');
}

function crumbs(route) {
  const sep = () => h('span.sep', { aria: { hidden: true } }, '›');
  const parts = [h('a', { href: to.projects() }, t('ui.nav.projects'))];
  if (route.name === 'project' || route.name === 'order' || route.name === 'compare') {
    parts.push(sep(), route.name === 'project' ? h('b', { aria: { current: 'page' } }, route.project) : h('a', { href: to.project(route.project) }, route.project));
  }
  if (route.name === 'order') parts.push(sep(), h('b', { aria: { current: 'page' } }, route.key));
  if (route.name === 'compare') parts.push(sep(), h('a', { href: to.order(route.project, route.key) }, route.key), sep(), h('b', { aria: { current: 'page' } }, t('ui.compare.crumb')));
  replace(el('crumbs'), parts);
}

/** Textos estáticos del index.html: data-i18n (contenido) y data-i18n-aria-label. */
function applyStatic() {
  for (const n of document.querySelectorAll('[data-i18n]')) if (i18n.has(n.dataset.i18n)) n.textContent = t(n.dataset.i18n);
  for (const n of document.querySelectorAll('[data-i18n-aria-label]')) if (i18n.has(n.dataset.i18nAriaLabel)) n.setAttribute('aria-label', t(n.dataset.i18nAriaLabel));
}

boot().catch((e) => { console.error(e); const m = el('main'); m.replaceChildren(h('p.notice.notice-bad', { role: 'alert' }, String(e.message || e))); });
