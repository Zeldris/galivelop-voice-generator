/* Nuevo en gvoice (no copiado de gimg) (F5.4): lógica pura de la galería de tomas, sin DOM, para probarla con node.
   Estado de una toma, huellas por modelo, a qué toma vuelve «Deshacer» y cálculos de la forma de onda. */

import { isSampleOrder } from './order-model.js';

export const STATES = ['new', 'candidate', 'discarded'];

/** `chosen` si la toma es la elegida del pedido; si no, su propio estado (`new`, `candidate`, `discarded`). */
export function takeState(order, take) {
  if (order && order.chosen === take.id) return 'chosen';
  return STATES.includes(take.state) ? take.state : 'new';
}

/** La toma de una muestra (`source: "sample"`): ni semilla ni instrucción; su origen y licencia son los del pedido. */
export const isSampleTake = (take) => !!take && take.source === 'sample';

/** Por qué no se piden más tomas (`'sample'`: la voz sale de una muestra y no hace tomas de diseño) o null si se puede. */
export function noMoreTakesReason(order) {
  return isSampleOrder(order) ? 'sample' : null;
}

/** Una toma tiene audio cuando el motor ya midió su duración (`audioMs`); sin él no se puede ni oír ni elegir. */
export function hasAudio(take) { return typeof take.audioMs === 'number' && take.audioMs > 0; }

/** ¿Se puede elegir? No la descartada ni la que no tiene audio (el servidor lo vuelve a comprobar con un 409). */
export function canChoose(order, take) {
  const s = takeState(order, take);
  return s !== 'chosen' && s !== 'discarded' && hasAudio(take);
}

/** Lo que hace «Deshacer»: la toma a la que vuelve la elección (`null` = sin elegida) o `undefined` si no hay historia. */
export function undoTarget(order) {
  const h = order && Array.isArray(order.chosenHistory) ? order.chosenHistory : [];
  return h.length ? h[h.length - 1] : undefined;
}

/** Las entradas de la cola abiertas (en cola o en marcha) de este pedido. */
export function openEntries(queue, project, key) {
  return (Array.isArray(queue) ? queue : []).filter((e) => e.project === project && e.key === key && (e.state === 'queued' || e.state === 'running'));
}

/** Huellas de una toma `voice`: una por modelo base del proyecto → [{model, status}] con status `done`, `running`,
    `queued` o `pending` (pendiente: ni hecha ni en cola; se encola al elegir la toma). */
export function printStates(take, models, entries) {
  const prints = take.prints || {};
  const mine = (entries || []).filter((e) => e.kind === 'prints' && e.take === take.id);
  return (models || []).map((model) => {
    if (prints[model]) return { model, status: 'done' };
    const e = mine[0];
    return { model, status: e ? (e.state === 'running' ? 'running' : 'queued') : 'pending' };
  });
}

/** Tomas pedidas (de tipo voice o line, aún sin su toma) de este pedido que siguen en la cola. */
export function pendingTakes(entries) { return (entries || []).filter((e) => e.kind !== 'prints').length; }

/** Cuántos picos pedir para un ancho en píxeles: una barra de 3 px más 1 de hueco (16..2000, como `gvoice/peaks.py`). */
export function bucketsFor(width) {
  const n = Math.floor((Number(width) || 0) / 4);
  return Math.max(16, Math.min(2000, n || 120));
}

/** Vuelve a muestrear `peaks` a `n` barras tomando el máximo de cada tramo (para redibujar sin volver a pedirlos). */
export function resample(peaks, n) {
  if (!peaks.length || n <= 0) return [];
  if (peaks.length === n) return peaks.slice();
  const out = [];
  for (let i = 0; i < n; i++) {
    const a = Math.floor(i * peaks.length / n);
    const b = Math.max(a + 1, Math.floor((i + 1) * peaks.length / n));
    let max = 0;
    for (let j = a; j < b && j < peaks.length; j++) max = Math.max(max, peaks[j]);
    out.push(max);
  }
  return out;
}

/** Rectángulos de las barras, centrados en vertical: una barra de `bar` px cada `step`; un pico 0 deja una raya de 1 px. */
export function barRects(peaks, width, height, { bar = 3, step = 4 } = {}) {
  const n = Math.min(peaks.length, Math.max(1, Math.floor(width / step)));
  const bars = resample(peaks, n);
  return bars.map((p, i) => {
    const h = Math.max(1, Math.round(Math.min(1, Math.max(0, p)) * height));
    return { x: i * step, y: Math.round((height - h) / 2), w: bar, h };
  });
}

/** Posición 0..1 de un clic (`x` en pantalla) sobre una caja `{left, width}`. */
export function fractionAt(x, rect) {
  if (!rect || !(rect.width > 0)) return 0;
  return Math.max(0, Math.min(1, (x - rect.left) / rect.width));
}
