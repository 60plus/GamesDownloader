"""Writing a playlist into the library, beside the discs it names.

GD has been able to put an .m3u inside a download since 1.0.32, but nothing
ever wrote one to disk. That is the difference between a playlist the browser
sees once and a playlist that is part of the library: copied to a handheld,
opened by RetroArch, or simply still there after the next scan.

The file is deliberately plain: one filename per line and nothing else. A
`path|Label` line reads nicely in EmulatorJS's own disc menu and is fatal to
PCSX-ReARMed, which hands the whole line to the filesystem. That was found by
running it, and there is a test below holding the lesson.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


def _discs(*names):
    """Rows as disk_set returns them: whole discs, in order, no tracks."""
    return [SimpleNamespace(fs_name=n, track_of=None) for n in names]


@pytest.mark.asyncio
async def test_a_multi_disc_title_gets_a_playlist_beside_its_discs(
    tmp_path, monkeypatch
):
    from endpoints.roms import roms_router
    from handler.database.rom_handler import rom_handler

    library = tmp_path / "roms"
    psx = library / "psx"
    psx.mkdir(parents=True)
    names = [f"Final Fantasy VIII (USA) (Disc {n}).chd" for n in range(1, 5)]
    for n in names:
        (psx / n).write_bytes(b"disc")

    async def _roms_path():
        return str(library)

    async def _get_by_id(rom_id):
        return SimpleNamespace(
            id=rom_id, name="Final Fantasy VIII", fs_path=str(psx),
            fs_name=names[0], fs_name_no_ext=names[0][:-4],
        )

    async def _disk_set(rom_id):
        return _discs(*names)

    monkeypatch.setattr(roms_router, "_get_roms_path", _roms_path)
    monkeypatch.setattr(rom_handler, "get_by_id", _get_by_id)
    monkeypatch.setattr(rom_handler, "disk_set", _disk_set)

    out = await roms_router.write_rom_playlist.__wrapped__(None, 65)

    written = psx / "Final Fantasy VIII.m3u"
    assert written.is_file(), "the playlist is written beside the discs"
    assert written.read_text(encoding="utf-8").splitlines() == names
    assert out["name"] == "Final Fantasy VIII.m3u"
    assert out["discs"] == 4


@pytest.mark.asyncio
async def test_a_single_disc_title_is_refused_rather_than_given_a_one_line_file(
    tmp_path, monkeypatch
):
    """A playlist with one entry is not a playlist, and some cores will boot it
    in place of the disc. Refusing is the honest answer, and it keeps the
    button from writing clutter into a library that had nothing to switch."""
    from fastapi import HTTPException

    from endpoints.roms import roms_router
    from handler.database.rom_handler import rom_handler

    psx = tmp_path / "roms" / "psx"
    psx.mkdir(parents=True)
    (psx / "Tekken 2.chd").write_bytes(b"disc")

    async def _roms_path():
        return str(tmp_path / "roms")

    async def _get_by_id(rom_id):
        return SimpleNamespace(
            id=rom_id, name="Tekken 2", fs_path=str(psx),
            fs_name="Tekken 2.chd", fs_name_no_ext="Tekken 2",
        )

    monkeypatch.setattr(roms_router, "_get_roms_path", _roms_path)
    monkeypatch.setattr(rom_handler, "get_by_id", _get_by_id)
    monkeypatch.setattr(rom_handler, "disk_set",
                        lambda rom_id: _as_async(_discs("Tekken 2.chd")))

    with pytest.raises(HTTPException) as refused:
        await roms_router.write_rom_playlist.__wrapped__(None, 7)
    assert refused.value.status_code == 422
    assert not list(psx.glob("*.m3u")), "nothing was written"


@pytest.mark.asyncio
async def test_a_row_pointing_outside_the_library_is_refused_before_writing(
    tmp_path, monkeypatch
):
    """fs_path is a stored string, and this route writes. A row that points
    somewhere else - through a symlink, or after the library path moved under
    it - must not turn a button into arbitrary file creation."""
    from fastapi import HTTPException

    from endpoints.roms import roms_router
    from handler.database.rom_handler import rom_handler

    library = tmp_path / "roms"
    (library / "psx").mkdir(parents=True)
    outside = tmp_path / "elsewhere"
    outside.mkdir()

    async def _roms_path():
        return str(library)

    async def _get_by_id(rom_id):
        return SimpleNamespace(
            id=rom_id, name="Escape", fs_path=str(outside),
            fs_name="a (Disc 1).chd", fs_name_no_ext="a (Disc 1)",
        )

    monkeypatch.setattr(roms_router, "_get_roms_path", _roms_path)
    monkeypatch.setattr(rom_handler, "get_by_id", _get_by_id)
    monkeypatch.setattr(rom_handler, "disk_set", lambda rom_id: _as_async(
        _discs("a (Disc 1).chd", "a (Disc 2).chd")))

    with pytest.raises(HTTPException) as refused:
        await roms_router.write_rom_playlist.__wrapped__(None, 9)
    assert refused.value.status_code == 403
    assert not list(outside.glob("*.m3u")), "nothing was written outside the library"


def test_the_playlist_never_carries_a_label_after_the_filename():
    """Learned by running it, not by reading it.

    EmulatorJS understands a `path|Label` line and uses the right hand side to
    title its own disc menu, so labelling looked free. PCSX-ReARMed does not:
    it hands the whole line to the filesystem, and a four disc set failed to
    load at all with

      Could't open '/Final Fantasy VIII (USA) (Disc 1).chd|Disc 1' for
      reading: No such file or directory
      Error opening CD-ROM plugin!
      [Content]: Failed to load content

    RetroArch dropped to its own menu and the game never started. Nicer menu
    entries are not worth a playlist the core cannot read, and both copies of
    it - the one in the library and the one handed to the browser - are the
    plain kind for that reason.
    """
    from endpoints.roms.roms_router import _playlist_for

    discs = [
        SimpleNamespace(fs_name="Game (Disc 1).chd", track_of=None, disk_number=1),
        SimpleNamespace(fs_name="Game (Disc 2).chd", track_of=None, disk_number=2),
    ]
    text = _playlist_for(discs)
    assert "|" not in text
    assert text.splitlines() == ["Game (Disc 1).chd", "Game (Disc 2).chd"]


def test_an_existing_playlist_is_recognised_whatever_it_is_called(tmp_path):
    """The button exists to fill a gap, so it has to know when there is none.
    Recognition is by content rather than by name: a playlist somebody wrote by
    hand, or one that came down with the discs, counts just as much as ours.
    """
    from endpoints.roms.roms_router import _existing_playlist

    discs = ["Game (Disc 1).chd", "Game (Disc 2).chd"]
    assert _existing_playlist(tmp_path, discs) is None

    (tmp_path / "whatever anyone called it.m3u").write_text(
        "Game (Disc 1).chd\nGame (Disc 2).chd\n", encoding="utf-8")
    assert _existing_playlist(tmp_path, discs) == "whatever anyone called it.m3u"


def test_a_playlist_for_a_different_game_does_not_count(tmp_path):
    """A shelf holds many titles. A playlist naming somebody else's discs is
    not this title's playlist, and treating it as one would hide the button on
    exactly the game that needs it."""
    from endpoints.roms.roms_router import _existing_playlist

    (tmp_path / "Other.m3u").write_text(
        "Other (Disc 1).chd\nOther (Disc 2).chd\n", encoding="utf-8")
    assert _existing_playlist(
        tmp_path, ["Game (Disc 1).chd", "Game (Disc 2).chd"]) is None


@pytest.mark.asyncio
async def test_the_emulator_is_handed_a_playlist_and_nothing_else(
    tmp_path, monkeypatch
):
    """What the browser loads as the game is a few hundred bytes.

    EmulatorJS only recognises a playlist by its extension, and it only sees
    extensions on the members of an archive, so the playlist has to arrive
    inside one. Putting the discs in there too is what we must not do: the
    extractor copies every extracted byte out of its heap one at a time from
    JavaScript, and a four disc set is 2.65 GiB. The discs go into the
    emulator's filesystem by another road; this carries the playlist alone.
    """
    import io
    import zipfile

    from endpoints.roms import roms_router
    from handler.database.rom_handler import rom_handler

    library = tmp_path / "roms"
    psx = library / "psx"
    psx.mkdir(parents=True)
    discs = [
        SimpleNamespace(fs_name="Game (Disc 1).chd", track_of=None, disk_number=1),
        SimpleNamespace(fs_name="Game (Disc 2).chd", track_of=None, disk_number=2),
    ]

    async def _roms_path():
        return str(library)

    async def _get_by_id(rom_id):
        return SimpleNamespace(
            id=rom_id, name="Game", fs_path=str(psx), fs_name_no_ext="Game")

    monkeypatch.setattr(roms_router, "_get_roms_path", _roms_path)
    monkeypatch.setattr(rom_handler, "get_by_id", _get_by_id)
    monkeypatch.setattr(rom_handler, "disk_set", lambda rom_id: _as_async(discs))

    response = await roms_router.rom_playlist_archive.__wrapped__(None, 65)
    with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
        assert archive.namelist() == ["Game.m3u"], "nothing but the playlist"
        assert archive.read("Game.m3u").decode().splitlines() == [
            "Game (Disc 1).chd", "Game (Disc 2).chd",
        ]
    assert len(response.body) < 4096, "a few hundred bytes, not a disc set"


@pytest.mark.asyncio
async def test_a_single_disc_title_has_no_playlist_to_hand_over(tmp_path, monkeypatch):
    from fastapi import HTTPException

    from endpoints.roms import roms_router
    from handler.database.rom_handler import rom_handler

    psx = tmp_path / "roms" / "psx"
    psx.mkdir(parents=True)

    async def _roms_path():
        return str(tmp_path / "roms")

    async def _get_by_id(rom_id):
        return SimpleNamespace(
            id=rom_id, name="Tekken 2", fs_path=str(psx), fs_name_no_ext="Tekken 2")

    monkeypatch.setattr(roms_router, "_get_roms_path", _roms_path)
    monkeypatch.setattr(rom_handler, "get_by_id", _get_by_id)
    monkeypatch.setattr(rom_handler, "disk_set", lambda rom_id: _as_async(
        [SimpleNamespace(fs_name="Tekken 2.chd", track_of=None, disk_number=1)]))

    with pytest.raises(HTTPException) as refused:
        await roms_router.rom_playlist_archive.__wrapped__(None, 7)
    assert refused.value.status_code == 422


def test_every_playlist_naming_this_set_is_found_for_removal(tmp_path):
    """Deleting the discs has to take the playlist with them.

    It is not a library row and no sheet names it, so neither of the two things
    that clean up after a deletion can reach it: the file would simply stay,
    naming four discs that are not there, and the next person to open the
    folder on a handheld would get an unplayable entry. All of them go, not
    just ours, because a hand-written one is left just as broken."""
    from endpoints.roms.roms_router import _playlists_naming

    discs = ["Game (Disc 1).chd", "Game (Disc 2).chd"]
    assert _playlists_naming(tmp_path, discs) == []

    (tmp_path / "Game.m3u").write_text(
        "Game (Disc 1).chd\nGame (Disc 2).chd\n", encoding="utf-8")
    (tmp_path / "by hand.m3u").write_text(
        "Game (Disc 2).chd\n", encoding="utf-8")
    (tmp_path / "Somebody else.m3u").write_text(
        "Other (Disc 1).chd\nOther (Disc 2).chd\n", encoding="utf-8")

    found = sorted(p.name for p in _playlists_naming(tmp_path, discs))
    assert found == ["Game.m3u", "by hand.m3u"], "somebody else's playlist stays"


def test_removing_a_playlist_goes_through_the_same_path_guard_as_a_rom(
    tmp_path, monkeypatch
):
    """The playlist is unlinked by the same helper that unlinks a stray track,
    which is what keeps it inside the ROM directory. Worth pinning rather than
    assuming: this is the one file GD writes into the library itself, so it is
    the one whose deletion path nobody would think to check."""
    from handler.roms import rom_removal

    library = tmp_path / "roms"
    library.mkdir()
    monkeypatch.setattr(rom_removal, "ROMS_PATH", str(library))

    inside = library / "Game.m3u"
    inside.write_text("Game (Disc 1).chd\nGame (Disc 2).chd\n", encoding="utf-8")
    outside = tmp_path / "elsewhere.m3u"
    outside.write_text("Game (Disc 1).chd\nGame (Disc 2).chd\n", encoding="utf-8")

    assert rom_removal.delete_paths([inside, outside]) == 1
    assert not inside.exists(), "the one in the library goes"
    assert outside.exists(), "and nothing outside it does"


def test_a_set_can_be_loaded_whole_when_the_player_can_put_every_disc_in_place():
    """Loading the whole set puts one file per disc into the emulator and hands
    the core a playlist naming them. That works when a disc IS one file, and
    now also when it is a zip, because the player unpacks those itself.

    A .7z is still out: the browser's DecompressionStream speaks deflate and
    nothing else, so there is no unpacking it without shipping a decoder.

    A sheet loose on disk is still out too, and for a different reason: a .cue
    is one library row and its .bin is not, so the player would fetch the sheet
    alone and the core would open a playlist pointing at a track that never
    arrived.

    All of those fail after the whole set has downloaded, which is the worst
    place to find out. The page asks first.
    """
    from endpoints.roms.roms_router import _set_loads_whole

    assert _set_loads_whole(["Game (Disc 1).chd", "Game (Disc 2).chd"])
    assert _set_loads_whole(["a.iso", "b.img", "c.pbp"])
    assert _set_loads_whole(["Game (Disc 1).zip", "Game (Disc 2).zip"])
    assert _set_loads_whole(["Game (Disc 1).chd", "Game (Disc 2).zip"]), \
        "a set may mix a bare image with an archive"

    assert not _set_loads_whole(["Game (Disc 1).cue", "Game (Disc 2).cue"])
    assert not _set_loads_whole(["Game (Disc 1).chd", "Game (Disc 2).7z"]), \
        "one archive the browser cannot open is enough to break it"
    assert not _set_loads_whole([])


def _zip_with(path, *members):
    """A deflated archive, the shape the library actually holds.

    Deliberately not stored: what comes down from an archive site is deflated,
    and stored is the one case that would have passed without any of the work
    this exercises.
    """
    import zipfile

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in members:
            archive.writestr(name, content)


def test_the_disc_inside_an_archive_is_the_sheet_and_never_its_track(tmp_path):
    """A .bin beside a .cue is half a disc. Handing it to a core gets a data
    file opened as a game, which is why the playlist has to name the sheet."""
    from endpoints.roms.roms_router import _disc_inside_archive

    archive = tmp_path / "Game (Disc 1).zip"
    _zip_with(archive,
              ("Game (Disc 1).bin", b"\0" * 64),
              ("Game (Disc 1).cue", b'FILE "Game (Disc 1).bin" BINARY\n'))
    assert _disc_inside_archive(archive) == "Game (Disc 1).cue"


def test_an_archive_holding_one_image_resolves_to_that_image(tmp_path):
    from endpoints.roms.roms_router import _disc_inside_archive

    archive = tmp_path / "Game (Disc 2).zip"
    _zip_with(archive, ("Game (Disc 2).iso", b"\0" * 64))
    assert _disc_inside_archive(archive) == "Game (Disc 2).iso"


def test_an_archive_with_nothing_playable_in_it_resolves_to_nothing(tmp_path):
    """Better to say so than to guess: a wrong name in the playlist fails
    inside the core, minutes after the download, with a message nobody sees."""
    from endpoints.roms.roms_router import _disc_inside_archive

    archive = tmp_path / "Game (Disc 3).zip"
    _zip_with(archive, ("readme.txt", b"hello"), ("scan.png", b"\x89PNG"))
    assert _disc_inside_archive(archive) is None

    assert _disc_inside_archive(tmp_path / "not there.zip") is None
    assert _disc_inside_archive(tmp_path / "Game (Disc 1).chd") is None


@pytest.mark.asyncio
async def test_the_emulator_playlist_names_the_disc_inside_each_archive(
    tmp_path, monkeypatch
):
    """The playlist has to name what the emulator will actually find.

    The player unpacks each archive into the emulator's filesystem, so what
    lands there is the .cue and its .bin - never the .zip the library row is
    named after. A playlist naming the .zip points at a file that does not
    exist on that side, and the core says so only in a log line nobody reads.
    """
    import io
    import zipfile

    from endpoints.roms import roms_router
    from handler.database.rom_handler import rom_handler

    library = tmp_path / "roms"
    psx = library / "psx"
    psx.mkdir(parents=True)
    names = [f"Final Fantasy IX (Europe) (Disc {n}).zip" for n in (1, 2)]
    for n in names:
        stem = n[:-4]
        _zip_with(psx / n,
                  (f"{stem}.bin", b"\0" * 64),
                  (f"{stem}.cue", f'FILE "{stem}.bin" BINARY\n'.encode()))

    async def _roms_path():
        return str(library)

    async def _get_by_id(rom_id):
        return SimpleNamespace(
            id=rom_id, name="Final Fantasy IX", fs_path=str(psx),
            fs_name=names[0], fs_name_no_ext=names[0][:-4],
        )

    monkeypatch.setattr(roms_router, "_get_roms_path", _roms_path)
    monkeypatch.setattr(rom_handler, "get_by_id", _get_by_id)
    monkeypatch.setattr(rom_handler, "disk_set", lambda rom_id: _as_async(_discs(*names)))

    response = await roms_router.rom_playlist_archive.__wrapped__(None, 91)
    with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
        assert archive.read("Final Fantasy IX.m3u").decode().splitlines() == [
            "Final Fantasy IX (Europe) (Disc 1).cue",
            "Final Fantasy IX (Europe) (Disc 2).cue",
        ]


@pytest.mark.asyncio
async def test_the_playlist_written_to_the_library_names_what_is_on_that_disk(
    tmp_path, monkeypatch
):
    """The two copies diverge on purpose, and this is the one that has to be
    honest about the folder it sits in. Beside four zips, a line naming a .cue
    points at nothing: the whole reason to have a file on disk is that it still
    works after the shelf is copied to a handheld.
    """
    from endpoints.roms import roms_router
    from handler.database.rom_handler import rom_handler

    library = tmp_path / "roms"
    psx = library / "psx"
    psx.mkdir(parents=True)
    names = [f"Final Fantasy IX (Europe) (Disc {n}).zip" for n in (1, 2)]
    for n in names:
        stem = n[:-4]
        _zip_with(psx / n, (f"{stem}.cue", b"FILE\n"))

    async def _roms_path():
        return str(library)

    async def _get_by_id(rom_id):
        return SimpleNamespace(
            id=rom_id, name="Final Fantasy IX", fs_path=str(psx),
            fs_name=names[0], fs_name_no_ext=names[0][:-4],
        )

    monkeypatch.setattr(roms_router, "_get_roms_path", _roms_path)
    monkeypatch.setattr(rom_handler, "get_by_id", _get_by_id)
    monkeypatch.setattr(rom_handler, "disk_set", lambda rom_id: _as_async(_discs(*names)))

    await roms_router.write_rom_playlist.__wrapped__(None, 91)
    written = psx / "Final Fantasy IX.m3u"
    assert written.read_text(encoding="utf-8").splitlines() == names


def test_a_playlist_in_the_library_never_becomes_a_game_of_its_own():
    """Pinned rather than discovered: `m3u` is absent from the scanner's
    extension list today, so a playlist sitting in the library is invisible to
    it. That is the whole reason writing one is safe, and it is one line away
    from being untrue - the Flash and DOS plans both add extensions to this
    same set. A playlist counted as a ROM would appear as a phantom game whose
    every checksum matches nothing.
    """
    from handler.filesystem.rom_scanner import _ROM_EXTENSIONS

    assert "m3u" not in _ROM_EXTENSIONS


async def _as_async(value):
    return value
