"""The blank save disk GD hands the Amiga.

A game that saves writes to a floppy, so the machine has to be given one it can
already write to. Every field checked here is one the Amiga itself checks: get
any of them wrong and the disk comes up as "not a DOS disk", which the player
would meet as their save silently having nowhere to go.
"""
from __future__ import annotations

import struct

from handler.roms import amiga_disk as ad


def _longs(block: bytes) -> list[int]:
    return [struct.unpack_from(">I", block, i)[0] for i in range(0, len(block), 4)]


def _block(image: bytes, n: int) -> bytes:
    return image[n * ad.BLOCK_SIZE:(n + 1) * ad.BLOCK_SIZE]


def test_the_image_is_the_size_of_a_real_floppy():
    # 880 KB. Tools and emulators recognise a disk by its size before anything
    # else, so a byte out either way makes it unreadable.
    assert len(ad.blank_adf()) == 901120


def test_it_announces_itself_as_a_dos_disk():
    image = ad.blank_adf()
    assert image[0:3] == b"DOS"


def test_the_filesystem_flag_follows_the_argument():
    assert ad.blank_adf(ffs=True)[3] == 1
    assert ad.blank_adf(ffs=False)[3] == 0


def test_the_default_is_the_filesystem_every_amiga_understands():
    # FFS came with Kickstart 2.0 in 1990; anything older calls an FFS disk
    # unreadable, which is exactly what Dungeon Master did.
    assert ad.blank_adf()[3] == 0


def test_it_is_deliberately_not_bootable():
    # A save disk is never booted from, and a zero checksum is what says so.
    image = ad.blank_adf()
    assert struct.unpack_from(">I", image, 4)[0] == 0


def test_the_root_block_is_a_root_directory():
    root = _block(ad.blank_adf(), ad.ROOT_BLOCK)
    assert struct.unpack_from(">I", root, 0)[0] == ad.T_HEADER
    assert struct.unpack_from(">I", root, ad.BLOCK_SIZE - 4)[0] == ad.ST_ROOT
    assert struct.unpack_from(">I", root, 12)[0] == ad.HASH_TABLE_SIZE


def test_the_root_block_checksum_is_right():
    # The Amiga adds the block up and expects zero.
    root = _block(ad.blank_adf(), ad.ROOT_BLOCK)
    assert sum(_longs(root)) % 0x100000000 == 0


def test_the_bitmap_block_checksum_is_right():
    bitmap = _block(ad.blank_adf(), ad.BITMAP_BLOCK)
    assert sum(_longs(bitmap)) % 0x100000000 == 0


def test_the_root_block_points_at_a_valid_bitmap():
    root = _block(ad.blank_adf(), ad.ROOT_BLOCK)
    assert struct.unpack_from(">i", root, ad.BLOCK_SIZE - 200)[0] == -1
    assert struct.unpack_from(">I", root, ad.BLOCK_SIZE - 196)[0] == ad.BITMAP_BLOCK


def test_the_disk_carries_the_name_it_was_given():
    root = _block(ad.blank_adf("Legion Saves"), ad.ROOT_BLOCK)
    length = root[ad.BLOCK_SIZE - 80]
    assert root[ad.BLOCK_SIZE - 79:ad.BLOCK_SIZE - 79 + length] == b"Legion Saves"


def test_an_over_long_name_is_cut_rather_than_overflowing_the_field():
    root = _block(ad.blank_adf("x" * 80), ad.ROOT_BLOCK)
    assert root[ad.BLOCK_SIZE - 80] == 30


