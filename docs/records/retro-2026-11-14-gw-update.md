# Retro 2026-11-14 — actualización del flujo 0.3.0 → 0.6.0

**Estado:** presentada a la persona y aprobada entera. Aplicada en la rama la medida de `gw-opt-tokens`; R1-R5 son
del flujo y quedan abajo para `gw-harvest`.

## gw-opt-tokens

Sesión `6ea0a867`: 42 llamadas, contexto medio 119k (suelo 80k, techo 151k), 0 compactaciones, sin subagentes, 98 %
lectura de caché. Lo más arrastrado: el `--dry-run` de `apply.py` (3k, 100k arrastrados) y la copia 0.3.0 de la
skill `gw-update` del proyecto (2k, 79k arrastrados), leída antes que la 0.6.0 del flujo. Medida apuntada en
`.claude/gw/gw-opt-tokens.md` (aplicada).

## Revisión

Fase 1: `review-scope.py --workflow` dejó 4 archivos de código fuera de lo copiado (`.claude/gw.json`,
`.claude/settings.json`, `.github/workflows/check.yml`, `.gitignore`), todo configuración generada por `apply.py`;
revisados en la sesión, 0 hallazgos, `SHIP`. El resto es contenido o borrado de nombres viejos.

## Para Galivelop-workflow

- **R1** (`gw-update`): la sesión siguió primero la copia vieja de la skill en el proyecto (0.3.0, `aplicar.py`) y
  luego tuvo que leer la del flujo (0.6.0, `apply.py`). La skill debería decir en su primera línea que se sigue
  `<flujo>/skills/gw-update/SKILL.md` en la etiqueta Y, no la copia del proyecto.
- **R2** (`apply.py`): `--dry-run` dio 314 líneas (87 `create`, los 9 avisos de nombres viejos dos veces) y el diff
  de `REVIEW.md`/`GLOSSARY.md` es proyecto contra plantilla, no plantilla vX contra vY como pide el paso 3 de la
  skill. Proponer `--summary` (recuentos por acción, solo lo que pide decisión, avisos sin repetir) y el diff de
  plantilla vX → vY directamente.
- **R3** (`apply.py`): las actualizaciones de plantilla de la bitácora y de las notas `.claude/gw/gw-*.md` solo salen
  en `--check`, tras aplicar, y eran renombres puros (`recuperar.py --estado` → `recover.py --state`, ```` ```opt-ai ````
  → ```` ```gw-opt-ai ````, `medir.py` → `measure.py`). Listarlas en `--dry-run` y aplicarles el mapa de nombres
  viejos; a mano, solo lo que no sea renombre.
- **R4** (`config.py`/esquema): `doctorTestDirsIgnore` por defecto debería incluir `.claude/skills/gw-*`: tras cada
  actualización doctor avisa de los tests de las skills copiadas, que se prueban en el flujo (y algunos fallan fuera,
  ya en la retro de F0). Aquí va en `.claude/gw.json` hasta que el flujo lo traiga.
- **R5** (`gw-update`): el paso 5.4 abre el PR justo tras el commit, y `AGENTS.md` pide antes las tres fases
  (revisión, retro, marca). Que diga «el PR, tras las tres fases de `AGENTS.md`».
