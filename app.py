from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import gradio as gr

ROOT = Path(__file__).resolve().parent
RUNNER = ROOT / "run.sh"


def newest_report() -> Path | None:
    reports = sorted((ROOT / "runs").glob("*/report.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return reports[0] if reports else None


def run_job(video_path: str, preset: str, job_name: str):
    if not video_path:
        yield "Choose a video first.", None, None
        return
    cmd = [str(RUNNER), video_path, preset]
    if job_name.strip():
        cmd += ["--name", job_name.strip()]

    yield "Starting…", None, None
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    lines = []
    assert p.stdout is not None
    for line in p.stdout:
        lines.append(line.rstrip())
        if len(lines) > 80:
            lines = lines[-80:]
        yield "\n".join(lines), None, None

    rc = p.wait()
    if rc:
        yield "\n".join(lines) + f"\n\nFAILED (exit {rc})", None, None
        return

    report_path = newest_report()
    if report_path is None:
        yield "\n".join(lines) + "\n\nFinished, but report.json was not found.", None, None
        return
    report = json.loads(report_path.read_text())
    ply = Path(report["splat"])
    yield "\n".join(lines), str(ply) if ply.exists() else None, str(report_path)


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="SPLAT — House Walkthrough → 3D") as demo:
        gr.Markdown(
            "# SPLAT\n"
            "**Drop in a long, continuous walkthrough. Get back a 3D Gaussian Splat.**\n\n"
            "Balanced is the default for a 45+ minute house walkthrough. "
            "The pipeline hard-caps useful frames so raw video length does not explode GPU time."
        )
        with gr.Row():
            video = gr.Video(label="House walkthrough", sources=["upload"])
            with gr.Column():
                preset = gr.Radio(
                    ["preview", "balanced", "quality"],
                    value="balanced",
                    label="Preset",
                    info="Preview = fastest. Balanced = recommended. Quality = more frames + splatfacto-big.",
                )
                name = gr.Textbox(label="Job name (optional)", placeholder="september-house")
                go = gr.Button("MAKE THE SPLAT", variant="primary")
        log = gr.Textbox(label="Live log", lines=24, max_lines=30)
        splat = gr.File(label="Download house.ply")
        report = gr.File(label="Run report")
        go.click(run_job, [video, preset, name], [log, splat, report])
    return demo


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=7860)
    args = p.parse_args()
    build_ui().queue(default_concurrency_limit=1).launch(
        server_name=args.host,
        server_port=args.port,
        allowed_paths=[str(ROOT / "runs")],
        show_error=True,
    )


if __name__ == "__main__":
    main()
