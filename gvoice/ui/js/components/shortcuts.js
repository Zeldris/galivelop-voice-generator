/* Copiado de gimg@46248251 (D7); adaptado a gvoice: las tomas son audios (reproducir, elegir, deshacer), no imágenes.
   Atajos de teclado y del mando de la Deck. Steam Input traduce el mando a teclas (cruceta = flechas, A = Intro,
   B = Escape); además, donde el navegador expone el mando (`navigator.getGamepads`), se lee directo: cruceta = tomas,
   A = reproducir/pausar, X = elegir, Y = deshacer, B = pausar, LB/RB = cambiar A↔B (comparación A/B, F5.5). Los de la galería los ejecuta order-view.js con
   `keyAction`/`padActions` (puras); aquí van los globales y el diálogo de ayuda, que se arma en JS (sin tocar el HTML).
   Ninguno actúa mientras el foco está en un campo de texto. */

import { h, replace, closest } from '../dom.js';
import { t } from '../i18n.js';
import { isQueueOpen } from './queue-bar.js';

/* [keys, label, action]: sin acción, la fila vale siempre; con ella (una o varias: basta una), solo se enseña en las vistas que la hacen (`bindShortcuts`). */
export const SHORTCUTS = [
  ['ui.shortcuts.group.global', [
    [['?'], 'ui.shortcuts.help'],
    [['Esc'], 'ui.shortcuts.escape'],
    [['Tab'], 'ui.shortcuts.tab'],
  ]],
  ['ui.shortcuts.group.gallery', [
    [['←', '↑'], 'ui.shortcuts.prev', 'prev'],
    [['→', '↓'], 'ui.shortcuts.next', 'next'],
    [['Intro', 'P'], 'ui.shortcuts.toggle', 'toggle'],
    [['E'], 'ui.shortcuts.choose', 'choose'],
    [['U'], 'ui.shortcuts.undo', 'undo'],
    [['C'], 'ui.shortcuts.candidate', 'candidate'],
    [['D'], 'ui.shortcuts.discard', 'discard'],
    [['G'], 'ui.shortcuts.another', 'another'],
    [['X'], 'ui.shortcuts.swap', 'swap'],
  ]],
  ['ui.shortcuts.group.pad', [
    [['✚'], 'ui.shortcuts.padDpad', ['prev', 'next']],
    [['A'], 'ui.shortcuts.toggle', 'toggle'],
    [['X'], 'ui.shortcuts.choose', 'choose'],
    [['Y'], 'ui.shortcuts.undo', 'undo'],
    [['B'], 'ui.shortcuts.padPause', 'pause'],
    [['LB', 'RB'], 'ui.shortcuts.swap', 'swap'],
  ]],
];

const ONE_KEY = 'gvoice.oneKey';

/** Interruptor «atajos de una tecla» (WCAG 2.1.4): activado por defecto, se guarda en el navegador. */
export function oneKeyEnabled() {
  try { return localStorage.getItem(ONE_KEY) !== 'off'; } catch { return true; }
}

function setOneKey(on) {
  try { localStorage.setItem(ONE_KEY, on ? 'on' : 'off'); } catch { /* sin almacenamiento: vale la sesión */ }
}

export function isTyping(target) {
  return target instanceof Element && (target.closest('input, textarea, select, [contenteditable="true"]') !== null);
}

/* Tecla → acción de la galería. Las flechas y Intro valen siempre; las letras, solo con los atajos de una tecla
   encendidos (`letters`). Pura: la usa la vista y la prueban los tests. Con Ctrl, Meta o Alt no hay acción. */
const KEYS = { ArrowLeft: 'prev', ArrowUp: 'prev', ArrowRight: 'next', ArrowDown: 'next', Enter: 'toggle', Escape: 'pause' };
const LETTERS = { p: 'toggle', e: 'choose', u: 'undo', c: 'candidate', d: 'discard', g: 'another', x: 'swap' };

export function keyAction(e, letters = true) {
  if (e.ctrlKey || e.metaKey || e.altKey) return null;
  if (KEYS[e.key]) return KEYS[e.key];
  if (e.key === ' ') return 'toggle';
  return letters && typeof e.key === 'string' ? (LETTERS[e.key.toLowerCase()] || null) : null;
}

/* Botones del mando estándar (W3C): 0 = A, 1 = B, 2 = X, 3 = Y, 4 y 5 = LB y RB, 12..15 = cruceta arriba, abajo, izquierda, derecha. */
const PAD = { 0: 'toggle', 1: 'pause', 2: 'choose', 3: 'undo', 4: 'swap', 5: 'swap', 12: 'prev', 13: 'next', 14: 'prev', 15: 'next' };

/** Acciones nuevas de un mando: las de los botones que ahora están pulsados y antes no (`before` es el array
    de booleanos del sondeo anterior). Devuelve {actions, pressed}. Pura. */
export function padActions(before, buttons) {
  const pressed = Array.from(buttons || [], (b) => Boolean(b && (b.pressed || b.value > 0.5)));
  const actions = [];
  for (const [i, action] of Object.entries(PAD)) if (pressed[i] && !(before && before[i])) actions.push(action);
  return { actions, pressed };
}

/** Sondea el mando cada 100 ms y llama a `onAction(acción)`. Devuelve `stop()`. Sin `navigator.getGamepads`, no hace nada. */
export function startGamepad(onAction) {
  if (typeof navigator === 'undefined' || typeof navigator.getGamepads !== 'function') return () => {};
  let before = [];
  let timer = null;
  let on = true;
  const poll = () => {
    if (!on) return;
    const pad = Array.from(navigator.getGamepads() || []).find((p) => p && p.connected !== false);
    if (pad) {
      const r = padActions(before, pad.buttons);
      before = r.pressed;
      for (const a of r.actions) onAction(a);
    } else before = [];
    timer = setTimeout(poll, 100);
  };
  timer = setTimeout(poll, 100);
  return () => { on = false; clearTimeout(timer); };
}

