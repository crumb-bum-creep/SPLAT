#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  echo "SPLAT is not installed yet. Run: cd $ROOT && bash install.sh"
  exit 1
fi
source "$ROOT/.venv/bin/activate"
export PYTHONUNBUFFERED=1
# COLMAP is Qt-linked even for CLI use. RunPod is headless, so force Qt offscreen.
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
exec python "$ROOT/app.py" --host 0.0.0.0 --port "${SPLAT_PORT:-7860}"
