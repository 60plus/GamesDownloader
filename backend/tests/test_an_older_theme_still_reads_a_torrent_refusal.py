"""A torrent refusal still reads as a sentence to a theme that predates its name.

Finding #19 of the 1.0.34 pre-release audit. 1.0.34 gave the add-torrent refusals
a name and figures, so the dialog could say them in the reader's language - and
put them INSIDE `detail`, which until then had been a sentence. The themes
already on the stores print `detail` as it is: NEON HORIZON 1.4.2
(`tError.value = e?.response?.data?.detail`) and every published Vapor
(`error.value = e?.response?.data?.detail`). An owner who upgrades the core before
the themes got a block of JSON in the dialog where a sentence used to be.

So `detail` stays the sentence, and the name and its figures travel beside it in
the body. A theme that predates them prints the sentence; the core dialog and the
themes of this release translate from the name.
"""

from __future__ import annotations

import io
import json
import pathlib
import re

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
FRONTEND = BACKEND.parent / "frontend"


# ── The body ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_body_keeps_detail_a_sentence_and_puts_the_name_beside_it():
    from utils.errors import RefusalError, refusal_handler

    exc = RefusalError(413, {"code": "quota_refused",
                             "message": "This torrent is 5 GB and only 1 GB is left.",
                             "size": 5, "room": 1})

    response = await refusal_handler(None, exc)
    body = json.loads(response.body)

    assert response.status_code == 413
    assert body["detail"] == "This torrent is 5 GB and only 1 GB is left.", (
        "detail nie jest zdaniem - motyw sprzed 1.0.34 pokaze w oknie blok JSON"
    )
    assert body["code"] == "quota_refused", "nazwa powodu nie jedzie obok zdania"
    assert body["size"] == 5 and body["room"] == 1, "liczby nie jada obok zdania"


def test_a_refusal_is_still_an_http_error_to_everything_that_catches_one():
    """The routes and their helpers catch HTTPException to pass refusals on
    untouched; a refusal that stopped being one would be swallowed there."""
    from fastapi import HTTPException

    from utils.errors import RefusalError

    exc = RefusalError(409, {"code": "already_added", "message": "Already there."})

    assert isinstance(exc, HTTPException)
    assert exc.detail == "Already there."
    assert exc.refusal["code"] == "already_added"


def test_the_application_answers_a_refusal_with_that_body():
    source = io.open(BACKEND / "main.py", encoding="utf-8").read()
    assert "app.add_exception_handler(RefusalError, refusal_handler)" in source, (
        "aplikacja nie obsluguje odmowy, wiec cialo wraca w domyslnym ksztalcie"
    )


def test_no_add_route_puts_a_refusal_inside_detail_any_more():
    source = io.open(BACKEND / "endpoints" / "torrent" / "torrent_router.py",
                     encoding="utf-8").read()
    wrapped = re.findall(r"HTTPException\([^)]*?_(?:daemon_)?refusal\(", source, re.S)
    assert wrapped == [], (
        f"odmowa nadal wlozona do detail zwyklego HTTPException: {wrapped}"
    )


# ── The dialog ───────────────────────────────────────────────────────────────

def test_the_dialog_reads_the_name_from_beside_detail():
    lib = FRONTEND / "src" / "lib" / "transferError.ts"
    if not lib.is_file():
        pytest.skip("frontend tree not present")
    body = io.open(lib, encoding="utf-8").read()
    at = body.index("export function describeAddRefusal")
    fn = body[at:body.index("\nexport function", at + 10)]

    assert "data?.code" in fn, "okno nie czyta nazwy powodu obok detail"
    # The plain-string shortcut must stand aside for a named refusal, whose
    # `detail` is a perfectly good English sentence too.
    shortcut = re.search(r"if \((.*?)typeof detail === 'string' && detail\.trim\(\)\) return detail;", fn)
    assert shortcut, "brak skrotu dla zwyklego zdania"
    assert "!r.code" in shortcut.group(1), (
        "okno pokazuje angielskie zdanie nazwanej odmowy, zamiast ja przetlumaczyc"
    )
    assert fn.index("data?.code") < shortcut.start()
