"""Why a CHD conversion or a GOG download stopped, in the reader's language.

The last two of the four sections the transfer tray draws. ROM and URL were done
beside this file; torrents on 2026-09-08.

>>> CHD IS GROUPED, AND THE OWNER CHOSE THAT. `ChdError` is raised in seventeen
places. Several are internal invariants nobody meets unless the install is
broken ("that file is not in this directory"), and giving each its own sentence
in eight languages would have been 136 keys, most of them for text no reader
ever sees. They are grouped into six reasons somebody can act on, and where
chdman or the file system said something specific, that sentence is QUOTED after
the translated frame - the same shape the Transmission daemon's own wording
already travels in. Nothing is lost; it is said in fewer, bigger sentences.

>>> GOG NEEDS COLUMNS, THE OTHER THREE DO NOT. ROM, URL and CHD jobs live in
memory and die with the process, so a field on the dataclass is enough. A GOG
download is a row in `download_jobs` that outlives restarts, so the reason has to
be stored - the same two columns the torrents got, with the same deliberate
absence of a backfill: a row written before today keeps its English sentence and
the screen falls back to showing it, which is exactly what it did yesterday.
Guessing a code for those would be inventing a reason nobody recorded.
"""

from __future__ import annotations

import io
import json
import pathlib
import re

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
FRONTEND = BACKEND.parent / "frontend"

CHD_CODES = {"chd_archive", "chd_source", "chd_exists", "chd_converter",
             "chd_move", "chd_failed"}
GOG_CODES = {"gog_checksum", "gog_incomplete", "gog_virus", "gog_failed"}


def _src(rel: str) -> str:
    return io.open(BACKEND / rel, encoding="utf-8").read()


# ── CHD ──────────────────────────────────────────────────────────────────────

def test_every_conversion_failure_carries_a_name():
    """Asked per CALL, through the syntax tree.

    The first version scanned 260 characters after each `raise ChdError(` and
    looked for the word `code=`. A mutation that stripped the code off one raise
    walked straight through it: the window reached into the NEXT raise, found
    its `code=`, and called the file clean. Seventeen sites and one of them
    forgetting is exactly the gap that shows up as an untranslated line months
    later, so this reads the call's own keywords instead of the text around it.
    """
    import ast

    tree = ast.parse(_src("handler/roms/chd_convert.py"))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call)
             and getattr(n.exc.func, "id", None) == "ChdError"]
    assert len(calls) >= 15, f"{len(calls)} miejsc - ksztalt pliku sie zmienil"

    missing = []
    for n in calls:
        first = ast.unparse(n.exc.args[0]) if n.exc.args else ""
        if "cancelled" in first:
            continue           # cancelling is not a failure and shows nothing
        if not any(k.arg == "code" for k in n.exc.keywords):
            missing.append(f"linia {n.lineno}: {first[:60]}")
    assert not missing, (
        "%d miejsc rzuca ChdError bez nazwy powodu:\n  %s"
        % (len(missing), "\n  ".join(missing))
    )


def test_no_conversion_reason_is_invented():
    """A typo in a code is silent: the screen falls through to the English
    sentence and nobody notices for months."""
    body = _src("handler/roms/chd_convert.py")
    used = set(re.findall(r'code="([a-z_]+)"', body))
    assert used, "zadnego kodu nie znalazlem - test bada co innego"
    assert used <= CHD_CODES, f"nieznane kody: {sorted(used - CHD_CODES)}"


def test_the_conversion_reason_travels_to_the_screen():
    body = _src("handler/roms/chd_jobs.py")
    at = body.index("def to_dict(") if "def to_dict(" in body else body.index("def as_dict(")
    row = body[at:body.index("\n\n", at)]
    for field in ("error_code", "error_detail"):
        assert field in row, f"zadanie konwersji nie niesie `{field}`"

    # And the branch that catches everything else still names itself, or a
    # failure nobody classified would be the one case with no code at all.
    at = body.index("except Exception as err:")
    # A window wide enough to hold the comment that explains it. The first
    # version used 700 characters and stopped one line short of the code.
    branch = body[at:at + 1200]
    assert "chd_failed" in branch, (
        "ogolna awaria konwersji nie ma nazwy, wiec zostanie po angielsku"
    )


# ── GOG ──────────────────────────────────────────────────────────────────────

