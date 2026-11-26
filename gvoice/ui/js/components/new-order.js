/* Copiado de gimg@46248251 (D7); adaptado a gvoice (F5.2): panel «Nuevo pedido», un `dialog` modal.
   - Tipo `voice`: clave, texto de prueba, ficha de diseño (los campos de design-sheet.schema.json más `extra`), semilla
     (vacía = al azar) y nº de tomas. Bajo la ficha, la instrucción y los avisos
     en vivo (F5.3: POST /api/sheet/check con espera de 300 ms; nunca bloquean «Crear» ni rompen el formulario).
   - Tipo `voice` con origen «Muestra» (0.3.2): ruta del WAV en la máquina del servidor, transcripción, origen, licencia
     y variante (`locale`, es-ES por defecto); sin ficha, frase de prueba, semilla ni número de tomas.
   - Tipo `line`: voz (las del `config` del proyecto y los pedidos `voice`), id de la frase (la clave es `<voz>/<id>`),
     texto, semilla y nº de tomas.
   - Muestreo (0.4.4, solo `voice` de ficha y `line`): campos opcionales de `sampling` (temperatura, top-k, top-p,
     penalización, voraz y los tres del sub-talker) en un `details`; vacío = no se envía (el núcleo rellena por proyecto y
     checkpoint).
   - El cuerpo lo arma y valida ../order-model.js (`buildOrder`, el mismo esquema que el servidor) y se envía con
     POST /api/projects/{p}/orders {order, count}. Un error de la API se muestra dentro del diálogo y en un aviso
     (un `dialog` modal tapa los avisos). */

