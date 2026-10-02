# Ava on Vapi: read-only conversation comparison

This milestone adds two tools and an isolated FastAPI app. It does not book,
cancel, reschedule, save messages, or persist calls. The custom app is unchanged.
No vector database, agent framework, new Python dependency, or migration is needed.

## Runtime

Caller speech → Vapi STT → Vapi conversation model with its call history →
`get_staff_information` → authenticated `POST /api/vapi/tools` → assistant ID
mapped to an existing Ava business → validated BusinessSettings → active staff
records → JSON serialized into the matching `results[].result` → Vapi model →
Vapi ElevenLabs voice → caller.

The backend receives structured pagination arguments, not utterances. It does
not recognize example phrases, resolve pronouns, generate wording, or infer
roles. Vapi handles those conversational tasks. Staff roles and qualifications
are separate fields. The directory does not assign a treating clinician.

Business information returns public business details, all active services, and
paged FAQs. Staff information returns paged active staff. Pagination metadata
prevents a partial directory being described as complete. Each request reloads
settings. Unknown fields remain null/empty, with explicit missing-data semantics.
FAQ prose cannot establish staff roles or qualifications.

## Local setup

If the tools have already been registered through `POST /tool`, set both
`VAPI_BUSINESS_TOOL_ID` and `VAPI_STAFF_TOOL_ID` in `.env`. The generator then
attaches these saved resources through `model.toolIds` instead of embedding
inline definitions. Saved tools appear in the dashboard's Tools list; inline
tools do not appear as separately managed resources. When a tunnel or credential
changes, update the saved tools' server configurations as well as the assistant
event server. Regenerating assistant JSON alone does not update saved tools.

Keep your existing app running as before. Add the blank Vapi variables from
`.env.example` to your private `.env`; do not overwrite existing keys.

1. Generate a random webhook token privately, at least 32 characters long, and
   set `VAPI_WEBHOOK_TOKEN`. This is a dedicated service credential, not a Vapi
   API key or dashboard login.
2. Use the existing database and its existing business ID. Do not bootstrap a
   second clinic. Add verified staff/services/FAQs using the existing settings
   UI, including parking, accessibility and walk-in policy where known.
3. In Vapi create a Custom Credential using an `Authorization` Bearer token
   matching `VAPI_WEBHOOK_TOKEN`. Set its ID as `VAPI_SERVER_CREDENTIAL_ID`.
4. Set `VAPI_PUBLIC_BASE_URL` to your HTTPS tunnel/proxy base URL and
   `VAPI_ELEVENLABS_VOICE_ID` to your chosen voice. Provider/model settings are
   environment-driven and should match providers enabled in your Vapi account.
