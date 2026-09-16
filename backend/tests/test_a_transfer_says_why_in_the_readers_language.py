"""Every reason a torrent row can carry is named, so the screen can translate it.

Reported by the owner, reading his own tray: "ale czesc jest po poilsku czesc po
angliesku - Blad Refused: this torrent is 62.94 GB and only 2.9...". The status
label beside it is translated; the sentence is not, because the server composed
it in English.

That is true of this whole application - 448 refusals in the backend, all
English - so this is not a regression. What made it visible is the tray putting
a translated word directly against an untranslated sentence. The owner's rule,
and it is the better one: "nie rozumiem czemu zostawiasz nieprztlumaczone
pozniej sie zapomina o takich pojedynczych".

THE SHAPE IS THE ONE THAT ALREADY WORKS HERE, from the refused-upload fix a day
earlier: the server sends a REASON CODE and the numbers, the screen writes the
sentence in its own language, and anything the screen does not recognise is
shown exactly as the server wrote it. That fallback is what makes this safe to
do a piece at a time - an unclassified message is no worse off than today, and
never blank.

WHY THE CODE IS STORED RATHER THAN SENT WITH THE EVENT. The tray reads the ROW,
not the socket: a transfer runs for hours and the page that started it is long
gone. The refusal event carries a reason already, and it is thrown away on
arrival - which is right, because after a reload there would be nothing left.
So the reason lives on the row, beside the sentence, and the sentence stays as
the fallback for every reader that does not know the code yet.
"""

from __future__ import annotations

import io
import json
import pathlib

import pytest

from handler.torrent import seed_monitor as M

BACKEND = pathlib.Path(__file__).resolve().parent.parent


def test_the_row_can_carry_a_reason_at_all():
    from models.torrent_download import TorrentDownload

    assert "error_code" in TorrentDownload.__table__.columns, (
        "wiersz nie ma gdzie zapisac powodu, wiec po odswiezeniu strony ekran "
        "moze pokazac tylko angielskie zdanie"
    )


def test_the_column_arrives_on_an_existing_install():
    """No backfill, deliberately: a row written before this column keeps its
    sentence, and the screen falls back to showing it. Guessing a code for it
    would be inventing a reason nobody recorded."""
    source = io.open(BACKEND / "main.py", encoding="utf-8").read()
    assert '"torrent_downloads", "error_code"' in source


# ── Every reason has a name ──────────────────────────────────────────────────

#: What the monitor can write, and what the screen has to be able to say.
REASONS = [
    "quota_refused",
    "quota_stopped",
    "lost",
    "daemon",
    "no_game",
    "no_folder",
    "no_files",
    "threat",
    "move_failed",
]


@pytest.mark.parametrize("reason", REASONS)
def test_each_reason_is_a_named_constant(reason):
    """Spelled once, in one place. A code written as a bare string at each site
    is how the writer and the reader come to disagree about one of them."""
    assert reason in M.REASONS, (
        f"powod {reason!r} nie jest nazwany, wiec ekran nie ma czego rozpoznac"
    )


def test_nothing_writes_a_reason_that_is_not_on_the_list():
    """The other direction, and the one that rots quietly: a site inventing its
    own code would leave the screen showing English for a reason that looks
    handled."""
    source = io.open(BACKEND / "handler" / "torrent" / "seed_monitor.py",
                     encoding="utf-8").read()
    import re

    uzyte = set(re.findall(r'reason\("([a-z_]+)"\)', source))
    nieznane = uzyte - set(M.REASONS)
    assert not nieznane, f"zapisywane sa powody spoza listy: {sorted(nieznane)}"


# ── The screen can say all of them ───────────────────────────────────────────

I18N = BACKEND.parent / "frontend" / "src" / "i18n" / "en.json"
LANGS = sorted((BACKEND.parent / "frontend" / "public" / "i18n").glob("*.json")) \
    if (BACKEND.parent / "frontend" / "public" / "i18n").is_dir() else []


def _keys(path: pathlib.Path) -> dict:
    return json.load(io.open(path, encoding="utf-8"))


@pytest.mark.parametrize("reason", REASONS)
def test_english_has_a_sentence_for_each_reason(reason):
    if not I18N.is_file():
        pytest.skip("frontend tree not present")
    assert f"download.err_{reason}" in _keys(I18N), (
        f"brak zdania dla powodu {reason} - ekran pokaze nazwe klucza"
    )


def test_every_language_has_them_too():
    """The parity gate in CI says this for all 2602 keys. Said here as well
    because these are the ones this change adds, and a skip in CI would hide
    them."""
    if not I18N.is_file() or not LANGS:
        pytest.skip("frontend tree not present")
    wanted = {f"download.err_{r}" for r in REASONS}
    for path in LANGS:
        brak = wanted - set(_keys(path))
        assert not brak, f"{path.name}: brakuje {sorted(brak)}"


def test_the_two_that_carry_numbers_say_so_in_every_language():
    """A sentence that drops its parameters reads as a refusal with no figures,
    which is the state this replaced."""
    if not I18N.is_file() or not LANGS:
        pytest.skip("frontend tree not present")
    for path in [I18N, *LANGS]:
        d = _keys(path)
        for key in ("download.err_quota_refused", "download.err_quota_stopped"):
            zdanie = d.get(key, "")
            assert "{size}" in zdanie and "{room}" in zdanie, (
                f"{path.name} / {key}: zdanie gubi liczby -> {zdanie!r}"
            )
        assert "{threat}" in d.get("download.err_threat", ""), (
            f"{path.name}: komunikat o zagrozeniu gubi jego nazwe"
        )


# ── And the fallback, which is what makes this safe ──────────────────────────

def test_the_screen_falls_back_to_what_the_server_wrote():
    """The branch that makes this safe to do a piece at a time.

    Asked as "does `row.error_msg` appear in the file" first, and a mutation
    walked straight through it: deleting the `default:` branch entirely left
    that text in place, because two other branches mention it. Asked now about
    the BRANCH - it has to exist, and it has to hand back the server's own
    words. The fourth time this round that a test of mine matched letters
    instead of an instruction.
    """
    tray = (BACKEND.parent / "frontend" / "src" / "lib" / "transferError.ts")
    if not tray.is_file():
        pytest.skip("frontend tree not present")
    body = io.open(tray, encoding="utf-8").read()

    at = body.find("default:")
    assert at > 0, (
        "brak galezi domyslnej: powod, ktorego ekran nie zna, zniknie zamiast "
        "pokazac sie po angielsku"
    )
    ogon = body[at:at + 400]
    assert "return raw" in ogon, (
        f"galaz domyslna nie oddaje tekstu serwera: {ogon[:120]!r}"
    )
    # And the same for a row that has no code at all - every transfer written
    # before this column existed.
    assert "if (!code) return raw;" in body, (
        "wiersz bez kodu (kazdy sprzed tej kolumny) nie ma czego pokazac"
    )
