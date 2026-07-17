"""Async SMTP email sender - uses stdlib smtplib in a thread executor."""
from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

logger = logging.getLogger(__name__)


def _html_to_text(html: str) -> str:
    """Cheap HTML -> plain text for the alternative part: drop head/style/script,
    turn breaks into newlines, strip tags, unescape entities, collapse blanks."""
    import html as _html
    import re
    t = re.sub(r"(?is)<(style|script|head|title)[^>]*>.*?</\1>", " ", html or "")
    t = re.sub(r"(?i)<(br|/p|/div|/tr|/h[1-6])\s*/?>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = _html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n\s*\n+", "\n\n", t)
    return t.strip() or "View this email in an HTML-capable client."


async def send_email(
    host:      str,
    port:      int,
    user:      str,
    password:  str,
    from_addr: str,
    to_addr:   str,
    subject:   str,
    body_html: str,
    tls_mode:  str = "starttls",  # "starttls" | "ssl" | "none"
    bcc:       list[str] | None = None,
    body_text: str | None = None,
) -> None:
    """Send an email asynchronously (runs smtplib in a thread executor).

    `bcc` are hidden recipients: they receive the mail (envelope) but no Bcc
    header is added, so recipients never see each other's addresses.
    `body_text` is the plain-text alternative; when omitted it is derived from
    the HTML (an HTML-only mail scores worse with spam filters)."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None, _send_sync,
        host, port, user, password, from_addr, to_addr, subject, body_html, tls_mode, bcc, body_text,
    )
    # Count what actually went out (recipients), for the admin dashboard. Only
    # reached when the send above did not raise; best-effort, never blocks mail.
    recipients = list(dict.fromkeys(a for a in (bcc if bcc else [to_addr]) if a))
    if recipients:
        from handler.email.email_stats import record_email_sent
        await record_email_sent(len(recipients))


def _send_sync(
    host: str, port: int, user: str, password: str,
    from_addr: str, to_addr: str, subject: str, body_html: str, tls_mode: str,
    bcc: list[str] | None = None, body_text: str | None = None,
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = to_addr
    # Date + a UNIQUE Message-ID are required by RFC 5322 and are a strong
    # deliverability signal. Without them, sending several mails in a row (same
    # subject/body) lets Mailjet/Gmail treat the later ones as duplicates and
    # drop them - the first arrives, the rest silently do not. A fresh msgid per
    # message keeps every send distinct.
    msg["Date"] = formatdate(localtime=True)
    _domain = from_addr.split("@")[-1] if "@" in (from_addr or "") else None
    msg["Message-ID"] = make_msgid(domain=_domain)
    # Order matters: last part is the client's preferred rendering. Plain text
    # first, HTML second - and always include a text part for deliverability.
    msg.attach(MIMEText(body_text or _html_to_text(body_html), "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    # When BCC recipients are given they are the real (hidden) audience and
    # `to_addr` is only the visible header placeholder - deliver to BCC only.
    # Otherwise it is an ordinary single-recipient message.
    if bcc:
        envelope = list(dict.fromkeys(a for a in bcc if a))
    else:
        envelope = [to_addr] if to_addr else []
    if not envelope:
        return

    if tls_mode == "ssl":
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=15) as smtp:
            if user:
                smtp.login(user, password)
            smtp.sendmail(from_addr, envelope, msg.as_string())
    elif tls_mode == "starttls":
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            if user:
                smtp.login(user, password)
            smtp.sendmail(from_addr, envelope, msg.as_string())
    else:  # "none"
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.ehlo()
            if user:
                smtp.login(user, password)
            smtp.sendmail(from_addr, envelope, msg.as_string())
