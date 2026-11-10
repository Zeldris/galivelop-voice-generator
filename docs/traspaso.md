<!-- galivelop-workflow v0.3.0 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `ccr-60ec66f6-qbtc42` (asignada por la sesión, desde `main` en `195bb86`) |
| **Fase / tarea** | F1 Núcleo (`docs/plan.md`), en marcha. Compactaciones: 0 de 2 presupuestadas |
| **Último punto estable** | F1.3 `orders` (pedidos `voice`/`line`, tomas, elegir/deshacer, desfasadas); antes F1.2 `sheet` y F1.4 `engine`, `limits`, `log` |
| **Siguiente paso** | F1.5 `queue`, `worker` y candado de la máquina (`docs/plan.md` § «F1 en detalle»); el trabajo `prints` al elegir una toma usa `orders.missing_prints`/`set_prints`, el de frase `attempt_specs`/`add_attempt` |
| **Check** | verde (`bash -n` de cada gancho y `unittest`, 246 tests) |

Con `logRows` en `.claude/gw.json`, cada rama escribe solo en su fila de esta tabla, como mucho 600 caracteres, con
la forma ``| **Tarea en curso · `<rama>`** | tarea, qué falta y siguiente paso |``; el push lo comprueba.

## Para la próxima publicación

Nada todavía: el diseño ya está en `main` (PR #2).

## Hecho (5 últimas)

0. 2026-11-10 — F1.3: `gvoice/orders.py` copiado de `gimg@fa1076e` y adaptado (sin perfiles, composición, texto, plantillas, borradores ni entrega) con sus tests. Pedido por proyecto + clave en `orders/<clave>/@/order.json`; tomas en `@/attempts/<id>|q<entrada>/audio.wav` y huellas en `prints/<modelo>.spk|.rvq`. `submit` devuelve los avisos de `sheet` (no se guardan); `line` exige voz `voice` con referencia elegida (`order.voice_unknown`, `order.voice_not_fixed`); cada toma de frase guarda su `reference`; `is_stale`/`stale_lines` calculan las desfasadas; `missing_prints`, `set_prints`, `add_attempt(spec con result=EngineResult)` para el trabajador. `choose` exige audio (`audioMs`). `paths.max_key()` lee el `maxLength` (100) del esquema común y se quita el tope por segmento (inalcanzable).
1. 2026-11-10 — F1.4: `gvoice/{engine,limits,log}.py` copiados de `gimg@fa1076e` con sus tests (`FakeEngine`, `EngineResult` D16, registro `app.voice.*`, límites).
2. 2026-11-10 — F1.2: `gvoice/sheet.py` (`instruction`, `warnings`, `is_adult`) con sus tests; textos `warning.sheet.*` y `error.sheet.invalid`, `machine.*`, `limit.*`, `engine.*`, `log.*` en es/en.
3. 2026-11-10 — F1.1: `gvoice/{errors,paths,fsutil,projects}.py` con sus tests. Variables `GVOICE_CONFIG_HOME`/`GVOICE_DATA_HOME`/`GVOICE_MODELS_HOME`, carpetas `galivelop-voice`, `paths.engine_dir()`; `GvoiceError`; `__version__ = "0.1.0"` en `gvoice/__init__.py`.
4. 2026-10-25 — F0 a `main` por el PR #3, con la confirmación de la persona. CI de GitHub sin arrancar (facturación); los pasos de `comprobar.yml` corrieron en local en un clon limpio, en verde.
4. 2026-10-25 — Arreglos de la revisión de código de F0: check con una orden `bash -n` por gancho; validador ampliado respecto a `gimg` (`$ref` a esquemas hermanos de `gvoice/schemas/`, ciclos y rutas fuera de carpeta como `SchemaError`, `allOf`, `if`/`then`/`else`, `load_schema` con caché y copia); `common.schema.json` y fin de las copias de `$defs`; pedido y pasos de efecto por tipo; `seed` 0-4294967295; D16 (`device` en `voice.json`, huellas y `pack.json`); `prints` y `models[].id` con `baseModel`; `formatVersion` solo en `pack.json`; `watchMemoryMb` obligatorio; `GVOICE_LANG` normalizado y limitado a `locales/`; README sin copias; ejemplos coherentes.

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