def _free(image: bytes, block_number: int) -> bool:
    """Read the bitmap the way the Amiga does, straight from the format.

    Deliberately written from the description of the format rather than from
    the code being tested: the first version of both agreed with each other and
    with nothing else, which is how a disk that destroyed itself on first write
    passed its own tests.

    The map is 32-bit words. Bit 0 - the least significant - of the first word
    is block 2. Words are big-endian, so that bit is in the word's last byte.
    """
    bitmap = _block(image, ad.BITMAP_BLOCK)
    index = block_number - 2
    word = struct.unpack_from(">I", bitmap, 4 + 4 * (index // 32))[0]
    return bool(word & (1 << (index % 32)))


def test_the_blocks_the_filesystem_itself_uses_are_marked_taken():
    # The bug this catches: with these free, the first file the game saved was
    # written straight over the root block. The save landed, the volume did
    # not survive it, and the next look at the disk found nothing on it.
    image = ad.blank_adf()
    assert not _free(image, ad.ROOT_BLOCK)
    assert not _free(image, ad.BITMAP_BLOCK)


def test_every_other_block_is_offered_to_the_game():
    # Otherwise the disk would report itself full, which is the same as having
    # no save disk at all.
    image = ad.blank_adf()
    assert _free(image, 2)
    assert _free(image, 879)
    assert _free(image, 882)
    assert _free(image, ad.BLOCKS - 1)


def test_exactly_two_blocks_are_taken_and_they_are_the_right_two():
    image = ad.blank_adf()
    taken = [n for n in range(2, ad.BLOCKS) if not _free(image, n)]
    assert taken == [ad.ROOT_BLOCK, ad.BITMAP_BLOCK]


def test_nothing_behind_the_end_of_the_disk_is_offered():
    # The map has room for more blocks than a floppy has. Leaving those bits
    # set invites the filesystem to allocate a block that is not there.
    image = ad.blank_adf()
    bitmap = _block(image, ad.BITMAP_BLOCK)
    for index in range(ad.BLOCKS - 2, ((ad.BLOCK_SIZE - 4) // 4) * 32):
        word = struct.unpack_from(">I", bitmap, 4 + 4 * (index // 32))[0]
        assert not word & (1 << (index % 32)), index


def test_the_name_can_be_read_back():
    assert ad.volume_name(ad.blank_adf("ARCHIWUM")) == "ARCHIWUM"


def test_renaming_changes_what_the_amiga_sees():
    # Games ask for a save disk by name and refuse anything else, so getting
    # this wrong means the game simply never finds the disk.
    renamed = ad.rename(ad.blank_adf("Saves"), "ARCHIWUM")
    assert ad.volume_name(renamed) == "ARCHIWUM"


def test_renaming_keeps_the_checksum_valid():
    renamed = ad.rename(ad.blank_adf("Saves"), "ARCHIWUM")
    root = _block(renamed, ad.ROOT_BLOCK)
    assert sum(_longs(root)) % 0x100000000 == 0


def test_renaming_leaves_everything_else_alone():
    # A player who already has saves on the disk keeps them when the name is
    # corrected - that is the whole reason for renaming rather than reformatting.
    original = ad.blank_adf("Saves")
    marked = bytearray(original)
    marked[100 * ad.BLOCK_SIZE:100 * ad.BLOCK_SIZE + 4] = b"DATA"
    renamed = ad.rename(bytes(marked), "ARCHIWUM")
    assert len(renamed) == len(original)
    assert _block(renamed, 100)[:4] == b"DATA"
    assert _block(renamed, ad.BITMAP_BLOCK) == _block(original, ad.BITMAP_BLOCK)


def test_a_shorter_name_does_not_leave_the_old_one_behind():
    renamed = ad.rename(ad.blank_adf("A Very Long Disk Name"), "AB")
    assert ad.volume_name(renamed) == "AB"


def test_a_fresh_disk_counts_as_untouched():
    assert ad.untouched(ad.blank_adf())
    assert ad.untouched(ad.blank_adf("ARCHIWUM"))


def test_a_renamed_but_unused_disk_is_still_untouched():
    # Otherwise correcting the name a second time would silently do nothing.
    assert ad.untouched(ad.rename(ad.blank_adf("Saves"), "ARCHIWUM"))


def test_a_disk_the_game_has_written_to_is_not_untouched():
    # This is what stops GD renaming a disk out from under its game. Dungeon
    # Master calls its own disk "DungeonSave" and stops recognising it the
    # moment the name changes.
    used = bytearray(ad.blank_adf("DungeonSave"))
    used[100 * ad.BLOCK_SIZE:100 * ad.BLOCK_SIZE + 4] = b"SAVE"
    assert not ad.untouched(bytes(used))


def test_nothing_but_the_three_special_blocks_is_written():
    # The rest of a fresh disk is zeroes; anything else would be data the
    # player never put there.
    image = ad.blank_adf()
    for n in (2, 3, 500, 879, 882, ad.BLOCKS - 1):
        assert _block(image, n) == b"\x00" * ad.BLOCK_SIZE
