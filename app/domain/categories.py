import re
import unicodedata
from dataclasses import dataclass

CATEGORIES = ("travel", "food", "accommodation", "activities", "shopping", "other")
RULES_VERSION = "v2"
WORDS = {
    "travel": {
        "auto",
        "cab",
        "bike",
        "taxi",
        "flight",
        "train",
        "bus",
        "uber",
        "ola",
        "petrol",
        "metro",
    },
    "food": {"dinner", "restaurant", "lunch", "breakfast", "cafe", "food", "snacks"},
    "accommodation": {"hotel", "stay", "hostel", "resort", "accommodation", "lodging"},
    "activities": {"museum", "tour", "concert", "tickets", "kayaking", "scuba"},
    "shopping": {"shopping", "souvenirs", "clothes", "purchase"},
}
PHRASES = {
    "bike rental": "travel",
    "bike purchase": "shopping",
    "hotel dinner": "food",
    **{
        f"{transport} {ticket}": "travel"
        for transport in ("bus", "flight", "train", "metro")
        for ticket in ("ticket", "tickets")
    },
}


@dataclass(frozen=True)
class Classification:
    category: str
    source: str
    rule: str | None


def classify_description(description: str) -> Classification:
    tokens = re.findall(r"\w+", unicodedata.normalize("NFKC", description).casefold())
    used, matches = set(), set()
    # Specific phrases consume only their own tokens, never unrelated surrounding context.
    for phrase in sorted(PHRASES, key=lambda value: (-len(value.split()), value)):
        parts = phrase.split()
        for index in range(len(tokens) - len(parts) + 1):
            positions = set(range(index, index + len(parts)))
            if not positions & used and tokens[index : index + len(parts)] == parts:
                used.update(positions)
                matches.add(PHRASES[phrase])
    words = {word for index, word in enumerate(tokens) if index not in used}
    generic_tickets = {"ticket", "tickets"}
    specific_words = words - generic_tickets
    matches.update(category for category, keywords in WORDS.items() if specific_words & keywords)
    # "tickets" alone suggests activities; it must not overrule flight/bus context.
    if not matches and words & generic_tickets:
        matches.add("activities")
    if len(matches) == 1:
        category = matches.pop()
        return Classification(
            category, "rule", f"{RULES_VERSION}:{'context' if used else 'keyword'}:{category}"
        )
    return Classification(
        "other", "fallback", f"{RULES_VERSION}:{'ambiguous' if matches else 'unknown'}"
    )
