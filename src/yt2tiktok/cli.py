from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .pipeline import Options, run
from .render import LAYOUTS


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="yt2tiktok",
        description="Transforme une vidéo YouTube (ou un fichier local) en plusieurs clips TikTok.",
    )
    p.add_argument("source", help="URL YouTube ou chemin d'un fichier vidéo")
    p.add_argument("-o", "--output", type=Path, default=Path("output"), help="dossier de sortie")
    p.add_argument("-n", "--max-clips", type=int, default=5)
    p.add_argument("--min", dest="min_seconds", type=float, default=20, help="durée min. d'un clip (s)")
    p.add_argument("--max", dest="max_seconds", type=float, default=60, help="durée max. d'un clip (s)")
    p.add_argument("--selector", choices=("llm", "heuristic"), default="llm",
                   help="llm = Claude choisit les moments forts (ANTHROPIC_API_KEY requis)")
    p.add_argument("--layout", choices=LAYOUTS, default="blur",
                   help="blur = vidéo entière sur fond flouté, crop = recadrage plein écran")
    p.add_argument("--no-subtitles", action="store_true")
    p.add_argument("--whisper-model", default="small", help="tiny, base, small, medium, large-v3…")
    p.add_argument("--language", default=None, help="code langue (fr, en…) ; auto si omis")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(message)s")
    if a.min_seconds > a.max_seconds:
        p.error("--min doit être inférieur ou égal à --max")

    opts = Options(
        max_clips=a.max_clips,
        min_seconds=a.min_seconds,
        max_seconds=a.max_seconds,
        selector=a.selector,
        layout=a.layout,
        subtitles=not a.no_subtitles,
        whisper_model=a.whisper_model,
        language=a.language,
    )
    try:
        outputs = run(a.source, a.output, opts)
    except Exception as e:  # noqa: BLE001 - message lisible en CLI
        logging.error("Erreur : %s", e)
        return 1
    print(f"{len(outputs)} clip(s) générés dans {outputs[0].parent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
