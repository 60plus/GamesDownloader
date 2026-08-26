"""Plugin config secrets stay with the people who can manage plugins.

Plugin config holds credentials - the PC Ports catalogue keeps a GitHub token
in it. They are encrypted at rest (see test_plugin_config_encryption.py) and
decrypted before the API answers, so this layer is what decides who receives
them. PLUGINS_READ is a base-user scope (the plugin list
feeds themes and the translate button), so `GET /api/plugins` and
`/{id}/config` reach ordinary users; the secret VALUES must not. These pin the
rule: an admin (PLUGINS_WRITE) sees everything, a plain reader loses every field
the schema types as "password", and a plugin whose schema we can't read is
withheld whole.
"""
from __future__ import annotations

from endpoints.settings.plugins_router import _redact_config


PCPORTS_SCHEMA = {
    "catalog_repo": {"type": "string"},
    "github_token": {"type": "password"},
    "include_ai_ports": {"type": "boolean"},
}

# The translate button is the one non-admin reader of a plugin config; its two
# fields are plain selects, so nothing should be stripped for a plain user.
TRANSLATOR_SCHEMA = {
    "from_lang": {"type": "select"},
    "to_lang": {"type": "select"},
}


def test_admin_sees_the_secret():
    cfg = {"catalog_repo": "a/b", "github_token": "ghp_secret"}
    assert _redact_config(cfg, PCPORTS_SCHEMA, is_admin=True) == cfg


def test_plain_reader_loses_only_the_password_field():
    cfg = {"catalog_repo": "a/b", "github_token": "ghp_secret", "include_ai_ports": True}
    out = _redact_config(cfg, PCPORTS_SCHEMA, is_admin=False)
    assert out == {"catalog_repo": "a/b", "include_ai_ports": True}
    assert "github_token" not in out


def test_translate_button_config_survives_for_plain_reader():
    cfg = {"from_lang": "en", "to_lang": "pl"}
    assert _redact_config(cfg, TRANSLATOR_SCHEMA, is_admin=False) == cfg


def test_schemaless_plugin_is_withheld_whole():
    """No schema means we cannot tell which values are safe - hide all of them."""
    cfg = {"api_key": "sk-live-xyz", "region": "eu"}
    assert _redact_config(cfg, None, is_admin=False) is None
    assert _redact_config(cfg, "not-a-dict", is_admin=False) is None


def test_none_and_nondict_config_pass_through_as_none():
    assert _redact_config(None, PCPORTS_SCHEMA, is_admin=False) is None
    assert _redact_config(None, PCPORTS_SCHEMA, is_admin=True) is None
    assert _redact_config(["not", "a", "dict"], PCPORTS_SCHEMA, is_admin=False) is None


def test_admin_flag_bypasses_even_without_schema():
    cfg = {"api_key": "sk-live-xyz"}
    assert _redact_config(cfg, None, is_admin=True) == cfg
