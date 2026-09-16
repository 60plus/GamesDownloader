"""A log line never carries a secret that lives in an address.

Found on 2026-09-16 while measuring the ROM metadata editor against the live
server's log: `[all-media] cover sample` wrote the first three ScreenScraper
cover URLs of every media lookup - 54 lines since that container started - each
with the developer password and the account name in its query string. The line
was cut at 120 characters, which ended just short of the account password. That
was the order of the parameters, not a decision anybody made.

Following it through the backend found the same leak in three shapes:

  * a log line writing an address outright - sixteen of them, a signed GOG
    download link among them (GOG keeps that token in the PATH, not the query);
  * a log line writing only the exception - but httpx repeats the whole request
    URL in the message of an HTTP error, so a picture that failed to download
    wrote the ScreenScraper password through `str(exc)` without naming a URL
    (shown by the two download tests below, which failed on the code as it was);
  * `logger.exception`, whose traceback carries that same message.

A scan for the second and third shape over the backend listed well over a
hundred log lines, most of them logging errors that never touch an address. A
fix per line would have rewritten all of them and lasted until the next one was
written. So the secret is taken out in one place instead: every log record is
cleaned as it is created, whichever logger, level or shape it came from.
"""

from __future__ import annotations

import ast
import inspect
import io
import logging
import pathlib

import httpx
import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent

SS = (
    "https://neoclone.screenscraper.fr/api2/mediaJeu.php?devid=dev&devpassword=DEVSECRET"
    "&softname=GD&ssid=someone&sspassword=USERSECRET&systemeid=57&jeuid=19270&media=box-2D(us)"
)
GOG_CDN = (
    "https://gog-cdn-fastly.gog.com/token=nva=1790000000~dirs=4~token=0SIGNEDTOKEN"
    "/secure/offline/1207658924/setup_game_1.0.exe"
)


def _assert_clean(text: str) -> None:
    for secret in ("USERSECRET", "DEVSECRET", "ssid=someone", "SIGNEDTOKEN"):
        assert secret not in text, f"{secret!r} reached the log"


def _http_error(url: str) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", url)
    return httpx.HTTPStatusError(
        f"Client error '404 Not Found' for url '{url}'",
        request=request, response=httpx.Response(404, request=request),
    )


@pytest.fixture
def redacting():
    from utils.log_redaction import install_log_redaction

    before = logging.getLogRecordFactory()
    install_log_redaction()
    yield
    logging.setLogRecordFactory(before)


# ── what is masked, and what is not ──────────────────────────────────────────

def test_the_screenscraper_credentials_are_masked_and_the_rest_of_the_address_stays():
    from utils.log_redaction import redact_secrets

    out = redact_secrets(SS)
    _assert_clean(out)
    assert "someone" not in out
    assert out.startswith("https://neoclone.screenscraper.fr/api2/mediaJeu.php?")
    for kept in ("devid=dev", "softname=GD", "jeuid=19270", "media=box-2D(us)"):
        assert kept in out, f"{kept} was masked too, and the line no longer says what was asked"


def test_a_token_signed_into_a_path_is_masked():
    from utils.log_redaction import redact_secrets

    out = redact_secrets(GOG_CDN)
    assert "SIGNEDTOKEN" not in out and "nva=" not in out
    assert out.startswith("https://gog-cdn-fastly.gog.com/token=***/secure/")
    assert out.endswith("/setup_game_1.0.exe")


def test_credentials_in_the_authority_are_masked():
    from utils.log_redaction import redact_secrets

    assert redact_secrets("https://user:pass@host.example/a?x=1") == "https://***@host.example/a?x=1"


@pytest.mark.parametrize("param", ["client_secret", "refresh_token", "code", "key", "api_key", "token", "password"])
def test_each_secret_parameter_is_masked(param):
    from utils.log_redaction import redact_secrets

    out = redact_secrets(f"https://auth.example/token?grant_type=x&{param}=S3CRET&next=1")
    assert "S3CRET" not in out
    assert f"{param}=***" in out and "grant_type=x" in out and "next=1" in out


def test_every_marker_the_leak_check_knows_is_masked():
    """One list decides what may not be stored or shown; logs may not drift from it."""
    from handler.notifications.recently_added import _CRED_MARKERS
    from utils.log_redaction import redact_secrets

    for marker in _CRED_MARKERS:
        name = marker.rstrip("=")
        out = redact_secrets(f"https://x.example/p?a=1&{name}=S3CRET")
        assert "S3CRET" not in out, f"{name}= is refused as leaky but still reaches a log"


@pytest.mark.parametrize("text", [
    "ROM 54: saved cover.png",
    "info_hash=abc123 seeding",
    "key=value pairs written in prose",
    'GET /api/roms/search?query=Tekken&platform_slug=playstation HTTP/1.1',
    "https://howlongtobeat.com/api/find/init?t=1789578745",
])
def test_ordinary_text_is_left_exactly_as_it_was(text):
    """THE LEGAL CASE: a log that stops saying what happened helps nobody."""
    from utils.log_redaction import redact_secrets

    assert redact_secrets(text) == text


