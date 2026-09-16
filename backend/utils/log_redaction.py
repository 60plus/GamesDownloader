"""No log line carries a secret that lives in an address.

Several providers authenticate through the address itself. ScreenScraper puts
the account name, the account password and the developer password in the query
string of every API call and every media URL; the IGDB token endpoint takes the
client secret the same way; a GOG download link is signed with a token written
into its path. Those addresses reached the log in three ways, all found on
2026-09-16:

  * written outright - `[all-media] cover sample` logged three ScreenScraper
    cover URLs on every media lookup, 54 lines on the live server;
  * inside an exception - httpx repeats the whole request URL in the message of
    an HTTP error, so `logger.warning("...: %s", exc)` wrote the password
    without the line naming any address;
  * inside a traceback, which carries that same message.

The second and third shape were in well over a hundred log lines across the
backend, most of them logging errors that never touch an address. Rewriting each
line would last until the next one is written, so the secret is taken out where
every record is made instead: `install_log_redaction` wraps the log record
factory, and each record is cleaned as it is created - its message, its
arguments and its traceback - whatever logger or level it came from.

What is masked is only the VALUE of a known secret parameter, the user:password
part of an address, and a token signed into a path. The host, the path and every
other parameter stay, so the line still says what was asked and what failed.
Arguments keep their type unless they actually contained a secret, because some
formatters depend on it: uvicorn's access log unpacks its arguments by position
and prints the status with %d.
"""

from __future__ import annotations

import logging
import re

MASK = "***"

# The names `recently_added._CRED_MARKERS` refuses to store or show, plus the
# ones only a log could ever see: the ScreenScraper account name, an OAuth
# client secret, refresh token and authorisation code. A test keeps the two
# lists from drifting apart.
_SECRET_PARAMETERS = (
    "password", "passwd", "pwd", "sspassword", "devpassword", "ssid",
    "apikey", "api_key", "api-key", "key",
    "access_token", "refresh_token", "id_token", "token",
    "client_secret", "secret", "code",
    "sig", "signature", "auth", "hash", "sessionid", "session",
)

# `?name=value`, `&name=value` or `;name=value`. The separator in front is what
# keeps `info_hash=` or `key=value` written in a sentence from being taken for a
# parameter.
_QUERY_SECRET = re.compile(
    r"(?i)([?&;](?:"
    + "|".join(re.escape(n) for n in sorted(_SECRET_PARAMETERS, key=len, reverse=True))
    + r")=)[^&;#\s'\"<>]*"
)
# scheme://user:password@host - only when the @ comes before the first slash.
_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)[^/?#@\s'\"<>]+@")
# GOG's CDN signs a link in its path: /token=nva=...~dirs=...~token=.../secure/...
_PATH_TOKEN = re.compile(r"(?i)(/token=)[^/?#\s'\"<>]*")


def redact_secrets(text) -> str:
    """`text` with the value of every secret in an address replaced by ***."""
    s = text if isinstance(text, str) else str(text)
    if not s:
        return s
    s = _USERINFO.sub(r"\1" + MASK + "@", s)
    s = _QUERY_SECRET.sub(r"\1" + MASK, s)
    return _PATH_TOKEN.sub(r"\1" + MASK, s)


def _clean_argument(value):
    """The argument itself when it holds no secret, its cleaned text when it does."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    try:
        plain = value if isinstance(value, str) else str(value)
    except Exception:
        return value
    cleaned = redact_secrets(plain)
    return cleaned if cleaned != plain else value


_TRACEBACK_FORMATTER = logging.Formatter()


def _clean_record(record: logging.LogRecord) -> None:
    if isinstance(record.msg, str):
        record.msg = redact_secrets(record.msg)
    else:
        record.msg = _clean_argument(record.msg)
    if isinstance(record.args, tuple):
        record.args = tuple(_clean_argument(a) for a in record.args)
    elif isinstance(record.args, dict):
        record.args = {k: _clean_argument(v) for k, v in record.args.items()}
    # A formatter writes the traceback from exc_text when it is already set, so
    # formatting it here, cleaned, is what every handler will print.
    if record.exc_info and not record.exc_text:
        record.exc_text = redact_secrets(_TRACEBACK_FORMATTER.formatException(record.exc_info))
    if record.stack_info:
        record.stack_info = redact_secrets(record.stack_info)


def install_log_redaction() -> None:
    """Clean every log record as it is created. Installing twice is harmless."""
    current = logging.getLogRecordFactory()
    if getattr(current, "_gd_redacts_secrets", False):
        return

    def factory(*args, **kwargs):
        record = current(*args, **kwargs)
        try:
            _clean_record(record)
        except Exception:
            # A log line that could not be cleaned is still better written than
            # lost; the cases above do not raise on anything logging accepts.
            pass
        return record

    factory._gd_redacts_secrets = True
    logging.setLogRecordFactory(factory)
