/* Nuevo en gvoice (no copiado de gimg) (F5.7): solo lógica pura, sin DOM, para probarla con node.
   La barra de cola: recuentos, partes de la pastilla, qué entradas se pueden cancelar, qué se ve en cada filtro y su
   orden, y el texto de error de una entrada fallida (`errorText` de GET /api/queue, o su clave traducida). */

export const FILTERS = ['all', 'pending', 'done', 'failed'];
export const PENDING = ['queued', 'running'];

/** Cuántas entradas hay en cada estado (los estados de `gvoice/queue.py`). */
export function counts(entries) {
  const c = { running: 0, queued: 0, done: 0, failed: 0, cancelled: 0 };
  for (const e of entries || []) if (e && e.state in c) c[e.state] += 1;
  return c;
}

/** Las partes de la pastilla: `{running, queued}`; ambas a 0 es «cola vacía». */
export function pillParts(entries) {
  const c = counts(entries);
  return { running: c.running, queued: c.queued, idle: c.running + c.queued === 0 };
}

/** Solo lo que espera o corre se cancela (`POST /api/queue/{id}/cancel`; el resto da 409). */
export function canCancel(entry) { return Boolean(entry) && PENDING.includes(entry.state); }

/** Las entradas que «Vaciar cola» cancela: las que esperan (de un proyecto, si se da); lo que corre no se toca. */
export function clearable(entries, project = null) {
  return (entries || []).filter((e) => e.state === 'queued' && (!project || e.project === project));
}

/** Las entradas de un filtro, con lo que corre primero, luego lo que espera por id y al final el resto, lo más nuevo antes. */
export function visible(entries, filter) {
  const rank = (e) => (e.state === 'running' ? 0 : e.state === 'queued' ? 1 : 2);
  const shown = (entries || []).filter((e) => filter === 'all' || (filter === 'pending' ? PENDING.includes(e.state) : e.state === filter));
  return shown.slice().sort((a, b) => rank(a) - rank(b) || (rank(a) === 2 ? b.id - a.id : a.id - b.id));
}

/** El texto de error de una entrada fallida: su `errorText` ya traducido; si no, `error.<código>` con `lookup(clave, params)`
    (que devuelve null si no hay clave); si tampoco, `ui.error.code` con el código (o el código solo si ni esa clave
    está cargada); sin código, null. */
export function errorOf(entry, lookup = () => null) {
  if (!entry || entry.state !== 'failed') return null;
  if (entry.errorText) return entry.errorText;
  if (entry.error && entry.error.code) return lookup(`error.${entry.error.code}`, entry.error.params || {}) ||
    lookup('ui.error.code', { code: entry.error.code }) || entry.error.code;   // no text for the code: show the code
  return null;
}
