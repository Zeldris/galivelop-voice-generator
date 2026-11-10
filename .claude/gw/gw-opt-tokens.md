<!-- galivelop-workflow v0.5.1 -->
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

## Ajustes en vigor

- Ventana de compactación automática: `CLAUDE_CODE_AUTO_COMPACT_WINDOW` en `.claude/settings.json`.

## Referencias medidas

<!-- Cifras medidas con las que comparar: fecha, sesión, contexto medio, llamadas, total. -->

- 2026-10-25, diseño del generador de voz (`af3f3065`): 35 llamadas, contexto medio 101k (techo 150k), 0
  compactaciones; subagentes 1,75M de entrada (banco 1,27M). Con `/clear` antes de F0.
- 2026-10-25, F0 esqueleto (`ad9f19a0`): 18 llamadas, contexto medio 68k (techo 89k), 0 compactaciones;
  subagentes 2,8M de entrada (revisión de código en opus 0,67M).
