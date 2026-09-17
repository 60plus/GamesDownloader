"""What went wrong belongs in the log; what the reader can act on goes on screen.

Today an ordinary account can be shown the text of any exception the server
happened to catch: a full path on the server's disk, a fragment of an SQL
statement out of an IntegrityError, the URL a provider was called with. Nothing
about that is deliberate - it is `except Exception as e: raise HTTPException(500,
str(e))`, written twenty times over several years, each time to avoid swallowing
a failure in silence. The instinct was right and the result leaks.

>>> MEASURED BEFORE ANY OF THIS WAS WRITTEN, because "61 places say str(e)" is a
number without a weight:
  - 41 of them catch a NARROW type, and are almost all our own ValueError with a
    sentence we wrote on purpose ("Quota exceeded"). Those are messages, not
    leaks, and this file deliberately does NOT touch them.
  - 20 catch `Exception`. Seven of those are reachable by an ordinary account,
    eleven need administrator permissions, and two already strip credentials.
  - 6 more put exception text into a job's error field, which is how it reaches
    the transfer tray.
  - 1 narrow one still leaks: `except OSError` on makedirs prints the whole path.

>>> THE OWNER CHOSE: SPLIT BY ACCOUNT. An administrator still sees the text -
they are the one who has to fix it, and a path or a module name is a clue rather
than a leak to somebody who configures paths for a living. Everybody else gets a
sentence and a reference. The full traceback always goes to the log under that
same reference, so nothing is lost and the two can be tied together.

>>> WHY THE ANSWER STAYS A PLAIN STRING. The obvious shape is the one the torrent
refusals use - `detail` as an object with a code and figures. Measured: 146
places in the core and 77 in the two themes read `.detail`, and most print it
straight into the interface. An object there renders as "[object Object]", and
the themes ship separately so they cannot be fixed in step. `detail` stays a
string here; classifying these for translation is the next task and can be done
one screen at a time, behind the fallback that already exists.

>>> THE MARKER IS `SETTINGS_WRITE`, NOT THE ROLE. Only the administrator role
holds it (measured), and `_PERM_REVOKE` takes a scope away WITHOUT changing the
role - so an administrator whose settings permission was withdrawn stops seeing
server internals, which is exactly right and is the lesson this project already
learned once, in the role model.
"""

from __future__ import annotations

import ast
import io
import logging
import pathlib
from types import SimpleNamespace

import pytest

from handler.auth.scopes import Scope

BACKEND = pathlib.Path(__file__).resolve().parent.parent

#: An exception whose text carries every kind of thing that must not reach an
#: ordinary account: a path on the server, a fragment of SQL, and a URL with a
#: token in it.
NASTY = OSError(
    "[Errno 13] Permission denied: '/APPS/GamesDownloader/library/pc/Doom.zip' "
    "while running INSERT INTO library_files (id, path) VALUES (?, ?) "
    "for https://api.example.com/v1?client_secret=hunter2"
)

SECRETS = (
    "/APPS/GamesDownloader",
    "INSERT INTO",
    "client_secret",
)


def _request(*scopes):
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=1, username="u"), scopes=set(scopes)))


# ── The helper ───────────────────────────────────────────────────────────────

def test_an_ordinary_account_is_not_shown_the_exception_text():
    from utils.errors import safe_detail

    said = safe_detail(NASTY, _request(Scope.LIBRARY_READ), what="Could not save the file")

    for secret in SECRETS:
        assert secret not in said, (
            f"zwykle konto dostaje `{secret}` prosto z wnetrza serwera: {said!r}"
        )
    assert "Could not save the file" in said, (
        "komunikat nie mowi nawet, CO sie nie udalo - to gorzej niz przeciek"
    )


def test_an_administrator_still_gets_the_text():
    """They are the one who has to fix it. Taking the text away from the person
    who configures the paths makes the application worse, not safer."""
    from utils.errors import safe_detail

    said = safe_detail(NASTY, _request(Scope.SETTINGS_WRITE), what="Could not save the file")

    assert "Permission denied" in said and "/APPS/GamesDownloader" in said, (
        "administrator stracil jedyna wskazowke, co sie stalo"
    )


