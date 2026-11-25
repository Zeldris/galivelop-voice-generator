/* Copiado de gimg@46248251 (D7); adaptado a gvoice.
   Cliente de la API local de gvoice (contrato en gvoice/api_contract.py y docs/api.md).
   - Toda petición lleva `?lang=` (el idioma del selector) y, si escribe, `Content-Type: application/json`.
   - Un error de la API llega como ApiError {status, code, params, message, errors}; la red caída, como OfflineError.
   - El transporte se puede sustituir (`setTransport`) para el prototipo sin servidor (`?mock=1`) y para los tests. */

export class ApiError extends Error {
  constructor(status, body) {
    const err = (body && body.error) || {};
    super(err.message || `HTTP ${status}`);
    this.name = 'ApiError';
    this.apiMessage = err.message || null;   // only what the API said (`message` falls back to `HTTP <status>`)
    this.status = status;
    this.code = err.code || 'api.unexpected';
    this.params = err.params || {};
    this.errors = err.errors || null;
  }
}

export class OfflineError extends Error {
  constructor(cause) { super('offline'); this.name = 'OfflineError'; this.cause = cause; }
}

const state = { lang: 'es', transport: null, offline: false };
const offlineListeners = new Set();

export function setLang(lang) { state.lang = lang; }
export function getLang() { return state.lang; }

/** transport(method, path, body) -> {status, json|blob}. Si es null se usa fetch. */
export function setTransport(fn) { state.transport = fn; }

/** Avisa de cambios de conectividad: fn(isOffline). */
export function onOffline(fn) { offlineListeners.add(fn); return () => offlineListeners.delete(fn); }
function setOffline(v) {
  if (state.offline === v) return;
  state.offline = v;
  for (const fn of offlineListeners) fn(v);
}
export function isOffline() { return state.offline; }

function withLang(path) {
  const sep = path.includes('?') ? '&' : '?';
  return `${path}${sep}lang=${encodeURIComponent(state.lang)}`;
}

async function request(method, path, body) {
  const url = withLang(path);
  if (state.transport) {
    const res = await state.transport(method, url, body);
    if (res.status >= 400) throw new ApiError(res.status, res.json);
    setOffline(false);
    return res.json;
  }
  let res;
  try {
    res = await fetch(url, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: 'no-store',
    });
  } catch (e) {
    setOffline(true);
    throw new OfflineError(e);
  }
  setOffline(false);
  if (res.status === 204) return null;
  let json = null;
  try { json = await res.json(); } catch { json = null; }
  if (!res.ok) throw new ApiError(res.status, json);
  return json;
}

/** URL to give an `<audio src>`. Without a transport the browser asks the server itself (no fetch of the WAV); with
 *  one (simulator, tests) the transport's blob becomes an object URL: free it with `revokeAudioUrl`. */
async function audioUrl(p, key, id) {
  const url = withLang(paths.audio(p, key, id));
  if (!state.transport) return url;
  const res = await state.transport('GET', url);
  if (res.status >= 400) throw new ApiError(res.status, res.json);
  return URL.createObjectURL(res.blob);
}
/** Revokes only object URLs (`blob:`); a plain server URL is left alone. */
function revokeAudioUrl(url) {
  if (typeof url === 'string' && url.startsWith('blob:')) URL.revokeObjectURL(url);
}

export const get = (path) => request('GET', path);
export const post = (path, body = {}) => request('POST', path, body);

/* ---- rutas: la clave de un pedido va codificada en un solo segmento (`narrator%2Fintro-01`) ---- */
const enc = encodeURIComponent;
export const paths = {
  health: () => '/api/health',
  locales: (lang) => `/api/locales/${enc(lang)}`,
  projects: () => '/api/projects',
  project: (p) => `/api/projects/${enc(p)}`,
  removeProject: (p) => `/api/projects/${enc(p)}/remove`,
  orders: (p, q = {}) => {
    const qs = Object.entries(q).filter(([, v]) => v !== undefined && v !== null && v !== '')
      .map(([k, v]) => `${enc(k)}=${enc(v)}`).join('&');
    return `/api/projects/${enc(p)}/orders${qs ? '?' + qs : ''}`;
  },
  newOrder: (p) => `/api/projects/${enc(p)}/orders`,
  order: (p, key) => `/api/projects/${enc(p)}/orders/${enc(key)}`,
  sheet: (p, key) => `${paths.order(p, key)}/sheet`,
  checkSheet: () => '/api/sheet/check',
  attempts: (p, key) => `${paths.order(p, key)}/attempts`,
  attempt: (p, key, id) => `${paths.order(p, key)}/attempts/${enc(id)}`,
  mark: (p, key, id) => `${paths.attempt(p, key, id)}/mark`,
  note: (p, key, id) => `${paths.attempt(p, key, id)}/note`,
  audio: (p, key, id) => `${paths.attempt(p, key, id)}/audio`,
  peaks: (p, key, id, n = 0) => `${paths.attempt(p, key, id)}/peaks${n ? '?n=' + enc(n) : ''}`,
  choose: (p, key) => `${paths.order(p, key)}/choose`,
  undo: (p, key) => `${paths.order(p, key)}/undo`,
  queue: (state) => `/api/queue${state ? '?state=' + enc(state) : ''}`,
  cancel: (id) => `/api/queue/${enc(id)}/cancel`,
  clear: () => '/api/queue/clear',
  models: (engine) => `/api/models${engine ? '?engine=' + enc(engine) : ''}`,
  verifyModels: () => '/api/models/verify',
  fetchModels: () => '/api/models/fetch',
};

/* ---- llamadas con nombre (lo que consumen los componentes) ---- */
export const api = {
  audioUrl,
  revokeAudioUrl,
  health: () => get(paths.health()),
  locales: (lang) => get(paths.locales(lang)),
  projects: () => get(paths.projects()),
  addProject: (path) => post(paths.projects(), { path }),
  project: (p) => get(paths.project(p)),
  removeProject: (p) => post(paths.removeProject(p), {}),
  orders: (p, q) => get(paths.orders(p, q)),
  newOrder: (p, order, count = 1) => post(paths.newOrder(p), { order, count }),
  order: (p, key) => get(paths.order(p, key)),
  sheet: (p, key) => get(paths.sheet(p, key)),
  checkSheet: (designSheet) => post(paths.checkSheet(), { designSheet }),
  newTakes: (p, key, spec = {}) => post(paths.attempts(p, key), spec),
  mark: (p, key, id, state) => post(paths.mark(p, key, id), { state }),
  note: (p, key, id, text) => post(paths.note(p, key, id), { text }),
  peaks: (p, key, id, n) => get(paths.peaks(p, key, id, n)),
  choose: (p, key, attempt) => post(paths.choose(p, key), { attempt }),
  undo: (p, key) => post(paths.undo(p, key), {}),
  queue: (state) => get(paths.queue(state)),
  cancel: (id) => post(paths.cancel(id), {}),
  clearQueue: (project) => post(paths.clear(), project ? { project } : {}),
  models: (engine) => get(paths.models(engine)),
  verifyModels: (engine, ids = []) => post(paths.verifyModels(), { engine, ids }),
  fetchModels: (engine, ids = []) => post(paths.fetchModels(), { engine, ids }),
};

/** Texto legible de cualquier fallo, para los avisos (el mensaje de la API ya viene en el idioma pedido). */
export function describeError(e, t) {
  if (e instanceof OfflineError) return t('ui.offline.title');
  if (e instanceof ApiError) return e.apiMessage || t('ui.error.code', { code: e.code });
  return t('ui.error.generic', { message: e && e.message ? e.message : String(e) });
}
