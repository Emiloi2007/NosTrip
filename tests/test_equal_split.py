from yt2tiktok.highlights import equal_split


def test_equal_parts_cover_whole_video():
    parts = equal_split(250, 60)
    assert len(parts) == 5
    assert parts[0].start == 0 and parts[-1].end == 250
    assert all(abs(p.duration - 50) < 1e-6 for p in parts)
    assert [p.title for p in parts][:2] == ["Partie 1/5", "Partie 2/5"]
    for a, b in zip(parts, parts[1:]):
        assert a.end == b.start


def test_exact_multiple_does_not_add_empty_part():
    assert len(equal_split(120, 60)) == 2


def test_short_video_single_part():
    parts = equal_split(30, 60)
    assert len(parts) == 1 and parts[0].duration == 30


def test_cuts_snap_to_sentence_gaps(segments):
    duration = segments[-1].end
    parts = equal_split(duration, 20, segments)
    gaps = {round((a.end + b.start) / 2, 3) for a, b in zip(segments, segments[1:])}
    for p in parts[:-1]:
        assert p.end in gaps
    assert parts[-1].end == round(duration, 3)
