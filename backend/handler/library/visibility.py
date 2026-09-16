"""Who may see which game, decided once.

There were two separate rules about hiding a game from somebody, written in
different places, and only one of them was ever asked.

The per-game deny list lived in `_check_user_can_access` and was consulted by
the game detail route and the file listing. The restricted-library rule lived
in `list_library_games` and was consulted by nothing else. So a user kept off a
restricted library got an empty browse listing and was satisfied, while
`GET /library/games/412`, its file list, a download token and the global search
all answered normally. Game ids are sequential, so the shelf was enumerable.

This module holds both rules together. Build a `Visibility` once per request and
ask it about a game, or hand it a list and let it filter. Nothing else should be
deciding this.

Admins bypass everything here EXCEPT one thing: a library that is switched
off is closed to them as well. That is the owner's rule in his own words -
off is off, no difference between an administrator, a user or anybody else -
and it is the only place in this codebase where the bypass does not apply.
The switch is flipped back from Settings > Libraries, which reads
/libraries/all and does not come through here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select

from handler.database.session import async_session_factory

DEFAULT_LIBRARY_SLUG = "games"


@dataclass(frozen=True)
class Visibility:
    """One user's view of the library, resolved.

    `hidden_library_ids` are restricted libraries the user is not on.
    `default_library_hidden` covers the case where the default library itself
    has been made restricted, which is allowed and would otherwise be missed:
    games sitting in it carry a flag rather than a membership row.

    `closed_library_ids` are libraries that are switched OFF, and they are the
    one thing here an administrator does not bypass. The settings screen says
    disabling a library hides it "for everyone", and the owner was explicit
    about what everyone means. `default_library_closed` is the same case for the
    default library, for the same reason as its restricted twin above.
    """

    is_admin: bool = False
    denied_game_ids: frozenset[int] = field(default_factory=frozenset)
    hidden_library_ids: frozenset[int] = field(default_factory=frozenset)
    default_library_hidden: bool = False
    closed_library_ids: frozenset[int] = field(default_factory=frozenset)
    default_library_closed: bool = False

    @property
    def unrestricted(self) -> bool:
        """True when this user can see everything, so callers can skip the work."""
        if self.closed_library_ids or self.default_library_closed:
            return False
        return self.is_admin or not (
            self.denied_game_ids or self.hidden_library_ids or self.default_library_hidden
        )

    def allows(self, game, member_library_ids: set[int] | None = None) -> bool:
        """May this user see this game?

        `member_library_ids` is the set of libraries the game belongs to. Pass
        it when you already have it (see `membership_map`); leaving it None
        means "unknown", and then only the default-library flag can vouch for
        the game, which is the conservative reading.
        """
        # A switched-off library is closed to everybody, so this is asked before
        # the administrator bypass rather than after it. Every other rule below
        # keeps its bypass; this one is about the switch, not about permission.
        in_default = bool(getattr(game, "in_default_library", False))
        reachable_when_closed = (
            (in_default and not self.default_library_closed)
            or bool((member_library_ids or set()) - self.closed_library_ids)
        )
        if (self.closed_library_ids or self.default_library_closed) and not reachable_when_closed:
            return False

        if self.is_admin:
            return True
        if not getattr(game, "is_active", True):
            return False
        if game.id in self.denied_game_ids:
            return False

        # A game is visible when at least one library it sits in is visible.
        # Being in the default library counts as one such membership, because
        # that association is a column rather than a row.
        if in_default and not self.default_library_hidden:
            return True
        if member_library_ids:
            return bool(member_library_ids - self.hidden_library_ids)

        # No visible home: in the default library while that is hidden, or in
        # nothing at all. An orphan with no membership and no flag is only
        # reachable by id, so it stays hidden from a restricted user.
        return False

    def filter(self, games, memberships: dict[int, set[int]] | None = None) -> list:
        """The subset of `games` this user may see, order preserved.

        Only an administrator skips the per-game pass, and only while nothing is
        switched off. `unrestricted` is not enough for anybody else: it means
        "no deny list and no hidden libraries", and `allows` ALSO drops a game
        that is not active. Short-circuiting on it handed an ordinary account
        every unpublished game in whatever list it was given - which today no
        caller does, because both guard themselves, and tomorrow is one new
        caller trusting what this module says about itself.
        """
        if self.is_admin and not (self.closed_library_ids or self.default_library_closed):
            return list(games)
        memberships = memberships or {}
        return [g for g in games if self.allows(g, memberships.get(g.id))]


async def membership_map(game_ids) -> dict[int, set[int]]:
    """Which libraries each of these games belongs to, in one query."""
    ids = [int(i) for i in game_ids]
    if not ids:
        return {}
    from models.library import LibraryMembership

    out: dict[int, set[int]] = {}
    async with async_session_factory() as s:
        rows = await s.execute(
            select(LibraryMembership.library_game_id, LibraryMembership.library_id)
            .where(LibraryMembership.library_game_id.in_(ids))
        )
        for game_id, library_id in rows.all():
            out.setdefault(game_id, set()).add(library_id)
    return out


async def visibility_for(user) -> Visibility:
    """Resolve what this user may see. Three queries, or none for an admin.

    It used to be three plus one per library, because the loop called
    `user_can_access`, which is decorated `@begin_session` and so took a
    connection out of the twenty-slot pool on every iteration - even for a
    public library, where it answers without querying anything. This runs on
    the single-game route, the file list, the download-ticket route and search,
    so a handful of libraries meant a handful of pool checkouts on requests
    that a page issues dozens of. The allowlist is one query; the rule it feeds
    is the same rule, evaluated in Python.
    """
    from models.user import Role

    if user is None:
        # No user means no route should have got this far, but returning a
        # deny-everything view is safer than a permissive default.
        return Visibility(is_admin=False, default_library_hidden=True)

    from handler.database.library_handler import LibraryHandler
    from handler.database.library_registry_handler import library_registry_handler

    is_admin = getattr(user, "role", None) == Role.ADMIN

    # An admin used to return here with a bypass-everything view and no queries
    # at all. One query now, because the switch binds them too and there is no
    # way to know which libraries are off without asking. The rest of the work -
    # the deny list and the allowlist - is still skipped for them.
    libs = await library_registry_handler.get_all()
    closed = frozenset(lib.id for lib in libs if not lib.enabled)
    default_closed = any(
        lib.slug == DEFAULT_LIBRARY_SLUG for lib in libs if lib.id in closed
    )
    if is_admin:
        return Visibility(is_admin=True, closed_library_ids=closed,
                          default_library_closed=default_closed)

    denied = frozenset(await LibraryHandler().get_denied_game_ids_for_user(user.id))
    allowed = await library_registry_handler.get_user_access_ids(user.id)
    # The same rule user_can_access applies, one library at a time: a library
    # that is switched off is closed, one that is not restricted is open, and a
    # restricted one needs an allowlist row. Admins never reach here - they
    # returned above.
    #
    # The two have to give the same answer or this module's own header comes
    # true again: a shelf somebody is kept out of, whose games they can still
    # fetch one at a time by an id that is sequential.
    hidden = {
        lib.id for lib in libs
        if not lib.enabled
        or ((lib.visibility or "public") == "restricted" and lib.id not in allowed)
    }
    default_hidden = any(
        lib.slug == DEFAULT_LIBRARY_SLUG for lib in libs if lib.id in hidden
    )

    return Visibility(
        is_admin=False,
        denied_game_ids=denied,
        hidden_library_ids=frozenset(hidden),
        default_library_hidden=default_hidden,
        closed_library_ids=closed,
        default_library_closed=default_closed,
    )


async def visible_game_or_none(user, game):
    """Convenience for the single-game case: the game, or None if hidden."""
    vis = await visibility_for(user)
    if vis.is_admin and not (vis.closed_library_ids or vis.default_library_closed):
        return game
    members = (await membership_map([game.id])).get(game.id)
    return game if vis.allows(game, members) else None
