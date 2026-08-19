"""Short-lived signed links for downloading a ROM.

The interface cannot send an Authorization header when it saves a file - a
download is a browser navigation - so the link carries a signature instead.
That makes the rules worth pinning down: a ticket is for one ROM, one user, and
only for a few minutes.
"""
from __future__ import annotations

import time

from utils import download_tickets as dt


def test_a_fresh_ticket_is_accepted():
    exp, sig = dt.issue(42, 7)
    assert dt.valid(42, 7, exp, sig) is True


def test_a_ticket_is_bound_to_its_rom():
    exp, sig = dt.issue(42, 7)
    assert dt.valid(43, 7, exp, sig) is False


def test_a_ticket_is_bound_to_its_user():
    # Otherwise a link handed to one account would serve anyone who received it.
    exp, sig = dt.issue(42, 7)
    assert dt.valid(42, 8, exp, sig) is False


def test_an_expired_ticket_is_refused_however_well_signed():
    exp, sig = dt.issue(42, 7, ttl_s=-1)
    assert dt.valid(42, 7, exp, sig) is False


def test_moving_the_deadline_invalidates_the_signature():
    # The expiry is signed, so it cannot be edited in the URL to buy more time.
    exp, sig = dt.issue(42, 7)
    assert dt.valid(42, 7, exp + 3600, sig) is False


def test_a_missing_or_wrong_signature_is_refused():
    exp, _ = dt.issue(42, 7)
    assert dt.valid(42, 7, exp, "") is False
    assert dt.valid(42, 7, exp, "0" * 32) is False


def test_tickets_last_long_enough_to_click():
    exp, _ = dt.issue(42, 7)
    assert exp - int(time.time()) >= 60
