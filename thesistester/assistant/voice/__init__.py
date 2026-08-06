"""Realtime voice agent package (VA-series).

VA-0 freezes contracts/settings. VA-2 adds xAI helpers + session service.
No mic UI or tool router yet (VA-3/VA-4).
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
from thesistester.assistant.voice.session import (
    VoiceSessionError,
    VoiceSessionService,
    build_honesty_instructions,
)
from thesistester.assistant.voice.settings import (
    VoiceSettings,
    VoiceSettingsError,
    load_voice_settings,
)
from thesistester.assistant.voice.xai_realtime import (
    EphemeralToken,
    VoiceConfigurationError,
    VoiceProviderError,
    mint_ephemeral_token,
    require_xai_api_key,
    speech_to_text,
    text_to_speech,
)

__all__ = [
    "VOICE_CONTRACT_SCHEMA_VERSION",
    "VOICE_SESSION_KIND",
    "EphemeralToken",
    "GroundingVerdict",
    "VoiceConfigurationError",
    "VoiceContractError",
    "VoiceProviderError",
    "VoiceSessionError",
    "VoiceSessionRecord",
    "VoiceSessionService",
    "VoiceSettings",
    "VoiceSettingsError",
    "VoiceToolInvocation",
    "VoiceTranscriptTurn",
    "build_honesty_instructions",
    "coerce_transcript",
    "load_voice_settings",
    "mint_ephemeral_token",
    "require_xai_api_key",
    "speech_to_text",
    "text_to_speech",
    "validate_voice_session_id",
]
