"""A torrent was the one way into the library that nothing ever looked at.

Four things can put a file on this server. A library upload is scanned when
`clamav_auto_scan_upload` is on. A ROM upload is scanned the same way, on the
`.part` before it is renamed into place. A GOG download is scanned when
`clamav_auto_scan_download` is on, before it is adopted. A torrent was not
scanned at any point - and it is the one where the bytes come from anonymous
peers rather than from the account's own machine or from a shop.

`_collect_files` filtered names beginning with a dot, and its docstring says
"every real file the torrent left behind": a hidden-file filter, never a check.

SAME SHAPE AS THE GOG PATH, deliberately, because that is the setting an admin
has already been offered for exactly this: a download that finishes and then
becomes library content. It scans BEFORE the files are moved, so a threat never
reaches the library folder at all, and it fails OPEN when the daemon cannot
answer - the same rule stated in `scan_file`, and the same reason: a broken
daemon must not become a broken server. Failing open is logged every time,
because the admin asked for scanning and is entitled to know it did not happen.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from handler.torrent import seed_monitor as M


@pytest.fixture
def scanner(monkeypatch, tmp_path):
    from handler.clamav import clamav_handler as C

    src = tmp_path / "dl"
    src.mkdir()
    (src / "gra.bin").write_text("bytes")
    (src / "czytaj.txt").write_text("bytes")

    state = SimpleNamespace(on=True, verdict={"ok": True, "status": "ok"},
                            scanned=[], quarantined=[])

    async def _enabled():
        return state.on

    async def _scan(path):
        state.scanned.append(path)
        return dict(state.verdict)

    async def _quarantine(path, threat, **_k):
        state.quarantined.append((path, threat))
        return {"action": "quarantined"}

    monkeypatch.setattr(C, "is_download_scanning_enabled", _enabled)
    monkeypatch.setattr(C, "scan_file", _scan)
    monkeypatch.setattr(C, "quarantine_or_delete", _quarantine)

    state.files = [str(src / "gra.bin"), str(src / "czytaj.txt")]
    return state


@pytest.mark.asyncio
async def test_every_file_the_torrent_brought_is_looked_at(scanner):
    threat = await M._threat_in(scanner.files)

    assert threat is None
    assert sorted(scanner.scanned) == sorted(scanner.files), (
        "nie kazdy plik z torrenta zostal obejrzany"
    )


@pytest.mark.asyncio
async def test_an_infected_file_stops_the_whole_transfer(scanner):
    scanner.verdict = {"ok": True, "status": "FOUND", "threat": "Win.Test.EICAR"}

    threat = await M._threat_in(scanner.files)

    assert threat == "Win.Test.EICAR", (
        "zarazony plik nie zatrzymuje wlozenia torrenta do biblioteki"
    )


@pytest.mark.asyncio
async def test_the_infected_file_is_taken_away_not_merely_noted(scanner):
    scanner.verdict = {"ok": True, "status": "FOUND", "threat": "Win.Test.EICAR"}

    await M._threat_in(scanner.files)

    assert scanner.quarantined, (
        "zagrozenie zostalo tylko odnotowane, a plik lezy dalej tam, gdzie byl"
    )
    assert scanner.quarantined[0][1] == "Win.Test.EICAR"


@pytest.mark.asyncio
async def test_scanning_switched_off_costs_nothing(scanner):
    """THE DEFAULT. `clamav_auto_scan_download` is off unless an admin turns it
    on, and a torrent can be sixty gigabytes across hundreds of files."""
    scanner.on = False

    threat = await M._threat_in(scanner.files)

    assert threat is None
    assert scanner.scanned == [], "skanowanie wylaczone, a pliki i tak przeszly przez clamd"


@pytest.mark.asyncio
async def test_a_daemon_that_cannot_answer_does_not_block_the_transfer(scanner, caplog):
    """Fails OPEN, and says so. The rule is `scan_file`'s own: network and IO
    errors come back as "skipped" and callers must treat FOUND as the only
    rejection. A broken scanner turning every torrent into a failure would be a
    worse outage than the one it is guarding against."""
    scanner.verdict = {"ok": False, "status": "skipped", "message": "no daemon"}

    with caplog.at_level("WARNING"):
        threat = await M._threat_in(scanner.files)

    assert threat is None
    assert any("scan" in r.message.lower() or "clamav" in r.message.lower()
               for r in caplog.records), (
        "transfer przeszedl NIESPRAWDZONY i nikt sie o tym nie dowie, chociaz "
        "admin wlaczyl skanowanie"
    )


@pytest.mark.asyncio
async def test_the_finished_transfer_says_clamav_stopped_it(monkeypatch):
    """The reason has to reach the row. "Finished, no game, no explanation" is
    the silence this release has been removing everywhere else."""
    async def _threat(_files):
        return "Win.Test.EICAR"

    monkeypatch.setattr(M, "_threat_in", _threat)
    monkeypatch.setattr(M, "_collect_files", lambda _d: ["/tmp/x.bin"])
    monkeypatch.setattr("os.path.isdir", lambda _p: True)

    td = SimpleNamespace(id=5, title="Gra", download_dir="/tmp/dl", os="windows",
                         library=None, created_by_id=3, uploaded_by_id=3)

    game_id, reason, code, detail = await M._auto_register_game(td)

    assert game_id is None
    assert reason and "Win.Test.EICAR" in reason, (
        f"wiersz nie mowi, ze to ClamAV zatrzymal transfer: {reason!r}"
    )
    # I nazwa powodu, zeby ekran mogl napisac to zdanie po swojemu, oraz
    # sama sygnatura osobno - jest nazwa, nie zdaniem, i tlumaczenie jej
    # uczynilby ja niewyszukiwalna.
    assert code == "threat", f"brak nazwy powodu: {code!r}"
    assert detail == "Win.Test.EICAR", f"sygnatura nie podana osobno: {detail!r}"
