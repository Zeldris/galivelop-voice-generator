<!-- galivelop-workflow v0.3.0 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `ccr-60ec66f6-qbtc42` (asignada por la sesión, desde `main` en `195bb86`) |
| **Fase / tarea** | F1 Núcleo (`docs/plan.md`), en marcha. Compactaciones: 0 de 2 presupuestadas |
| **Último punto estable** | F1.2 `sheet` (avisos D11) y F1.4 `engine` (`FakeEngine`: diseño, frase, huella), `limits` y `log` (D16) |
| **Siguiente paso** | F1.3 `orders` (`docs/plan.md` § «F1 en detalle»): pedidos `voice`/`line`, intentos, elegir/deshacer, desfasadas |
| **Check** | verde (`bash -n` de cada gancho y `unittest`, 198 tests) |

Con `logRows` en `.claude/gw.json`, cada rama escribe solo en su fila de esta tabla, como mucho 600 caracteres, con
la forma ``| **Tarea en curso · `<rama>`** | tarea, qué falta y siguiente paso |``; el push lo comprueba.

## Para la próxima publicación

Nada todavía: el diseño ya está en `main` (PR #2).

## Hecho (5 últimas)

0. 2026-11-10 — F1.4: `gvoice/{engine,limits,log}.py` copiados de `gimg@fa1076e` con sus tests. `FakeEngine` con `design`/`line`/`voiceprint` (`.wav` PCM16 mono 24 kHz determinista por semilla, texto y dispositivo; huellas `.spk`/`.rvq` falsas por sha256); `EngineResult` con dispositivo, semilla, commit y modelo (D16); registro `app.voice.*` y `estimate` por operación, modelo y dispositivo; `limits` con tiempo, memoria (inicio y vigilancia) y modelos del perfil. Variables `GVOICE_ENGINE`, `GVOICE_FAKE_DELAY`, `GVOICE_FAKE_FAIL`, `GVOICE_MACHINE_PROFILE`.
1. 2026-11-10 — F1.2: `gvoice/sheet.py` (`instruction`, `warnings`, `is_adult`) con sus tests; textos `warning.sheet.*` y `error.sheet.invalid`, `machine.*`, `limit.*`, `engine.*`, `log.*` en es/en.
2. 2026-11-10 — F1.1: `gvoice/{errors,paths,fsutil,projects}.py` con sus tests. Variables `GVOICE_CONFIG_HOME`/`GVOICE_DATA_HOME`/`GVOICE_MODELS_HOME`, carpetas `galivelop-voice`, `paths.engine_dir()`; `GvoiceError`; `__version__ = "0.1.0"` en `gvoice/__init__.py`.
3. 2026-10-25 — F0 a `main` por el PR #3, con la confirmación de la persona. CI de GitHub sin arrancar (facturación); los pasos de `comprobar.yml` corrieron en local en un clon limpio, en verde.
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
