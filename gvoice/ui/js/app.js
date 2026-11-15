/* Copiado de gimg@46248251 (D7); adaptado a gvoice: solo la carcasa (F5.1). Las vistas llegan con F5.2 y siguientes.
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

async function boot() {
  const params = new URLSearchParams(location.search);
  if (params.get('mock') === '1') {
    const mock = await import('/ui/mock/api-mock.js');
    setTransport(mock.transport);
  }
  await i18n.load(i18n.detect());
  applyStatic();
  const langSel = el('lang');
  langSel.value = i18n.lang();
  langSel.addEventListener('change', async () => { await i18n.load(langSel.value); applyStatic(); render(router.parse()); });
  // «Saltar al contenido»: sin pasar por el router de hash (#main no es una ruta); la CSP prohíbe onclick en el HTML
  const skip = document.querySelector('a.skip');
  if (skip) skip.addEventListener('click', (e) => { e.preventDefault(); el('main').focus(); });
  initTheme(el('theme'));

  onOffline((off) => {
    const banner = el('banner');
    banner.hidden = !off;
    replace(banner, h('span.dot', { aria: { hidden: true } }), h('b', {}, t('ui.offline.title')), h('span', {}, t('ui.offline.hint')), h('code.mono', {}, 'gvoice ui'),
      h('button.btn.btn-ghost', { type: 'button', onclick: () => location.reload() }, t('ui.offline.retry')));
  });

  router.onChange(render);
  router.start();
  try { await api.health(); } catch { /* sin API todavía (F4): la carcasa no la necesita; la banda avisa si no hay servidor */ }
}

let current = null;
function render(route) {
  const main = el('main');
  if (current && current.cleanup) current.cleanup();
  const host = h('div');
  main.replaceChildren(host);
  current = host;
  crumbs(route);
  try {
    if (route.name === 'notfound') host.append(h('div.empty', {}, h('p', {}, t('ui.nav.notFound')), h('a.btn', { href: to.projects() }, t('ui.nav.projects'))));
    else host.append(soon(route));
  } catch (e) {
    console.error(e);
    toastError(t('ui.error.generic', { message: e.message || String(e) }));
  }
  document.title = `${titleOf(route)} · Galivelop Voice Generator`;
}

/** La vista vacía de cada ruta, hasta que llegue la real (F5.2: proyectos y pedidos). */
function soon(route) {
  return h('section.empty', {}, h('h1', {}, titleOf(route)), h('p', {}, t('ui.soon.text')));
}

function titleOf(route) {
  if (route.name === 'order') return route.key;
  if (route.name === 'project') return route.project;
  return t('ui.projects.title');
}

function crumbs(route) {
  const sep = () => h('span.sep', { aria: { hidden: true } }, '›');
  const parts = [h('a', { href: to.projects() }, t('ui.nav.projects'))];
  if (route.name === 'project' || route.name === 'order') {
    parts.push(sep(), route.name === 'project' ? h('b', { aria: { current: 'page' } }, route.project) : h('a', { href: to.project(route.project) }, route.project));
  }
  if (route.name === 'order') parts.push(sep(), h('b', { aria: { current: 'page' } }, route.key));
  replace(el('crumbs'), parts);
}

/** Textos estáticos del index.html: data-i18n (contenido) y data-i18n-aria-label. */
function applyStatic() {
  for (const n of document.querySelectorAll('[data-i18n]')) n.textContent = t(n.dataset.i18n);
  for (const n of document.querySelectorAll('[data-i18n-aria-label]')) n.setAttribute('aria-label', t(n.dataset.i18nAriaLabel));
}

boot().catch((e) => { console.error(e); const m = el('main'); m.replaceChildren(h('p.notice.notice-bad', { role: 'alert' }, String(e.message || e))); });
