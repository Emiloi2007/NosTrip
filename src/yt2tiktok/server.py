"""Worker HTTP appelé par n8n : découpage des vidéos et publication TikTok.

Lancement : uvicorn yt2tiktok.server:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
import os
import secrets
import threading
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from .pipeline import Options, run
from .tiktok import TikTokClient, TikTokError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/data/output")).resolve()
TOKEN_FILE = Path(os.environ.get("TIKTOK_TOKEN_FILE", "/data/tiktok_token.json"))
WORKER_TOKEN = os.environ.get("WORKER_TOKEN", "")

app = FastAPI(title="yt2tiktok worker")
_split_lock = threading.Lock()  # un seul découpage à la fois (Whisper et ffmpeg sont gourmands)
_oauth_states: set[str] = set()


def check_token(x_worker_token: str = Header(default="")) -> None:
    if WORKER_TOKEN and not secrets.compare_digest(x_worker_token, WORKER_TOKEN):
        raise HTTPException(401, "X-Worker-Token invalide")


def tiktok() -> TikTokClient:
    try:
        return TikTokClient(
            os.environ["TIKTOK_CLIENT_KEY"],
            os.environ["TIKTOK_CLIENT_SECRET"],
            os.environ["TIKTOK_REDIRECT_URI"],
            TOKEN_FILE,
        )
    except KeyError as e:
        raise HTTPException(500, f"Variable d'environnement manquante : {e.args[0]}") from None


def safe_path(file: str) -> Path:
    path = Path(file).resolve()
    if not path.is_relative_to(OUTPUT_DIR) or not path.is_file():
        raise HTTPException(404, f"Fichier introuvable : {file}")
    return path


@app.get("/health")
def health() -> dict:
    return {"ok": True, "tiktok_connected": TOKEN_FILE.exists()}


class SplitRequest(BaseModel):
    url: str
    mode: Literal["equal", "highlights"] = "equal"
    part_seconds: float = Field(60, gt=5)
    part_label: bool = True
    max_clips: int = 5
    min_seconds: float = 20
    max_seconds: float = 60
    selector: Literal["llm", "heuristic"] = "heuristic"
    layout: Literal["blur", "crop"] = "blur"
    subtitles: bool = True
    whisper_model: str = "small"
    language: str | None = None


@app.post("/split", dependencies=[Depends(check_token)])
def split(req: SplitRequest) -> dict:
    if Path(req.url).exists():
        raise HTTPException(400, "Seules les URL sont acceptées.")
    opts = Options(**req.model_dump(exclude={"url"}))
    with _split_lock:
        try:
            parts = run(req.url, OUTPUT_DIR, opts)
        except Exception as e:  # noqa: BLE001 - renvoyé tel quel à n8n
            logging.exception("Échec du découpage")
            raise HTTPException(500, str(e)) from e
    video_id = parts[0].path.parent.name
    return {
        "video_id": video_id,
        "count": len(parts),
        "parts": [
            {"index": i, "total": len(parts), "download": f"/files/{video_id}/{p.path.name}", **p.to_dict()}
            for i, p in enumerate(parts, 1)
        ],
    }


@app.get("/files/{video_id}/{name}", dependencies=[Depends(check_token)])
def files(video_id: str, name: str) -> FileResponse:
    return FileResponse(safe_path(str(OUTPUT_DIR / video_id / name)))


# ---------- TikTok ----------
@app.get("/tiktok/login")
def tiktok_login() -> RedirectResponse:
    state = secrets.token_urlsafe(16)
    _oauth_states.add(state)
    return RedirectResponse(tiktok().authorize_url(state))


@app.get("/tiktok/callback", response_class=HTMLResponse)
def tiktok_callback(code: str = "", state: str = "", error: str = "", error_description: str = "") -> str:
    if error:
        raise HTTPException(400, f"TikTok a refusé l'autorisation : {error} {error_description}")
    if state not in _oauth_states:
        raise HTTPException(400, "state OAuth invalide ; relancez /tiktok/login")
    _oauth_states.discard(state)
    try:
        tiktok().exchange_code(code)
    except TikTokError as e:
        raise HTTPException(400, str(e)) from e
    return "<h1>Compte TikTok connecté ✅</h1><p>Vous pouvez fermer cette page et lancer le workflow n8n.</p>"


@app.get("/tiktok/status", dependencies=[Depends(check_token)])
def tiktok_status() -> dict:
    try:
        return {"connected": True, "creator": tiktok().creator_info()}
    except TikTokError as e:
        return {"connected": False, "error": str(e)}


class PublishRequest(BaseModel):
    file: str
    title: str = ""
    privacy_level: Literal["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY"] | None = None
    disable_comment: bool = False
    disable_duet: bool = False
    disable_stitch: bool = False


@app.post("/tiktok/publish", dependencies=[Depends(check_token)])
def tiktok_publish(req: PublishRequest) -> dict:
    path = safe_path(req.file)
    try:
        return tiktok().publish_video(
            path, req.title, req.privacy_level,
            req.disable_comment, req.disable_duet, req.disable_stitch,
        )
    except TikTokError as e:
        raise HTTPException(502, str(e)) from e
