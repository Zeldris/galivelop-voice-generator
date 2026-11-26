/* Copiado de gimg@46248251 (D7); reescrito para el dominio de voces.
   Servidor fingido para el prototipo (solo con `?mock=1`): mismo contrato que `gvoice/api_contract.py`
   (docs/api.md), en memoria y con datos pequeños coherentes con examples/ (proyecto `example-world`, voces `narrator`
   y `orc`, frases de `narrator`). Las tomas suenan: el audio es un WAV generado aquí (un tono con envolvente) y los picos
   de la forma de onda salen de esas mismas muestras. La cola avanza sola (una entrada tarda ~6 s).
   Los textos y los mensajes de error salen de /api/locales/<lang> (lo sirve `python3 -m gvoice ui`).
   No se carga en producción: app.js solo lo importa si la URL lleva `?mock=1`.
   Cada `route(...)` es una ruta de `gvoice/api_contract.ROUTES`; tests/test_ui.py comprueba que son las mismas. */

const now = () => new Date().toISOString();
const ago = (s) => new Date(Date.now() - s * 1000).toISOString();
const PROJECT = 'example-world';
const PRINT_MODELS = ['0.6b-base', '1.7b-base'];
const TAKE_MS = 6000;
const LOCALES = ['es-ES', 'es-419', 'en-US', 'en-GB'];

const projects = {
  [PROJECT]: {
    name: PROJECT, root: '/home/deck/Desarrollos/example-world',
    config: {
      minVersion: '0.1.0', name: PROJECT,
      voices: { narrator: { description: 'Main narrator' }, orc: { description: 'Orc warchief', effects: 'orc' } },
      printModels: PRINT_MODELS, delivery: { dir: 'uploads/voices' },
    },
  },
  tavern: { name: 'tavern', root: '/home/deck/Desarrollos/tavern', config: { minVersion: '0.1.0', name: 'tavern', voices: {}, printModels: ['0.6b-base'], delivery: { dir: 'voices' } } },
};

const NARRATOR_SHEET = { gender: 'male', age: 'middle-aged adult', pitch: 'low', speed: 'slow', volume: 'moderate', clarity: 'clear',
  fluency: 'measured, deliberate pauses', accent: 'neutral', texture: 'dry, slightly rough', emotion: 'calm', tone: 'authoritative',
  personality: 'precise and formal', extra: { breathing: 'audible between sentences' } };
const ORC_SHEET = { gender: 'male', age: 'young', pitch: 'very low', texture: 'bright, gravelly', tone: 'menacing' };
const SHEET_ORDER = ['gender', 'age', 'pitch', 'speed', 'volume', 'clarity', 'fluency', 'accent', 'texture', 'emotion', 'tone', 'personality'];
export const BANNED = ['bright', 'cute', 'small', 'light', 'childlike', 'high-pitched'];
export const SUGGESTIONS = 'airy, breathy, soft-spoken, whispering';

function instructionOf(sheet) {
  const pairs = [...SHEET_ORDER.filter((k) => k in sheet).map((k) => [k, sheet[k]]), ...Object.entries(sheet.extra || {})];
  return pairs.map(([k, v]) => `${k[0].toUpperCase()}${k.slice(1)}: ${String(v).trim().replace(/\.$/, '')}.`).join(' ');
}

/* Como `gvoice/sheet.py` (`is_adult`, mismas reglas; lo comprueba tests/test_ui_js.py sobre un juego de fichas). */
const CHILD = /^(child\w*|kids?|teen\w*|boys?|girls?|youth\w*|juveniles?|minors?|underage|babys?|babies|infants?|toddlers?|adolescent\w*|tweens?|preteens?)$/;
const ADULT = /^(adults?|middle|aged|elderly|old|older|senior|mature|men|man|women|woman|(twen|thir|for|fif|six|seven|eight|nine)ties|[2-9]0s|(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)\w*)$/;
function isAdult(age) {
  if (typeof age !== 'string') return false;
  const words = age.toLowerCase().match(/[a-z0-9]+/g) || [];
  const numbers = words.filter((w) => /^\d+$/.test(w)).map(Number);
  if (numbers.some((n) => n < 18)) return false;
  for (let i = 0; i < words.length; i++) {
    if (CHILD.test(words[i])) return false;
    if (words[i] === 'young' && words[i + 1] !== 'adult') return false;
  }
  return words.some((w) => ADULT.test(w)) || numbers.some((n) => n >= 18);
}

