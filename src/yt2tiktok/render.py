"""Rendu ffmpeg : découpe, recadrage vertical 9:16 et incrustation des sous-titres."""
from __future__ import annotations

import subprocess
from pathlib import Path

LAYOUTS = ("blur", "crop")


def video_filter(layout: str, width: int, height: int, subtitles: str | None) -> str:
    if layout == "blur":
        # Vidéo entière au centre, fond = même vidéo agrandie et floutée.
        vf = (
            f"split=2[bg][fg];"
            f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},boxblur=20:2[bg2];"
            f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[fg2];"
            f"[bg2][fg2]overlay=(W-w)/2:(H-h)/2"
        )
    elif layout == "crop":
        # Recadrage centré plein écran.
        vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
    else:
        raise ValueError(f"layout inconnu : {layout!r} (attendu : {', '.join(LAYOUTS)})")
    vf += ",setsar=1"
    if subtitles:
        vf += f",ass={subtitles}"
    return vf


def build_command(
    source: Path,
    output: Path,
    start: float,
    duration: float,
    layout: str = "blur",
    subtitles: str | None = None,
    width: int = 1080,
    height: int = 1920,
) -> list[str]:
    return [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-i", str(source), "-t", f"{duration:.3f}",
        "-filter_complex", f"[0:v]{video_filter(layout, width, height, subtitles)}[v]",
        "-map", "[v]", "-map", "0:a?",
        "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(output),
    ]


def render_clip(source: Path, output: Path, start: float, duration: float, layout: str = "blur",
                subtitles: Path | None = None) -> None:
    # ffmpeg est lancé depuis le dossier de sortie pour que le chemin du fichier
    # .ass reste un simple nom, sans échappement propre au filtre « ass ».
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_command(source.resolve(), output.resolve(), start, duration, layout,
                        subtitles.name if subtitles else None)
    subprocess.run(cmd, check=True, cwd=subtitles.parent if subtitles else output.parent)
