<!-- galivelop-workflow v0.3.0 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `claude/voces-f0` |
| **Fase / tarea** | F0 Esqueleto (`docs/plan.md`), primera fase del roadmap F0-F7. Compactaciones: 0 de 1 presupuestada |
| **Último punto estable** | F0 con los arreglos de la revisión de código: validador con `$ref` hermano, `allOf` e `if`/`then`/`else`; `common.schema.json`; pedido y pasos de efecto por tipo; D16 en `voice.json`; i18n normalizado (87 tests) |
| **Siguiente paso** | F1 Núcleo (`docs/plan.md`) en una rama nueva desde `main` |
| **Tarea en curso · `ccr-a6c4dde9-3qadwv`** | Apuntado VoiceStudio como repo de referencia (`docs/investigacion/2026-11-08-voicestudio.md`). Falta: localizar su URL y revisarlo con un subagente. Siguiente: lo que pida la persona; F1 sigue siendo el siguiente paso del proyecto |
| **Check** | verde (`bash -n` de cada gancho y `unittest`, 87 tests) |

Con `logRows` en `.claude/gw.json`, cada rama escribe solo en su fila de esta tabla, como mucho 600 caracteres, con
la forma ``| **Tarea en curso · `<rama>`** | tarea, qué falta y siguiente paso |``; el push lo comprueba.

## Para la próxima publicación

Nada todavía: el diseño ya está en `main` (PR #2).

## Hecho (5 últimas)

1. 2026-10-25 — F0 a `main` por el PR #3, con la confirmación de la persona. CI de GitHub sin arrancar (facturación); los pasos de `comprobar.yml` corrieron en local en un clon limpio, en verde.
2. 2026-10-25 — Arreglos de la revisión de código de F0: check con una orden `bash -n` por gancho; validador ampliado respecto a `gimg` (`$ref` a esquemas hermanos de `gvoice/schemas/`, ciclos y rutas fuera de carpeta como `SchemaError`, `allOf`, `if`/`then`/`else`, `load_schema` con caché y copia); `common.schema.json` y fin de las copias de `$defs`; pedido y pasos de efecto por tipo; `seed` 0-4294967295; D16 (`device` en `voice.json`, huellas y `pack.json`); `prints` y `models[].id` con `baseModel`; `formatVersion` solo en `pack.json`; `watchMemoryMb` obligatorio; `GVOICE_LANG` normalizado y limitado a `locales/`; README sin copias; ejemplos coherentes.
3. 2026-10-25 — F0 Esqueleto: paquete `gvoice/` (validador e i18n copiados de `gimg@4365f9a`), esquemas de proyecto, pedido, perfil de máquina, ficha, cadena de efectos, `pack.json` y `voice.json`, ejemplos, README es/en y check real. Decisiones de forma: pedido sin condicionales (el motor exige `voice`/`text` en `line`) y pasos de efecto planos con parámetros opcionales (el subconjunto no tiene `oneOf`/`if`).
4. 2026-10-25 — Diseño a `main` por el PR #2, con la confirmación de la persona. El CI de GitHub no arrancó (facturación de la cuenta); los pasos de `comprobar.yml` corrieron en local en un clon limpio, en verde.
5. 2026-10-25 — Diseño del generador de voz en tres rondas de `grilling`: D1-D17, fases F0-F7 y banco de pruebas en la Deck.

## Pendiente

- Revisar VoiceStudio (AGPL-3.0; solo ideas, sin copiar código): `docs/investigacion/2026-11-08-voicestudio.md`.
- Hallazgos leves de la revisión de F0, sin arreglar en este PR: el mensaje de `propertyNames` sale con «()» vacío cuando el motivo no es un `pattern` (p. ej. un `enum`) y solo cuenta el primer motivo (`gvoice/schema.py`); `i18n.t()` lanza `KeyError` si a un idioma le falta un parámetro del texto y no mira `LANGUAGE`; los commits `81d76f1` y `7cebd24` de F0 tienen `Siguiente:` separado de la atribución por una línea en blanco.
- F1: `printModels` ya no tiene `default` en el esquema; el valor por defecto de D14 (0.6B y 1.7B Base) lo aplica el
  código al cargar la configuración.
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
