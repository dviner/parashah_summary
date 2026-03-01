"""
Sefaria API client for fetching the weekly Parashah name and English text.
No API key required — Sefaria is a free, open resource.
"""

import requests
from config import SEFARIA_CALENDARS_URL, SEFARIA_TEXTS_URL, PARASHAH_VERSE_LIMIT


def get_current_parashah() -> dict:
    """
    Fetch the current week's Parashah from the Sefaria calendars API.

    Returns a dict with:
        - name: str  — display name (e.g. "Vayikra")
        - ref:  str  — Sefaria reference (e.g. "Leviticus 1:1-5:26")

    Raises RuntimeError if the Parashah cannot be found.
    """
    response = requests.get(SEFARIA_CALENDARS_URL, timeout=15)
    response.raise_for_status()
    data = response.json()

    for item in data.get("calendar_items", []):
        if item.get("title", {}).get("en") == "Parashat Hashavua":
            return {
                "name": item["displayValue"]["en"],
                "ref": item["ref"],
            }

    raise RuntimeError(
        "Could not find 'Parashat Hashavua' in Sefaria calendars response. "
        f"Available items: {[i.get('title', {}).get('en') for i in data.get('calendar_items', [])]}"
    )


def _flatten_verses(text_data) -> list[str]:
    """
    Recursively flatten nested verse lists (Sefaria returns chapters as nested arrays)
    into a flat list of verse strings.
    """
    if isinstance(text_data, str):
        return [text_data] if text_data.strip() else []
    if isinstance(text_data, list):
        verses = []
        for item in text_data:
            verses.extend(_flatten_verses(item))
        return verses
    return []


def get_parashah_text(ref: str) -> str:
    """
    Fetch the English translation of a Torah portion from Sefaria.

    Limits the result to the first PARASHAH_VERSE_LIMIT verses.
    Returns the verses joined as a single string, each verse on its own line.

    Raises RuntimeError if the text cannot be retrieved.
    """
    url = f"{SEFARIA_TEXTS_URL}/{requests.utils.quote(ref)}"
    response = requests.get(url, params={"version": "english"}, timeout=15)
    response.raise_for_status()
    data = response.json()

    # Sefaria v3 returns text under data["versions"][0]["text"]
    versions = data.get("versions", [])
    if not versions:
        raise RuntimeError(f"No text versions returned for ref '{ref}'. Response: {data}")

    raw_text = versions[0].get("text", [])
    verses = _flatten_verses(raw_text)

    if not verses:
        raise RuntimeError(f"No verses found in Sefaria response for ref '{ref}'.")

    limited = verses[:PARASHAH_VERSE_LIMIT]
    return "\n".join(limited)
