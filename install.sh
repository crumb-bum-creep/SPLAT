#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"

echo "== SPLAT RunPod installer =="
echo "repo: $ROOT"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi not found. Start this on a GPU RunPod."
  exit 1
fi

echo "== GPU =="
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || true

if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y --no-install-recommends \
    ffmpeg git python3 python3-pip python3-venv python3-dev \
    build-essential ninja-build cmake pkg-config \
    libgl1 libglib2.0-0 colmap
else
  echo "ERROR: apt-get is required by the turnkey installer."
  exit 1
fi

python3 -m venv --system-site-packages "$VENV"
source "$VENV/bin/activate"
python -m pip install --upgrade pip setuptools wheel

if python - <<'PY'
try:
    import torch
    ok = bool(torch.cuda.is_available())
    if ok:
        print("Using existing torch:", torch.__version__, "CUDA:", torch.version.cuda, "GPU:", torch.cuda.get_device_name(0))
    raise SystemExit(0 if ok else 1)
except Exception:
    raise SystemExit(1)
PY
then
  echo "Existing CUDA PyTorch is usable."
else
  echo "Installing a Blackwell-capable CUDA PyTorch wheel..."
  python -m pip install --upgrade torch torchvision --index-url https://download.pytorch.org/whl/cu128
fi

python -m pip install -r "$ROOT/requirements.txt"
python -m pip install --upgrade nerfstudio

echo "== Verification =="
ffmpeg -version | head -n 1
colmap -h | head -n 2 || true
ns-process-data --help >/dev/null
ns-train splatfacto --help >/dev/null
ns-export gaussian-splat --help >/dev/null

python "$ROOT/splat_house/doctor.py"

chmod +x "$ROOT/run.sh" "$ROOT/serve.sh" "$ROOT/doctor.sh"
echo
echo "INSTALL COMPLETE"
echo "CLI:  $ROOT/run.sh /workspace/YOUR_VIDEO.mp4 balanced"
echo "UI:   $ROOT/serve.sh"