5. Generate configuration without making network calls:

   ```powershell
   .\venv\Scripts\python.exe -m backend.app.vapi_config > vapi-assistant.json
   ```

   The generated JSON contains configuration and credential IDs, not tokens.
   Create a **saved assistant** in Vapi using that JSON (`POST /assistant` via
   Vapi's API explorer, or the equivalent dashboard settings). Do not pass a
   transient assistant or override its server URLs per call. The configuration
   embeds exactly two modern Function tools under `model.tools`, each with its
   own authenticated server URL. No deprecated `model.functions` is used.
6. Set `VAPI_ASSISTANT_BUSINESS_MAP` in your private `.env`:

   ```dotenv
   VAPI_ASSISTANT_BUSINESS_MAP={"YOUR_SAVED_ASSISTANT_ID":"YOUR_EXISTING_BUSINESS_ID"}
   ```

   Multiple assistant IDs may map to different existing businesses. Mapping
   values are server configuration, never tool arguments. Unknown assistants
   and conflicting expanded assistant metadata are rejected.
7. Run the isolated app on an unused port (8002 avoids the existing 8000/8001):

   ```powershell
   .\venv\Scripts\python.exe -m uvicorn backend.app.vapi_api:build_app --factory --host 127.0.0.1 --port 8002
   ```

   Forward only `/api/vapi/tools`, `/api/vapi/events` and optionally `/health`
   through your HTTPS tunnel/proxy. Authentication is required on both POST
   routes, independently of browser Origin/cookies. The existing staff API's
   Origin and session rules are unchanged. Restart this app after mapping/token
   changes. Real voice calls consume provider/Vapi usage credits.
8. Start a browser voice test using the **saved** assistant in Vapi. No custom
   browser UI or telephone number is required for this milestone.

The app imports `business.py`, `database.py` and the new Vapi modules only. It
never imports or initializes `agent.py`, `conversation.py`, `semantic.py`, the
custom voice modules, Scheduling, Google Calendar, or provider SDKs.

## Webhook contract

Use `Authorization: Bearer <dedicated webhook token>`.

```json
{
  "message": {
    "type": "tool-calls",
    "call": {"id": "VAPI_CALL_ID", "assistantId": "SAVED_ASSISTANT_ID"},
    "toolCallList": [
      {"id": "TOOL_CALL_ID", "name": "get_staff_information", "parameters": {}}
    ]
  }
}
```

The OpenAI-style `function.name` / `function.arguments` envelope is also
accepted; arguments can be a JSON object or a JSON-encoded string. Both tools
reject unknown arguments, including caller-supplied business IDs.

Successful calls return HTTP 200 and `results[].toolCallId` plus a flat string
`result` containing structured `{success, status, data}` JSON. Tool failures
return a correlated flat string `error` containing `{success, status, code}`.
Authentication/mapping/envelope failures use HTTP 401/403/400. Bodies are limited
to 256 KiB including streamed requests; batches are limited to eight calls.

Business arguments: `faq_offset` (0–100), `faq_limit` (1–10, default 5).
Staff arguments: `offset` (0–100), `limit` (1–20, default 20).
Use returned `next_offset` to retrieve remaining pages when needed.

Read-only retries are safe: the app makes no database writes. The event route
authenticates and acknowledges events without saving them. Status events emit
concise lifecycle logs; delivery retries can repeat log lines. No transcript or
end-of-call reporting subscription is enabled. Tool logs contain IDs, allowlisted
tool names, latency and success only, never full inputs/results or credentials.

## Verification and live comparison

Run offline integration tests:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_vapi_tools.py -q
```

Tests use an independent temporary database and make no Vapi/provider calls.
They cover facts, staff roles/qualifications, inactive records, unknown data,
pagination, both webhook envelopes, authentication, tenant isolation, malformed
requests, failures, safe retries, no writes, and runtime import isolation.

Backend tests do **not** prove spoken conversational quality. Use this sequence
in a live Vapi voice call, then repeat on custom Ava with the same clinic facts:

| Caller turn | Check |
| --- | --- |
| Hey, how are you? | Natural small talk; no unnecessary tool call or repeated introduction |
| What exactly do you guys do there? | Explain actual active services |
| And who would actually treat me? | Use staff facts; do not promise a particular assignment |
| Do you have any physicians? | Use configured roles, not titles/qualifications |
| What about Abdul Hadi? | Resolve the named person from staff records |
| So he's a physiotherapist? | Confirm/correct from the actual role |
| Who was the physician again? | Resolve the earlier physician, or clarify if ambiguous |
| Is the place wheelchair accessible? | Preserve the actual FAQ conditions, or acknowledge unknown |
| What about parking? | Answer the actual parking FAQ |
| If I just show up, is that okay? | Answer actual walk-in policy without implying a booking |

Use the real directory; these names/roles in the automated fixture are test
data, not production defaults. Also test a different order, paraphrases,
corrections, interrupted answers, ambiguous names and missing FAQs. Record
factual accuracy, context errors, response latency and awkward repetition;
inspect Vapi tool logs to see which facts the model received.

The prompt guides Vapi wording; it cannot guarantee every spoken claim is
correct. This milestone establishes the backend boundary, not a measured
improvement or pre-speech factual-validation guarantee. Do not enable appointment
writes until later milestones and their confirmation/interruption tests.

Official references:
[Function tools](https://docs.vapi.ai/tools/custom-tools),
[server authentication](https://docs.vapi.ai/server-url/server-authentication),
[server events](https://docs.vapi.ai/server-url/events),
[speech configuration](https://docs.vapi.ai/customization/speech-configuration).
