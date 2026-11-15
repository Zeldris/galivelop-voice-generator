/* Copiado de gimg@46248251 (D7); adaptado a gvoice (F5.2): proyectos registrados, registrar uno por su carpeta y quitarlo.
   GET /api/projects, POST /api/projects {path} y POST /api/projects/{p}/remove. La vista devuelve su nodo y la función
   que la desactiva al cambiar de ruta (una respuesta tardía ya no pinta). */

import { h, replace } from '../dom.js';
import { t } from '../i18n.js';
import { api, describeError } from '../api.js';
import { to } from '../router.js';
import { confirmAction } from './confirm.js';
import { toastError, toastOk } from './toast.js';

const loading = () => h('p.empty', {}, h('span.spin', { aria: { hidden: true } }), ' ', t('ui.loading'));

export function projectsView() {
  let alive = true;
  let seq = 0;
  const count = h('span.hint', { aria: { live: 'polite' } });
  const list = h('div', { aria: { live: 'polite', busy: 'true' } }, loading());
  const path = h('input', { id: 'pv-path', type: 'text', autocomplete: 'off', spellcheck: 'false', aria: { describedby: 'pv-path-hint pv-path-error' } });
  const error = h('p.field-error', { id: 'pv-path-error', role: 'alert', hidden: true });
  const send = h('button.btn.btn-primary', { type: 'submit' }, t('ui.projects.add.submit'));
  const form = h('form.add-project', { novalidate: true, onsubmit: (ev) => { ev.preventDefault(); add(); } },
    h('div.field', {}, h('label', { for: 'pv-path' }, t('ui.projects.add.label')), path, h('span.hint', { id: 'pv-path-hint' }, t('ui.projects.add.hint')), error),
    h('div.row', {}, send));

  async function add() {
    const value = path.value.trim();
    error.hidden = true;
    if (!value) { error.textContent = `✗ ${t('ui.projects.add.required')}`; error.hidden = false; path.focus(); return; }
    send.disabled = true;
    try {
      const res = await api.addProject(value);
      if (!alive) return;
      path.value = '';
      toastOk(t('ui.projects.added', { name: (res && res.name) || value }));
      await load();
    } catch (e) {
      if (!alive) return;
      const message = describeError(e, t);
      error.textContent = `✗ ${message}`;
      error.hidden = false;
      toastError(message);
      path.focus();
    }
    send.disabled = false;
  }

  async function remove(p, opener) {
    const yes = await confirmAction({
      title: t('ui.projects.remove.title', { name: p.name }),
      message: t('ui.projects.remove.message', { name: p.name, root: p.root || '' }),
      confirmLabel: t('ui.projects.remove.confirm'), opener,
    });
    if (!yes || !alive) return;
    try {
      await api.removeProject(p.name);
      toastOk(t('ui.projects.removed', { name: p.name }));
    } catch (e) { toastError(describeError(e, t)); }
    if (alive) await load();
  }

  async function load() {
    const mine = ++seq;
    list.setAttribute('aria-busy', 'true');
    try {
      const res = await api.projects();
      if (!alive || mine !== seq) return;
      const projects = (Array.isArray(res) ? res : (res && res.projects) || []).slice().sort((a, b) => String(a.name).localeCompare(String(b.name)));
      count.textContent = t('ui.projects.count', { n: projects.length });
      replace(list, projects.length
        ? h('div.project-grid', {}, projects.map((p) => card(p, remove)))
        : h('div.empty', {}, h('p', {}, t('ui.projects.empty'))));
    } catch (e) {
      if (!alive || mine !== seq) return;
      count.textContent = '';
      replace(list, h('p.notice.notice-bad', { role: 'alert' }, '✗ ', describeError(e, t)));
    }
    list.setAttribute('aria-busy', 'false');
  }

  const node = h('section', {}, h('div.page-head', {}, h('h1', {}, t('ui.projects.title')), count), form, list);
  load();
  return { node, cleanup: () => { alive = false; } };
}

function card(p, remove) {
  const name = p.name || '?';
  const removeBtn = h('button.btn.btn-danger', { type: 'button', onclick: (ev) => remove(p, ev.currentTarget), aria: { label: t('ui.projects.remove.aria', { name }) } }, '✗ ', t('ui.projects.remove'));
  return h('div.card.project-card', {},
    h('h2', {}, h('a', { href: to.project(name) }, name)),
    h('span.path', { title: p.root || '' }, p.root || ''),
    h('div.row', {}, h('a.btn', { href: to.project(name) }, t('ui.projects.open')), removeBtn));
}
