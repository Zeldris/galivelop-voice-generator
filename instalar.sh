#!/usr/bin/env bash
# Instala el motor real (qwentts.cpp) para galivelop-voice-generator (D17). Sin root. Idempotente. bash 3.2.
#
# Uso: bash instalar.sh [--cpu-only] [--skip-models] [--dry-run] [--help]
#
# Entorno (se detecta; GVOICE_INSTALL_ENV=native|steamos|flatpak lo fuerza):
#   flatpak  dentro de un Flatpak (VS Code en la Deck): el compilador del SDK ya está; los binarios se prueban en
#            el anfitrión con `flatpak-spawn --host`.
#   steamos  sin compilador: se compila con `flatpak run org.freedesktop.Sdk//25.08` (se instala si falta).
#   native   distribución con cmake, g++ y git: directo.
# Otras variables: GVOICE_INSTALL_SDK=present|system|missing (fuerza la detección del SDK: de usuario, del sistema o
# ausente), GVOICE_INSTALL_SPIRV=system|local (SPIRV-Headers), GVOICE_INSTALL_JOBS (hilos de compilación).
# Rutas: GVOICE_DATA_HOME / XDG_DATA_HOME (como `gvoice`). Idioma de los mensajes: LANGUAGE, LC_ALL, LC_MESSAGES o
# LANG (inglés si empieza por «en»; si no, español).
set -euo pipefail

# Versión fijada del SDK: la rama 25.08, la estable de org.freedesktop.Sdk en flathub y la que se usó en el banco de la
# Deck (docs/investigacion/2026-10-25-banco-deck.md); consultado 2026-11.
SDK="org.freedesktop.Sdk//25.08"
FLATHUB_URL="https://dl.flathub.org/repo/flathub.flatpakrepo"
SPIRV_REPO="https://github.com/KhronosGroup/SPIRV-Headers"
SPIRV_COMMIT="fbf86836"   # el del banco de la Deck (docs/investigacion/2026-10-25-banco-deck.md)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CPU_ONLY=0
SKIP_MODELS=0
DRY=0

# --- idioma de los mensajes ----------------------------------------------------------------------------------
UI_LANG=es
for _v in "${LANGUAGE:-}" "${LC_ALL:-}" "${LC_MESSAGES:-}" "${LANG:-}"; do
  if [ -n "$_v" ]; then
    case "$_v" in en*) UI_LANG=en ;; esac
    break
  fi
done

# m <español> <inglés>: el texto en el idioma de los mensajes.
m() { if [ "$UI_LANG" = en ]; then printf '%s' "$2"; else printf '%s' "$1"; fi; }

PREFIX_TAG="$(m '[instalar]' '[install]')"

usage() {
  if [ "$UI_LANG" = en ]; then
    cat <<'USAGE'
Usage: bash instalar.sh [--cpu-only] [--skip-models] [--dry-run]

  --cpu-only      build only the CPU version (no Vulkan)
  --skip-models   do not download or verify the models (`python3 -m gvoice models fetch`)
  --dry-run       print every command ("DRY-RUN: ..." lines) without running it or touching the disk or the network
  -h, --help      this help
USAGE
  else
    cat <<'USAGE'
Uso: bash instalar.sh [--cpu-only] [--skip-models] [--dry-run]

  --cpu-only      compila solo la versión CPU (sin Vulkan)
  --skip-models   no baja ni verifica los modelos (`python3 -m gvoice models fetch`)
  --dry-run       imprime cada orden (líneas "DRY-RUN: ...") sin ejecutarla ni tocar disco ni red
  -h, --help      esta ayuda
USAGE
  fi
}

say() { echo "$PREFIX_TAG $*"; }
die() { echo "instalar.sh: $(m error error): $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --cpu-only) CPU_ONLY=1 ;;
    --skip-models) SKIP_MODELS=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "instalar.sh: $(m 'opción desconocida' 'unknown option'): $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

