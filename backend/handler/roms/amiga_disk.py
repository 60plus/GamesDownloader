"""A blank, formatted Amiga floppy.

The Amiga has no battery-backed memory. A game that saves does it to a disk -
usually a second one the player is told to insert - so GD's battery-save slot
holds a disk image rather than a chunk of SRAM. To start that off, the machine
needs a floppy it can already write to: handing it an empty file gets "not a
DOS disk" and a request to format, and there is no Workbench in the browser to
format it with.

So GD makes the disk itself. The layout is the ordinary AmigaDOS one for a
double-density floppy, and nothing here is Amiga-specific beyond that: 1760
blocks of 512 bytes, a boot block that says which filesystem it is, a root
block holding the name and an empty hash table, and a bitmap saying every other
block is free.

References: the AmigaDOS filesystem is documented in the Amiga Developer docs
and, more usefully, in the ADF format description that every Amiga tool follows.
"""
from __future__ import annotations

import struct

BLOCK_SIZE = 512
BLOCKS = 1760                       # double density: 2 sides * 80 tracks * 11
ADF_SIZE = BLOCK_SIZE * BLOCKS      # 901120, the size every .adf tool expects
ROOT_BLOCK = 880                    # the middle of the disk, by convention
BITMAP_BLOCK = ROOT_BLOCK + 1

