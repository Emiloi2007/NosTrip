"""Sous-titres « style TikTok » : gros texte centré, mot courant surligné."""
from __future__ import annotations

from .models import Segment, Word

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

HIGHLIGHT = r"{\c&H00FFFF&}"  # jaune (ASS = BGR)
RESET = r"{\c&HFFFFFF&}"


def ass_time(t: float) -> str:
    t = max(t, 0.0)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def escape(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").upper()


def words_in_range(segments: list[Segment], start: float, end: float) -> list[Word]:
    return [w for s in segments for w in s.words if w.end > start and w.start < end and w.text]


def chunk_words(words: list[Word], max_words: int = 3, max_gap: float = 0.6) -> list[list[Word]]:
    chunks: list[list[Word]] = []
    for w in words:
        if chunks and len(chunks[-1]) < max_words and w.start - chunks[-1][-1].end < max_gap:
            chunks[-1].append(w)
        else:
            chunks.append([w])
    return chunks


def build_ass(
    segments: list[Segment],
    start: float,
    end: float,
    width: int = 1080,
    height: int = 1920,
    font: str = "Arial",
    max_words: int = 3,
) -> str:
    """Génère un fichier ASS dont les temps sont relatifs au début du clip."""
    out = [ASS_HEADER.format(w=width, h=height, font=font, size=int(height * 0.045), margin_v=int(height * 0.28))]
    chunks = chunk_words(words_in_range(segments, start, end), max_words)
    for k, chunk in enumerate(chunks):
        next_start = chunks[k + 1][0].start if k + 1 < len(chunks) else None
        for i, w in enumerate(chunk):
            w_start = max(w.start, start) - start
            # Le mot reste surligné jusqu'au début du suivant (pas de clignotement),
            # y compris entre deux groupes si la pause est courte.
            if i + 1 < len(chunk):
                w_end = chunk[i + 1].start
            elif next_start is not None and next_start - w.end < 0.6:
                w_end = next_start
            else:
                w_end = w.end
            w_end = min(w_end, end) - start
            if w_end <= w_start:
                continue
            text = " ".join(
                f"{HIGHLIGHT}{escape(x.text)}{RESET}" if j == i else escape(x.text)
                for j, x in enumerate(chunk)
            )
            out.append(f"Dialogue: 0,{ass_time(w_start)},{ass_time(w_end)},Default,,0,0,0,,{text}")
    return "\n".join(out) + "\n"
