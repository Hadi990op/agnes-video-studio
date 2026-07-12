"""core.audio.bgm — Background music (BGM) mixing.

Provides royalty-free procedurally-generated music tracks in several moods,
and mixes BGM with narration audio at a configurable volume level.

Tracks are generated via ffmpeg sine-wave synthesis (no copyright issues).
"""

import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

# ── BGM track definitions ──
# Each track is a 60-second loopable MP3 in assets/music/
_MUSIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "music")

BGM_TRACKS = [
    {"id": "none", "label": "No Background Music", "file": ""},
    {"id": "epic_cinematic", "label": "Epic / Cinematic", "file": "epic_cinematic.mp3"},
    {"id": "calm_ambient", "label": "Calm / Ambient", "file": "calm_ambient.mp3"},
    {"id": "action_dramatic", "label": "Action / Dramatic", "file": "action_dramatic.mp3"},
    {"id": "emotional_sad", "label": "Emotional / Sad", "file": "emotional_sad.mp3"},
    {"id": "upbeat_happy", "label": "Upbeat / Happy", "file": "upbeat_happy.mp3"},
    {"id": "mysterious_suspense", "label": "Mysterious / Suspense", "file": "mysterious_suspense.mp3"},
]


def get_bgm_track_path(track_id: str) -> Optional[str]:
    """Return the file path for a BGM track, or None if not found / 'none'."""
    if not track_id or track_id == "none":
        return None
    for track in BGM_TRACKS:
        if track["id"] == track_id and track["file"]:
            path = os.path.join(_MUSIC_DIR, track["file"])
            if os.path.exists(path):
                return path
    return None


def mix_bgm_with_narration(
    narration_path: str,
    bgm_track_id: str,
    output_path: str,
    bgm_volume: float = 0.15,
) -> str:
    """Mix background music under narration audio.

    The BGM is looped/truncated to match the narration duration, faded in/out
    at the edges, and mixed at a lower volume so narration stays clear.

    Args:
        narration_path: Path to the narration audio file (MP3/WAV).
        bgm_track_id: BGM track ID (see BGM_TRACKS). "none" = no BGM.
        output_path: Where to save the mixed audio.
        bgm_volume: BGM volume level (0.0–1.0). Default 0.15 (15%).

    Returns:
        Path to the mixed audio file. If BGM is "none" or narration doesn't
        exist, returns the narration_path unchanged.
    """
    if not narration_path or not os.path.exists(narration_path):
        return narration_path

    bgm_path = get_bgm_track_path(bgm_track_id)
    if not bgm_path:
        # No BGM — just return narration as-is
        return narration_path

    # Get narration duration
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", narration_path],
            capture_output=True, text=True, timeout=10,
        )
        duration = float(r.stdout.strip())
    except Exception:
        logger.warning("[BGM] Could not get narration duration, skipping BGM")
        return narration_path

    if duration <= 0:
        return narration_path

    # Build ffmpeg command:
    # - Input 1: narration (full volume)
    # - Input 2: BGM (looped, trimmed to duration, volume reduced, fade in/out)
    # - Mix the two streams
    fade_out_start = max(0, duration - 3)

    cmd = [
        "ffmpeg", "-y",
        "-i", narration_path,
        "-stream_loop", "-1", "-i", bgm_path,  # loop BGM infinitely
        "-filter_complex",
        f"[1:a]atrim=0:{duration},"
        f"afade=t=in:st=0:d=2,"           # fade in over 2s
        f"afade=t=out:st={fade_out_start}:d=3,"  # fade out over last 3s
        f"volume={bgm_volume}[bgm];"
        f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0",
        "-ac", "2",
        "-ar", "44100",
        "-b:a", "192k",
        output_path,
    ]

    try:
        subprocess.run(cmd, capture_output=True, timeout=60, check=True)
        logger.info(f"[BGM] Mixed BGM '{bgm_track_id}' with narration → {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error(f"[BGM] Failed to mix BGM: {e.stderr.decode(errors='replace')[:300]}")
        return narration_path
    except subprocess.TimeoutExpired:
        logger.error("[BGM] BGM mixing timed out")
        return narration_path


def get_available_tracks() -> list:
    """Return list of available BGM tracks for the API/frontend."""
    available = []
    for track in BGM_TRACKS:
        if track["id"] == "none":
            available.append(track)
            continue
        path = os.path.join(_MUSIC_DIR, track["file"])
        if os.path.exists(path):
            available.append(track)
    return available