import { h, replace } from '../dom.js';
import { t } from '../i18n.js';
import { api, describeError } from '../api.js';
import { SHEET_FIELDS, SAMPLING_FIELDS, SAMPLING_RANGES, SUB_TALKER_FIELDS, MAX_COUNT, MAX_SEED, MAX_SAMPLE_TEXT, MAX_SAMPLE_SOURCE, MAX_SAMPLE_LICENSE, LOCALES, DEFAULT_LOCALE, buildOrder, ordersOf, sheetFromFields } from '../order-model.js';
import { createSheetChecker } from '../sheet-check.js';
import { busy } from '../async-guard.js';
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
  if (e.code === 'locale') return t('ui.newOrder.error.locale', { locales: p.locales });
  if (e.code === 'absolute') return t('ui.newOrder.error.absolute', { field: fieldName(e.field) });
  if (e.code === 'number') return t('ui.newOrder.error.samplingNumber', { field: fieldName(e.field) });
  if (e.code === 'integer') return t('ui.newOrder.error.samplingInteger', { field: fieldName(e.field) });
  if (e.code === 'range') return t(p.exclusive ? 'ui.newOrder.error.samplingRangeAbove' : 'ui.newOrder.error.samplingRange', { field: fieldName(e.field), min: p.min, max: p.max });
  if (e.code === 'count') return t('ui.newOrder.error.count', { max: p.max });
  return t('ui.newOrder.error.extra', { line: p.line || '' });
}
const FIELD_NAMES = {
  key: () => t('ui.newOrder.key'), testText: () => t('ui.newOrder.testText'), voice: () => t('ui.newOrder.voice'),
  lineId: () => t('ui.newOrder.lineId'), locale: () => t('ui.newOrder.locale'), sampleAudio: () => t('ui.newOrder.sample.audio'),
  sampleText: () => t('ui.newOrder.sample.text'), sampleSource: () => t('ui.newOrder.sample.source'), sampleLicense: () => t('ui.newOrder.sample.license'), text: () => t('ui.newOrder.text'), type: () => t('ui.newOrder.type'),
};
/** `sampling.topK` / `sampling.subTalker.topK` → el nombre del campo de muestreo (el del sub-talker, con su prefijo). */
function samplingName(f) {
  const m = /^sampling\.(subTalker\.)?(\w+)$/.exec(f);
  if (!m) return null;
  return (m[1] ? `${t('ui.newOrder.sampling.sub')}: ` : '') + t(`ui.newOrder.sampling.${m[2]}`);
}
const fieldName = (f) => (FIELD_NAMES[f] ? FIELD_NAMES[f]() : samplingName(f) || f);

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

  const error = h('p.notice.notice-bad', { id: 'no-error', role: 'alert', hidden: true });
  const typeSel = h('select', { id: 'no-type' },
    h('option', { value: 'voice' }, t('ui.project.type.voice')), h('option', { value: 'line' }, t('ui.project.type.line')));
  const originSel = h('select', { id: 'no-origin' },
    h('option', { value: 'sheet' }, t('ui.newOrder.originSheet')), h('option', { value: 'sample' }, t('ui.newOrder.originSample')));
  // voice
  const key = h('input', { id: 'no-key', type: 'text', autocomplete: 'off', spellcheck: 'false', maxlength: 100, aria: { describedby: 'no-key-hint' } });
  const testText = h('textarea', { id: 'no-testtext', rows: 2, maxlength: 1000, spellcheck: 'false' });
  const sheet = Object.fromEntries(SHEET_FIELDS.map((name) => [name, h('input', { id: `no-sheet-${name}`, type: 'text', autocomplete: 'off', spellcheck: 'false' })]));
  const extra = h('textarea', { id: 'no-extra', rows: 2, spellcheck: 'false', placeholder: 'breathing: audible between sentences', aria: { describedby: 'no-extra-hint' } });
  // voice, muestra
  const sampleAudio = h('input', { id: 'no-sample-audio', type: 'text', autocomplete: 'off', spellcheck: 'false', aria: { describedby: 'no-sample-audio-hint' } });
  const sampleText = h('textarea', { id: 'no-sample-text', rows: 3, maxlength: MAX_SAMPLE_TEXT, spellcheck: 'false' });
  const sampleSource = h('input', { id: 'no-sample-source', type: 'text', autocomplete: 'off', maxlength: MAX_SAMPLE_SOURCE });
  const sampleLicense = h('input', { id: 'no-sample-license', type: 'text', autocomplete: 'off', maxlength: MAX_SAMPLE_LICENSE });
  const locale = h('select', { id: 'no-locale' }, LOCALES.map((l) => h('option', { value: l }, t(`ui.newOrder.locale.${l}`))));
  locale.value = DEFAULT_LOCALE;
  // line
  const voiceLabel = (v) => {
    if (!chosenOf.has(v)) return t('ui.newOrder.voiceNoOrder', { voice: v }); // solo en el `config`: el servidor rechaza la frase
    return chosenOf.get(v) === false ? t('ui.newOrder.voiceUnchosen', { voice: v }) : v;
  };
  const voiceSel = h('select', { id: 'no-voice' }, voices.map((v) => h('option', { value: v }, voiceLabel(v))));
  const lineId = h('input', { id: 'no-lineid', type: 'text', autocomplete: 'off', spellcheck: 'false', maxlength: 100, aria: { describedby: 'no-lineid-hint' } });
  const lineKeyHint = h('span.hint', { id: 'no-lineid-hint' });
  const lineText = h('textarea', { id: 'no-text', rows: 3, maxlength: 4000, spellcheck: 'false' });
  // muestreo (voice de ficha y line): texto libre, con coma decimal; vacío = no se envía
  const samplingInput = (id) => h('input', { id: `no-sampling-${id}`, type: 'text', inputmode: 'decimal', autocomplete: 'off', spellcheck: 'false' });
  const sampling = Object.fromEntries(SAMPLING_FIELDS.map((name) => [name, samplingInput(name)]));
  const subSampling = Object.fromEntries(SUB_TALKER_FIELDS.map((name) => [name, samplingInput(`sub-${name}`)]));
  const greedy = h('select', { id: 'no-sampling-greedy' },
    h('option', { value: '' }, t('ui.newOrder.sampling.greedy.default')),
    h('option', { value: 'true' }, t('ui.newOrder.sampling.greedy.on')), h('option', { value: 'false' }, t('ui.newOrder.sampling.greedy.off')));
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
    if (isSample()) return;
    const { sheet: designSheet } = sheetFromFields(fields());
    // «extra» a medias: se comprueba la ficha sin esas líneas (`sheetFromFields` las deja fuera); el panel sigue vivo
    checker.request(designSheet);
  }
  const originField = h('div.field', {}, h('label', { for: 'no-origin' }, t('ui.newOrder.origin')), originSel);
  const designBox = h('div.stack', { id: 'no-design' },
    h('div.field', {}, h('label', { for: 'no-testtext' }, t('ui.newOrder.testText')), testText, h('span.hint', {}, t('ui.newOrder.testTextHint'))),
    h('h3', {}, t('ui.newOrder.sheet.title')),
    h('p.hint', {}, t('ui.newOrder.sheet.hint')),
    h('div.cols-2', {}, SHEET_FIELDS.map((name) => h('div.field', {}, h('label', { for: `no-sheet-${name}` }, SHEET_LABELS[name]()), sheet[name]))),
    h('div.field', {}, h('label', { for: 'no-extra' }, t('ui.newOrder.sheet.extra')), extra, h('span.hint', { id: 'no-extra-hint' }, t('ui.newOrder.sheet.extraHint'))),
    panel.node);
  const sampleBox = h('div.stack', { id: 'no-sample', hidden: true },
    h('p.hint', {}, t('ui.newOrder.sample.hint')),
    h('div.field', {}, h('label', { for: 'no-sample-audio' }, t('ui.newOrder.sample.audio')), sampleAudio, h('span.hint', { id: 'no-sample-audio-hint' }, t('ui.newOrder.sample.audioHint'))),
    h('div.field', {}, h('label', { for: 'no-sample-text' }, t('ui.newOrder.sample.text')), sampleText, h('span.hint', {}, t('ui.newOrder.sample.textHint'))),
    h('div.cols-2', {},
      h('div.field', {}, h('label', { for: 'no-sample-source' }, t('ui.newOrder.sample.source')), sampleSource, h('span.hint', {}, t('ui.newOrder.sample.sourceHint'))),
      h('div.field', {}, h('label', { for: 'no-sample-license' }, t('ui.newOrder.sample.license')), sampleLicense, h('span.hint', {}, t('ui.newOrder.sample.licenseHint')))),
    h('div.field', {}, h('label', { for: 'no-locale' }, t('ui.newOrder.locale')), locale, h('span.hint', {}, t('ui.newOrder.localeHint'))));
  const voiceBox = h('div.stack', {},
    originField,
    h('div.field', {}, h('label', { for: 'no-key' }, t('ui.newOrder.key')), key, h('span.hint', { id: 'no-key-hint' }, t('ui.newOrder.keyHint'))),
    designBox, sampleBox);
  const lineBox = h('div.stack', { hidden: true },
    voices.length
      ? h('div.cols-2', {},
        h('div.field', {}, h('label', { for: 'no-voice' }, t('ui.newOrder.voice')), voiceSel),
        h('div.field', {}, h('label', { for: 'no-lineid' }, t('ui.newOrder.lineId')), lineId, lineKeyHint))
      : h('p.notice.notice-warn', {}, '⚠ ', t('ui.newOrder.noVoices')),
    h('div.field', {}, h('label', { for: 'no-text' }, t('ui.newOrder.text')), lineText));

  const rangeHint = (name) => { const r = SAMPLING_RANGES[name]; return t(r.exclusive ? 'ui.newOrder.sampling.rangeAbove' : 'ui.newOrder.sampling.range', { min: r.min, max: r.max }); };
  const samplingField = (name, input, id) => h('div.field', {}, h('label', { for: id }, t(`ui.newOrder.sampling.${name}`)), input, h('span.hint', {}, rangeHint(name)));
  const samplingBox = h('details.sampling', { id: 'no-sampling' },
    h('summary', {}, t('ui.newOrder.sampling.title')),
    h('div.stack', {},
      h('p.hint', {}, t('ui.newOrder.sampling.hint')),
      h('div.cols-2', {}, SAMPLING_FIELDS.map((name) => samplingField(name, sampling[name], `no-sampling-${name}`))),
      h('div.field', {}, h('label', { for: 'no-sampling-greedy' }, t('ui.newOrder.sampling.greedy')), greedy),
      h('h4', {}, t('ui.newOrder.sampling.sub')),
      h('div.cols-2', {}, SUB_TALKER_FIELDS.map((name) => samplingField(name, subSampling[name], `no-sampling-sub-${name}`)))));
  const commonBox = h('div.cols-2', { id: 'no-common' },
    h('div.field', {}, h('label', { for: 'no-seed' }, t('ui.newOrder.seed')), seed, h('span.hint', { id: 'no-seed-hint' }, t('ui.newOrder.seedHint'))),
    h('div.field', {}, h('label', { for: 'no-count' }, t('ui.newOrder.count')), count));
  const form = h('form.no-form', { novalidate: true, onsubmit: (ev) => { ev.preventDefault(); submit(); } },
    h('div.field', {}, h('label', { for: 'no-type' }, t('ui.newOrder.type')), typeSel),
    voiceBox, lineBox,
    commonBox, samplingBox,
    error,
    h('div.row', {}, send, cancel));

  const dlg = h('dialog.new-order', { aria: { labelledby: 'no-title' } },
    h('h2', { id: 'no-title' }, t('ui.newOrder.title'), ' ', h('span.hint', {}, project)), form);

  function onType() {
    const line = typeSel.value === 'line';
    voiceBox.hidden = line;
    lineBox.hidden = !line;
    onOrigin();
    showKey();
  }
  const isSample = () => typeSel.value === 'voice' && originSel.value === 'sample';
  function onOrigin() {   // una voz de muestra no lleva ficha, frase de prueba, semilla ni tomas
    designBox.hidden = isSample();
    sampleBox.hidden = !isSample();
    commonBox.hidden = isSample();
    samplingBox.hidden = isSample();   // la muestra no se sintetiza: sin muestreo
  }
  originSel.addEventListener('change', () => { onOrigin(); if (!isSample()) checkSheet(); });
  function showKey() { lineKeyHint.textContent = t('ui.newOrder.lineKey', { key: `${voiceSel.value || '…'}/${lineId.value.trim() || '…'}` }); }
  typeSel.addEventListener('change', onType);
  voiceSel.addEventListener('change', showKey);
  lineId.addEventListener('input', showKey);
  showKey();
  for (const input of [...Object.values(sheet), extra]) input.addEventListener('input', checkSheet);
  checkSheet(); // ficha vacía: ya avisa de la edad que falta

  function fields() {
    return {
      type: typeSel.value, origin: originSel.value, key: key.value,
      locale: locale.value, sampleAudio: sampleAudio.value, sampleText: sampleText.value, sampleSource: sampleSource.value, sampleLicense: sampleLicense.value, testText: testText.value, extra: extra.value,
      sheet: Object.fromEntries(SHEET_FIELDS.map((name) => [name, sheet[name].value])),
      sampling: { ...Object.fromEntries(SAMPLING_FIELDS.map((name) => [name, sampling[name].value])), greedy: greedy.value,
        sub: Object.fromEntries(SUB_TALKER_FIELDS.map((name) => [name, subSampling[name].value])) },
      voice: voiceSel.value, lineId: lineId.value, text: lineText.value, seed: seed.value, count: count.value,
      seedBad: seed.validity.badInput, countBad: count.validity.badInput, // texto que no es un número: el valor sale ''
    };
  }
  const focusOf = { key, locale, sampleAudio, sampleText, sampleSource, sampleLicense, testText, extra, voice: voiceSel, lineId, text: lineText, seed, count,
    ...Object.fromEntries(SAMPLING_FIELDS.map((name) => [`sampling.${name}`, sampling[name]])),
    ...Object.fromEntries(SUB_TALKER_FIELDS.map((name) => [`sampling.subTalker.${name}`, subSampling[name]])) };

  function showError(message, focusOn) {
    toastError(message);
    replace(error, '✗ ', message);
    error.hidden = false;
    if (focusOn) focusOn.focus();
  }
  function setBusy(v) {
    send.disabled = v;
    replace(sendLabel, v ? t('ui.newOrder.sending') : t('ui.newOrder.submit'));
  }

  // un solo envío a la vez (doble clic o Intro repetido); la bandera se repone con `finally` y el botón la sigue
  const submit = busy(async () => {
    error.hidden = true;
    const { body, errors } = buildOrder(fields(), existingKeys);
    if (!body) {
      if (errors.some((e) => e.field.startsWith('sampling.'))) samplingBox.open = true;   // el campo mal escrito tiene que verse
      showError(errors.map(validationText).join(' '), focusOf[errors[0].field]);
      return;
    }
    let res;
    try { res = await api.newOrder(project, body.order, body.count); } catch (e) { showError(describeError(e, t)); return; }
    const n = res && Array.isArray(res.entries) ? res.entries.length : body.count;
    toastOk(body.order.sample ? t('ui.newOrder.createdSample', { key: body.order.key }) : t('ui.newOrder.created', { key: body.order.key, n }));
    poll.refreshNow();
    dlg.close();
    if (onCreated) onCreated(res);
  }, { onChange: setBusy });

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
