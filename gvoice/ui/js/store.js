/* Copiado de gimg@46248251 (D7); adaptado a gvoice.
   Estado compartido mínimo: la cola (la sondea queue-poll.js) y comodidades del navegador (filtros).
   Lo que importa (estados de las tomas, notas, elegida, textos) vive en la API, no aquí. */

const state = {
  queue: [],            // entradas de GET /api/queue, tal cual
  queueAt: null,        // Date.now() del último sondeo bueno
  filters: {},          // por proyecto: {type, chosen}
};
const subs = new Map();

export function get(key) { return state[key]; }

export function set(key, value) {
  state[key] = value;
  for (const fn of subs.get(key) || []) fn(value);
}

export function subscribe(key, fn) {
  if (!subs.has(key)) subs.set(key, new Set());
  subs.get(key).add(fn);
  return () => subs.get(key).delete(fn);
}

/** Entradas de la cola de un pedido concreto. */
export function queueOf(project, key) {
  return state.queue.filter((e) => e.project === project && e.key === key);
}
