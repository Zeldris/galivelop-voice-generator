# Retro: actualización del flujo a v0.8.1 (2026-11-19)

**Estado:** pendiente de la decisión de la persona.

Sesión `6ea0a867` desde el último `/clear`: 44 llamadas, contexto medio 108k (suelo 91k, techo 134k), 4,7M de
entrada en la principal, sin subagentes ni compactaciones. Medido con `measure.py --session` (sin `--session`, la
herramienta midió la sesión `987999aa` del 2026-11-16).

## Propuestas (gw-opt-tokens y retro), de más a menos ahorro

- **P1 — El ledger y el gancho `Stop` de la nube se realimentan** (flujo). `docs/metrics/ledger.jsonl` se reescribe
  en cada turno; el gancho `Stop` del entorno pide commit y push de cambios sin subir, y cada commit abre otro turno
  que vuelve a tocar el ledger. Costó 5 turnos extra (~108k cada uno, ~0,5M) y dos commits sueltos. Propuesta al
  flujo: escribir el ledger fuera del árbol versionado (`<git common dir>/gw/`) y volcarlo solo en el commit de
  trabajo. Riesgo: ninguno si el volcado va en el `commit-msg`/`pre-commit`.
- **P2 — Arranque de 84k del sistema** (persona). El suelo de 91k es casi todo instrucciones y herramientas (MCP). La
  P4 de la retro del 2026-11-18 (desconectar Claude Docs) sigue sin aplicar: sus herramientas siguen cargadas. Con
  ~5k menos por llamada, ~0,2M por sesión como esta. Riesgo: ninguno; el proyecto no usa Claude Docs.
- **P3 — `measure.py` elige otra sesión en la nube** (flujo). Sin `--session` tomó una sesión anterior de la misma
  carpeta en vez de la abierta. Propuesta al flujo: preferir la sesión del gancho de inicio (o la del `transcript`
  más reciente por mtime) y decir cuál eligió y por qué. Riesgo: ninguno.
- **P4 — Línea sin efecto en `AGENTS.md`** (proyecto). «Instalar: —.» no cambia ninguna conducta; quitarla deja el
  archivo en 153 líneas (el aviso de `doctor.py` es por encima de 150). Riesgo: ninguno.

## Barrido de leves

El bloque no tocó código del proyecto, solo el flujo y la configuración: ningún script suyo acumula leves de este
bloque. Los leves abiertos de `docs/records/pending.md` ya están repartidos en B1/B2 de la 0.3.0 (`docs/plan.md`).

## For Galivelop-workflow

- P1: ledger fuera del árbol versionado hasta el commit de trabajo, para no realimentar el `Stop` de la nube.
- P3: `measure.py` sin `--session` debe medir la sesión abierta, no la más reciente de otra fecha en la carpeta.