export function warningsOf(sheet) {
  const out = [];
  const age = String(sheet.age || '').toLowerCase();
  if (!age.trim()) out.push({ code: 'sheet.age_missing', params: {} });
  else if (!isAdult(sheet.age)) {
    out.push({ code: 'sheet.age_not_adult', params: { age: sheet.age } });
  }
  const fields = [...SHEET_ORDER.filter((k) => k in sheet).map((k) => [k, sheet[k]]), ...Object.entries(sheet.extra || {})];
  for (const [field, value] of fields) {
    for (const word of BANNED) {
      if (new RegExp(`(^|[^a-z0-9])${word.replace('-', '[\\s-]+')}($|[^a-z0-9])`).test(String(value).toLowerCase())) {
        out.push({ code: 'sheet.banned_word', params: { word, field, suggestions: SUGGESTIONS } });
      }
    }
  }
  return out;
}

let nextEntry = 3;
const take = (id, seed, text, extra = {}) => ({
  id, state: 'new', seed, text, dir: `attempts/${id}`, audio: `attempts/${id}/audio.wav`, note: '', createdAt: ago(7200 - id * 600),
  device: 'Vulkan0', engineVersion: '0.1.0', engineCommit: '5916bf7', model: '1.7b-voicedesign', durationMs: 5200 + id * 300, audioMs: 2600 + id * 450, loadMs: 900, ...extra,
});
const printed = (models) => Object.fromEntries(models.map((m) => [m, { madeAt: ago(3000), device: 'Vulkan0', durationMs: 1800 }]));
const orders = {
  [PROJECT]: [
    { key: 'narrator', type: 'voice', seed: 1234, testText: 'The law of the obelisks admits no exceptions.', designSheet: NARRATOR_SHEET,
      attempts: [
        take(1, 1234, 'The law of the obelisks admits no exceptions.', { state: 'discarded', note: 'demasiado agudo', instruction: instructionOf(NARRATOR_SHEET), prints: {} }),
        take(2, 1235, 'The law of the obelisks admits no exceptions.', { state: 'candidate', note: 'la mejor', instruction: instructionOf(NARRATOR_SHEET), prints: printed(PRINT_MODELS) }),
        take(3, 1236, 'The law of the obelisks admits no exceptions.', { instruction: instructionOf(NARRATOR_SHEET), prints: {} }),
      ],
      chosen: 2, chosenHistory: [null], createdAt: ago(9000), updatedAt: ago(1200) },
    { key: 'orc', type: 'voice', seed: null, testText: 'Blood for the war chief.', designSheet: ORC_SHEET,
      attempts: [take(1, 77, 'Blood for the war chief.', { instruction: instructionOf(ORC_SHEET), prints: {} })],
      chosen: null, chosenHistory: [], createdAt: ago(3000), updatedAt: ago(3000) },
    { key: 'narrator/intro-01', type: 'line', voice: 'narrator', text: 'Long ago, the valley was silent.', seed: 7,
      attempts: [take(1, 7, 'Long ago, the valley was silent.', { state: 'candidate', voice: 'narrator', reference: 2 })],
      chosen: 1, chosenHistory: [null], createdAt: ago(2400), updatedAt: ago(2000) },
    { key: 'narrator/intro-02', type: 'line', voice: 'narrator', text: 'Then the obelisks rose.', seed: null,
      attempts: [take(1, 8, 'Then the obelisks rose.', { voice: 'narrator', reference: 1 })],
      chosen: 1, chosenHistory: [null], createdAt: ago(2300), updatedAt: ago(1900) },
  ],
  tavern: [],
};

