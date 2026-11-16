/* DOM falso compartido por los tests del JS de la UI (tests/test_ui_js.py): lo justo de un navegador para montar los
   componentes de gvoice/ui/js con `h()` de dom.js y mirar el resultado, sin npm. No es un navegador: no hay estilos,
   ni foco real, ni selectores; `dialog.close()` avisa con `close` en un microtarea, como el navegador (asíncrono).
   Desde F5.4: `<canvas>` con contexto 2D que anota cada llamada (`ctx.calls`), `<audio>` con `play`/`pause`/`currentTime`/
   `duration`, `closest()` con selectores simples y escuchas en `document` (a las que llegan los eventos que suben).
   `installFakeDom()` instala `document`, `Node` y `Element` globales y devuelve `document`. */

export class FakeNode {
  constructor() { this.children = []; this.parent = null; }
  get parentNode() { return this.parent; }
  get isConnected() { let n = this; while (n.parent) n = n.parent; return n.isRoot === true; }
  append(...c) { for (const x of c) this.appendChild(typeof x === 'string' ? new FakeText(x) : x); }
  appendChild(c) { if (c.parent) c.parent.removeChild(c); c.parent = this; this.children.push(c); return c; }
  removeChild(c) { this.children = this.children.filter((x) => x !== c); c.parent = null; return c; }
  replaceChildren(...c) { for (const x of this.children) x.parent = null; this.children = []; this.append(...c); }
  remove() { if (this.parent) this.parent.removeChild(this); }
  get firstChild() { return this.children[0] || null; }
  get textContent() { return this.children.map((c) => c.textContent).join(''); }
  set textContent(v) { for (const x of this.children) x.parent = null; this.children = []; if (String(v) !== '') this.appendChild(new FakeText(String(v))); }
}

export class FakeText extends FakeNode {
  constructor(s) { super(); this.text = s; }
  get textContent() { return this.text; }
  set textContent(v) { this.text = String(v); }
}

class ClassList {
  constructor(el) { this.el = el; }
  get list() { return this.el.className.split(/\s+/).filter(Boolean); }
  contains(c) { return this.list.includes(c); }
  add(...cs) { this.el.className = [...new Set([...this.list, ...cs])].join(' '); }
  remove(...cs) { this.el.className = this.list.filter((c) => !cs.includes(c)).join(' '); }
  toggle(c, force) { const on = force === undefined ? !this.contains(c) : force; if (on) this.add(c); else this.remove(c); return on; }
}

