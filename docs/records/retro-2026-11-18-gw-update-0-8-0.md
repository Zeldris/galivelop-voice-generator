# Retro 2026-11-18: actualización a Galivelop-workflow v0.8.0

**Estado:** aprobada y aplicada (P2, P3); P1 aprobada para el flujo (abajo); P4 aprobada, la aplica la persona.

Sesión `6ea0a867` desde `4dfa016`: `gw-update` de 0.7.0 a 0.8.0, fase 1 con 1 hallazgo medio arreglado
(`f95fd11`). 29 llamadas, contexto medio 119k, sin compactaciones ni subagentes.

## Propuestas

- **P1 (flujo):** la fusión de `.claude/settings.json` de `apply.py` dejó repetido `whole-read.py`. Sumó el matcher
  nuevo `^(Read|Bash)$` sin quitar el antiguo `Read`, así que el gancho corría dos veces en cada `Read`. Ni `doctor.py`
  ni `apply.py --check` lo vieron. Arreglado a mano en el proyecto; el arreglo de fondo va al flujo (abajo).
- **P2 (proyecto):** `AGENTS.md` tenía 156 líneas, por encima del aviso de 150. La regla «Flatpak» pasa a ser una
  línea con puntero a `docs/investigacion/2026-10-25-banco-deck.md`; queda en 153. Riesgo: en la Deck hay que seguir
  el puntero.
- **P3 (proyecto):** línea base de un `gw-update` en `.claude/gw/gw-opt-tokens.md`.
- **P4 (persona):** desconectar el conector Claude Docs del entorno de la nube. El suelo del arranque (~87k) es casi
  todo prompt, herramientas y MCP, y un `/clear` no lo baja. Se mide en el próximo arranque.

Barrido de leves: este bloque no tocó código del proyecto, y el barrido B2 ya está en 0.3.0. Desviaciones de alcance:
ninguna.

## For Galivelop-workflow

- La fusión de `settings.json` en `apply.py` sustituye la entrada de un gancho del flujo cuyo matcher cambió (mismo
  script, mismo evento), en vez de añadir otra al lado. Test: un `settings.json` 0.7.0 con `Read` → `whole-read.py`
  queda solo con `^(Read|Bash)$` tras `--update`.
- `doctor.py` da `FAIL` cuando el mismo script está enganchado dos veces en un evento con matchers que se solapan, con
  la orden que lo arregla.