# ── every shape a record can take ────────────────────────────────────────────

def test_an_address_passed_as_an_argument_is_masked(redacting, caplog):
    caplog.set_level(logging.DEBUG)
    logging.getLogger("gd.test").warning("could not fetch %s", SS)
    _assert_clean(caplog.text)
    assert "neoclone.screenscraper.fr/api2/mediaJeu.php" in caplog.text


def test_an_httpx_error_passed_as_an_argument_is_masked(redacting, caplog):
    caplog.set_level(logging.DEBUG)
    logging.getLogger("gd.test").warning("ScreenScraper error (%s): %s", "by hash", _http_error(SS))
    _assert_clean(caplog.text)
    assert "404 Not Found" in caplog.text


def test_an_f_string_message_is_masked(redacting, caplog):
    caplog.set_level(logging.DEBUG)
    err = _http_error(GOG_CDN)
    logging.getLogger("gd.test").warning(f"download failed: {err}")
    _assert_clean(caplog.text)


def test_a_traceback_is_masked(redacting, caplog):
    caplog.set_level(logging.DEBUG)
    try:
        raise _http_error(SS)
    except httpx.HTTPStatusError:
        logging.getLogger("gd.test").exception("download failed")
    _assert_clean(caplog.text)
    assert "Traceback" in caplog.text and "HTTPStatusError" in caplog.text


def test_an_access_log_record_keeps_its_arguments_as_they_were(redacting):
    """THE LEGAL CASE: uvicorn's access formatter unpacks record.args by position
    and formats the status with %d."""
    args = ("192.168.0.40:50000", "GET", "/api/roms/54/all-media?platform_slug=playstation&ss_id=19270", "1.1", 200)
    record = logging.getLogger("uvicorn.access").makeRecord(
        "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d', args, None,
    )
    assert record.args == args
    assert record.getMessage().endswith(" 200")


def test_a_record_with_nothing_secret_is_untouched(redacting, caplog):
    caplog.set_level(logging.DEBUG)
    logging.getLogger("gd.test").info("ROM %s: %d covers, %.1f MB", 54, 22, 94.0)
    assert "ROM 54: 22 covers, 94.0 MB" in caplog.text


def test_an_argument_without_a_secret_keeps_being_itself(redacting, caplog):
    """THE LEGAL CASE: `%r` of an object with nothing to hide still shows the
    object, not its text in quotes."""
    caplog.set_level(logging.DEBUG)
    logging.getLogger("gd.test").info("wrote %r", pathlib.PurePosixPath("/data/resources/roms/54/cover.png"))
    assert "wrote PurePosixPath('/data/resources/roms/54/cover.png')" in caplog.text


# ── the paths that leaked ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_screenscraper_picture_that_fails_to_download_logs_no_password(redacting, monkeypatch, tmp_path, caplog):
    from handler.metadata import rom_scrape_handler as rsh

    async def refuse(url, **kw):
        raise _http_error(url)

    monkeypatch.setattr(rsh, "fetch_media_bytes", refuse)
    caplog.set_level(logging.DEBUG)

    assert await rsh._download_image(SS, tmp_path / "cover.png") is None

    _assert_clean(caplog.text)
    assert "neoclone.screenscraper.fr/api2/mediaJeu.php" in caplog.text, (
        "the line no longer says which download failed"
    )
    assert "404" in caplog.text, "the line no longer says why it failed"


@pytest.mark.asyncio
async def test_a_request_cover_that_fails_to_download_logs_no_password(redacting, monkeypatch, caplog):
    """The line that names no URL at all, and wrote the password through the error."""
    from handler.library import media_handler

    async def refuse(url, **kw):
        raise _http_error(url)

    monkeypatch.setattr(media_handler, "fetch_media_bytes", refuse)
    caplog.set_level(logging.DEBUG)

    assert await media_handler.download_request_cover(7, SS) is None

    _assert_clean(caplog.text)


# ── in the running app ───────────────────────────────────────────────────────

def test_the_app_cleans_its_log_records_from_the_moment_logging_is_set_up():
    """Checked on the source: importing main in one test and a fixture restoring
    the factory in another would make an import-time check depend on test order."""
    tree = ast.parse(io.open(BACKEND / "main.py", encoding="utf-8").read())
    statements = [ast.unparse(node) for node in tree.body]
    setup = next(i for i, s in enumerate(statements) if s.startswith("logging.basicConfig("))
    install = next((i for i, s in enumerate(statements) if s == "install_log_redaction()"), None)
    assert install is not None, "main.py never installs the log redaction"
    assert install == setup + 1, "the redaction is installed later than logging itself"


def test_the_media_lookup_no_longer_logs_sample_cover_addresses():
    from endpoints.roms import roms_router

    assert "cover sample" not in inspect.getsource(roms_router.get_rom_all_media)
