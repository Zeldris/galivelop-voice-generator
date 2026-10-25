<!-- galivelop-workflow v0.3.0 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `ccr-a6c4dde9-3qadwv` |
| **Fase / tarea** | Fase 0: flujo Galivelop-workflow v0.3.0 aplicado y llevado a `main` por PR; aún no hay código |
| **Último punto estable** | Commit «Flujo Galivelop-workflow v0.3.0»: actualiza skills, ganchos, CI y plantillas desde la v0.1.0 |
| **Siguiente paso** | Elegir el stack del generador de voz y sustituir el check provisional `true` en `.claude/gw.json` por el real (tests + linter) |
| **Check** | `true`: verde (provisional, no comprueba nada) |

Con `logRows` en `.claude/gw.json`, cada rama escribe solo en su fila de esta tabla, como mucho 600 caracteres, con
la forma ``| **Tarea en curso · `<rama>`** | tarea, qué falta y siguiente paso |``; el push lo comprueba.

## Para la próxima publicación

La aplicación del flujo, por pull request desde `ccr-a6c4dde9-3qadwv`, confirmada por la persona. El CI de GitHub está
agotado: se corrieron en local los pasos de `comprobar.yml` en un clon limpio (validar config, install, check), en verde.

## Hecho (5 últimas)

1. 2026-10-25 — Revisión, `opt-tokens` y retro (`docs/registros/retro-2026-10-25-aplicar-flujo.md`) antes de `main`.
2. 2026-10-25 — Flujo actualizado a v0.3.0 (se había aplicado la v0.1.0 de la rama por defecto del repo del flujo).
3. 2026-10-25 — Aplicado Galivelop-workflow con todas las skills (incluidas `opt-ai` y `scout-updates`).

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
