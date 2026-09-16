"""A plugin's API key, hidden until somebody asks to see it.

Reported by the owner on 2026-09-10, the same day his TheGamesDB key leaked
through a probe of mine: "ukryj tez klucz w ustawieniach pluginu pod *** i daj
ikone oka zeby zobaczyc bo teraz widac odrazu jak sie wejdzie."

>>> THE PLUGIN ALREADY SAID SO AND THE SCREEN IGNORED IT. `plugin.json` declares
the field as `"type": "password"`, and TheGamesDB has done so since v1.0.1. The
settings screen has branches for boolean, select and number, and everything else
- password included - falls through to a plain `type="text"`. So the declaration
was correct, honoured nowhere, and the key sat in clear on an ordinary screen
that an administrator leaves open while sharing it, screenshotting it or being
watched.

>>> WHY HERE AND NOT ON THE OTHER SECRET FIELDS. Measured before choosing: the
SMTP password, the Transmission password and the four SSO client secrets are all
`type="password"` already, and all of them are write-only - the screen shows a
placeholder and the server never sends the stored value back. This one is
different in kind: the value really does travel to the browser, because a plugin
config round-trips. An eye belongs where there is something to reveal.
"""

from __future__ import annotations

import io
import json
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
FRONTEND = BACKEND.parent / "frontend"
SCREEN = FRONTEND / "src" / "views" / "settings" / "SettingsPlugins.vue"


def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        pytest.skip("frontend tree not present")
    return io.open(path, encoding="utf-8").read()


def _config_block(body: str) -> str:
    """The rows the plugin config panel draws, and nothing else."""
    at = body.index('v-for="(schema, key) in p.config_schema"')
    return body[at:body.index("sp-config-actions", at)]


def test_a_password_field_is_not_drawn_as_plain_text():
    """Asked about the BRANCH, because the bug is precisely that there was no
    branch: `password` fell through to the same `type="text"` that draws a
    folder name."""
    rows = _config_block(_read(SCREEN))
    assert "schema.type === 'password'" in rows, (
        "ekran nie ma galezi dla pola typu password, wiec klucz API rysuje sie "
        "jak zwykly tekst - a wtyczka deklaruje `password` od wersji 1.0.1"
    )


def test_the_field_starts_hidden():
    """Hidden by default is the whole request: it was visible the moment the
    panel opened."""
    rows = _config_block(_read(SCREEN))
    at = rows.index("schema.type === 'password'")
    field = rows[at:at + 700]
    assert ":type=" in field, (
        "typ pola jest staly, wiec albo zawsze widac, albo nigdy nie da sie "
        "zobaczyc"
    )
    assert "'password'" in field and "'text'" in field, (
        "pole nie przelacza sie miedzy ukryciem a pokazaniem"
    )


def test_there_is_something_to_click():
    rows = _config_block(_read(SCREEN))
    assert "toggleSecret(" in rows, "brak przycisku odslaniajacego"
    assert "<svg" in rows, "przycisk nie ma ikony oka"


def test_revealing_one_key_does_not_reveal_another():
    """A plugin may declare more than one secret, and two plugins certainly do.
    A single shared flag would uncover all of them at once, which is a worse
    version of the bug being fixed."""
    body = _read(SCREEN)

    # Asked about the KEY the flag is stored under, and about it being built
    # from both arguments. The first version looked for the words `plugin_id`
    # or `pid` in the function and failed against a parameter spelled
    # `pluginId` - matching letters instead of the instruction, again.
    at = body.index("function secretKey")
    maker = body[at:body.index("\n}", at)]
    args = maker[maker.index("(") + 1:maker.index(")")]
    names = [a.split(":")[0].strip() for a in args.split(",")]
    assert len(names) == 2, f"klucz stanu powstaje z {len(names)} rzeczy zamiast dwoch"
    for name in names:
        assert name in maker[maker.index(")"):], (
            f"argument `{name}` nie trafia do klucza, wiec dwa pola dziela jedna flage"
        )

    at = body.index("function toggleSecret")
    fn = body[at:body.index("\n}", at)]
    assert "secretKey(" in fn, (
        "przelacznik nie uzywa wspolnego klucza, wiec da sie go rozjechac z odczytem"
    )


def test_the_other_field_types_are_untouched():
    """THE LEGAL CASE. Four kinds of field share this loop; a new branch in the
    middle of a v-if chain is exactly where one of the others quietly stops
    being reachable."""
    rows = _config_block(_read(SCREEN))
    for kind in ("'boolean'", "'select'", "'number'"):
        assert kind in rows, f"galaz {kind} zniknela z panelu ustawien wtyczki"
    assert 'v-else' in rows, "zniknela galaz domyslna dla zwyklego tekstu"


@pytest.mark.parametrize("key", ["plugins.reveal_secret", "plugins.hide_secret"])
def test_every_language_names_the_button(key):
    en = FRONTEND / "src" / "i18n" / "en.json"
    if not en.is_file():
        pytest.skip("frontend tree not present")
    langs = sorted((FRONTEND / "public" / "i18n").glob("*.json"))
    assert len(langs) == 7
    for path in [en, *langs]:
        d = json.load(io.open(path, encoding="utf-8"))
        assert key in d, f"{path.name}: brak {key}"
