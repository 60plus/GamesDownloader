"""Why a ROM or a URL transfer stopped, in the reader's language.

The tray learned to say this for torrents on 2026-09-08, and the owner gave the
rule that made it worth finishing: "nie rozumiem czemu zostawiasz
nieprztlumaczone pozniej sie zapomina o takich pojedynczych". Four sections of
that same tray still answer in English - ROM sources, URL uploads, CHD
conversion and GOG - and this file is the first two.

>>> THE COUNT WAS WRONG AND SMALLER THAN RECORDED. The note in memory said "77
messages left". That number came from counting strings in the source, including
ones that never reach a screen. Measured from the SCREEN backwards instead - the
five places the tray actually draws an error - there are 22 distinct reasons in
the four subsystems, of which ROM has 5 and URL has 2.

>>> ROM WAS ALREADY HALF DONE AND NOBODY HAD NOTICED. `_safe_error` sorts every
failure into five outcomes already, because it was written to keep the source
URL and the auth header out of the message. It just says them in English instead
of naming them. So this is not new classification, it is letting the existing
classification travel.

SAME SHAPE AS THE TORRENTS, deliberately: the server names the reason and hands
over the one figure that reason is read with, and the screen writes the
sentence. The English text STAYS on the row - it is the fallback for a reason
nobody has written a sentence for yet, and it carries the messages that are not
ours to translate.
"""

from __future__ import annotations

import io
import json
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
FRONTEND = BACKEND.parent / "frontend"


def _src(rel: str) -> str:
    return io.open(BACKEND / rel, encoding="utf-8").read()


# ── ROM: the classification that already existed, now with a name ────────────

@pytest.mark.parametrize("kind,code,detail", [
    ("http", "rom_http", "503"),
    ("unreachable", "rom_unreachable", None),
    ("timeout", "rom_timeout", None),
    ("other", "rom_failed", None),
])
def test_a_rom_failure_is_named_not_only_described(kind, code, detail):
    """Asked per OUTCOME with the figure that outcome is read with. A status
    code is the whole difference between "the archive is down" and "that file is
    gone", and a sentence cannot be translated without pulling it back out of
    the text."""
    import httpx
    from handler.roms import rom_source_handler as R

    if kind == "http":
        request = httpx.Request("GET", "https://example.invalid/x.zip")
        response = httpx.Response(503, request=request)
        exc = httpx.HTTPStatusError("boom", request=request, response=response)
    elif kind == "unreachable":
        exc = httpx.ConnectError("boom")
    elif kind == "timeout":
        exc = httpx.ReadTimeout("boom")
    else:
        exc = KeyError("boom")

    said, got_code, got_detail = R._safe_error(exc)

    assert isinstance(said, str) and said, (
        "zdanie awaryjne zniknelo - czytelnik, ktory nie zna kodu, zostanie z niczym"
    )
    assert got_code == code, f"{kind}: kod {got_code!r} zamiast {code!r}"
    assert (got_detail or None) == detail, f"{kind}: liczba {got_detail!r} zamiast {detail!r}"


def test_our_own_message_still_comes_through_word_for_word():
    """THE LEGAL CASE. A ValueError here is a sentence somebody wrote on purpose
    - "this file is bigger than the account's remaining quota" and its like. A
    classification that swallowed those into "Download failed" would be a loss,
    not an improvement."""
    from handler.roms import rom_source_handler as R

    said, code, _detail = R._safe_error(ValueError("no room left on this shelf"))
    assert said == "no room left on this shelf"
    assert not code, (
        "nasze wlasne zdanie dostalo kod, wiec ekran zastapi je ogolnikiem"
    )


def test_the_reason_travels_with_the_job_and_the_event():
    """The tray reads the job list on load and the event afterwards. A reason
    that rides only one of them is missing exactly half the time - which is how
    the torrent name vanished a second after every refresh."""
    body = _src("handler/roms/rom_source_handler.py")

    at = body.index("def as_dict(")
    row = body[at:body.index("\n\n", at)]
    for field in ("error_code", "error_detail"):
        assert field in row, f"lista zadan nie niesie `{field}`"

    at = body.index('"romsource:download_error"')
    payload = body[at:body.index("})", at)]
    for field in ("error_code", "error_detail"):
        assert field in payload, f"zdarzenie o bledzie nie niesie `{field}`"


# ── URL: two reasons, and one of them is a name from the scanner ─────────────

