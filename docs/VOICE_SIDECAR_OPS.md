# Voice realtime sidecar ops (VA-5)

Local full-duplex spoken Discuss for a completed, hash-verified run uses a
**localhost-only** ASGI sidecar. Streamlit never opens the xAI WebSocket and
never embeds `XAI_API_KEY`.

Normative voice contract: [`REALTIME_VOICE_AGENT_IMPLEMENTATION.md`](REALTIME_VOICE_AGENT_IMPLEMENTATION.md).
Duplex content parity: [`DUPLEX_INTELLIGENCE_IMPLEMENTATION.md`](DUPLEX_INTELLIGENCE_IMPLEMENTATION.md).

## Prerequisites

- Voice enabled via Research Assistant **sidebar → Voice** (writes
  `config/assistant.voice.override.toml`) **or** `assistant.voice.enabled = true`
  in tracked `config/assistant.toml`
- Mode `realtime` from the same sidebar control (or TOML); PTT remains fallback
- `XAI_API_KEY` in the environment (or Streamlit Secrets) for the **sidecar process**
- Starlette + uvicorn + websockets (already present in the Streamlit stack)

## Start the sidecar

```bash
export XAI_API_KEY=…   # never commit; never paste into page modules
python -m thesistester.assistant.voice.sidecar --host 127.0.0.1 --port 8765
```

Non-loopback `--host` values are rejected (`0.0.0.0`, LAN IPs, `localhost` string).

**Connection refused / WinError 10061** means nothing is listening on
`127.0.0.1:8765` — the Streamlit page does not embed the duplex bridge. Either:

1. Start the process manually (command above — use the same port as the page
   **Sidecar port** control), or
2. In **Voice discuss (realtime)** click **Launch local sidecar** (probes
   `GET /health`, resolves `XAI_API_KEY` from env or Streamlit Secrets, then
   spawns a detached `python -m thesistester.assistant.voice.sidecar` with that
   key forwarded into the child env).

Helpers: `probe_sidecar_health`, `launch_local_sidecar`, `ensure_local_sidecar`
in `thesistester/assistant/voice/sidecar.py` (loopback-only; health requires
boolean `ok` plus sidecar host/port/mode; child-exit re-probes in case another
listener already bound the port).

## Endpoints

| Path | Role |
|---|---|
| `GET /health` | Liveness + model/mode (no secrets) |
| `POST /v1/sessions` | Create run-bound `mode=realtime` voice session; returns `client_url` |
| `WS /v1/realtime/{session_id}` | Browser PCM 24 kHz ↔ sidecar ↔ xAI; tool bridge runs here |
| `GET /client?session_id=…` | Minimal mic/speaker page |
| `POST /v1/sessions/{id}/end` | End + flush transcript/tool audits |

## Streamlit flow

1. Open Research Assistant → sidebar **Voice** → Enable + Mode **Realtime**.
2. **Discuss runs** mode → select the run → **Voice discuss (realtime)**.
3. Confirm sidecar status (green = `/health` ok). If warned, click
   **Launch local sidecar** or start the process in a terminal.
4. Click **Start realtime voice session** (page POSTs to the sidecar; sidecar
   re-reads the local override on register, so a restart is usually unnecessary).
5. Open/iframe the returned `/client` URL; speak to the bound run.
6. Closing the client ends/flushes the voice session.

Help realtime is deferred in v1 — use push-to-talk Help. Search/`mcp` tools are
never attached to `session.update` payloads.
