#!/usr/bin/env bash
# Instala el motor real (qwentts.cpp) para galivelop-voice-generator (D17). Sin root. Idempotente.
#
# Uso: bash instalar.sh [--cpu-only] [--skip-models] [--dry-run] [--help]
#
# Entorno (se detecta; GVOICE_INSTALL_ENV=native|steamos|flatpak lo fuerza):
#   flatpak  dentro de un Flatpak (VS Code en la Deck): el compilador del SDK ya esta; los binarios se prueban en
#            el anfitrion con `flatpak-spawn --host`.
#   steamos  sin compilador: se compila con `flatpak run --user org.freedesktop.Sdk//25.08` (se instala si falta).
#   native   distribucion con cmake, g++ y git: directo.
# Otras variables: GVOICE_INSTALL_SDK=present|missing (fuerza la deteccion del SDK), GVOICE_INSTALL_SPIRV=system|local
# (SPIRV-Headers), GVOICE_INSTALL_JOBS (hilos de compilacion). Rutas: GVOICE_DATA_HOME / XDG_DATA_HOME (como `gvoice`).
set -euo pipefail

SDK="org.freedesktop.Sdk//25.08"
SPIRV_REPO="https://github.com/KhronosGroup/SPIRV-Headers"
SPIRV_COMMIT="fbf86836"   # el del banco de la Deck (docs/investigacion/2026-10-25-banco-deck.md)
PREFIX_TAG="[instalar]"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CPU_ONLY=0
SKIP_MODELS=0
DRY=0

usage() {
  cat <<'USAGE'
Uso: bash instalar.sh [--cpu-only] [--skip-models] [--dry-run]

  --cpu-only      compila solo la version CPU (sin Vulkan)
  --skip-models   no baja ni verifica los modelos (`python3 -m gvoice models fetch`)
  --dry-run       imprime cada orden (lineas "DRY-RUN: ...") sin ejecutarla ni tocar disco ni red
  -h, --help      esta ayuda
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --cpu-only) CPU_ONLY=1 ;;
    --skip-models) SKIP_MODELS=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "instalar.sh: opcion desconocida: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

say() { echo "$PREFIX_TAG $*"; }
die() { echo "instalar.sh: error: $*" >&2; exit 1; }

# Ejecuta una orden, o la imprime con --dry-run (una por linea, comillas de shell para que se pueda copiar).
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

# --- entorno -------------------------------------------------------------------------------------------------
detect_env() {
  if [ -n "${GVOICE_INSTALL_ENV:-}" ]; then
    case "$GVOICE_INSTALL_ENV" in
      native|steamos|flatpak) echo "$GVOICE_INSTALL_ENV"; return ;;
      *) die "GVOICE_INSTALL_ENV=$GVOICE_INSTALL_ENV no vale (native, steamos o flatpak)" ;;
    esac
  fi
  if [ -e /.flatpak-info ] || [ -n "${FLATPAK_ID:-}" ]; then echo flatpak; return; fi
  if have cmake && have g++ && have git; then echo native; return; fi
  if have flatpak; then echo steamos; return; fi
  die "no hay compilador (cmake, g++, git) ni flatpak: instala el compilador o flatpak y vuelve a correr instalar.sh"
}

ENV_KIND="$(detect_env)"