def test_the_role_is_not_the_marker():
    """`_PERM_REVOKE` takes a scope away without touching the role. An account
    that still says "admin" but has had settings withdrawn must NOT see server
    internals - the same reading the role model settled once already."""
    from utils.errors import safe_detail

    revoked = SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=1, username="a", role="admin"),
        scopes={Scope.LIBRARY_ADMIN}))

    said = safe_detail(NASTY, revoked, what="Could not save the file")
    assert "/APPS/GamesDownloader" not in said, (
        "odczyt idzie po roli, a nie po uprawnieniu, wiec odebranie uprawnienia "
        "niczego nie zmienia"
    )


def test_no_request_is_treated_as_an_ordinary_account():
    """Several of these sites are helpers with no request in reach. The default
    has to be the safe one; a helper that assumes an administrator is a leak
    waiting for the first caller who is not one."""
    from utils.errors import safe_detail

    said = safe_detail(NASTY, None, what="Could not save the file")
    assert "/APPS/GamesDownloader" not in said


def test_both_sides_carry_the_same_reference_and_the_log_has_it(caplog):
    """A reference nobody can look up is decoration. The full traceback goes to
    the log under the same short code the reader was given."""
    from utils.errors import safe_detail

    with caplog.at_level(logging.ERROR):
        said = safe_detail(NASTY, _request(Scope.LIBRARY_READ), what="Could not save the file")

    import re
    m = re.search(r"[0-9a-f]{6}", said)
    assert m, f"komunikat nie niesie zadnego odnosnika: {said!r}"
    ref = m.group(0)

    written = "\n".join(r.getMessage() for r in caplog.records)
    assert ref in written, f"odnosnika {ref} nie ma w logu - nie da sie tego odszukac"
    assert "Permission denied" in written or any(r.exc_info for r in caplog.records), (
        "log dostal sam odnosnik bez tresci bledu, wiec wiedza przepadla"
    )


def test_two_failures_do_not_share_a_reference():
    from utils.errors import safe_detail

    a = safe_detail(NASTY, None, what="x")
    b = safe_detail(NASTY, None, what="x")
    assert a != b, "kazda awaria dostaje ten sam odnosnik, wiec nie wskazuje na nic"


def test_the_answer_is_a_plain_string():
    """146 places in the core and 77 in the themes print `detail` directly. An
    object here renders as "[object Object]" in all of them, and the themes are
    published separately so they cannot be fixed in step."""
    from utils.errors import safe_detail, safe_note

    assert isinstance(safe_detail(NASTY, None, what="x"), str)
    assert isinstance(safe_note(NASTY, what="x"), str)


def test_a_stored_note_is_never_the_administrators_version():
    """A job's error field is written ONCE and read by everybody who can see the
    transfer. Composing it for the account that happened to trigger it would
    persist an administrator's view for every later reader."""
    from utils.errors import safe_note
    import inspect

    said = safe_note(NASTY, what="Download failed")
    for secret in SECRETS:
        assert secret not in said

    # And it cannot be handed a request by accident.
    assert "request" not in inspect.signature(safe_note).parameters, (
        "safe_note przyjmuje request, wiec da sie zapisac w bazie widok admina"
    )


# ── Every leaking site actually goes through it ──────────────────────────────

BROAD = {"Exception", "BaseException"}

#: Two sites strip credentials with `_bez_poswiadczen` already and are reached
#: only by an administrator. Left as they are on purpose: that helper removes
#: secrets even from an administrator, which is the right call on an install
#: with more than one of them.
ALLOWED = {("handler/config/connection_tests.py", "_bez_poswiadczen")}


#: What an answer can be built with. `JSONResponse` since 1.0.35: the ROM upload
#: RETURNS its refusal (a raised one drops the background registration), and
#: this guard, reading only `HTTPException`, never saw it hand out the path of
#: the file it could not write (1.0.34 audit, #16).
_ANSWERS = {"HTTPException", "JSONResponse"}


