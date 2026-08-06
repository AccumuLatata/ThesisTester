"""Realtime voice agent package (VA-series).

VA-0 freezes contracts and settings only. No STT/TTS, tools, or UI yet.
"""

from thesistester.assistant.voice.contracts import (
    VOICE_CONTRACT_SCHEMA_VERSION,
    VOICE_SESSION_KIND,
    GroundingVerdict,
    VoiceContractError,
    VoiceSessionRecord,
    VoiceToolInvocation,
    VoiceTranscriptTurn,
    coerce_transcript,
    validate_voice_session_id,
)
from thesistester.assistant.voice.settings import (
    VoiceSettings,
    VoiceSettingsError,
    load_voice_settings,
)

__all__ = [
    "VOICE_CONTRACT_SCHEMA_VERSION",
    "VOICE_SESSION_KIND",
    "GroundingVerdict",
    "VoiceContractError",
    "VoiceSessionRecord",
    "VoiceSettings",
    "VoiceSettingsError",
    "VoiceToolInvocation",
    "VoiceTranscriptTurn",
    "coerce_transcript",
    "load_voice_settings",
    "validate_voice_session_id",
]
