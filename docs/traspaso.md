<!-- galivelop-workflow v0.3.0 -->
# Bitácora (traspaso)

> Léela entera al empezar cualquier sesión. Lo que no está subido no existe: commit + push en cada punto estable,
> con esta bitácora actualizada en el mismo commit. El flujo nunca la sobrescribe una vez creada.

## Estado actual

| Campo | Valor |
|---|---|
| **Rama** | `ccr-a6c4dde9-3qadwv` |
| **Fase / tarea** | Fase 0: flujo Galivelop-workflow v0.3.0 aplicado; aún no hay código |
| **Último punto estable** | Commit «Flujo Galivelop-workflow v0.3.0»: actualiza skills, ganchos, CI y plantillas desde la v0.1.0 |
| **Siguiente paso** | Elegir el stack del generador de voz y sustituir el check provisional `true` en `.claude/gw.json` por el real (tests + linter) |
| **Check** | `true`: verde (provisional, no comprueba nada) |

Con `logRows` en `.claude/gw.json`, cada rama escribe solo en su fila de esta tabla, como mucho 600 caracteres, con
la forma ``| **Tarea en curso · `<rama>`** | tarea, qué falta y siguiente paso |``; el push lo comprueba.

## Para la próxima publicación

La aplicación del flujo, por pull request desde `ccr-a6c4dde9-3qadwv`.

## Hecho (5 últimas)

1. 2026-10-25 — Flujo actualizado a v0.3.0 (se había aplicado la v0.1.0 de la rama por defecto del repo del flujo).
2. 2026-10-25 — Aplicado Galivelop-workflow con todas las skills (incluidas `opt-ai` y `scout-updates`).

## Pendiente

- **Deuda:** el `check` es `true` provisional porque no hay código; cambiarlo al elegir el stack.

## Comprobar el estado

- Últimos commits: `git fetch origin <rama> && git log --oneline -5 origin/<rama>`.
- El check: `true`.
- Flujo bien montado: `python3 .claude/gw/scripts/doctor.py`.
- Estado de la bitácora tal como lo recibe una sesión nueva: `python3 .claude/gw/scripts/recuperar.py --estado`.
