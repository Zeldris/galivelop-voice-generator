#!/usr/bin/env bash
# instalar.sh — instala el motor de voz (qwentts.cpp) y sus modelos en la carpeta de datos (D17).
# Compila en el SDK de Flatpak (org.freedesktop.Sdk//25.08) si no hay compilador, sin root ni paquetes del sistema.
set -euo pipefail

COMMIT="5916bf7c79dbb4e66fc059cdc507a79a23a28bb4"
SPIRV_COMMIT="fbf86836"
URL_MOTOR="https://github.com/ServeurpersoCom/qwentts.cpp"
URL_SPIRV="https://github.com/KhronosGroup/SPIRV-Headers"
URL_MODELOS="https://huggingface.co/Serveurperso/Qwen3-TTS-GGUF/resolve/main"
SDK="org.freedesktop.Sdk//25.08"
# Archivo de marca del sandbox de Flatpak (variable solo para poder probarlo).
FLATPAK_INFO="${GVOICE_FLATPAK_INFO:-/.flatpak-info}"

# Modelos: "archivo sha256" (tabla de docs/investigacion/2026-10-25-banco-deck.md).
MODELOS=(
  "qwen-talker-0.6b-base-Q8_0.gguf d54dbaf10591421fa764ed630d764efa717ae40cd959bd48c66d4eb1af226426"
  "qwen-talker-1.7b-base-Q8_0.gguf 4b9a33a236908dd9435a42f7a396e38038329d053b704342a6413c08544c4fda"
  "qwen-talker-1.7b-voicedesign-Q8_0.gguf 575610ab1ddcca4dca6bd9a64bcd859d93bbad8764f9cab24e1dbc0c51f62276"
  "qwen-tokenizer-12hz-Q8_0.gguf 1883beeed99348fc35e23dd225e9082f93f6f8c109330a33d935baa8acdbfd94"
)
CODEC_MODELO="qwen-tokenizer-12hz-Q8_0.gguf"
BINARIOS=(qwen-tts qwen-codec tts-server)

SOLO_CPU=0
SIN_MODELOS=0
PLAN=0

ayuda() {
  cat <<'AYUDA'
Uso: ./instalar.sh [opciones]

Instala el motor de voz (qwentts.cpp) y los modelos en la carpeta de datos:
  ${GVOICE_DATA_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/galivelop-voice}

Opciones:
  --ayuda, --help   Muestra esta ayuda y sale.
  --solo-cpu        Compila solo la versión de CPU (sin Vulkan).
  --sin-modelos     No descarga los modelos.
  --plan            Imprime los pasos que daría, con el sitio de compilación decidido,
                    y sale sin tocar nada.

Compila directo si hay compilador de C++ y cmake; si no, dentro del SDK de Flatpak
(org.freedesktop.Sdk//25.08, con --user, sin root). Es idempotente: repetirlo salta lo ya hecho.
AYUDA
}

di() { printf '%s\n' "$*"; }
aviso() { printf 'AVISO: %s\n' "$*" >&2; }
falla() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --ayuda|--help) ayuda; exit 0 ;;
    --solo-cpu) SOLO_CPU=1 ;;
    --sin-modelos) SIN_MODELOS=1 ;;
    --plan) PLAN=1 ;;
    *) printf 'ERROR: opción desconocida: %s (usa --ayuda)\n' "$1" >&2; exit 2 ;;
  esac
  shift
done

# Carpeta de datos: la misma que gvoice/paths.py (GVOICE_DATA_HOME, luego XDG_DATA_HOME absoluta, luego ~/.local/share).
if [ -n "${GVOICE_DATA_HOME:-}" ]; then
  DATA="$GVOICE_DATA_HOME"
elif [ -n "${XDG_DATA_HOME:-}" ] && [ "${XDG_DATA_HOME:0:1}" = "/" ]; then
  DATA="$XDG_DATA_HOME/galivelop-voice"
else
  DATA="$HOME/.local/share/galivelop-voice"
