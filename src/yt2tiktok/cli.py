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
    p.add_argument("--mode", choices=("equal", "highlights"), default="equal",
                   help="equal = toute la vidéo en parties de même durée ; highlights = moments forts")
    p.add_argument("--part-seconds", type=float, default=60, help="mode equal : durée de chaque partie (s)")
    p.add_argument("--no-part-label", action="store_true", help="mode equal : pas de bandeau « PARTIE x/N »")
    p.add_argument("-n", "--max-clips", type=int, default=5)
    p.add_argument("--min", dest="min_seconds", type=float, default=20, help="mode highlights : durée min. (s)")
    p.add_argument("--max", dest="max_seconds", type=float, default=60, help="mode highlights : durée max. (s)")
    p.add_argument("--selector", choices=("llm", "heuristic"), default="llm",
                   help="mode highlights : llm = Claude choisit (ANTHROPIC_API_KEY requis)")
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
        mode=a.mode,
        part_seconds=a.part_seconds,
        part_label=not a.no_part_label,
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
        parts = run(a.source, a.output, opts)
    except Exception as e:  # noqa: BLE001 - message lisible en CLI
        logging.error("Erreur : %s", e)
        return 1
    print(f"{len(parts)} clip(s) générés dans {parts[0].path.parent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
