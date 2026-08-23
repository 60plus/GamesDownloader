"""One rule about who may see a game, asked everywhere.

There used to be two rules in two places. The per-game deny list was checked by
the game detail route and the file listing. The restricted-library rule was
checked by the browse listing and by nothing else. A user kept off a restricted
library therefore saw an empty listing and could still fetch any game in it by
id, list its files, mint a download token and find the titles through search.

These tests are about the decision itself, so they build plain objects rather
than touching the database: the point is that `allows` says the same thing no
matter which route is asking.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from handler.library.visibility import Visibility


def gra(id: int, *, aktywna: bool = True, domyslna: bool = False):
    return SimpleNamespace(id=id, is_active=aktywna, in_default_library=domyslna)


# ── Admin ─────────────────────────────────────────────────────────────────────

def test_admin_widzi_wszystko():
    vis = Visibility(is_admin=True)
    assert vis.unrestricted
    # Denied, in a hidden library, inactive: an admin still sees it.
    assert vis.allows(gra(1, aktywna=False), {99})


# ── Lista zakazow per gra ─────────────────────────────────────────────────────

def test_zakazana_gra_jest_niewidoczna():
    vis = Visibility(denied_game_ids=frozenset({7}))
    assert not vis.allows(gra(7, domyslna=True))
    assert vis.allows(gra(8, domyslna=True))


def test_nieaktywna_gra_jest_niewidoczna():
    assert not Visibility().allows(gra(1, aktywna=False, domyslna=True))


# ── Ograniczone biblioteki ────────────────────────────────────────────────────

def test_gra_wylacznie_w_ukrytej_bibliotece_jest_niewidoczna():
    """The hole this module was written for."""
    vis = Visibility(hidden_library_ids=frozenset({5}))
    assert not vis.allows(gra(1), {5})


def test_gra_w_ukrytej_I_widocznej_bibliotece_jest_widoczna():
    """One visible home is enough. A game can sit in several libraries."""
    vis = Visibility(hidden_library_ids=frozenset({5}))
    assert vis.allows(gra(1), {5, 6})


def test_flaga_biblioteki_domyslnej_wystarcza():
    """Membership of the default library is a column, not a row."""
    vis = Visibility(hidden_library_ids=frozenset({5}))
    assert vis.allows(gra(1, domyslna=True), {5})


def test_ukryta_biblioteka_domyslna_nie_wystarcza():
    """The default library can itself be made restricted."""
    vis = Visibility(hidden_library_ids=frozenset({1}), default_library_hidden=True)
    assert not vis.allows(gra(1, domyslna=True), {1})


def test_sierota_bez_przynaleznosci_jest_ukryta_przed_ograniczonym():
    """Reachable only by id, so it does not get the benefit of the doubt."""
    vis = Visibility(hidden_library_ids=frozenset({5}))
    assert not vis.allows(gra(1), None)
    assert not vis.allows(gra(1), set())


def test_nieznana_przynaleznosc_nie_odblokowuje_gry():
    """Passing None means "I did not look", which must not read as "allowed"."""
    vis = Visibility(hidden_library_ids=frozenset({5}))
    assert not vis.allows(gra(1))


# ── Uzytkownik bez ograniczen ─────────────────────────────────────────────────

def test_uzytkownik_bez_zakazow_widzi_zwykla_gre():
    vis = Visibility()
    assert vis.unrestricted
    assert vis.allows(gra(1, domyslna=True))
    assert vis.allows(gra(2), {3})


def test_brak_uzytkownika_nie_widzi_niczego():
    """A missing user should never have reached the check, but if it does the
    answer is no, not yes."""
    vis = Visibility(default_library_hidden=True)
    assert not vis.unrestricted
    assert not vis.allows(gra(1, domyslna=True))
    assert not vis.allows(gra(1), set())


# ── Filtrowanie list ──────────────────────────────────────────────────────────

def test_filtr_zachowuje_kolejnosc_i_wycina_ukryte():
    vis = Visibility(denied_game_ids=frozenset({2}), hidden_library_ids=frozenset({9}))
    gry = [gra(1, domyslna=True), gra(2, domyslna=True), gra(3), gra(4)]
    czlonkostwa = {3: {9}, 4: {9, 10}}
    widoczne = [g.id for g in vis.filter(gry, czlonkostwa)]
    assert widoczne == [1, 4]


def test_filtr_dla_admina_niczego_nie_rusza():
    gry = [gra(1), gra(2, aktywna=False)]
    assert Visibility(is_admin=True).filter(gry) == gry


@pytest.mark.parametrize("pole,wartosc", [
    ("denied_game_ids", frozenset({1})),
    ("hidden_library_ids", frozenset({1})),
    ("default_library_hidden", True),
])
def test_kazde_ograniczenie_znosi_skrot_unrestricted(pole, wartosc):
    """`unrestricted` is a fast path callers use to skip the membership query,
    so it must never be True while a restriction is in force."""
    assert not Visibility(**{pole: wartosc}).unrestricted


# ── Resolving it: which libraries are hidden, and at what cost ────────────────
#
# `visibility_for` runs on the single-game route, the file listing, the
# download-ticket route and search - the ones a page issues dozens of. It used
# to ask the registry per library through `user_can_access`, which is decorated
# `@begin_session` and so took a connection out of the twenty-slot pool on
# every iteration, including for public libraries where it answers without
# querying anything. These pin both halves: the rule is unchanged, and the
# allowlist is fetched once.

def biblioteka(id: int, slug: str, widocznosc: str = "public"):
    return SimpleNamespace(id=id, slug=slug, visibility=widocznosc)


class RejestrAtrapa:
    """Stands in for library_registry_handler, and counts what was asked."""

    def __init__(self, biblioteki, dozwolone):
        self._biblioteki = biblioteki
        self._dozwolone = dozwolone
        self.zapytania = 0

    async def get_all(self):
        self.zapytania += 1
        return self._biblioteki

    async def get_user_access_ids(self, user_id):
        self.zapytania += 1
        return self._dozwolone

    async def user_can_access(self, user, lib):
        raise AssertionError("per-library query: this is the cost being removed")


async def rozwiaz(monkeypatch, biblioteki, dozwolone, *, rola="user"):
    import handler.library.visibility as modul
    from handler.database import library_registry_handler as rejestr_modul

    rejestr = RejestrAtrapa(biblioteki, dozwolone)
    monkeypatch.setattr(rejestr_modul, "library_registry_handler", rejestr)

    class HandlerAtrapa:
        async def get_denied_game_ids_for_user(self, user_id):
            return []

    from handler.database import library_handler as lh_modul
    monkeypatch.setattr(lh_modul, "LibraryHandler", HandlerAtrapa)

    from models.user import Role
    user = SimpleNamespace(id=7, role=Role.ADMIN if rola == "admin" else Role.USER)
    return await modul.visibility_for(user), rejestr


async def test_publiczna_biblioteka_jest_widoczna_bez_wiersza_w_allowliscie(monkeypatch):
    vis, _ = await rozwiaz(monkeypatch, [biblioteka(1, "games")], set())
    assert vis.hidden_library_ids == frozenset()
    assert not vis.default_library_hidden


async def test_ograniczona_biblioteka_bez_wiersza_jest_ukryta(monkeypatch):
    vis, _ = await rozwiaz(
        monkeypatch, [biblioteka(4, "prywatna", "restricted")], set()
    )
    assert vis.hidden_library_ids == frozenset({4})


async def test_ograniczona_biblioteka_z_wierszem_jest_widoczna(monkeypatch):
    vis, _ = await rozwiaz(
        monkeypatch, [biblioteka(4, "prywatna", "restricted")], {4}
    )
    assert vis.hidden_library_ids == frozenset()


async def test_ukryta_biblioteka_domyslna_zapala_flage(monkeypatch):
    from handler.library.visibility import DEFAULT_LIBRARY_SLUG
    vis, _ = await rozwiaz(
        monkeypatch, [biblioteka(1, DEFAULT_LIBRARY_SLUG, "restricted")], set()
    )
    assert vis.default_library_hidden


async def test_brak_widocznosci_liczy_sie_jak_publiczna(monkeypatch):
    """An older row can have NULL there; NULL has always meant open."""
    vis, _ = await rozwiaz(monkeypatch, [biblioteka(9, "stara", None)], set())
    assert vis.hidden_library_ids == frozenset()


async def test_koszt_nie_rosnie_z_liczba_bibliotek(monkeypatch):
    """Two registry queries whether there are two libraries or twenty."""
    duzo = [biblioteka(i, f"lib{i}", "restricted" if i % 2 else "public")
            for i in range(1, 21)]
    vis, rejestr = await rozwiaz(monkeypatch, duzo, {3})
    assert rejestr.zapytania == 2
    assert vis.hidden_library_ids == frozenset({5, 7, 9, 11, 13, 15, 17, 19, 1})


async def test_admin_nie_pyta_rejestru_w_ogole(monkeypatch):
    vis, rejestr = await rozwiaz(
        monkeypatch, [biblioteka(4, "prywatna", "restricted")], set(), rola="admin"
    )
    assert vis.is_admin
    assert vis.unrestricted
    assert rejestr.zapytania == 0