fi
MODELS="${GVOICE_MODELS_HOME:-$DATA/models}"
ENGINE="$DATA/engine"
SRC="$ENGINE/src"
PREFIX="$ENGINE/deps/prefix"

EN_SANDBOX=0
if [ -e "$FLATPAK_INFO" ]; then EN_SANDBOX=1; fi

# Decide dónde se compila: directo, en el SDK de Flatpak, o nada.
SITIO="ninguno"
if command -v c++ >/dev/null 2>&1 && command -v cmake >/dev/null 2>&1; then
  if [ "$EN_SANDBOX" = 1 ]; then SITIO="sandbox-sdk"; else SITIO="directo"; fi
elif [ "$EN_SANDBOX" = 0 ] && command -v flatpak >/dev/null 2>&1; then
  SITIO="flatpak-sdk"
fi

describe_sitio() {
  case "$SITIO" in
    directo) di "compilador y cmake del sistema (compilación directa)" ;;
    sandbox-sdk) di "compilador y cmake del SDK dentro del sandbox de Flatpak; las pruebas en el anfitrión con flatpak-spawn --host" ;;
    flatpak-sdk) di "dentro del SDK de Flatpak ($SDK, flatpak run --user)" ;;
    *) di "ninguno" ;;
  esac
}

if [ "$PLAN" = 1 ]; then
  di "Plan de instalación (no se toca nada):"
  di "  carpeta de datos: $DATA"
  di "  sitio de compilación: $SITIO — $(describe_sitio)"
  if [ "$SITIO" = "ninguno" ]; then di "  (sin compilador ni flatpak: la instalación se detendría aquí)"; fi
  if [ "$SITIO" = "flatpak-sdk" ]; then di "  0. instalar el SDK $SDK con flatpak install --user si falta (avisándolo antes)"; fi
  di "  1. clonar $URL_MOTOR en $SRC y fijar el commit $COMMIT"
  if [ "$SOLO_CPU" = 0 ]; then
    di "  2. clonar SPIRV-Headers ($SPIRV_COMMIT) e instalarlo en $PREFIX (solo para Vulkan)"
  else
    di "  2. (omitido: --solo-cpu) SPIRV-Headers"
  fi
  di "  3. compilar CPU sin BLAS en $ENGINE/bin-cpu (rpath \$ORIGIN)"
  if [ "$SOLO_CPU" = 0 ]; then
    di "  4. compilar Vulkan en $ENGINE/bin-vulkan (si falla, aviso: la CPU sigue valiendo)"
  else
    di "  4. (omitido: --solo-cpu) compilación Vulkan"
  fi
  if [ "$SIN_MODELOS" = 0 ]; then
    for m in "${MODELOS[@]}"; do di "  5. modelo ${m%% *} desde $URL_MODELOS en $MODELS (sha256 comprobado)"; done
  else
    di "  5. (omitido: --sin-modelos) descarga de modelos"
  fi
  di "  6. prueba de arranque de ${BINARIOS[*]} en cada carpeta compilada"
  di "  7. escribir $ENGINE/install.json"
  exit 0
fi

[ "$SITIO" != "ninguno" ] || falla "no hay compilador de C++ con cmake ni flatpak. Instala uno de los dos (en SteamOS, flatpak ya viene) y repite."
command -v git >/dev/null 2>&1 || falla "falta git."
command -v curl >/dev/null 2>&1 || falla "falta curl."
command -v sha256sum >/dev/null 2>&1 || falla "falta sha256sum."

mkdir -p "$ENGINE" "$MODELS"

# Ejecuta una orden de compilación en el sitio decidido.
en_sdk() {
  if [ "$SITIO" = "flatpak-sdk" ]; then
    local prog="$1"; shift
    flatpak run --user --command="$prog" --filesystem="$DATA" --filesystem="$MODELS" "$SDK" "$@"
  else
    "$@"
  fi
}

