/* Copiado de gimg@46248251 (D7); adaptado a gvoice: sin perfiles, la clave del pedido va sola.
   Rutas por #hash (sin servidor de rutas, D6).
   #/                              proyectos
   #/p/<proyecto>[/orders]         un proyecto
   #/p/<proyecto>/o/<clave codificada>   un pedido (la clave de una frase lleva «/»: va con encodeURIComponent)
   #/p/<proyecto>/o/<clave codificada>/ab?a=<id>&b=<id>   comparación A/B de dos tomas del pedido (F5.5)
   Opcional: ...?a=<id> enfoca esa toma al abrir el pedido; #/p/<proyecto>?type=voice|line&chosen=true|false filtra la lista. */

const listeners = new Set();

export function parse(hash = location.hash) {
  const raw = hash.replace(/^#/, '') || '/';
  const [pathPart, queryPart] = raw.split('?');
  const query = Object.fromEntries(new URLSearchParams(queryPart || ''));
  let seg;
  try { seg = pathPart.split('/').filter(Boolean).map(decodeURIComponent); } catch { return { name: 'notfound', query }; } // %E0%A4 mal formado
  if (seg.length === 0) return { name: 'projects', query };
  if (seg[0] === 'p' && seg[1]) {
    if (seg[2] === 'o' && seg[3] && seg[4] === 'ab' && seg.length === 5) return { name: 'compare', project: seg[1], key: seg[3], query };
    if (seg[2] === 'o' && seg[3]) return { name: 'order', project: seg[1], key: seg[3], query };
    if (seg[2] === undefined || seg[2] === 'orders') return { name: 'project', project: seg[1], tab: 'orders', query };
  }
  return { name: 'notfound', query };
}

const qs = (query) => new URLSearchParams(Object.entries(query).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString();

export const to = {
  projects: () => '#/',
  project: (p, tab = 'orders', query = {}) => {
    const q = qs(query);
    return `#/p/${encodeURIComponent(p)}/${tab}${q ? '?' + q : ''}`;
  },
  order: (p, key, attempt) => `#/p/${encodeURIComponent(p)}/o/${encodeURIComponent(key)}${attempt ? '?a=' + attempt : ''}`,
  compare: (p, key, a, b) => {
    const q = qs({ a, b });
    return `#/p/${encodeURIComponent(p)}/o/${encodeURIComponent(key)}/ab${q ? '?' + q : ''}`;
  },
};

export function navigate(hash) { if (location.hash !== hash) location.hash = hash; else emit(); }

/** Cambia el hash sin avisar a nadie (ni `hashchange` ni repintar): para los filtros, que la vista aplica ella misma. */
export function replaceHash(hash) { if (location.hash !== hash) history.replaceState(null, '', hash); }

export function onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); }

function emit() { const r = parse(); for (const fn of listeners) fn(r); }

export function start() { addEventListener('hashchange', emit); emit(); }
