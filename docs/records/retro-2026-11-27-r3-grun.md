# Retro R3 — adoptar `grun` (2026-11-27)

**Estado:** pendiente de presentar a la persona; P1 y P2 ya cuentan con su visto bueno de la medición de `gw-opt-tokens`, falta su decisión sobre P3 y P4.

Fuentes: `measure.py` sobre la sesión `15c9eb88` (10 llamadas en la principal, 39 en subagentes), `pending.md`,
diff de la rama contra `origin/main` (52 archivos, +3443/−810) y las skills usadas (`gw-orchestrate-dealer`,
`gw-reviewer`, `gw-worker`).

## Qué fue bien

- La principal se quedó en 94k de contexto medio, sin compactaciones: el reparto a subagentes funcionó.
- Los arreglos de la revisión de bloque (13 llamadas, 435k) fueron a `gw-worker` y no a la principal.
- Ninguna desviación del guardián de alcance que repetir.

## Propuestas

### P1 — Revisión de bloque sin anidar en diffs pequeños (general: al flujo)

La revisión de bloque de R3 costó 2,5M de entrada, 26 llamadas a 97k de contexto medio: el `gw-reviewer` abre un
`/code-review` anidado. Segunda medición tras la de F5.9 (0,93M de 1,03M), ya rechazada una vez sin cifras
repetidas. Propuesta: `gw-reviewer` revisa directamente por debajo de `changeSize.block` líneas y anida solo por
encima o en ganchos, guardas y seguridad.
**Riesgo de calidad:** una pasada menos puede dejar pasar un hallazgo; contrapeso: el umbral y la excepción de
ganchos y seguridad, y contar los hallazgos de la fase 1 antes de `main`.
**Salida:** `## For Galivelop-workflow` (abajo); no se parchea aquí.

### P2 — Registrar la cifra de R3 en las notas del proyecto (específica)

`.claude/gw/gw-opt-tokens.md`: línea en «Costes conocidos» y en «Referencias medidas». Coste: dos líneas.

### P3 — Barrido de leves de R3 (específica)

Tres leves abiertos de la revisión de bloque de R3 en `pending.md`; dos tocan `gvoice/worker.py` (carga del
perfil antes del candado; alias `GVOICE_MEMINFO`/`GVOICE_PROC_STATUS`) y uno la validación de `KINDS` en la cola
(`gvoice/queue.py`, `tests/test_queue.py`). Propuesta: una tarea de un solo commit que los cierre los tres, para la
siguiente versión no empezada. Id: la forma de `taskId` es `[A-Z]{2,5}-\d+`, pero `handoff.py next-id` no lee
ids porque `plan` no está en `gw.json`; la persona o el siguiente relevo lo asigna al abrirla.
Ningún otro script reúne dos o más leves abiertos.

### P4 — `pending.md` creció a 23 entradas (específica)

Muchas son «leves de la revisión de F…» de bloques ya fusionados. Propuesta: al abrir P3, cerrar de paso los que
ya no aplican. Sin cambio de reglas.

## For Galivelop-workflow

- **gw-reviewer / code-review:** revisar sin anidar cuando el diff sea menor que `changeSize.block` líneas; la
  medición de R3 (2,5M en 26 llamadas a 97k) y la de F5.9 (0,93M de 1,03M) apoyan el cambio.
