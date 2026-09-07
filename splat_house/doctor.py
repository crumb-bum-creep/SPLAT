from __future__ import annotations

import shutil
import subprocess


def line(cmd: list[str]) -> str:
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=20)
        out = (p.stdout or p.stderr).strip().splitlines()
        return out[0] if out else f"exit={p.returncode}"
    except Exception as e:
        return f"ERROR: {e}"


def main() -> int:
    print("== SPLAT doctor ==")
    for exe in ("ffmpeg", "ffprobe", "colmap", "ns-process-data", "ns-train", "ns-export"):
        path = shutil.which(exe)
        print(f"{exe:16} {path or 'MISSING'}")

    try:
        import torch
        print(f"torch            {torch.__version__}")
        print(f"torch CUDA       {torch.version.cuda}")
        print(f"cuda available   {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"GPU              {torch.cuda.get_device_name(0)}")
            props = torch.cuda.get_device_properties(0)
            print(f"VRAM             {props.total_memory / 1024**3:.1f} GiB")
            print(f"capability       sm_{props.major}{props.minor}")
    except Exception as e:
        print(f"torch ERROR      {e}")
        return 2

    print(f"ffmpeg           {line(['ffmpeg', '-version'])}")
    print(f"colmap           {line(['colmap', '-h'])}")

    missing = [x for x in ("ffmpeg", "ffprobe", "colmap", "ns-process-data", "ns-train", "ns-export") if not shutil.which(x)]
    if missing:
        print("MISSING:", ", ".join(missing))
        return 2
    print("doctor: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
