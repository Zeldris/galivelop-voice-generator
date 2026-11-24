# Retro: actualización del flujo a Galivelop-workflow v0.9.0 (2026-11-24)

**Estado:** aprobada por la persona el 2026-11-24: P1 aprobada (la aplica la persona: desconectar Claude Docs y los
conectores sin uso); P2 aprobada y apuntada abajo para el flujo; P3 aplazada (se quita de pendientes).

## Medida

29 llamadas desde el `/clear`, contexto medio 107k (suelo 91k, techo 129k), 0 compactaciones; 3,09M de entrada en la
principal, 0,17M en el revisor `sonnet`. Arranque fijo ~81,5k por llamada = 77 % de la entrada.

## Propuestas

- **P1 (entorno, persona).** Desconectar Claude Docs y los conectores que el proyecto no usa: el arranque fijo es el
  77 % del gasto y se propuso ya en las retros del 18 y del 22 sin aplicarse. Riesgo: ninguno.
- **P2 (flujo).** Ver abajo.
- **P3 (proyecto).** `workflowClone` apunta a `../Galivelop-workflow`, que vale en el equipo de la persona; en la nube
  se pasa `--workflow <ruta>` a `review-scope.py`. Sin cambio.

Sin barrido de leves: el bloque no tocó scripts del proyecto, solo copias del flujo y configuración.

## For Galivelop-workflow

- `gw-update`, paso 1: `git ls-remote --tags` devolvió v0.8.2 como última etiqueta cuando ya existía v0.9.0; tras
  `git fetch origin --tags --prune` apareció. El agente dijo «al día» y la persona tuvo que corregirlo (~3 llamadas,
  ~320k). Propuesta: el paso 1 hace `git -C <workflow> fetch origin --tags --prune` y compara con
  `git -C <workflow> tag --sort=-v:refname | head -1`; y `apply.py --check` avisa si `origin` tiene una etiqueta más
  nueva que la copia.
