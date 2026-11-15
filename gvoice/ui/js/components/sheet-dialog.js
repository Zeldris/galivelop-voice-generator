/* Nuevo en gvoice (no copiado de gimg) (F5.3). Diálogo «Ficha» de un pedido `voice` (F5.3): GET /api/projects/{p}/orders/{key}/sheet pintado con el mismo panel que
   «Nuevo pedido». Modal, con el patrón de confirm.js: Esc o «Cerrar» lo quitan y el foco vuelve a `opener`. Devuelve el
   `dialog` (para que la vista lo cierre si cambia la ruta) o null si no pudo abrirse. */

import { h } from '../dom.js';
import { t } from '../i18n.js';
import { api, describeError } from '../api.js';
import { sheetPanel } from './sheet-warnings.js';
import { toastError } from './toast.js';

export async function openSheetDialog(project, key, { opener = null, onClose = null, isAlive = () => true } = {}) {
  let res;
  try { res = await api.sheet(project, key); } catch (e) { if (isAlive()) toastError(describeError(e, t)); return null; }
  if (!isAlive()) return null; // la ruta cambió mientras la ficha estaba en vuelo: ni se crea ni se muestra
  const panel = sheetPanel();
  panel.update(res);
  const close = h('button.btn', { type: 'button', onclick: () => dlg.close() }, t('ui.actions.close'));
  const dlg = h('dialog.sheet-dialog', { aria: { labelledby: 'sheet-title' } },
    h('h2', { id: 'sheet-title' }, t('ui.sheet.title'), ' ', h('span.hint', {}, key)), panel.node, h('div.row', {}, close));
  dlg.addEventListener('keydown', (ev) => ev.stopPropagation());
  dlg.addEventListener('close', () => {
    dlg.remove();
    if (onClose) onClose();
    if (opener && opener.isConnected) opener.focus();
  });
  document.body.append(dlg);
  dlg.showModal();
  close.focus();
  return dlg;
}
