from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import Segment, Word


def transcribe(
    media: Path,
    cache: Path | None = None,
    model_size: str = "small",
    language: str | None = None,
    device: str = "auto",
) -> list[Segment]:
    """Transcrit l'audio avec horodatage mot à mot (faster-whisper).

    Le résultat est mis en cache en JSON pour éviter de retranscrire.
    """
    if cache and cache.exists():
        return [Segment.from_dict(d) for d in json.loads(cache.read_text())]

    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device=device, compute_type="auto")
    raw, _info = model.transcribe(
        str(media), language=language, word_timestamps=True, vad_filter=True
    )
    segments = [
        Segment(
            start=s.start,
            end=s.end,
            text=s.text.strip(),
            words=[Word(w.start, w.end, w.word.strip()) for w in (s.words or [])],
        )
        for s in raw
    ]
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps([asdict(s) for s in segments], ensure_ascii=False))
    return segments
