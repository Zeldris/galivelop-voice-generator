/* Copiado de gimg@46248251 (D7); adaptado a gvoice.
   Tema: claro por defecto, u oscuro, o auto (prefers-color-scheme); guardado en el navegador (propuesta.md «Técnica»). */

const KEY = 'gvoice.theme';

export function initTheme(select) {
  let saved = 'light'; // claro por defecto (plan: «Tema claro por defecto»); «auto» sigue siendo una opción
  try { saved = localStorage.getItem(KEY) || 'light'; } catch { /* sin almacenamiento */ }
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
