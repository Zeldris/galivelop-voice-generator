<!-- galivelop-workflow v0.3.0 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `claude/voces-f0` |
| **Fase / tarea** | F0 Esqueleto (`docs/plan.md`), primera fase del roadmap F0-F7. Compactaciones: 0 de 1 presupuestada |
| **Último punto estable** | F0 hecha: `gvoice/` con validador e i18n (copiados de `gimg@4365f9a`), 7 esquemas, ejemplos, README es/en y check real (58 tests) |
| **Siguiente paso** | Revisión de código de F0 antes de `main` (`/code-review --max-findings all` contra `origin/main`, fase 1 de `AGENTS.md`); después F1 |
| **Check** | verde (`bash -n` de los ganchos y `unittest`, 58 tests) |

Con `logRows` en `.claude/gw.json`, cada rama escribe solo en su fila de esta tabla, como mucho 600 caracteres, con
la forma ``| **Tarea en curso · `<rama>`** | tarea, qué falta y siguiente paso |``; el push lo comprueba.

## Para la próxima publicación

Nada todavía: el diseño ya está en `main` (PR #2).

## Hecho (5 últimas)

1. 2026-10-25 — F0 Esqueleto: paquete `gvoice/` (validador e i18n copiados de `gimg@4365f9a`), esquemas de proyecto, pedido, perfil de máquina, ficha, cadena de efectos, `pack.json` y `voice.json`, ejemplos, README es/en y check real. Decisiones de forma: pedido sin condicionales (el motor exige `voice`/`text` en `line`) y pasos de efecto planos con parámetros opcionales (el subconjunto no tiene `oneOf`/`if`).
2. 2026-10-25 — Diseño a `main` por el PR #2, con la confirmación de la persona. El CI de GitHub no arrancó (facturación de la cuenta); los pasos de `comprobar.yml` corrieron en local en un clon limpio, en verde.
3. 2026-10-25 — Diseño del generador de voz en tres rondas de `grilling`: D1-D17, fases F0-F7 y banco de pruebas en la Deck.
4. 2026-10-25 — Investigación de actualizaciones del documento de voces (motor activo sin binarios, español confirmado, Piper ahora GPL, riesgo Vulkan en APU AMD).
5. 2026-10-25 — Revisión, `opt-tokens` y retro (`docs/registros/retro-2026-10-25-aplicar-flujo.md`) antes de `main`.

## Pendiente

- Escucha del banco y registro del núcleo tras Vulkan: los dos, de la persona (ver «Pendiente» en `docs/plan.md`).
- Para proponer al flujo: R2-R4 de `docs/registros/retro-2026-10-25-diseno-voces.md`, y las aplazadas de la retro anterior: rama por defecto del flujo en 0.1.0; camino para CI
  agotado (`ci-local.sh`); 2 tests de `scout-updates` fallan fuera del flujo; `gw-init` debe decir que no se llame a
  `register_repo_root`.

## Comprobar el estado

- Últimos commits: `git fetch origin <rama> && git log --oneline -5 origin/<rama>`.
- El check: `bash -n .githooks/pre-commit .githooks/pre-push && python3 -m unittest discover -s tests -t .`.
- Flujo bien montado: `python3 .claude/gw/scripts/doctor.py`.
- Estado de la bitácora tal como lo recibe una sesión nueva: `python3 .claude/gw/scripts/recuperar.py --estado`.
