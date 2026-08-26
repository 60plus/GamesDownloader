"""A plugin's credentials must not sit in the database in the clear.

Plugins declare their settings, and the fields they type as `password` hold
real credentials: PC Ports keeps a GitHub token there, RomDownloader an
archive.org password. Those were written to `plugin_configs` verbatim, so every
dump of that database carried them.

The tests that matter here look at what is actually stored, not at what a
helper returns, because a fix that encrypts on the way out and stores the
plaintext anyway would satisfy every round-trip test ever written.
"""

from __future__ import annotations

import json

import pytest

from plugins.config_crypto import (
    ENC_PREFIX,
    CannotEncrypt,
    decrypt_secrets,
    encrypt_secrets,
    has_plaintext_secret,
    is_encrypted,
    secret_keys,
)

PCPORTS_SCHEMA = {
    "catalog_repo": {"type": "string"},
    "github_token": {"type": "password"},
    "include_ai_ports": {"type": "boolean"},
}


# ── what ends up in the column ───────────────────────────────────────────────

def test_the_secret_is_not_recoverable_from_what_is_stored():
    stored = encrypt_secrets(
        {"catalog_repo": "a/b", "github_token": "ghp_realsecret"}, PCPORTS_SCHEMA
    )
    blob = json.dumps(stored)
    assert "ghp_realsecret" not in blob
    assert is_encrypted(stored["github_token"])


def test_everything_that_is_not_a_secret_stays_legible():
    stored = encrypt_secrets(
        {"catalog_repo": "a/b", "github_token": "ghp_x", "include_ai_ports": True},
        PCPORTS_SCHEMA,
    )
    assert stored["catalog_repo"] == "a/b"
    assert stored["include_ai_ports"] is True


def test_the_plugin_gets_its_secret_back():
    stored = encrypt_secrets({"github_token": "ghp_realsecret"}, PCPORTS_SCHEMA)
    assert decrypt_secrets(stored)["github_token"] == "ghp_realsecret"


def test_saving_twice_does_not_wrap_it_twice():
    once = encrypt_secrets({"github_token": "ghp_x"}, PCPORTS_SCHEMA)
    twice = encrypt_secrets(once, PCPORTS_SCHEMA)
    assert twice == once
    assert decrypt_secrets(twice)["github_token"] == "ghp_x"


def test_an_unset_password_stays_unset():
    """An empty field must read as empty, not as a token that decrypts to ''."""
    stored = encrypt_secrets({"github_token": ""}, PCPORTS_SCHEMA)
    assert stored["github_token"] == ""
    assert decrypt_secrets(stored)["github_token"] == ""


def test_a_config_written_before_encryption_existed_still_reads():
    legacy = {"catalog_repo": "a/b", "github_token": "ghp_old"}
    assert decrypt_secrets(legacy) == legacy


def test_a_value_this_installation_cannot_decrypt_reads_as_unset():
    """A row copied from another installation, or one whose AUTH_SECRET_KEY was
    changed. The plugin must take its "not configured" path rather than
    authenticate with a ciphertext."""
    out = decrypt_secrets({"github_token": ENC_PREFIX + "not-a-real-token"})
    assert out["github_token"] == ""


def test_a_plugin_with_no_password_fields_is_left_exactly_as_it_is():
    cfg = {"from_lang": "en", "to_lang": "pl"}
    schema = {"from_lang": {"type": "select"}, "to_lang": {"type": "select"}}
    assert encrypt_secrets(cfg, schema) == cfg
    assert decrypt_secrets(cfg) == cfg


def test_a_plugin_with_no_schema_at_all_is_left_alone():
    cfg = {"api_key": "sk-live"}
    assert encrypt_secrets(cfg, None) == cfg


def test_which_fields_count_as_secrets():
    assert secret_keys(PCPORTS_SCHEMA) == {"github_token"}
    assert secret_keys(None) == set()
    assert secret_keys("not-a-dict") == set()


def test_the_migration_can_tell_a_done_row_from_an_undone_one():
    plain = {"github_token": "ghp_old"}
    assert has_plaintext_secret(plain, PCPORTS_SCHEMA) is True
    assert has_plaintext_secret(encrypt_secrets(plain, PCPORTS_SCHEMA), PCPORTS_SCHEMA) is False
    assert has_plaintext_secret({"github_token": ""}, PCPORTS_SCHEMA) is False
    assert has_plaintext_secret({"catalog_repo": "a/b"}, PCPORTS_SCHEMA) is False


