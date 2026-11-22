# Retro: actualización del flujo a v0.8.2 (2026-11-22)

**Estado:** decidida por la persona el 2026-11-22: P1-P4 aprobadas; P4 aplicada con la opción b (`instructionLines.warn` a 160 en `.claude/gw.json`); P2 y P3 van al flujo (sección For Galivelop-workflow); P1 la aplica la persona (desconectar Claude Docs).

Sesión `6ea0a867` desde el último `/clear` (`measure.py`, que ya mide la sesión abierta): 22 llamadas, contexto medio
102k (suelo 88k, techo 115k), 2,25M de entrada en la principal, sin subagentes ni compactaciones. El resultado más
arrastrado fue leer `gw-update/SKILL.md` (2,5k, 50k arrastrados), necesario. La revisión de fase 1 fue trivial (4
líneas de código, `review-scope.py --trivial`) y se hizo en la sesión, sin hallazgos.

## Propuestas (gw-opt-tokens y retro), de más a menos ahorro

- **P1 — Claude Docs sigue conectado** (persona). Tercera retro seguida: sus herramientas e instrucciones siguen en
  el arranque (suelo 88k, ~81k del sistema). Desconectarlo en claude.ai (Conectores) quita ~5k por llamada, ~0,1M en
  una sesión como esta. Riesgo: ninguno; el proyecto no lo usa.
- **P2 — El gancho `Stop` de la nube pide commit del ledger** (flujo). Volvió a pasar: un turno extra (~100k) solo
  para decir que el ledger va en el siguiente commit. La v0.8.2 lo resuelve como regla en `AGENTS.md`, pero el
  gancho sigue disparándose. Sigue abierta la P1 de la retro del 2026-11-19 (ledger fuera del árbol versionado hasta
  el commit de trabajo). Riesgo: ninguno.
- **P3 — `workflowClone` no existe en la nube** (flujo). `add_repo` deja el clon del flujo en
  `/home/user/zeldris/galivelop-workflow`, no en `../Galivelop-workflow`; `doctor.py` avisa en cada sesión en la nube
  y hubo que buscar dónde estaba. Propuesta al flujo: `doctor.py`, `review-scope.py` y `gw-update` prueban también
  `/home/user/<owner>/<repo>` y `/home/user/<repo>` (en minúsculas) antes de avisar. Riesgo: ninguno.
- **P4 — `AGENTS.md` en 155 líneas** (proyecto). La frase nueva del ledger lo sube por encima del aviso de 150. Mover
  el paso 6 de «Al empezar» (sesión abierta fuera del repo, 5 líneas) a `docs/` con un puntero de una línea lo deja
  en ~151. Riesgo: bajo; ese paso solo importa cuando la sesión se abre mal, y el gancho de inicio no lo puede decir
  porque entonces no corre. Alternativa: subir `instructionLines` a 160 y no tocar nada.

## Barrido de leves

La actualización no tocó código del proyecto: ningún script suyo acumula leves de este bloque. Los leves abiertos de
`docs/records/pending.md` siguen repartidos en B1/B2 de la 0.3.0 (`docs/plan.md`).

## For Galivelop-workflow

- P2: ledger fuera del árbol versionado hasta el commit de trabajo, para que el `Stop` de la nube no pida un commit
  solo para él.
- P3: buscar el clon del flujo también en las rutas donde lo deja `add_repo` en la nube.