# Ejecuta una orden, o la imprime con --dry-run (una por línea, comillas de shell para que se pueda copiar).
run() {
  if [ "$DRY" = 1 ]; then
    printf 'DRY-RUN:'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

have() { command -v "$1" >/dev/null 2>&1; }

# --- entorno (en el ámbito principal: un `die` aquí aborta el script) ---------------------------------------------
if [ -n "${GVOICE_INSTALL_ENV:-}" ]; then
  case "$GVOICE_INSTALL_ENV" in
    native|steamos|flatpak) ENV_KIND="$GVOICE_INSTALL_ENV" ;;
    *) die "$(m "GVOICE_INSTALL_ENV=$GVOICE_INSTALL_ENV no vale (native, steamos o flatpak)" \
                "GVOICE_INSTALL_ENV=$GVOICE_INSTALL_ENV is not valid (native, steamos or flatpak)")" ;;
  esac
elif [ -e /.flatpak-info ] || [ -n "${FLATPAK_ID:-}" ]; then
  ENV_KIND=flatpak
elif have cmake && have g++ && have git; then
  ENV_KIND=native
elif have flatpak; then
  ENV_KIND=steamos
else
  die "$(m "no hay compilador (cmake, g++, git) ni flatpak: instala el compilador o flatpak y vuelve a correr instalar.sh" \
           "no compiler (cmake, g++, git) and no flatpak: install the compiler or flatpak and run instalar.sh again")"
fi

case "${GVOICE_INSTALL_SPIRV:-}" in
  system|local) SPIRV_MODE="$GVOICE_INSTALL_SPIRV" ;;
  "") if [ "$ENV_KIND" = native ] && [ -e /usr/include/spirv/unified1/spirv.hpp ]; then SPIRV_MODE=system
      else SPIRV_MODE=local; fi ;;
  *) die "$(m "GVOICE_INSTALL_SPIRV=$GVOICE_INSTALL_SPIRV no vale (system o local)" \
              "GVOICE_INSTALL_SPIRV=$GVOICE_INSTALL_SPIRV is not valid (system or local)")" ;;
esac

# --- catálogo y rutas (una sola fuente: gvoice) --------------------------------------------------------------
have python3 || die "$(m "falta python3 (lo necesita gvoice)" "python3 is missing (gvoice needs it)")"
INFO="$(cd "$ROOT" && python3 -c '
from gvoice import models, paths
c = models.load("qwentts")
print(c["repo"]); print(c["commit"]); print(paths.engine_dir())')" \
  || die "$(m "no se pudo leer el catálogo del motor (python3 -m gvoice): revisa la salida de arriba" \
              "could not read the engine catalog (python3 -m gvoice): see the output above")"
ENGINE_REPO="$(printf '%s\n' "$INFO" | sed -n 1p)"
ENGINE_COMMIT="$(printf '%s\n' "$INFO" | sed -n 2p)"
ENGINE="$(printf '%s\n' "$INFO" | sed -n 3p)"
if [ -z "$ENGINE_REPO" ] || [ -z "$ENGINE_COMMIT" ] || [ -z "$ENGINE" ]; then
  die "$(m "el catálogo del motor está incompleto (repo, commit y carpeta)" \
           "the engine catalog is incomplete (repo, commit and folder)")"
fi
SRC="$ENGINE/src"
PREFIX="$ENGINE/deps/prefix"
SPIRV_SRC="$ENGINE/deps/SPIRV-Headers"

JOBS="${GVOICE_INSTALL_JOBS:-$( (nproc 2>/dev/null || echo 4) | head -n1)}"

# Instalación de flatpak donde está el SDK (steamos): --user o --system; la fija ensure_sdk.
SDK_SCOPE="--user"

# Ejecuta una herramienta de compilación: en SteamOS, dentro del SDK de Flatpak, con red (git clone/fetch/submodule).
tool() {
  if [ "$ENV_KIND" = steamos ]; then
    local cmd="$1"; shift
    run flatpak run "$SDK_SCOPE" --share=network "--filesystem=$ENGINE" "--command=$cmd" "$SDK" "$@"
  else
    run "$@"
  fi
}