const queue = [
  { id: 1, kind: 'line', project: PROJECT, key: 'narrator/intro-02', seed: 9, text: 'Then the obelisks rose.', voice: 'narrator', reference: 2, state: 'running', pid: 4242, enqueuedAt: ago(20), startedAt: ago(3), finishedAt: null, error: null, attemptId: null, cancelRequested: false },
  { id: 2, kind: 'voice', project: PROJECT, key: 'orc', seed: 78, text: 'Blood for the war chief.', instruction: instructionOf(ORC_SHEET), state: 'queued', pid: null, enqueuedAt: ago(15), startedAt: null, finishedAt: null, error: null, attemptId: null, cancelRequested: false },
  { id: 0, kind: 'line', project: PROJECT, key: 'narrator/intro-01', seed: 6, text: 'Long ago, the valley was silent.', state: 'failed', pid: null, enqueuedAt: ago(900), startedAt: ago(890), finishedAt: ago(880), error: { code: 'engine.failed', params: { message: 'out of memory' } }, attemptId: null, cancelRequested: false },
];

/* la cola avanza sola: la que corre termina a los TAKE_MS y empieza la siguiente */
setInterval(() => {
  const running = queue.find((e) => e.state === 'running');
  if (running && running.cancelRequested) { // como el trabajador real: cancelada sin crear toma
    running.state = 'cancelled'; running.pid = null; running.finishedAt = now();
  } else if (running && Date.now() - Date.parse(running.startedAt) >= TAKE_MS) finishEntry(running);
  else if (!running) {
    const next = queue.filter((e) => e.state === 'queued').sort((a, b) => a.id - b.id)[0];
    if (next) { next.state = 'running'; next.startedAt = now(); }
  }
}, 1000);

function finishEntry(entry) {
  entry.state = 'done'; entry.finishedAt = now();
  const order = findOrder(entry.project, entry.key);
  if (!order) return;
  if (entry.kind === 'prints') {
    const item = order.attempts.find((a) => a.id === entry.take);
    if (item) item.prints = printed(PRINT_MODELS);
    entry.attemptId = entry.take;
    return;
  }
  const id = Math.max(0, ...order.attempts.map((a) => a.id)) + 1;
  const extra = entry.kind === 'voice' ? { instruction: entry.instruction, prints: {} } : { voice: entry.voice, reference: entry.reference };
  order.attempts.push(take(id, entry.seed, entry.text, { ...extra, createdAt: now() }));
  order.updatedAt = now();
  entry.attemptId = id;
}

function findOrder(p, key) { return (orders[p] || []).find((o) => o.key === key); }
function referenceOf(p, voice) { const o = findOrder(p, voice); return o && o.type === 'voice' ? o.chosen : null; }
function isStale(p, order) {
  if (order.chosen === null) return false;
  const a = order.attempts.find((x) => x.id === order.chosen);
  return (a.voice || order.voice) !== order.voice || a.reference !== referenceOf(p, order.voice);
}
function staleLines(p, voice) { return orders[p].filter((o) => o.type === 'line' && o.voice === voice && isStale(p, o)).map((o) => o.key).sort(); }
function view(p, order) {
  const copy = JSON.parse(JSON.stringify(order));
  if (order.type === 'line') copy.stale = isStale(p, order); else copy.staleLines = staleLines(p, order.key);
  return copy;
}

