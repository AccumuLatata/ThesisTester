"""Realtime voice agent package (VA-series).

VA-0 contracts/settings, VA-2 xAI helpers + sessions, VA-3 read-only tools,
VA-4 push-to-talk spoken Discuss/Help. Realtime sidecar is VA-5.
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
    HELP_NO_OPENAI_REMEDIATION,
    UNGROUNDED_SPOKEN_REMEDIATION,
    audit_spoken_text,
    extract_digit_tokens,
    format_speakable_help_reply,
    format_speakable_results_reply,
    format_speakable_tool_result,
    normalize_number_token,
)
from thesistester.assistant.voice.intent import VoiceIntent, VoiceIntentRouter
from thesistester.assistant.voice.session import (
    PushToTalkTurnResult,
    VoiceSessionError,
    VoiceSessionService,
    build_honesty_instructions,
    run_push_to_talk_turn,
)
from thesistester.assistant.voice.settings import (
    VoiceSettings,
    VoiceSettingsError,
    clear_voice_ui_overrides,
    load_voice_settings,
    load_voice_ui_overrides,
    resolve_voice_settings,
    save_voice_ui_overrides,
    with_voice_overrides,
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
    "HELP_NO_OPENAI_REMEDIATION",
    "UNGROUNDED_SPOKEN_REMEDIATION",
    "VOICE_CONTRACT_SCHEMA_VERSION",
    "VOICE_SESSION_KIND",
    "VOICE_TOOL_SCHEMAS",
    "EphemeralToken",
    "GroundingVerdict",
    "PushToTalkTurnResult",
    "VoiceConfigurationError",
    "VoiceContractError",
    "VoiceIntent",
    "VoiceIntentRouter",
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
    "format_speakable_help_reply",
    "format_speakable_results_reply",
    "format_speakable_tool_result",
    "clear_voice_ui_overrides",
    "load_voice_settings",
    "load_voice_ui_overrides",
    "mint_ephemeral_token",
    "resolve_voice_settings",
    "save_voice_ui_overrides",
    "with_voice_overrides",
    "normalize_number_token",
    "require_xai_api_key",
    "run_push_to_talk_turn",
    "speech_to_text",
    "text_to_speech",
    "validate_voice_session_id",
]
