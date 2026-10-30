import json

import httpx

from yt2tiktok.tiktok import MB, TikTokClient, chunk_plan, chunk_ranges


def test_chunk_plan_small_and_large():
    assert chunk_plan(3 * MB) == (3 * MB, 1)
    assert chunk_plan(64 * MB) == (64 * MB, 1)
    size = 105 * MB + 123
    chunk, count = chunk_plan(size)
    assert chunk == 10 * MB and count == 10
    ranges = chunk_ranges(size)
    assert len(ranges) == 10 and ranges[-1] == (90 * MB, size - 1)
    assert ranges[-1][1] - ranges[-1][0] + 1 <= 128 * MB


def make_client(tmp_path, handler):
    token = tmp_path / "token.json"
    token.write_text(json.dumps({"access_token": "AT", "refresh_token": "RT", "expires_at": 9e12}))
    return TikTokClient("ck", "cs", "https://x/cb", token, httpx.Client(transport=httpx.MockTransport(handler)))


def test_publish_flow(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x" * 1000)
    calls = []

    def handler(req: httpx.Request):
        calls.append(req)
        path = req.url.path
        if path.endswith("creator_info/query/"):
            return httpx.Response(200, json={"data": {"privacy_level_options": ["SELF_ONLY"]}, "error": {"code": "ok"}})
        if path.endswith("video/init/"):
            body = json.loads(req.content)
            assert body["source_info"] == {"source": "FILE_UPLOAD", "video_size": 1000, "chunk_size": 1000, "total_chunk_count": 1}
            assert body["post_info"]["privacy_level"] == "SELF_ONLY"
            return httpx.Response(200, json={"data": {"publish_id": "p1", "upload_url": "https://upload.test/u?x=1"}, "error": {"code": "ok"}})
        if req.url.host == "upload.test":
            assert req.headers["Content-Range"] == "bytes 0-999/1000"
            return httpx.Response(201)
        if path.endswith("status/fetch/"):
            return httpx.Response(200, json={"data": {"status": "PUBLISH_COMPLETE"}, "error": {"code": "ok"}})
        raise AssertionError(path)

    result = make_client(tmp_path, handler).publish_video(video, "Partie 1/3")
    assert result["status"] == "PUBLISH_COMPLETE" and result["publish_id"] == "p1"
    assert all(c.headers.get("Authorization") == "Bearer AT" for c in calls if c.url.host != "upload.test")


def test_refresh_when_expired(tmp_path):
    token = tmp_path / "token.json"
    token.write_text(json.dumps({"access_token": "old", "refresh_token": "RT", "expires_at": 0}))

    def handler(req):
        assert b"grant_type=refresh_token" in req.content
        return httpx.Response(200, json={"access_token": "new", "refresh_token": "RT2", "expires_in": 86400})

    c = TikTokClient("ck", "cs", "https://x/cb", token, httpx.Client(transport=httpx.MockTransport(handler)))
    assert c.access_token() == "new"
    assert json.loads(token.read_text())["refresh_token"] == "RT2"
