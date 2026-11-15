/* Copiado de gimg@46248251 (D7); escrito de nuevo para gvoice (F5.3). Ficha de diseño con avisos (F5.3): la instrucción que saldrá de la ficha (vista previa, monoespaciada) y la lista de
   avisos de `gvoice/sheet.py` (D11: nunca bloquean). Cada aviso lleva icono y texto, nunca solo color. Los iconos son una
   serie propia de línea simple, legible a 24 px, hecha con `createElementNS` (sin archivos externos, compatible con la
   CSP); van con aria-hidden: el texto es lo que se lee. Los textos salen de `warning.<código>` del idioma activo y, si
   la clave no existe, del `message` que ya trae la API. La lógica pura (`warningItems`) se prueba sin DOM. */

import { h, replace } from '../dom.js';
import { t, has } from '../i18n.js';

const SVG_NS = 'http://www.w3.org/2000/svg';

/* Trazos de cada icono en una rejilla de 24: [etiqueta, atributos]. Un icono por código; `default` para los demás. */
const ICONS = {
  // edad sin decir: círculo con interrogación
  'sheet.age_missing': [['circle', { cx: 12, cy: 12, r: 9 }], ['path', { d: 'M9.5 9.5a2.5 2.5 0 1 1 3.6 2.2c-.8.4-1.1.9-1.1 1.8' }], ['path', { d: 'M12 16.5v.5' }]],
  // edad no adulta: figura pequeña (cabeza y hombros)
  'sheet.age_not_adult': [['circle', { cx: 12, cy: 8, r: 3 }], ['path', { d: 'M6 20v-1.5a6 6 0 0 1 12 0V20' }], ['path', { d: 'M20 4v4M20 10.5v.5' }]],
  // palabra que empuja a sonido infantil: bocadillo con una raya
  'sheet.banned_word': [['path', { d: 'M4 5h16v11h-9l-4 4v-4H4z' }], ['path', { d: 'M8 10.5h8' }]],
  default: [['path', { d: 'M12 3l10 18H2z' }], ['path', { d: 'M12 10v5M12 18v.5' }]],
};

/** Icono SVG (24 px, trazo de línea) de un código de aviso. Con `aria-hidden`: el texto del aviso es el accesible. */
export function warningIcon(code) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  for (const [k, v] of Object.entries({ viewBox: '0 0 24 24', width: 24, height: 24, fill: 'none', stroke: 'currentColor',
    'stroke-width': 1.75, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true', focusable: 'false', class: 'warn-icon' })) {
    svg.setAttribute(k, String(v));
  }
  for (const [tag, attrs] of ICONS[code] || ICONS.default) {
    const part = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) part.setAttribute(k, String(v));
    svg.appendChild(part);
  }
  return svg;
}

/** Avisos de la API ({code, params, message?}) → [{code, icon, text}] (`icon` es el código del icono usado). Puro. */
export function warningItems(warnings) {
  return (Array.isArray(warnings) ? warnings : []).map((w) => {
    const key = 'warning.' + w.code;
    const text = has(key) ? t(key, w.params) : (typeof w.message === 'string' && w.message ? w.message : key);
    return { code: w.code, icon: ICONS[w.code] ? w.code : 'default', text };
  });
}

/** Panel con la instrucción y los avisos. `update(res)` lo repinta (la lista es una región `aria-live` que persiste, para
    que el lector anuncie los cambios); `fail(text)` deja un aviso discreto de que no se pudo comprobar. */
export function sheetPanel() {
  const preview = h('pre.sheet-instruction.mono', { aria: { label: t('ui.sheet.instruction') } });
  const list = h('ul.sheet-warnings', { role: 'status', aria: { live: 'polite' } });
  const note = h('p.hint.sheet-fail', { hidden: true });
  const node = h('div.sheet-check', {}, h('h4', {}, t('ui.sheet.instruction')), preview, list, note);
  return {
    node,
    update(res) {
      note.hidden = true;
      preview.textContent = (res && res.instruction) || '';
      const items = warningItems(res && res.warnings);
      replace(list, items.length
        ? items.map((it) => h('li.sheet-warning', { data: { code: it.code } }, warningIcon(it.icon), h('span.warn-text', {}, it.text)))
        : h('li.sheet-ok', {}, t('ui.sheet.noWarnings')));
    },
    fail(text) { note.textContent = text; note.hidden = false; },
  };
}

/** Panel ya pintado con `res` ({instruction, warnings}). */
export function sheetWarnings(res) {
  const p = sheetPanel();
  p.update(res);
  return p.node;
}
