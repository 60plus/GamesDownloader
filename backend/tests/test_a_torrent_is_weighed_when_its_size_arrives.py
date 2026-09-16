"""A transfer nobody weighed is a quota nobody keeps.

Adding a torrent by FILE is weighed before anything moves: a .torrent carries
its own metadata, so the total is read from the bytes the caller uploaded and a
transfer that does not fit is refused on the spot.

Adding one by magnet is not, and the comment beside the file route says why: a
magnet link is a hash, the sizes arrive from peers minutes later, so there is
nothing to weigh at that moment. That much is right. What it left unsaid is that
"count it afterwards" was never implemented - nothing ever counted it - so the
URL route was a way round the limit entirely: paste a magnet, take as much as
you like.

An http(s) address used to go to the daemon as it was, on the reasoning that
the server fetching an address the caller chose would be a new hole. The 1.0.34
pre-release audit (finding #18) showed the hole was already there: Transmission
fetches the address itself, following redirects, with nothing between it and
the container's own network. So the route now fetches a .torrent address HERE,
through the network guard on every hop, and weighs those bytes like an upload.
Only a magnet is left for later.

The honest moment for a magnet is the one the comment already names: when the
size arrives. The seed monitor is polling these torrents anyway and `totalSize`
turns up there as soon as the metadata does. The download is charged to
`created_by_id`, which the row already carries.

WHAT HAPPENS AT THAT MOMENT CHANGED, on the owner's decision, after he watched
it work: a transfer that does not fit is now REFUSED and removed rather than
paused. Two things made the old shape wrong. It was not what he expected of a
limit, and a paused row drops out of the only set this monitor looks at, so the
single Resume button lifted the limit for that transfer for ever. What makes
removing safe is an interlock, not good intentions - see the last test here and
test_a_magnet_that_does_not_fit_is_turned_away.py, which measures it by ticking.
"""

from __future__ import annotations

import io
import pathlib
from types import SimpleNamespace

BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _monitor() -> str:
    return io.open(BACKEND / "handler" / "torrent" / "seed_monitor.py",
                   encoding="utf-8").read()



def _loop() -> str:
    """The body of `_check_downloads` ALONE.

    Slicing to the end of the file swept in the completion handler below it,
    which has its own emits and its own file handling - so an assertion about
    this loop passed or failed on code it was never about.
    """
    import re

    body = _monitor()
    at = body.index("async def _check_downloads(")
    nxt = re.search(r"\n(async )?def ", body[at + 10:])
    return body[at:at + 10 + nxt.start()] if nxt else body[at:]


def _router() -> str:
    return io.open(BACKEND / "endpoints" / "torrent" / "torrent_router.py",
                   encoding="utf-8").read()


def _function(source: str, name: str) -> str:
    """One top-level function of the router, up to the next decorator or def."""
    import re

    at = source.index(f"async def {name}(")
    nxt = re.search(r"\n(@|async def |def )", source[at + 10:])
    return source[at:at + 10 + nxt.start()] if nxt else source[at:]


def test_the_file_route_still_weighs_what_it_can():
    """The check that was already right. Losing it while adding the late one
    would trade an early refusal for a late one. The weighing moved into a
    helper when the address route started using it too."""
    source = _router()
    assert "_refuse_if_it_does_not_fit(" in _function(source, "add_torrent_file")
    assert "quota.fits(" in _function(source, "_refuse_if_it_does_not_fit")


def test_an_address_is_fetched_only_through_the_network_guard():
    """This test used to say the opposite: that the route must not fetch the
    address itself. The 1.0.34 audit (finding #18) turned that round. Handing
    the address to Transmission did not avoid a server-side fetch, it only made
    it one with no guard at all - libcurl following redirects into loopback and
    the link-local metadata range. So the address IS fetched here now, and what
    matters is that every hop of it goes through the guard. What the guard
    refuses, and that a magnet never reaches the fetch, is measured in
    test_a_torrent_address_cannot_reach_inside_the_server.py."""
    source = _router()
    assert "_fetch_torrent_file(" in _function(source, "add_torrent_url")
    assert "make_request_guard(" in _function(source, "_fetch_torrent_file"), (
        "adres .torrent pobierany bez oslony sieci - kazdy przekierowany skok "
        "moze trafic w 127.0.0.1 albo 169.254.169.254"
    )
    assert "_refuse_if_it_does_not_fit(" in _function(source, "add_torrent_url"), (
        "pobrany .torrent nie jest wazony przed dodaniem, choc jego rozmiar jest "
        "juz znany"
    )


def test_the_monitor_weighs_a_torrent_once_its_size_is_known():
    loop = _loop()
    assert "quota" in loop, (
        "nic nigdy nie liczy torrenta do limitu - magnet jest droga na obejscie "
        "limitu w calosci"
    )
    assert "totalSize" in loop, "waga brana skadinad niz z rozmiaru od peerow"


def test_it_charges_the_account_that_added_it():
    body = _monitor()
    assert "created_by_id" in body, (
        "monitor nie wie, czyj jest transfer, wiec nie ma czyjego limitu pytac"
    )


