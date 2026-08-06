"""Realtime voice agent package (VA-series).

VA-0 contracts/settings, VA-2 xAI helpers + sessions, VA-3 read-only tools.
No mic UI yet (VA-4).
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
from thesistester.assistant.voice.grounding import (
    audit_spoken_text,
    extract_digit_tokens,
    normalize_number_token,
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
from thesistester.assistant.voice.tools import (
    VOICE_TOOL_SCHEMAS,
    VoiceToolError,
    VoiceToolSession,
    execute_voice_tool,
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
    "VOICE_TOOL_SCHEMAS",
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
    "VoiceToolError",
    "VoiceToolInvocation",
    "VoiceToolSession",
    "VoiceTranscriptTurn",
    "audit_spoken_text",
    "build_honesty_instructions",
    "coerce_transcript",
    "execute_voice_tool",
    "extract_digit_tokens",
    "load_voice_settings",
    "mint_ephemeral_token",
    "normalize_number_token",
    "require_xai_api_key",
    "speech_to_text",
    "text_to_speech",
    "validate_voice_session_id",
]
