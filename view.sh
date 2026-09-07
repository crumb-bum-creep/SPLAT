#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  echo "SPLAT is not installed yet. Run: cd $ROOT && bash install.sh"
  exit 1
fi
source "$ROOT/.venv/bin/activate"

JOB="${1:-}"
if [ -z "$JOB" ]; then
  JOB="$("$ROOT/.venv/bin/python" - <<'PY'
from pathlib import Path
root = Path("runs")
reports = sorted(root.glob("*/report.json"), key=lambda p: p.stat().st_mtime, reverse=True)
print(reports[0].parent if reports else "")
PY
)"
fi

if [ -z "$JOB" ] || [ ! -d "$JOB" ]; then
  echo "Usage: ./view.sh /workspace/SPLAT/runs/<job>"
  exit 2
fi

CONFIG="$("$ROOT/.venv/bin/python" - "$JOB" <<'PY'
import json, sys
from pathlib import Path
job = Path(sys.argv[1])
report = job / "report.json"
if report.exists():
    print(json.loads(report.read_text()).get("nerfstudio_config", ""))
else:
    configs = sorted(job.rglob("config.yml"), key=lambda p: p.stat().st_mtime, reverse=True)
    print(configs[0] if configs else "")
PY
)"

if [ -z "$CONFIG" ] || [ ! -f "$CONFIG" ]; then
  echo "Could not find Nerfstudio config.yml in $JOB"
  exit 2
fi

echo "Opening SPLAT viewer on 0.0.0.0:${SPLAT_PORT:-7860}"
exec ns-viewer --load-config "$CONFIG" --viewer.websocket-host 0.0.0.0 --viewer.websocket-port "${SPLAT_PORT:-7860}"