def test_a_torrent_that_does_not_fit_does_not_simply_carry_on():
    """The guarantee is unchanged; what fulfils it is not.

    This used to assert `pause_torrent` appears in the loop, because the rule
    then was "pause, never delete". The owner replaced that rule after watching
    it: he expected a transfer that does not fit to be turned away, not parked
    ("myslalem ze jak jest za duzy to poprostu go nie przyjmie"), and parking
    it had a worse property nobody had noticed - a paused row leaves the only
    set this monitor ever looks at, so one press of Resume lifted the limit for
    that transfer permanently.

    What the refusal actually does is measured, by running a tick, in
    test_a_magnet_that_does_not_fit_is_turned_away.py. All this one keeps is
    that the decision is still taken here, before the row is written as
    ordinary progress.
    """
    loop = _loop()
    at_refusal = loop.index("_refuse_over_quota(")
    at_progress = loop.index("_update_download(td.id, updates)")
    assert at_refusal < at_progress, (
        "transfer ponad limit jest zapisywany jako zwykly postep, zanim "
        "ktokolwiek zapyta o limit"
    )


def test_nothing_here_deletes_data_without_first_confirming_whose_it_is():
    """Refusing rather than parking makes `delete_data=True` reachable in this
    file for the first time, so the interlock that keeps it safe is worth a
    test of its own.

    The danger was named when the previous version was reverted:
    `transmission_id` is a number the daemon hands out and starts again from 1
    after a restart, so it can point at a torrent this row was never about -
    two rows on the live install already share id 1. `info_hash` is the
    content's own name; both queue routes wrote it and nothing had ever read it
    back.

    Structural on purpose. The behaviour of the deletion that exists is
    measured next door; what this guards against is a SECOND one added later by
    somebody who did not read this far.
    """
    import re as _re

    body = _monitor()
    deletions = [ln for ln in body.splitlines()
                 if "delete_data=True" in ln and not ln.strip().startswith("#")]
    assert len(deletions) == 1, (
        f"kasowanie danych w tym pliku zdarza sie {len(deletions)} razy - kazde "
        "musi byc osobno zabezpieczone hashem"
    )

    at = body.index("delete_data=True")
    start = body.rindex("\nasync def ", 0, at)
    after = _re.search(r"\n(async )?def ", body[at:])
    enclosing = body[start:at + after.start()] if after else body[start:]
    assert "_is_the_torrent_we_queued" in enclosing, (
        "kasowanie danych po numerze sesyjnym demona, bez potwierdzenia, ze to "
        "ten sam torrent - to droga do skasowania cudzych plikow po restarcie"
    )


def test_the_notice_goes_to_the_owner_and_not_to_everybody():
    loop = _loop()
    shouted = [ln.strip() for ln in loop.splitlines()
               if "sio.emit(" in ln and "room=" not in ln]
    assert not shouted, (
        "zdarzenie o limicie idzie rozgloszeniem do kazdego zalogowanego konta: "
        + "; ".join(shouted)
    )


def test_it_weighs_once_rather_than_on_every_tick():
    """`_over_quota` is three queries, and when a limit is in force two of them
    are aggregate sums - one over `roms`, whose `published_by` column arrived by
    an ALTER with no index behind it. The monitor wakes every ten seconds for
    every transfer, and the answer cannot change: `totalSize` is fixed once the
    metadata arrives.

    Weighing once is also the more careful reading. Asked again and again, the
    same transfer could be condemned later by an ordinary upload from the same
    account - legal when it started, refused halfway through."""
    from handler.torrent import seed_monitor as M

    fresh = SimpleNamespace(total_size=0)
    assert M._size_just_arrived(fresh, 5000) is True

    known = SimpleNamespace(total_size=5000)
    assert M._size_just_arrived(known, 5000) is False, (
        "ten sam torrent jest wazony na kazdym takcie, chociaz jego rozmiar sie "
        "nie zmienia"
    )


def test_a_magnet_with_no_size_yet_is_not_weighed():
    """Zero is "not known yet", not "empty". Every magnet looks like that on its
    first tick and refusing on it would refuse them all."""
    from handler.torrent import seed_monitor as M

    assert M._size_just_arrived(SimpleNamespace(total_size=0), 0) is False
    assert M._size_just_arrived(SimpleNamespace(total_size=None), 0) is False


def test_the_loop_asks_that_question_before_it_pays_for_the_answer():
    loop = _loop()
    assert "_size_just_arrived(" in loop, (
        "petla wola `_over_quota` bez sprawdzenia, czy jest po co"
    )
    assert loop.index("_size_just_arrived(") < loop.index("_over_quota("), (
        "tania odpowiedz zadawana PO drogiej"
    )


def test_a_torrent_of_unknown_size_is_left_alone():
    """The same caution the file route states: "no idea" is not "too big". A
    magnet has no size at all until the metadata arrives, and refusing on that
    would refuse every magnet at its first tick."""
    loop = _loop()
    charge = loop.index("quota")
    guard = loop[max(0, charge - 600):charge]
    assert "total_size" in guard or "totalSize" in guard, (
        "brak sprawdzenia, czy rozmiar jest juz znany"
    )
