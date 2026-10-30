"""Choix des passages à transformer en clips TikTok."""
from __future__ import annotations

import json
import re

from .models import Clip, Segment

LLM_MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """Tu es monteur vidéo spécialiste des formats courts (TikTok, Reels, Shorts).
On te donne la transcription horodatée d'une vidéo YouTube. Choisis les passages qui
feront les meilleurs clips autonomes : une accroche forte dès les premières secondes,
une idée complète compréhensible sans le reste de la vidéo, et une fin nette.
Les clips ne doivent pas se chevaucher. Utilise les horodatages de la transcription
pour start et end (en secondes). Rédige titre, description et hashtags dans la langue
de la vidéo."""

CLIPS_SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "score": {"type": "number", "description": "Potentiel viral de 0 à 10"},
                },
                "required": ["start", "end", "title", "description", "hashtags", "score"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clips"],
    "additionalProperties": False,
}


def format_transcript(segments: list[Segment]) -> str:
    return "\n".join(f"[{s.start:.1f}-{s.end:.1f}] {s.text}" for s in segments)


def snap_to_segments(clip: Clip, segments: list[Segment], min_s: float, max_s: float) -> Clip | None:
    """Aligne un clip sur des limites de phrases et force sa durée dans [min_s, max_s]."""
    inside = [s for s in segments if s.end > clip.start and s.start < clip.end]
    if not inside:
        return None
    start = inside[0].start
    end = inside[-1].end
    # Trop long : on retire des phrases à la fin.
    while end - start > max_s and len(inside) > 1:
        inside.pop()
        end = inside[-1].end
    if end - start > max_s:
        end = start + max_s
    # Trop court : on ajoute les phrases suivantes.
    idx = segments.index(inside[-1])
    while end - start < min_s and idx + 1 < len(segments) and segments[idx + 1].end - start <= max_s:
        idx += 1
        end = segments[idx].end
    if end - start < min_s:
        return None
    return Clip(start, end, clip.title, clip.description, clip.hashtags, clip.score)


def remove_overlaps(clips: list[Clip]) -> list[Clip]:
    kept: list[Clip] = []
    for c in sorted(clips, key=lambda c: -c.score):
        if all(c.end <= k.start or c.start >= k.end for k in kept):
            kept.append(c)
    return sorted(kept, key=lambda c: c.start)


def heuristic_select(
    segments: list[Segment], max_clips: int, min_s: float = 20, max_s: float = 60
) -> list[Clip]:
    """Sélection sans IA : fenêtres de phrases consécutives, notées sur le débit
    de parole et la présence de questions/exclamations."""
    candidates: list[Clip] = []
    target = (min_s + max_s) / 2
    for i, first in enumerate(segments):
        j = i
        while j + 1 < len(segments) and segments[j].end - first.start < target:
            j += 1
        window = segments[i : j + 1]
        dur = window[-1].end - first.start
        if not (min_s <= dur <= max_s):
            continue
        text = " ".join(s.text for s in window)
        words = len(text.split())
        punch = len(re.findall(r"[?!]", text))
        hook = 1.0 if re.search(r"[?!]", first.text) else 0.0
        score = words / dur + 0.5 * punch + hook
        title = first.text[:80]
        candidates.append(Clip(first.start, window[-1].end, title, text[:150], [], round(score, 3)))
    return remove_overlaps(candidates)[:max_clips] if candidates else []


def llm_select(
    segments: list[Segment],
    max_clips: int,
    min_s: float = 20,
    max_s: float = 60,
    video_title: str = "",
    client=None,
) -> list[Clip]:
    """Sélection par Claude : renvoie des clips avec titre, description et hashtags."""
    import anthropic

    client = client or anthropic.Anthropic()
    prompt = (
        f"Titre de la vidéo : {video_title or 'inconnu'}\n"
        f"Propose au maximum {max_clips} clips, chacun entre {min_s:.0f} et {max_s:.0f} secondes.\n\n"
        f"<transcription>\n{format_transcript(segments)}\n</transcription>"
    )
    with client.beta.messages.stream(
        model=LLM_MODEL,
        max_tokens=64000,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": CLIPS_SCHEMA}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "refusal":
        raise RuntimeError("Claude a refusé la requête ; relancez avec --selector heuristic.")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Réponse tronquée (max_tokens atteint).")
    text = "".join(b.text for b in response.content if b.type == "text")
    data = json.loads(text)

    clips = []
    for c in data["clips"]:
        snapped = snap_to_segments(
            Clip(c["start"], c["end"], c["title"], c["description"], c["hashtags"], c["score"]),
            segments,
            min_s,
            max_s,
        )
        if snapped:
            clips.append(snapped)
    return remove_overlaps(clips)[:max_clips]