# Ejecuta una orden en el anfitrión (dentro del sandbox de Flatpak hace falta flatpak-spawn).
en_anfitrion() {
  if [ "$EN_SANDBOX" = 1 ] && command -v flatpak-spawn >/dev/null 2>&1; then
    flatpak-spawn --host "$@"
  else
    "$@"
  fi
}

if [ "$SITIO" = "flatpak-sdk" ]; then
  if ! flatpak info --user "$SDK" >/dev/null 2>&1 && ! flatpak info "$SDK" >/dev/null 2>&1; then
    di "Falta el SDK $SDK: se instala con flatpak install --user (puede tardar y bajar cientos de MB)."
    flatpak install --user -y flathub "$SDK"
  fi
fi

di "Carpeta de datos: $DATA"
di "Sitio de compilación: $SITIO"

# 1. Motor en el commit fijado.
if [ ! -d "$SRC/.git" ]; then
  di "Clonando $URL_MOTOR..."
  git clone "$URL_MOTOR" "$SRC"
fi
if [ "$(git -C "$SRC" rev-parse HEAD)" != "$COMMIT" ]; then
  git -C "$SRC" fetch origin "$COMMIT" 2>/dev/null || git -C "$SRC" fetch origin
  git -C "$SRC" checkout -q "$COMMIT"
fi
[ "$(git -C "$SRC" rev-parse HEAD)" = "$COMMIT" ] || falla "el motor no está en el commit $COMMIT."
git -C "$SRC" submodule update --init --recursive >/dev/null 2>&1 || true

hilos="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"

# Copia los binarios y las bibliotecas compartidas de una compilación a su carpeta final.
instalar_binarios() {  # <carpeta de compilación> <carpeta final>
  local build="$1" bin="$2" b
  mkdir -p "$bin"
  for b in "${BINARIOS[@]}"; do cp -f "$build/$b" "$bin/$b"; done
  find "$build" -maxdepth 1 \( -name '*.so' -o -name '*.so.*' \) -exec cp -af {} "$bin/" \;
  rm -rf "$build"
}

compilar() {  # <nombre> <carpeta final> [opciones de cmake...]
  local nombre="$1" bin="$2"; shift 2
  local build="$ENGINE/build-$nombre"
  rm -rf "$build"
  en_sdk cmake -S "$SRC" -B "$build" -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_BUILD_RPATH='$ORIGIN' -DCMAKE_INSTALL_RPATH='$ORIGIN' -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON "$@" || return 1
  en_sdk cmake --build "$build" --config Release -j "$hilos" || return 1
  instalar_binarios "$build" "$bin"
}

ya_compilado() {  # <carpeta final>: mismo commit y binarios presentes
  local bin="$1" b
  [ -f "$ENGINE/install.json" ] || return 1
  grep -q "\"commit\": \"$COMMIT\"" "$ENGINE/install.json" || return 1
  for b in "${BINARIOS[@]}"; do [ -x "$bin/$b" ] || return 1; done
}

DISPOSITIVOS=()

# 3. CPU (fatal si falla).
if ya_compilado "$ENGINE/bin-cpu"; then
  di "CPU: ya compilada en el commit ${COMMIT:0:7}, se salta."
else
  di "Compilando CPU (sin BLAS)..."
  compilar cpu "$ENGINE/bin-cpu" -DGGML_BLAS=OFF || falla "falló la compilación de CPU (es obligatoria)."
fi
DISPOSITIVOS+=("cpu")