def test_a_url_upload_names_its_two_reasons():
    """Asked about what the EVENT carries, not about the first `except
    _VirusFound` in the file - the first version did that and landed on the
    direct-upload route, a different site that answers 422 and already has its
    own code. Anchoring on a keyword instead of on the thing under test, for the
    third time in one sitting.
    """
    import re

    body = _src("endpoints/library/upload_router.py")
    # A fixed window rather than "up to the closing `})`": the antivirus branch
    # interpolates `{v.threat}` inside an f-string, so the first `})` after the
    # match sits INSIDE the message and the slice ended before the code line.
    blocks = [body[m.start():m.start() + 900]
              for m in re.finditer(r'"upload:url_error"', body)]
    assert len(blocks) >= 2, f"{len(blocks)} zdarzen bledu URL zamiast dwoch"
    joined = "\n".join(blocks)

    assert '"url_virus"' in joined, (
        "odmowa antywirusa nie ma nazwy, wiec tacka nie przetlumaczy jej inaczej "
        "niz przez podmiane calego zdania"
    )
    assert "v.threat" in joined, "nazwa sygnatury przepadla"
    assert '"url_failed"' in joined
    assert "error_detail" in joined, (
        "ogolna awaria nie podaje odnosnika, wiec zwykle konto nie ma czym sie "
        "poslugiwac, zglaszajac to administratorowi"
    )


def test_the_reference_from_a_swallowed_exception_is_reachable():
    """`safe_note` composes a sentence AND hides the reference inside it. The
    screen needs the reference on its own, or it cannot write that sentence in
    another language without parsing English back out of it."""
    from utils.errors import safe_note_ref

    said, ref = safe_note_ref(OSError("/srv/secret/path"), what="Download failed")
    assert ref and ref in said
    assert "/srv/secret/path" not in said


# ── The screen ───────────────────────────────────────────────────────────────

def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        pytest.skip("frontend tree not present")
    return io.open(path, encoding="utf-8").read()


TRAY = FRONTEND / "src" / "components" / "gog" / "DownloadManager.vue"


@pytest.mark.parametrize("section,row", [("rom", "r"), ("url", "u")])
def test_the_tray_composes_these_rather_than_printing_them(section, row):
    """Both sections print the server's sentence straight into the row today.

    Asked about the CALL, not about whether the word `describeTransferError`
    appears anywhere in the file - it already does, for torrents, so that
    version of this question was green before a line was written.
    """
    body = _read(TRAY)
    assert f"truncate({row}.error, 40)" not in body, (
        f"sekcja {section} nadal drukuje angielskie zdanie serwera wprost"
    )
    assert f"whyFailed({row})" in body, (
        f"sekcja {section} nie sklada zdania z kodu powodu"
    )


def test_the_live_event_does_not_wipe_the_reason_it_just_drew():
    """The trap this file's neighbours document twice over: the branch rebuilds
    the row, so a field the event does not carry is erased."""
    body = _read(TRAY)
    for fn in ("function handleRomSource", "function handleUrlUpload"):
        at = body.index(fn)
        handler = body[at:body.index("\nfunction ", at + 10)]
        assert "error_code" in handler, (
            f"{fn} przebudowuje wiersz bez kodu powodu"
        )


def test_the_composer_reads_either_field_name():
    """Torrents call it `error_msg`, these three call it `error`. One function
    has to serve both or the rule ends up written twice and they drift."""
    lib = FRONTEND / "src" / "lib" / "transferError.ts"
    body = _read(lib)
    at = body.index("export function describeTransferError")
    fn = body[at:body.index("\n}", at)]
    assert "error" in fn and "error_msg" in fn


# ── In every language ────────────────────────────────────────────────────────

CODES = ["rom_http", "rom_unreachable", "rom_timeout", "rom_failed",
         "url_virus", "url_failed"]


@pytest.mark.parametrize("code", CODES)
def test_every_language_has_a_sentence_for_it(code):
    en = FRONTEND / "src" / "i18n" / "en.json"
    if not en.is_file():
        pytest.skip("frontend tree not present")
    langs = sorted((FRONTEND / "public" / "i18n").glob("*.json"))
    assert len(langs) == 7
    for path in [en, *langs]:
        d = json.load(io.open(path, encoding="utf-8"))
        assert f"download.err_{code}" in d, f"{path.name}: brak {code}"


def test_a_reason_nobody_has_written_a_sentence_for_still_says_something():
    """THE FALLBACK IS THE POINT, and it is what makes this safe to do a piece at
    a time: an unclassified failure is no worse off than before, and never
    blank. Asked about the BRANCH and what it returns, because a previous
    version of this asked whether the words `row.error_msg` appear in the file
    and a mutation deleting the whole default branch walked straight through."""
    lib = FRONTEND / "src" / "lib" / "transferError.ts"
    body = _read(lib)
    at = body.index("export function describeTransferError")
    fn = body[at:body.index("\n}", at)]
    tail = fn[fn.index("default:"):]
    assert "return" in tail and "raw" in tail, (
        "galaz awaryjna nie oddaje tekstu serwera, wiec nieznany powod bedzie pusty"
    )