/** Steam Input turns the pad into keys, and where the browser also exposes the pad (`navigator.getGamepads`) the same
    press arrives twice. `merge(perform)` returns `{key, pad}`, one entry per source: an action that already came from
    the OTHER source less than `windowMs` ago is dropped (the same source repeating, e.g. key auto-repeat, is not). */
export function mergeSources(perform, { windowMs = 200, now = () => Date.now() } = {}) {
  const last = new Map(); // action -> {source, at} of the last action performed
  const gate = (source) => (action) => {
    const prev = last.get(action);
    const at = now();
    if (prev && prev.source !== source && at - prev.at < windowMs) return;
    last.set(action, { source, at });
    perform(action);
  };
  return { key: gate('key'), pad: gate('pad') };
}

let help = null;
let viewActions = new Set(); // actions of the view that bound the shortcuts (empty: no view bound, only the global rows), so the help lists only those

/** Wires keyboard and pad to `perform(action)` for one view. `actions` (an iterable) are the actions the view does;
    others are neither blocked nor listed in the help. Returns `stop()`. Keeps the filters in one place: not with the
    queue drawer open, not while typing, not over a dialog; Steam Input and the pad are merged (`mergeSources`). */
export function bindShortcuts(perform, { actions = null } = {}) {
  const set = actions ? new Set(actions) : null;
  const merged = mergeSources(perform);
  const onKey = (e) => {
    if (isQueueOpen() || e.defaultPrevented) return;   // the queue drawer is on top: the view below does not act
    if (isTyping(e.target) || e.ctrlKey || e.metaKey || e.altKey) return;
    const action = keyAction(e, oneKeyEnabled());
    if (!action || (set && !set.has(action))) return;   // a key that does nothing here is not blocked
    // Enter and space on a button, link or waveform do their own thing; on the card or the page they play
    if ((e.key === 'Enter' || e.key === ' ') && closest(e.target, 'button, a, [role="slider"], summary, dialog')) return;
    e.preventDefault();
    merged.key(action);
  };
  document.addEventListener('keydown', onKey);
  const stopPad = startGamepad((action) => {
    const a = document.activeElement;
    if (isQueueOpen() || isTyping(a) || helpOpen() || closest(a, 'dialog')) return;
    if (set && !set.has(action)) return;
    merged.pad(action);
  });
  viewActions = set;   // a view without `actions` does everything: null = no filter
  return () => {
    document.removeEventListener('keydown', onKey);
    stopPad();
    if (viewActions === set) viewActions = new Set();
    closeHelp();   // the route changed: a help open over the old view would list its actions
  };
}

/** ¿Está abierto el diálogo de ayuda? (un mando no debe actuar sobre la galería por debajo). */
export function helpOpen() { return help !== null; }

export function initShortcuts({ closeAll = () => {} } = {}) {
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      // con la ayuda abierta encima, Esc solo cierra la ayuda; `closeAll()` devuelve true si cerró algo (entonces las vistas ignoran la tecla)
      const wasHelp = help !== null;
      closeHelp();
      if (!wasHelp && closeAll() === true) e.preventDefault();
      return;
    }
    if (isTyping(e.target) || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === '?' && oneKeyEnabled()) { e.preventDefault(); openHelp(); } // «?» es un atajo de una tecla (WCAG 2.1.4)
  });
}

export function closeHelp() {
  if (!help) return;
  const dlg = help;
  help = null;
  dlg.close();
  dlg.remove();
}

/** Diálogo de ayuda con todos los atajos y el interruptor de los de una tecla. Devuelve el `dialog`. */
export function openHelp(opener = null, { actions = viewActions } = {}) {   // `actions: null` lists everything
  if (help) return help;
  const shown = (items) => items.filter(([, , action]) => !action || !actions || [].concat(action).some((a) => actions.has(a)));
  const close = h('button.btn', { type: 'button', onclick: () => dlg.close() }, t('ui.actions.close'));
  const body = h('div');
  replace(body, h('dl.shortcut-list', {}, SHORTCUTS.filter(([, items]) => shown(items).length).map(([group, items]) => [
    h('h3', {}, t(group)),
    shown(items).map(([keys, label]) => [h('dt', {}, keys.map((k) => h('kbd.kbd', {}, k))), h('dd', {}, t(label))]),
  ])),
  h('label.check', {}, h('input', { type: 'checkbox', checked: oneKeyEnabled(), onchange: (ev) => setOneKey(ev.target.checked) }), h('span', {}, t('ui.shortcuts.oneKey'))),
  h('p.hint', {}, t('ui.shortcuts.oneKeyHint')), h('p.hint', {}, t('ui.shortcuts.deck')));
  const dlg = h('dialog.shortcuts', { aria: { labelledby: 'shortcuts-title' } }, h('h2', { id: 'shortcuts-title' }, t('ui.shortcuts.title')), body, h('div.row', {}, close));
  dlg.addEventListener('keydown', (ev) => { if (ev.key !== 'Escape') ev.stopPropagation(); }); // Esc lo cierra el propio diálogo
  dlg.addEventListener('close', () => {
    dlg.remove();
    if (help === dlg) help = null;
    if (opener && opener.isConnected) opener.focus();
  });
  help = dlg;
  document.body.append(dlg);
  dlg.showModal();
  close.focus();
  return dlg;
}
