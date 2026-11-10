#!/bin/bash
# Instala reel-analyzer dentro de esta carpeta (no toca nada del sistema):
#   1. crea un entorno virtual en .venv
#   2. instala las dependencias de Python
#   3. deja el comando `reel` en ~/.local/bin
set -e
DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$(uname)" != "Darwin" ]; then
  echo "❌ Por ahora reel-analyzer solo funciona en macOS."
  exit 1
fi
if ! command -v python3 >/dev/null; then
  echo "❌ No encontré python3. Instálalo (por ejemplo: brew install python) y vuelve a correr esto."
  exit 1
fi

echo "→ Creando el entorno virtual en $DIR/.venv"
python3 -m venv "$DIR/.venv"
echo "→ Instalando dependencias (puede tardar unos minutos)"
"$DIR/.venv/bin/python" -m pip install -q --upgrade pip
"$DIR/.venv/bin/python" -m pip install -q -r "$DIR/requirements.txt"

mkdir -p "$HOME/.local/bin"
ln -sf "$DIR/reel" "$HOME/.local/bin/reel"
echo "✅ Listo: comando instalado en ~/.local/bin/reel"

case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo "⚠️  ~/.local/bin no está en tu PATH. Agrégalo con:"
     echo "    echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc && source ~/.zshrc" ;;
esac
if ! command -v ffmpeg >/dev/null; then
  echo "⚠️  Falta ffmpeg. Instálalo con: brew install ffmpeg"
fi
echo "Siguiente paso: reel doctor"
