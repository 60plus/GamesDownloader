"""Converting one disc on disk: what is read, what is written, what it replaces.

The filesystem half of the conversion, kept apart from the database half so
each can be asked its own question. This one runs chdman for real against
discs it builds, because the interesting failures are all about which files
were touched and no mock has an opinion about that.

The list of replaced files is the part to be careful with. It decides what
gets deleted or moved aside afterwards, and this project has removed a user's
data three times by being one item too generous.
"""
from __future__ import annotations

import shutil
import zipfile

import pytest


def _disc(directory, stem="Game (Disc 1)", sectors=512):
    """A real Mode1/2048 disc: a sheet and the track it names."""
    (directory / f"{stem}.bin").write_bytes(bytes(range(256)) * 8 * sectors)
    (directory / f"{stem}.cue").write_text(
        f'FILE "{stem}.bin" BINARY\n  TRACK 01 MODE1/2048\n    INDEX 01 00:00:00\n',
        encoding="utf-8",
    )
    return directory / f"{stem}.cue"


def _zipped_disc(directory, stem="Game (Disc 1)"):
    """The shape a disc arrives in from an archive site: sheet and track,
    deflated, in one file that is the library row."""
    staging = directory / "_staging"
    staging.mkdir()
    _disc(staging, stem)
    archive = directory / f"{stem}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for name in (f"{stem}.cue", f"{stem}.bin"):
            z.write(staging / name, arcname=name)
    shutil.rmtree(staging)
    return archive


needs_chdman = pytest.mark.skipif(
    not shutil.which("chdman"), reason="chdman nie jest w tym obrazie")


@needs_chdman
@pytest.mark.asyncio
async def test_a_sheet_and_its_track_become_one_file(tmp_path):
    from handler.roms.chd_convert import convert_disc_files

    psx = tmp_path / "psx"
    psx.mkdir()
    cue = _disc(psx)
    (psx / "Game (Disc 1).sbi").write_bytes(b"\0" * 452)

    done = await convert_disc_files(cue, psx)

    assert done.path == psx / "Game (Disc 1).chd"
    assert done.path.is_file()
    assert done.path.open("rb").read(8) == b"MComprHD"
    assert len(done.sha1) == 40, "brak hasza z naglowka"

    replaced = {p.name for p in done.replaced}
    assert replaced == {"Game (Disc 1).cue", "Game (Disc 1).bin"}, (
        "arkusz i jego sciezka sa zastapione, i nic wiecej"
    )


@needs_chdman
@pytest.mark.asyncio
async def test_the_subchannel_file_is_never_replaced(tmp_path):
    """It is not part of the disc image and the converted disc still needs it:
    converting a bare .bin produces a CHD with no subchannel, so a LibCrypt
    protected PAL disc goes straight back to hanging on a black screen."""
    from handler.roms.chd_convert import convert_disc_files

    psx = tmp_path / "psx"
    psx.mkdir()
    cue = _disc(psx)
    sbi = psx / "Game (Disc 1).sbi"
    sbi.write_bytes(b"\0" * 452)

    done = await convert_disc_files(cue, psx)

    assert sbi not in done.replaced
    assert sbi.is_file(), "plik podkanalu ma zostac przy plycie"


@needs_chdman
@pytest.mark.asyncio
async def test_an_archived_disc_is_unpacked_and_only_the_archive_is_replaced(tmp_path):
    """The library row is the .zip, and what came out of it never existed on
    the shelf, so the archive is the only thing that stops being current."""
    from handler.roms.chd_convert import convert_disc_files

    psx = tmp_path / "psx"
    psx.mkdir()
    archive = _zipped_disc(psx)

    done = await convert_disc_files(archive, psx)

    assert done.path == psx / "Game (Disc 1).chd"
    assert done.path.is_file()
    assert [p.name for p in done.replaced] == ["Game (Disc 1).zip"]
    assert not (psx / "Game (Disc 1).cue").exists(), \
        "rozpakowane pliki nie maja prawa zostac w bibliotece"
    assert not (psx / "Game (Disc 1).bin").exists()


@needs_chdman
@pytest.mark.asyncio
async def test_nothing_is_written_over(tmp_path):
    """A .chd of that name already being there means either a conversion that
    already happened or somebody else's disc. Either way the answer is no."""
    from handler.roms.chd_convert import ChdError, convert_disc_files

    psx = tmp_path / "psx"
    psx.mkdir()
    cue = _disc(psx)
    already = psx / "Game (Disc 1).chd"
    already.write_bytes(b"somebody else's disc")

    with pytest.raises(ChdError):
        await convert_disc_files(cue, psx)
    assert already.read_bytes() == b"somebody else's disc", "plik zostal nadpisany"


@pytest.mark.asyncio
async def test_a_source_outside_the_library_is_refused(tmp_path):
    """fs_path is a stored string and a row can point elsewhere, through a
    symlink or after the library path moved under it. This reads a file and
    then deletes things next to it, so it asks first."""
    from handler.roms.chd_convert import ChdError, convert_disc_files

    psx = tmp_path / "psx"
    psx.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    stranger = _disc(outside, "Not Ours")

    with pytest.raises(ChdError):
        await convert_disc_files(stranger, psx)
    assert stranger.is_file()


@needs_chdman
@pytest.mark.asyncio
async def test_a_stopped_conversion_leaves_the_disc_exactly_as_it_was(tmp_path):
    """Cancelling is a button somebody will press, and the disc it was working
    on is the one they still want to play afterwards."""
    from handler.roms.chd_convert import ChdError, convert_disc_files

    psx = tmp_path / "psx"
    psx.mkdir()
    cue = _disc(psx, sectors=16384)          # big enough to still be running
    before = {p.name: p.stat().st_size for p in psx.iterdir()}

    with pytest.raises(ChdError):
        await convert_disc_files(cue, psx, should_stop=lambda: True)

    after = {p.name: p.stat().st_size for p in psx.iterdir()}
    assert after == before, f"katalog sie zmienil: {after}"


@needs_chdman
@pytest.mark.asyncio
async def test_the_saving_is_reported_from_the_files_themselves(tmp_path):
    """The page offers this to save room, so the number it shows afterwards
    should be measured rather than assumed from a ratio."""
    from handler.roms.chd_convert import convert_disc_files

    psx = tmp_path / "psx"
    psx.mkdir()
    cue = _disc(psx, sectors=4096)

    done = await convert_disc_files(cue, psx)

    assert done.was_bytes == sum(p.stat().st_size for p in done.replaced), (
        "waga przed to suma plikow, ktore zastapiono"
    )
    assert done.now_bytes == done.path.stat().st_size
    assert done.was_bytes > done.now_bytes > 0, "konwersja ma cos oszczedzic"
