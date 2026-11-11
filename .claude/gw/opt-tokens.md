<!-- galivelop-workflow v0.3.0 -->
# opt-tokens — notas del proyecto

Las lee la skill `opt-tokens` antes de proponer nada, y se actualizan cuando la persona aprueba un cambio. El flujo
las crea una vez; desde entonces son del proyecto.

## Herramientas que ya ahorran

<!-- Una línea cada una, con cómo se corre. -->
- `python3 .claude/gw/scripts/recuperar.py --estado` y `--buscar "<texto>"`: recuperar lo que se llevó una
  compactación.
- `orchestrate-dealer`: el trabajo de más de un paso, repartido a subagentes de contexto limpio.

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
  las herramientas que usa; medir su arranque con `medir.py` en el primer encargo de F2 y volver atrás si no baja
  o le falta algo.

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