# ── when it cannot be done safely ────────────────────────────────────────────

# A lone surrogate survives json.loads and cannot be encoded to UTF-8, so this
# is what an unencryptable value actually looks like coming off the wire.
UNENCODABLE = "p\ud800ss"


def test_a_value_that_cannot_be_encrypted_is_refused_rather_than_dropped():
    """The first version stored an empty string here and let the save report
    success, so a working credential was destroyed and nothing said so."""
    with pytest.raises(CannotEncrypt):
        encrypt_secrets({"github_token": UNENCODABLE}, PCPORTS_SCHEMA)


@pytest.mark.asyncio
async def test_a_save_that_cannot_be_encrypted_changes_nothing(tmp_path, monkeypatch):
    from fastapi import HTTPException
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from endpoints.settings import plugins_router
    from models.plugin_config import PluginConfig

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(PluginConfig.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(plugins_router, "async_session_factory", maker)
    monkeypatch.setattr(plugins_router, "PLUGINS_PATH", str(tmp_path))

    good = json.dumps(encrypt_secrets({"github_token": "ghp_working"}, PCPORTS_SCHEMA))
    try:
        async with maker() as session:
            session.add(PluginConfig(
                plugin_id="gd3-pcports", name="PC Ports", version="1.0.1",
                author="a", plugin_type="catalog", config_json=good,
                config_schema_json=json.dumps(PCPORTS_SCHEMA),
            ))
            await session.commit()

        class _Req:
            state = type("S", (), {"scopes": set()})()

            async def json(self):
                return {"github_token": UNENCODABLE}

        with pytest.raises(HTTPException) as refused:
            await plugins_router.update_plugin_config.__wrapped__(_Req(), "gd3-pcports")
        assert refused.value.status_code == 400

        async with maker() as session:
            row = (await session.execute(
                select(PluginConfig).where(PluginConfig.plugin_id == "gd3-pcports")
            )).scalar_one()
        assert row.config_json == good, "the refused save destroyed the old credential"
    finally:
        await engine.dispose()


def test_a_blank_field_does_not_clear_a_secret_this_install_cannot_read():
    """The key was lost or changed, so every password field reads back empty.
    The admin then saves an unrelated toggle on that page, and the blank must
    not overwrite the ciphertext that the right key would still open."""
    unreadable = {"github_token": ENC_PREFIX + "gAAAAABmnot-ours"}
    out = encrypt_secrets({"github_token": ""}, PCPORTS_SCHEMA, previous=unreadable)
    assert out["github_token"] == unreadable["github_token"]


def test_a_blank_field_still_clears_a_secret_that_can_be_read():
    """Because there the empty field is the admin's own doing."""
    readable = encrypt_secrets({"github_token": "ghp_x"}, PCPORTS_SCHEMA)
    out = encrypt_secrets({"github_token": ""}, PCPORTS_SCHEMA, previous=readable)
    assert out["github_token"] == ""


def test_the_migration_leaves_a_credential_it_cannot_encrypt_alone():
    """Unattended, at boot, with nobody looking at a form. Storing an empty
    string there is not a prompt to re-enter it, it is deleting it."""
    with pytest.raises(CannotEncrypt):
        encrypt_secrets({"github_token": UNENCODABLE}, PCPORTS_SCHEMA)


# ── through the routes, against a real table ─────────────────────────────────

@pytest.mark.asyncio
async def test_saving_a_token_through_the_api_writes_ciphertext_to_the_table(
    tmp_path, monkeypatch
):
    """The half the unit tests above cannot see: whether the route actually
    stores the encrypted value, and whether reading it back returns the real
    one. A route that encrypted a copy and wrote the original would pass every
    test in the first half of this file."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from endpoints.settings import plugins_router
    from models.plugin_config import PluginConfig

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(PluginConfig.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(plugins_router, "async_session_factory", maker)
    # No plugin on disk, so the schema comes from the stored copy.
    monkeypatch.setattr(plugins_router, "PLUGINS_PATH", str(tmp_path))

    try:
        async with maker() as session:
            session.add(PluginConfig(
                plugin_id="gd3-pcports", name="PC Ports", version="1.0.1",
                author="a", plugin_type="catalog",
                config_schema_json=json.dumps(PCPORTS_SCHEMA),
            ))
            await session.commit()

        class _Req:
            state = type("S", (), {"scopes": set()})()

            async def json(self):
                return {"catalog_repo": "a/b", "github_token": "ghp_realsecret"}

        await plugins_router.update_plugin_config.__wrapped__(_Req(), "gd3-pcports")

        async with maker() as session:
            row = (await session.execute(
                select(PluginConfig).where(PluginConfig.plugin_id == "gd3-pcports")
            )).scalar_one()
            assert "ghp_realsecret" not in row.config_json, "the token was stored in the clear"
            assert json.loads(row.config_json)["catalog_repo"] == "a/b"

        # An admin reading it back gets the real token, not the ciphertext.
        from handler.auth.scopes import Scope

        class _AdminReq:
            state = type("S", (), {"scopes": {Scope.PLUGINS_WRITE}})()

        out = await plugins_router.get_plugin_config.__wrapped__(
            _AdminReq(), "gd3-pcports"
        )
        assert out["config"]["github_token"] == "ghp_realsecret"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_the_startup_pass_encrypts_a_row_saved_by_an_older_version(tmp_path, monkeypatch):
    """Without this, a token entered before the update stays in the clear until
    somebody happens to re-save that plugin's form, which nobody does."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import StaticPool

    from plugins import config_crypto

    monkeypatch.setattr("config.PLUGINS_PATH", str(tmp_path), raising=False)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "CREATE TABLE plugin_configs (plugin_id TEXT, config_json TEXT, "
                "config_schema_json TEXT)"))
            await conn.execute(
                text("INSERT INTO plugin_configs VALUES (:pid, :cfg, :sch)"),
                {"pid": "gd3-pcports",
                 "cfg": json.dumps({"catalog_repo": "a/b", "github_token": "ghp_old"}),
                 "sch": json.dumps(PCPORTS_SCHEMA)},
            )

        assert await config_crypto.encrypt_stored_secrets(engine) == ["gd3-pcports"]

        async with engine.begin() as conn:
            stored = (await conn.execute(
                text("SELECT config_json FROM plugin_configs"))).scalar_one()
        assert "ghp_old" not in stored
        assert decrypt_secrets(json.loads(stored))["github_token"] == "ghp_old"

        # Second boot: nothing left to do, and nothing double-wrapped.
        assert await config_crypto.encrypt_stored_secrets(engine) == []
        async with engine.begin() as conn:
            again = (await conn.execute(
                text("SELECT config_json FROM plugin_configs"))).scalar_one()
        assert again == stored
    finally:
        await engine.dispose()


