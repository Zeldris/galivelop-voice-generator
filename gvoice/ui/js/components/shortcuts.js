/* Copiado de gimg@46248251 (D7); adaptado a gvoice: las tomas son audios (reproducir, elegir, deshacer), no imágenes.
   Atajos de teclado y del mando de la Deck. Steam Input traduce el mando a teclas (cruceta = flechas, A = Intro,
   B = Escape); además, donde el navegador expone el mando (`navigator.getGamepads`), se lee directo: cruceta = tomas,
   A = reproducir/pausar, X = elegir, Y = deshacer, B = pausar. Los de la galería los ejecuta order-view.js con
   `keyAction`/`padActions` (puras); aquí van los globales y el diálogo de ayuda, que se arma en JS (sin tocar el HTML).
   Ninguno actúa mientras el foco está en un campo de texto. */

import { h, replace } from '../dom.js';
import { t } from '../i18n.js';

export const SHORTCUTS = [
  ['ui.shortcuts.group.global', [
    [['?'], 'ui.shortcuts.help'],
    [['Esc'], 'ui.shortcuts.escape'],
    [['Tab'], 'ui.shortcuts.tab'],
  ]],
  ['ui.shortcuts.group.gallery', [
    [['←', '↑'], 'ui.shortcuts.prev'],
    [['→', '↓'], 'ui.shortcuts.next'],
    [['Intro', 'P'], 'ui.shortcuts.toggle'],
    [['E'], 'ui.shortcuts.choose'],
    [['U'], 'ui.shortcuts.undo'],
    [['C'], 'ui.shortcuts.candidate'],
    [['D'], 'ui.shortcuts.discard'],
    [['G'], 'ui.shortcuts.another'],
  ]],
  ['ui.shortcuts.group.pad', [
    [['✚'], 'ui.shortcuts.padDpad'],
    [['A'], 'ui.shortcuts.toggle'],
    [['X'], 'ui.shortcuts.choose'],
    [['Y'], 'ui.shortcuts.undo'],
    [['B'], 'ui.shortcuts.padPause'],
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
const LETTERS = { p: 'toggle', e: 'choose', u: 'undo', c: 'candidate', d: 'discard', g: 'another' };

export function keyAction(e, letters = true) {
  if (e.ctrlKey || e.metaKey || e.altKey) return null;
  if (KEYS[e.key]) return KEYS[e.key];
  if (e.key === ' ') return 'toggle';
  return letters && typeof e.key === 'string' ? (LETTERS[e.key.toLowerCase()] || null) : null;
}

/* Botones del mando estándar (W3C): 0 = A, 1 = B, 2 = X, 3 = Y, 12..15 = cruceta arriba, abajo, izquierda, derecha. */
const PAD = { 0: 'toggle', 1: 'pause', 2: 'choose', 3: 'undo', 12: 'prev', 13: 'next', 14: 'prev', 15: 'next' };

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

let help = null;

export function initShortcuts({ closeAll = () => {} } = {}) {
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { closeHelp(); closeAll(); return; }
    if (isTyping(e.target) || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === '?') { e.preventDefault(); openHelp(); }
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
export function openHelp(opener = null) {
  if (help) return help;
  const close = h('button.btn', { type: 'button', onclick: () => dlg.close() }, t('ui.actions.close'));
  const body = h('div');
  replace(body, h('dl.shortcut-list', {}, SHORTCUTS.map(([group, items]) => [
    h('h3', {}, t(group)),
    items.map(([keys, label]) => [h('dt', {}, keys.map((k) => h('kbd.kbd', {}, k))), h('dd', {}, t(label))]),
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
