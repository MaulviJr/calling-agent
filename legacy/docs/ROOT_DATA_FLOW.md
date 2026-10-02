# Data flow

## Input and output

While a finalized caller turn is being processed: after one second, optionally
speak one short waiting acknowledgement → finish that stream → speak final reply.
No second controller call or synthetic caller transcript is created. Interruption
cancels both acknowledgement and final speech via the same turn flag. The opening
greeting and fast responses skip this acknowledgement path.

Browser connection → STT connected → `ready` displays configured greeting →
VoiceSession queues outbound greeting → ElevenLabs → binary PCM playback.
No caller utterance or LLM request is needed. StartOfTurn cancels the greeting
through the normal interruption path; normal caller turns follow on the same worker.

```text
Microphone → bounded 16 kHz PCM queue → Deepgram Flux listener
Browser mic → unchanged audio worklet → same-origin /api/voice WebSocket
    → transparent Node gateway → FastAPI browser transport → Deepgram Flux
    EndOfTurn → deduplicate → agent worker → receptionist
    Update → no LLM call
    StartOfTurn → cancel old reply; browser clears queued output

Validated reply → ElevenLabs streaming PCM → speaker / browser output
```

The listener keeps processing while reasoning or playback is busy. User turns
remain in state even when an old audio reply is cancelled. Generated text and
delivery status are separate; interrupted confirmation is not permission to book.

Turn finalization uses a configurable 0.7 confidence threshold and 2000 ms maximum
silence wait. This is a speech-end wait, separate from model and TTS latency.
Knowledge/conversation/clarification uses one structured semantic call. Action
proposals use at most one additional bounded wording call. No grounding review.

## Agent

```text
Final transcript -> redact -> current settings, workflow, recent history
  -> existing safety/privacy/explicit-confirmation guards
  -> bounded facts packet + compact discourse
  -> one SemanticDraft (intent, sources, entities, answer, memory proposal)
      -> knowledge/conversation: local validation -> accepted text or fallback
      -> action: existing controller/tools -> exact consent/receipt or one wording call
  -> persist state, transcript, idempotent receipt -> TTS/caller output
```

Python owns tool execution, business truth, consent and calendar operations.
Knowledge turns preserve pending workflow state. Discourse stores validated
references; authoritative settings reload each turn. Interrupted delivery cannot
unlock consent to another turn. See [docs/SEMANTIC_ROUTING.md](docs/SEMANTIC_ROUTING.md)
for schemas, validation and limitations. The saved replay is controlled offline
evidence, not a live-model interpretation test.
