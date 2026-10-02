I want to migrate my existing custom AI receptionist, Ava, to Vapi.

The goal is NOT to rebuild the entire application.

I want Vapi to handle the realtime voice infrastructure:
- telephony
- STT
- turn-taking / endpointing
- interruptions / barge-in
- realtime LLM conversation
- TTS
- voice streaming

My existing backend should continue to own authoritative business logic:
- business settings
- staff information
- services
- opening hours
- approved business knowledge
- Google Calendar availability
- appointment booking
- appointment cancellation
- appointment rescheduling
- message creation
- ownership verification
- confirmation / idempotency
- database records
- dashboard data

The existing project is a Python/FastAPI application.

Before modifying anything, inspect the repository and explain the current architecture and what should be reused versus replaced.

IMPORTANT:
Do not delete or rewrite the existing custom voice pipeline yet.
Build the Vapi integration alongside it first so I can compare both systems.

--------------------------------------------------
TARGET ARCHITECTURE
--------------------------------------------------

I want the architecture to become approximately:

Caller
  ↓
Vapi
  ├── STT
  ├── realtime conversation model
  ├── TTS
  ├── interruptions / turn taking
  │
  ↓
Vapi Tools / Server URL
  ↓
Ava FastAPI backend
  ├── business knowledge
  ├── staff/services/settings
  ├── appointment availability
  ├── booking
  ├── cancellation
  ├── rescheduling
  ├── messages
  └── database
  ↓
Google Calendar / DB

The model may interpret the caller's language.

Python remains authoritative over facts and side effects.

The model must NEVER be trusted to:
- invent calendar availability
- claim a booking succeeded without backend confirmation
- cancel/reschedule without backend verification
- invent staff roles or qualifications
- invent prices, hours, policies, or services
- bypass explicit confirmation where required

--------------------------------------------------
PHASE 1 — INSPECT CURRENT PROJECT
--------------------------------------------------

First inspect:

- backend/app/agent.py
- backend/app/business.py
- backend/app/scheduling.py
- backend/app/calendar.py
- backend/app/conversation.py
- backend/app/api.py
- backend/app/database.py
- current voice modules
- frontend settings/dashboard components
- tests

Explain:

1. Which current components become unnecessary when using Vapi.
2. Which components should remain.
3. Which functions can become Vapi tools.
4. Which existing safeguards must remain in Python.
5. What Vapi-specific files/endpoints should be added.

Do not implement until you show this migration plan.

--------------------------------------------------
PHASE 2 — CREATE A MINIMAL VAPI ASSISTANT
--------------------------------------------------

Create the smallest possible Vapi-based Ava first.

Initial assistant behavior:

Ava is an AI receptionist for an appointment-based clinic.

She should:
- greet naturally
- answer simple conversational questions
- answer business questions using approved information
- explain services
- answer questions about staff
- answer opening-hours/location/policy questions
- check appointment availability
- book appointments
- reschedule appointments
- cancel appointments
- take a message for staff

Conversation style:

- concise
- warm
- natural spoken English
- avoid sounding like an IVR
- do not repeatedly say "I am an AI receptionist"
- do not end every response with "Is there anything else I can help you with?"
- answer the user's actual question first
- use recent conversational context
- resolve pronouns and follow-ups naturally
- acknowledge corrections naturally
- avoid unnecessarily repeating information
- do not expose internal terms such as:
  "approved knowledge"
  "tool result"
  "configured information"
  "retrieval failed"
  "provider error"

Examples of desired style:

User:
"How are you?"

Ava:
"I'm good, thanks. How can I help?"

User:
"What do you guys do there?"

Ava:
"We mainly offer physiotherapy and rehabilitation services."

Not:
"I am an AI receptionist here to help with clinic questions..."

User:
"What about parking?"

Ava:
Answer the clinic's actual parking information naturally.

User:
"Who was the physician again?"

Ava:
Use recent conversational context instead of treating it as an isolated query.

--------------------------------------------------
PHASE 3 — VAPI CONFIGURATION
--------------------------------------------------

Use current Vapi APIs and concepts.

Prefer:
- Vapi Assistant
- Vapi Tools
- Vapi Server URL / webhooks
- existing Ava backend APIs

Do not use deprecated Vapi Custom Functions if the current Tools system should be used instead.

Create configuration for:

1. Transcriber
2. Conversation model
3. ElevenLabs voice
4. system prompt
5. endpointing / speaking behavior
6. interruption behavior
7. tools
8. server URL
9. end-of-call reporting

Keep configuration values environment-driven where appropriate.

Do not hardcode secrets.

Create an `.env.example` showing required variables, but never write real API keys.

--------------------------------------------------
PHASE 4 — BACKEND TOOLS
--------------------------------------------------

Design a small, explicit tool surface.

Do NOT expose dozens of internal functions directly to the model.

Start with tools conceptually like:

get_business_information
get_staff_information
check_availability
create_appointment
get_appointment
cancel_appointment
reschedule_appointment
leave_message

You may adjust these after inspecting the backend.

Each tool must:
- have a narrow purpose
- use a clear JSON schema
- validate caller-supplied fields
- return structured JSON
- return explicit success/failure states
- never expose secrets
- never trust model-provided business IDs
- derive trusted tenant/business context server-side

