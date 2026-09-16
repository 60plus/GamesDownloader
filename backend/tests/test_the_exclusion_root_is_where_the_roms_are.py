"""The folder a pattern is measured against has to be the folder that is walked.

Exclusion patterns are relative to a platform's directory, so both sides need
the same root. The scan takes it from the directory it is walking
(`platform_dir`, and `fs_slug = platform_dir.name`); the settings screen built
it as `roms_root / platform.fs_slug` instead.

Those are not the same folder. `slug_from_fs_slug` maps several directory names
onto one platform - `genesis`, `megadrive` and `md` all mean the same shelf -
so a library whose ROMs sit in `megadrive/` while the row stores `genesis` gets
patterns saved against a directory that does not exist, and matched against one
that does. The pattern then covers nothing, silently, and the preview shows an
empty list while the scan goes on adding what it was told to skip.

The root is taken from where the rows actually are, which is what the scan used
when it made them.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def _platform(fs_slug="genesis", slug="genesis", pid=1):
    return SimpleNamespace(id=pid, slug=slug, fs_slug=fs_slug)


@pytest.mark.asyncio
async def test_the_root_follows_the_rows_not_the_stored_slug(monkeypatch):
    from endpoints.roms import roms_router as R

    async def roms_path():
        return "/data/roms"

    async def rows(_pid):
        # What the scan actually wrote: it walked `megadrive/`.
        return [{"id": 1, "fs_name": "Sonic.bin", "name": "Sonic",
                 "size_bytes": 1, "fs_path": "/data/roms/megadrive"}]

    monkeypatch.setattr(R, "_get_roms_path", roms_path)
    monkeypatch.setattr(R.rom_handler, "all_for_platform", rows)

    root = await R._platform_root(_platform(fs_slug="genesis"))
    assert root == "/data/roms/megadrive", (
        "korzen liczony ze slugi zapisanej w wierszu, a nie z katalogu, ktory "
        "skan naprawde obchodzi - wzorce nie pasuja do niczego"
    )


@pytest.mark.asyncio
async def test_an_empty_shelf_falls_back_to_the_stored_slug(monkeypatch):
    """A platform with no rows yet has no evidence on disk. The stored slug is
    the best guess available, and it is what the scan will use when it first
    walks a folder of that name."""
    from endpoints.roms import roms_router as R

    async def roms_path():
        return "/data/roms"

    async def rows(_pid):
        return []

    monkeypatch.setattr(R, "_get_roms_path", roms_path)
    monkeypatch.setattr(R.rom_handler, "all_for_platform", rows)

    assert await R._platform_root(_platform(fs_slug="genesis")) == "/data/roms/genesis"


@pytest.mark.asyncio
async def test_rows_scattered_across_folders_take_the_commonest(monkeypatch):
    """A shelf can hold rows written by two different folder names over time.
    One root has to be chosen, and the one holding most of the library is the
    one most patterns were typed against."""
    from endpoints.roms import roms_router as R

    async def roms_path():
        return "/data/roms"

    async def rows(_pid):
        return [
            {"id": 1, "fs_name": "a.bin", "name": "a", "size_bytes": 1,
             "fs_path": "/data/roms/megadrive"},
            {"id": 2, "fs_name": "b.bin", "name": "b", "size_bytes": 1,
             "fs_path": "/data/roms/megadrive"},
            {"id": 3, "fs_name": "c.bin", "name": "c", "size_bytes": 1,
             "fs_path": "/data/roms/genesis"},
        ]

    monkeypatch.setattr(R, "_get_roms_path", roms_path)
    monkeypatch.setattr(R.rom_handler, "all_for_platform", rows)

    assert await R._platform_root(_platform(fs_slug="genesis")) == "/data/roms/megadrive"


def test_both_sides_ask_the_same_helper():
    """The preview and the save have to agree, or a pattern is judged one way
    when it is stored and another way when it is shown."""
    import io
    import pathlib

    backend = pathlib.Path(__file__).resolve().parent.parent
    source = io.open(backend / "endpoints" / "roms" / "roms_router.py",
                     encoding="utf-8").read()

    for name in ("_excluded_rows", "set_platform_exclusions"):
        at = source.index(f"async def {name}(")
        body = source[at:source.index("\n@", at)]
        assert "_platform_root(" in body, f"{name} liczy korzen po swojemu"
        assert "platform.fs_slug" not in body, (
            f"{name} nadal sklada korzen ze slugi zapisanej w wierszu"
        )
