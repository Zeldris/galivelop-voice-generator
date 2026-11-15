/* Copiado de gimg@46248251 (D7); adaptado a gvoice.
   Tema: auto (prefers-color-scheme), claro u oscuro; guardado en el navegador (propuesta.md «Técnica»). */

const KEY = 'gvoice.theme';

export function initTheme(select) {
  let saved = 'auto';
  try { saved = localStorage.getItem(KEY) || 'auto'; } catch { /* sin almacenamiento */ }
  apply(saved);
  select.value = saved;
  select.addEventListener('change', () => {
    apply(select.value);
    try { localStorage.setItem(KEY, select.value); } catch { /* sin almacenamiento */ }
  });
}

function apply(mode) {
  if (mode === 'light' || mode === 'dark') document.documentElement.dataset.theme = mode;
  else delete document.documentElement.dataset.theme;
}
