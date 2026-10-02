# Telephony decision point — proposal only

No telephony provider has been selected or integrated. Implementation is paused
at the user's explicit instruction. Official documentation checked 2026-09-27.

| Option | Audio transport | Estimated complexity |
|---|---|---|
| Twilio bidirectional Media Streams | WSS JSON/base64, mono μ-law 8 kHz; convert to/from Ava's 16 kHz PCM; media/mark/clear | Moderate: answer webhook/TwiML, signatures, codec conversion and playback tracking |
| Telnyx Media Streaming | Bidirectional WSS with configured codec; L16 16 kHz or PCMU 8 kHz; verify framing/byte order | Moderate: call-control webhooks/commands, codec/sequence handling and clear/mark |
| Plivo Audio Streaming | Bidirectional WSS with linear PCM 16 kHz or μ-law 8 kHz; provider playback/clear framing | Moderate; 16 kHz can reduce resampling, but auth/lifecycle/interruption still need testing |

Complexity is an engineering estimate. All require a suitable number/account,
public HTTPS/WSS endpoint, credentials and real-call QA. Country availability,
regulatory onboarding, data region and volume must be known before pricing or
choosing. No purchase is implied.

Sources: [Twilio audio/control messages](https://www.twilio.com/docs/voice/media-streams/websocket-messages),
[Twilio stream setup](https://www.twilio.com/docs/voice/media-streams),
[Telnyx media streaming](https://developers.telnyx.com/docs/voice/programmable-voice/media-streaming),
[Plivo formats](https://docs.plivo.com/docs/voice/api/audio-streams),
[Plivo protocol](https://docs.plivo.com/docs/voice-agents/audio-streaming/concepts/audio-streaming-reference).

## Proposed adapter boundary

```text
Caller ↔ telephone provider ↔ provider adapter ↔ Ava voice session
                                                 ↕
                                    receptionist / calendar / DB
```

The adapter owns provider authentication, call IDs/lifecycle, codec framing,
resampling, audio send/receive, playback completion/clear, DTMF and optional
transfer/hangup. Ava owns STT/LLM/TTS, interruption decisions, business state,
tools, scheduling and persistent records. No provider SDK objects enter the
agent/scheduling modules. Proposed operations are input PCM, output PCM tagged
by reply ID, clear playback, playback completion and call start/end.

These are proposed responsibilities, not a shipped phone interface.

Vapi is a managed voice-orchestration alternative. Its documented WebSocket
transport sends audio to Vapi assistants; this is not evidence of a transparent
phone-to-Ava bridge. A custom-LLM arrangement could preserve business tools while
moving voice orchestration into Vapi, changing our intended ownership boundary.
Sources: [Vapi WebSocket transport](https://docs.vapi.ai/calls/websocket-transport),
[Vapi data flow](https://docs.vapi.ai/security-and-privacy/data-flow).

The architectural recommendation is raw bidirectional media, keeping Ava's
runtime. No vendor is selected. Before implementation, establish the initial
phone-number country/market and preferred provider or existing account.
