from yt2tiktok.subtitles import ass_time, build_ass, chunk_words


def test_ass_time():
    assert ass_time(0) == "0:00:00.00"
    assert ass_time(3725.456) == "1:02:05.46"


def test_chunks_limit_words(segments):
    words = [w for s in segments[:2] for w in s.words]
    assert all(len(c) <= 3 for c in chunk_words(words, 3))


def test_build_ass_relative_times(segments):
    start = segments[1].start
    ass = build_ass(segments, start, segments[2].end)
    lines = [l for l in ass.splitlines() if l.startswith("Dialogue")]
    assert lines
    assert lines[0].split(",")[1] == "0:00:00.00"
    assert "{\\c&H00FFFF&}" in lines[0]


def test_no_flicker_between_chunks(segments):
    ass = build_ass(segments, segments[0].start, segments[0].end)
    times = [l.split(",")[1:3] for l in ass.splitlines() if l.startswith("Dialogue")]
    for (_, end), (start, _) in zip(times, times[1:]):
        assert end == start
