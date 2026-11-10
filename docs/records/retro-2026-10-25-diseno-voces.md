# Retro 2026-10-25 — diseño del generador de voz

**Estado:** presentada a la persona y aprobada entera. Aplicadas en la rama O1, O2, O3 y R1; R2, R3 y R4 son del
flujo y quedan abajo para `gw-harvest`.

## opt-tokens

35 llamadas, contexto medio 101k (techo 150k), 0 compactaciones, 96 % de la entrada desde caché. Subagentes: 1,75M de
entrada, de los que el banco de pruebas se llevó 1,27M. Lo más arrastrado de la sesión principal fue leer entero el
documento de origen (5,5k tokens, ~181k arrastrados), justificado porque era la entrada del diseño.

- **O1** (aplicada): el banco pasa a ser una orden en F2 (`gvoice bench`), en `docs/plan.md`.
- **O2** (aplicada): `.claude/gw/opt-tokens.md` apunta que el documento de origen ya no se relee y que del plan de
  `gimg` basta la tabla de decisiones.
- **O3** (aplicada): cifra de referencia en `.claude/gw/opt-tokens.md`; `/clear` antes de F0.

## Propuestas del proyecto

- **R1** (aplicada): la sesión corre dentro del Flatpak de VS Code (compilador del SDK, sin `journalctl`, el anfitrión
  con `flatpak-spawn --host`). Se descubrió a mitad del banco y es clave para F2. Línea en «Reglas del proyecto» de
  `AGENTS.md`, con el puntero al informe del banco.

## For Galivelop-workflow

- **R2 — CI agotado, segunda vez.** `AGENTS.md` exige el CI en verde y no da camino sin minutos de CI. Se volvieron a
  correr a mano en un clon limpio los pasos de `comprobar.yml`. Propuesta (ya hecha en la retro del 2026-10-25 al
  aplicar el flujo): un `ci-local.sh` que lo haga y deje constancia en la bitácora.
- **R3 — Sesión dentro de un Flatpak.** `doctor.py` podría detectarlo (`/.flatpak-info`) y avisar de que el compilador
  y las herramientas son del SDK y de que el anfitrión se alcanza con `flatpak-spawn --host`.
- **R4 — `selector`, fila «traer algo de otro repo».** Dice que la sesión principal nunca lee los archivos enteros;
  cuando un diseño nace de un único documento, leerlo entero una vez en la sesión principal es lo correcto. Matizar:
  el documento de entrada de un diseño se lee entero una vez; el resto, con `Explore`.
