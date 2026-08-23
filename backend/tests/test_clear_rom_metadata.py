"""Clearing a platform's metadata has to clear the platform, not the first page.

`clear_platform_metadata` paged the platform with `list_for_platform(limit=9999)`
and then cleared one ROM per transaction. On a large set that meant it stopped
at ten thousand and reported the number as though it were the whole job; it
skipped every `extra_disk` and `missing_from_fs` row, because that listing query
filters those out for the shelf, so the extra disks of a multi-disk title kept
the metadata the operator had just asked to be rid of; and because clearing sets
`name` to NULL while the default sort is `name_asc`, and MariaDB puts NULLs
first, a second click walked the same already-cleared rows again.

The field list also lived twice, verbatim, and both copies were missing seven
things a scraper writes.
"""
from __future__ import annotations

from handler.database.rom_handler import (
    SCRAPED_METADATA_FIELDS,
    cleared_metadata_values,
)
from models.rom import Rom

# What "clear the scraped metadata" must not touch. Hashes and paths are the
# filesystem scan's, not a provider's, and announced_at is the record that this
# ROM has already been announced - clearing it would re-post every ROM in the
# library to Discord the next time the notifier ran.
FILESYSTEM_AND_BOOKKEEPING = (
    "id", "platform_id",
    "fs_name", "fs_name_no_ext", "fs_extension", "fs_path", "fs_size_bytes",
    "crc_hash", "md5_hash", "sha1_hash",
    "missing_from_fs", "disk_group", "disk_number", "extra_disk",
    "save_disk_name", "announced_at", "created_at", "updated_at",
)


def test_every_listed_field_exists_on_the_model():
    """The old code guarded each write with `hasattr`, so a typo dropped a
    field silently and permanently. Nothing catches that but this."""
    missing = [f for f in SCRAPED_METADATA_FIELDS if not hasattr(Rom, f)]
    assert missing == [], f"listed for clearing but not on Rom: {missing}"


def test_the_list_has_no_duplicates():
    assert len(set(SCRAPED_METADATA_FIELDS)) == len(SCRAPED_METADATA_FIELDS)


def test_clearing_nulls_the_scraped_fields():
    values = cleared_metadata_values()
    for field in SCRAPED_METADATA_FIELDS:
        assert values[field] is None, field


def test_clearing_marks_the_rom_unidentified():
    assert cleared_metadata_values()["is_identified"] is False


def test_clearing_leaves_the_filesystem_and_the_bookkeeping_alone():
    values = cleared_metadata_values()
    touched = [f for f in FILESYSTEM_AND_BOOKKEEPING if f in values]
    assert touched == [], f"a metadata reset must not write: {touched}"


def test_every_raw_provider_blob_is_cleared():
    """ss_metadata and igdb_metadata were cleared; launchbox_metadata, the third
    one of exactly the same kind, was not."""
    values = cleared_metadata_values()
    for blob in ("ss_metadata", "igdb_metadata", "launchbox_metadata"):
        assert blob in values, blob


def test_the_scraped_ids_and_times_go_with_their_fields():
    """Clearing `developer` while leaving `developer_ss_id` behind leaves the
    row half-scraped: unidentified, but still pointing at a provider record."""
    values = cleared_metadata_values()
    for field in ("developer_ss_id", "publisher_ss_id",
                  "hltb_id", "hltb_main_s", "hltb_extra_s", "hltb_complete_s"):
        assert field in values, field


def test_the_route_no_longer_pages_the_platform_to_clear_it():
    import inspect

    from endpoints.roms import roms_router

    source = inspect.getsource(roms_router.clear_platform_metadata)
    assert "9999" not in source
    assert "clear_metadata_for_platform" in source
