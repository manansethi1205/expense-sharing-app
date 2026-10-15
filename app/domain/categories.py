import re
import unicodedata
from dataclasses import dataclass

CATEGORIES = ("travel", "food", "accommodation", "activities", "shopping", "other")
RULES_VERSION = "v1"
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
PHRASES = {"bike rental": "travel", "bike purchase": "shopping", "hotel dinner": "food"}


@dataclass(frozen=True)
class Classification:
    category: str
    source: str
    rule: str | None


def classify_description(description: str) -> Classification:
    normalized = " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", description).casefold()))
    phrase_matches = [phrase for phrase in PHRASES if f" {phrase} " in f" {normalized} "]
    if phrase_matches:
        categories = {PHRASES[phrase] for phrase in phrase_matches}
        if len(categories) == 1:
            return Classification(
                categories.pop(),
                "rule",
                f"{RULES_VERSION}:phrase:{','.join(sorted(phrase_matches))}",
            )
        return Classification("other", "fallback", f"{RULES_VERSION}:ambiguous")
    words = set(normalized.split())
    matches = {category for category, keywords in WORDS.items() if words & keywords}
    if len(matches) == 1:
        category = matches.pop()
        return Classification(category, "rule", f"{RULES_VERSION}:keyword:{category}")
    return Classification(
        "other", "fallback", f"{RULES_VERSION}:{'ambiguous' if matches else 'unknown'}"
    )