/* ---- audio: un WAV de 16 bits a 24 kHz con un tono por toma; los picos salen de las mismas muestras ---- */
const RATE = 24000;
const samplesCache = new Map();
function samplesOf(p, key, a) {
  const id = `${p}/${key}/${a.id}`;
  if (!samplesCache.has(id)) {
    const n = Math.round(RATE * (a.audioMs || 2000) / 1000);
    const hz = 110 + ((a.seed || 0) % 7) * 18 + (key.startsWith('orc') ? -40 : 0);
    const out = new Int16Array(n);
    for (let i = 0; i < n; i++) {
      const t = i / RATE;
      const env = Math.min(1, i / 1200, (n - i) / 2400) * (0.55 + 0.45 * Math.abs(Math.sin(t * 5.2)));
      out[i] = Math.round(Math.sin(2 * Math.PI * hz * t) * 9000 * env);
    }
    samplesCache.set(id, out);
  }
  return samplesCache.get(id);
}
function wavOf(samples) {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, 'RIFF'); v.setUint32(4, 36 + samples.length * 2, true); str(8, 'WAVE'); str(12, 'fmt ');
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, RATE, true);
  v.setUint32(28, RATE * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); str(36, 'data'); v.setUint32(40, samples.length * 2, true);
  new Int16Array(buf, 44).set(samples);
  return new Blob([buf], { type: 'audio/wav' });
}
/* Same rules as gvoice/peaks.py (a test keeps them equal): bucket i spans floor(i*L/n)..floor((i+1)*L/n), an empty
   bucket is 0, and the peak is max/32768 rounded half-up to 3 decimals, in integers. */
export function peaksOf(samples, n) {
  const L = samples.length;
  const out = [];
  for (let i = 0; i < n; i++) {
    let max = 0;
    for (let j = Math.floor(i * L / n); j < Math.floor((i + 1) * L / n); j++) max = Math.max(max, Math.abs(samples[j]));
    out.push(Math.min(1000, Math.floor((2000 * max + 32768) / 65536)) / 1000);
  }
  return out;
}

/* ---- textos y errores: el diccionario del servidor, con los huecos {nombre} ---- */
const locales = {};
async function loadLocale(lang) {
  if (!locales[lang]) { try { locales[lang] = await (await fetch(`/api/locales/${lang}`)).json(); } catch { locales[lang] = {}; } }
  return locales[lang];
}
const fill = (s, params) => s.replace(/\{(\w+)\}/g, (m, k) => (k in params ? String(params[k]) : m));
async function text(lang, key, params = {}) { const d = await loadLocale(lang); return fill(d[key] || key, params); }
async function fail(lang, status, code, params = {}) {
  const shown = code === 'order.origin_changed'   // was/new son códigos de origen: se muestran en el idioma
    ? { ...params, was: await text(lang, 'order.origin.' + params.was), new: await text(lang, 'order.origin.' + params.new) } : params;
  return { status, json: { error: { code, params, message: await text(lang, 'error.' + code, shown) } } };
}
const ok = (json, status = 200) => ({ status, json });
const warnView = async (lang, list) => Promise.all(list.map(async (w) => ({ ...w, message: await text(lang, 'warning.' + w.code, w.params) })));

/* ---- las rutas: las de gvoice/api_contract.py, con la misma forma de patrón ---- */
const routes = [];
function route(method, pattern, handler) { routes.push({ method, parts: pattern.split('/').filter(Boolean), handler }); }

route('GET', '/api/health', () => ok({ ok: true, version: '0.0.0-mock', worker: true,
  queue: { running: queue.filter((e) => e.state === 'running').length, queued: queue.filter((e) => e.state === 'queued').length } }));
route('GET', '/api/locales/{lang}', async (c) => ok(await loadLocale(c.params.lang)));

route('GET', '/api/projects', () => ok(Object.values(projects).map((p) => ({ name: p.name, root: p.root }))));
route('POST', '/api/projects', async (c) => {
  const path = c.body && c.body.path;
  if (typeof path !== 'string' || !path.trim()) return fail(c.lang, 400, 'api.bad_param', { name: 'path' });
  const name = path.replace(/\/+$/, '').split('/').pop();
  if (!projects[name]) { projects[name] = { name, root: path, config: { minVersion: '0.1.0', name, voices: {}, printModels: ['0.6b-base'], delivery: { dir: 'voices' } } }; orders[name] = []; }
  return ok({ name });
});
route('GET', '/api/projects/{p}', (c) => (projects[c.params.p] ? ok(projects[c.params.p]) : fail(c.lang, 404, 'project.unknown', { name: c.params.p })));
route('POST', '/api/projects/{p}/remove', (c) => {
  if (!projects[c.params.p]) return fail(c.lang, 404, 'project.unknown', { name: c.params.p });
  delete projects[c.params.p]; delete orders[c.params.p];
  return ok({ removed: c.params.p });
});