# --- SDK (solo SteamOS) --------------------------------------------------------------------------------------
ensure_sdk() {
  have flatpak || [ "$DRY" = 1 ] || die "$(m "falta flatpak: en SteamOS viene de serie; si no, instala un compilador (cmake, g++, git)" \
                                             "flatpak is missing: SteamOS ships it; otherwise install a compiler (cmake, g++, git)")"
  local state="${GVOICE_INSTALL_SDK:-}"
  case "$state" in
    present|system|missing|"") ;;
    *) die "$(m "GVOICE_INSTALL_SDK=$state no vale (present, system o missing)" \
                "GVOICE_INSTALL_SDK=$state is not valid (present, system or missing)")" ;;
  esac
  if [ -z "$state" ]; then
    if have flatpak && flatpak info --user "$SDK" >/dev/null 2>&1; then state=present
    elif have flatpak && flatpak info --system "$SDK" >/dev/null 2>&1; then state=system
    else state=missing; fi
  fi
  case "$state" in
    missing)
      say "$(m "instalando el SDK $SDK (flatpak --user, sin root; baja unos cientos de MB)" \
               "installing the SDK $SDK (flatpak --user, no root; downloads a few hundred MB)")"
      run flatpak --user remote-add --if-not-exists flathub "$FLATHUB_URL"
      run flatpak --user install -y --noninteractive flathub "$SDK"
      ;;
    system)
      SDK_SCOPE="--system"
      say "$(m "SDK $SDK ya instalado en el sistema" "SDK $SDK already installed system-wide")"
      ;;
    *)
      say "$(m "SDK $SDK ya instalado" "SDK $SDK already installed")"
      ;;
  esac
}

check_native_tools() {
  local missing=""
  for t in cmake g++ git; do have "$t" || missing="$missing $t"; done
  [ -z "$missing" ] || [ "$DRY" = 1 ] || die "$(m "faltan herramientas:$missing (instálalas o corre instalar.sh en SteamOS con flatpak)" \
                                                 "missing tools:$missing (install them or run instalar.sh on SteamOS with flatpak)")"
}

# --- motor ---------------------------------------------------------------------------------------------------
fetch_source() {
  say "$(m motor engine) $ENGINE_REPO @ $ENGINE_COMMIT -> $SRC"
  run mkdir -p "$ENGINE"
  if [ -d "$SRC/.git" ]; then
    tool git -C "$SRC" fetch origin
  else
    tool git clone "$ENGINE_REPO" "$SRC"
  fi
  tool git -C "$SRC" checkout "$ENGINE_COMMIT"
  tool git -C "$SRC" submodule update --init --recursive
}

ensure_spirv() {
  if [ -e "$PREFIX/include/spirv/unified1/spirv.hpp" ]; then
    say "$(m "SPIRV-Headers ya en $PREFIX" "SPIRV-Headers already in $PREFIX")"
    return
  fi
  say "SPIRV-Headers $SPIRV_COMMIT -> $PREFIX $(m '(sin tocar el sistema)' '(without touching the system)')"
  if [ ! -d "$SPIRV_SRC/.git" ]; then
    tool git clone "$SPIRV_REPO" "$SPIRV_SRC"
  fi
  tool git -C "$SPIRV_SRC" checkout "$SPIRV_COMMIT"
  tool cmake -S "$SPIRV_SRC" -B "$SPIRV_SRC/build" "-DCMAKE_INSTALL_PREFIX=$PREFIX"
  tool cmake --install "$SPIRV_SRC/build"
}

# Los binarios y sus .so quedan en la raíz de la carpeta (el rpath `$ORIGIN` los busca ahí). Lo que cmake dejó en
# una subcarpeta se copia siempre, encima de lo que hubiera: una copia vieja de otra compilación no se queda.
collect() {
  local dir="$1" name found lib
  if [ "$DRY" = 1 ]; then
    say "$(m "reunir qwen-tts, qwen-codec, tts-server y sus .so en $dir" \
             "gather qwen-tts, qwen-codec, tts-server and their .so files in $dir")"
    return
  fi
  for name in qwen-tts qwen-codec tts-server; do
    found="$(find "$dir" -mindepth 2 -type f -name "$name" -perm -u+x 2>/dev/null | head -n1)"
    [ -z "$found" ] || cp -f "$found" "$dir/$name"
  done
  while IFS= read -r lib; do
    rm -f "$dir/$(basename "$lib")"
    cp -P "$lib" "$dir/" < /dev/null
  done < <(find "$dir" -mindepth 2 \( -type f -o -type l \) -name '*.so*' 2>/dev/null)
  for name in qwen-tts qwen-codec; do
    [ -x "$dir/$name" ] || die "$(m "la compilación no dejó $name en $dir (revisa la salida de cmake)" \
                                    "the build did not leave $name in $dir (see the cmake output)")"
  done
}