export class FakeEl extends FakeNode {
  constructor(tag, doc) {
    super();
    this.tag = tag; this.ownerDocument = doc; this.attrs = {}; this.className = ''; this.dataset = {}; this.hidden = false;
    this.disabled = false; this.checked = false; this.selected = false; this.open = false;
    this.listeners = {}; this.classList = new ClassList(this);
    this.vars = {}; this.style = { setProperty: (k, v) => { this.vars[k] = v; }, removeProperty: (k) => { delete this.vars[k]; } };
    this._value = '';
    this.validity = { badInput: false };
    this.focused = 0;
    this.paused = true; this.currentTime = 0; this.duration = NaN; this.clientWidth = 300; // <audio> y medidas de un <canvas>/caja
  }
  get id() { return this.attrs.id || ''; }
  get value() {
    if (this.tag === 'select') {
      const opts = this.find((e) => e.tag === 'option');
      const chosen = opts.find((o) => o.selected) || opts[0];
      return chosen ? chosen.value : '';
    }
    return this._value;
  }
  set value(v) {
    if (this.tag === 'select') { for (const o of this.find((e) => e.tag === 'option')) o.selected = o.value === String(v); } else this._value = String(v);
  }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  removeEventListener(type, fn) { this.listeners[type] = (this.listeners[type] || []).filter((f) => f !== fn); }
  /** Despacha un evento y lo deja subir por los padres (salvo `stopPropagation`). Devuelve el evento. */
  dispatchEvent(ev) {
    const event = typeof ev === 'string' ? { type: ev } : ev;
    event.target = event.target || this;
    event.defaultPrevented = false; event.stopped = false;
    event.preventDefault = () => { event.defaultPrevented = true; };
    event.stopPropagation = () => { event.stopped = true; };
    for (let n = this; n && !event.stopped; n = n.parent) {
      if (!(n instanceof FakeEl)) break;
      for (const fn of [...(n.listeners[event.type] || [])]) fn(event);
    }
    if (!event.stopped && this.isConnected) this.ownerDocument.fire(event);
    return event;
  }
  getBoundingClientRect() { return { left: 0, top: 0, width: this.clientWidth, height: 64 }; }
  scrollIntoView() { this.scrolled = (this.scrolled || 0) + 1; }
  /** Contexto 2D falso: cada método y cada asignación (`fillStyle`…) quedan en `calls` como [nombre, ...argumentos]. */
  getContext(kind) {
    if (kind !== '2d') return null;
    if (!this._ctx) {
      const calls = [];
      this._ctx = new Proxy({ calls }, {
        get: (o, k) => (k in o ? o[k] : (...a) => { calls.push([String(k), ...a]); }),
        set: (o, k, v) => { calls.push(['set ' + String(k), v]); return true; },
      });
    }
    return this._ctx;
  }
  play() { this.paused = false; this.dispatchEvent('play'); return Promise.resolve(); }
  pause() { if (this.paused) return; this.paused = true; this.dispatchEvent('pause'); }
  /** Selectores simples separados por comas: `tag`, `.clase`, `[atributo]`, `[atributo="valor"]`. Sube por los padres. */
  matches(sel) {
    return sel.split(',').map((x) => x.trim()).some((one) => {
      const m = one.match(/^([a-z0-9]*)(?:\.([\w-]+))?(?:\[([\w-]+)(?:=\"?([^\"\]]*)\"?)?\])?$/i);
      if (!m) return false;
      const [, tag, cls, attr, val] = m;
      return (!tag || this.tag === tag) && (!cls || this.classList.contains(cls)) && (!attr || (attr in this.attrs && (val === undefined || this.attrs[attr] === val)));
    });
  }
  closest(sel) { for (let n = this; n instanceof FakeEl; n = n.parent) if (n.matches(sel)) return n; return null; }
  /** Atajo de test: escribe en un campo y dispara `input`. */
  type(text) { this.value = text; return this.dispatchEvent('input'); }
  click() { return this.dispatchEvent('click'); }
  focus() { this.focused++; this.ownerDocument.activeElement = this; }
  showModal() { this.open = true; }
  close() {
    if (!this.open) return;
    this.open = false;
    queueMicrotask(() => this.dispatchEvent({ type: 'close' }));
  }
  find(pred, acc = []) { for (const c of this.children) if (c instanceof FakeEl) { if (pred(c)) acc.push(c); c.find(pred, acc); } return acc; }
  byId(id) { return this.find((e) => e.attrs.id === id)[0] || null; }
}

/** Instala el DOM falso en `globalThis` y devuelve `document`. */
export function installFakeDom() {
  const listeners = {};
  const doc = { activeElement: null, createTextNode: (s) => new FakeText(s), visibilityState: 'visible', listeners,
    addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn); },
    removeEventListener: (type, fn) => { listeners[type] = (listeners[type] || []).filter((f) => f !== fn); },
    fire: (event) => { for (const fn of [...(listeners[event.type] || [])]) fn(event); },
    /** Cuántas escuchas hay en `document` (los tests comprueban que limpiar una vista no deja ninguna). */
    listenerCount: () => Object.values(listeners).reduce((n, l) => n + l.length, 0) };
  doc.documentElement = Object.assign(new FakeEl('html', doc), { lang: '', isRoot: true });
  doc.body = new FakeEl('body', doc);
  doc.documentElement.appendChild(doc.body);
  doc.createElement = (tag) => new FakeEl(tag, doc);
  doc.createElementNS = (ns, tag) => { const e = new FakeEl(tag, doc); e.ns = ns; return e; };
  doc.getElementById = (id) => doc.documentElement.byId(id);
  globalThis.Node = FakeNode;
  globalThis.Element = FakeEl;
  globalThis.document = doc;
  globalThis.location = { hash: '' };
  globalThis.history = { replaceState: (_s, _t, hash) => { globalThis.location.hash = hash; } };
  return doc;
}

/** Espera a que acaben las promesas ya resueltas (varias vueltas de microtareas). */
export async function flush(n = 10) { for (let i = 0; i < n; i++) await Promise.resolve(); }

/** Temporizadores falsos: sustituye `setTimeout`/`clearTimeout` globales; `advance(ms)` dispara los que vencen. */
export function fakeTimers() {
  const real = { setTimeout: globalThis.setTimeout, clearTimeout: globalThis.clearTimeout };
  let now = 0; let next = 1; const pending = new Map();
  globalThis.setTimeout = (fn, ms = 0) => { const id = next++; pending.set(id, { fn, at: now + ms }); return id; };
  globalThis.clearTimeout = (id) => { pending.delete(id); };
  return {
    get pending() { return pending.size; },
    async advance(ms) {
      now += ms;
      for (const [id, t] of [...pending]) if (t.at <= now) { pending.delete(id); t.fn(); }
      await flush();
    },
    restore() { Object.assign(globalThis, real); },
  };
}
