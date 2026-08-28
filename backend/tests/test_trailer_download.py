"""Why ffmpeg has to stay in the image.

ffmpeg is the single most expensive thing this image installs that only one
feature needs: yt-dlp gluing together the separate video and audio streams
YouTube serves, for the trailer download in the metadata editor. It arrives
with a dependency tail nothing else touches, and it is how two of the worst
advisories against this image reach us - the critical libtiff one through
gdk-pixbuf, and three in cjson through librist. Removing it therefore looks
like the best trade on the board, and it is the obvious thing for the next
person to try.

It does not work. Measured from inside the image against real videos on
2026-08-28, before deploying anything:

    aqz-KE-bpKQ | formats: 53 | already carrying video and audio: 0
    dQw4w9WgXcQ | formats: 48 | already carrying video and audio: 0

YouTube no longer publishes pre-merged streams, at 720p or at any other
height. A format string without a "+" does not fall back to something
smaller: it fails with "Requested format is not available", and every trailer
button in the product stops working.

Nothing else in the suite catches that. The whole run stayed green while the
feature was broken, because the failure only appears on a network call none
of these tests make - which is exactly why these assertions are here.

If the dependency tail is worth attacking again, the way through is a smaller
ffmpeg carrying only the mp4 muxer, pinned by checksum the way EmulatorJS
already is, rather than a download that avoids merging.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DOCKERFILE = ROOT / "Dockerfile"
HANDLER = (pathlib.Path(__file__).resolve().parent.parent
           / "handler" / "library" / "media_handler.py")


def test_the_image_carries_the_merger_the_download_depends_on():
    """The assertion that would have caught it."""
    if not DOCKERFILE.is_file():
        pytest.skip("Dockerfile nie jest obecny")
    installed = "\n".join(
        line for line in DOCKERFILE.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    assert "ffmpeg" in installed, (
        "bez ffmpeg zaden zwiastun sie nie pobierze - patrz docstring"
    )


@pytest.mark.parametrize("quality", ["best", "2160", "1440", "1080", "720", "480"])
def test_every_offered_quality_asks_for_the_streams_it_will_merge(quality):
    """Each entry the editor offers has to resolve to something YouTube will
    actually serve, and above the pre-merged tier that means two streams."""
    from handler.library.media_handler import _video_format
    picked = _video_format(quality)
    assert "+" in picked, f"{quality}: format nie prosi o scalanie strumieni"
    assert "bestvideo" in picked and "bestaudio" in picked


def test_the_lowest_rung_still_takes_whatever_exists():
    """A trailer published only at 360p has to arrive rather than fail, so the
    last resort carries no height filter at all."""
    from handler.library.media_handler import _video_format
    assert _video_format("1080").split("/")[-1] == "best"
    assert _video_format("360").split("/")[-1] == "best"


def test_the_merge_is_actually_requested():
    """merge_output_format tells yt-dlp which container to remux into. Without
    it the two streams can land beside each other as separate files."""
    assert "merge_output_format" in HANDLER.read_text(encoding="utf-8")