build() {  # build <cpu|vulkan>
  local kind="$1" dir="$ENGINE/bin-$1"
  local -a args=(-S "$SRC" -B "$dir" -DCMAKE_BUILD_TYPE=Release -DGGML_BLAS=OFF
    '-DCMAKE_BUILD_RPATH=$ORIGIN' '-DCMAKE_INSTALL_RPATH=$ORIGIN' -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON)
  if [ "$kind" = vulkan ]; then
    args+=(-DGGML_VULKAN=ON)
    if [ "$SPIRV_MODE" = local ]; then
      args+=("-DCMAKE_PREFIX_PATH=$PREFIX" "-DCMAKE_CXX_FLAGS=-I$PREFIX/include")
    fi
  fi
  say "$(m compilando building) $kind -> $dir"
  tool cmake "${args[@]}"
  tool cmake --build "$dir" --parallel "$JOBS"
  collect "$dir"
}

# --- prueba de arranque --------------------------------------------------------------------------------------
smoke() {  # smoke <carpeta>
  local dir="$1" out rc=0
  say "$(m "probando que $dir/qwen-tts arranca" "checking that $dir/qwen-tts starts")"
  local -a cmd=("$dir/qwen-tts" --help)
  if [ "$ENV_KIND" = flatpak ]; then
    cmd=(flatpak-spawn --host "${cmd[@]}")
  fi
  if [ "$DRY" = 1 ]; then run "${cmd[@]}"; return; fi
  out="$("${cmd[@]}" 2>&1)" || rc=$?
  if [ "$rc" -ge 126 ] || printf '%s' "$out" | grep -qi 'error while loading shared libraries'; then
    printf '%s\n' "$out" | head -n 10 >&2
    die "$(m "$dir/qwen-tts no arranca (código $rc). Librería que falta o binario incompatible con este sistema." \
             "$dir/qwen-tts does not start (code $rc). A missing library or a binary that does not fit this system.")"
  fi
}

# --- ejecución -----------------------------------------------------------------------------------------------
if [ "$DRY" = 1 ]; then
  say "$(m entorno environment): $ENV_KIND $(m '(--dry-run: solo se imprimen las órdenes)' '(--dry-run: the commands are only printed)')"
else
  say "$(m entorno environment): $ENV_KIND"
fi
case "$ENV_KIND" in
  steamos) ensure_sdk ;;
  *) check_native_tools ;;
esac

fetch_source
BUILT=(bin-cpu)
build cpu
if [ "$CPU_ONLY" = 0 ]; then
  if [ "$SPIRV_MODE" = local ]; then ensure_spirv; fi
  build vulkan
  BUILT+=(bin-vulkan)
fi

for b in "${BUILT[@]}"; do smoke "$ENGINE/$b"; done

if [ "$SKIP_MODELS" = 0 ]; then
  say "$(m modelos models) -> gvoice models fetch"
  run env "PYTHONPATH=$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 -m gvoice models fetch
  run env "PYTHONPATH=$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 -m gvoice models verify
fi

echo
if [ "$DRY" = 1 ]; then
  say "$(m "--dry-run: no se ha instalado nada. Quedaría en $ENGINE:" "--dry-run: nothing was installed. It would go to $ENGINE:")"
else
  say "$(m "listo. Instalado en $ENGINE:" "done. Installed in $ENGINE:")"
fi
for b in "${BUILT[@]}"; do echo "  $b/ (qwen-tts, qwen-codec)"; done
if [ "$SKIP_MODELS" = 1 ]; then
  echo "  $(m "modelos: sin bajar (--skip-models); bájalos con: python3 -m gvoice models fetch" \
              "models: not downloaded (--skip-models); download them with: python3 -m gvoice models fetch")"
else
  echo "  $(m "modelos: verificados con gvoice models verify" "models: verified with gvoice models verify")"
fi
echo "$(m "Para activar el motor:  export GVOICE_ENGINE=qwentts" "To turn the engine on:  export GVOICE_ENGINE=qwentts")"
echo "$(m "o en <config>/config.json:" "or in <config>/config.json:")  {\"engine\": \"qwentts\"}"
