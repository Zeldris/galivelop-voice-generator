/* Nuevo en gvoice (no copiado de gimg) (F5.4). Forma de onda de una toma en un `<canvas>`: barras a partir de los picos
   del servidor (`GET …/peaks`), con la parte ya reproducida y un cursor. Los colores salen de los tokens CSS
   (`getComputedStyle`), y se redibuja al cambiar el tamaño, el tema (`data-theme` o el del sistema) o los picos.
   Es un control deslizante accesible (`role="slider"`): clic para saltar y, con el foco, ← → (5 %), Inicio y Fin. */

import { h } from '../dom.js';
import { barRects, fractionAt } from '../take-model.js';

const HEIGHT = 64;

/** createWaveform({label, onSeek, valueText}) → {node, setPeaks(peaks), setProgress(0..1), draw(), width(), destroy()}. */
export function createWaveform({ label, onSeek = () => {}, valueText = null }) {
  let peaks = [];
  let progress = 0;
  let destroyed = false;
  const canvas = h('canvas', { height: HEIGHT, aria: { hidden: true } });
  const node = h('div.wave', { role: 'slider', tabindex: 0, aria: { label, valuemin: 0, valuemax: 100, valuenow: 0 } }, canvas);

  const colors = () => {
    const cs = typeof getComputedStyle === 'function' ? getComputedStyle(document.documentElement) : null;
    const pick = (name, fallback) => (cs && cs.getPropertyValue(name).trim()) || fallback;
    return { bar: pick('--border', '#6f8493'), played: pick('--accent', '#d9467a'), cursor: pick('--text', '#13212b'), back: pick('--surface-2', '#f1f6f9') };
  };
  const width = () => Math.max(1, Math.round(node.clientWidth || (node.getBoundingClientRect && node.getBoundingClientRect().width) || 300));

  // What does not change with the playback position is computed once and cached: the size (and so the canvas
  // resize), the colours (`getComputedStyle`) and the bars. `draw()` recomputes everything (on resize, theme or peaks change);
  // `setProgress()` only repaints, which is what runs on every animation frame while playing.
  const hasRO = typeof ResizeObserver === 'function';
  let cache = null; // {w, colors, bars}

  function measure() {
    const w = width();
    const dpr = (typeof devicePixelRatio === 'number' && devicePixelRatio > 0) ? devicePixelRatio : 1;
    const cw = Math.round(w * dpr); const ch = Math.round(HEIGHT * dpr);
    if (canvas.width !== cw) canvas.width = cw; // assigning resets the canvas, so only when the size changed
    if (canvas.height !== ch) canvas.height = ch;
    cache = { w, dpr, colors: colors(), bars: barRects(peaks, w, HEIGHT) };
  }

  function paint(ctx) {
    const { w, dpr, colors: c, bars } = cache;
    if (ctx.setTransform) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, HEIGHT);
    ctx.fillStyle = c.back;
    ctx.fillRect(0, 0, w, HEIGHT);
    const cut = progress * w;
    for (const r of bars) {
      ctx.fillStyle = r.x + r.w <= cut ? c.played : c.bar;
      ctx.fillRect(r.x, r.y, r.w, r.h);
    }
    if (progress > 0) { ctx.fillStyle = c.cursor; ctx.fillRect(Math.min(w - 2, Math.round(cut)), 0, 2, HEIGHT); }
  }

  function draw({ full = true } = {}) {
    if (destroyed) return;
    const ctx = canvas.getContext && canvas.getContext('2d');
    if (!ctx) return;
    if (full || !cache || (!hasRO && width() !== cache.w)) measure();
    paint(ctx);
  }
  // the observers and `matchMedia` call their callback with an event/entries: always a full redraw
  const redraw = () => draw();

  function setProgress(f) {
    progress = Math.max(0, Math.min(1, Number.isFinite(f) ? f : 0));
    node.setAttribute('aria-valuenow', String(Math.round(progress * 100)));
    if (valueText) node.setAttribute('aria-valuetext', valueText(progress));
    draw({ full: false });
  }
  function setPeaks(next) { peaks = Array.isArray(next) ? next : []; draw(); }

  node.addEventListener('click', (e) => onSeek(fractionAt(e.clientX, node.getBoundingClientRect())));
  node.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const to = e.key === 'ArrowRight' ? progress + 0.05 : e.key === 'ArrowLeft' ? progress - 0.05 : e.key === 'Home' ? 0 : e.key === 'End' ? 1 : null;
    if (to === null) return;
    e.preventDefault(); e.stopPropagation(); // las flechas con el foco aquí mueven la reproducción, no de toma
    onSeek(Math.max(0, Math.min(1, to)));
  });

  // redibujar al cambiar el tamaño o el tema
  const stops = [];
  if (typeof ResizeObserver === 'function') { const ro = new ResizeObserver(redraw); ro.observe(node); stops.push(() => ro.disconnect()); }
  if (typeof MutationObserver === 'function') {
    const mo = new MutationObserver(redraw); mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] }); stops.push(() => mo.disconnect());
  }
  if (typeof matchMedia === 'function') {
    const mq = matchMedia('(prefers-color-scheme: dark)');
    if (mq && mq.addEventListener) { mq.addEventListener('change', redraw); stops.push(() => mq.removeEventListener('change', redraw)); }
  }
  return { node, setPeaks, setProgress, draw: redraw, width, destroy() { destroyed = true; for (const s of stops) s(); } };
}
