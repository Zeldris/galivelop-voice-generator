/* Copiado de gimg@46248251 (D7); escrito de nuevo para gvoice (F5.2): solo lógica pura, sin DOM, para probarla con node.
   Filtros de la lista de pedidos (de y hacia la URL), resumen de una fila y el pedido que se envía desde «Nuevo pedido»
   (validado como `gvoice/schemas/order.schema.json` y `common.schema.json`). */

export const TYPES = ['voice', 'line'];
export const CHOSEN = ['true', 'false'];
export const MAX_COUNT = 50;       // orders.py: count 1..50
export const MAX_SEED = 4294967295;
export const MAX_KEY = 100;
export const MAX_TEST_TEXT = 1000;
export const MAX_LINE_TEXT = 4000;
export const KEY_PATTERN = /^[a-z0-9][a-z0-9-]*(\/[a-z0-9][a-z0-9-]*)*$/;
export const SEGMENT_PATTERN = /^[a-z0-9][a-z0-9-]*$/;
/** Los campos de la ficha de diseño, en el orden de design-sheet.schema.json (el orden del instruct). */
export const SHEET_FIELDS = ['gender', 'age', 'pitch', 'speed', 'volume', 'clarity', 'fluency', 'accent', 'texture', 'emotion', 'tone', 'personality'];

/* ---- filtros ---- */

/** {type, chosen} desde la query de la ruta (`route.query`); un valor que no es de la lista cuenta como «todos» (''). */
export function filtersFromQuery(query = {}) {
  return {
    type: TYPES.includes(query.type) ? query.type : '',
    chosen: CHOSEN.includes(query.chosen) ? query.chosen : '',
  };
}

/** La query de los filtros, sin los vacíos: es la de la URL y la de GET …/orders. */
export function filtersToQuery(filters = {}) {
  const q = {};
  if (TYPES.includes(filters.type)) q.type = filters.type;
  if (CHOSEN.includes(filters.chosen)) q.chosen = filters.chosen;
  return q;
}

/* ---- fila de la lista ---- */

/** Lo que muestra una fila: clave, tipo, voz (solo `line`), texto de prueba o texto, nº de tomas y toma elegida. */
export function orderSummary(o) {
  const takes = Array.isArray(o.attempts) ? o.attempts.length : (Number.isFinite(o.attempts) ? o.attempts : (o.attemptCount || 0));
  const chosen = o.chosen !== null && o.chosen !== undefined;
  return {
    key: o.key,
    type: o.type,
    voice: o.type === 'line' ? (o.voice || '') : '',
    text: (o.type === 'line' ? o.text : o.testText) || '',
    takes,
    chosen,
    chosenId: chosen ? o.chosen : null,
  };
}

/* ---- «Nuevo pedido» ---- */

function intField(raw) {
  const s = String(raw ?? '').trim();
  return /^\d+$/.test(s) ? Number(s) : null;
}

/** «nombre: texto» por línea → {nombre: texto}. Devuelve {extra, bad}: `bad` es la primera línea mal escrita o null. */
export function parseExtra(raw) {
  const extra = {};
  for (const line of String(raw ?? '').split('\n')) {
    if (!line.trim()) continue;
    const at = line.indexOf(':');
    const name = at < 0 ? '' : line.slice(0, at).trim();
    const value = at < 0 ? '' : line.slice(at + 1).trim();
    if (!name || !value) return { extra: {}, bad: line.trim() };
    extra[name] = value;
  }
  return { extra, bad: null };
}

/** Clave de una frase: `<voz>/<id>`. */
export const lineKey = (voice, id) => `${String(voice || '').trim()}/${String(id || '').trim()}`;

/**
 * Construye el cuerpo de POST …/orders a partir de los campos del formulario (todo texto, como salen de los inputs):
 *   voice: {type, key, testText, sheet: {gender…personality}, extra, seed, count}
 *   line:  {type, voice, lineId, text, seed, count}
 * Devuelve {body, errors}: `body` es {order, count} (null si hay errores) y cada error {field, code, params?}, con los
 * códigos `required`, `pattern`, `too_long`, `seed`, `count` y `extra`; la interfaz los traduce.
 */
export function buildOrder(f) {
  const errors = [];
  const bad = (field, code, params) => errors.push(params ? { field, code, params } : { field, code });
  const order = {};
  const type = f.type;
  if (!TYPES.includes(type)) { bad('type', 'required'); return { body: null, errors }; }
  order.type = type;

  if (type === 'voice') {
    const key = String(f.key ?? '').trim();
    if (!key) bad('key', 'required');
    else if (!KEY_PATTERN.test(key)) bad('key', 'pattern');
    else if (key.length > MAX_KEY) bad('key', 'too_long', { max: MAX_KEY });
    order.key = key;
    const testText = String(f.testText ?? '').trim();
    if (!testText) bad('testText', 'required');
    else if (testText.length > MAX_TEST_TEXT) bad('testText', 'too_long', { max: MAX_TEST_TEXT });
    order.testText = testText;
    const sheet = {};
    for (const name of SHEET_FIELDS) {
      const v = String((f.sheet || {})[name] ?? '').trim();
      if (v) sheet[name] = v;
    }
    const { extra, bad: badLine } = parseExtra(f.extra);
    if (badLine !== null) bad('extra', 'extra', { line: badLine });
    else if (Object.keys(extra).length) sheet.extra = extra;
    order.designSheet = sheet;
  } else {
    const voice = String(f.voice ?? '').trim();
    const id = String(f.lineId ?? '').trim();
    if (!voice) bad('voice', 'required');
    else if (!SEGMENT_PATTERN.test(voice)) bad('voice', 'pattern');
    if (!id) bad('lineId', 'required');
    else if (!SEGMENT_PATTERN.test(id)) bad('lineId', 'pattern');
    order.voice = voice;
    order.key = lineKey(voice, id);
    if (!errors.some((e) => e.field === 'voice' || e.field === 'lineId') && order.key.length > MAX_KEY) bad('lineId', 'too_long', { max: MAX_KEY });
    const text = String(f.text ?? '').trim();
    if (!text) bad('text', 'required');
    else if (text.length > MAX_LINE_TEXT) bad('text', 'too_long', { max: MAX_LINE_TEXT });
    order.text = text;
  }

  const seedRaw = String(f.seed ?? '').trim();
  if (seedRaw !== '') {
    const seed = intField(seedRaw);
    if (seed === null || seed > MAX_SEED) bad('seed', 'seed', { max: MAX_SEED });
    else order.seed = seed;
  }
  const countRaw = String(f.count ?? '').trim();
  const count = countRaw === '' ? 1 : intField(countRaw);
  if (count === null || count < 1 || count > MAX_COUNT) bad('count', 'count', { max: MAX_COUNT });

  if (errors.length) return { body: null, errors };
  return { body: { order, count }, errors };
}
