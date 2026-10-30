import shutil
import subprocess

import pytest

from yt2tiktok.render import build_command, render_clip
from yt2tiktok.subtitles import build_ass


def test_command_contains_filters(tmp_path):
    cmd = build_command(tmp_path / "in.mp4", tmp_path / "out.mp4", 12.5, 30, "crop", "s.ass")
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "crop=1080:1920" in fc and fc.endswith("ass=s.ass[v]")
    assert cmd[cmd.index("-ss") + 1] == "12.500"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg absent")
@pytest.mark.parametrize("layout", ["blur", "crop"])
def test_render_produces_vertical_video(tmp_path, segments, layout):
    src = tmp_path / "src.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=8",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=8", "-shortest", str(src)],
        check=True,
    )
    ass = tmp_path / "clip.ass"
    ass.write_text(build_ass(segments, 1, 5), encoding="utf-8")
    out = tmp_path / "clip.mp4"
    render_clip(src, out, 1, 4, layout, ass)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    )
    assert probe.stdout.strip() == "1080,1920"