T_HEADER = 2                        # block type: a header
ST_ROOT = 1                         # secondary type: the root directory
HASH_TABLE_SIZE = (BLOCK_SIZE // 4) - 56   # 72 entries on a floppy


def _checksum(block: bytearray, at: int) -> None:
    """Write the checksum that makes the block's longwords sum to zero.

    Every AmigaDOS block carries one, and a wrong one is indistinguishable from
    a corrupt disk as far as the machine is concerned.
    """
    struct.pack_into(">I", block, at, 0)
    total = 0
    for offset in range(0, BLOCK_SIZE, 4):
        total = (total + struct.unpack_from(">I", block, offset)[0]) & 0xFFFFFFFF
    struct.pack_into(">I", block, at, (-total) & 0xFFFFFFFF)


def _boot_block(ffs: bool) -> bytes:
    """The first two blocks. Not bootable - this disk only holds saves.

    A save disk is never booted from, and leaving the checksum zero is what
    marks it as non-bootable, which is exactly right here.
    """
    block = bytearray(BLOCK_SIZE * 2)
    block[0:3] = b"DOS"
    block[3] = 1 if ffs else 0
    return bytes(block)


def _root_block(name: str) -> bytes:
    block = bytearray(BLOCK_SIZE)
    struct.pack_into(">I", block, 0, T_HEADER)
    struct.pack_into(">I", block, 12, HASH_TABLE_SIZE)
    # The hash table is left empty: a fresh disk has no files on it.

    # The bitmap is valid and lives in exactly one block on a floppy.
    struct.pack_into(">i", block, BLOCK_SIZE - 200, -1)
    struct.pack_into(">I", block, BLOCK_SIZE - 196, BITMAP_BLOCK)

    # The name is a BCPL string: a length byte, then the characters. Anything
    # longer than 30 would not fit the field, and the Amiga would not show it.
    raw = name.encode("ascii", "replace")[:30]
    block[BLOCK_SIZE - 80] = len(raw)
    block[BLOCK_SIZE - 79:BLOCK_SIZE - 79 + len(raw)] = raw

    # Dates are left at zero. The Amiga reads that as 1978-01-01, which is
    # honest for a disk that has never been written to, and no game cares.
    struct.pack_into(">I", block, BLOCK_SIZE - 4, ST_ROOT)
    _checksum(block, 20)
    return bytes(block)


# The bitmap is an array of 32-bit words, and the bit for a block is found in
# the word, not in the byte: bit 0 - the least significant bit - of the first
# word stands for block 2, bit 1 for block 3, and so on into the next word at
# bit 32. Because the words are stored big-endian, that bit lives in the LAST
# byte of its word, not the first. Walking the map a byte at a time instead
# names the right block only by accident: it advertised the root block as free,
# the first file the Amiga wrote landed on top of it, and the disk stopped being
# a disk the moment it was written to.
_BITMAP_WORDS = (BLOCK_SIZE - 4) // 4


def _bitmap_block() -> bytes:
    """Which blocks are free. A set bit means free, and bit 0 is block 2.

    Blocks 0 and 1 are the boot block and are not covered by the map at all.
    The root and bitmap blocks are in use, so their two bits are cleared, and
    so are the bits past the end of the disk - there is no block behind them to
    allocate, and that is how a real Amiga leaves them.
    """
    block = bytearray(BLOCK_SIZE)
    covered = BLOCKS - 2
    assert covered <= _BITMAP_WORDS * 32
    words = [0xFFFFFFFF] * _BITMAP_WORDS
    for used in (ROOT_BLOCK, BITMAP_BLOCK):
        index = used - 2
        words[index // 32] &= ~(1 << (index % 32)) & 0xFFFFFFFF
    for index in range(covered, _BITMAP_WORDS * 32):
        words[index // 32] &= ~(1 << (index % 32)) & 0xFFFFFFFF
    for n, word in enumerate(words):
        struct.pack_into(">I", block, 4 + 4 * n, word)
    _checksum(block, 0)
    return bytes(block)


def untouched(image: bytes) -> bool:
    """True when nothing has ever been written to this disk.

    Which decides whether GD may rename it. A disk the game has written to
    carries the name the game chose - Dungeon Master calls its own disk
    "DungeonSave" - and renaming that is how you make a game stop recognising
    its own saves. A disk still exactly as GD formatted it belongs to nobody
    yet, so correcting the name is safe.
    """
    return image == blank_adf(volume_name(image), ffs=bool(image[3:4] == b"\x01"))


def volume_name(image: bytes) -> str:
    """What the Amiga calls this disk."""
    if len(image) < ADF_SIZE:
        return ""
    at = ROOT_BLOCK * BLOCK_SIZE + BLOCK_SIZE - 80
    length = image[at]
    if length > 30:
        return ""
    return image[at + 1:at + 1 + length].decode("ascii", "replace")


def rename(image: bytes, name: str) -> bytes:
    """The same disk under a different name, contents untouched.

    Games are particular about this: a title that saves to a disk usually asks
    for one with a specific name, and refuses anything else. Renaming rather
    than reformatting means a player who already has saves keeps them when the
    name is corrected.
    """
    if len(image) < ADF_SIZE:
        return image
    out = bytearray(image)
    start = ROOT_BLOCK * BLOCK_SIZE
    root = bytearray(out[start:start + BLOCK_SIZE])
    raw = name.encode("ascii", "replace")[:30]
    root[BLOCK_SIZE - 80:BLOCK_SIZE - 80 + 31] = bytes([len(raw)]) + raw + b"\x00" * (30 - len(raw))
    _checksum(root, 20)
    out[start:start + BLOCK_SIZE] = root
    return bytes(out)


def blank_adf(name: str = "Saves", ffs: bool = False) -> bytes:
    """An empty, formatted double-density floppy, ready to be written to.

    The old filesystem by default, and deliberately. FFS arrived with Kickstart
    2.0 in 1990; a game older than that cannot read an FFS disk and says so -
    Dungeon Master answers "that disk is unreadable" and offers to format it.
    OFS is understood by every Amiga ever made, and a save disk holds a few
    kilobytes, so the space FFS would save is worth nothing here.
    """
    image = bytearray(ADF_SIZE)
    boot = _boot_block(ffs)
    image[0:len(boot)] = boot
    root = _root_block(name)
    image[ROOT_BLOCK * BLOCK_SIZE:ROOT_BLOCK * BLOCK_SIZE + BLOCK_SIZE] = root
    bitmap = _bitmap_block()
    image[BITMAP_BLOCK * BLOCK_SIZE:BITMAP_BLOCK * BLOCK_SIZE + BLOCK_SIZE] = bitmap
    return bytes(image)
