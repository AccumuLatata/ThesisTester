"""Localhost realtime voice sidecar (VA-5).

Browser mic/speaker ↔ this ASGI sidecar ↔ xAI Realtime WebSocket.

The sidecar owns ``XAI_API_KEY`` and never sends it to the browser. Streamlit
only starts/registers sessions and never opens the upstream xAI socket.

Implemented with Starlette (already in the Streamlit/uvicorn stack) so CI does
not require a new hard dependency. Run with::

    python -m thesistester.assistant.voice.sidecar --host 127.0.0.1 --port 8765
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping
from urllib.parse import urlencode

from thesistester.assistant.repository import LocalThesisRepository
from thesistester.assistant.tools import AssistantTools
from thesistester.assistant.voice.contracts import VoiceTranscriptTurn
from thesistester.assistant.voice.session import (
    VoiceSessionError,
    VoiceSessionService,
    session_exceeded_ttl,
)
from thesistester.assistant.voice.settings import VoiceSettings, load_voice_settings
from thesistester.assistant.voice.tools import (
    VoiceToolError,
    VoiceToolSession,
    assert_realtime_tools_allowlisted,
    execute_voice_tool,
    realtime_function_tool_schemas,
)
from thesistester.assistant.voice.xai_realtime import (
    VoiceConfigurationError,
    realtime_websocket_url,
    require_xai_api_key,
)
from thesistester.persistence.local_store import get_store_root

logger = logging.getLogger(__name__)

DEFAULT_SIDECAR_HOST = "127.0.0.1"
DEFAULT_SIDECAR_PORT = 8765
_FORBIDDEN_LOG_KEYS = frozenset(
    {
        "authorization",
        "api_key",
        "xai_api_key",
        "client_secret",
        "token",
        "value",
        "secret",
    }
)
_TRANSCRIPT_EVENT_TYPES = frozenset(
    {
        "conversation.item.input_audio_transcription.completed",
        "response.output_audio_transcript.done",
        "response.audio_transcript.done",
    }
)
# Browser→upstream: audio buffer + barge-in only. Never allow the browser to
# inject conversation.item.create / response.create (forged tool outputs).
_BROWSER_UPSTREAM_EVENT_TYPES = frozenset(
    {
        "input_audio_buffer.append",
        "input_audio_buffer.commit",
        "input_audio_buffer.clear",
        "response.cancel",
    }
)


class SidecarError(ValueError):
    """Raised when the realtime sidecar cannot start or serve a session safely."""


UpstreamConnect = Callable[[str, str], Awaitable[Any]]


def assert_localhost_bind(host: str) -> str:
    """Accept only loopback binds (single trusted local user)."""
    if not isinstance(host, str) or not host.strip():
        raise SidecarError("Sidecar host must be a non-empty string.")
    normalized = host.strip().lower()
    if normalized not in {"127.0.0.1", "::1"}:
        raise SidecarError(
            "Realtime sidecar must bind 127.0.0.1 (or ::1); non-localhost binds are rejected."
        )
    return host.strip()


def redact_for_logs(payload: Any) -> Any:
    """Return a JSON-safe structure with secret-bearing keys removed."""
    if isinstance(payload, Mapping):
        out: dict[str, Any] = {}
        for key, value in payload.items():
            key_text = str(key)
            if key_text.lower() in _FORBIDDEN_LOG_KEYS:
                out[key_text] = "[redacted]"
                continue
            out[key_text] = redact_for_logs(value)
        return out
    if isinstance(payload, list):
        return [redact_for_logs(item) for item in payload]
    if isinstance(payload, tuple):
        return [redact_for_logs(item) for item in payload]
    return payload


def build_realtime_session_update(
    *,
    instructions: str,
    voice: str,
    settings: VoiceSettings | None = None,
    include_tools: bool = True,
) -> dict[str, Any]:
    """Build an xAI ``session.update`` payload with VA-3 function tools only."""
    resolved = settings or load_voice_settings()
    if not isinstance(instructions, str) or not instructions.strip():
        raise SidecarError("Realtime session instructions must be non-empty.")
    if not isinstance(voice, str) or not voice.strip():
        raise SidecarError("Realtime session voice must be non-empty.")
    tools = list(realtime_function_tool_schemas()) if include_tools else []
    assert_realtime_tools_allowlisted(tools)
    # Fail closed: never attach search/mcp even if config later flips.
    if resolved.allow_web_search:
        logger.warning(
            "assistant.voice.allow_web_search=true is ignored for realtime sessions; "
            "search/mcp tools remain disabled."
        )
    session: dict[str, Any] = {
        "voice": voice.strip(),
        "instructions": instructions.strip(),
        "turn_detection": {"type": "server_vad"},
        # Client sends/receives raw PCM16 frames; enable binary transport and
        # input transcription so user turns flush into the voice session record.
        "audio": {
            "input": {
                "format": {"type": "audio/pcm", "rate": 24000},
                "transport": "binary",
                "transcription": {"model": "grok-transcribe"},
            },
            "output": {
                "format": {"type": "audio/pcm", "rate": 24000},
                "transport": "binary",
            },
        },
        "tools": tools,
    }
    payload = {"type": "session.update", "session": session}
    assert_realtime_tools_allowlisted(payload["session"]["tools"])
    return payload


def build_function_call_output_events(
    *,
    call_id: str,
    output: Mapping[str, Any] | list[Any] | str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return conversation.item.create + response.create for one tool result."""
    if not isinstance(call_id, str) or not call_id.strip():
        raise SidecarError("function_call_output requires a non-empty call_id.")
    if isinstance(output, str):
        encoded = output
    else:
        encoded = json.dumps(output if output is not None else {}, default=str)
    create_item = {
        "type": "conversation.item.create",
        "item": {
            "type": "function_call_output",
            "call_id": call_id.strip(),
            "output": encoded,
        },
    }
    return create_item, {"type": "response.create"}