# --- catalogo y rutas (una sola fuente: gvoice) --------------------------------------------------------------------
if [ "$DRY" = 0 ] || have python3; then
  mapfile -t INFO < <(cd "$ROOT" && python3 -c '
from gvoice import models, paths
c = models.load("qwentts")
print(c["repo"]); print(c["commit"]); print(paths.engine_dir())') || die "no se pudo leer el catalogo del motor (python3 -m gvoice)"
else
  die "falta python3"
fi
ENGINE_REPO="${INFO[0]}"
ENGINE_COMMIT="${INFO[1]}"
ENGINE="${INFO[2]}"
SRC="$ENGINE/src"
PREFIX="$ENGINE/deps/prefix"
SPIRV_SRC="$ENGINE/deps/SPIRV-Headers"

JOBS="${GVOICE_INSTALL_JOBS:-$( (nproc 2>/dev/null || echo 4) | head -n1)}"

# Ejecuta una herramienta de compilacion: en SteamOS, dentro del SDK de Flatpak.
tool() {
  if [ "$ENV_KIND" = steamos ]; then
    local cmd="$1"; shift
    run flatpak run --user "--filesystem=$ENGINE" "--command=$cmd" "$SDK" "$@"
  else
    run "$@"
  fi
}

# --- SDK (solo SteamOS) --------------------------------------------------------------------------------------
ensure_sdk() {
  have flatpak || [ "$DRY" = 1 ] || die "falta flatpak: en SteamOS viene de serie; si no, instala un compilador (cmake, g++, git)"
  local state="${GVOICE_INSTALL_SDK:-}"
  if [ -z "$state" ]; then
    if have flatpak && flatpak info --user "$SDK" >/dev/null 2>&1; then state=present; else state=missing; fi
  fi
  if [ "$state" = missing ]; then
    say "instalando el SDK $SDK (flatpak --user, sin root; baja unos cientos de MB)"
    run flatpak --user install -y --noninteractive flathub "$SDK"
  else
    say "SDK $SDK ya instalado"
  fi
}

check_native_tools() {
  local missing=""
  for t in cmake g++ git; do have "$t" || missing="$missing $t"; done
  [ -z "$missing" ] || [ "$DRY" = 1 ] || die "faltan herramientas:$missing (instalalas o corre instalar.sh en SteamOS con flatpak)"
}

# --- motor ---------------------------------------------------------------------------------------------------
fetch_source() {
  say "motor $ENGINE_REPO @ $ENGINE_COMMIT -> $SRC"
  run mkdir -p "$ENGINE"
  if [ -d "$SRC/.git" ]; then
    tool git -C "$SRC" fetch origin
  else
    tool git clone "$ENGINE_REPO" "$SRC"
  fi
  tool git -C "$SRC" checkout "$ENGINE_COMMIT"
  tool git -C "$SRC" submodule update --init --recursive
}

spirv_mode() {
  case "${GVOICE_INSTALL_SPIRV:-}" in
    system|local) echo "$GVOICE_INSTALL_SPIRV"; return ;;
    "") ;;
    *) die "GVOICE_INSTALL_SPIRV=$GVOICE_INSTALL_SPIRV no vale (system o local)" ;;
  esac
  if [ "$ENV_KIND" = native ] && [ -e /usr/include/spirv/unified1/spirv.hpp ]; then echo system; else echo local; fi
}

ensure_spirv() {
  if [ -e "$PREFIX/include/spirv/unified1/spirv.hpp" ]; then
    say "SPIRV-Headers ya en $PREFIX"
    return
  fi
  say "SPIRV-Headers $SPIRV_COMMIT -> $PREFIX (sin tocar el sistema)"
  if [ ! -d "$SPIRV_SRC/.git" ]; then
    tool git clone "$SPIRV_REPO" "$SPIRV_SRC"
  fi
  tool git -C "$SPIRV_SRC" checkout "$SPIRV_COMMIT"
  tool cmake -S "$SPIRV_SRC" -B "$SPIRV_SRC/build" "-DCMAKE_INSTALL_PREFIX=$PREFIX"
  tool cmake --install "$SPIRV_SRC/build"
}