route('GET', '/api/projects/{p}/orders', (c) => {
  if (!projects[c.params.p]) return fail(c.lang, 404, 'project.unknown', { name: c.params.p });
  const type = c.query.get('type'); const chosen = c.query.get('chosen');
  if (type !== null && !['voice', 'line'].includes(type)) return fail(c.lang, 400, 'api.bad_param', { name: 'type' });
  if (chosen !== null && !['true', 'false'].includes(chosen)) return fail(c.lang, 400, 'api.bad_param', { name: 'chosen' });
  return ok(orders[c.params.p].filter((o) => (type === null || o.type === type) && (chosen === null || (o.chosen !== null) === (chosen === 'true')))
    .sort((a, b) => (a.key < b.key ? -1 : 1)).map((o) => view(c.params.p, o)));
});
route('POST', '/api/projects/{p}/orders', async (c) => {
  const p = c.params.p;
  if (!projects[p]) return fail(c.lang, 404, 'project.unknown', { name: p });
  const spec = c.body && c.body.order; const count = (c.body && c.body.count) ?? 1;
  if (!spec || typeof spec.key !== 'string' || !['voice', 'line'].includes(spec.type)) return fail(c.lang, 400, 'api.bad_param', { name: 'order' });
  if (!Number.isInteger(count) || count < 1 || count > 50) return fail(c.lang, 400, 'api.bad_param', { name: 'count' });
  let record = findOrder(p, spec.key);
  if (record && record.type !== spec.type) return fail(c.lang, 409, 'order.type_changed', { order: spec.key, type: record.type, new: spec.type });
  if (spec.type === 'line') {
    const voice = findOrder(p, spec.voice);
    if (!voice || voice.type !== 'voice') return fail(c.lang, 404, 'order.voice_unknown', { project: p, voice: spec.voice });
    if (voice.chosen === null) return fail(c.lang, 409, 'order.voice_not_fixed', { voice: spec.voice });
  }
  const sample = spec.type === 'voice' && spec.sample;
  if (sample) {   // como orders.submit: locale obligatoria, sin ficha ni semilla ni frase de prueba
    if (spec.designSheet || spec.testText !== undefined || spec.seed !== undefined || spec.sampling !== undefined || !LOCALES.includes(spec.locale)) return fail(c.lang, 400, 'api.bad_param', { name: 'order' });
    for (const f of ['audio', 'text', 'source', 'license']) if (typeof sample[f] !== 'string' || !sample[f].trim()) return fail(c.lang, 400, 'api.bad_param', { name: 'order' });
    if (record && !record.sample) return fail(c.lang, 409, 'order.origin_changed', { order: spec.key, was: 'sheet', new: 'sample' });
    // el audio del simulador es siempre el mismo: como orders.submit, otra transcripción o variante exige otro audio
    if (record && record.attempts.some((a) => a.source === 'sample' && (a.text !== sample.text.trim() || a.locale !== spec.locale))) return fail(c.lang, 409, 'order.sample_changed', { order: spec.key });
  } else if (record && record.sample) return fail(c.lang, 409, 'order.origin_changed', { order: spec.key, was: 'sample', new: 'sheet' });
  if (!record) {
    record = { key: spec.key, type: spec.type, attempts: [], chosen: null, chosenHistory: [], createdAt: now() };
    orders[p].push(record);
  }
  if (sample) {   // la muestra entra como toma 1 (source sample: sin semilla ni instrucción) con un audio del simulador
    record.locale = spec.locale; record.seed = null; record.updatedAt = now();
    record.sample = { source: sample.source.trim(), license: sample.license.trim(), text: sample.text.trim(), sha256: 'mock'.padEnd(64, '0') };
    if (!record.attempts.some((a) => a.source === 'sample')) {
      record.attempts.push(take(Math.max(0, ...record.attempts.map((a) => a.id)) + 1, null, record.sample.text,
        { source: 'sample', locale: spec.locale, sha256: record.sample.sha256, prints: {}, audioMs: 4800, durationMs: undefined, model: undefined, device: undefined }));
    }
    return ok({ order: { ...view(p, record), warnings: [] }, entries: [], warnings: [] });
  }
  Object.assign(record, spec.type === 'voice' ? { testText: spec.testText, designSheet: spec.designSheet } : { voice: spec.voice, text: spec.text }, { seed: spec.seed ?? null, updatedAt: now() });
  const entries = [];
  for (let i = 0; i < count; i++) entries.push(enqueueTake(p, record, record.seed === null ? null : record.seed + i));
  const warnings = record.type === 'voice' ? await warnView(c.lang, warningsOf(record.designSheet)) : [];
  return ok({ order: { ...view(p, record), warnings }, entries: entries.map((e) => ({ ...e })), warnings });
});
route('GET', '/api/projects/{p}/orders/{key}', (c) => {
  const o = lookup(c);
  return o.error || ok(view(c.params.p, o));
});
route('GET', '/api/projects/{p}/orders/{key}/sheet', async (c) => {
  const o = lookup(c);
  if (o.error) return o.error;
  if (o.type !== 'voice' || o.sample) return fail(c.lang, 409, 'order.wrong_type', { order: o.key, expected: 'voice' });
  return ok({ instruction: instructionOf(o.designSheet), warnings: await warnView(c.lang, warningsOf(o.designSheet)) });
});
route('POST', '/api/sheet/check', async (c) => {
  const sheet = c.body && c.body.designSheet;
  if (!sheet || typeof sheet !== 'object') return fail(c.lang, 400, 'api.bad_param', { name: 'designSheet' });
  return ok({ instruction: instructionOf(sheet), warnings: await warnView(c.lang, warningsOf(sheet)) });
});