def _sites():
    """Every `except Exception as e:` that puts `e` into an HTTPException or a
    JSONResponse, raised or returned."""
    out = []
    for path in sorted(BACKEND.rglob("*.py")):
        rel = path.relative_to(BACKEND).as_posix()
        if rel.startswith("tests/"):
            continue
        try:
            tree = ast.parse(io.open(path, encoding="utf-8").read())
        except SyntaxError:
            continue
        for h in ast.walk(tree):
            if not isinstance(h, ast.ExceptHandler) or not h.name:
                continue
            types = ([ast.unparse(x) for x in h.type.elts]
                     if isinstance(h.type, ast.Tuple)
                     else [ast.unparse(h.type)] if h.type else ["bare"])
            if not any(t in BROAD for t in types):
                continue
            for n in ast.walk(h):
                if isinstance(n, (ast.Raise, ast.Return)):
                    call = n.exc if isinstance(n, ast.Raise) else n.value
                else:
                    continue
                if not isinstance(call, ast.Call):
                    continue
                f = call.func
                if (getattr(f, "id", None) or getattr(f, "attr", None)) not in _ANSWERS:
                    continue
                if not any(isinstance(x, ast.Name) and x.id == h.name
                           for x in ast.walk(call)):
                    continue
                out.append((rel, n.lineno, ast.unparse(call)))
    return out


def test_no_broad_failure_reaches_a_screen_unfiltered():
    """The guard that makes this stick. A new `except Exception: str(e)` written
    next year fails here, which is the only reason a sweep like this does not
    quietly undo itself."""
    bad = []
    for rel, line, src in _sites():
        if any(rel == f and helper in src for f, helper in ALLOWED):
            continue
        if "safe_detail(" in src:
            continue
        bad.append(f"{rel}:{line}  {src[:90]}")

    assert not bad, (
        "tresc dowolnego wyjatku idzie prosto na ekran w %d miejscach:\n  %s"
        % (len(bad), "\n  ".join(bad))
    )


def test_the_sweep_did_not_swallow_our_own_messages():
    """THE LEGAL CASE, and the half that is easy to forget. 41 sites catch a
    narrow type and answer with a sentence we wrote on purpose. If this rewrite
    had reached them too, every precise refusal in the application would have
    turned into "something went wrong" - a bigger loss than the leak."""
    body = io.open(BACKEND / "endpoints" / "roms" / "rom_sources_router.py",
                   encoding="utf-8").read()
    assert "except ValueError as e:" in body
    at = body.index("except ValueError as e:")
    assert "str(e)" in body[at:at + 200], (
        "wlasne komunikaty tez zostaly zamienione na ogolniki"
    )


def test_the_path_on_disk_is_not_offered_when_a_folder_cannot_be_made():
    """The one narrow site that still leaks: OSError's own text is the full path
    on the server's disk, and creating a library folder is not an administrator
    action."""
    body = io.open(BACKEND / "endpoints" / "library" / "libraries_router.py",
                   encoding="utf-8").read()
    # Anchored on the message rather than on `except OSError`, which the first
    # version used: that matched the FIRST such handler in the file - an unrelated
    # `except OSError: pass` around a saved icon - and reported the wrong site as
    # broken. Matching letters instead of the instruction, again.
    at = body.index("Could not create folder")
    line = body[body.rindex("\n", 0, at) + 1:body.index("\n", at)]
    assert "safe_detail(" in line, (
        "blad tworzenia katalogu nadal podaje pelna sciezke na serwerze: " + line.strip()
    )
    assert "makedirs" in body[max(0, at - 400):at], (
        "ten komunikat nie stoi juz przy zakladaniu katalogu - test bada co innego"
    )


#: Everything that is allowed to stand between a caught exception and a field a
#: screen reads. `_safe_error` predates this file and does the same job for ROM
#: downloads; the other two strip credentials.
SANITISERS = ("safe_note", "safe_detail", "_safe_error", "loggable_error",
              "_bez_poswiadczen")

#: A field name a screen is likely to render.
ERRORISH = ("error", "error_msg", "error_message")


