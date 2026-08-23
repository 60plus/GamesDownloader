"""A stop must not leave a download stuck at 'downloading' for ever.

Shutdown was seven bare `.cancel()` calls and nothing else. Cancelling without
awaiting means no cancelled task reaches its own except or finally, so none of
them tidied up - and the transfers actually in flight were never touched at
all. Their rows stayed at status='downloading'.

That is not cosmetic. `gog_download_incomplete` answers yes while any job sits
in a pending state, so `refresh_downloaded_state` returns early for that game
for ever: it never flips back to downloaded even after a successful
re-download, and zip_packer refuses to pack it. And it needs no crash to
happen - installing a theme restarts the container a second after the
response, which is the documented way to do it.
"""
from __future__ import annotations

import ast
import pathlib

KORZEN = pathlib.Path(__file__).resolve().parent.parent


def _main() -> str:
    return (KORZEN / "main.py").read_text(encoding="utf-8")


def _funkcja(nazwa: str) -> str:
    for w in ast.walk(ast.parse(_main())):
        if isinstance(w, (ast.FunctionDef, ast.AsyncFunctionDef)) and w.name == nazwa:
            return ast.unparse(w)
    raise AssertionError(f"nie ma {nazwa} w main.py")


# ── Zamykanie ─────────────────────────────────────────────────────────────────

def test_zamkniecie_czeka_na_anulowane_petle():
    """Without the await, `.cancel()` only schedules the exception - the finally
    blocks never run because the loop is gone before they can."""
    src = _funkcja("lifespan")
    assert "asyncio.gather(*_loops, return_exceptions=True)" in src, (
        "petle sa anulowane, ale nikt na nie nie czeka")


def test_czekanie_na_petle_jest_ograniczone_czasem():
    """A container stop is on a clock, and a loop that will not go must not be
    what makes the stop look like a hang."""
    src = _funkcja("lifespan")
    assert "asyncio.wait_for" in src
    assert "asyncio.TimeoutError" in src, "brak obslugi przekroczenia czasu"


def test_zamkniecie_domyka_transfery_PRZED_anulowaniem_petli():
    src = _funkcja("lifespan")
    assert "_settle_transfers()" in src, "transfery w locie nie sa domykane"
    assert src.index("_settle_transfers()") < src.index("_t.cancel()"), (
        "petle gina zanim transfery zdaza sie zapisac")


def test_domykanie_uzywa_istniejacej_sciezki_pauzy():
    """Pausing already lands the row on `paused` and keeps the .part resumable.
    Inventing a shutdown-shaped state instead would be a second thing to keep
    right."""
    src = _funkcja("_settle_transfers")
    assert "pause_job" in src
    for handler in ("gog_download_handler", "rom_source_handler"):
        assert handler in src, f"{handler} nie jest domykany przy zamknieciu"


def test_domykanie_transferow_tez_ma_zegar():
    src = _funkcja("_settle_transfers")
    assert "asyncio.wait_for" in src and "asyncio.TimeoutError" in src


def test_domykanie_nie_wywraca_zamkniecia():
    """A handler that raises here must not stop the rest of the shutdown."""
    src = _funkcja("_settle_transfers")
    assert src.count("except Exception") >= 2


# ── Start ─────────────────────────────────────────────────────────────────────

def test_start_odblokowuje_zadania_zostawione_w_locie():
    src = _funkcja("_unstick_downloads")
    assert "'downloading', 'queued'" in src or '"downloading", "queued"' in src
    assert "'paused'" in src or '"paused"' in src


def test_odblokowanie_biegnie_PRZED_uzgadnianiem():
    """reconcile reads these rows to decide whether a game counts as
    downloaded, so it has to see them settled."""
    src = _funkcja("lifespan")
    assert src.index("_unstick_downloads()") < src.index("reconcile_loop"), (
        "uzgadnianie czyta wiersze, zanim ktos je naprawi")


def test_odblokowanie_nie_wywraca_startu():
    src = _funkcja("_unstick_downloads")
    assert "except Exception" in src, "blad tej migracji zatrzymalby caly serwer"
