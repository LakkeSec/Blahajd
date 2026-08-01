"""Blahajd - the yearly role refresh bot.

Run with: python bot.py
Requires a filled-in .env, see .env.example.
"""

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

import approvals
import config
import interview
import store

log = logging.getLogger("blahajd")

intents = discord.Intents.default()
intents.members = True  # needed to see everyone and hand out roles
# we don't read chat, but commands.Bot warns without this intent
intents.message_content = True

# Bot instead of Client because we want a slash command tree.
# the prefix is never used; it's just required to construct one.
client = commands.Bot(
    command_prefix="!",
    intents=intents,
    # chunk_guilds_at_startup (defaults to True when the members intent is
    # on) sends gateway member-chunk requests on every connect. Discord's
    # lazy guilds rate-limit those aggressively and discord.py then never
    # fires on_ready. We fetch members over REST when needed instead.
    chunk_guilds_at_startup=False,
)


async def all_members(guild: discord.Guild) -> list[discord.Member]:
    """Every member of the guild, minus bots.

    Uses REST because gateway chunking is unreliable on lazy guilds.
    Falls back to the cache if the request fails.
    """
    try:
        return [m async for m in guild.fetch_members() if not m.bot]
    except (discord.Forbidden, discord.HTTPException) as exc:
        log.warning("member fetch failed (%s); using cache", exc)
        return [m for m in guild.members if not m.bot]


def configured_guild() -> discord.Guild | None:
    """Return the configured guild from cache, if available."""
    return client.get_guild(config.CONFIG.guild_id)


# commands are guild-scoped so they register instantly; syncing as a global
# command would take up to an hour to propagate
TARGET_GUILD = discord.Object(id=config.CONFIG.guild_id)

# shared with the approval view
is_maintainer = approvals.is_maintainer


@client.event
async def on_ready() -> None:
    cfg = config.CONFIG
    guild = configured_guild()
    if guild is None:
        log.error("guild %s not found — is the bot invited?", cfg.guild_id)
        return

    missing = [key for key, rid in cfg.role_ids.items() if guild.get_role(rid) is None]
    if missing:
        log.warning("these configured roles were not found in the server: %s", missing)
    me = guild.me
    if me is None and client.user is not None:
        me = guild.get_member(client.user.id)
    if me is None:
        log.warning("could not resolve the bot member object in guild %s", guild.id)
    elif not me.guild_permissions.manage_roles:
        log.warning("the bot lacks the Manage Roles permission!")

    log.info("ready on %s (%d members)", guild.name, guild.member_count or 0)

    # guild-scoped sync registers instantly; a bare sync() would register
    # globally, which can take up to an hour to show up
    try:
        synced = await client.tree.sync(guild=guild)
    except discord.HTTPException as exc:
        log.error("slash command sync failed: %s", exc)
    else:
        log.info("slash commands synced for %s: %s", guild.name, [c.name for c in synced])
        if not synced:
            log.error("sync returned no commands — check the guilds() decorators")


async def send_interview_message(member: discord.Member) -> None:
    """DM a member the start prompt. Raises Forbidden if DMs are closed."""
    dm = await member.create_dm()
    await dm.send(
        embed=interview.rollout_embed(), view=interview.StartView(member.id)
    )


@client.tree.command(
    name="rollout", description="DM every member with the yearly role interview"
)
@app_commands.guilds(TARGET_GUILD)
async def cmd_rollout(interaction: discord.Interaction) -> None:
    if not is_maintainer(interaction):
        await interaction.response.send_message(
            "You need the Maintainer role to use this.", ephemeral=True
        )
        return
    if interaction.guild_id != config.CONFIG.guild_id:
        await interaction.response.send_message(
            "This bot is configured for another server.", ephemeral=True
        )
        return
    await interaction.response.defer(thinking=True)

    guild = configured_guild()
    if guild is None:
        await interaction.followup.send(
            "I can't find the configured server right now. Try again in a moment.",
            ephemeral=True,
        )
        return

    sent = failed = 0
    blocked = []
    for member in await all_members(guild):
        try:
            await send_interview_message(member)
            store.upsert_session(member.id, {}, status="sent")
            sent += 1
        except discord.Forbidden:
            failed += 1
            blocked.append(member.display_name)
        except discord.HTTPException as exc:
            failed += 1
            log.warning("DM to %s failed: %s", member.id, exc)
        await asyncio.sleep(1.0)  # take it easy on the API during big rollouts

    description = f"Sent to **{sent}** members.\nCould not DM: **{failed}**"
    if blocked:
        description += "\n\nBlocked DMs: " + ", ".join(blocked[:25])
        if len(blocked) > 25:
            description += "…"
    await interaction.followup.send(
        embed=discord.Embed(
            title="Rollout started 🚀",
            description=description,
            color=discord.Color.blurple(),
        )
    )


