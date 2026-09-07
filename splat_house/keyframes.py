from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class VideoInfo:
    duration: float
    width: int
    height: int
    fps: float
    frames: int


def probe_video(video: Path) -> VideoInfo:
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,nb_frames:format=duration",
        "-of", "json", str(video),
    ]
    data = json.loads(subprocess.check_output(cmd, text=True))
    stream = data["streams"][0]
    duration = float(data["format"]["duration"])
    num, den = stream.get("r_frame_rate", "30/1").split("/")
    fps = float(num) / max(float(den), 1.0)
    frames_raw = stream.get("nb_frames")
    frames = int(frames_raw) if frames_raw and str(frames_raw).isdigit() else int(duration * fps)
    return VideoInfo(duration, int(stream["width"]), int(stream["height"]), fps, frames)


def target_frames(duration: float, preset: dict) -> int:
    desired = int(round(duration * float(preset["frames_per_second_of_video"])))
    return max(int(preset["min_frames"]), min(int(preset["max_frames"]), desired))


def _sharpness(img: np.ndarray) -> float:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _exposure(img: np.ndarray) -> float:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mean = float(gray.mean())
    return max(0.0, 1.0 - abs(mean - 128.0) / 128.0)


def _hist(img: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0, 1], None, [24, 16], [0, 180, 0, 256])
    cv2.normalize(h, h)
    return h


def extract_candidates(video: Path, out_dir: Path, candidate_fps: float, max_width: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    vf = f"fps={candidate_fps},scale='min(iw,{max_width})':-2"
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
        "-i", str(video),
        "-an", "-vf", vf,
        "-q:v", "2",
        str(out_dir / "candidate_%06d.jpg"),
    ]
    subprocess.run(cmd, check=True)


def select_keyframes(candidates: Path, selected: Path, target: int) -> dict:
    images = sorted(candidates.glob("candidate_*.jpg"))
    if not images:
        raise RuntimeError("FFmpeg extracted no candidate frames.")
    target = min(target, len(images))
    selected.mkdir(parents=True, exist_ok=True)

    edges = np.linspace(0, len(images), target + 1, dtype=int)
    previous_hist = None
    chosen = []
    rejected_blurry = 0

    for i in range(target):
        lo, hi = int(edges[i]), int(edges[i + 1])
        if hi <= lo:
            continue
        best = None
        best_score = -1e30
        best_hist = None
        for idx in range(lo, hi):
            path = images[idx]
            img = cv2.imread(str(path))
            if img is None:
                continue
            small = cv2.resize(img, (max(320, img.shape[1] // 4), max(180, img.shape[0] // 4)))
            sharp = _sharpness(small)
            expo = _exposure(small)
            hist = _hist(small)
            novelty = 0.35 if previous_hist is None else float(
                cv2.compareHist(previous_hist, hist, cv2.HISTCMP_BHATTACHARYYA)
            )
            score = math.log1p(max(sharp, 0.0)) * 1.9 + novelty * 3.0 + expo * 0.8
            if sharp < 12:
                score -= 4.0
                rejected_blurry += 1
            if score > best_score:
                best = path
                best_score = score
                best_hist = hist

        if best is None:
            continue
        dst = selected / f"frame_{len(chosen):06d}.jpg"
        dst.write_bytes(best.read_bytes())
        chosen.append({"source": best.name, "output": dst.name, "score": round(best_score, 4)})
        previous_hist = best_hist

    manifest = {
        "candidate_count": len(images),
        "target_count": target,
        "selected_count": len(chosen),
        "low_sharpness_observations": rejected_blurry,
        "frames": chosen,
    }
    (selected.parent / "keyframes.json").write_text(json.dumps(manifest, indent=2))
    return manifest
