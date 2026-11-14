# Retro 2026-10-25 — aplicar Galivelop-workflow

**Estado:** propuestas presentadas a la persona; las cuatro aplazadas (son del flujo, no del proyecto) y apuntadas
en la bitácora. `opt-tokens` sin propuestas.

## opt-tokens

31 llamadas, contexto medio ~96k (techo 123k, sin compactaciones), 98 % de la entrada desde caché. Por debajo del
umbral de 150k de `orchestrate-dealer`: no hay despilfarro que justifique un cambio.

## Propuestas (todas generales, para Galivelop-workflow)

1. **Versión vieja instalada sin aviso.** La rama por defecto del repo del flujo (`claude/galivelop-workflow-inicio`)
   está en 0.1.0 y la publicada es 0.3.0 (`main`, `v0.3.0`); se aplicó 0.1.0 y hubo que actualizar. Propuesta: que
   `gw-init` use la última etiqueta (`git describe --tags --abbrev=0`) o avise si el clon no está en ella, y poner
   `main` como rama por defecto en GitHub.
2. **Sin camino para CI agotado.** `AGENTS.md` exige el CI en verde y no dice qué hacer sin minutos de CI. Propuesta:
   un `ci-local.sh` que corra los pasos de `comprobar.yml` en un clon limpio, aceptado como sustituto y anotado en la
   bitácora.
3. **Tests de `scout-updates` fallan fuera del repo del flujo.** 2 de 23 (`test_compare.py`) suponen la estructura
   del flujo (`scripts/config.py` en la raíz). Propuesta: saltarlos fuera del flujo o no copiar los tests.
4. **Guía y herramienta en conflicto.** La guía dice no registrar el repo del flujo como raíz de la sesión; el
   resultado de `add_repo` pide `register_repo_root`, y se siguió a la herramienta. Propuesta: que `gw-init` diga
   explícitamente que no se llame.
