from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .highlights import equal_split, heuristic_select, llm_select
from .models import Clip, Segment
from .render import probe_duration, render_clip
from .subtitles import build_ass
from .transcribe import transcribe

log = logging.getLogger("yt2tiktok")


@dataclass
class Options:
    mode: str = "equal"  # "equal" (parties de même durée) ou "highlights" (moments forts)
    part_seconds: float = 60  # mode equal : durée visée de chaque partie
    part_label: bool = True  # mode equal : bandeau « PARTIE x/N »
    max_clips: int = 5  # mode highlights
    min_seconds: float = 20  # mode highlights
    max_seconds: float = 60  # mode highlights
    selector: str = "llm"  # mode highlights : "llm" ou "heuristic"
    layout: str = "blur"  # "blur" ou "crop"
    subtitles: bool = True
    whisper_model: str = "small"
    language: str | None = None


@dataclass
class Part:
    path: Path
    clip: Clip
    caption: str

    def to_dict(self) -> dict:
        return {"file": str(self.path), "caption": self.caption, **self.clip.to_dict()}


def caption(clip: Clip, video_title: str = "") -> str:
    tags = " ".join(t if t.startswith("#") else f"#{t}" for t in clip.hashtags)
    title = f"{video_title} – {clip.title}" if video_title and clip.title.startswith("Partie") else clip.title
    return "\n\n".join(p for p in (title, clip.description, tags) if p)


def fetch(source: str, work: Path) -> tuple[Path, dict]:
    if Path(source).exists():
        video = Path(source)
        return video, {"id": video.stem, "title": video.stem}
    from .download import download

    log.info("Téléchargement de %s", source)
    return download(source, work)


def choose_clips(video: Path, meta: dict, segments: list[Segment], opts: Options) -> list[Clip]:
    if opts.mode == "equal":
        return equal_split(probe_duration(video), opts.part_seconds, segments)
    if opts.selector == "llm":
        return llm_select(segments, opts.max_clips, opts.min_seconds, opts.max_seconds, meta.get("title", ""))
    return heuristic_select(segments, opts.max_clips, opts.min_seconds, opts.max_seconds)


def run(source: str, out_dir: Path, opts: Options) -> list[Part]:
    work = out_dir / "_work"
    video, meta = fetch(source, work)
    dest = out_dir / meta["id"]
    dest.mkdir(parents=True, exist_ok=True)

    # La transcription sert aux sous-titres, à la sélection des moments forts
    # et à placer les coupures entre deux phrases ; inutile sinon.
    segments: list[Segment] = []
    if opts.subtitles or opts.mode == "highlights":
        log.info("Transcription (whisper %s)", opts.whisper_model)
        segments = transcribe(video, work / f"{meta['id']}.transcript.json", opts.whisper_model, opts.language)
        if not segments and opts.mode == "highlights":
            raise RuntimeError("Aucune parole détectée dans la vidéo.")

    log.info("Découpage (%s)", opts.mode)
    clips = choose_clips(video, meta, segments, opts)
    if not clips:
        raise RuntimeError("Aucun passage ne respecte les contraintes de durée.")

    parts = []
    for i, clip in enumerate(clips, 1):
        name = f"clip_{i:02d}"
        label = clip.title if opts.mode == "equal" and opts.part_label and len(clips) > 1 else None
        ass = None
        if opts.subtitles or label:
            ass = dest / f"{name}.ass"
            ass.write_text(build_ass(segments, clip.start, clip.end, label=label, words=opts.subtitles),
                           encoding="utf-8")
        mp4 = dest / f"{name}.mp4"
        log.info("Rendu %s [%.1fs → %.1fs] %s", name, clip.start, clip.end, clip.title)
        render_clip(video, mp4, clip.start, clip.duration, opts.layout, ass)
        text = caption(clip, meta.get("title", "") if opts.mode == "equal" else "")
        (dest / f"{name}.txt").write_text(text, encoding="utf-8")
        parts.append(Part(mp4, clip, text))

    manifest = {"source": meta, "parts": [p.to_dict() for p in parts]}
    (dest / "clips.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return parts
