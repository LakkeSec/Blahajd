# Blahajd

A small Discord bot that handles the yearly role refresh for a student
cybersecurity server. Blåhaj the shark DMs every member a few questions and
sets their roles based on the answers.

## How it works

- An admin (or the server owner) runs `/rollout`, which DMs every member a
  button-based interview.
- Questions: who you are (student / graduate / teacher), your name (which
  Blåhaj uses as your server nickname once a request is approved), and for
  students: program
  (Cloud & Cybersecurity first — it's the common one), year (select all that
  apply — mixed schedules are normal), and an optional specialisation that
  most people skip. Teachers and alumni are done after
  the first two questions. Everyone closes out by telling Blåhaj whether they
  have a Blåhaj friend — yeses get the Blahaj 🦈 role — and which
  extracurriculars they're in (SIN 💡 and/or Studentenraad ⚖️, or none).
- The interview ends with a confirmation screen listing exactly which roles
  would be applied.
- Confirming posts a **role request** to a mod-only channel with
  Approve/Reject buttons. Roles are never granted without a maintainer's
  approval.
- On **approve** the member gets their roles (replaced, not stacked: someone
  who was `2CCS 🐊` and answers 3rd year loses `2CCS 🐊` and gains `3CCS 🐊`)
  plus a DM confirming it. On **reject** they get a DM saying the request was
  denied. The bot only ever touches the roles it finds in `.env`, nothing
  else.

## Role logic

| Answers | Roles given |
|---|---|
| Teacher | Docent 🐐 |
| Graduate | Alumni 🦒 |
| Student, APP/AI | ITF🐊 + APP/AIHAAI/ML ㊙️ + year role |
| Student, Digital Innovation | ITF🐊 + Digital Innovation 🤖 + year role |
| Student, Cloud & Cybersecurity | ITF🐊 + year role |
| 2nd year student | + 2CCS 🐊 |
| 3rd year student | + 3CCS🐊 |
| Student taking courses across years | + each matching year role (e.g. 2nd + 3rd → 2CCS 🐊 + 3CCS 🐊) |
| 3rd year, Cloud & Cybersecurity | optionally + Ethical Hacking 🥷 or Cloud Automation & Defence 🧙♂️ |
| Anyone with a Blåhaj friend | + Blahaj 🦈 |
| Member of SIN | + Sin 💡 |
| Member of Studentenraad | + Studentenraad ⚖️ |

## Setup

1. Create an application in the [Discord Developer Portal](https://discord.com/developers/applications)
   and add a bot user to it. Copy the bot token (**Bot → Token**) — it goes
   into `DISCORD_TOKEN` in `.env`.
2. In the developer portal, enable **Privileged Gateway Intents → Members**.
3. Invite the bot with the `Manage Roles`, `Send Messages`, `View Channels`
   and `Read Message History` permissions, plus the `applications.commands`
   scope:

   ```
   https://discord.com/api/oauth2/authorize?client_id=<APP_ID>&permissions=268504064&scope=bot%20applications.commands
   ```

   `268504064` is the sum of exactly those four permissions. You can also pick
   them manually in the portal.
4. Make sure the bot's role sits **above** the roles it has to manage in
   Server Settings.
5. Copy the example config and fill it in:

   ```
   cp .env.example .env
   ```

   Enable Developer Mode (User Settings → Advanced) if you haven't, then
   right-click each role in Server Settings → Copy Role ID. Also grab the ID
   of the mod-only channel where requests should land and the ID of the
   **Maintainer** role (whoever holds it can run the admin commands below and
   approve requests).
6. Install and run:

   ```
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   python bot.py
   ```

## Run with Docker

Skip the manual install above if you'd rather containerise — the repo ships a
`Dockerfile`. Do steps 1–5 of [Setup](#setup) first (you still need a filled-in
`.env`), then:

1. Point the database at the volume and let the run command pass your `.env`
   into the container (your secrets never end up inside the image):

   ```
   DB_PATH=/data/blahajd.db
   ```

   Add that to `.env`.

2. Build and run:

   ```
   docker build -t blahajd .
   docker run -d --name blahajd --env-file .env \
     -v blahajd-data:/data --restart unless-stopped blahajd
   ```

3. Watch the logs (the bot logs its presence rotations and slash command sync):

   ```
   docker logs -f blahajd
   ```

The `blahajd-data` volume keeps `blahajd.db` between restarts and rebuilds.
To update the bot: `docker build -t blahajd . && docker restart blahajd`.

## Commands

`/update` is for everyone; the rest need the `Maintainer` role (or the server
owner).

| Command | Who can use it | What it does |
|---|---|---|
| `/update` | Everyone | Re-runs the interview on yourself — the DM flow asks the questions, a maintainer approves |
| `/rollout` | Maintainer | Starts the annual rollout and DMs every member |
| `/interview @user` | Maintainer | Sends the interview to a single member (late joiners, closed DMs) |
| `/rollout_status` | Maintainer | Shows how many members completed / are stuck / can't be DM'd |
| `/rollout_reset` | Maintainer | Wipes all sessions before the next year's rollout (audit log is kept) |

## Notes

- Roles are **trust-based**: answers are not verified against any registry.
  The bot was built for a small, well-known community.
- Every role change is written to an audit log in SQLite (`blahajd.db`).
- Sessions survive bot restarts, but an interview interrupted by a restart is
  best redone with `/interview @user`. The Approve/Reject buttons on pending
  requests in the mod channel also stop working after a restart — resend the
  interview to have the request posted fresh.
- DMs are throttled to one per second during a rollout to stay friendly to the
  Discord API.

## Development

Format and lint before opening a PR:

```
pip install -r requirements-dev.txt
ruff check .
ruff format .
```

There are no unit tests yet, but the pure-logic layer (`roles.py`) and the
database layer (`store.py`) were deliberately kept dependency-free so tests
can be added without a running bot. The list of managed roles lives only in
`roles.py`; `config.py` verifies its env mapping matches at startup, so the two
can't silently drift.

## License

MIT — see [LICENSE](LICENSE).
