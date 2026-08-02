"""Discord-touching role helpers shared by the interview and approval flows."""

import discord

import config


def configured_roles(
    guild: discord.Guild,
) -> tuple[dict[str, discord.Role], list[str]]:
    """Map every configured role key to its guild role.

    Returns (roles_by_key, missing_keys), where missing_keys are keys whose
    role could not be found on the server.
    """
    roles_by_key = {key: guild.get_role(role_id) for key, role_id in config.CONFIG.role_ids.items()}
    missing = [key for key, role in roles_by_key.items() if role is None]
    return roles_by_key, missing


def role_diff(
    member: discord.Member,
    target: set[str],
    roles_by_key: dict[str, discord.Role],
) -> tuple[set[str], set[str]]:
    """Diff a member's current managed roles against the target set.

    Returns (to_add, to_remove) — only keys in ``roles_by_key`` count as
    removable, so the bot never touches roles it doesn't manage.
    """
    current = {key for key, role in roles_by_key.items() if role in member.roles}
    return target - current, current - target
