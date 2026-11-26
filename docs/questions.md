# Questions

Questions for the user, one entry each; `python3 .claude/gw/scripts/questions.py` reads and rewrites this
file (format: header of scripts/questions.py). Answer by number: `questions.py answer "5. a, 6. ok"`.

## Q-1
- Refs: 0.3.0
- Status: answered
- Asked: 2026-11-25
- Question: ¿Cómo entra la muestra peninsular en un pedido voice?
- Recommendation: Sí: campo opcional `sample` en el pedido voice ({audio, text, source, license}), excluyente con `designSheet`. La muestra entra como una toma más (con `source: sample`), así elegir, fijar (huellas Base), frases y desfasadas funcionan sin cambios; las tomas clonadas del testText con Base sirven para comparar
- Answer: ok
- Answered: 2026-11-25

## Q-2
- Refs: 0.3.0
- Status: answered
- Asked: 2026-11-25
- Question: ¿De dónde sale la muestra peninsular de referencia?
- Recommendation: Una muestra que grabes tú (o alguien con permiso escrito) de 10-15 s, limpia; Common Voice es-ES (CC0) como reserva. El pedido guarda origen y licencia
- Answer: ok
- Answered: 2026-11-25

## Q-3
- Refs: 0.3.0
- Status: answered
- Asked: 2026-11-25
- Question: ¿Qué motor se integra en 0.3.0?
- Recommendation: Primero solo Qwen3 Base (ya integrado) con la muestra; Chatterbox como motor enchufable solo si en la Deck suena claramente más peninsular. Dejo preparada la orden del banco para comparar a oído
- Answer: ok
- Answered: 2026-11-25

## Q-4
- Refs: 0.3.0
- Status: answered
- Asked: 2026-11-25
- Question: ¿El pedido del Portal (7 trozos) se entrega con la lectora-es actual, sin esperar a la vía 1?
- Recommendation: Sí: los 7 trozos del Portal se generan ya con la lectora-es actual (vía 2, la de los audios aprobados) en la Deck; no esperan a la vía 1
- Answer: ok
- Answered: 2026-11-25

## Q-5
- Refs: 0.3.1
- Status: answered
- Asked: 2026-11-25
- Question: ¿Se puede corregir la transcripción de una muestra ya registrada sin cambiar el audio?
- Recommendation: No: con el mismo audio el texto de la toma no cambia (las huellas casan con su texto); para corregirla se envía otro audio, aunque sea un recorte
- Answer: ok
- Answered: 2026-11-25

## Q-6
- Refs: 0.3.1
- Status: answered
- Asked: 2026-11-25
- Question: ¿Se limita la duración o el formato de la muestra (p. ej. 3-30 s, frecuencia mínima)?
- Recommendation: No limitar todavía (hoy: cualquier WAV PCM con sonido hasta 64 MB); se decide tras oír en la Deck (0.3.3) qué pide Qwen3 Base
- Answer: ok
- Answered: 2026-11-25

## Q-7
- Refs: 0.4.0
- Status: open
- Asked: 2026-11-26
- Question: ¿Dónde se fijan los parámetros de muestreo y qué se guarda en cada toma?
- Recommendation: Objeto opcional `sampling` (temperature, topK, topP, repetitionPenalty, greedy y los sub-* del sub-talker) en el pedido voice y line, con valores por defecto en la configuración del proyecto y, si faltan, los del checkpoint (0,9 / 50 / 1,0 / 1,05) en el catálogo del motor; al motor se le pasan siempre explícitos y la toma guarda los efectivos

## Q-8
- Refs: 0.4.0
- Status: open
- Asked: 2026-11-26
- Question: ¿Qué «pruebas sin oído» automáticas lleva cada toma?
- Recommendation: Sí, cada toma, al generarse, con la biblioteca estándar: segundos por carácter fuera de rango (bucles o cortes), silencio interno más largo que X, recorte (clipping), nivel muy bajo y silencio final largo; son avisos en la toma, no bloquean; umbrales en la configuración del proyecto. Más una orden `gvoice take replay` que regenera con los mismos parámetros y compara el sha256 (reproducibilidad, E8)

## Q-9
- Refs: 0.4.0
- Status: open
- Asked: 2026-11-26
- Question: ¿Cómo es la ficha de escucha?
- Recommendation: Lista de criterios por proyecto con los 5 de la investigación por defecto ((a) θ en hace/cinco/zona, (b) sin acento inglés ni seseo, (c) sin ruido, eco, siseo ni deriva infantil, (d) tono y entonación, (e) estabilidad); cada uno sí/no/sin oír y una nota por toma; marcar «no» en uno eliminatorio avisa al elegir la toma, no lo impide; se rellena en la interfaz y con `gvoice take rate`

## Q-10
- Refs: 0.4.0
- Status: open
- Asked: 2026-11-26
- Question: ¿Se parte 0.4.0 en estos pasos?
- Recommendation: 0.4.1 muestreo (esquema, motor, toma), 0.4.2 pruebas sin oído, 0.4.3 ficha de escucha (núcleo y CLI), 0.4.4 interfaz (muestreo en el diálogo, avisos y ficha en la toma), 0.4.5 en la Deck (persona): E1-E8 y cierre de F2.6