def test_the_helper_plugins_actually_call_returns_the_real_secret(monkeypatch):
    """`get_plugin_config` is how a plugin reads its own settings, and it goes
    straight to the column with its own SQL. If it stopped handing back usable
    credentials, every plugin that authenticates would break at once."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import StaticPool

    from plugins import manager

    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE plugin_configs (plugin_id TEXT, config_json TEXT)"))
        conn.execute(
            text("INSERT INTO plugin_configs VALUES (:pid, :cfg)"),
            {"pid": "gd3-pcports",
             "cfg": json.dumps(encrypt_secrets(
                 {"catalog_repo": "a/b", "github_token": "ghp_realsecret"},
                 PCPORTS_SCHEMA))},
        )
    monkeypatch.setattr(manager, "_sync_engine", lambda: engine)
    try:
        cfg = manager.get_plugin_config("gd3-pcports")
        assert cfg["github_token"] == "ghp_realsecret"
        assert cfg["catalog_repo"] == "a/b"
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_a_plain_user_still_never_sees_the_field_at_all(tmp_path, monkeypatch):
    """Encryption is at rest. The existing rule - that only an admin sees a
    password field over the API - has to keep holding on top of it."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from endpoints.settings import plugins_router
    from models.plugin_config import PluginConfig

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(PluginConfig.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(plugins_router, "async_session_factory", maker)

    try:
        async with maker() as session:
            session.add(PluginConfig(
                plugin_id="gd3-pcports", name="PC Ports", version="1.0.1",
                author="a", plugin_type="catalog",
                config_json=json.dumps(
                    encrypt_secrets({"catalog_repo": "a/b", "github_token": "ghp_x"},
                                    PCPORTS_SCHEMA)),
                config_schema_json=json.dumps(PCPORTS_SCHEMA),
            ))
            await session.commit()

        class _PlainReq:
            state = type("S", (), {"scopes": set()})()

        out = await plugins_router.get_plugin_config.__wrapped__(_PlainReq(), "gd3-pcports")
        assert "github_token" not in out["config"]
        assert out["config"]["catalog_repo"] == "a/b"
    finally:
        await engine.dispose()
