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

Admins bypass everything, as they do everywhere else in this codebase.
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
    """

    is_admin: bool = False
    denied_game_ids: frozenset[int] = field(default_factory=frozenset)
    hidden_library_ids: frozenset[int] = field(default_factory=frozenset)
    default_library_hidden: bool = False

    @property
    def unrestricted(self) -> bool:
        """True when this user can see everything, so callers can skip the work."""
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
        if self.is_admin:
            return True
        if not getattr(game, "is_active", True):
            return False
        if game.id in self.denied_game_ids:
            return False

        # A game is visible when at least one library it sits in is visible.
        # Being in the default library counts as one such membership, because
        # that association is a column rather than a row.
        if getattr(game, "in_default_library", False) and not self.default_library_hidden:
            return True
        if member_library_ids:
            return bool(member_library_ids - self.hidden_library_ids)

        # No visible home: in the default library while that is hidden, or in
        # nothing at all. An orphan with no membership and no flag is only
        # reachable by id, so it stays hidden from a restricted user.
        return False

    def filter(self, games, memberships: dict[int, set[int]] | None = None) -> list:
        """The subset of `games` this user may see, order preserved."""
        if self.is_admin:
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

    if getattr(user, "role", None) == Role.ADMIN:
        return Visibility(is_admin=True)

    from handler.database.library_handler import LibraryHandler
    from handler.database.library_registry_handler import library_registry_handler

    denied = frozenset(await LibraryHandler().get_denied_game_ids_for_user(user.id))

    libs = await library_registry_handler.get_all()
    allowed = await library_registry_handler.get_user_access_ids(user.id)
    # The same rule user_can_access applies, one library at a time: a library
    # that is not restricted is open, and a restricted one needs an allowlist
    # row. Admins never reach here - they returned above.
    hidden = {
        lib.id for lib in libs
        if (lib.visibility or "public") == "restricted" and lib.id not in allowed
    }
    default_hidden = any(
        lib.slug == DEFAULT_LIBRARY_SLUG for lib in libs if lib.id in hidden
    )

    return Visibility(
        is_admin=False,
        denied_game_ids=denied,
        hidden_library_ids=frozenset(hidden),
        default_library_hidden=default_hidden,
    )


async def visible_game_or_none(user, game):
    """Convenience for the single-game case: the game, or None if hidden."""
    vis = await visibility_for(user)
    if vis.is_admin:
        return game
    members = (await membership_map([game.id])).get(game.id)
    return game if vis.allows(game, members) else None
