<!-- galivelop-workflow v0.3.0 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `claude/voces-diseno` |
| **Fase / tarea** | Diseño del generador de voz a partir de `World-Maker-Fantasy/docs/arquitectura/reutilizables/02-voces-y-sonidos-locales.md`, con `grilling`; luego implementación. Presupuesto: 1 compactación para el diseño (llevadas: 0) |
| **Último punto estable** | Decisiones D1-D13 en `docs/plan.md` (rondas 1 y 2 de `grilling` aprobadas), ADR 0001-0002 y glosario |
| **Siguiente paso** | Banco de pruebas en la Deck (subagente; informe en `docs/investigacion/2026-10-25-banco-deck.md`, motor y modelos en `~/.local/share/galivelop-voice/`); con sus cifras, ronda 3: niveles de hardware, perfil `steam-deck` y fases de implementación |
| **Check** | `true`: verde (provisional, no comprueba nada) |

Con `logRows` en `.claude/gw.json`, cada rama escribe solo en su fila de esta tabla, como mucho 600 caracteres, con
la forma ``| **Tarea en curso · `<rama>`** | tarea, qué falta y siguiente paso |``; el push lo comprueba.

## Para la próxima publicación

Nada todavía: la aplicación del flujo ya está en `main` (`8216893`).

## Hecho (5 últimas)

1. 2026-10-25 — Investigación de actualizaciones del documento de voces (motor activo sin binarios, español confirmado, Piper ahora GPL, riesgo Vulkan en APU AMD).
2. 2026-10-25 — Revisión, `opt-tokens` y retro (`docs/registros/retro-2026-10-25-aplicar-flujo.md`) antes de `main`.
3. 2026-10-25 — Flujo actualizado a v0.3.0 (se había aplicado la v0.1.0 de la rama por defecto del repo del flujo).
4. 2026-10-25 — Aplicado Galivelop-workflow con todas las skills (incluidas `opt-ai` y `scout-updates`).

## Pendiente

- **Deuda:** el `check` es `true` provisional porque no hay código; cambiarlo al elegir el stack.
- Rellenar «Reglas del proyecto» en `AGENTS.md` cuando haya stack.
- Aplazadas, para proponer al flujo (detalle en la retro): rama por defecto del flujo en 0.1.0; camino para CI
  agotado (`ci-local.sh`); 2 tests de `scout-updates` fallan fuera del flujo; `gw-init` debe decir que no se llame a
  `register_repo_root`.

## Comprobar el estado

- Últimos commits: `git fetch origin <rama> && git log --oneline -5 origin/<rama>`.
- El check: `true`.
- Flujo bien montado: `python3 .claude/gw/scripts/doctor.py`.
- Estado de la bitácora tal como lo recibe una sesión nueva: `python3 .claude/gw/scripts/recuperar.py --estado`.