function enqueueTake(p, order, seed) {
  const s = seed ?? Math.floor(Math.random() * 1e6);
  const entry = { id: nextEntry++, kind: order.type, project: p, key: order.key, seed: s, state: 'queued', pid: null, enqueuedAt: now(), startedAt: null, finishedAt: null, error: null, attemptId: null, cancelRequested: false };
  if (order.type === 'voice') Object.assign(entry, { text: order.testText, instruction: instructionOf(order.designSheet) });
  else Object.assign(entry, { text: order.text, voice: order.voice, reference: referenceOf(p, order.voice) });
  queue.push(entry);
  return entry;
}
function lookup(c) {
  if (!projects[c.params.p]) return { error: fail(c.lang, 404, 'project.unknown', { name: c.params.p }) };
  const o = findOrder(c.params.p, c.params.key);
  return o || { error: fail(c.lang, 404, 'order.unknown', { project: c.params.p, order: c.params.key }) };
}
function lookupTake(c) {
  const o = lookup(c);
  if (o.error) return o;
  const a = o.attempts.find((x) => x.id === Number(c.params.id));
  return a ? { order: o, take: a } : { error: fail(c.lang, 404, 'order.attempt_unknown', { attempt: c.params.id, order: o.key }) };
}

route('POST', '/api/projects/{p}/orders/{key}/attempts', (c) => {
  const o = lookup(c);
  if (o.error) return o.error;
  const count = (c.body && c.body.count) ?? 1;
  if (!Number.isInteger(count) || count < 1 || count > 50) return fail(c.lang, 400, 'api.bad_param', { name: 'count' });
  if (o.sample) return fail(c.lang, 409, 'order.sample_no_takes', { order: o.key });
  const seed = c.body && Number.isInteger(c.body.seed) ? c.body.seed : null;
  return ok(Array.from({ length: count }, (_, i) => ({ ...enqueueTake(c.params.p, o, seed === null ? null : seed + i) })));
});
route('POST', '/api/projects/{p}/orders/{key}/attempts/{id}/mark', async (c) => {
  const r = lookupTake(c);
  if (r.error) return r.error;
  if (!['new', 'candidate', 'discarded'].includes(c.body && c.body.state)) return fail(c.lang, 400, 'api.bad_param', { name: 'state' });
  r.take.state = c.body.state;
  return ok({ ...r.take });
});
route('POST', '/api/projects/{p}/orders/{key}/attempts/{id}/note', (c) => {
  const r = lookupTake(c);
  if (r.error) return r.error;
  r.take.note = String((c.body && c.body.text) || '');
  return ok({ ...r.take });
});
route('GET', '/api/projects/{p}/orders/{key}/attempts/{id}/audio', (c) => {
  const r = lookupTake(c);
  if (r.error) return r.error;
  return { status: 200, blob: wavOf(samplesOf(c.params.p, c.params.key, r.take)), headers: { 'Content-Type': 'audio/wav' } };
});
route('GET', '/api/projects/{p}/orders/{key}/attempts/{id}/peaks', (c) => {
  const r = lookupTake(c);
  if (r.error) return r.error;
  const raw = c.query.get('n');
  const n = raw === null ? 400 : Number(raw);  // 400 = DEFAULT_N of gvoice/peaks.py
  if (raw === '' || !Number.isInteger(n) || n < 16 || n > 2000) return fail(c.lang, 400, 'api.bad_param', { name: 'n' });
  return ok({ peaks: peaksOf(samplesOf(c.params.p, c.params.key, r.take), n), audioMs: r.take.audioMs });
});

