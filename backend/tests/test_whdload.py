"""Building a bootable Amiga hard drive out of a WHDLoad archive.

The pieces worth pinning down are the ones that were expensive to work out on a
real emulator: which Kickstart gets chosen, what the generated boot script says,
and that nothing is built while a required file is missing - an image assembled
without one boots to an error requester inside the Amiga, where the reason is
much harder to see than a sentence on the page.

Unpacking itself is not exercised here: it shells out to lhasa, which cannot
create archives, so a fixture would have to be a committed binary. The functions
around it take the file list as an argument for exactly that reason.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from handler.roms import whdload_handler as wh


@pytest.fixture(autouse=True)
def _isolated_root(tmp_path, monkeypatch):
    monkeypatch.setattr(wh, "firmware_root", lambda: tmp_path)
    return tmp_path


def _supply(root: Path, *, whdload=True, kickstart="kick40063.A600", rtb=True):
    """Put the shared pieces on disk the way an administrator would."""
    if whdload:
        (root / "whdload").mkdir(parents=True, exist_ok=True)
        (root / "whdload" / "WHDLoad").write_bytes(b"WHDL")
    if kickstart:
        (root / "puae").mkdir(parents=True, exist_ok=True)
        (root / "puae" / kickstart).write_bytes(b"\0" * 64)
        if rtb:
            (root / "whdload").mkdir(parents=True, exist_ok=True)
            (root / "whdload" / f"{kickstart}.RTB").write_bytes(b"RTB")


# ── Recognising the format ────────────────────────────────────────────────────

@pytest.mark.parametrize("name,expected", [
    ("Mentor_v1.1_Pl.lha", True),
    ("Turrican.LHA", True),
    ("something.lzh", True),
    ("Lemmings.adf", False),
    ("disk.zip", False),
])
def test_recognises_whdload_archives(name, expected):
    assert wh.is_whdload_archive(name) is expected


# ── Choosing a Kickstart ──────────────────────────────────────────────────────

def test_prefers_the_kickstart_that_is_not_aga_only(_isolated_root):
    # Both present: 40.063 wins over the A1200 ROM. This is the whole lesson
    # from getting a 1992 title to run - the A1200 ROM forces an AGA machine
    # and the game crashes on it.
    _supply(_isolated_root, kickstart="kick40063.A600")
    (_isolated_root / "puae" / "kick40068.A1200").write_bytes(b"\0" * 64)
    name, aga_only = wh.available_kickstart()
    assert name == "kick40063.A600"
    assert aga_only is False


def test_falls_back_to_an_aga_rom_when_it_is_all_there_is(_isolated_root):
    _supply(_isolated_root, kickstart="kick40068.A1200")
    name, aga_only = wh.available_kickstart()
    assert name == "kick40068.A1200"
    assert aga_only is True


def test_every_kickstart_goes_on_the_hard_drive(_isolated_root, monkeypatch):
    """The ROM a game wants is not the ROM the machine boots.

    This is the mistake that cost a round of testing: shipping only the boot
    Kickstart left Mentor asking for the 1.3 sitting unused in the store.
    """
    _supply(_isolated_root, kickstart="kick40063.A600")
    (_isolated_root / "puae" / "kick34005.A500").write_bytes(b"\0" * 32)
    (_isolated_root / "whdload" / "kick34005.A500.RTB").write_bytes(b"RTB13")

    monkeypatch.setattr(wh, "_unpack", lambda a, d: _one_slave(d))
    data = wh.build_image(Path("Mentor.lha"))

    import io
    import zipfile
    names = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
    assert "Devs/Kickstarts/kick34005.A500" in names
    assert "Devs/Kickstarts/kick34005.A500.RTB" in names
    assert "Devs/Kickstarts/kick40063.A600" in names


def _one_slave(dest: Path) -> list[Path]:
    p = dest / "Mentor" / "Mentor.Slave"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"slave")
    return [p]


def test_a_kickstart_that_cannot_boot_a_hard_drive_does_not_count(_isolated_root):
    # 1.3 has no hard-drive filesystem in ROM; a machine booted on it stops at
    # "Not a DOS disk". It is fine as the ROM WHDLoad emulates, not as this one.
    _supply(_isolated_root, kickstart=None)
    (_isolated_root / "puae").mkdir(parents=True, exist_ok=True)
    (_isolated_root / "puae" / "kick34005.A500").write_bytes(b"\0" * 64)
    assert wh.available_kickstart() is None


def test_machine_matches_the_chosen_rom(_isolated_root, monkeypatch):
    monkeypatch.setattr(wh, "_unpack", lambda a, d: [d / "Game" / "Game.Slave"])
    monkeypatch.setattr(wh, "_find_slave", lambda f, r: f[0])

    _supply(_isolated_root, kickstart="kick40063.A600")
    assert wh.plan(Path("x.lha")).machine["DENISE_REVISION"] == "ECS"

    (_isolated_root / "puae" / "kick40063.A600").unlink()
    (_isolated_root / "whdload" / "kick40063.A600.RTB").unlink()
    _supply(_isolated_root, kickstart="kick40068.A1200")
    p = wh.plan(Path("x.lha"))
    assert p.machine["DENISE_REVISION"] == "AGA"
    assert p.warning and "AGA" in p.warning


# ── Refusing to build half an image ───────────────────────────────────────────

def _stub_archive(monkeypatch, slave="Mentor/Mentor.Slave"):
    def fake_unpack(archive, dest):
        p = dest / slave
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"slave")
        return [p]
    monkeypatch.setattr(wh, "_unpack", fake_unpack)


def test_plan_reports_every_missing_piece(_isolated_root, monkeypatch):
    _stub_archive(monkeypatch)
    p = wh.plan(Path("Mentor.lha"))
    assert p.ok is False
    assert "whdload" in p.missing and "kickstart" in p.missing


def test_a_missing_relocation_table_warns_rather_than_blocks(_isolated_root, monkeypatch):
    # Which table is needed depends on the ROM this particular game asks
    # WHDLoad to emulate, and that cannot be known without reading the slave.
    # Refusing to build would ground every title over one absent file.
    _stub_archive(monkeypatch)
    _supply(_isolated_root, rtb=False)
    p = wh.plan(Path("Mentor.lha"))
    assert p.ok is True
    assert p.warning and "relocation table" in p.warning


def test_plan_is_ok_once_everything_is_supplied(_isolated_root, monkeypatch):
    _stub_archive(monkeypatch)
    _supply(_isolated_root)
    p = wh.plan(Path("Mentor.lha"))
    assert p.ok is True
    assert p.missing == ()
    assert p.slave == "Mentor/Mentor.Slave"
    assert p.warning is None


def test_an_archive_without_a_slave_is_not_a_whdload_install(_isolated_root, monkeypatch):
    def fake_unpack(archive, dest):
        p = dest / "readme.txt"
        p.write_bytes(b"hello")
        return [p]
    monkeypatch.setattr(wh, "_unpack", fake_unpack)
    _supply(_isolated_root)
    p = wh.plan(Path("notagame.lha"))
    assert p.ok is False
    assert p.missing == ("slave",)


def test_build_refuses_while_a_piece_is_missing(_isolated_root, monkeypatch):
    _stub_archive(monkeypatch)
    with pytest.raises(ValueError, match="missing"):
        wh.build_image(Path("Mentor.lha"))


# ── The boot script ───────────────────────────────────────────────────────────

def test_startup_sequence_enters_the_game_directory():
    s = wh._startup_sequence("Mentor/Mentor.Slave")
    assert s == 'cd "Mentor"\nC:WHDLoad "Mentor.Slave" PRELOAD NOWRITECACHE\n'


def test_startup_sequence_without_a_directory_does_not_cd():
    s = wh._startup_sequence("Game.Slave")
    assert s == 'C:WHDLoad "Game.Slave" PRELOAD NOWRITECACHE\n'


def test_the_write_cache_is_off_so_a_savegame_reaches_the_drive():
    """The one option a player's saves depend on.

    WHDLoad caches writes and defers them until the program exits. Nobody exits
    a game in a browser tab - they close it - so without this the savegame is
    thrown away with the machine. Verified on a real title: the drive image
    hashed identically before and after saving from inside the game.
    """
    assert "NOWRITECACHE" in wh._startup_sequence("Game.Slave")


def test_startup_sequence_handles_a_nested_install():
    s = wh._startup_sequence("Games/Turrican/Turrican.slave")
    assert s.startswith('cd "Games/Turrican"\n')


# ── Picking a slave out of several ────────────────────────────────────────────

def test_the_shallowest_slave_wins(tmp_path):
    files = [
        tmp_path / "Game" / "extras" / "Game.CD32.Slave",
        tmp_path / "Game" / "Game.Slave",
    ]
    assert wh._find_slave(files, tmp_path) == files[1]


def test_among_equals_the_plain_name_wins(tmp_path):
    files = [
        tmp_path / "Game" / "Game.AGA.Slave",
        tmp_path / "Game" / "Game.Slave",
    ]
    assert wh._find_slave(files, tmp_path) == files[1]


# ── Multi-disk archives ───────────────────────────────────────────────────────

def _zip_of(tmp_path: Path, *names: str) -> Path:
    import zipfile
    p = tmp_path / "game.zip"
    with zipfile.ZipFile(p, "w") as z:
        for n in names:
            z.writestr(n, b"disk")
    return p


def test_disks_are_listed_in_insertion_order(tmp_path):
    p = _zip_of(tmp_path,
                "Legion (Disk 2 of 2).adf",
                "Legion (Disk 1 of 2).adf")
    assert wh.disks_in(p) == (
        "Legion (Disk 1 of 2).adf",
        "Legion (Disk 2 of 2).adf",
    )


def test_disk_ten_comes_after_disk_two(tmp_path):
    # Alphabetical order would put 10 between 1 and 2, and a game handed its
    # disks out of order asks for one already sitting in a drive.
    p = _zip_of(tmp_path, "Game Disk 10.adf", "Game Disk 2.adf", "Game Disk 1.adf")
    assert wh.disks_in(p) == ("Game Disk 1.adf", "Game Disk 2.adf", "Game Disk 10.adf")


def test_non_disk_members_are_ignored(tmp_path):
    p = _zip_of(tmp_path, "readme.txt", "cover.png", "Game.adf", "__MACOSX/Game.adf")
    assert wh.disks_in(p) == ("Game.adf",)


def test_a_bare_floppy_lists_no_disks(tmp_path):
    p = tmp_path / "Game.adf"
    p.write_bytes(b"x")
    assert wh.disks_in(p) == ()


def test_a_corrupt_archive_is_not_fatal(tmp_path):
    p = tmp_path / "broken.zip"
    p.write_bytes(b"not a zip at all")
    assert wh.disks_in(p) == ()


def test_plan_carries_the_disks_for_a_floppy_archive(_isolated_root, tmp_path):
    _supply(_isolated_root)
    p = _zip_of(tmp_path, "A (Disk 1 of 2).adf", "A (Disk 2 of 2).adf")
    plan = wh.plan(p)
    # An archive holding more than one disk is a set, whichever way the disks
    # arrived - the player fills a drive per disk either way.
    assert plan.mode == "floppyset"
    assert plan.ok is True
    assert len(plan.disks) == 2


# ── Disks split across separate files ─────────────────────────────────────────

def _touch(d: Path, *names: str) -> None:
    for n in names:
        (d / n).write_bytes(b"disk")


def test_loose_disks_of_one_title_find_each_other(tmp_path):
    _touch(tmp_path,
           "Legion (1996)(Gobi)(PL)(Disk 1 of 2)[cr WT].adf",
           "Legion (1996)(Gobi)(PL)(Disk 2 of 2)[cr WT].adf")
    found = wh.sibling_disks(tmp_path / "Legion (1996)(Gobi)(PL)(Disk 1 of 2)[cr WT].adf")
    assert [p.name for p in found] == [
        "Legion (1996)(Gobi)(PL)(Disk 1 of 2)[cr WT].adf",
        "Legion (1996)(Gobi)(PL)(Disk 2 of 2)[cr WT].adf",
    ]


def test_opening_the_second_disk_still_finds_the_first(tmp_path):
    _touch(tmp_path, "Game (Disk 1 of 2).adf", "Game (Disk 2 of 2).adf")
    found = wh.sibling_disks(tmp_path / "Game (Disk 2 of 2).adf")
    assert [p.name for p in found][0] == "Game (Disk 1 of 2).adf"


def test_a_different_title_is_not_a_sibling(tmp_path):
    _touch(tmp_path, "Legion (Disk 1 of 2).adf", "Turrican (Disk 2 of 2).adf")
    assert wh.sibling_disks(tmp_path / "Legion (Disk 1 of 2).adf") == ()


def test_a_number_in_a_title_is_not_a_disk_number(tmp_path):
    # "1943" and "Turrican 2" would otherwise be read as disks of something.
    _touch(tmp_path, "1943 - The Battle of Midway.adf", "Turrican 2.adf")
    assert wh.sibling_disks(tmp_path / "1943 - The Battle of Midway.adf") == ()


def test_a_lone_disk_of_a_set_is_not_a_set(tmp_path):
    _touch(tmp_path, "Game (Disk 1 of 3).adf")
    assert wh.sibling_disks(tmp_path / "Game (Disk 1 of 3).adf") == ()


def test_loose_disks_are_ordered_numerically(tmp_path):
    _touch(tmp_path, *[f"Game (Disk {n} of 11).adf" for n in (1, 2, 10, 11)])
    found = wh.sibling_disks(tmp_path / "Game (Disk 1 of 11).adf")
    assert [p.name for p in found] == [
        "Game (Disk 1 of 11).adf", "Game (Disk 2 of 11).adf",
        "Game (Disk 10 of 11).adf", "Game (Disk 11 of 11).adf",
    ]


@pytest.mark.parametrize("names", [
    ("Game Disk 1.adf", "Game Disk 2.adf"),
    ("Game [Disk 1].adf", "Game [Disk 2].adf"),
    ("Game (Disc 1 of 2).adf", "Game (Disc 2 of 2).adf"),
])
def test_the_common_ways_of_writing_a_disk_number(tmp_path, names):
    _touch(tmp_path, *names)
    assert len(wh.sibling_disks(tmp_path / names[0])) == 2


def test_plan_treats_a_loose_set_as_one_title(_isolated_root, tmp_path):
    _supply(_isolated_root)
    _touch(tmp_path, "Game (Disk 1 of 2).adf", "Game (Disk 2 of 2).adf")
    p = wh.plan(tmp_path / "Game (Disk 1 of 2).adf")
    assert p.mode == "floppyset"
    assert p.disks == ("Game (Disk 1 of 2).adf", "Game (Disk 2 of 2).adf")


def test_plan_leaves_a_single_floppy_alone(_isolated_root, tmp_path):
    _supply(_isolated_root)
    _touch(tmp_path, "Solo.adf")
    p = wh.plan(tmp_path / "Solo.adf")
    assert p.mode == "floppy"
    assert p.disks == ()


def test_build_packs_a_loose_set(_isolated_root, tmp_path):
    import io
    import zipfile
    _supply(_isolated_root)
    _touch(tmp_path, "Game (Disk 1 of 2).adf", "Game (Disk 2 of 2).adf")
    data = wh.build_image(tmp_path / "Game (Disk 1 of 2).adf")
    assert set(zipfile.ZipFile(io.BytesIO(data)).namelist()) == {
        "Game (Disk 1 of 2).adf", "Game (Disk 2 of 2).adf",
    }


def test_build_refuses_a_single_floppy(_isolated_root, tmp_path):
    _supply(_isolated_root)
    _touch(tmp_path, "Solo.adf")
    with pytest.raises(ValueError, match="single disk"):
        wh.build_image(tmp_path / "Solo.adf")


# ── Support-file names ────────────────────────────────────────────────────────

def test_support_store_accepts_what_it_asks_for(_isolated_root):
    assert wh.store_support_file("WHDLoad", b"x")["size"] == 1
    assert wh.store_support_file("kick40063.A600.RTB", b"yy")["size"] == 2


@pytest.mark.parametrize("name", [
    "../../etc/passwd",
    "kick40063.A600",          # the ROM itself belongs in the firmware store
    "WHDLoad.exe",
    "anything.RTB",
])
def test_support_store_refuses_anything_else(_isolated_root, name):
    with pytest.raises(ValueError):
        wh.store_support_file(name, b"x")


def test_support_store_refuses_an_empty_file(_isolated_root):
    with pytest.raises(ValueError):
        wh.store_support_file("WHDLoad", b"")


# ── Removing, and fetching one row at a time ─────────────────────────────────

def test_support_remove_drops_a_stored_file(_isolated_root):
    wh.store_support_file("WHDLoad", b"x")
    assert wh.remove_support_file("WHDLoad") is True
    assert not (wh.support_dir() / "WHDLoad").exists()


def test_support_remove_says_so_when_there_was_nothing(_isolated_root):
    assert wh.remove_support_file("kick40063.A600.RTB") is False


@pytest.mark.parametrize("name", [
    "../../etc/passwd",
    "whdload/../../secret",
    "kick40063.A600",          # the ROM itself belongs in the firmware store
    "anything.RTB",
])
def test_support_remove_refuses_anything_but_its_own_names(_isolated_root, name):
    # The same guard as storing, and for a better reason: a path walked out of
    # the support directory here deletes somebody else's file.
    with pytest.raises(ValueError):
        wh.remove_support_file(name)


@pytest.mark.asyncio
async def test_fetching_one_row_leaves_the_others_alone(_isolated_root, monkeypatch):
    # The button beside a row asks for that file. Nothing else may go over the
    # network because of it - least of all a second host that is not involved.
    _supply(_isolated_root, whdload=False, kickstart="kick40063.A600", rtb=False)
    monkeypatch.setattr(wh, "_download", _refuse_to_download)
    result = await wh.fetch_support("kick40063.A600.RTB")
    assert result["failed"] == {"kick40063.A600.RTB": "AssertionError"}
    assert "WHDLoad" not in result["fetched"] + result["already_present"]


@pytest.mark.asyncio
async def test_fetching_a_name_nobody_has_asks_for_nothing(_isolated_root, monkeypatch):
    # A screen left open while the Kickstart it named was removed. Nothing to
    # fetch is an empty answer, not an error and not a download.
    _supply(_isolated_root, whdload=True, kickstart="kick40063.A600", rtb=True)
    monkeypatch.setattr(wh, "_download", _refuse_to_download)
    result = await wh.fetch_support("kick33180.A500.RTB")
    assert result == {"fetched": [], "already_present": [], "failed": {}}


async def _refuse_to_download(urls):
    raise AssertionError(f"nothing should have been fetched, was asked for {urls}")


# ── Telling an install from a set of floppies ────────────────────────────────

def _zip_with(tmp_path, name, members):
    import zipfile
    p = tmp_path / name
    with zipfile.ZipFile(p, "w") as z:
        for member, data in members.items():
            z.writestr(member, data)
    return p


def test_a_zip_holding_a_slave_is_a_whdload_install(tmp_path):
    # How the collections actually publish them: Another World arrives as
    # AnotherWorld_v2.4_0425.zip with the install inside. Judged by extension
    # it looked like a floppy, so no hard drive was ever built and the machine
    # came up with nothing in its drive.
    p = _zip_with(tmp_path, "AnotherWorld_v2.4_0425.zip", {
        "AnotherWorld/AnotherWorld.slave": b"slave",
        "AnotherWorld/data/bank01": b"data",
    })
    assert wh.looks_like_whdload(p) is True


def test_a_zip_of_floppies_is_not_one(tmp_path):
    p = _zip_with(tmp_path, "Legion.zip", {
        "Legion (Disk 1 of 2).adf": b"\0" * 16,
        "Legion (Disk 2 of 2).adf": b"\0" * 16,
    })
    assert wh.looks_like_whdload(p) is False


def test_an_lha_is_taken_at_its_word(tmp_path):
    # Not opened: that is how WHDLoad has always shipped, and unpacking every
    # one to check would cost an unpack per listing.
    p = tmp_path / "Mentor_v1.1_Pl.lha"
    p.write_bytes(b"not really an archive")
    assert wh.looks_like_whdload(p) is True


def test_a_bare_floppy_is_not_one(tmp_path):
    p = tmp_path / "Dungeon Master.adf"
    p.write_bytes(b"\0" * 16)
    assert wh.looks_like_whdload(p) is False


def test_something_claiming_to_be_a_zip_and_failing_to_be_one(tmp_path):
    # A truncated download must read as "not a WHDLoad install" rather than
    # taking the plan down with it.
    p = tmp_path / "half-downloaded.zip"
    p.write_bytes(b"PK\x03\x04 and then nothing")
    assert wh.looks_like_whdload(p) is False


def test_a_zip_entry_that_escapes_its_directory_is_refused(tmp_path):
    import zipfile
    p = tmp_path / "evil.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("../../escaped.txt", b"x")
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(ValueError, match="escapes"):
        wh._unpack_zip(p, dest)
    assert not (tmp_path.parent / "escaped.txt").exists()


def test_a_zip_that_claims_to_unpack_to_more_than_any_install_is_refused(tmp_path, monkeypatch):
    # Checked before extracting, so a bomb is refused rather than written out
    # and then noticed.
    monkeypatch.setattr(wh, "MAX_UNPACKED_BYTES", 64)
    p = _zip_with(tmp_path, "big.zip", {"a": b"x" * 1024})
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(ValueError, match="more than a WHDLoad install"):
        wh._unpack_zip(p, dest)
    assert not any(dest.iterdir())


def test_a_zipped_install_unpacks_with_its_directories(tmp_path):
    p = _zip_with(tmp_path, "AnotherWorld.zip", {
        "AnotherWorld/AnotherWorld.slave": b"slave",
        "AnotherWorld/data/bank01": b"data",
    })
    dest = tmp_path / "out"
    dest.mkdir()
    files = wh._unpack(p, dest)
    assert {str(f.relative_to(dest)).replace("\\", "/") for f in files} == {
        "AnotherWorld/AnotherWorld.slave", "AnotherWorld/data/bank01",
    }


# ── What the player saved ─────────────────────────────────────────────────────
# A WHDLoad title writes its savegame onto the hard drive it runs from, and that
# drive is built again from the archive on every launch - which is what lets a
# replaced Kickstart take effect, and what would otherwise throw the savegame
# away. The browser sends back the files that differ; these are the rules for
# letting them in again.

def _save_zip(members: dict[str, bytes]) -> bytes:
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for member, data in members.items():
            z.writestr(member, data)
    return buf.getvalue()


def _built(data: bytes):
    import io
    import zipfile
    return zipfile.ZipFile(io.BytesIO(data))


def _stub_archive_with_data(monkeypatch):
    """An install that ships a file the game later writes over."""
    def fake_unpack(archive, dest):
        slave = dest / "Mentor" / "Mentor.Slave"
        slave.parent.mkdir(parents=True, exist_ok=True)
        slave.write_bytes(b"slave")
        table = dest / "Mentor" / "highscores"
        table.write_bytes(b"empty")
        return [slave, table]
    monkeypatch.setattr(wh, "_unpack", fake_unpack)


def test_a_saved_file_rides_back_into_the_drive(_isolated_root, monkeypatch):
    _stub_archive(monkeypatch)
    _supply(_isolated_root)
    data = wh.build_image(Path("Mentor.lha"),
                          saves=_save_zip({"Mentor/Mentor.save": b"level 7"}))
    z = _built(data)
    assert z.read("Mentor/Mentor.save") == b"level 7"
    # A save that ADDS a file is the normal case, and the file listing is taken
    # after the overlay for exactly this reason - the archive never held it.
    assert z.read("Mentor/Mentor.Slave") == b"slave"


def test_a_save_wins_over_the_file_the_archive_shipped(_isolated_root, monkeypatch):
    _stub_archive_with_data(monkeypatch)
    _supply(_isolated_root)
    data = wh.build_image(Path("Mentor.lha"),
                          saves=_save_zip({"Mentor/highscores": b"1. GD"}))
    assert _built(data).read("Mentor/highscores") == b"1. GD"


def test_the_drive_is_unchanged_when_nothing_was_saved(_isolated_root, monkeypatch):
    _stub_archive_with_data(monkeypatch)
    _supply(_isolated_root)
    plain = set(_built(wh.build_image(Path("Mentor.lha"))).namelist())
    assert "Mentor/highscores" in plain
    assert "Mentor/Mentor.save" not in plain


@pytest.mark.parametrize("member", [
    "Devs/Kickstarts/kick40063.A600",
    "devs/kickstarts/kick40063.A600",     # AmigaDOS does not care about case
    "DEVS/Kickstarts/anything.RTB",
    "S/Startup-Sequence",
    "s/startup-sequence",
    "C/WHDLoad",
])
def test_a_save_may_not_take_over_what_gd_puts_on_the_drive(
    _isolated_root, monkeypatch, member,
):
    """The paths GD owns decide which ROM boots and what runs at startup.

    Left open, a save could ship its own Kickstart and the machine would boot
    that instead of the one the administrator installed - and the entry would
    also collide with GD's own, leaving the emulator to pick between two files
    of the same name.
    """
    _stub_archive(monkeypatch)
    _supply(_isolated_root)
    with pytest.raises(ValueError, match="may not write"):
        wh.build_image(Path("Mentor.lha"), saves=_save_zip({member: b"mine"}))


def test_a_save_may_not_escape_the_drive(_isolated_root, monkeypatch):
    _stub_archive(monkeypatch)
    _supply(_isolated_root)
    with pytest.raises(ValueError, match="escapes"):
        wh.build_image(Path("Mentor.lha"),
                       saves=_save_zip({"../../escaped": b"nope"}))


def test_an_oversized_save_is_refused_before_anything_is_written(
    _isolated_root, monkeypatch,
):
    _stub_archive(monkeypatch)
    _supply(_isolated_root)
    monkeypatch.setattr(wh, "MAX_SAVE_BYTES", 16)
    with pytest.raises(ValueError, match="larger than a save"):
        wh.build_image(Path("Mentor.lha"),
                       saves=_save_zip({"Mentor/big": b"x" * 64}))


def test_a_save_holding_too_many_files_is_refused(_isolated_root, monkeypatch):
    _stub_archive(monkeypatch)
    _supply(_isolated_root)
    monkeypatch.setattr(wh, "MAX_SAVE_ENTRIES", 2)
    with pytest.raises(ValueError, match="more files than a save"):
        wh.build_image(Path("Mentor.lha"), saves=_save_zip({
            "Mentor/a": b"1", "Mentor/b": b"2", "Mentor/c": b"3",
        }))