def execute_realtime_tool_bridge(
    *,
    name: str,
    arguments: Any,
    tool_session: VoiceToolSession,
) -> dict[str, Any]:
    """Run one VA-3 tool for a realtime function_call (deny-by-default)."""
    parsed_args: dict[str, Any]
    if arguments is None or arguments == "":
        parsed_args = {}
    elif isinstance(arguments, Mapping):
        parsed_args = dict(arguments)
    elif isinstance(arguments, str):
        try:
            loaded = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise VoiceToolError("function_call arguments must be valid JSON.") from exc
        if loaded is None:
            parsed_args = {}
        elif not isinstance(loaded, Mapping):
            raise VoiceToolError("function_call arguments must decode to an object.")
        else:
            parsed_args = dict(loaded)
    else:
        raise VoiceToolError("function_call arguments must be a JSON object.")
    return execute_voice_tool(name, parsed_args, session=tool_session)


def extract_transcript_from_event(event: Mapping[str, Any]) -> tuple[str, str] | None:
    """Return ``(role, text)`` for transcript-bearing realtime events."""
    if not isinstance(event, Mapping):
        return None
    event_type = str(event.get("type") or "")
    if event_type not in _TRANSCRIPT_EVENT_TYPES:
        return None
    text = event.get("transcript")
    if not isinstance(text, str) or not text.strip():
        text = event.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    if "input_audio_transcription" in event_type:
        return "user", text.strip()
    return "assistant", text.strip()


