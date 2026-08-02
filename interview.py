"""The DM interview: a small button-driven flow.

One message is reused for the whole conversation — each answer edits it in
place, so the DM doesn't turn into a wall of messages.
"""

import logging

import discord

import approvals
import config
import embeds
import guild_utils
import roles
import store

log = logging.getLogger("blahajd.interview")

DONE_COLOR = embeds.DONE
ERROR_COLOR = embeds.ERROR


# question -> (prompt, [(button label, answer value, button style), ...])
QUESTIONS = {
    "who": (
        "Identity check: who are you? (This is the legit login prompt, promise)",
        [
            ("Student 🎓", "student", discord.ButtonStyle.primary),
            ("Graduate 🦒", "graduate", discord.ButtonStyle.primary),
            ("Teacher 🐐", "teacher", discord.ButtonStyle.primary),
        ],
    ),
    "program": (
        "Choose your fighter: which program are you in?",
        [
            # cloud is the common one, so it goes first
            ("Cloud & Cybersecurity", "cloud", discord.ButtonStyle.primary),
            ("APP/AI", "app_ai", discord.ButtonStyle.primary),
            ("Digital Innovation", "digital_innovation", discord.ButtonStyle.primary),
        ],
    ),
    "year": (
        "Which year are you in?",
        [
            ("1st", "1", discord.ButtonStyle.primary),
            ("2nd", "2", discord.ButtonStyle.primary),
            ("3rd", "3", discord.ButtonStyle.primary),
            ("Other", "other", discord.ButtonStyle.secondary),
        ],
    ),
    "track": (
        "Last one! Some 3rd years grab a specialisation — an optional side "
        "quest. Most people skip it, no shame:",
        [
            ("Not enrolled — skip", "neither", discord.ButtonStyle.secondary),
            ("Ethical Hacking 🥷", "ethical_hacking", discord.ButtonStyle.primary),
            (
                "Cloud Automation & Defence 🧙‍♂️",
                "cloud_defence",
                discord.ButtonStyle.primary,
            ),
        ],
    ),
    "name": (
        "What should we call you? Type your (first) name and pretty please "
        "also set your server nickname to include it, so everyone knows "
        "who's behind the account.",
        [
            ("Enter your name", "name", discord.ButtonStyle.primary),
        ],
    ),
}

QUESTION_ORDER = ("who", "name", "program", "year", "track")


def rollout_embed() -> discord.Embed:
    embed = embeds.styled(
        title="Yearly role refresh 🦈",
        description=(
            "New year, new you, new roles. Blåhaj just needs a few answers to "
            "line up your role request.\n\n"
            "A maintainer double-checks every request before it goes live, so "
            "no stress about getting it perfect."
        ),
    )
    embed.add_field(
        name="How it works",
        value="1. Answer a few quick questions\n2. Confirm your answers\n3. A maintainer signs off",
        inline=False,
    )
    return embed