route('POST', '/api/projects/{p}/orders/{key}/choose', async (c) => {
  const o = lookup(c);
  if (o.error) return o.error;
  const id = c.body && c.body.attempt;
  const a = o.attempts.find((x) => x.id === id);
  if (!a) return fail(c.lang, 404, 'order.attempt_unknown', { attempt: id, order: o.key });
  if (a.state === 'discarded') return fail(c.lang, 409, 'order.choose_discarded', { attempt: id });
  if (!('audioMs' in a)) return fail(c.lang, 409, 'order.choose_no_audio', { attempt: id });
  const old = o.chosen;
  if (old !== id) { o.chosenHistory.push(old); o.chosen = id; }
  return ok({ old, new: id, entries: printsJob(c.params.p, o, id) });
});
route('POST', '/api/projects/{p}/orders/{key}/undo', async (c) => {
  const o = lookup(c);
  if (o.error) return o.error;
  if (!o.chosenHistory.length) return fail(c.lang, 409, 'order.history_empty', { order: o.key });
  const target = o.chosenHistory[o.chosenHistory.length - 1];
  if (target !== null && o.attempts.find((x) => x.id === target).state === 'discarded') return fail(c.lang, 409, 'order.undo_discarded', { attempt: target });
  const old = o.chosen;
  o.chosenHistory.pop(); o.chosen = target;
  return ok({ old, new: target, entries: printsJob(c.params.p, o, target) });
});
/* elegir (o deshacer hacia) una toma de voz sin todas sus huellas encola el trabajo `prints` */
function printsJob(p, order, id) {
  if (order.type !== 'voice' || id === null) return [];
  const a = order.attempts.find((x) => x.id === id);
  if (PRINT_MODELS.every((m) => a.prints && a.prints[m])) return [];
  const open = queue.find((e) => e.kind === 'prints' && e.project === p && e.key === order.key && e.take === id && ['queued', 'running'].includes(e.state));
  if (open) return [];
  const entry = { id: nextEntry++, kind: 'prints', project: p, key: order.key, seed: null, text: null, take: id, state: 'queued', pid: null, enqueuedAt: now(), startedAt: null, finishedAt: null, error: null, attemptId: null, cancelRequested: false };
  queue.push(entry);
  return [{ ...entry }];
}

