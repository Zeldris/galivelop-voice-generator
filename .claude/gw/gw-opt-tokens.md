<!-- galivelop-workflow v0.9.0 -->
# gw-opt-tokens — notas del proyecto

Las lee la skill `gw-opt-tokens` antes de proponer nada, y se actualizan cuando la persona aprueba un cambio. El flujo
las crea una vez; desde entonces son del proyecto.

## Herramientas que ya ahorran

<!-- Una línea cada una, con cómo se corre. -->
- `python3 .claude/gw/scripts/recover.py --state` y `--search "<texto>"`: recuperar lo que se llevó una
  compactación.
- `gw-orchestrate-dealer`: el trabajo de más de un paso, repartido a subagentes de contexto limpio.

## Costes conocidos

<!-- Lo que se ha visto que cuesta mucho en este proyecto (archivos grandes leídos enteros, salidas largas...). -->

- El documento de origen (`World-Maker-Fantasy/docs/arquitectura/reutilizables/02-voces-y-sonidos-locales.md`) ya
  está sustituido por `docs/plan.md` y `docs/investigacion/`: no se relee. Leerlo entero costó 5,5k tokens arrastrados
  ~181k en la sesión de diseño.
- Del plan de `galivelop-image-generator` se lee solo la tabla de decisiones (`grep -n "^| D" docs/plan.md`).
- Medir el motor a mano con un subagente costó ~1,3M tokens (banco del 2026-10-25): desde F2, `gvoice bench`.
- Al empezar una fase, el gancho de inicio ya trae la bitácora: se lee solo la fase de `docs/plan.md`. Releer
  bitácora, glosario y `gw.json` en F0 arrastró 79k.
- `docs/plan.md` entero y releído 5 veces arrastró 173k en F1: la fase se lee con
  `sed -n '/^## F<n> en detalle/,/^## Pendiente/p' docs/plan.md`, una vez.
- Clonar y leer `gimg` desde la sesión principal arrastró ~140k en F1: otro repositorio lo lee un subagente que
  devuelve rutas y fragmentos.
- Cada subagente `general-purpose` arranca con ~68k (instrucciones y herramientas del entorno), y lo paga en cada
  llamada: ~8M de los 13M de F1. Los encargos de código van al tipo `implementador` (`.claude/agents/`), con solo
  las herramientas que usa; medir su arranque con `measure.py` en el primer encargo de F2 y volver atrás si no baja
  o le falta algo.
- Preparar el encargo de F5.2 leyendo la interfaz en la sesión principal (`api.md`, `app.js`, simulador, plan, tests)
  costó ~11k tokens, arrastrados ~170k. El encargo de un paso de F5 se escribe con la fila del plan, `docs/api.md` y
  las rutas; el subagente lee el resto (retro F5.2, aprobada).

- Encadenar tareas sin `/clear` (F2.4 → F5.7, sesión `6ea0a867`): 454 llamadas a 117k de media, 2 compactaciones,
  53M en la principal. Al cerrar una tarea, si el contexto pasa de ~120k, no se empieza la siguiente aunque la persona
  diga «Siguiente»: se pide el `/clear` y se para (retro 2026-11-16, P1).
- Versionado y releases ya viven aquí (`docs/plan.md` § Versiones, `releases.py`, CHANGELOG): no se lee `gimg`
  para eso. Leerlo desde la principal arrastró ~380k en la sesión `d2b52ac4` (retro 2026-11-17, P1).
- Las revisiones van al tipo `gw-reviewer`, no a `general-purpose` (arranque 66-70k frente a ~15k); medir su arranque
  con `measure.py` en la primera (retro 2026-11-16, P2).
- Los arreglos de una revisión de bloque van a `implementador` sonnet, no a la principal: en F5.7 arrastraron ~150k
  (retro 2026-11-16, P3).
- `gw-reviewer` lanza `/code-review`, que abre otro subagente `general-purpose` opus: en la fase 1 de F5.9 (diff de
  ~220 líneas) 0,93M de los 1,03M de la revisión. Propuesto revisar sin anidar en diffs pequeños y rechazado por la
  persona (retro 2026-11-17 F5.9, P1): medir cada revisión pequeña; si se repite y pesa, se vuelve a proponer con
  las cifras.

## Ajustes en vigor

- Ventana de compactación automática: `CLAUDE_CODE_AUTO_COMPACT_WINDOW` en `.claude/settings.json`.

## Referencias medidas

<!-- Cifras medidas con las que comparar: fecha, sesión, contexto medio, llamadas, total. -->

- 2026-10-25, diseño del generador de voz (`af3f3065`): 35 llamadas, contexto medio 101k (techo 150k), 0
  compactaciones; subagentes 1,75M de entrada (banco 1,27M). Con `/clear` antes de F0.
- 2026-10-25, F0 esqueleto (`ad9f19a0`): 18 llamadas, contexto medio 68k (techo 89k), 0 compactaciones;
  subagentes 2,8M de entrada (revisión de código en opus 0,67M).
- 2026-11-10, F1 núcleo (`acd19f75`): 35 llamadas, contexto medio 118k (techo 143k), 0 compactaciones; 5 subagentes
  en sonnet, 88 llamadas, 9,6M de entrada, arranque medio 68k. Revisión (`8c6b4aa5`): 12 llamadas, 99k; subagentes
  3,5M (revisión en opus 1,4M).
- 2026-11-14, `/gw-update` 0.3.0 → 0.6.0 (`6ea0a867`): 42 llamadas, contexto medio 119k (suelo 80k, techo 151k),
  0 compactaciones, sin subagentes; la revisión de fase 1 (4 archivos de configuración) en la sesión.
- 2026-11-15, F5.2 (`86bcfcfb`): 22 llamadas, contexto medio 113k (suelo 86k, techo 138k), 0 compactaciones;
  subagentes 4,98M de entrada (implementador en sonnet 3,3M; revisión en opus 1,6M).
- 2026-11-16, F2.4 → F5.7 en una sesión (`6ea0a867`): 454 llamadas, contexto medio 117k (suelo 90k, techo 162k), 2
  compactaciones; subagentes 14M (revisiones en `general-purpose` opus 5,1M). Arranque tras `/clear`: 94k, ~85k del
  entorno de la nube.
- 2026-11-17, versiones y cierre de 0.2.0 (`d2b52ac4`): 48 llamadas, contexto medio 98k (suelo 50k, techo 130k), 0
  compactaciones, 4,7M en la principal; 4 subagentes, 1,4M (arranque medio 18k).
- 2026-11-18, `gw-update` 0.7.0 → 0.8.0 (`6ea0a867`, desde `4dfa016`): 29 llamadas, contexto medio 119k (suelo 107k,
  techo 131k), 0 compactaciones, 3,46M de entrada; sin subagentes (diffs de plantilla de menos de 200 líneas leídos en
  la principal). Suelo ≈ entorno de la nube (~87k de prompt, herramientas y MCP); la persona desconecta Claude Docs
  (retro 2026-11-18, P4): medir el arranque del próximo `/clear`.
- 2026-11-22, `gw-update` 0.8.1 → 0.8.2 (`6ea0a867`): 22 llamadas, contexto medio 102k (suelo 88k, techo 115k),
  0 compactaciones, 2,25M de entrada; sin subagentes. Claude Docs seguía conectado (retro 2026-11-22, P1).