@client.tree.command(
    name="interview", description="Send the role interview to a single member"
)
@app_commands.guilds(TARGET_GUILD)
async def cmd_interview(
    interaction: discord.Interaction, member: discord.Member
) -> None:
    if not is_maintainer(interaction):
        await interaction.response.send_message(
            "You need the Maintainer role to use this.", ephemeral=True
        )
        return
    if interaction.guild_id != config.CONFIG.guild_id:
        await interaction.response.send_message(
            "This bot is configured for another server.", ephemeral=True
        )
        return
    if member.bot:
        await interaction.response.send_message(
            "Bots already have all the permissions. Nice try though.",
            ephemeral=True,
        )
        return
    await interaction.response.defer(thinking=True)
    try:
        await send_interview_message(member)
        store.upsert_session(member.id, {}, status="sent")
    except discord.Forbidden:
        await interaction.followup.send(
            f"Couldn't reach {member.display_name} — their DMs are locked down.",
            ephemeral=True,
        )
        return
    await interaction.followup.send(
        f"Interview sent to {member.display_name}.", ephemeral=True
    )


@client.tree.command(
    name="update",
    description="Request a role update for yourself (new year, new roles)",
)
@app_commands.guilds(TARGET_GUILD)
async def cmd_update(interaction: discord.Interaction) -> None:
    """The public version of /interview — anyone can run it on themselves."""
    if interaction.guild_id != config.CONFIG.guild_id:
        await interaction.response.send_message(
            "This bot is configured for another server.", ephemeral=True
        )
        return
    await interaction.response.defer(thinking=True)
    try:
        await send_interview_message(interaction.user)
        store.upsert_session(interaction.user.id, {}, status="sent")
    except discord.Forbidden:
        await interaction.followup.send(
            "I couldn't reach you — your DMs are closed. Open up and try again.",
            ephemeral=True,
        )
        return
    await interaction.followup.send(
        "Check your DMs — Blåhaj is knocking. A maintainer will review your request.",
        ephemeral=True,
    )


@client.tree.command(name="rollout_status", description="How the rollout is going")
@app_commands.guilds(TARGET_GUILD)
async def cmd_rollout_status(interaction: discord.Interaction) -> None:
    if not is_maintainer(interaction):
        await interaction.response.send_message(
            "You need the Maintainer role to use this.", ephemeral=True
        )
        return
    if interaction.guild_id != config.CONFIG.guild_id:
        await interaction.response.send_message(
            "This bot is configured for another server.", ephemeral=True
        )
        return
    guild = configured_guild()
    if guild is None:
        await interaction.response.send_message(
            "I can't find the configured server right now. Try again in a moment.",
            ephemeral=True,
        )
        return

    counts = store.status_counts()
    members = len(await all_members(guild))
    untouched = max(0, members - counts["total"])

    description = (
        f"Members to reach: **{members}**\n"
        f"- contacted, not started: **{counts['sent']}**\n"
        f"- mid-interview: **{counts['active']}**\n"
        f"- awaiting mod approval: **{counts['pending']}**\n"
        f"- approved & done: **{counts['completed']}**\n"
        f"- rejected: **{counts['rejected']}**\n"
        f"- cancelled: **{counts['cancelled']}**\n"
        f"- not contacted yet: **{untouched}**"
    )
    await interaction.response.send_message(
        embed=discord.Embed(
            title="Rollout status", description=description, color=discord.Color.blurple()
        )
    )


@client.tree.command(
    name="rollout_reset", description="Wipe all sessions (audit log is kept)"
)
@app_commands.guilds(TARGET_GUILD)
async def cmd_rollout_reset(interaction: discord.Interaction) -> None:
    if not is_maintainer(interaction):
        await interaction.response.send_message(
            "You need the Maintainer role to use this.", ephemeral=True
        )
        return
    if interaction.guild_id != config.CONFIG.guild_id:
        await interaction.response.send_message(
            "This bot is configured for another server.", ephemeral=True
        )
        return
    store.clear_sessions()
    await interaction.response.send_message(
        "Sessions cleared. Use /rollout to start a fresh round.", ephemeral=True
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # discord's own logs are noisy; only surface problems
    logging.getLogger("discord").setLevel(logging.WARNING)

    store.init(config.CONFIG.db_path)
    client.run(config.CONFIG.token)
