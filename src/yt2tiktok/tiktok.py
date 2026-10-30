"""Publication sur TikTok via la Content Posting API (Direct Post).

Doc : https://developers.tiktok.com/doc/content-posting-api-reference-direct-post
Les jetons OAuth sont stockés dans un fichier JSON et rafraîchis automatiquement
(jeton d'accès valable 24 h, jeton de rafraîchissement 365 jours).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
API = "https://open.tiktokapis.com/v2"
SCOPES = "user.info.basic,video.publish"

MB = 1024 * 1024
MAX_SINGLE_CHUNK = 64 * MB
CHUNK_SIZE = 10 * MB


class TikTokError(RuntimeError):
    pass


def chunk_plan(size: int) -> tuple[int, int]:
    """(chunk_size, total_chunk_count) selon les règles TikTok : un seul morceau
    jusqu'à 64 Mo, sinon des morceaux de 10 Mo, le reste étant ajouté au dernier."""
    if size <= MAX_SINGLE_CHUNK:
        return size, 1
    return CHUNK_SIZE, size // CHUNK_SIZE


def chunk_ranges(size: int) -> list[tuple[int, int]]:
    """Plages d'octets [début, fin] inclusives de chaque morceau."""
    chunk, count = chunk_plan(size)
    ranges = [(i * chunk, (i + 1) * chunk - 1) for i in range(count)]
    ranges[-1] = (ranges[-1][0], size - 1)
    return ranges


class TikTokClient:
    def __init__(self, client_key: str, client_secret: str, redirect_uri: str, token_file: Path,
                 http: httpx.Client | None = None):
        self.client_key = client_key
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.token_file = token_file
        self.http = http or httpx.Client(timeout=120)

    # ---------- OAuth ----------
    def authorize_url(self, state: str) -> str:
        return AUTH_URL + "?" + urlencode({
            "client_key": self.client_key,
            "response_type": "code",
            "scope": SCOPES,
            "redirect_uri": self.redirect_uri,
            "state": state,
        })

    def _token_request(self, **params) -> dict:
        r = self.http.post(
            f"{API}/oauth/token/",
            data={"client_key": self.client_key, "client_secret": self.client_secret, **params},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        data = r.json()
        if "access_token" not in data:
            raise TikTokError(f"Échec OAuth TikTok : {data}")
        data["expires_at"] = time.time() + data.get("expires_in", 0) - 300
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(json.dumps(data))
        return data

    def exchange_code(self, code: str) -> dict:
        return self._token_request(code=code, grant_type="authorization_code", redirect_uri=self.redirect_uri)

    def access_token(self) -> str:
        if not self.token_file.exists():
            raise TikTokError("Compte TikTok non connecté : ouvrez /tiktok/login sur le worker.")
        tok = json.loads(self.token_file.read_text())
        if time.time() >= tok.get("expires_at", 0):
            tok = self._token_request(grant_type="refresh_token", refresh_token=tok["refresh_token"])
        return tok["access_token"]

    def connected(self) -> bool:
        return self.token_file.exists()

    # ---------- API ----------
    def _post(self, path: str, body: dict) -> dict:
        r = self.http.post(
            f"{API}{path}",
            json=body,
            headers={"Authorization": f"Bearer {self.access_token()}",
                     "Content-Type": "application/json; charset=UTF-8"},
        )
        data = r.json()
        err = data.get("error", {})
        if err.get("code") not in (None, "ok"):
            raise TikTokError(f"{path} : {err.get('code')} – {err.get('message')} (log_id {err.get('log_id')})")
        return data.get("data", {})

    def creator_info(self) -> dict:
        return self._post("/post/publish/creator_info/query/", {})

    def publish_video(self, path: Path, title: str, privacy_level: str | None = None,
                      disable_comment: bool = False, disable_duet: bool = False,
                      disable_stitch: bool = False, wait: bool = True, timeout: float = 600) -> dict:
        """Publie une vidéo locale. privacy_level par défaut : le plus public autorisé
        pour ce compte (une app non auditée ne peut publier qu'en SELF_ONLY)."""
        info = self.creator_info()
        options = info.get("privacy_level_options", [])
        if privacy_level is None:
            order = ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY"]
            privacy_level = next((p for p in order if p in options), "SELF_ONLY")
        elif options and privacy_level not in options:
            raise TikTokError(f"privacy_level {privacy_level} non autorisé ; choix possibles : {options}")

        size = path.stat().st_size
        chunk, count = chunk_plan(size)
        init = self._post("/post/publish/video/init/", {
            "post_info": {
                "title": title[:2200],
                "privacy_level": privacy_level,
                "disable_comment": disable_comment or info.get("comment_disabled", False),
                "disable_duet": disable_duet or info.get("duet_disabled", False),
                "disable_stitch": disable_stitch or info.get("stitch_disabled", False),
            },
            "source_info": {"source": "FILE_UPLOAD", "video_size": size,
                            "chunk_size": chunk, "total_chunk_count": count},
        })
        publish_id, upload_url = init["publish_id"], init["upload_url"]

        with path.open("rb") as f:
            for first, last in chunk_ranges(size):
                f.seek(first)
                body = f.read(last - first + 1)
                r = self.http.put(upload_url, content=body, headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(body)),
                    "Content-Range": f"bytes {first}-{last}/{size}",
                })
                if r.status_code not in (200, 201, 206):
                    raise TikTokError(f"Envoi du morceau {first}-{last} refusé : HTTP {r.status_code} {r.text}")

        result = {"publish_id": publish_id, "privacy_level": privacy_level, "status": "PROCESSING_UPLOAD"}
        deadline = time.time() + timeout
        while wait and time.time() < deadline:
            status = self._post("/post/publish/status/fetch/", {"publish_id": publish_id})
            result.update(status)
            if status.get("status") in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
                break
            if status.get("status") == "FAILED":
                raise TikTokError(f"Publication échouée : {status.get('fail_reason')}")
            time.sleep(10)  # limite : 30 req/min sur ce endpoint
        return result
