# Lectora en castellano de España (`locale`)

**Fecha:** 2026-11-17 · **Pedido de ejemplo:** `examples/order-voice-lectora-es.json` (clave `lectora-es`)

## Problema

El motor recibe `language` (`Spanish` por defecto) y la ficha de diseño no distingue castellano peninsular de español
latino: solo el campo libre `accent`, cuya redacción cambia de un pedido a otro. Nada rellenaba `language` desde el
pedido.

## Qué hay ahora

Campo opcional `locale` en los pedidos `voice` (y en `voice.json` del paquete): `es-ES`, `es-419`, `en-US`, `en-GB`.
Un `line` no lo admite: hereda el de su voz (el trabajador lo lee del pedido `voice` en el momento de generar).
`gvoice/speech_locale.py` da, por locale, el `language` del motor y la frase del instruct. La instrucción de la toma
acaba con `Locale: <frase>.` y el trabajo del motor lleva `language`.

Frase de `es-ES`, tal cual:

> Castilian Spanish from Spain, peninsular pronunciation with distinción (θ for z/ce/ci), not Latin American

## Por qué la frase es fija

Debe llegar idéntica a cada toma de cada voz de ese locale. Con texto libre (`accent`) la variante dependería de cómo
la redacte cada autor, y dos voces «de España» no sonarían igual de peninsulares. Va al final del instruct, tras los
campos de la ficha, para no desplazar el orden fijo de estos. Sin `locale` la instrucción y el idioma son los de
siempre.

## Escucha

**Pendiente de la persona.** Las semillas 101-606 ya generadas con la ficha del Portal, sin `locale`, sirven de
referencia. Falta generar las mismas semillas con `lectora-es` y comparar a oído: θ en «hace», «cinco», «zona»,
entonación de la pregunta y limpieza (sin ruido, eco ni siseo). Hasta entonces no se da por probado que la frase
logre la pronunciación peninsular.
