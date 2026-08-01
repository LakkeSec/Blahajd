"""The mod approval flow.

A finished interview is posted to the mod channel as a request instead of
granting roles directly. Mods click Approve or Reject; roles are only ever
touched from here, after an approval.
"""

import logging

import discord

import config
import roles
import store

log = logging.getLogger("blahajd.approvals")

FOOTER = "Cloud & Cybersecurity Discord"
REQUEST_COLOR = discord.Color.orange()


def styled(
    title: str | None = None,
    description: str | None = None,
    color: discord.Color = REQUEST_COLOR,
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=FOOTER)
    return embed


# answers -> something a mod can actually read
ANSWER_LABELS = {
    "who": {
        "student": "Student 🎓",
        "graduate": "Graduate 🦒",
        "teacher": "Teacher 🐐",
    },
    "program": {
        "app_ai": "APP/AI",
        "digital_innovation": "Digital Innovation",
        "cloud": "Cloud & Cybersecurity",
    },
    "year": {"1": "1st year", "2": "2nd year", "3": "3rd year", "other": "Other"},
    "track": {
        "ethical_hacking": "Ethical Hacking 🥷",
        "cloud_defence": "Cloud Automation & Defence 🧙‍♂️",
        "neither": "Not enrolled",
    },
}


def is_maintainer(interaction: discord.Interaction) -> bool:
    """Guild owner or someone holding the Maintainer role."""
    user = interaction.user
    if not isinstance(user, discord.Member):
        return False
    if user == interaction.guild.owner:
        return True
    return any(role.id == config.CONFIG.maintainer_role_id for role in user.roles)


def _answers_summary(answers: dict) -> str:
    lines = []
    for step, value in answers.items():
        if step == "name":
            lines.append(f"name: {value}")
            continue
        label = ANSWER_LABELS.get(step, {}).get(value)
        lines.append(f"{step}: {label or value}")
    return "\n".join(lines) if lines else "_no answers_"


def build_request_embed(
    member: discord.Member, answers: dict, to_add: set[str], to_remove: set[str]
) -> discord.Embed:
    embed = styled(
        title="Role request 🦈",
        description=f"{member.mention} ({member.display_name}) submitted a role request.",
    )
    name = answers.get("name")
    if name:
        embed.add_field(
            name="Name",
            value=f"{name} — remind them to set their nickname accordingly.",
            inline=False,
        )
    embed.add_field(name="Answers", value=_answers_summary(answers), inline=False)
    if to_add:
        embed.add_field(
            name="Add",
            value="\n".join(f"- {roles.ROLE_LABELS[k]}" for k in sorted(to_add)),
        )
    if to_remove:
        embed.add_field(
            name="Remove",
            value="\n".join(f"- {roles.ROLE_LABELS[k]}" for k in sorted(to_remove)),
        )
    return embed


def _outcome_embed(approved: bool, added: set[str] = frozenset()) -> discord.Embed:
    if approved:
        if added:
            description = "Your roles are updated:\n" + "\n".join(
                f"- {roles.ROLE_LABELS[k]}" for k in sorted(added)
            )
        else:
            description = "Your roles are already up to date. Enjoy the new year!"
        return styled(
            title="Access granted ✅",
            description=description,
            color=discord.Color.green(),
        )
    return styled(
        title="Access denied 🚫",
        description=(
            "Your role request didn't pass review. If that feels like a false "
            "positive, appeal to the maintainers."
        ),
        color=discord.Color.red(),
    )


class RequestView(discord.ui.View):
    """Approve/reject buttons on a request message in the mod channel."""

    def __init__(self, member_id: int, answers: dict, target: set[str]):
        super().__init__(timeout=None)
        self.member_id = member_id
        self.answers = answers
        self.target = target

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, _):
        await self._decide(interaction, approved=True)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, _):
        await self._decide(interaction, approved=False)

    async def _decide(self, interaction: discord.Interaction, approved: bool) -> None:
        if interaction.channel is None or interaction.channel.id != config.CONFIG.request_channel_id:
            await interaction.response.send_message(
                "That's not the approval channel.", ephemeral=True
            )
            return
        if not is_maintainer(interaction):
            await interaction.response.send_message(
                "You need the Maintainer role to do that.", ephemeral=True
            )
            return

        # close the request before doing anything slow, so nobody double-clicks
        embed = None
        if interaction.message.embeds:
            embed = interaction.message.embeds[0].copy()
            embed.color = discord.Color.green() if approved else discord.Color.red()
            embed.set_footer(
                text=f"{'Approved' if approved else 'Rejected'} by {interaction.user.display_name}"
            )
        await interaction.response.edit_message(embed=embed, view=None)

        store.log_action(
            self.member_id,
            "request approved" if approved else "request rejected",
            f"decided_by={interaction.user.id}",
        )

        if approved:
            result = await self._apply_roles(interaction.client)
        else:
            store.upsert_session(self.member_id, self.answers, status="rejected")
            result = _outcome_embed(approved=False)

        try:
            user = await interaction.client.fetch_user(self.member_id)
            await user.send(embed=result)
        except discord.HTTPException as exc:
            log.warning("could not DM %s the decision: %s", self.member_id, exc)

    async def _apply_roles(self, client: discord.Client) -> discord.Embed:
        cfg = config.CONFIG
        guild = client.get_guild(cfg.guild_id)
        if guild is None:
            log.error("guild %s missing while approving roles", cfg.guild_id)
            return _outcome_embed(approved=False)

        roles_by_key = {key: guild.get_role(rid) for key, rid in cfg.role_ids.items()}
        missing = [key for key, role in roles_by_key.items() if role is None]
        if missing:
            log.error("configured roles missing in guild %s: %s", guild.id, missing)
            return _outcome_embed(approved=False)

        try:
            member = await guild.fetch_member(self.member_id)
        except discord.NotFound:
            store.upsert_session(self.member_id, {}, status="cancelled")
            return styled(
                title="Nothing applied",
                description="The member is no longer in the server, so their roles weren't touched.",
                color=discord.Color.red(),
            )

        # re-diff against their current roles; things may have changed while
        # the request sat in the channel
        current = {key for key, role in roles_by_key.items() if role in member.roles}
        to_add = self.target - current
        to_remove = current - self.target

        try:
            if to_remove:
                await member.remove_roles(
                    *[roles_by_key[k] for k in to_remove], reason="Approved role request"
                )
            if to_add:
                await member.add_roles(
                    *[roles_by_key[k] for k in to_add], reason="Approved role request"
                )
        except (discord.Forbidden, discord.HTTPException) as exc:
            log.warning("role change failed for %s: %s", self.member_id, exc)
            return styled(
                title="Couldn't apply",
                description=(
                    "The roles couldn't be applied — Blåhaj's permissions got "
                    "revoked? Check the bot's role in Server Settings."
                ),
                color=discord.Color.red(),
            )

        store.log_action(
            self.member_id,
            "roles applied",
            f"added={sorted(to_add)} removed={sorted(to_remove)}",
        )
        store.upsert_session(self.member_id, self.answers, status="completed")
        return _outcome_embed(approved=True, added=to_add)
