"""Shared embed helpers used by the interview and approval flows."""

import discord

FOOTER = "Cloud & Cybersecurity Discord"

# the default accent colour across the bot
BRAND = discord.Color.blurple()
DONE = discord.Color.green()
ERROR = discord.Color.red()
REQUEST = discord.Color.orange()


def styled(
    title: str | None = None,
    description: str | None = None,
    color: discord.Color = BRAND,
    footer: str = FOOTER,
) -> discord.Embed:
    """Build an embed pre-filled with the standard footer."""
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=footer)
    return embed
