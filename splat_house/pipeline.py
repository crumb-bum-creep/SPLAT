from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rich.console import Console

from .keyframes import extract_candidates, probe_video, select_keyframes, target_frames

CONSOLE = Console()

PRESETS = {
    "preview": {
        "candidate_fps": 5.0,
        "frames_per_second_of_video": 2.5,
        "min_frames": 450,
        "max_frames": 900,
        "max_width": 1280,
        "iterations": 7000,
        "method": "splatfacto",
        "registration_floor": 0.55,
    },
    "balanced": {
        "candidate_fps": 2.0,
        "frames_per_second_of_video": 0.56,
        "min_frames": 850,
        "max_frames": 1500,
        "max_width": 1600,
        "iterations": 12000,
        "method": "splatfacto",
        "registration_floor": 0.65,
    },
    "quality": {
        "candidate_fps": 2.5,
        "frames_per_second_of_video": 0.82,
        "min_frames": 1200,
        "max_frames": 2200,
        "max_width": 1920,
        "iterations": 20000,
        "method": "splatfacto-big",
        "registration_floor": 0.70,
    },
}


@dataclass
class Job:
    root: Path
    selected: Path
    dataset: Path
    training: Path
    export: Path
    logs: Path


def run(cmd: list[str], log_path: Path | None = None, env: dict | None = None) -> None:
    CONSOLE.print("[bold cyan]$[/] " + shlex.join(cmd))
    if log_path is None:
        subprocess.run(cmd, check=True, env=env)
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w") as log:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
        assert p.stdout is not None
        for line in p.stdout:
            sys.stdout.write(line)
            log.write(line)
        rc = p.wait()
        if rc:
            raise subprocess.CalledProcessError(rc, cmd)


def make_job(runs_dir: Path, video: Path, name: str | None) -> Job:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = name or f"{video.stem}_{stamp}"
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in base)
    root = runs_dir / safe
    if root.exists():
        suffix = 2
        while (runs_dir / f"{safe}_{suffix}").exists():
            suffix += 1
        root = runs_dir / f"{safe}_{suffix}"
    for d in ("selected", "dataset", "training", "export", "logs", "candidates"):
        (root / d).mkdir(parents=True, exist_ok=True)
    return Job(root, root / "selected", root / "dataset", root / "training", root / "export", root / "logs")


def registration_ratio(dataset: Path, selected_count: int) -> tuple[float, int]:
    tf = dataset / "transforms.json"
    if not tf.exists():
        return 0.0, 0
    try:
        frames = len(json.loads(tf.read_text()).get("frames", []))
    except Exception:
        return 0.0, 0
    return (frames / max(selected_count, 1)), frames


def process_poses(job: Job, selected_count: int, preset: dict, retry_vocab: bool = True) -> tuple[float, int, str]:
    # Ubuntu's distro COLMAP often has the OpenGL SIFT backend but not a headless CUDA
    # SIFT backend. Nerfstudio defaults to GPU=True, which then tries to create an
    # OpenGL context and aborts on cloud/headless pods. CPU SIFT is slower, but for
    # our capped keyframe sets it is reliable and keeps the RTX free for 3DGS training.
    CONSOLE.print("[cyan]COLMAP SfM: headless-safe CPU SIFT/matching; GPU stays available for splat training.[/]")
    common = [
        "ns-process-data", "images",
        "--data", str(job.selected),
        "--output-dir", str(job.dataset),
        "--camera-type", "perspective",
        "--matching-method", "sequential",
        "--sfm-tool", "colmap",
        "--no-gpu",
        "--num-downscales", "2",
    ]
    run(common, job.logs / "poses-sequential.log")
    ratio, registered = registration_ratio(job.dataset, selected_count)
    method = "sequential"

    if retry_vocab and ratio < float(preset["registration_floor"]):
        CONSOLE.print(
            f"[yellow]Only {registered}/{selected_count} frames registered ({ratio:.1%}). "
            "Retrying pose solve with vocabulary-tree matching.[/]"
        )
        shutil.rmtree(job.dataset, ignore_errors=True)
        job.dataset.mkdir(parents=True, exist_ok=True)
        retry = [
            "ns-process-data", "images",
            "--data", str(job.selected),
            "--output-dir", str(job.dataset),
            "--camera-type", "perspective",
            "--matching-method", "vocab_tree",
            "--sfm-tool", "colmap",
            "--no-gpu",
            "--num-downscales", "2",
        ]
        run(retry, job.logs / "poses-vocab-tree.log")
        ratio2, registered2 = registration_ratio(job.dataset, selected_count)
        if ratio2 >= ratio:
            ratio, registered, method = ratio2, registered2, "vocab_tree"

    return ratio, registered, method