# 2 y 4. Vulkan (aviso si falla, D4).
vulkan() {
  if [ ! -f "$PREFIX/include/spirv/unified1/spirv.hpp" ]; then
    local spirv="$ENGINE/deps/SPIRV-Headers"
    if [ ! -d "$spirv/.git" ]; then git clone "$URL_SPIRV" "$spirv"; fi
    git -C "$spirv" checkout -q "$SPIRV_COMMIT"
    en_sdk cmake -S "$spirv" -B "$spirv/build" -DCMAKE_INSTALL_PREFIX="$PREFIX"
    en_sdk cmake --install "$spirv/build"
  fi
  compilar vulkan "$ENGINE/bin-vulkan" -DGGML_BLAS=OFF -DGGML_VULKAN=ON \
    -DCMAKE_PREFIX_PATH="$PREFIX" -DCMAKE_CXX_FLAGS="-I$PREFIX/include"
}
if [ "$SOLO_CPU" = 0 ]; then
  if ya_compilado "$ENGINE/bin-vulkan"; then
    di "Vulkan: ya compilado en el commit ${COMMIT:0:7}, se salta."
    DISPOSITIVOS=("Vulkan0" "${DISPOSITIVOS[@]}")
  else
    di "Compilando Vulkan..."
    if (vulkan); then
      DISPOSITIVOS=("Vulkan0" "${DISPOSITIVOS[@]}")
    else
      aviso "falló la compilación de Vulkan; la CPU sigue siendo utilizable (D4)."
      rm -rf "$ENGINE/bin-vulkan" "$ENGINE/build-vulkan"
    fi
  fi
fi

# Modelos.
sha_de() { sha256sum "$1" | cut -d' ' -f1; }
if [ "$SIN_MODELOS" = 0 ]; then
  for m in "${MODELOS[@]}"; do
    f="${m%% *}"; sha="${m##* }"; dest="$MODELS/$f"
    if [ -f "$dest" ] && [ "$(sha_de "$dest")" = "$sha" ]; then
      di "Modelo $f: ya está con el sha256 correcto, se salta."
      continue
    fi
    di "Descargando $f..."
    tmp="$dest.part"
    if curl -fL --retry 3 -o "$tmp" "$URL_MODELOS/$f"; then mv "$tmp" "$dest"; else rm -f "$tmp"; falla "no se pudo descargar $f."; fi
    if [ "$(sha_de "$dest")" != "$sha" ]; then
      rm -f "$dest"
      falla "el sha256 de $f no coincide con el esperado ($sha); se borró."
    fi
  done
fi

# Prueba de arranque: cada binario carga sus bibliotecas; qwen-codec además carga el códec si está.
prueba() {  # <carpeta>
  local bin="$1" b salida codec="$MODELS/$CODEC_MODELO"
  for b in "${BINARIOS[@]}"; do
    salida="$(en_anfitrion "$bin/$b" --help 2>&1 || true)"
    if printf '%s' "$salida" | grep -qiE 'error while loading shared libraries|cannot open shared object|not found'; then
      printf '%s\n' "$salida" >&2
      return 1
    fi
  done
  # La carga del códec sin talker no se ha probado en la Deck: si falla, solo avisa.
  if [ -f "$codec" ] && ! en_anfitrion "$bin/qwen-codec" --model "$codec" >/dev/null 2>&1; then
    aviso "qwen-codec de $bin no cargó el códec sin --talker; compruébalo con gvoice doctor."
  fi
}
FINALES=()
for dev in "${DISPOSITIVOS[@]}"; do
  carpeta="$ENGINE/bin-cpu"
  if [ "$dev" = "Vulkan0" ]; then carpeta="$ENGINE/bin-vulkan"; fi
  if prueba "$carpeta"; then
    di "Prueba de arranque de $carpeta: bien."
    FINALES+=("$dev")
  elif [ "$dev" = "cpu" ]; then
    falla "los binarios de $carpeta no arrancan."
  else
    aviso "los binarios de $carpeta no arrancan; se quita Vulkan0 de los dispositivos."
  fi
done

# install.json
lista=""
for d in "${FINALES[@]}"; do lista="${lista:+$lista, }\"$d\""; done
cat > "$ENGINE/install.json.tmp" <<JSON
{"commit": "$COMMIT", "devices": [$lista], "installedAt": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"}
JSON
mv "$ENGINE/install.json.tmp" "$ENGINE/install.json"
di "Listo: $ENGINE/install.json (dispositivos: ${FINALES[*]})."
