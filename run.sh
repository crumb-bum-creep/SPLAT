#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  echo "SPLAT is not installed yet. Run: cd $ROOT && bash install.sh"
  exit 1
fi
source "$ROOT/.venv/bin/activate"
exec python -m splat_house.pipeline "$@"