For booking actions:
- checking availability is not booking
- booking requires verified slot availability
- booking result must come from the backend
- cancellation/rescheduling must verify appointment ownership
- maintain existing idempotency protections
- maintain existing calendar safety

--------------------------------------------------
PHASE 5 — KNOWLEDGE
--------------------------------------------------

Do not let the Vapi system prompt become a giant database.

Use the existing structured settings where possible:

- business name
- phone
- location
- hours
- services
- prices
- cancellation policy
- staff names
- roles
- qualifications

Generic FAQs can remain approved knowledge.

For a small knowledge base, returning bounded trusted facts from the backend is acceptable.

Do not add a vector database yet.

Do not add RAG infrastructure unless measured failures show it is necessary.

--------------------------------------------------
PHASE 6 — CONVERSATIONAL CONTEXT
--------------------------------------------------

This is important because the custom Ava struggled here.

The Vapi version must handle conversational follow-ups such as:

User:
"Who are the physicians?"

Ava:
[answers]

User:
"What about Abdul Hadi?"

Ava:
[answers specifically about Abdul Hadi]

User:
"So he's a physiotherapist?"

Ava:
Correct or confirm using structured staff data.

Also test:

"What do you guys do there?"
"And who would actually treat me?"
"What about parking?"
"If I just show up, is that okay?"
"Who was the physician again?"
"No sorry, I meant Ali."
"What did you say the first appointment time was?"

Do not add exact hardcoded phrase matching for these sentences.

The solution should rely on normal conversational understanding plus trusted backend facts.

--------------------------------------------------
PHASE 7 — CALL EVENTS AND RECORDS
--------------------------------------------------

Use Vapi server events to persist useful call information.

At minimum capture:

- Vapi call ID
- call start
- call end
- caller number where available
- transcript
- assistant messages
- tool calls
- tool results
- call status
- end-of-call summary/report if available

Map this into the existing Call / TranscriptTurn architecture where sensible.

Do not blindly duplicate events.

Use Vapi's call ID as an external identifier for idempotency/correlation.

--------------------------------------------------
PHASE 8 — TESTING
--------------------------------------------------

Create integration tests for the backend tool endpoints independently of Vapi.

Test at least:

BUSINESS KNOWLEDGE
- What services do you offer?
- What are your prices?
- What are your hours?
- Where are you located?
- Do you have parking?
- Is the clinic wheelchair accessible?
- Do you accept walk-ins?

STAFF
- Who are your physiotherapists?
- Do you have a physician?
- Is Abdul Hadi a physician?
- Who has a PhD?
- Is someone with a PhD necessarily a physician? The system must not infer that.

BOOKING
- check available Tuesday slots
- choose one
- change selection before confirmation
- confirm
- ensure exactly one appointment is created

CANCELLATION
- ask about cancellation policy
- distinguish policy question from cancellation action
- cancel only after verification and confirmation

RESCHEDULING
- verify existing appointment
- choose new slot
- confirm
- ensure calendar and DB are consistent

FAILURES
- calendar unavailable
- invalid appointment ID
- wrong phone number
- tool timeout
- duplicate tool call
- interrupted confirmation
- caller changes details after confirmation prompt

--------------------------------------------------
PHASE 9 — OBSERVABILITY
--------------------------------------------------

Add concise structured logs for:

VAPI_CALL_STARTED
VAPI_CALL_ENDED
VAPI_TOOL_REQUESTED
VAPI_TOOL_COMPLETED
VAPI_TOOL_FAILED

Include:
- call_id
- tool
- latency_ms
- success/failure

Never log:
- API keys
- credentials
- full sensitive payloads

--------------------------------------------------
PHASE 10 — KEEP OLD VOICE PIPELINE FOR NOW
--------------------------------------------------

Do not remove:

- Deepgram custom code
- ElevenLabs custom code
- browser WebSocket voice path
- VoiceSession
- current custom pipeline

Mark it as the legacy/custom path.

The new Vapi implementation should coexist until we compare:

- latency
- naturalness
- interruption handling
- contextual understanding
- booking reliability
- TTS quality

Only after successful comparison should we discuss deleting or archiving the old implementation.

--------------------------------------------------
IMPLEMENTATION STYLE
--------------------------------------------------

I am learning voice-agent engineering, so do not blindly generate a giant rewrite.

Work incrementally.

For every major change:
1. explain what problem it solves
2. show which file will change
3. explain how Vapi communicates with that code
4. implement it
5. run relevant tests
6. report results

Prefer small explicit modules over complicated abstractions.

Do not introduce:
- LangGraph
- vector databases
- additional agent frameworks
- unnecessary event buses
- unnecessary microservices

unless there is a demonstrated need.

--------------------------------------------------
FIRST TASK
--------------------------------------------------

Start ONLY with the architecture inspection.

Show me:

1. current Ava architecture
2. proposed Vapi architecture
3. components we keep
4. components Vapi replaces
5. backend tools we need
6. server/webhook endpoints we need
7. security boundaries
8. files that will change
9. files that should remain untouched
10. implementation order

Do not modify code until I approve that plan.