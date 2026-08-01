"""Pure logic: interview answers -> the set of roles a member should have.

No discord imports here on purpose, so this stays unit-testable.
Role *keys* are used throughout; keys map to real role IDs in config.py.
"""

# every role the bot is allowed to manage. anything a member has that isn't
# in the resolved target set gets removed.
MANAGED_ROLES = (
    "itf",
    "app_ai",
    "digital_innovation",
    "year_2",
    "year_3",
    "alumni",
    "docent",
    "ethical_hacking",
    "cloud_defence",
)

# human-readable labels, used in the confirmation screen
ROLE_LABELS = {
    "itf": "ITF 🐊",
    "app_ai": "APP/AIHAAI/ML ㊙️",
    "digital_innovation": "Digital Innovation 🤖",
    "year_2": "2CCS 🐊",
    "year_3": "3CCS 🐊",
    "alumni": "Alumni 🦒",
    "docent": "Docent 🐐",
    "ethical_hacking": "Ethical Hacking 🥷",
    "cloud_defence": "Cloud Automation & Defence 🧙‍♂️",
}


def resolve_roles(answers: dict) -> set[str]:
    """Return the exact set of role keys these answers map to."""
    who = answers.get("who")
    if who == "teacher":
        return {"docent"}
    if who == "graduate":
        return {"alumni"}

    # everyone below this line is a student
    roles = {"itf"}
    program = answers.get("program")
    if program == "app_ai":
        roles.add("app_ai")
    elif program == "digital_innovation":
        roles.add("digital_innovation")
    # cloud & cybersecurity students don't have a program role of their own

    year = answers.get("year")
    if year == "2":
        roles.add("year_2")
    elif year == "3":
        roles.add("year_3")
        if program == "cloud":
            # the specialisation question is only asked in this case
            track = answers.get("track")
            if track in ("ethical_hacking", "cloud_defence"):
                roles.add(track)

    return roles
