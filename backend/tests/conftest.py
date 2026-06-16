"""Shared test setup.

Set a deterministic, sufficiently long auth secret BEFORE any test imports
`config` (which reads AUTH_SECRET_KEY at import time). A key of at least 32
chars also keeps PyJWT from emitting InsecureKeyLengthWarning during token
round-trips. We force the value (not setdefault) so the tests behave the same
regardless of whatever the shell or container happens to have exported.
"""
from __future__ import annotations

import os

os.environ["GD_AUTH_SECRET_KEY"] = "unit-test-secret-key-0123456789-abcdefghijklmnop"
os.environ.setdefault("GD_DEBUG", "true")
