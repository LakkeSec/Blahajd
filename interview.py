"""The DM interview: a small component-driven flow.

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
            ("APP/AI/ML", "app_ai", discord.ButtonStyle.primary),
            ("Digital Innovation", "digital_innovation", discord.ButtonStyle.primary),
            ("Associates Degree", "associates", discord.ButtonStyle.primary),
        ],
    ),
    "year": (
        "Which years are you taking courses in? Select all that apply — "
        "lots of people do a mixed schedule.",
        [],
    ),
    "track": (
        "Some 3rd years grab a specialisation — an optional side quest. "
        "Most people skip it, no shame:",
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
        "What should we call you? Type your (first) name — Blåhaj will "
        "set it as your server nickname once a maintainer approves.",
        [
            ("Enter your name", "name", discord.ButtonStyle.primary),
        ],
    ),
    "blahaj": (
        "Do you have a Blåhaj friend? 🦈",
        [
            ("Yes 🦈", "yes", discord.ButtonStyle.primary),
            ("No", "no", discord.ButtonStyle.secondary),
        ],
    ),
    "activity": (
        "Last one! Do you help out with anything outside class? Select all that apply.",
        [],
    ),
}

QUESTION_ORDER = ("who", "name", "program", "year", "track", "blahaj", "activity")

# multi-select year options (label, value)
YEAR_OPTIONS = (
    ("1st", "1"),
    ("2nd", "2"),
    ("3rd", "3"),
)

# multi-select extracurricular options (label, value)
ACTIVITY_OPTIONS = (
    ("Sin 💡", "sin"),
    ("Studentenraad ⚖️", "student_council"),
)


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
    if step == "year":
        return YearView(user_id, answers)
    if step == "activity":
        return ActivityView(user_id, answers)
    view = discord.ui.View(timeout=None)
    for label, value, style in options:
        button = discord.ui.Button(label=label, style=style, custom_id=f"{step}:{value}")
        button.callback = _make_answer_callback(user_id, answers, step, value)
        view.add_item(button)
    return view


class YearView(discord.ui.View):
    """Multi-select year picker — mix-and-match years, then hit Continue."""

    def __init__(self, user_id: int, answers: dict):
        super().__init__(timeout=None)
        self._user_id = user_id
        self._answers = answers
        self._selected: list[str] = []

    @discord.ui.select(
        placeholder="Select all years that apply",
        min_values=1,
        max_values=len(YEAR_OPTIONS),
        options=[discord.SelectOption(label=label, value=value) for label, value in YEAR_OPTIONS],
    )
    async def pick(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self._user_id:
            await interaction.response.send_message("This interview isn't for you.", ephemeral=True)
            return
        self._selected = list(select.values)
        # keep the select open so they can revise the mix before continuing
        await interaction.response.defer()

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.primary)
    async def continue_(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self._user_id:
            await interaction.response.send_message("This interview isn't for you.", ephemeral=True)
            return
        if not self._selected:
            await interaction.response.send_message(
                "Pick at least one year before continuing.",
                ephemeral=True,
            )
            return
        self._answers["year"] = self._selected
        store.upsert_session(self._user_id, self._answers, status="active")
        await _advance(interaction, self._user_id, self._answers, "year")


class ActivityView(discord.ui.View):
    """Multi-select extracurricular picker — SIN and/or Studentenraad, or None."""

    def __init__(self, user_id: int, answers: dict):
        super().__init__(timeout=None)
        self._user_id = user_id
        self._answers = answers
        self._selected: list[str] = []

    @discord.ui.select(
        placeholder="Select all that apply",
        min_values=1,
        max_values=len(ACTIVITY_OPTIONS),
        options=[
            discord.SelectOption(label=label, value=value) for label, value in ACTIVITY_OPTIONS
        ],
    )
    async def pick(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self._user_id:
            await interaction.response.send_message("This interview isn't for you.", ephemeral=True)
            return
        self._selected = list(select.values)
        # keep the select open so they can revise the mix before continuing
        await interaction.response.defer()

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.secondary)
    async def continue_(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self._user_id:
            await interaction.response.send_message("This interview isn't for you.", ephemeral=True)
            return
        if not self._selected:
            await interaction.response.send_message(
                "Pick at least one activity before continuing, or hit None.",
                ephemeral=True,
            )
            return
        self._answers["activity"] = self._selected
        store.upsert_session(self._user_id, self._answers, status="active")
        await _advance(interaction, self._user_id, self._answers, "activity")

    @discord.ui.button(label="None", style=discord.ButtonStyle.primary)
    async def none(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user.id != self._user_id:
            await interaction.response.send_message("This interview isn't for you.", ephemeral=True)
            return
        self._answers["activity"] = []
        store.upsert_session(self._user_id, self._answers, status="active")
        await _advance(interaction, self._user_id, self._answers, "activity")


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
        # teachers and alumni are done with identity questions; everyone
        # still gets asked about their Blåhaj friend
        if answers.get("who") in ("teacher", "graduate"):
            await ask(interaction, "blahaj", answers)
        else:
            await ask(interaction, "program", answers)
    elif step == "year":
        # the specialisation question only exists for cloud third years
        if "3" in roles.selected_years(answers) and answers.get("program") == "cloud":
            await ask(interaction, "track", answers)
        else:
            await ask(interaction, "blahaj", answers)
    elif step == "track":
        await ask(interaction, "blahaj", answers)
    elif step == "blahaj":
        await ask(interaction, "activity", answers)
    elif step == "activity":
        await _show_confirmation(interaction, user_id, answers)
    elif step == "program":
        # APP/AI and Digital Innovation students don't get year roles, so skip
        # the year question for them entirely
        if answers.get("program") in ("app_ai", "digital_innovation", "associates"):
            await ask(interaction, "blahaj", answers)
        else:
            await ask(interaction, "year", answers)


async def _show_confirmation(interaction: discord.Interaction, user_id: int, answers: dict) -> None:
    target = roles.resolve_roles(answers)
    lines = "\n".join(f"- {roles.ROLE_LABELS[key]}" for key in sorted(target))
    description = f"Blåhaj will request these roles:\n{lines}\n\n"
    name = answers.get("name")
    if name:
        description += (
            f"Name: **{name}** — Blåhaj will set your server nickname to "
            "this once a maintainer approves.\n\n"
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
                description="Blåhaj couldn't reach the server Try again in a bit. If it keeps failing, poke a maintainer.",
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
                description="Looks like you've left the server?! How dare you?! Nothing changed, sorry to see you go.",
                color=ERROR_COLOR,
            ),
            view=None,
        )
        return
    except (discord.Forbidden, discord.HTTPException) as exc:
        log.warning("could not fetch %s: %s", user_id, exc)
        # keep the confirmation alive so they can retry once it's fixed
        await interaction.response.edit_message(
            embed=embeds.styled(
                title="Request stuck",
                description="Blåhaj couldn't reach the server. Try again in a bit. If it keeps failing, poke a maintainer.",
                color=ERROR_COLOR,
            ),
            view=ConfirmView(user_id, answers, target),
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
                description="You already have the right roles. Blub.",
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
                description="Your request couldn't be sent.. Hmmm.. try again in a bit okay?",
                color=ERROR_COLOR,
            ),
            view=ConfirmView(user_id, answers, target),
        )
        return

    try:
        await channel.send(
            embed=approvals.build_request_embed(member, answers, to_add, to_remove),
            view=approvals.RequestView(user_id, answers, target),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        log.warning("could not post request for %s: %s", user_id, exc)
        # keep the confirmation alive so they can retry once it's fixed
        await interaction.response.edit_message(
            embed=embeds.styled(
                title="Request lost in transit",
                description="Your request couldn't be sent.. Hmmm.. try again in a bit okay?",
                color=ERROR_COLOR,
            ),
            view=ConfirmView(user_id, answers, target),
        )
        return
    store.upsert_session(user_id, answers, status="pending")
    await interaction.response.edit_message(
        embed=embeds.styled(
            title="Request sent ✅",
            description=("A maintainer will review it and you'll get the verdict in your DMs. Blub."),
            color=DONE_COLOR,
        ),
        view=None,
    )
