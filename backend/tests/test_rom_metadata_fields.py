"""Everything the ROM editor can send has to be something the handler will store.

The editor posts a field, the endpoint copies it into the update dict, and the
handler drops anything outside its whitelist - silently, because a whitelist
that complained would be a way to probe the schema. So a field added to the
editor and forgotten in the whitelist saves to nothing at all, reports success,
and is only noticed when a player wonders why their setting keeps reverting.
That is exactly how the Amiga save-disk name came to do nothing for a week.

These tests need no database: they compare the endpoint's own request model
against the handler's own whitelist.
"""
from __future__ import annotations

from sqlalchemy import inspect as sa_inspect

from endpoints.roms.roms_router import RomMetadataUpdate
from handler.database.rom_handler import _METADATA_FIELDS
from models.rom import Rom


def _rom_columns() -> set[str]:
    return {c.key for c in sa_inspect(Rom).mapper.column_attrs}


# Fields the editor sends that are NOT columns: each is an instruction to go and
# fetch something, and the endpoint turns it into a *_path before storing.
_NOT_COLUMNS = {
    "background_url", "support_url", "wheel_url",
    "bezel_url", "steamgrid_url", "video_url",
}


def test_every_editable_field_is_one_the_handler_will_store():
    sendable = set(RomMetadataUpdate.model_fields) - _NOT_COLUMNS
    columns = _rom_columns()
    forgotten = sorted(f for f in sendable & columns if f not in _METADATA_FIELDS)
    assert not forgotten, (
        "the editor can send these but the handler discards them: "
        + ", ".join(forgotten)
    )


def test_the_download_only_fields_really_are_not_columns():
    # Keeps the exemption list above honest: the day one of these becomes a
    # column, it has to be checked like the rest rather than sit exempt.
    columns = _rom_columns()
    assert not (_NOT_COLUMNS & columns)


def test_the_save_disk_name_survives_a_rescrape():
    # It is typed by hand and no scraper knows it, so clearing scraped metadata
    # must leave it alone - otherwise the next scrape silently unsets the name
    # the game asks for and the save disk stops being found.
    import inspect as py_inspect

    from handler.database.rom_handler import RomHandler

    source = py_inspect.getsource(RomHandler.clear_metadata)
    assert "save_disk_name" not in source


def test_identity_and_filesystem_columns_stay_out_of_reach():
    # The whitelist exists to stop a request rewriting which file a ROM is, so
    # these must never drift into it.
    for column in ("id", "platform_id", "fs_path", "fs_name", "fs_size_bytes",
                   "missing_from_fs", "md5_hash", "sha1_hash", "crc_hash"):
        assert column not in _METADATA_FIELDS
