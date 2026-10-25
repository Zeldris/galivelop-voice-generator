<!-- galivelop-workflow v0.3.0 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `claude/voces-f1` |
| **Fase / tarea** | F1 Núcleo (`docs/plan.md`, «F1 en detalle», pasos F1.1-F1.6). Compactaciones: 0 de 1 presupuestada |
| **Último punto estable** | F1.2 (`orders` con `voice` y `line`, `model` y `count` en el esquema de pedido, `sheet` con `build_instruct` y `warnings`; 192 tests). Antes, F1.1 (`paths`, `fsutil`, `errors`, `projects` con `print_models`) |
| **Siguiente paso** | F1.3: `engine` (`FakeEngine`), `machine`, `machinelock` y `log` |
| **Check** | verde (`bash -n` de cada gancho y `unittest`, 192 tests) |

Con `logRows` en `.claude/gw.json`, cada rama escribe solo en su fila de esta tabla, como mucho 600 caracteres, con
la forma ``| **Tarea en curso · `<rama>`** | tarea, qué falta y siguiente paso |``; el push lo comprueba.

## Para la próxima publicación

Nada todavía: el diseño ya está en `main` (PR #2).

## Hecho (5 últimas)

1. 2026-10-25 — F1.2: `orders` copiado de `gimg@0d02f51` (pedidos `voice` y `line`, API `(project, type, key)`, carpeta `orders/<tipo>/<key>/`, audio `.wav`, `voiceReference` como parámetro de `add_attempt`, clave `attempts` reservada) y `sheet` nuevo (`build_instruct` en el orden de `design-sheet.schema.json`, `warnings` con edad y palabras vetadas de D11); `model` y `count` en el esquema de pedido; textos es/en.
2. 2026-10-25 — F1.1: `paths`, `fsutil`, `errors` y `projects` copiados de `gimg@0d02f51` y adaptados (`GVOICE_*`, `galivelop-voice`, `galivelop-voices.json`, `GvoiceError`); `project_data_dir` usa el patrón de `common.schema.json`; sin `check_key` (el límite de la clave es del esquema) ni plantilla/manifiesto; `delivery.dir` se comprueba contra `.git` y el archivo de configuración; `print_models` lee el enum `baseModel`; `gvoice.__version__`.
3. 2026-10-25 — F0 a `main` por el PR #3, con la confirmación de la persona. CI de GitHub sin arrancar (facturación); los pasos de `comprobar.yml` corrieron en local en un clon limpio, en verde.
4. 2026-10-25 — Arreglos de la revisión de código de F0: check con una orden `bash -n` por gancho; validador ampliado respecto a `gimg` (`$ref` a esquemas hermanos de `gvoice/schemas/`, ciclos y rutas fuera de carpeta como `SchemaError`, `allOf`, `if`/`then`/`else`, `load_schema` con caché y copia); `common.schema.json` y fin de las copias de `$defs`; pedido y pasos de efecto por tipo; `seed` 0-4294967295; D16 (`device` en `voice.json`, huellas y `pack.json`); `prints` y `models[].id` con `baseModel`; `formatVersion` solo en `pack.json`; `watchMemoryMb` obligatorio; `GVOICE_LANG` normalizado y limitado a `locales/`; README sin copias; ejemplos coherentes.
5. 2026-10-25 — F0 Esqueleto: paquete `gvoice/` (validador e i18n copiados de `gimg@4365f9a`), esquemas de proyecto, pedido, perfil de máquina, ficha, cadena de efectos, `pack.json` y `voice.json`, ejemplos, README es/en y check real. Decisiones de forma: pedido sin condicionales (el motor exige `voice`/`text` en `line`) y pasos de efecto planos con parámetros opcionales (el subconjunto no tiene `oneOf`/`if`).

## Pendiente

- F1.4: el trabajador comprueba otra vez que la voz del pedido sigue en el proyecto (`orders.add_attempt` no lo hace).
- Leve de la revisión corta de F1.1: `projects._version` confía en el patrón del esquema (seguro hoy, porque siempre se valida antes).
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
