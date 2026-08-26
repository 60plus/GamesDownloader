"""Encryption for the secrets inside a plugin's stored configuration.

A plugin declares its settings in `config_schema`, and the fields it types as
`password` are exactly the ones that hold credentials: an archive.org password,
a GitHub token, an API key. Those values were written to `plugin_configs`
verbatim, so anyone holding a database dump held the credentials with it -
which is the same reach the app itself has, from a file that gets copied to
backup drives and pasted into bug reports.

They are stored encrypted now, with the app's own Fernet: the same key the
sensitive AppConfig rows use, derived from AUTH_SECRET_KEY, so no new secret
has to be managed and no new failure mode is introduced.

Each encrypted value carries a prefix, which is what makes this readable both
ways. A reader decrypts whatever is marked and leaves everything else alone, so
a configuration written before this existed still reads correctly, and a value
that is not a secret stays legible to anyone looking at the table.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Marks a value as encrypted. Versioned so a future change of scheme can be
# told apart from this one rather than guessed at.
ENC_PREFIX = "gd3:enc:v1:"


def secret_keys(config_schema: Any) -> set[str]:
    """The setting names a plugin declared as passwords."""
    if not isinstance(config_schema, dict):
        return set()
    return {
        key
        for key, spec in config_schema.items()
        if isinstance(spec, dict) and spec.get("type") == "password"
    }


def is_encrypted(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(ENC_PREFIX)


class CannotEncrypt(ValueError):
    """A secret could not be encrypted, so it must not be stored at all."""


def encrypt_secrets(config: Any, config_schema: Any, previous: Any = None) -> Any:
    """Return the config with its password fields encrypted, ready to store.

    Anything already encrypted is left as it is, so saving a form twice does
    not wrap a value in a second layer.

    Raises `CannotEncrypt` rather than storing a value it could not protect.
    The first version wrote an empty string in that case, reasoning that the
    admin would see a blank field and type the password again - but the save
    still reported success, so what actually happened was that a working
    credential was destroyed and nothing said so. A save that cannot be made
    safely has to fail.

    `previous` is the config as currently stored, and it exists for one narrow
    case that is otherwise unrecoverable. When the app's key is lost or
    changed, every secret reads back as empty; the admin then opens the form,
    sees blank password fields, changes something unrelated and saves - and the
    blank overwrites the ciphertext that the right key would still have opened.
    So an empty incoming password does not clear a stored value that cannot be
    decrypted. Clearing one that *can* be decrypted still works, because there
    the blank field is the admin's own doing.
    """
    if not isinstance(config, dict):
        return config
    keys = secret_keys(config_schema)
    if not keys:
        return config

    from handler.config.config_handler import _encrypt

    stored = previous if isinstance(previous, dict) else {}
    out = dict(config)
    for key in keys:
        value = out.get(key)
        if isinstance(value, str) and value and not is_encrypted(value):
            try:
                out[key] = ENC_PREFIX + _encrypt(value)
            except Exception as exc:
                raise CannotEncrypt(
                    f"the value of '{key}' cannot be stored safely"
                ) from exc
            continue
        if value in ("", None) and is_encrypted(stored.get(key)) and not _readable(stored[key]):
            # Not the admin clearing the field: the field was never shown to
            # them, because this installation cannot read it.
            out[key] = stored[key]
            logger.info(
                "Kept the unreadable stored value of '%s' rather than clearing "
                "it. It is still there if the original key comes back.", key,
            )
    return out


def _readable(value: Any) -> bool:
    """Whether an encrypted value opens with this installation's key."""
    if not is_encrypted(value):
        return False
    try:
        from handler.config.config_handler import _decrypt
        _decrypt(value[len(ENC_PREFIX):])
        return True
    except Exception:
        return False


def decrypt_secrets(config: Any) -> Any:
    """Return the config as the plugin should see it, secrets in the clear.

    Needs no schema: an encrypted value says so itself. A value that cannot be
    decrypted - the app's secret was changed, the row was copied from another
    installation - reads as unset, which sends the plugin down its "not
    configured yet" path instead of authenticating with a ciphertext.
    """
    if not isinstance(config, dict):
        return config
    if not any(is_encrypted(v) for v in config.values()):
        return config

    from handler.config.config_handler import _decrypt

    out = dict(config)
    for key, value in config.items():
        if not is_encrypted(value):
            continue
        try:
            out[key] = _decrypt(value[len(ENC_PREFIX):])
        except Exception:
            logger.warning(
                "Plugin setting '%s' could not be decrypted - treating it as unset",
                key,
            )
            out[key] = ""
    return out


