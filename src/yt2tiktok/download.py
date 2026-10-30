from __future__ import annotations

from pathlib import Path


def download(url: str, workdir: Path) -> tuple[Path, dict]:
    """Télécharge la vidéo en MP4 (<=1080p) et renvoie (chemin, métadonnées)."""
    import yt_dlp

    workdir.mkdir(parents=True, exist_ok=True)
    opts = {
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(workdir / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    path = workdir / f"{info['id']}.mp4"
    if not path.exists():
        path = Path(ydl.prepare_filename(info))
    meta = {k: info.get(k) for k in ("id", "title", "uploader", "duration", "webpage_url")}
    return path, meta
