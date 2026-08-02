"""Permission and guild-scope guards for slash commands.

Used both as ``app_commands.check`` decorators on commands and as
plain functions inside component handlers (buttons/menus don't go through
the command tree, so they call :func:`is_maintainer` directly).
"""

from __future__ import annotations

import discord

import config


class GuardError(discord.app_commands.CheckFailure):
    """Raised when a guard rejects an interaction, with a user-facing message."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def is_maintainer(interaction: discord.Interaction) -> bool:
    """Guild owner or someone holding the Maintainer role."""
    user = interaction.user
    if not isinstance(user, discord.Member):
        return False
    guild = interaction.guild
    if guild is None:
        return False
    if guild.owner is not None and user.id == guild.owner.id:
        return True
    return any(role.id == config.CONFIG.maintainer_role_id for role in user.roles)


def same_guild(interaction: discord.Interaction) -> bool:
    """Whether the interaction happened in the configured server."""
    return interaction.guild_id == config.CONFIG.guild_id


async def check_maintainer(interaction: discord.Interaction) -> bool:
    """app_commands-check wrapper: reject with a friendly, ephemeral message."""
    if not is_maintainer(interaction):
        raise GuardError("You need the Maintainer role to use this.")
    return True


async def check_guild(interaction: discord.Interaction) -> bool:
    """app_commands-check wrapper: reject with a friendly, ephemeral message."""
    if not same_guild(interaction):
        raise GuardError("This bot is configured for another server.")
    return True


async def reply_guard_error(interaction: discord.Interaction, error: GuardError) -> None:
    """Surface a guard rejection as an ephemeral message if we still can."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(error.message, ephemeral=True)
        else:
            await interaction.response.send_message(error.message, ephemeral=True)
    except discord.HTTPException:
        # the interaction already timed out; nothing sensible left to do
        pass
