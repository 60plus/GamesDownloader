"""What the public resources mount is willing to render in place.

The artwork upload route refuses an SVG, and that shuts one door. It is not the
only one. A metadata backup is an archive supplied by whoever restores it, and
its members are checked for where they land - inside the resources tree - and
never for what they are. So a hand-built backup can put a .svg or an .html
under this mount, where it is served from our own origin as image/svg+xml or
text/html, and either one is a script running as us.

Refusing at the way out covers every way in at once, which is the point.

The comparable rule in RomM is at backend/handler/filesystem/assets_handler.py,
where anything outside a trusted image map is served as octet-stream with
Content-Disposition attachment.
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

import main
from config import RESOURCES_PATH


@pytest.fixture
def served(tmp_path, monkeypatch):
    """The real mount, over a directory this test owns."""
    from starlette.applications import Starlette

    app = Starlette()
    app.mount("/resources", main._ResourcesStatic(directory=str(tmp_path)), name="resources")
    return TestClient(app), tmp_path


def test_a_cover_is_still_served_as_a_picture(served):
    client, root = served
    (root / "cover.jpg").write_bytes(b"\xff\xd8\xff\xe0 not really a jpeg")

    r = client.get("/resources/cover.jpg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert "content-disposition" not in r.headers


@pytest.mark.parametrize("name", ["logo.png", "art.webp", "shot.gif", "trailer.mp4", "favicon.ico"])
def test_the_formats_this_library_actually_stores_still_render(served, name):
    client, root = served
    (root / name).write_bytes(b"data")
    r = client.get(f"/resources/{name}")
    assert r.status_code == 200
    assert r.headers["content-type"] != "application/octet-stream"
    assert "content-disposition" not in r.headers


@pytest.mark.parametrize("name", ["cover.svg", "page.html", "note.xhtml", "run.js", "doc.pdf"])
def test_anything_else_comes_back_as_a_download_of_unknown_type(served, name):
    """An SVG is the one that matters - it is a script container that a browser
    executes when it is opened directly, and no Content-Security-Policy on some
    other response protects a top-level navigation to this one."""
    client, root = served
    (root / name).write_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>")

    r = client.get(f"/resources/{name}")
    assert r.status_code == 200, "it is still served - this is about how, not whether"
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["content-disposition"] == "attachment"


def test_the_type_is_taken_from_the_extension_not_from_the_bytes(served):
    """A file whose contents are an SVG but whose name says .png is served as a
    png, which is exactly what we want: the browser is told a raster type and
    told not to sniff, so the markup inside it never gets a chance to run."""
    client, root = served
    (root / "cover.png").write_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>")

    r = client.get("/resources/cover.png")
    assert r.headers["content-type"] == "image/png"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_nothing_here_is_ever_sniffed(served):
    client, root = served
    (root / "cover.jpg").write_bytes(b"data")
    (root / "odd.svg").write_bytes(b"data")
    for name in ("cover.jpg", "odd.svg"):
        assert client.get(f"/resources/{name}").headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("rel", [
    "roms/psx/9/saves/1/Medievil.srm",      # a live memory card
    "roms/psx/9/states/1/slot1.state",
    "roms/_superseded/Medievil.srm",        # one the dedupe parked
])
def test_saves_are_still_out_of_reach(served, rel):
    """The rule that was already here, asserted because this function grew and
    the refusal now sits above a good deal more code than it used to."""
    client, root = served
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"somebody's saved game")

    assert client.get(f"/resources/{rel}").status_code == 404


def test_the_allow_list_covers_what_the_upload_route_accepts():
    """The two lists are separate and would drift apart silently: a format the
    upload route starts accepting but this mount will not render comes back as
    a download, which looks like the artwork simply failing to appear."""
    from endpoints.roms.roms_router import _UPLOAD_EXTS

    inline = {ext.lstrip(".") for ext in main._INLINE_RESOURCE_TYPES}
    missing = _UPLOAD_EXTS - inline
    assert not missing, f"upload accepts {missing}, which this mount would not render"
    assert str(RESOURCES_PATH)
