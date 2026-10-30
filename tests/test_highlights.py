import json
from types import SimpleNamespace

from yt2tiktok.highlights import heuristic_select, llm_select, remove_overlaps, snap_to_segments
from yt2tiktok.models import Clip


def test_heuristic_respects_duration_and_overlap(segments):
    clips = heuristic_select(segments, max_clips=3, min_s=10, max_s=25)
    assert 1 <= len(clips) <= 3
    for c in clips:
        assert 10 <= c.duration <= 25
    for a, b in zip(clips, clips[1:]):
        assert a.end <= b.start


def test_snap_aligns_on_sentence_boundaries(segments):
    clip = snap_to_segments(Clip(1.0, 14.0), segments, 5, 30)
    starts = {s.start for s in segments}
    ends = {s.end for s in segments}
    assert clip.start in starts and clip.end in ends


def test_snap_extends_short_clips(segments):
    clip = snap_to_segments(Clip(0.5, 1.0), segments, 10, 30)
    assert clip.duration >= 10


def test_snap_drops_out_of_range():
    assert snap_to_segments(Clip(100, 120), [], 5, 30) is None


def test_remove_overlaps_keeps_best():
    kept = remove_overlaps([Clip(0, 10, score=1), Clip(5, 15, score=9), Clip(20, 30, score=2)])
    assert [(c.start, c.end) for c in kept] == [(5, 15), (20, 30)]


class FakeStream:
    def __init__(self, payload):
        self.msg = SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=json.dumps(payload))],
        )

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.msg


def test_llm_select_parses_and_snaps(segments):
    payload = {"clips": [
        {"start": 0.2, "end": 16, "title": "Pieuvres", "description": "d", "hashtags": ["#science"], "score": 8},
        {"start": 5, "end": 12, "title": "Chevauche", "description": "d", "hashtags": [], "score": 2},
    ]}
    calls = {}

    def stream(**kwargs):
        calls.update(kwargs)
        return FakeStream(payload)

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream)))
    clips = llm_select(segments, 3, 10, 30, "Les pieuvres", client=client)
    assert len(clips) == 1 and clips[0].title == "Pieuvres"
    assert clips[0].start == segments[0].start
    assert calls["output_config"]["format"]["type"] == "json_schema"
