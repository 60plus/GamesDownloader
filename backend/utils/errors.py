"""What went wrong belongs in the log; what the reader can act on goes on screen.

`except Exception as e: raise HTTPException(500, str(e))` is written twenty times
across this application, always for a good reason - a failure swallowed in
silence is worse than an ugly message. The result is that an ordinary account
can be shown a full path on the server's disk, a fragment of an SQL statement out
of an IntegrityError, or the URL a provider was called with.

>>> SPLIT BY ACCOUNT, which is the owner's decision. An administrator still sees
the text: they are the one who has to fix it, and a path or a missing module name
is a clue rather than a leak to somebody who configures paths for a living.
Everybody else gets a sentence and a reference. The full traceback always goes to
the log under that same reference, so nothing is lost and the two can be tied
together afterwards.

>>> THE MARKER IS `SETTINGS_WRITE`, NOT THE ROLE. Only the administrator role
holds it, and `_PERM_REVOKE` takes a scope away WITHOUT changing the role - so an
administrator whose settings permission was withdrawn stops seeing server
internals. Reading the role instead would ignore that, which is the mistake the
role model already cost this project once.

>>> `detail` IS A PLAIN STRING, ON PURPOSE. Measured before choosing: 146 places
in the core and 77 in the two themes read `.detail`, and most print it straight
into the interface, where an object renders as "[object Object]" or a block of
JSON. The themes are published separately and cannot be fixed in step. The
torrent refusals learned that the hard way (1.0.34 audit, finding #19): they put
a reason code and figures INSIDE `detail`, and every theme already on the stores
showed JSON where a sentence had been. `RefusalError` below is the shape that
works for both kinds of reader - `detail` stays the sentence, and the code and
figures travel beside it in the body.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import HTTPException

from handler.auth.scopes import Scope

logger = logging.getLogger(__name__)


def _reference() -> str:
    """Short enough to read out over the phone, long enough not to collide."""
    return secrets.token_hex(3)


def _may_see_internals(request) -> bool:
    """Whether this caller already has the run of the server's insides.

    Deliberately a SCOPE and not a role: see the note at the top of this file.
    Anything unreadable - no request, no state, no scopes - answers no, because
    the safe direction is the one that shows less.
    """
    scopes = getattr(getattr(request, "state", None), "scopes", None)
    try:
        return Scope.SETTINGS_WRITE in (scopes or ())
    except TypeError:
        return False


def _log(exc: BaseException, what: str) -> str:
    ref = _reference()
    # `exc_info` rather than the message: the traceback is the part worth having,
    # and it is the only copy of what the reader was not shown.
    logger.error("[%s] %s", ref, what, exc_info=exc)
    return ref


def safe_detail(exc: BaseException, request=None, *, what: str) -> str:
    """The text for `HTTPException(detail=...)`, cut to fit the caller.

    `what` is the operation that failed, in the wording the call site already
    used ("GOG API error", "Could not create folder"). It reaches everybody: a
    message that does not say what failed is worse than one that says too much.
    """
    ref = _log(exc, what)
    if _may_see_internals(request):
        return f"{what}: {exc} (ref {ref})"
    return f"{what}. (ref {ref})"


def safe_note_ref(exc: BaseException, *, what: str) -> tuple[str, str]:
    """The sentence AND the reference, separately.

    The screen needs the reference on its own. A transfer that failed for a
    reason nobody has classified still gets to say "ask an administrator about
    a1b2c3" in the reader's language, and it cannot do that by pulling the code
    back out of an English sentence.
    """
    ref = _log(exc, what)
    return f"{what}. (ref {ref})", ref


def safe_note(exc: BaseException, *, what: str) -> str:
    """The same, for a field that is STORED or broadcast rather than answered.

    A job's error column is written once and read by everybody who can see that
    transfer, possibly hours later; a socket event goes to whoever is listening.
    There is no caller to measure at that moment, so this never takes a request -
    handing it one would persist an administrator's view for every later reader,
    and that mistake would be invisible until somebody looked.
    """
    return safe_note_ref(exc, what=what)[0]


class RefusalError(HTTPException):
    """A refusal the screen can translate that still reads as a sentence.

    `detail` is the sentence: what every reader that does not know the name
    prints - a theme published before the name existed, a plugin, curl. The name
    and its figures travel BESIDE it in the body (see `refusal_handler`), and the
    dialog composes the sentence in the reader's language from those.

    A subclass of HTTPException, so every `except HTTPException: raise` on the
    way out passes it on untouched.
    """

    def __init__(self, status_code: int, refusal: dict, headers: dict | None = None):
        super().__init__(status_code, str(refusal.get("message") or ""), headers=headers)
        self.refusal = dict(refusal)


async def refusal_handler(_request, exc: RefusalError):
    """The body of a `RefusalError`: the name and figures, with `detail` written
    last so nothing in the refusal can replace the sentence."""
    from fastapi.responses import JSONResponse

    return JSONResponse({**exc.refusal, "detail": exc.detail},
                        status_code=exc.status_code, headers=exc.headers)
