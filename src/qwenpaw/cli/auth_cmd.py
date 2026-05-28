# -*- coding: utf-8 -*-
from __future__ import annotations

import secrets

import click

from ..app.auth import (
    _get_users,
    _hash_password,
    _load_auth_data,
    _save_auth_data,
)


@click.group("auth", help="Manage web authentication.")
def auth_group() -> None:
    """Manage web authentication."""


@auth_group.command("reset-password")
def reset_password_cmd() -> None:
    """Reset the password for the registered web user."""
    data = _load_auth_data()

    if data.get("_auth_load_error"):
        raise click.ClickException(
            "Failed to read auth data. Check auth.json for corruption.",
        )

    users = _get_users(data)
    if not users:
        click.echo("No registered user found. Nothing to reset.")
        return

    if len(users) > 1:
        click.echo(
            f"Multiple users registered ({len(users)}). "
            "Reset password via the web console account settings.",
        )
        return

    user = users[0]
    username = user.get("username", "<unknown>")
    click.echo(f"Resetting password for user: {username}")

    new_password = click.prompt(
        "New password",
        hide_input=True,
        confirmation_prompt=True,
    )

    if not new_password or not new_password.strip():
        raise click.ClickException("Password cannot be empty.")

    pw_hash, salt = _hash_password(new_password)
    data["user"]["password_hash"] = pw_hash
    data["user"]["password_salt"] = salt

    # Invalidate existing tokens by rotating jwt_secret
    data["jwt_secret"] = secrets.token_hex(32)

    _save_auth_data(data)
    click.echo(
        "✓ Password reset successfully. "
        "All existing sessions have been invalidated.",
    )
