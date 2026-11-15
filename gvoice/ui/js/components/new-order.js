/* Copiado de gimg@46248251 (D7); adaptado a gvoice (F5.2): panel «Nuevo pedido», un `dialog` modal.
   - Tipo `voice`: clave, texto de prueba, ficha de diseño (los campos de design-sheet.schema.json más `extra`), semilla
     (vacía = al azar) y nº de tomas. Bajo la ficha, la instrucción y los avisos
     en vivo (F5.3: POST /api/sheet/check con espera de 300 ms; nunca bloquean «Crear» ni rompen el formulario).
   - Tipo `line`: voz (las del `config` del proyecto y los pedidos `voice`), id de la frase (la clave es `<voz>/<id>`),
     texto, semilla y nº de tomas.
   - El cuerpo lo arma y valida ../order-model.js (`buildOrder`, el mismo esquema que el servidor) y se envía con
     POST /api/projects/{p}/orders {order, count}. Un error de la API se muestra dentro del diálogo y en un aviso
     (un `dialog` modal tapa los avisos). */

import { h, replace } from '../dom.js';
import { t } from '../i18n.js';
import { api, describeError } from '../api.js';
import { SHEET_FIELDS, MAX_COUNT, MAX_SEED, buildOrder, ordersOf, sheetFromFields } from '../order-model.js';
import { createSheetChecker } from '../sheet-check.js';
import { sheetPanel } from './sheet-warnings.js';
import * as poll from '../queue-poll.js';
import { toastError, toastOk } from './toast.js';

const SHEET_LABELS = {
  gender: () => t('ui.newOrder.sheet.gender'), age: () => t('ui.newOrder.sheet.age'), pitch: () => t('ui.newOrder.sheet.pitch'),
  speed: () => t('ui.newOrder.sheet.speed'), volume: () => t('ui.newOrder.sheet.volume'), clarity: () => t('ui.newOrder.sheet.clarity'),
  fluency: () => t('ui.newOrder.sheet.fluency'), accent: () => t('ui.newOrder.sheet.accent'), texture: () => t('ui.newOrder.sheet.texture'),
  emotion: () => t('ui.newOrder.sheet.emotion'), tone: () => t('ui.newOrder.sheet.tone'), personality: () => t('ui.newOrder.sheet.personality'),
};

/** Texto de un fallo de validación de `buildOrder` ({field, code, params}). */
function validationText(e) {
  const p = e.params || {};
  if (e.code === 'required') return t('ui.newOrder.error.required', { field: fieldName(e.field) });
  if (e.code === 'key_exists') return t('ui.newOrder.error.keyExists', { field: fieldName(e.field) });
  if (e.code === 'seed_range') return t('ui.newOrder.error.seedRange', { max: p.max, count: p.count });
  if (e.code === 'pattern') return t(e.field === 'key' || e.field === 'voice' ? 'ui.newOrder.error.keyPattern' : 'ui.newOrder.error.segmentPattern', { field: fieldName(e.field) });
  if (e.code === 'too_long') return t('ui.newOrder.error.tooLong', { field: fieldName(e.field), max: p.max });
  if (e.code === 'seed') return t('ui.newOrder.error.seed', { max: p.max });
  if (e.code === 'count') return t('ui.newOrder.error.count', { max: p.max });
  return t('ui.newOrder.error.extra', { line: p.line || '' });
}
const FIELD_NAMES = {
  key: () => t('ui.newOrder.key'), testText: () => t('ui.newOrder.testText'), voice: () => t('ui.newOrder.voice'),
  lineId: () => t('ui.newOrder.lineId'), text: () => t('ui.newOrder.text'), type: () => t('ui.newOrder.type'),
};
const fieldName = (f) => (FIELD_NAMES[f] ? FIELD_NAMES[f]() : f);

/** Abre el panel y devuelve su `dialog` (null si no pudo abrirse). `opener`: el botón que lo abrió (recupera el foco al
    cerrar); `onCreated(res)`: tras crear el pedido; `onClose()`: cuando el panel se cierra y se quita. */
