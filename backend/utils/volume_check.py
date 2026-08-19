"""Does a directory survive the next container recreate?

The shipped compose bind-mounts each data directory separately rather than
/data as a whole. That is deliberate - it lets an operator put games on one
disk and the database on another - but it has a sharp edge: every time the
application grows a NEW directory under /data, an install running an older
compose file has no mount for it, and everything written there lives in the
container's writable layer. It disappears on the next `up -d`, silently.

Saves hit this first. Firmware hit it second. Rather than each feature
re-deriving the check, it lives here: ask before writing anything a user would
be upset to lose.
"""

from __future__ import annotations

from pathlib import Path


def is_ephemeral(path: Path) -> bool:
    """True when *path* would vanish on the next container recreate.

    Only meaningful inside a container. Outside one this is the host's own
    filesystem and nothing is about to be thrown away, so the answer is False.

    A directory counts as persistent when it, or any directory above it, is a
    mount point - that covers both a mount on the directory itself and a mount
    on a parent such as /data.
    """
    if not Path("/.dockerenv").exists():
        return False   # not a container: this is the host's own filesystem
    try:
        mounts = set()
        for line in Path("/proc/self/mountinfo").read_text().splitlines():
            parts = line.split(" ")
            if len(parts) > 4:
                mounts.add(parts[4])
    except OSError:
        return False   # cannot tell; do not block the app over it
    p = path.resolve()
    for cand in (p, *p.parents):
        if str(cand) == "/":
            break
        if str(cand) in mounts:
            return False
    return True