def _note_sites():
    """Exception text landing in a field a screen later reads.

    >>> READ THE HISTORY BEFORE SIMPLIFYING THIS. The first version matched
    lines containing `"error"` or `error_msg` together with `str(e)`/`str(exc)`,
    and it was blind twice over: it never saw an ATTRIBUTE (`job.error = ...`),
    and it never saw an exception bound to any other name (`except ... as err`).
    `chd_jobs.py` put `str(err)` straight into the field the tray draws and this
    guard reported the file as clean.

    So it reads the tree instead: inside a handler that binds an exception, any
    value derived from that exception which lands in an error-ish field has to
    pass through one of the sanitisers first.
    """
    out = []
    for path in sorted(BACKEND.rglob("*.py")):
        rel = path.relative_to(BACKEND).as_posix()
        if rel.startswith("tests/"):
            continue
        try:
            tree = ast.parse(io.open(path, encoding="utf-8").read())
        except SyntaxError:
            continue
        for h in ast.walk(tree):
            if not isinstance(h, ast.ExceptHandler) or not h.name:
                continue
            # The same narrow/broad line the rest of this file draws, and for
            # the same reason: `except _VirusFound as v` naming the signature
            # and `except ChdError as err` are sentences we wrote on purpose.
            # Without this the guard demanded that every precise message be
            # replaced by a vague one, which is the loss the legal-case test
            # below exists to prevent.
            htypes = ([ast.unparse(x) for x in h.type.elts]
                      if isinstance(h.type, ast.Tuple)
                      else [ast.unparse(h.type)] if h.type else ["bare"])
            if not any(t in BROAD for t in htypes):
                continue
            for n in ast.walk(h):
                pairs = []
                if isinstance(n, ast.Assign):
                    pairs = [(t, n.value) for t in n.targets]
                elif isinstance(n, ast.keyword) and n.arg in ERRORISH:
                    pairs = [(None, n.value)]
                elif isinstance(n, ast.Dict):
                    pairs = [(k, v) for k, v in zip(n.keys, n.values)
                             if isinstance(k, ast.Constant) and k.value in ERRORISH]
                for target, value in pairs:
                    if target is not None:
                        name = (getattr(target, "attr", None)
                                or getattr(target, "id", None)
                                or (target.value if isinstance(target, ast.Constant) else None)
                                or (getattr(target, "slice", None)
                                    and getattr(target.slice, "value", None)))
                        if name not in ERRORISH:
                            continue
                    src = ast.unparse(value)
                    uses = any(isinstance(x, ast.Name) and x.id == h.name
                               for x in ast.walk(value))
                    if uses and not any(s + "(" in src for s in SANITISERS):
                        out.append((rel, n.lineno, src[:80]))
    return out


#: Channels only an administrator ever reads. They keep the exception text, and
#: that is the SAME decision as everywhere else in this file rather than an
#: exception to it: an administrator is allowed to see the server's insides.
#:
#: A stored field cannot be composed per reader - it is written once, possibly
#: hours before anybody looks - so the split has to be made here, by channel,
#: and each one had its audience measured rather than assumed:
#:   gog_router          `_sync_status` is served by a route needing GOG_READ,
#:                       which only the administrator role holds.
#:   clamav_handler      the scan events are emitted `to_role="admin"` and the
#:                       screen reading them is Settings > Security.
#:   plugins_router      plugin sources: LIBRARY_ADMIN.
#:   settings_router     Settings, so SETTINGS_WRITE by definition.
#:   catalog_sync        the catalogue is published from the administrator's
#:                       side of the store.
#: Taking the text away from these would leave an administrator with no way to
#: read "cannot connect to clamd" without a shell on the server, which is a
#: worse application rather than a safer one.
ADMIN_ONLY_NOTES = (
    "endpoints/gog/gog_router.py",
    "endpoints/settings/plugins_router.py",
    "endpoints/settings/settings_router.py",
    "handler/clamav/clamav_handler.py",
    "handler/library/catalog_sync_handler.py",
)


def test_nothing_writes_raw_exception_text_into_a_field_an_ordinary_account_reads():
    """This is the road into the transfer tray, and the one the owner would meet
    first: a row saying `str(e)[:300]` sits there for hours.

    `meta_sources` is in here rather than on the list above because it was
    measured, not guessed: `library_game_meta_sources` asks for LIBRARY_READ,
    which every account has.
    """
    bad = [f"{rel}:{i}  {src[:80]}" for rel, i, src in _note_sites()
           if "safe_note(" not in src and rel not in ADMIN_ONLY_NOTES]
    assert not bad, (
        "tresc wyjatku laduje w polu, ktore czyta ekran, w %d miejscach:\n  %s"
        % (len(bad), "\n  ".join(bad))
    )