@dataclass
class SidecarRuntime:
    """Process-local registry for active realtime voice sessions."""

    service: VoiceSessionService
    settings: VoiceSettings
    host: str = DEFAULT_SIDECAR_HOST
    port: int = DEFAULT_SIDECAR_PORT
    upstream_connect: UpstreamConnect | None = None
    _active: dict[str, dict[str, Any]] = field(default_factory=dict)

    def public_base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def register_session(
        self,
        *,
        thesis_id: str,
        run_id: str,
        expected_hash: str,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.settings.enabled:
            raise SidecarError(
                "Voice is disabled (assistant.voice.enabled=false). "
                "Enable it before starting the realtime sidecar."
            )
        record = self.service.create_session(
            thesis_id,
            run_id=run_id,
            expected_hash=expected_hash,
            mode="realtime",
            channel="results_qa",
            conversation_id=conversation_id,
        )
        self._active[record.session_id] = {
            "thesis_id": thesis_id,
            "conversation_id": conversation_id,
            "created_at": record.created_at,
        }
        return {
            "session_id": record.session_id,
            "thesis_id": thesis_id,
            "run_id": record.run_id,
            "channel": record.channel,
            "mode": record.mode,
            "ws_path": f"/v1/realtime/{record.session_id}",
            "client_url": (
                f"{self.public_base_url()}/client?" + urlencode({"session_id": record.session_id})
            ),
            "max_session_minutes": self.settings.max_session_minutes,
            # Never include API keys / tokens in public responses.
        }

    def require_active(self, session_id: str) -> tuple[str, str | None]:
        meta = self._active.get(session_id)
        if meta is None:
            # Allow reconnect from persisted active record.
            # thesis_id is required by repository API — scan is avoided; caller
            # must register via POST /v1/sessions in this process.
            raise SidecarError("Realtime session is not registered in this sidecar process.")
        thesis_id = str(meta["thesis_id"])
        record = self.service.repository.get_voice_session(thesis_id, session_id)
        if record.status != "active":
            raise SidecarError("Realtime session is not active.")
        if session_exceeded_ttl(record, max_session_minutes=self.settings.max_session_minutes):
            self.end_session(session_id)
            raise SidecarError("Realtime session exceeded max_session_minutes.")
        return thesis_id, meta.get("conversation_id")

    def end_session(self, session_id: str, *, missing_ok: bool = False) -> dict[str, Any]:
        meta = self._active.pop(session_id, None)
        if meta is None:
            # TTL / disconnect races may end the same session twice.
            if missing_ok:
                return {
                    "session_id": session_id,
                    "status": "ended",
                    "transcript_turns": 0,
                    "tool_invocations": 0,
                    "noop": True,
                }
            raise SidecarError("Realtime session is not registered in this sidecar process.")
        thesis_id = str(meta["thesis_id"])
        conversation_id = meta.get("conversation_id")
        ended = self.service.end_session(
            thesis_id,
            session_id,
            conversation_id=conversation_id if isinstance(conversation_id, str) else None,
        )
        return {
            "session_id": ended.session_id,
            "status": ended.status,
            "transcript_turns": len(ended.transcript),
            "tool_invocations": len(ended.tool_invocations),
        }


def _html_client_page(*, session_id: str) -> str:
    """Minimal localhost mic/speaker page (PCM 24 kHz ↔ sidecar WS)."""
    safe_id = json.dumps(session_id)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>ThesisTester realtime voice</title>
  <style>
    body {{ font-family: Georgia, serif; margin: 2rem; background: #f6f3ee; color: #1b1b1b; }}
    button {{ margin-right: 0.5rem; padding: 0.5rem 0.9rem; }}
    #log {{ white-space: pre-wrap; margin-top: 1rem; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <h1>ThesisTester realtime voice</h1>
  <p>Local sidecar only. The xAI key never reaches this page.</p>
  <button id="start">Start mic</button>
  <button id="stop" disabled>Stop</button>
  <div id="log"></div>
  <script>
    const sessionId = {safe_id};
    const logEl = document.getElementById('log');
    const startBtn = document.getElementById('start');
    const stopBtn = document.getElementById('stop');
    let ws = null;
    let audioCtx = null;
    let processor = null;
    let source = null;
    let mediaStream = None;
    let playTime = 0;

    function log(msg) {{
      logEl.textContent += msg + "\\n";
    }}

    function downsampleTo24k(float32, inputRate) {{
      if (inputRate === 24000) return float32;
      const ratio = inputRate / 24000;
      const length = Math.floor(float32.length / ratio);
      const out = new Float32Array(length);
      for (let i = 0; i < length; i++) out[i] = float32[Math.floor(i * ratio)];
      return out;
    }}

    function floatTo16BitPCM(float32) {{
      const out = new Int16Array(float32.length);
      for (let i = 0; i < float32.length; i++) {{
        const s = Math.max(-1, Math.min(1, float32[i]));
        out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }}
      return out;
    }}

    function playPcm16(arrayBuffer) {{
      if (!audioCtx) return;
      const pcm = new Int16Array(arrayBuffer);
      const floats = new Float32Array(pcm.length);
      for (let i = 0; i < pcm.length; i++) floats[i] = pcm[i] / 32768;
      const buffer = audioCtx.createBuffer(1, floats.length, 24000);
      buffer.copyToChannel(floats, 0);
      const src = audioCtx.createBufferSource();
      src.buffer = buffer;
      src.connect(audioCtx.destination);
      const now = audioCtx.currentTime;
      if (playTime < now) playTime = now;
      src.start(playTime);
      playTime += buffer.duration;
    }}

    async function start() {{
      audioCtx = new (window.AudioContext || window.webkitAudioContext)({{ sampleRate: 48000 }});
      mediaStream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      ws = new WebSocket(proto + '://' + location.host + '/v1/realtime/' + sessionId);
      ws.binaryType = 'arraybuffer';
      ws.onopen = () => log('connected');
      ws.onclose = () => log('disconnected');
      ws.onerror = () => log('socket error');
      ws.onmessage = (ev) => {{
        if (typeof ev.data !== 'string') {{
          playPcm16(ev.data);
          return;
        }}
        let event;
        try {{ event = JSON.parse(ev.data); }} catch (e) {{ return; }}
        if (event.type === 'response.output_audio.delta' && event.delta) {{
          const raw = atob(event.delta);
          const bytes = new Uint8Array(raw.length);
          for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
          playPcm16(bytes.buffer);
        }} else if (event.type === 'sidecar.error') {{
          log('error: ' + (event.message || 'unknown'));
        }} else if (event.type && event.type.indexOf('transcript') !== -1) {{
          log(event.type + ': ' + (event.transcript || event.text || ''));
        }}
      }};
      source = audioCtx.createMediaStreamSource(mediaStream);
      processor = audioCtx.createScriptProcessor(4096, 1, 1);
      processor.onaudioprocess = (e) => {{
        if (!ws || ws.readyState !== 1) return;
        const input = e.inputBuffer.getChannelData(0);
        const down = downsampleTo24k(input, audioCtx.sampleRate);
        const pcm = floatTo16BitPCM(down);
        ws.send(pcm.buffer);
      }};
      source.connect(processor);
      processor.connect(audioCtx.destination);
      startBtn.disabled = true;
      stopBtn.disabled = false;
    }}

    function stop() {{
      if (processor) processor.disconnect();
      if (source) source.disconnect();
      if (mediaStream) mediaStream.getTracks().forEach(t => t.stop());
      if (ws) ws.close();
      if (audioCtx) audioCtx.close();
      startBtn.disabled = false;
      stopBtn.disabled = true;
      log('stopped');
    }}

    startBtn.onclick = () => start().catch(err => log(String(err)));
    stopBtn.onclick = stop;
  </script>
</body>
</html>
"""


def create_sidecar_app(runtime: SidecarRuntime):
    """Build the Starlette ASGI app for the localhost realtime sidecar."""
    try:
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
        from starlette.routing import Route, WebSocketRoute
        from starlette.websockets import WebSocket as StarletteWebSocket
    except ImportError as exc:  # pragma: no cover - starlette ships with Streamlit stack
        raise SidecarError("Starlette is required to run the realtime voice sidecar.") from exc

    async def health(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "host": runtime.host,
                "port": runtime.port,
                "voice_enabled": runtime.settings.enabled,
                "mode": runtime.settings.mode,
                "model": runtime.settings.model,
            }
        )

    async def create_session(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Request body must be JSON."}, status_code=400)
        if not isinstance(body, Mapping):
            return JSONResponse({"error": "Request body must be an object."}, status_code=400)
        try:
            public = runtime.register_session(
                thesis_id=str(body.get("thesis_id") or ""),
                run_id=str(body.get("run_id") or ""),
                expected_hash=str(body.get("expected_hash") or ""),
                conversation_id=(
                    str(body["conversation_id"])
                    if isinstance(body.get("conversation_id"), str)
                    else None
                ),
            )
        except (SidecarError, VoiceSessionError, VoiceConfigurationError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse(public)

    async def end_session(request: Request) -> JSONResponse:
        session_id = request.path_params.get("session_id", "")
        try:
            payload = runtime.end_session(str(session_id))
        except (SidecarError, VoiceSessionError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse(payload)

    async def client_page(request: Request) -> HTMLResponse:
        session_id = str(request.query_params.get("session_id") or "").strip()
        if not session_id:
            return HTMLResponse("Missing session_id query parameter.", status_code=400)
        return HTMLResponse(_html_client_page(session_id=session_id))

    async def root(_: Request) -> PlainTextResponse:
        return PlainTextResponse(
            "ThesisTester voice sidecar. POST /v1/sessions then open /client?session_id=…\n"
        )

    async def realtime_ws(websocket: StarletteWebSocket) -> None:
        session_id = str(websocket.path_params.get("session_id") or "")
        await websocket.accept()
        try:
            thesis_id, conversation_id = runtime.require_active(session_id)
        except SidecarError as exc:
            await websocket.send_json({"type": "sidecar.error", "message": str(exc)})
            await websocket.close()
            return

        record = runtime.service.repository.get_voice_session(thesis_id, session_id)
        instructions = runtime.service.build_honesty_instructions(record)
        session_update = build_realtime_session_update(
            instructions=instructions,
            voice=runtime.settings.voice,
            settings=runtime.settings,
        )
        try:
            api_key = require_xai_api_key()
        except VoiceConfigurationError as exc:
            await websocket.send_json({"type": "sidecar.error", "message": str(exc)})
            await websocket.close()
            return

        upstream_url = realtime_websocket_url(settings=runtime.settings)
        connect = runtime.upstream_connect or _default_upstream_connect
        upstream = None
        try:
            upstream = await connect(upstream_url, api_key)
            await _upstream_send_json(upstream, session_update)
            tool_session = runtime.service.tool_session(thesis_id, session_id)
            await asyncio.gather(
                _pump_browser_to_upstream(
                    websocket,
                    upstream,
                    runtime=runtime,
                    thesis_id=thesis_id,
                    session_id=session_id,
                ),
                _pump_upstream_to_browser(
                    websocket,
                    upstream,
                    runtime=runtime,
                    thesis_id=thesis_id,
                    session_id=session_id,
                    conversation_id=conversation_id,
                    tool_session=tool_session,
                ),
            )
        except Exception as exc:
            logger.info("Realtime bridge ended: %s", type(exc).__name__)
            try:
                await websocket.send_json(
                    {"type": "sidecar.error", "message": "Realtime bridge closed."}
                )
            except Exception:
                pass
        finally:
            if upstream is not None:
                await _upstream_close(upstream)
            try:
                await websocket.close()
            except Exception:
                pass
            # Best-effort end/flush when the socket drops.
            try:
                runtime.end_session(session_id, missing_ok=True)
            except Exception:
                pass

    routes = [
        Route("/", root),
        Route("/health", health),
        Route("/client", client_page),
        Route("/v1/sessions", create_session, methods=["POST"]),
        Route("/v1/sessions/{session_id}/end", end_session, methods=["POST"]),
        WebSocketRoute("/v1/realtime/{session_id}", realtime_ws),
    ]
    return Starlette(routes=routes)


async def _default_upstream_connect(url: str, api_key: str) -> Any:
    try:
        import websockets
    except ImportError as exc:  # pragma: no cover
        raise SidecarError("websockets package is required for upstream xAI connections.") from exc
    # Never log api_key.
    return await websockets.connect(
        url,
        additional_headers={"Authorization": f"Bearer {api_key}"},
        max_size=8 * 1024 * 1024,
    )


async def _upstream_send_json(upstream: Any, payload: Mapping[str, Any]) -> None:
    await upstream.send(json.dumps(payload))


async def _upstream_close(upstream: Any) -> None:
    close = getattr(upstream, "close", None)
    if callable(close):
        result = close()
        if asyncio.iscoroutine(result):
            await result


async def _pump_browser_to_upstream(
    browser_ws: Any,
    upstream: Any,
    *,
    runtime: SidecarRuntime,
    thesis_id: str,
    session_id: str,
) -> None:
    from starlette.websockets import WebSocketDisconnect

    while True:
        if session_exceeded_ttl(
            runtime.service.repository.get_voice_session(thesis_id, session_id),
            max_session_minutes=runtime.settings.max_session_minutes,
        ):
            await browser_ws.send_json(
                {
                    "type": "sidecar.error",
                    "message": "Realtime session exceeded max_session_minutes.",
                }
            )
            runtime.end_session(session_id, missing_ok=True)
            await _upstream_close(upstream)
            try:
                await browser_ws.close()
            except Exception:
                pass
            return
        try:
            message = await browser_ws.receive()
        except WebSocketDisconnect:
            return
        if message.get("type") == "websocket.disconnect":
            return
        if "bytes" in message and message["bytes"] is not None:
            await upstream.send(message["bytes"])
            continue
        text = message.get("text")
        if isinstance(text, str) and text:
            # Browser may send JSON control events; forward only audio/barge-in.
            try:
                event = json.loads(text)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(event, Mapping)
                and str(event.get("type") or "") in _BROWSER_UPSTREAM_EVENT_TYPES
            ):
                await _upstream_send_json(upstream, event)


async def _pump_upstream_to_browser(
    browser_ws: Any,
    upstream: Any,
    *,
    runtime: SidecarRuntime,
    thesis_id: str,
    session_id: str,
    conversation_id: str | None,
    tool_session: VoiceToolSession,
) -> None:
    _ = conversation_id  # reserved for periodic mid-session flush
    while True:
        if session_exceeded_ttl(
            runtime.service.repository.get_voice_session(thesis_id, session_id),
            max_session_minutes=runtime.settings.max_session_minutes,
        ):
            await browser_ws.send_json(
                {
                    "type": "sidecar.error",
                    "message": "Realtime session exceeded max_session_minutes.",
                }
            )
            runtime.end_session(session_id, missing_ok=True)
            await _upstream_close(upstream)
            try:
                await browser_ws.close()
            except Exception:
                pass
            return
        raw = await upstream.recv()
        if isinstance(raw, (bytes, bytearray)):
            await browser_ws.send_bytes(bytes(raw))
            continue
        if not isinstance(raw, str):
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, Mapping):
            continue
        # Never echo secrets upstream may include in diagnostics.
        safe_event = redact_for_logs(event)
        event_type = str(event.get("type") or "")

        if event_type == "response.function_call_arguments.done":
            call_id = str(event.get("call_id") or "").strip()
            name = str(event.get("name") or "").strip()
            if not call_id:
                await browser_ws.send_json(
                    {
                        "type": "sidecar.error",
                        "message": "Upstream function_call missing call_id; tool bridge skipped.",
                    }
                )
                continue
            try:
                result = execute_realtime_tool_bridge(
                    name=name,
                    arguments=event.get("arguments"),
                    tool_session=tool_session,
                )
            except (VoiceToolError, VoiceSessionError, SidecarError) as exc:
                result = {"ok": False, "error": str(exc), "tool_name": name}
            try:
                create_item, response_create = build_function_call_output_events(
                    call_id=call_id,
                    output=result,
                )
            except SidecarError as exc:
                await browser_ws.send_json({"type": "sidecar.error", "message": str(exc)})
                continue
            await _upstream_send_json(upstream, create_item)
            await _upstream_send_json(upstream, response_create)
            # Inform browser without tool payload secrets.
            await browser_ws.send_json(
                {
                    "type": "sidecar.tool_result",
                    "tool_name": name,
                    "ok": bool(result.get("ok")) if isinstance(result, Mapping) else False,
                }
            )
            continue

        transcript = extract_transcript_from_event(event)
        if transcript is not None:
            role, text = transcript
            try:
                runtime.service.append_transcript_turn(
                    thesis_id,
                    session_id,
                    VoiceTranscriptTurn(
                        role=role,
                        text=text,
                        channel="results_qa",
                        path="realtime",
                        created_at=datetime.now(timezone.utc).isoformat(),
                    ),
                )
            except (VoiceSessionError, Exception):
                pass

        # Forward JSON events to browser (redacted on error diagnostics).
        if event_type.startswith("response.output_audio") or event_type.endswith("transcript.done"):
            await browser_ws.send_json(dict(event))
        elif event_type in {"session.updated", "session.created", "error"}:
            await browser_ws.send_json(safe_event if event_type == "error" else dict(event))


def build_default_runtime(
    *,
    host: str = DEFAULT_SIDECAR_HOST,
    port: int = DEFAULT_SIDECAR_PORT,
    settings: VoiceSettings | None = None,
    repository: LocalThesisRepository | None = None,
    tools: AssistantTools | None = None,
    upstream_connect: UpstreamConnect | None = None,
) -> SidecarRuntime:
    """Construct a production-shaped sidecar runtime bound to local store roots."""
    bind_host = assert_localhost_bind(host)
    if not isinstance(port, int) or isinstance(port, bool) or port < 1 or port > 65535:
        raise SidecarError("Sidecar port must be an integer in 1..65535.")
    resolved_settings = settings or load_voice_settings()
    roots = (Path.cwd().resolve(), get_store_root().resolve())
    resolved_tools = tools or AssistantTools(data_roots=roots)
    resolved_repo = repository or LocalThesisRepository()
    service = VoiceSessionService(
        resolved_repo,
        tools=resolved_tools,
        settings=resolved_settings,
    )
    return SidecarRuntime(
        service=service,
        settings=resolved_settings,
        host=bind_host,
        port=port,
        upstream_connect=upstream_connect,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry for ``python -m thesistester.assistant.voice.sidecar``."""
    parser = argparse.ArgumentParser(description="ThesisTester localhost realtime voice sidecar")
    parser.add_argument("--host", default=DEFAULT_SIDECAR_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_SIDECAR_PORT)
    args = parser.parse_args(argv)
    host = assert_localhost_bind(args.host)
    runtime = build_default_runtime(host=host, port=args.port)
    app = create_sidecar_app(runtime)
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise SidecarError("uvicorn is required to run the realtime voice sidecar.") from exc
    # Refuse non-localhost again at server boot.
    assert_localhost_bind(host)
    uvicorn.run(app, host=host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