def schema_for(plugin_id: str, stored_schema_json: Any) -> Any:
    """A plugin's config schema: from its manifest, or from the stored copy.

    The manifest on disk is authoritative - it is where the schema is declared,
    and a plugin dropped in by hand may have no stored copy at all. The copy in
    the row covers the other direction: a plugin whose files are unreadable at
    this moment still has its secrets recognised.
    """
    import json as _json
    from pathlib import Path

    from config import PLUGINS_PATH
    from handler.plugins.install_handler import read_manifest

    if plugin_id and "/" not in plugin_id and "\\" not in plugin_id and ".." not in plugin_id:
        manifest = read_manifest(Path(PLUGINS_PATH) / plugin_id)
        if manifest and manifest.get("config_schema") is not None:
            return manifest["config_schema"]
    if stored_schema_json:
        try:
            return _json.loads(stored_schema_json)
        except (TypeError, ValueError):
            return None
    return None


async def encrypt_stored_secrets(engine) -> list[str]:
    """Encrypt any plugin credential still sitting in the table in the clear.

    Runs at startup. Idempotent - an encrypted value is recognised as one - so
    it needs no guard flag and costs a single query on the boots where there is
    nothing to do.

    Three things about the shape of this, each of which it got wrong first:

    * **One transaction per row.** All of them shared a single transaction, so
      one row that could not be written rolled back every row that could, on
      that boot and on every boot after it, behind a single warning. The pass
      would never have finished and would have looked like it had.
    * **The manifests are read before anything is written.** Resolving a
      schema touches the filesystem, and doing that with a write transaction
      open meant a stalled mount could hold one open indefinitely.
    * **It says what it did, including nothing.** A row whose schema cannot be
      resolved is skipped, and a silent skip is indistinguishable from a
      successful pass - which is the wrong way round for a security fix.

    Returns the plugin ids it rewrote.
    """
    import json as _json

    from sqlalchemy import text

    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT plugin_id, config_json, config_schema_json FROM plugin_configs "
            "WHERE config_json IS NOT NULL"
        ))).all()

    # Filesystem work first, with nothing held open.
    pending: list[tuple[str, str]] = []
    unresolved: list[str] = []
    for plugin_id, config_raw, schema_raw in rows:
        try:
            config = _json.loads(config_raw)
        except (TypeError, ValueError):
            continue
        schema = schema_for(plugin_id, schema_raw)
        if schema is None:
            unresolved.append(plugin_id)
            continue
        if not has_plaintext_secret(config, schema):
            continue
        try:
            pending.append((plugin_id, _json.dumps(encrypt_secrets(config, schema))))
        except CannotEncrypt as exc:
            # Leave the plaintext where it is. It is readable, which is the
            # problem, but overwriting the only copy of a credential during an
            # unattended boot would be worse than the problem.
            logger.error(
                "Plugin '%s' has a credential that could not be encrypted and "
                "is still stored in the clear: %s", plugin_id, exc,
            )

    done: list[str] = []
    for plugin_id, encrypted in pending:
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text("UPDATE plugin_configs SET config_json = :cfg "
                         "WHERE plugin_id = :pid"),
                    {"cfg": encrypted, "pid": plugin_id},
                )
            done.append(plugin_id)
        except Exception as exc:
            logger.error(
                "Could not encrypt the stored credentials of plugin '%s', so "
                "they are still in the clear: %s", plugin_id, exc,
            )

    if unresolved:
        logger.warning(
            "Could not tell which settings of %s are credentials (no manifest "
            "on disk and no stored schema), so they were left as they are.",
            ", ".join(sorted(unresolved)),
        )
    return done


def has_plaintext_secret(config: Any, config_schema: Any) -> bool:
    """Whether a stored config still holds a secret in the clear.

    Used by the one-time migration, which has to tell a row that predates
    encryption from one that is already done.
    """
    if not isinstance(config, dict):
        return False
    return any(
        isinstance(config.get(key), str) and config[key] and not is_encrypted(config[key])
        for key in secret_keys(config_schema)
    )
