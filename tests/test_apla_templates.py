# //Pranjal Das
"""
Unit Tests for APLA Multi-Track Audio and AudioPlayer Directives
"""
import sys
from pathlib import Path

# Inject Drive D packages
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGES = _REPO_ROOT / "packages"
if _PACKAGES.exists() and str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from src.apla_templates import build_apla_telemetry_document, build_audio_player_directive, calculate_reaction_timestamp_window

def test_apla_normal_ducking():
    doc = build_apla_telemetry_document("System nominal", severity="NORMAL")
    assert doc["type"] == "APLA"
    assert doc["version"] == "0.91"

    mixer = doc["mainTemplate"]["item"]
    assert mixer["type"] == "Mixer"

    ambient_audio = mixer["items"][0]
    volume_filter = ambient_audio["filter"][0]
    assert volume_filter["amount"] == "20%"

def test_apla_critical_ducking():
    doc = build_apla_telemetry_document("Critical socket leak", severity="CRITICAL")
    mixer = doc["mainTemplate"]["item"]
    ambient_audio = mixer["items"][0]
    volume_filter = ambient_audio["filter"][0]
    # Critical alerts duck ambient audio to 10%
    assert volume_filter["amount"] == "10%"

def test_audio_player_directive():
    directive = build_audio_player_directive("https://example.com/stream.mp3", offset_ms=1500)
    assert directive["type"] == "AudioPlayer.Play"
    assert directive["playBehavior"] == "REPLACE_ALL"
    assert directive["audioItem"]["stream"]["offsetInMilliseconds"] == 1500

def test_reaction_timestamp_window():
    window = calculate_reaction_timestamp_window(audio_duration_sec=2.5, start_timestamp=100.0)
    assert window["playback_finished_at"] == 102.5
    assert window["rapid_response_cutoff"] == 105.5