class StartView(discord.ui.View):
    """The DM message users get during a rollout."""

    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self._user_id = user_id

    @discord.ui.button(label="Start", style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self._user_id:
            await interaction.response.send_message("This interview isn't for you.", ephemeral=True)
            return
        store.upsert_session(interaction.user.id, {}, status="active")
        await ask(interaction, "who", {})


def build_question_view(user_id: int, answers: dict, step: str) -> discord.ui.View:
    _, options = QUESTIONS[step]
    view = discord.ui.View(timeout=None)
    for label, value, style in options:
        button = discord.ui.Button(label=label, style=style, custom_id=f"{step}:{value}")
        button.callback = _make_answer_callback(user_id, answers, step, value)
        view.add_item(button)
    return view


class NameModal(discord.ui.Modal, title="What's your name?"):
    """Free-text name input; the one question buttons can't ask."""

    name_input = discord.ui.TextInput(
        label="Your name",
        placeholder="e.g. Alex",
        max_length=32,
        required=True,
    )

    def __init__(self, user_id: int, answers: dict):
        super().__init__()
        self._user_id = user_id
        self._answers = answers

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self._user_id:
            await interaction.response.send_message("This interview isn't for you.", ephemeral=True)
            return
        name = self.name_input.value.strip()
        if not name:
            await interaction.response.send_message(
                "That's an empty packet — try again with an actual name.",
                ephemeral=True,
            )
            return
        self._answers["name"] = name
        store.upsert_session(self._user_id, self._answers, status="active")
        await _advance(interaction, self._user_id, self._answers, "name")


def _make_answer_callback(user_id: int, answers: dict, step: str, value: str):
    async def callback(interaction: discord.Interaction):
        if interaction.user.id != user_id:
            await interaction.response.send_message("This interview isn't for you.", ephemeral=True)
            return
        if step == "name":
            await interaction.response.send_modal(NameModal(user_id, answers))
            return
        answers[step] = value
        store.upsert_session(user_id, answers, status="active")
        await _advance(interaction, user_id, answers, step)

    return callback


async def ask(interaction: discord.Interaction, step: str, answers: dict) -> None:
    prompt, _ = QUESTIONS[step]
    step_number = QUESTION_ORDER.index(step) + 1
    embed = embeds.styled(
        title=f"Question {step_number} of {len(QUESTION_ORDER)}",
        description=prompt,
    )
    view = build_question_view(interaction.user.id, answers, step)
    await interaction.response.edit_message(embed=embed, view=view)


async def _advance(
    interaction: discord.Interaction, user_id: int, answers: dict, step: str
) -> None:
    if step == "who":
        # everyone gets asked their name next
        await ask(interaction, "name", answers)
    elif step == "name":
        # teachers and alumni are done here; students continue
        if answers.get("who") in ("teacher", "graduate"):
            await _show_confirmation(interaction, user_id, answers)
        else:
            await ask(interaction, "program", answers)
    elif step == "year":
        # the specialisation question only exists for cloud third years
        if answers.get("year") == "3" and answers.get("program") == "cloud":
            await ask(interaction, "track", answers)
        else:
            await _show_confirmation(interaction, user_id, answers)
    elif step == "track":
        await _show_confirmation(interaction, user_id, answers)
    else:
        await ask(interaction, QUESTION_ORDER[QUESTION_ORDER.index(step) + 1], answers)


async def _show_confirmation(interaction: discord.Interaction, user_id: int, answers: dict) -> None:
    target = roles.resolve_roles(answers)
    lines = "\n".join(f"- {roles.ROLE_LABELS[key]}" for key in sorted(target))
    description = f"Blåhaj will request these roles:\n{lines}\n\n"
    name = answers.get("name")
    if name:
        description += (
            f"Name: **{name}** — remember to change your nickname to match, "
            "so we know who we're dealing with.\n\n"
        )
    description += "A maintainer signs off before anything goes live."
    embed = embeds.styled(
        title="Looks about right?",
        description=description,
    )
    view = ConfirmView(user_id, answers, target)
    await interaction.response.edit_message(embed=embed, view=view)


class ConfirmView(discord.ui.View):
    def __init__(self, user_id: int, answers: dict, target: set[str]):
        super().__init__(timeout=None)
        self._user_id = user_id
        self._answers = answers
        self._target = target

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self._user_id:
            await interaction.response.send_message("This interview isn't for you.", ephemeral=True)
            return
        await _submit_request(interaction, self._user_id, self._answers, self._target)

    @discord.ui.button(label="Start over", style=discord.ButtonStyle.secondary)
    async def restart(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self._user_id:
            await interaction.response.send_message("This interview isn't for you.", ephemeral=True)
            return
        store.upsert_session(interaction.user.id, {}, status="active")
        await ask(interaction, "who", {})

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self._user_id:
            await interaction.response.send_message("This interview isn't for you.", ephemeral=True)
            return
        store.upsert_session(interaction.user.id, {}, status="cancelled")
        embed = embeds.styled(
            title="Rolled back",
            description="Nothing was changed. Hit Start whenever you want another go.",
            color=ERROR_COLOR,
        )
        await interaction.response.edit_message(embed=embed, view=None)


async def _submit_request(
    interaction: discord.Interaction,
    user_id: int,
    answers: dict,
    target: set[str],
) -> None:
    """Post a role request to the mod channel; nothing is applied here."""
    cfg = config.CONFIG
    guild = interaction.client.get_guild(cfg.guild_id)
    if guild is None:
        log.error("guild %s not found while submitting a request", cfg.guild_id)
        await interaction.response.edit_message(
            embed=embeds.styled(
                title="Connection dropped",
                description="Blåhaj couldn't reach the server — try again in a bit.",
                color=ERROR_COLOR,
            ),
            view=None,
        )
        return

    try:
        member = await guild.fetch_member(user_id)
    except discord.NotFound:
        store.upsert_session(user_id, {}, status="cancelled")
        await interaction.response.edit_message(
            embed=embeds.styled(
                title="Rolled back",
                description="Looks like you've left the server — nothing to update then.",
                color=ERROR_COLOR,
            ),
            view=None,
        )
        return

    roles_by_key, missing = guild_utils.configured_roles(guild)
    if missing:
        log.error("configured roles missing in guild %s: %s", guild.id, missing)
        await interaction.response.edit_message(
            embed=embeds.styled(
                title="Misconfigured",
                description=(
                    "Blåhaj is missing some role IDs — poke the bot owner to "
                    f"check .env. Missing: {', '.join(missing)}"
                ),
                color=ERROR_COLOR,
            ),
            view=None,
        )
        return

    to_add, to_remove = guild_utils.role_diff(member, target, roles_by_key)

    if not to_add and not to_remove:
        store.upsert_session(user_id, answers, status="completed")
        await interaction.response.edit_message(
            embed=embeds.styled(
                title="All good 🎉",
                description="You already have the right roles. Enjoy the new year!",
                color=DONE_COLOR,
            ),
            view=None,
        )
        return

    channel = interaction.client.get_channel(cfg.request_channel_id)
    if channel is None:
        try:
            channel = await interaction.client.fetch_channel(cfg.request_channel_id)
        except discord.HTTPException:
            channel = None
    if channel is None:
        log.error("request channel %s not found", cfg.request_channel_id)
        # keep the confirmation alive so they can retry once it's fixed
        await interaction.response.edit_message(
            embed=embeds.styled(
                title="Request lost in transit",
                description="Your request couldn't be sent — try again in a bit.",
                color=ERROR_COLOR,
            ),
            view=ConfirmView(user_id, answers, target),
        )
        return

    await channel.send(
        embed=approvals.build_request_embed(member, answers, to_add, to_remove),
        view=approvals.RequestView(user_id, answers, target),
    )
    store.upsert_session(user_id, answers, status="pending")
    await interaction.response.edit_message(
        embed=embeds.styled(
            title="Request sent ✅",
            description=("A maintainer will review it and you'll get the verdict in your DMs."),
            color=DONE_COLOR,
        ),
        view=None,
    )
