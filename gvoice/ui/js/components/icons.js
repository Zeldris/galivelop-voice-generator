/* Nuevo en gvoice (no copiado de gimg) (F5.4). Iconos de la interfaz: serie propia de línea simple, legible a 24 px
   (sin lucide), hecha con `createElementNS` (sin archivos externos, compatible con la CSP). Van con `aria-hidden`: el
   texto que los acompaña es lo que se lee. Los avisos de la ficha llevan los suyos en sheet-warnings.js. */

const SVG_NS = 'http://www.w3.org/2000/svg';

/* Trazos en una rejilla de 24: [etiqueta, atributos]. */
const SHAPES = {
  play: [['path', { d: 'M8 5l11 7-11 7z' }]],
  pause: [['path', { d: 'M8 5v14' }], ['path', { d: 'M16 5v14' }]],
  check: [['path', { d: 'M5 12.5l4.5 4.5L19 7' }]],
  undo: [['path', { d: 'M9 14L4 9l5-5' }], ['path', { d: 'M4 9h10a6 6 0 0 1 0 12h-3' }]],
  keys: [['path', { d: 'M3 7h18v10H3z' }], ['path', { d: 'M7 11h.5M11 11h.5M15 11h.5M8 14h8' }]],
  plus: [['path', { d: 'M12 5v14M5 12h14' }]],
};

/** Icono de línea de 24 px (`play`, `pause`, `check`, `undo`, `keys`, `plus`), oculto a los lectores de pantalla. */
export function icon(name, cls = 'icon') {
  const svg = document.createElementNS(SVG_NS, 'svg');
  for (const [k, v] of Object.entries({ viewBox: '0 0 24 24', width: 20, height: 20, fill: 'none', stroke: 'currentColor',
    'stroke-width': 1.75, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true', focusable: 'false', class: cls })) {
    svg.setAttribute(k, String(v));
  }
  for (const [tag, attrs] of SHAPES[name] || []) {
    const part = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) part.setAttribute(k, String(v));
    svg.appendChild(part);
  }
  return svg;
}
