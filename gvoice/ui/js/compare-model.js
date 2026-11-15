/* Nuevo en gvoice (no copiado de gimg) (F5.5): lógica pura de la comparación A/B, sin DOM, para probarla con node.
   Qué dos tomas se comparan y a qué punto de la otra toma se pasa al cambiar. */

import { hasAudio } from './take-model.js';

/** Las dos tomas a comparar → `{a, b}` (ids de tomas con audio y distintas) o `null` si el pedido tiene menos de dos
    con audio. `query` es la del hash (`a`, `b`, como texto): vale el id que sea de una toma con audio; `a` si no, la
    elegida (si tiene audio) o la primera con audio; `b`, si no vale (o es igual que `a`), la primera otra con audio. */
export function pickPair(order, query = {}) {
  const ids = ((order && order.attempts) || []).filter(hasAudio).map((x) => x.id).sort((x, y) => x - y);
  if (ids.length < 2) return null;
  const valid = (v) => (v === undefined || v === null || v === '' ? null : ids.includes(Number(v)) ? Number(v) : null);
  const q = query || {};
  let a = valid(q.a);
  if (a === null) a = order.chosen !== null && order.chosen !== undefined && ids.includes(order.chosen) ? order.chosen : ids[0];
  let b = valid(q.b);
  if (b === null || b === a) b = ids.find((id) => id !== a);
  return { a, b };
}

/** Posición en la otra toma al cambiar de lado: la misma (en segundos), recortada a [0, duración]. `atEnd` es verdadero
    cuando la otra es más corta y la posición queda al final (no hay nada que oír desde ahí). Sin duración conocida
    (`otherDurationSec` no es un número) no se recorta por arriba. */
export function switchPoint(posSec, otherDurationSec) {
  const pos = Number.isFinite(posSec) && posSec > 0 ? posSec : 0;
  if (!Number.isFinite(otherDurationSec) || otherDurationSec < 0) return { pos, atEnd: false };
  if (pos >= otherDurationSec) return { pos: otherDurationSec, atEnd: true };
  return { pos, atEnd: false };
}

export const otherSide = (side) => (side === 'a' ? 'b' : 'a');
