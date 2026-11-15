/* Copiado de gimg@46248251 (D7); adaptado a gvoice: sin perfiles, la clave del pedido va sola.
   Rutas por #hash (sin servidor de rutas, D6).
   #/                              proyectos
   #/p/<proyecto>[/pedidos]        un proyecto
   #/p/<proyecto>/o/<clave codificada>   un pedido (la clave de una frase lleva «/»: va con encodeURIComponent)
   Opcional: ...?a=<id> enfoca esa toma al abrir el pedido. */

const listeners = new Set();

export function parse(hash = location.hash) {
  const raw = hash.replace(/^#/, '') || '/';
  const [pathPart, queryPart] = raw.split('?');
  const query = Object.fromEntries(new URLSearchParams(queryPart || ''));
  const seg = pathPart.split('/').filter(Boolean).map(decodeURIComponent);
  if (seg.length === 0) return { name: 'projects', query };
  if (seg[0] === 'p' && seg[1]) {
    if (seg[2] === 'o' && seg[3]) return { name: 'order', project: seg[1], key: seg[3], query };
    const tab = ['pedidos'].includes(seg[2]) ? seg[2] : 'pedidos';
    return { name: 'project', project: seg[1], tab, query };
  }
  return { name: 'notfound', query };
}

export const to = {
  projects: () => '#/',
  project: (p, tab = 'pedidos') => `#/p/${encodeURIComponent(p)}/${tab}`,
  order: (p, key, attempt) => `#/p/${encodeURIComponent(p)}/o/${encodeURIComponent(key)}${attempt ? '?a=' + attempt : ''}`,
};

export function navigate(hash) { if (location.hash !== hash) location.hash = hash; else emit(); }

export function onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); }

function emit() { const r = parse(); for (const fn of listeners) fn(r); }

export function start() { addEventListener('hashchange', emit); emit(); }
