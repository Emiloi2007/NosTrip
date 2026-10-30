import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("TIKTOK_TOKEN_FILE", str(tmp_path / "token.json"))
    monkeypatch.setenv("WORKER_TOKEN", "secret")
    import yt2tiktok.server as s
    return importlib.reload(s)


def test_token_required(server):
    c = TestClient(server.app)
    assert c.get("/health").status_code == 200
    assert c.post("/tiktok/publish", json={"file": "x"}).status_code == 401


def test_publish_rejects_paths_outside_output(server, tmp_path):
    c = TestClient(server.app)
    (tmp_path / "secret.txt").write_text("x")
    r = c.post("/tiktok/publish", json={"file": str(tmp_path / "secret.txt")}, headers={"X-Worker-Token": "secret"})
    assert r.status_code == 404


def test_split_returns_parts(server, monkeypatch, tmp_path):
    from yt2tiktok.models import Clip
    from yt2tiktok.pipeline import Part

    out = tmp_path / "out" / "vid123"
    out.mkdir(parents=True)

    def fake_run(url, out_dir, opts):
        assert opts.part_seconds == 45 and opts.mode == "equal"
        return [Part(out / f"clip_0{i}.mp4", Clip(i * 45, (i + 1) * 45, f"Partie {i + 1}/2"), "cap") for i in range(2)]

    monkeypatch.setattr(server, "run", fake_run)
    r = TestClient(server.app).post("/split", json={"url": "https://youtu.be/abc", "part_seconds": 45},
                                    headers={"X-Worker-Token": "secret"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2 and body["parts"][1]["index"] == 2 and body["parts"][1]["total"] == 2
    assert body["parts"][0]["download"] == "/files/vid123/clip_00.mp4"