# Los binarios y sus .so quedan en la raiz de la carpeta (el rpath `$ORIGIN` los busca ahi).
collect() {
  local dir="$1" name found lib
  if [ "$DRY" = 1 ]; then
    say "reunir qwen-tts, qwen-codec, tts-server y sus .so en $dir"
    return
  fi
  for name in qwen-tts qwen-codec tts-server; do
    if [ ! -x "$dir/$name" ]; then
      found="$(find "$dir" -mindepth 2 -type f -name "$name" -perm -u+x 2>/dev/null | head -n1)"
      [ -z "$found" ] || cp -f "$found" "$dir/$name"
    fi
  done
  while IFS= read -r lib; do
    [ -e "$dir/$(basename "$lib")" ] || cp -P "$lib" "$dir/"
  done < <(find "$dir" -mindepth 2 \( -type f -o -type l \) -name '*.so*' 2>/dev/null)
  for name in qwen-tts qwen-codec; do
    [ -x "$dir/$name" ] || die "la compilacion no dejo $name en $dir (revisa la salida de cmake)"
  done
}

build() {  # build <cpu|vulkan>
  local kind="$1" dir="$ENGINE/bin-$1"
  local -a args=(-S "$SRC" -B "$dir" -DCMAKE_BUILD_TYPE=Release -DGGML_BLAS=OFF
    '-DCMAKE_BUILD_RPATH=$ORIGIN' '-DCMAKE_INSTALL_RPATH=$ORIGIN' -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON)
  if [ "$kind" = vulkan ]; then
    args+=(-DGGML_VULKAN=ON)
    if [ "$(spirv_mode)" = local ]; then
      args+=("-DCMAKE_PREFIX_PATH=$PREFIX" "-DCMAKE_CXX_FLAGS=-I$PREFIX/include")
    fi
  fi
  say "compilando $kind -> $dir"
  tool cmake "${args[@]}"
  tool cmake --build "$dir" --parallel "$JOBS"
  collect "$dir"
}

# --- prueba de arranque --------------------------------------------------------------------------------------
smoke() {  # smoke <carpeta>
  local dir="$1" out rc=0
  say "probando que $dir/qwen-tts arranca"
  local -a cmd=("$dir/qwen-tts" --help)
  if [ "$ENV_KIND" = flatpak ]; then
    cmd=(flatpak-spawn --host "${cmd[@]}")
  fi
  if [ "$DRY" = 1 ]; then run "${cmd[@]}"; return; fi
  out="$("${cmd[@]}" 2>&1)" || rc=$?
  if [ "$rc" -ge 126 ] || printf '%s' "$out" | grep -qi 'error while loading shared libraries'; then
    printf '%s\n' "$out" | head -n 10 >&2
    die "$dir/qwen-tts no arranca (codigo $rc). Libreria que falta o binario incompatible con este sistema."
  fi
}

# --- ejecucion -----------------------------------------------------------------------------------------------
say "entorno: $ENV_KIND$([ "$DRY" = 1 ] && echo ' (--dry-run: solo se imprimen las ordenes)')"
case "$ENV_KIND" in
  steamos) ensure_sdk ;;
  *) check_native_tools ;;
esac

fetch_source
BUILT=(bin-cpu)
build cpu
if [ "$CPU_ONLY" = 0 ]; then
  if [ "$(spirv_mode)" = local ]; then ensure_spirv; fi
  build vulkan
  BUILT+=(bin-vulkan)
fi

for b in "${BUILT[@]}"; do smoke "$ENGINE/$b"; done

if [ "$SKIP_MODELS" = 0 ]; then
  say "modelos -> gvoice models fetch"
  run env "PYTHONPATH=$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 -m gvoice models fetch
  run env "PYTHONPATH=$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 -m gvoice models verify
fi

echo
if [ "$DRY" = 1 ]; then say "--dry-run: no se ha instalado nada. Quedaria en $ENGINE:"; else say "listo. Instalado en $ENGINE:"; fi
for b in "${BUILT[@]}"; do echo "  $b/ (qwen-tts, qwen-codec)"; done
if [ "$SKIP_MODELS" = 1 ]; then
  echo "  modelos: sin bajar (--skip-models); bajalos con: python3 -m gvoice models fetch"
else
  echo "  modelos: verificados con gvoice models verify"
fi
echo "Para activar el motor:  export GVOICE_ENGINE=qwentts"
echo "o en <config>/config.json:  {\"engine\": \"qwentts\"}"
