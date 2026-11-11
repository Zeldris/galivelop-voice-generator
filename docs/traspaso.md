<!-- galivelop-workflow v0.3.0 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `ccr-60ec66f6-qbtc42` (asignada por la sesión, desde `main` en `195bb86`) |
| **Fase / tarea** | F1 Núcleo (`docs/plan.md`) completa; falta su revisión antes de `main`. Compactaciones: 0 de 2 presupuestadas |
| **Último punto estable** | F1 completa: F1.6 `cli` y prueba de extremo a extremo; antes F1.5 `queue`/`worker`, F1.3 `orders`, F1.4 `engine`/`limits`/`log`, F1.2 `sheet` |
| **Siguiente paso** | Revisión de F1 antes de `main`, fase 1 de `AGENTS.md`: `git fetch origin main` y `/code-review --max-findings all` del diff contra `origin/main` con el criterio de `REVIEW.md`; luego fases 2 y 3 |
| **Check** | verde (`bash -n` de cada gancho y `unittest`) |

Con `logRows` en `.claude/gw.json`, cada rama escribe solo en su fila de esta tabla, como mucho 600 caracteres, con
la forma ``| **Tarea en curso · `<rama>`** | tarea, qué falta y siguiente paso |``; el push lo comprueba.

## Para la próxima publicación

Nada todavía: el diseño ya está en `main` (PR #2).

## Hecho (5 últimas)

0. 2026-11-11 — F1.6: `gvoice/cli.py` y `__main__.py` (`python3 -m gvoice`) copiados de `gimg@fa1076e` y adaptados: `project add|list|remove`, `order submit|list|show`, `attempt new|mark|note`, `choose`, `undo`, `queue list|cancel`, `work`, `version`; `--json` y `--lang`; códigos de salida 0/1/2/130. `order submit` muestra los avisos de la ficha; `order list|show` marcan las frases desfasadas (`stale` en las líneas y `staleLines` en las voces, en `--json`). Textos `cli.*` en es/en. `tests/test_cli.py` y `tests/test_e2e.py` (ciclo completo con las huellas de cada `printModels`, desfasada y deshacer). README es/en con el uso. Sin `doctor`, `serve`, `ui` ni estimado (F2-F5).
1. 2026-11-11 — F1.5: `gvoice/{queue,worker,machine_lock}.py` copiados de `gimg@fa1076e` y adaptados, con sus tests. Cola con tres clases de trabajo (`voice`: `design` con la instrucción; `line`: `line` con la huella del modelo de producción, el primero de `models.produce` del perfil, que debe estar en `printModels`, si no `queue.model_not_printed`, y si falta el archivo `worker.print_missing`; `prints`: una huella por modelo de `orders.missing_prints`). `queue.submit_order/new_takes/choose/undo` envuelven `orders` y encolan `prints` solo si a la toma le faltan huellas (sin duplicar uno en cola o en curso). Candado de la máquina `paths.machine_lock_path()` = `<state>/gpu.lock` (`GVOICE_STATE_HOME`, `$XDG_STATE_HOME/galivelop`, `~/.local/state/galivelop`): `flock` exclusivo durante todo el trabajo, sondeado cada 50 ms (ocupado = espera, cancelable, nunca falla); lo suelta el núcleo si el proceso muere. Cada trabajo escribe su línea D16 (`voice_design`, `speech_generation`, `voice_print`).
2. 2026-11-10 — F1.3: `gvoice/orders.py` copiado de `gimg@fa1076e` y adaptado (sin perfiles, composición, texto, plantillas, borradores ni entrega) con sus tests. Pedido por proyecto + clave en `orders/<clave>/@/order.json`; tomas en `@/attempts/<id>|q<entrada>/audio.wav` y huellas en `prints/<modelo>.spk|.rvq`. `submit` devuelve los avisos de `sheet` (no se guardan); `line` exige voz `voice` con referencia elegida (`order.voice_unknown`, `order.voice_not_fixed`); cada toma de frase guarda su `reference`; `is_stale`/`stale_lines` calculan las desfasadas; `missing_prints`, `set_prints`, `add_attempt(spec con result=EngineResult)` para el trabajador. `choose` exige audio (`audioMs`). `paths.max_key()` lee el `maxLength` (100) del esquema común y se quita el tope por segmento (inalcanzable).
3. 2026-11-10 — F1.4: `gvoice/{engine,limits,log}.py` copiados de `gimg@fa1076e` con sus tests (`FakeEngine`, `EngineResult` D16, registro `app.voice.*`, límites).
4. 2026-11-10 — F1.2: `gvoice/sheet.py` (`instruction`, `warnings`, `is_adult`) con sus tests; textos `warning.sheet.*` y `error.sheet.invalid`, `machine.*`, `limit.*`, `engine.*`, `log.*` en es/en.

## Pendiente

- Hallazgos leves de la revisión de F0, sin arreglar en este PR: el mensaje de `propertyNames` sale con «()» vacío cuando el motivo no es un `pattern` (p. ej. un `enum`) y solo cuenta el primer motivo (`gvoice/schema.py`); `i18n.t()` lanza `KeyError` si a un idioma le falta un parámetro del texto y no mira `LANGUAGE`; los commits `81d76f1` y `7cebd24` de F0 tienen `Siguiente:` separado de la atribución por una línea en blanco.
- Escucha del banco y registro del núcleo tras Vulkan: los dos, de la persona (ver «Pendiente» en `docs/plan.md`).
- Para la persona, en `galivelop-image-generator`: su check `bash -n a b c` solo comprueba `a` (R3 de la retro de F0).
- Para proponer al flujo: R2-R3 de `docs/registros/retro-2026-10-25-f0.md`, R2-R4 de `docs/registros/retro-2026-10-25-diseno-voces.md`, y las aplazadas de la retro anterior: rama por defecto del flujo en 0.1.0; camino para CI
  agotado (`ci-local.sh`); 2 tests de `scout-updates` fallan fuera del flujo; `gw-init` debe decir que no se llame a
  `register_repo_root`.

## Comprobar el estado

- Últimos commits: `git fetch origin <rama> && git log --oneline -5 origin/<rama>`.
- El check: `bash -n .githooks/pre-commit && bash -n .githooks/pre-push && python3 -m unittest discover -s tests -t .`.
- Flujo bien montado: `python3 .claude/gw/scripts/doctor.py`.
- Estado de la bitácora tal como lo recibe una sesión nueva: `python3 .claude/gw/scripts/recuperar.py --estado`.
