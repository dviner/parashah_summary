"""
Main script — generates one weekly Parashah podcast episode end-to-end.

Usage:
    python generate_episode.py

Reads from environment:
    ANTHROPIC_API_KEY   — Anthropic API key
    ELEVENLABS_API_KEY  — ElevenLabs API key
    ELEVENLABS_VOICE_ID — (optional) override the voice ID from config.py
"""

import os
import sys
from datetime import datetime, timezone

import anthropic

from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, EPISODES_DIR, SCRIPTS_DIR, PODCAST_BASE_URL
from sefaria_client import get_current_parashah, get_parashah_text
from elevenlabs_client import text_to_mp3
from rss_manager import add_episode


EPISODE_SCRIPT_PROMPT = """\
You are the host of a short weekly podcast called "Parashah in 5" that summarizes \
the Jewish weekly Torah portion in under 5 minutes.

Below is the English text of this week's Torah portion, called {parashah_name} \
({parashah_ref}).

Write a podcast episode script that is approximately 350 words — \
suitable for a 2.5 to 3 minute recording. The script must have exactly three parts, \
clearly separated by a blank line between each part:

Part 1 — Introduction (2-3 sentences): Welcome listeners warmly and introduce the \
name of this week's Torah portion and where it falls in the larger story.

Part 2 — Story Summary (8-12 sentences): Begin with one sentence stating the specific \
book, chapter, and verse range being summarized — written out in natural spoken English, \
for example: "Here is our summary of Exodus, chapter thirty, verse eleven, \
through chapter thirty-four, verse thirty-five." Then retell the events of the portion \
in detail. Cover the key scenes and characters. Make it vivid and engaging — help the \
listener feel like they are hearing the story unfold.

Part 3 — Closing (1-2 sentences): A brief, warm sign-off.

Between each part, output exactly this on its own line:
<break time="1.5s" />

Write in a warm, clear, conversational tone. Do not include section labels, headers, \
stage directions, or any other formatting. \
Do not use Hebrew terms without briefly explaining them in English.

Torah portion text:
{parashah_text}
"""


def _get_audio_duration(mp3_path: str) -> int:
    """
    Estimate MP3 duration in seconds from file size.
    Uses a rough estimate of 128 kbps = 16 KB/s.
    For production accuracy, install mutagen: pip install mutagen
    """
    try:
        from mutagen.mp3 import MP3
        audio = MP3(mp3_path)
        return int(audio.info.length)
    except ImportError:
        size_bytes = os.path.getsize(mp3_path)
        return int(size_bytes / 16_000)  # 128 kbps ≈ 16,000 bytes/sec


def generate_episode() -> None:
    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    # Determine today's episode filename
    today = datetime.now(tz=timezone.utc)
    date_str = today.strftime("%Y-%m-%d")
    os.makedirs(EPISODES_DIR, exist_ok=True)
    mp3_filename = f"{date_str}.mp3"
    mp3_path = os.path.join(EPISODES_DIR, mp3_filename)

    if os.path.exists(mp3_path):
        print(f"Episode for {date_str} already exists at {mp3_path}. Skipping.")
        return

    # Step 1: Get this week's Parashah
    print("Fetching current Parashah from Sefaria...")
    parashah = get_current_parashah()
    print(f"  Parashah: {parashah['name']} ({parashah['ref']})")

    # Step 2: Fetch the English text
    print("Fetching Torah text from Sefaria...")
    parashah_text = get_parashah_text(parashah["ref"])
    print(f"  Retrieved text ({parashah_text.count(chr(10)) + 1} lines)")

    # Step 3: Generate the podcast script with Claude
    print(f"Generating episode script with {ANTHROPIC_MODEL}...")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = EPISODE_SCRIPT_PROMPT.format(
        parashah_name=parashah["name"],
        parashah_ref=parashah["ref"],
        parashah_text=parashah_text,
    )
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    script = message.content[0].text.strip()
    print(f"  Script generated ({len(script)} characters, ~{len(script.split())} words)")

    # Save script to scripts/YYYY-MM-DD.txt
    os.makedirs(SCRIPTS_DIR, exist_ok=True)
    script_path = os.path.join(SCRIPTS_DIR, f"{date_str}.txt")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(f"Parashah: {parashah['name']} ({parashah['ref']})\n")
        f.write(f"Date: {date_str}\n\n")
        f.write(script)
    print(f"  Script saved to: {script_path}")
    print(f"\n--- SCRIPT ---\n{script}\n--- END SCRIPT ---\n")

    # Step 4: Convert script to MP3
    print("Converting script to audio with ElevenLabs...")
    text_to_mp3(script, mp3_path)

    # Step 5: Update the RSS feed
    mp3_size = os.path.getsize(mp3_path)
    duration = _get_audio_duration(mp3_path)
    episode_title = f"{parashah['name']} — {date_str}"
    episode_description = (
        f"This week's Torah portion is {parashah['name']} ({parashah['ref']}). "
        f"A brief summary of the key events and themes."
    )

    print("Updating RSS feed...")
    add_episode(
        title=episode_title,
        description=episode_description,
        pub_date=today,
        mp3_filename=mp3_filename,
        mp3_size_bytes=mp3_size,
        duration_seconds=duration,
    )

    print(f"\nEpisode complete!")
    print(f"  Audio: {mp3_path}")
    print(f"  Duration: {duration // 60}m {duration % 60}s")
    print(f"  RSS feed updated: docs/feed.xml")
    print(f"  RSS URL (after push): {PODCAST_BASE_URL}/feed.xml")


if __name__ == "__main__":
    generate_episode()