/* la cola: cada entrada con `errorText` si falló */
async function entryView(lang, e) {
  const item = { ...e };
  if (e.error) item.errorText = await text(lang, 'error.' + e.error.code, e.error.params || {});
  return item;
}
route('GET', '/api/queue', async (c) => {
  const state = c.query.get('state');
  if (state !== null && !['queued', 'running', 'done', 'failed', 'cancelled'].includes(state)) return fail(c.lang, 400, 'api.bad_param', { name: 'state' });
  return ok(await Promise.all(queue.filter((e) => state === null || e.state === state).sort((a, b) => a.id - b.id).map((e) => entryView(c.lang, e))));
});
route('POST', '/api/queue/{id}/cancel', async (c) => {
  const e = queue.find((x) => x.id === Number(c.params.id));
  if (!e) return fail(c.lang, 404, 'queue.unknown', { id: c.params.id });
  if (!['queued', 'running'].includes(e.state)) return fail(c.lang, 409, 'queue.not_cancellable', { id: c.params.id, state: e.state });
  if (e.state === 'running') e.cancelRequested = true; else { e.state = 'cancelled'; e.finishedAt = now(); }
  return ok(await entryView(c.lang, e));
});
route('POST', '/api/queue/clear', (c) => {
  const gone = queue.filter((e) => e.state === 'queued' && (!(c.body && c.body.project) || e.project === c.body.project));
  for (const e of gone) { e.state = 'cancelled'; e.finishedAt = now(); }
  return ok(gone.map((e) => ({ ...e })));
});

/* modelos: el catálogo de qwentts, con los dos primeros ya descargados */
const MODELS = [
  { id: '0.6b-base', file: 'qwen-talker-0.6b-base-Q8_0.gguf', use: 'base', bytes: 992615488, state: 'ok' },
  { id: '1.7b-base', file: 'qwen-talker-1.7b-base-Q8_0.gguf', use: 'base', bytes: 2079448256, state: 'ok' },
  { id: '1.7b-voicedesign', file: 'qwen-talker-1.7b-voicedesign-Q8_0.gguf', use: 'design', bytes: 2042833824, state: 'missing' },
  { id: 'tokenizer-12hz', file: 'qwen-codec-12hz-Q8_0.gguf', use: 'codec', bytes: 291150624, state: 'ok' },
];
const modelView = (m) => ({ ...m, path: `/home/deck/.local/share/gvoice/models/${m.file}`, actual: m.state === 'missing' ? null : m.bytes });
const pick = (c) => { const ids = (c.body && c.body.ids) || []; return MODELS.filter((m) => !ids.length || ids.includes(m.id)); };
route('GET', '/api/models', () => ok(MODELS.map(modelView)));
route('POST', '/api/models/verify', (c) => ok(pick(c).map(modelView)));
route('POST', '/api/models/fetch', (c) => ok(pick(c).map((m) => {
  const action = m.state === 'missing' ? 'downloaded' : 'present';
  m.state = 'ok';
  return { id: m.id, action, path: modelView(m).path };
})));

/* ---- el transporte que enchufa app.js en api.js: (method, url, body) -> {status, json|blob, headers} ---- */
export async function transport(method, url, body) {
  await new Promise((r) => setTimeout(r, 80 + Math.random() * 120));
  const u = new URL(url, location.origin);
  const seg = u.pathname.split('/').filter(Boolean).map(decodeURIComponent);
  const lang = u.searchParams.get('lang') || 'es';
  let shapeFound = false;
  query: for (const r of routes) {
    if (r.parts.length !== seg.length) continue;
    const params = {};
    for (let i = 0; i < seg.length; i++) {
      if (r.parts[i].startsWith('{')) params[r.parts[i].slice(1, -1)] = seg[i];
      else if (r.parts[i] !== seg[i]) continue query;
    }
    shapeFound = true; // la ruta existe: si el método no es el suyo, 405 como el servidor
    if (r.method !== method) continue;
    const q = new URLSearchParams(u.search); q.delete('lang');
    return r.handler({ params, query: q, body, lang });
  }
  if (shapeFound) return fail(lang, 405, 'api.method_not_allowed', { method });
  return fail(lang, 404, 'api.not_found', { path: u.pathname });
}
