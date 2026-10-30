from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .highlights import heuristic_select, llm_select
from .models import Clip
from .render import render_clip
from .subtitles import build_ass
from .transcribe import transcribe

log = logging.getLogger("yt2tiktok")


@dataclass
class Options:
    max_clips: int = 5
    min_seconds: float = 20
    max_seconds: float = 60
    selector: str = "llm"  # "llm" ou "heuristic"
    layout: str = "blur"  # "blur" ou "crop"
    subtitles: bool = True
    whisper_model: str = "small"
    language: str | None = None


def caption(clip: Clip) -> str:
    tags = " ".join(t if t.startswith("#") else f"#{t}" for t in clip.hashtags)
    return "\n\n".join(p for p in (clip.title, clip.description, tags) if p)


def run(source: str, out_dir: Path, opts: Options) -> list[Path]:
    work = out_dir / "_work"
    if Path(source).exists():
        video = Path(source)
        meta = {"id": video.stem, "title": video.stem}
    else:
        from .download import download

        log.info("Téléchargement de %s", source)
        video, meta = download(source, work)

    dest = out_dir / meta["id"]
    dest.mkdir(parents=True, exist_ok=True)

    log.info("Transcription (whisper %s)", opts.whisper_model)
    segments = transcribe(video, work / f"{meta['id']}.transcript.json", opts.whisper_model, opts.language)
    if not segments:
        raise RuntimeError("Aucune parole détectée dans la vidéo.")

    log.info("Sélection des passages (%s)", opts.selector)
    if opts.selector == "llm":
        clips = llm_select(segments, opts.max_clips, opts.min_seconds, opts.max_seconds, meta.get("title", ""))
    else:
        clips = heuristic_select(segments, opts.max_clips, opts.min_seconds, opts.max_seconds)
    if not clips:
        raise RuntimeError("Aucun passage ne respecte les contraintes de durée.")

    outputs = []
    for i, clip in enumerate(clips, 1):
        name = f"clip_{i:02d}"
        ass = None
        if opts.subtitles:
            ass = dest / f"{name}.ass"
            ass.write_text(build_ass(segments, clip.start, clip.end), encoding="utf-8")
        mp4 = dest / f"{name}.mp4"
        log.info("Rendu %s [%.1fs → %.1fs] %s", name, clip.start, clip.end, clip.title)
        render_clip(video, mp4, clip.start, clip.duration, opts.layout, ass)
        (dest / f"{name}.txt").write_text(caption(clip), encoding="utf-8")
        outputs.append(mp4)

    manifest = {"source": meta, "clips": [{"file": p.name, **c.to_dict()} for p, c in zip(outputs, clips)]}
    (dest / "clips.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return outputs