def locate_config(job: Job) -> Path:
    configs = sorted(job.training.rglob("config.yml"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not configs:
        raise RuntimeError("Training completed but no Nerfstudio config.yml was found.")
    return configs[0]


def train(job: Job, preset: dict) -> Path:
    method = str(preset["method"])
    iterations = int(preset["iterations"])
    cmd = [
        "ns-train", method,
        "--data", str(job.dataset),
        "--output-dir", str(job.training),
        "--experiment-name", "house",
        "--timestamp", "run",
        "--max-num-iterations", str(iterations),
        "--viewer.quit-on-train-completion=True",
        "--logging.local-writer.enable=True",
        "--pipeline.model.use-scale-regularization=True",
    ]
    run(cmd, job.logs / "training.log")
    return locate_config(job)


def export_splat(job: Job, config: Path) -> Path:
    out = job.export / "splat"
    out.mkdir(parents=True, exist_ok=True)
    run(
        ["ns-export", "gaussian-splat", "--load-config", str(config), "--output-dir", str(out)],
        job.logs / "export.log",
    )
    plys = sorted(out.rglob("*.ply"), key=lambda p: p.stat().st_size, reverse=True)
    if not plys:
        raise RuntimeError("Export command completed but no .ply splat was produced.")
    final = job.export / "house.ply"
    shutil.copy2(plys[0], final)
    return final


def write_report(job: Job, report: dict) -> None:
    (job.root / "report.json").write_text(json.dumps(report, indent=2))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="SPLAT",
        description="Turn a long, continuous house walkthrough into a 3D Gaussian Splat.",
    )
    p.add_argument("video", type=Path, help="Path to MP4/MOV walkthrough video")
    p.add_argument("preset", nargs="?", default="balanced", choices=PRESETS)
    p.add_argument("--name", default=None, help="Optional job name")
    p.add_argument("--runs-dir", type=Path, default=Path("runs"))
    p.add_argument("--keep-candidates", action="store_true", help="Keep temporary candidate JPGs")
    p.add_argument("--no-pose-retry", action="store_true", help="Do not retry low-registration COLMAP solve")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    video = args.video.expanduser().resolve()
    if not video.is_file():
        CONSOLE.print(f"[red]Video not found: {video}[/]")
        return 2

    repo_root = Path(__file__).resolve().parents[1]
    runs_dir = args.runs_dir
    if not runs_dir.is_absolute():
        runs_dir = repo_root / runs_dir
    runs_dir.mkdir(parents=True, exist_ok=True)

    preset = PRESETS[args.preset]
    info = probe_video(video)
    target = target_frames(info.duration, preset)
    job = make_job(runs_dir, video, args.name)
    start = time.time()

    CONSOLE.rule("[bold green]SPLAT")
    CONSOLE.print(f"video:     {video}")
    CONSOLE.print(f"duration:  {info.duration/60:.1f} min")
    CONSOLE.print(f"source:    {info.width}x{info.height} @ {info.fps:.2f} fps")
    CONSOLE.print(f"preset:    {args.preset}")
    CONSOLE.print(f"budget:    {target} selected frames max")
    CONSOLE.print(f"job:       {job.root}")
    CONSOLE.rule()

    candidates = job.root / "candidates"
    extract_candidates(video, candidates, float(preset["candidate_fps"]), int(preset["max_width"]))
    manifest = select_keyframes(candidates, job.selected, target)
    selected_count = int(manifest["selected_count"])
    if selected_count < 50:
        raise RuntimeError(f"Only {selected_count} usable frames were selected.")

    if not args.keep_candidates:
        shutil.rmtree(candidates, ignore_errors=True)

    ratio, registered, pose_method = process_poses(
        job, selected_count, preset, retry_vocab=not args.no_pose_retry
    )
    if ratio < 0.35:
        raise RuntimeError(
            f"Pose solve registered only {registered}/{selected_count} frames ({ratio:.1%}). "
            "The walkthrough may contain too much blur, too little overlap, or major camera/lens changes."
        )

    config = train(job, preset)
    ply = export_splat(job, config)

    elapsed = time.time() - start
    report = {
        "video": str(video),
        "preset": args.preset,
        "duration_seconds": info.duration,
        "source_resolution": [info.width, info.height],
        "selected_frames": selected_count,
        "registered_frames": registered,
        "registration_ratio": ratio,
        "pose_method": pose_method,
        "training_method": preset["method"],
        "iterations": preset["iterations"],
        "elapsed_seconds": round(elapsed, 2),
        "splat": str(ply),
        "nerfstudio_config": str(config),
    }
    write_report(job, report)

    CONSOLE.rule("[bold green]DONE")
    CONSOLE.print(f"[bold]3D splat:[/] {ply}")
    CONSOLE.print(f"registered: {registered}/{selected_count} ({ratio:.1%})")
    CONSOLE.print(f"elapsed:    {elapsed/60:.1f} min")
    CONSOLE.print(f"job:        {job.root}")
    CONSOLE.print()
    CONSOLE.print("To open the interactive viewer on RunPod port 7860:")
    CONSOLE.print(f"  cd {shlex.quote(str(repo_root))} && ./view.sh {shlex.quote(str(job.root))}")
    CONSOLE.rule()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
