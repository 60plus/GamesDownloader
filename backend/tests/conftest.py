"""Shared test setup.

Set a deterministic, sufficiently long auth secret BEFORE any test imports
`config` (which reads AUTH_SECRET_KEY at import time). A key of at least 32
chars also keeps PyJWT from emitting InsecureKeyLengthWarning during token
round-trips. We force the value (not setdefault) so the tests behave the same
regardless of whatever the shell or container happens to have exported.

`GD_BASE_PATH` is forced for the same reason and at the same moment. It
defaults to `/data`, which exists inside the container and nowhere else, and
importing `main` creates the resources directory under it at import time. Left
alone, the suite passes in the container and cannot even be collected on a
machine without a writable `/data`, which is the wrong way round: a unit test
that touches a real path there is a test that lies about where it runs. The
directory is temporary and per run, so nothing carries between runs either.
"""
from __future__ import annotations

import os
import tempfile

os.environ["GD_AUTH_SECRET_KEY"] = "unit-test-secret-key-0123456789-abcdefghijklmnop"
os.environ["GD_BASE_PATH"] = tempfile.mkdtemp(prefix="gd-tests-")
os.environ.setdefault("GD_DEBUG", "true")
