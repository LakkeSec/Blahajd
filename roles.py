"""Pure logic for interview answers -> the set of roles a member should have.

No discord imports here on purpose, so this stays unit-testable. Role *keys*
are the single source of truth; they map to real role IDs in config.py, and
guards.py assumes these are the only roles the bot manages.
"""

# every role key the bot knows about. config.py maps each of these to an env
# var (and from there to a real role ID), and the bot never touches any role
# that isn't in this list.
ROLE_KEYS = (
    "itf",
    "app_ai",
    "digital_innovation",
    "it_graduaten",
    "year_2",
    "year_3",
    "alumni",
    "docent",
    "ethical_hacking",
    "cloud_defence",
    "blahaj",
    "sin",
    "student_council",
)

# human-readable labels, used in the confirmation screen
ROLE_LABELS = {
    "itf": "ITF 🐊",
    "app_ai": "APP/AIHAAI/ML ㊙️",
    "digital_innovation": "Digital Innovation 🤖",
    "it_graduaten": "IT Graduaten 🦉",
    "year_2": "2CCS 🐊",
    "year_3": "3CCS 🐊",
    "alumni": "Alumni 🦒",
    "docent": "Docent 🐐",
    "ethical_hacking": "Ethical Hacking 🥷",
    "cloud_defence": "Cloud Automation & Defence 🧙‍♂️",
    "blahaj": "Blahaj 🦈",
    "sin": "Sin 💡",
    "student_council": "Studentenraad ⚖️",
}


def selected_years(answers: dict) -> list[str]:
    """Normalize the (possibly multi-select) year answer to a list.

    Before the multi-select change the answer was a single string like "2";
    keep accepting those so in-flight sessions don't break.
    """
    year = answers.get("year", [])
    if isinstance(year, str):
        return [year]
    return list(year)


def resolve_roles(answers: dict) -> set[str]:
    """Return the exact set of role keys these answers map to."""
    roles = set()
    who = answers.get("who")
    if who == "teacher":
        roles.add("docent")
    elif who == "graduate":
        roles.add("alumni")
    else:
        # everyone below this line is a student
        roles.add("itf")
        program = answers.get("program")
        if program == "app_ai":
            roles.add("app_ai")
        elif program == "digital_innovation":
            roles.add("digital_innovation")
        elif program == "associates":
            roles.add("it_graduaten")
        # cloud & cybersecurity students don't have a program role of their own

        # APP/AI, Digital Innovation and Associates Degree students don't get
        # year roles — the year question is only relevant for cloud &
        # cybersecurity students
        years = []
        if program not in ("app_ai", "digital_innovation", "associates"):
            years = selected_years(answers)
        # first-year cloud students get nothing beyond the base ITF role:
        # year "1" exists in the picker but intentionally maps to no role
        if "2" in years:
            roles.add("year_2")
        if "3" in years:
            roles.add("year_3")
            if program == "cloud":
                # the specialisation question is only asked in this case
                track = answers.get("track")
                if track in ("ethical_hacking", "cloud_defence"):
                    roles.add(track)

    if answers.get("blahaj") == "yes":
        roles.add("blahaj")

    activities = answers.get("activity", [])
    if isinstance(activities, str):
        activities = [activities]
    if "sin" in activities:
        roles.add("sin")
    if "student_council" in activities:
        roles.add("student_council")

    return roles