export async function openNewOrder(project, { opener = null, onCreated = null, onClose = null } = {}) {
  let info;
  let allOrders = [];
  try {
    [info, allOrders] = await Promise.all([api.project(project), api.orders(project, {}).catch(() => [])]);
  } catch (e) { toastError(describeError(e, t)); return null; }
  allOrders = ordersOf(allOrders);
  const existingKeys = new Set(allOrders.map((o) => o.key));
  const configVoices = Object.keys((info.config && info.config.voices) || {});
  const chosenOf = new Map(allOrders.filter((o) => o.type === 'voice').map((o) => [o.key, o.chosen !== null && o.chosen !== undefined]));
  const voices = [...new Set([...configVoices, ...chosenOf.keys()])].sort();

  let busy = false;

  const error = h('p.notice.notice-bad', { id: 'no-error', role: 'alert', hidden: true });
  const typeSel = h('select', { id: 'no-type' },
    h('option', { value: 'voice' }, t('ui.project.type.voice')), h('option', { value: 'line' }, t('ui.project.type.line')));
  // voice
  const key = h('input', { id: 'no-key', type: 'text', autocomplete: 'off', spellcheck: 'false', maxlength: 100, aria: { describedby: 'no-key-hint' } });
  const testText = h('textarea', { id: 'no-testtext', rows: 2, maxlength: 1000, spellcheck: 'false' });
  const sheet = Object.fromEntries(SHEET_FIELDS.map((name) => [name, h('input', { id: `no-sheet-${name}`, type: 'text', autocomplete: 'off', spellcheck: 'false' })]));
  const extra = h('textarea', { id: 'no-extra', rows: 2, spellcheck: 'false', placeholder: 'breathing: audible between sentences', aria: { describedby: 'no-extra-hint' } });
  // line
  const voiceLabel = (v) => {
    if (!chosenOf.has(v)) return t('ui.newOrder.voiceNoOrder', { voice: v }); // solo en el `config`: el servidor rechaza la frase
    return chosenOf.get(v) === false ? t('ui.newOrder.voiceUnchosen', { voice: v }) : v;
  };
  const voiceSel = h('select', { id: 'no-voice' }, voices.map((v) => h('option', { value: v }, voiceLabel(v))));
  const lineId = h('input', { id: 'no-lineid', type: 'text', autocomplete: 'off', spellcheck: 'false', maxlength: 100, aria: { describedby: 'no-lineid-hint' } });
  const lineKeyHint = h('span.hint', { id: 'no-lineid-hint' });
  const lineText = h('textarea', { id: 'no-text', rows: 3, maxlength: 4000, spellcheck: 'false' });
  // común
  const seed = h('input', { id: 'no-seed', type: 'number', min: 0, max: MAX_SEED, aria: { describedby: 'no-seed-hint' } });
  const count = h('input', { id: 'no-count', type: 'number', min: 1, max: MAX_COUNT, value: 1 });
  const sendLabel = h('span', {}, t('ui.newOrder.submit'));
  const send = h('button.btn.btn-primary', { type: 'submit' }, sendLabel);
  const cancel = h('button.btn', { type: 'button', onclick: () => dlg.close() }, t('ui.actions.cancel'));

  const panel = sheetPanel();
  const checker = createSheetChecker({
    check: (designSheet) => api.checkSheet(designSheet),
    onResult: (res) => panel.update(res),
    onError: () => panel.fail(t('ui.sheet.checkFailed')), // aviso discreto: el formulario sigue igual
  });
  function checkSheet() {
    const { sheet: designSheet } = sheetFromFields(fields());
    // «extra» a medias: se comprueba la ficha sin esas líneas (`sheetFromFields` las deja fuera); el panel sigue vivo
    checker.request(designSheet);
  }
  const voiceBox = h('div.stack', {},
    h('div.field', {}, h('label', { for: 'no-key' }, t('ui.newOrder.key')), key, h('span.hint', { id: 'no-key-hint' }, t('ui.newOrder.keyHint'))),
    h('div.field', {}, h('label', { for: 'no-testtext' }, t('ui.newOrder.testText')), testText, h('span.hint', {}, t('ui.newOrder.testTextHint'))),
    h('h3', {}, t('ui.newOrder.sheet.title')),
    h('p.hint', {}, t('ui.newOrder.sheet.hint')),
    h('div.cols-2', {}, SHEET_FIELDS.map((name) => h('div.field', {}, h('label', { for: `no-sheet-${name}` }, SHEET_LABELS[name]()), sheet[name]))),
    h('div.field', {}, h('label', { for: 'no-extra' }, t('ui.newOrder.sheet.extra')), extra, h('span.hint', { id: 'no-extra-hint' }, t('ui.newOrder.sheet.extraHint'))),
    panel.node);
  const lineBox = h('div.stack', { hidden: true },
    voices.length
      ? h('div.cols-2', {},
        h('div.field', {}, h('label', { for: 'no-voice' }, t('ui.newOrder.voice')), voiceSel),
        h('div.field', {}, h('label', { for: 'no-lineid' }, t('ui.newOrder.lineId')), lineId, lineKeyHint))
      : h('p.notice.notice-warn', {}, '⚠ ', t('ui.newOrder.noVoices')),
    h('div.field', {}, h('label', { for: 'no-text' }, t('ui.newOrder.text')), lineText));

  const form = h('form.no-form', { novalidate: true, onsubmit: (ev) => { ev.preventDefault(); submit(); } },
    h('div.field', {}, h('label', { for: 'no-type' }, t('ui.newOrder.type')), typeSel),
    voiceBox, lineBox,
    h('div.cols-2', {},
      h('div.field', {}, h('label', { for: 'no-seed' }, t('ui.newOrder.seed')), seed, h('span.hint', { id: 'no-seed-hint' }, t('ui.newOrder.seedHint'))),
      h('div.field', {}, h('label', { for: 'no-count' }, t('ui.newOrder.count')), count)),
    error,
    h('div.row', {}, send, cancel));

  const dlg = h('dialog.new-order', { aria: { labelledby: 'no-title' } },
    h('h2', { id: 'no-title' }, t('ui.newOrder.title'), ' ', h('span.hint', {}, project)), form);

  function onType() {
    const line = typeSel.value === 'line';
    voiceBox.hidden = line;
    lineBox.hidden = !line;
    showKey();
  }
  function showKey() { lineKeyHint.textContent = t('ui.newOrder.lineKey', { key: `${voiceSel.value || '…'}/${lineId.value.trim() || '…'}` }); }
  typeSel.addEventListener('change', onType);
  voiceSel.addEventListener('change', showKey);
  lineId.addEventListener('input', showKey);
  showKey();
  for (const input of [...Object.values(sheet), extra]) input.addEventListener('input', checkSheet);
  checkSheet(); // ficha vacía: ya avisa de la edad que falta

  function fields() {
    return {
      type: typeSel.value, key: key.value, testText: testText.value, extra: extra.value,
      sheet: Object.fromEntries(SHEET_FIELDS.map((name) => [name, sheet[name].value])),
      voice: voiceSel.value, lineId: lineId.value, text: lineText.value, seed: seed.value, count: count.value,
      seedBad: seed.validity.badInput, countBad: count.validity.badInput, // texto que no es un número: el valor sale ''
    };
  }
  const focusOf = { key, testText, extra, voice: voiceSel, lineId, text: lineText, seed, count };

  function showError(message, focusOn) {
    toastError(message);
    replace(error, '✗ ', message);
    error.hidden = false;
    if (focusOn) focusOn.focus();
  }
  function setBusy(v) {
    busy = v;
    send.disabled = v;
    replace(sendLabel, v ? t('ui.newOrder.sending') : t('ui.newOrder.submit'));
  }

  async function submit() {
    if (busy) return;
    error.hidden = true;
    const { body, errors } = buildOrder(fields(), existingKeys);
    if (!body) {
      showError(errors.map(validationText).join(' '), focusOf[errors[0].field]);
      return;
    }
    setBusy(true);
    let res;
    try { res = await api.newOrder(project, body.order, body.count); } catch (e) { setBusy(false); showError(describeError(e, t)); return; }
    const n = res && Array.isArray(res.entries) ? res.entries.length : body.count;
    toastOk(t('ui.newOrder.created', { key: body.order.key, n }));
    poll.refreshNow();
    dlg.close();
    if (onCreated) onCreated(res);
  }

  dlg.addEventListener('keydown', (ev) => ev.stopPropagation()); // los atajos globales no actúan con el panel abierto
  dlg.addEventListener('close', () => {
    checker.cancel();
    dlg.remove();
    if (onClose) onClose();
    if (opener && opener.isConnected) opener.focus();
  });
  document.body.append(dlg);
  dlg.showModal();
  key.focus();
  return dlg;
}
