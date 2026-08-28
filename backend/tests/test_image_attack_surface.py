"""What the image ships that nothing in it actually runs.

Docker Scout scanned the published image and found 76 fixable advisories in
ten packages. Reading them one by one produced an uncomfortable result: 62 of
those 76, and all three of the critical ones, came from two programs that GD
either barely uses or never uses at all.

  * gosu is one small program, called once at startup to step down from root
    to PUID/PGID. It is written in Go, so it drags a statically linked Go
    runtime into the image, and with it 46 advisories against Go's networking
    and TLS libraries - code gosu never enters. Debian will not rebuild it
    against a newer Go on this timescale, so the advisories stay as long as
    the binary does. setpriv does the same job, ships in util-linux, and is
    already in the image because Debian installs it everywhere.
  * npm is needed to build the image (it installs Vite for the theme plugin
    compiler) and is never invoked afterwards. Its own dependency tree carries
    16 advisories including a critical one in tar. Nothing that runs at
    runtime imports it.

The rest is ordinary: Debian published a fixed openssl after the base image
was built, and a build that never upgrades will never take it.

These are pinned rather than trusted to review because each failure is silent.
An image that quietly reacquires gosu, or that stops removing npm because the
layer moved, looks and behaves exactly like a correct one.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DOCKERFILE = ROOT / "Dockerfile"
ENTRYPOINT = ROOT / "entrypoint.sh"

# Everything that runs after the image is built. If npm is to be deleted from
# the image, no line here may reach for it.
RUNTIME_TREES = (
    ROOT / "backend",
    ROOT / "scripts",
)
RUNTIME_FILES = (ENTRYPOINT,)


@pytest.fixture(scope="module")
def dockerfile() -> str:
    if not DOCKERFILE.is_file():
        pytest.skip("Dockerfile nie jest obecny")
    return DOCKERFILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def entrypoint() -> str:
    if not ENTRYPOINT.is_file():
        pytest.skip("entrypoint.sh nie jest obecny")
    return ENTRYPOINT.read_text(encoding="utf-8")


def _instructions(source: str) -> str:
    """The file with its comments taken out.

    Both files explain at length why gosu is gone, so a test that forbade the
    word would be answered by deleting the explanation. What must not come
    back is the call and the package, not the name.
    """
    return "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )


def test_privileges_are_dropped_without_a_go_runtime(dockerfile, entrypoint):
    """The single highest-value line in the whole scan. Dropping gosu takes 46
    advisories out of the image, two of them critical, and costs nothing: the
    replacement is already installed."""
    assert "setpriv" in _instructions(entrypoint), (
        "entrypoint nie schodzi z roota przez setpriv"
    )
    assert "gosu" not in _instructions(entrypoint), (
        "gosu wciaz uzywany przy zrzucaniu uprawnien"
    )
    assert "gosu" not in _instructions(dockerfile), (
        "gosu wciaz instalowany do obrazu"
    )


def test_the_dropped_process_keeps_the_groups_gosu_gave_it(entrypoint):
    """setpriv is only a drop-in replacement if it is called like one. Without
    the group flags the process keeps root's supplementary groups, which is a
    quieter and worse outcome than not dropping privileges at all."""
    called = _instructions(entrypoint)
    assert "--reuid" in called and "--regid" in called, "setpriv nie ustawia uid/gid"
    assert "--init-groups" in called, "brak grup pomocniczych uzytkownika"
    # gosu accepts a bare numeric uid with no passwd entry; --init-groups does
    # not, and a setpriv that fails here means the container never starts.
    assert "--clear-groups" in called, (
        "brak wariantu dla uid bez wpisu w passwd - kontener by nie wstal"
    )
    assert "--inh-caps=-all" in called, "zdejmowane uprawnienia nie sa czyszczone"


def test_npm_does_not_ship_in_the_runtime_image(dockerfile):
    """npm builds the image and is dead weight afterwards, together with the
    16 advisories in its own node_modules."""
    built = _instructions(dockerfile)
    assert "/usr/lib/node_modules/npm" in built, (
        "npm zostaje w obrazie razem ze swoim drzewem zaleznosci"
    )
    # The build's own guarantee: if npm is still on PATH afterwards the image
    # does not get built at all. Pinned because it is the only thing standing
    # between a moved path and a silently reinstated package manager.
    assert "! command -v npm" in built, (
        "nic nie sprawdza, czy npm naprawde zniknal"
    )


def test_the_scanner_comes_without_the_command_line_tools_nobody_calls(dockerfile):
    """clamd is reached over its socket and freshclam is run as a subprocess,
    and those belong to clamav-daemon and clamav-freshclam. The `clamav`
    package on top of them carries clamscan, sigtool and clambc - 32 MB of
    programs this project never invokes, and clamav-daemon does not depend on
    it. Matched on the whole line so clamav-daemon does not satisfy it."""
    lines = [
        line.strip().rstrip("\\").strip()
        for line in _instructions(dockerfile).splitlines()
    ]
    assert "clamav-daemon" in lines, "clamd nie jest instalowany"
    assert "clamav" not in lines, (
        "wrocil pakiet clamav - same narzedzia wiersza polecen, ktorych nie wolamy"
    )


def test_npm_is_removed_only_after_the_plugin_compiler_is_built(dockerfile):
    """Order is the whole correctness of the previous test. Removing npm
    before the layer that runs `npm install` breaks the build; removing it in
    the same RUN would work today and break the moment the layers are
    reordered."""
    built = _instructions(dockerfile)
    assert "npm install --no-fund" in built, "kompilator motywow nie jest budowany"
    assert "/usr/lib/node_modules/npm" in built, "npm nie jest usuwany"
    installs = built.index("npm install --no-fund")
    removes = built.index("/usr/lib/node_modules/npm")
    assert removes > installs, (
        "npm jest usuwany zanim zbuduje kompilator motywow"
    )


def test_nothing_in_the_runtime_reaches_for_npm():
    """The guard under the removal. Theme plugins are compiled by the Vite
    that npm already installed, invoked through node directly, so nothing
    should call npm once the image is built. A future line that does would
    fail at a user's site rather than here."""
    # A search over a tree that is not there finds nothing and reports a pass.
    # That is the failure mode this whole file exists to avoid, so say so.
    if not all(tree.is_dir() for tree in RUNTIME_TREES):
        pytest.skip("drzewo runtime nie jest obecne")

    candidates = [path for tree in RUNTIME_TREES for path in tree.rglob("*")]
    candidates += [path for path in RUNTIME_FILES if path.is_file()]

    offenders = []
    for path in candidates:
        if path.suffix not in (".py", ".mjs", ".js", ".sh"):
            continue
        if "tests" in path.parts or "node_modules" in path.parts:
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue
            if "npm " in stripped or '"npm"' in stripped or "'npm'" in stripped:
                offenders.append(f"{path.relative_to(ROOT)}:{number}")
    assert not offenders, "runtime wola npm, ktorego nie ma w obrazie: " + ", ".join(
        offenders
    )


def test_the_build_takes_the_security_updates_debian_has_published(dockerfile):
    """The base image is rebuilt on its own schedule and GD's is not, so
    between the two there is always a window where Debian has shipped a fix
    that the image does not carry. Today that window holds openssl."""
    assert "apt-get upgrade" in _instructions(dockerfile), (
        "build nie zabiera poprawek bezpieczenstwa wydanych po bazie"
    )
