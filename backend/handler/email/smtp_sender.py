"""Async SMTP email sender - uses stdlib smtplib in a thread executor."""
from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


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
) -> None:
    """Send an email asynchronously (runs smtplib in a thread executor)."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None, _send_sync,
        host, port, user, password, from_addr, to_addr, subject, body_html, tls_mode,
    )


def _send_sync(
    host: str, port: int, user: str, password: str,
    from_addr: str, to_addr: str, subject: str, body_html: str, tls_mode: str,
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = to_addr
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    if tls_mode == "ssl":
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=15) as smtp:
            if user:
                smtp.login(user, password)
            smtp.sendmail(from_addr, to_addr, msg.as_string())
    elif tls_mode == "starttls":
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            if user:
                smtp.login(user, password)
            smtp.sendmail(from_addr, to_addr, msg.as_string())
    else:  # "none"
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.ehlo()
            if user:
                smtp.login(user, password)
            smtp.sendmail(from_addr, to_addr, msg.as_string())
