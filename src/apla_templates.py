# //PRANJAL DAS
"""
APLA Telemetry Audio Directives & Response Windows (src/apla_templates.py)

Generates Alexa Presentation Language for Audio (APLA) documents:
- Multi-track audio mixing with ambient telemetry beds and programmatic ducking.
- AudioPlayer stream directives for continuous monitoring sessions.
- Deterministic reaction window calculations to neutralize playback jitter.
"""
import time
from typing import Dict, Any

def build_apla_telemetry_document(speech_text: str, severity: str = "NORMAL") -> Dict[str, Any]:
    """
    Constructs an APLA document combining an ambient telemetry bed with spoken diagnostics.
    Ducks ambient hum down to 10% during critical alerts to ensure vocal intelligibility.
    """
    is_critical = severity.upper() in ["CRITICAL", "HIGH", "ALERT"]
    ambient_volume = "10%" if is_critical else "20%"
    chime_source = (
        "https://cdn.sentinelplus.dev/audio/critical_alarm.mp3"
        if is_critical else
        "https://cdn.sentinelplus.dev/audio/sonar_sweep.mp3"
    )

    return {
        "type": "APLA",
        "version": "0.91",
        "description": "Sentinel+ Multi-Track Ambient Telemetry with Programmatic Ducking",
        "mainTemplate": {
            "parameters": ["payload"],
            "item": {
                "type": "Mixer",
                "description": "Mixes continuous low-volume server drone under diagnostic voice",
                "items": [
                    {
                        "type": "Audio",
                        "description": "Background Ambient Server Room Drone",
                        "source": "https://cdn.sentinelplus.dev/audio/server_room_hum.mp3",
                        "filter": [
                            {"type": "Volume", "amount": ambient_volume},
                            {"type": "FadeIn", "duration": 400},
                            {"type": "FadeOut", "duration": 800}
                        ]
                    },
                    {
                        "type": "Sequencer",
                        "description": "Chains sonic chime before spoken SSML diagnostic",
                        "items": [
                            {
                                "type": "Audio",
                                "description": "Diagnostic Sonic Ping",
                                "source": chime_source
                            },
                            {
                                "type": "Silence",
                                "duration": 200
                            },
                            {
                                "type": "Speech",
                                "contentType": "SSML",
                                "content": f"<speak>{speech_text}</speak>"
                            }
                        ]
                    }
                ]
            }
        }
    }


def build_audio_player_directive(stream_url: str,
                                token: str = "sentinel-stream-01",
                                offset_ms: int = 0,
                                play_behavior: str = "REPLACE_ALL") -> Dict[str, Any]:
    """
    Builds the official Alexa AudioPlayer.Play directive.
    Enables background continuous audio streaming across device interruptions.
    """
    return {
        "type": "AudioPlayer.Play",
        "playBehavior": play_behavior,
        "audioItem": {
            "stream": {
                "url": stream_url,
                "token": token,
                "expectedPreviousToken": None,
                "offsetInMilliseconds": offset_ms
            },
            "metadata": {
                "title": "Sentinel+ Live Acoustic Surveillance Stream",
                "subtitle": "Autonomous Infrastructure & Security Sentry",
                "art": {
                    "sources": [
                        {"url": "https://cdn.sentinelplus.dev/img/sentinel_logo_512.png"}
                    ]
                }
            }
        }
    }


def calculate_reaction_timestamp_window(audio_duration_sec: float, start_timestamp: float) -> Dict[str, float]:
    """
    Computes an exact millisecond reaction window based on audio duration,
    compensating for playback latency and network jitter.
    """
    finish_t = start_timestamp + audio_duration_sec
    bonus_window_end = finish_t + 3.0  # 3-second rapid response threshold
    return {
        "playback_started_at": start_timestamp,
        "audio_duration_sec": audio_duration_sec,
        "playback_finished_at": finish_t,
        "rapid_response_cutoff": bonus_window_end
    }
