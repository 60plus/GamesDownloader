"""A memory card in the browser belongs to an account, not to the browser.

EmulatorJS mounts its save filesystem with IDBFS at the fixed path
/data/saves. That mount is per browser: not per game, and not per account.
Signing in as somebody else on the same machine therefore left the previous
person's cards in the emulator, the next game booted on them, and the auto
sync uploaded them to the new account. One user's progress ended up filed
under another user's name, which is how this was found: a test on the `gdtest`
account came up holding the admin's MediEvil card and sent it to the server.

There is no test runner for player.html, so this reads it. That is worth doing
anyway for a file whose failure mode is silence: every one of these lines was
missing entirely rather than being wrong.
"""
from __future__ import annotations

import pathlib

import pytest

PLAYER = (pathlib.Path(__file__).resolve().parent.parent.parent
          / "frontend" / "public" / "player.html")


@pytest.fixture(scope="module")
def zrodlo() -> str:
    if not PLAYER.is_file():
        pytest.skip("player.html nie jest kopiowany do obrazu")
    return PLAYER.read_text(encoding="utf-8")


def test_odtwarzacz_wie_kto_jest_zalogowany(zrodlo):
    """It knew a token and nothing else, so it could not tell one player from
    another. The subject claim is enough to name the owner of the cards."""
    assert "const WHO" in zrodlo, "brak tozsamosci konta w odtwarzaczu"
    assert "TOKEN.split('.')[1]" in zrodlo, "WHO nie pochodzi z tokenu"


def test_karty_sa_czyszczone_przy_zmianie_konta(zrodlo):
    assert "forgetOtherUsersCards" in zrodlo


def test_czyszczenie_biegnie_PRZED_startem_emulatora(zrodlo):
    """Once the game is running the core has already read the file, so deleting
    it then changes nothing about what is being played."""
    czysci = zrodlo.index("await forgetOtherUsersCards()")
    laduje = zrodlo.index("_loadEJSFrom(LOCAL_EJS)")
    assert czysci < laduje, "czyszczenie po starcie emulatora nie ma zadnego skutku"


def test_czysci_oba_montowania(zrodlo):
    """EmulatorJS and vAmigaWeb each keep a writable filesystem in this browser."""
    assert "'/data/saves'" in zrodlo, "brak montowania EmulatorJS"
    assert "'/exported_hd'" in zrodlo, "brak zapisywalnego dysku vAmigaWeb"


def test_nie_kasuje_zasobow_emulatora(zrodlo):
    """ROMs, cores and BIOS files are not personal and cost a lot to fetch
    again, so the sweep must not take them with it."""
    import re
    blok = zrodlo[zrodlo.index("async function forgetOtherUsersCards"):]
    blok = blok[:blok.index("\n}")]
    for baza in ("EmulatorJS-roms", "EmulatorJS-core", "EmulatorJS-bios"):
        assert baza not in blok, f"czyszczenie zabiera {baza}"
    # Anything enumerated is taken only when it looks like a filesystem mount.
    assert re.search(r"charAt\(0\)\s*===\s*'/'", blok), (
        "wyliczanie baz nie ogranicza sie do sciezek montowania")


def test_brak_czytelnego_konta_niczego_nie_kasuje(zrodlo):
    """A token that merely failed to parse is not evidence of a different
    person, and acting on it would throw away a legitimate player's cards."""
    assert "WHO === 'anon'" in zrodlo


def test_wysylka_odmawia_gdy_karta_nalezy_do_kogos_innego(zrodlo):
    """Belt and braces: if the clearing ever fails, the one thing that must not
    happen anyway is filing somebody else's card under this account."""
    blok = zrodlo[zrodlo.index("async function uploadSave"):]
    blok = blok[:blok.index("\n}")]
    assert "CARD_OWNER_KEY" in blok
    assert "owner !== WHO" in blok


def test_punkt_synchronizacji_jest_per_konto(zrodlo):
    """Two accounts on one browser must not share the record of which version
    of a card they are holding."""
    assert "'gd_card_sync_' + WHO + '_' + ROM_ID" in zrodlo


def test_nic_dotyczace_zapisow_nie_zalezy_od_https(zrodlo):
    """`crypto.subtle` only exists in a secure context, and GD is routinely
    reached over plain http on a LAN address.

    The first version of the card fingerprint used it, so on that address it
    returned null every single time: no sync point was ever written, every
    launch decided the local card held unsent work, and a second browser could
    load a save, play on, and never update the server. The user found it in an
    afternoon; nothing in the code said a word.
    """
    for nazwa in ("fingerprint", "rememberCardSync", "_fullHash", "uploadSave",
                  "takeServerCardIfItIsAhead", "_autoSyncTick"):
        poczatek = zrodlo.index("function " + nazwa)
        blok = zrodlo[poczatek:]
        blok = blok[:blok.index("\n}")]
        assert "crypto.subtle" not in blok, (
            f"{nazwa} zalezy od crypto.subtle, wiec nie dziala po zwyklym http")


def test_decyzje_o_zapisach_licza_kazdy_bajt(zrodlo):
    """`_quickHash` reads one byte in every step. On a 128 KB memory card that
    is one in 128, so a save written entirely between two samples reads as no
    change: the auto sync stays quiet and the next launch decides the card is
    safe to replace with the server's copy."""
    for nazwa in ("fingerprint", "_autoSyncTick"):
        poczatek = zrodlo.index("function " + nazwa)
        blok = zrodlo[poczatek:]
        blok = blok[:blok.index("\n}")]
        assert "_quickHash" not in blok, f"{nazwa} decyduje o zapisie na probce bajtow"
        assert "_fullHash" in blok, f"{nazwa} nie liczy pelnego skrotu"