def test_a_gog_download_can_remember_why_it_stopped():
    """A row that outlives the process needs columns, not attributes."""
    model = _src("models/download_job.py")
    for field in ("error_code", "error_detail"):
        assert field in model, f"model download_job nie ma `{field}`"

    boot = _src("main.py")
    # Matched loosely: the migration table is aligned in columns, so the exact
    # run of spaces between the table name and the column is a formatting
    # choice, not the thing under test.
    m = re.search(r'\("download_jobs",\s*"error_code"', boot)
    assert m, "migracja nie dodaje kolumny error_code do download_jobs"
    block = boot[m.start():m.start() + 260]
    assert "error_detail" in block, "migracja dodaje tylko jedna z dwoch kolumn"


def test_the_gog_reasons_are_named():
    body = _src("handler/gog/gog_download_handler.py")
    used = set(re.findall(r'error_code="([a-z_]+)"', body))
    assert used == GOG_CODES, (
        f"nazwane powody GOG: {sorted(used)}, oczekiwane: {sorted(GOG_CODES)}"
    )


def test_the_gog_listing_hands_them_over():
    body = _src("endpoints/gog/download_router.py")
    at = body.index('"error_msg":')
    block = body[at:at + 300]
    for field in ("error_code", "error_detail"):
        assert field in block, f"lista pobran GOG nie niesie `{field}`"


def test_an_older_row_keeps_its_sentence():
    """THE LEGAL CASE, and the reason there is no backfill. A download that
    failed last week has no code, and must still say what it said - the fallback
    branch carries it. A migration that guessed codes would be inventing reasons
    nobody recorded."""
    boot = _src("main.py")
    m = re.search(r'\("download_jobs",\s*"error_code"', boot)
    assert m, "migracja nie dodaje kolumny error_code do download_jobs"
    context = boot[max(0, m.start() - 700):m.start()]
    assert "backfill" in context.lower() or "uzupelnien" in context.lower(), (
        "brak notatki o tym, ze wstecz nie uzupelniamy - nastepna osoba to zrobi"
    )
    assert "UPDATE download_jobs" not in boot, (
        "migracja zgaduje powody dla wierszy, ktore ich nie maja"
    )


# ── The screen ───────────────────────────────────────────────────────────────

def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        pytest.skip("frontend tree not present")
    return io.open(path, encoding="utf-8").read()


TRAY = FRONTEND / "src" / "components" / "gog" / "DownloadManager.vue"


@pytest.mark.parametrize("section,raw", [
    ("chd", "{{ cv.error }}"),
    ("gog", "truncate(job.error_msg"),
])
def test_the_tray_composes_these_rather_than_printing_them(section, raw):
    body = _read(TRAY)
    assert raw not in body, (
        f"sekcja {section} nadal drukuje angielskie zdanie serwera wprost"
    )


def test_the_composer_knows_all_ten_reasons():
    lib = FRONTEND / "src" / "lib" / "transferError.ts"
    body = _read(lib)
    at = body.index("export function describeTransferError")
    fn = body[at:body.index("\n}", at)]
    for code in sorted(CHD_CODES | GOG_CODES):
        assert f"'{code}'" in fn, f"skladacz zdan nie zna `{code}`"


# ── In every language ────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", sorted(CHD_CODES | GOG_CODES))
def test_every_language_has_a_sentence_for_it(code):
    en = FRONTEND / "src" / "i18n" / "en.json"
    if not en.is_file():
        pytest.skip("frontend tree not present")
    langs = sorted((FRONTEND / "public" / "i18n").glob("*.json"))
    assert len(langs) == 7
    for path in [en, *langs]:
        d = json.load(io.open(path, encoding="utf-8"))
        assert f"download.err_{code}" in d, f"{path.name}: brak {code}"


def test_the_quoted_half_is_actually_quoted():
    """The grouping only holds together because the specific wording survives:
    chdman's own diagnosis is framed by a translated sentence and then repeated
    verbatim, the way the Transmission daemon's words already are. A frame with
    nowhere to put the quote would be the loss the owner was asked about."""
    en = FRONTEND / "src" / "i18n" / "en.json"
    if not en.is_file():
        pytest.skip("frontend tree not present")
    d = json.load(io.open(en, encoding="utf-8"))
    assert "{detail}" in d["download.err_chd_converter"], (
        "ramka konwertera nie ma miejsca na to, co powiedzial chdman"
    )
    assert "{name}" in d["download.err_chd_archive"]
