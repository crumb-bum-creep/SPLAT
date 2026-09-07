# SPLAT

**Long house walkthrough video → 3D Gaussian Splat, with one command.**

SPLAT is aimed at exactly one use case first: a long, continuous phone/camera walkthrough of a mostly static house or building. It turns that video into a manageable set of sharp, overlapping keyframes, solves camera poses with COLMAP's video-friendly sequential matcher, trains a Nerfstudio Gaussian Splat, and exports `house.ply`.

The project is designed around RunPod and the NVIDIA RTX PRO 6000 Blackwell (96 GB), but it should work on other modern NVIDIA GPUs too.

## What it does

```text
45+ minute MP4/MOV
      |
      v
FFmpeg candidate extraction
      |
      v
adaptive temporal + sharpness + novelty keyframe selection
      |
      v
COLMAP sequential SfM + loop closure
      |
      +-- poor registration? --> automatic vocabulary-tree retry
      |
      v
Nerfstudio Splatfacto / gsplat
      |
      v
runs/<job>/export/house.ply
```

The important bit is the **frame budget**. A 45 minute 30 fps video contains ~81,000 frames. SPLAT never tries to train on all of them.

| preset | selected frame cap | training | intended use |
|---|---:|---:|---|
| `preview` | 900 | 7k steps / Splatfacto | fastest sanity check |
| `balanced` | 1,500 | 12k steps / Splatfacto | **recommended** |
| `quality` | 2,200 | 20k steps / Splatfacto Big | final nicer pass |

For long videos the selected count reaches the cap; shorter videos scale down automatically.

## RunPod: install

On a fresh GPU pod:

```bash
cd /workspace && git clone https://github.com/crumb-bum-creep/SPLAT.git && cd SPLAT && bash install.sh
```

If the repo is already present:

```bash
cd /workspace/SPLAT && git pull && bash install.sh
```

The installer checks NVIDIA/CUDA availability, installs FFmpeg + COLMAP, creates `.venv`, installs Nerfstudio and verifies the full toolchain.

## Easiest use: phone/web UI

```bash
cd /workspace/SPLAT && bash serve.sh
```

Expose port **7860** in RunPod and open it. Upload the walkthrough, leave `balanced` selected, click **MAKE THE SPLAT**.

For very large source videos, putting the MP4 directly in `/workspace` first is faster than uploading through the browser; use the CLI below.

## CLI

```bash
cd /workspace/SPLAT && ./run.sh /workspace/house_walkthrough.mp4 balanced
```

Fast preview:

```bash
cd /workspace/SPLAT && ./run.sh /workspace/house_walkthrough.mp4 preview
```

Higher quality:

```bash
cd /workspace/SPLAT && ./run.sh /workspace/house_walkthrough.mp4 quality
```

Named job:

```bash
cd /workspace/SPLAT && ./run.sh /workspace/house_walkthrough.mp4 balanced --name september-house
```

## Output

Each job lands under:

```text
runs/<job>/
├── selected/
├── dataset/
├── training/
├── export/
│   ├── house.ply
│   └── splat/
├── logs/
├── keyframes.json
└── report.json
```

`house.ply` can be opened in Gaussian-splat viewers including PlayCanvas SuperSplat and other compatible viewers.

## Why this is 3D, not 4D

A walkthrough of a house under construction is mainly a **static-scene reconstruction** problem: the camera moves through one house. A true 4D Gaussian model is for geometry/appearance changing over time inside the same reconstruction. For construction progress, the cleaner future feature is one 3D splat per date plus a timeline/compare viewer.

## Capture advice

Best results come from continuous movement with lots of overlap, slow turns through doorways instead of whip-pans, avoiding long stretches pointed at the floor, keeping the same lens/zoom throughout the walkthrough, and enough light to avoid motion blur.

People walking through the shot are usually tolerable in moderation, but a mostly static scene is much easier to reconstruct cleanly.

## Diagnostics

```bash
cd /workspace/SPLAT && ./doctor.sh
```

If pose recovery is weak, inspect `runs/<job>/selected/`, `runs/<job>/logs/poses-sequential.log`, and `runs/<job>/report.json`.

SPLAT automatically retries COLMAP with vocabulary-tree matching when sequential registration falls below the preset threshold.

## Design priorities

1. **Turnkey**
2. **Do not scale compute with every raw video frame**
3. **Fail early if camera reconstruction is bad**
4. **Produce a standard `.ply` instead of trapping the result in a custom format**
5. **Keep the pipeline understandable enough to debug on a rented RunPod**

## Current status

v0.1 is the initial functional RunPod pipeline. Next likely additions: optional learned pose path (VGGT-Ω / newer scalable reconstructor), dynamic-person masking, generated camera-path preview MP4, built-in interactive web splat viewer, and multiple-date construction-progress comparison.
