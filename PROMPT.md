You are the senior software engineer responsible for turning my existing Ava voice-agent prototype into a complete, understandable, production-oriented MVP.

IMPORTANT: Do not immediately rewrite the repository.

FIRST:
1. Inspect the entire existing codebase.
2. Understand what already works.
3. Run the existing application/tests where possible.
4. Identify the current architecture and dependencies.
5. Produce a short implementation plan.
6. Preserve working code unless there is a concrete reason to replace it.
7. Then implement the system incrementally and verify each major stage before moving on.

==================================================
PROJECT
==================================================

Product name: Ava

Ava is an AI voice receptionist for appointment-based businesses.

Primary initial vertical:
- Physiotherapy / physical therapy clinics

The architecture should remain adaptable enough for:
- dental clinics
- salons
- spas
- medspas
- gyms
- other appointment-based businesses

Future expansion may include:
- restaurants
- e-commerce/order taking

Do NOT build all future verticals now.

Build a strong appointment-based-business MVP with a configuration layer that will allow other verticals later.

==================================================
MY CURRENT TECHNICAL UNDERSTANDING
==================================================

I am a CS undergraduate and I need to be able to understand this codebase after you build it.

I already understand:

- Python
- FastAPI basics
- REST APIs
- PostgreSQL basics
- React / Next.js
- WebSockets
- microphone audio capture
- digital audio / PCM
- 16 kHz audio
- audio chunks
- sounddevice
- queues
- Python threading fundamentals
- streaming STT
- Deepgram Flux
- interim transcripts
- StartOfTurn / Update / EndOfTurn
- LLM calls
- Gemini chat history
- ElevenLabs TTS
- PCM playback
- basic barge-in using threading.Event
- general RAG concepts

Therefore:

DO NOT overengineer this project.

Prefer:
- simple functions
- clear classes
- explicit state
- readable modules
- descriptive variable names
- comments explaining WHY something exists
- straightforward control flow

Avoid unless clearly necessary:
- microservices
- Kubernetes
- Kafka
- complex event buses
- excessive dependency injection
- unnecessary design patterns
- huge class hierarchies
- metaprogramming
- clever abstractions
- premature distributed architecture

I want a modular monolith that a CS student with my background can understand.

==================================================
EXISTING VOICE PROTOTYPE
==================================================

My current local prototype already demonstrates the following concepts:

Microphone
    ↓
16 kHz PCM
    ↓
Deepgram Flux streaming STT
    ↓
StartOfTurn / Update / EndOfTurn
    ↓
final user transcript
    ↓
LLM
    ↓
response text
    ↓
ElevenLabs streaming TTS
    ↓
16 kHz PCM
    ↓
sounddevice speaker playback

The prototype also has:

- continuous microphone streaming
- roughly 80 ms microphone audio chunks
- Deepgram Flux
- end-of-turn detection
- Gemini chat-based conversation memory
- separate audio and agent queues
- separate worker/listener execution
- ElevenLabs streaming TTS
- direct sounddevice PCM output instead of ffplay
- stop_speaking_event using threading.Event
- basic interruption/barge-in:
    Deepgram StartOfTurn
        → stop_speaking_event.set()
        → TTS playback stops

Do not throw these concepts away without justification.

You may refactor them into cleaner modules.

==================================================
TARGET MVP
==================================================

Build Ava into a complete AI receptionist system consisting of:

1. Voice agent runtime
2. Conversation orchestration
3. Business knowledge system
4. Google Calendar scheduling
5. Appointment management
6. Message-taking
7. Human escalation support
8. Call logging
9. Conversation transcripts
10. AI call summaries
11. Structured database storage
12. Admin dashboard
13. Business settings/configuration
14. Basic analytics
15. Error handling and observability
16. Documentation
17. Automated tests for important business logic

The completed MVP should feel like a real product, not a collection of demo scripts.

==================================================
CORE ARCHITECTURE
==================================================

Use a modular-monolith architecture.

A reasonable backend structure might resemble:

backend/
    app/
        main.py
        config.py

        voice/
            stt.py
            tts.py
            audio.py
            turn_manager.py
            session.py

        agent/
            agent.py
            prompts.py
            conversation.py
            state.py
            tools.py

        scheduling/
            calendar.py
            availability.py
            appointments.py

        business/
            knowledge.py
            configuration.py
            policies.py

        services/
            call_service.py
            message_service.py
            summary_service.py

        database/
            models.py
            repository.py
            db.py

        api/
            calls.py
            appointments.py
            messages.py
            dashboard.py
            settings.py

        schemas/
            ...

        tests/
            ...

This is guidance, not a rigid requirement.

Use whatever structure is clearest after inspecting the existing repository.

==================================================
PROVIDER ABSTRACTION
==================================================

Do not tightly couple Ava's business logic to one AI provider.

Create small provider interfaces/adapters where useful.

Conceptually:

STTProvider
LLMProvider
TTSProvider
CalendarProvider

Initial implementations:

STT:
- Deepgram Flux

LLM:
- keep whichever current Gemini model is already verified working in the repository
- structure code so OpenAI can replace it later without rewriting business logic

TTS:
- ElevenLabs streaming TTS

Calendar:
- Google Calendar

IMPORTANT:
Before changing model names, SDK methods, request parameters, or API behavior, verify against CURRENT official provider documentation.

Do not invent model names or API methods.

Do not replace a currently working model merely because another model sounds newer.

==================================================
VOICE PIPELINE
==================================================

Preserve the realtime pipeline:

incoming audio
    ↓
STT
    ↓
turn detection
    ↓
conversation controller
    ↓
LLM/tool decision
    ↓
response
    ↓
TTS
    ↓
outgoing audio

Voice behavior requirements:

- Stream audio instead of waiting for complete recordings.
- Keep STT listening while other work occurs.
- LLM/TTS processing must not block STT event processing.
- Support basic full-duplex behavior.
- Support barge-in/interruption.
- User speech during Ava's speech should be able to cancel TTS playback.
- Avoid accidentally generating multiple LLM calls from interim transcripts.
- Only finalized user turns should normally trigger agent reasoning.
- Prevent duplicate responses from duplicate events.
- Conversation state must remain consistent across interruptions.

Keep the current simple basic barge-in first.

Design it so smarter interruption detection can later consider:
- minimum speech duration
- backchannels such as "yeah"
- coughs/noise
- echo
- confidence
- whether Ava is currently speaking

Do not overbuild smart interruption detection in the first MVP.

==================================================
LOCAL AUDIO VS TELEPHONY
==================================================

Keep local microphone/speaker mode available as a development/debug mode.

Architecture should separate:

incoming caller audio
and
outgoing Ava audio

Do not rely on Ava "recognizing her own voice."

In real telephony these are separate streams.

Local speaker → microphone acoustic echo is primarily a development-environment issue.

Do not spend excessive time building custom acoustic echo cancellation for the local prototype.

==================================================
TELEPHONY
==================================================

Design the system so real telephone calls can be connected.

If the existing repository already uses Vapi, Twilio, or another telephony provider, inspect that integration first and preserve it where sensible.

Do NOT build a telecom carrier/SIP stack from scratch.

Telephony should be an adapter around the core Ava agent.

The business/agent logic must not depend directly on a specific telephony provider.

The same agent should eventually be usable from:

- phone calls
- browser microphone demo
- local development microphone

If full telephony integration cannot be completed because credentials/account configuration are unavailable, implement the adapter/interface, webhook/API structure, tests/mocks, and exact setup documentation.

==================================================
CONVERSATION ENGINE
==================================================

Ava must maintain conversational context.

However:

DO NOT use LLM chat history as the only source of business state.

Separate:

1. Natural-language conversation history
2. Structured operational state

Example:

Conversation:
Caller:
"I need an appointment Friday around five."

Structured state:

appointment_state = {
    "caller_name": null,
    "phone": null,
    "email": null,
    "service": null,
    "requested_date": "...",
    "requested_time": "17:00",
    "selected_slot": null,
    "confirmed": false
}

Build an explicit appointment state model.

The LLM can help extract/update fields, but business actions must operate on validated structured values.

==================================================
GOOGLE CALENDAR
==================================================

Integrate Google Calendar properly.

Support at least:

- read free/busy information
- check availability
- list valid slots
- create appointment
- retrieve appointment when possible
- reschedule appointment
- cancel appointment
- retain Google Calendar event ID
- correctly handle timezone
- correctly handle appointment duration
- reject invalid dates/times
- prevent double booking

CRITICAL RULE:

The LLM must NEVER invent calendar availability.

Wrong:

LLM:
"Yes, Friday at 5 is free."

Correct:

LLM/tool controller:
check_availability(...)
    ↓
Google Calendar
    ↓
actual result
    ↓
LLM responds based on tool result

Calendar truth must come from Google Calendar.

==================================================
BOOKING FLOW
==================================================

A normal booking should roughly work like:

Caller requests appointment
    ↓
determine service
    ↓
determine requested date/time
    ↓
validate date
    ↓
query real calendar
    ↓
if unavailable, offer nearby valid alternatives
    ↓
collect required caller details
    ↓
repeat important booking information
    ↓
ask for explicit confirmation
    ↓
create calendar event
    ↓
persist local appointment record
    ↓
return confirmation

Never create an appointment before explicit confirmation.

Required information should be configurable, but for the MVP likely include:

- caller name
- phone number
- service
- appointment date
- appointment time

Email may be optional/configurable.

Never fabricate missing information.

If a required value is absent, Ava should ask for it.

==================================================
CONCURRENCY / DOUBLE BOOKING
==================================================

Assume multiple callers can attempt to book at the same time.

Design booking operations defensively.

A slot that was available five seconds ago may no longer be available.

Before final event creation:

- revalidate availability

Use appropriate idempotency and locking/transaction strategies where necessary.

Prevent:

- duplicate calendar events
- repeated booking from duplicate tool invocation
- duplicate database appointments
- two callers silently acquiring the same slot

Do not claim perfect unlimited scalability.

Build correct MVP concurrency behavior and document its limits.

==================================================
BUSINESS KNOWLEDGE
==================================================

Ava needs access to business information such as:

- business name
- locations
- opening hours
- services
- pricing where appropriate
- appointment durations
- staff/providers
- cancellation policies
- FAQs
- parking/location instructions
- insurance information if supplied
- escalation rules
- after-hours rules

Never allow the LLM to invent business facts.

Business-specific information should come from stored/configured data.

For MVP, prefer a clear database-backed knowledge/configuration model over prematurely building a complicated RAG architecture.

RAG can be added where long documents justify it.

If RAG is introduced:
- keep it isolated behind a knowledge service
- cite/source internally where possible
- never let retrieval override calendar/business transactional truth

==================================================
CLINIC-SPECIFIC SAFETY
==================================================

This is initially intended for physiotherapy clinics.

Ava is NOT a doctor.

Do not let Ava diagnose medical conditions or provide personalized medical treatment advice.

For normal clinical-information questions:
- provide only business-approved informational material

If a caller describes a medical emergency or clearly urgent situation:
- instruct them to contact the appropriate emergency service / seek immediate professional emergency help
- do not attempt diagnosis

Do not collect payment card information through the AI voice agent.

Do not store unnecessary sensitive information.

==================================================
MESSAGE TAKING
==================================================

When Ava cannot complete a request, it should be able to take a message.

Message should contain structured fields such as:

- caller name
- phone
- reason/message
- timestamp
- urgency classification if appropriate
- associated call ID
- status: new / reviewed / resolved

Dashboard staff should be able to review messages.

==================================================
HUMAN ESCALATION
==================================================

Support an escalation decision.

Examples:

- caller explicitly asks for a human
- complaint
- request outside configured scope
- repeated agent failure
- sensitive situation
- certain configured keywords/workflows

For the MVP:

If live call transfer is available through the telephony provider:
- implement it cleanly

Otherwise:
- collect caller details/message
- mark escalation
- store it for staff follow-up

Do not pretend a transfer occurred when it did not.

==================================================
DATABASE
==================================================

Use a real persistent relational database for the main application state.

Preferred:
- PostgreSQL

If Supabase is already in the repository and appropriate, it can be used as managed PostgreSQL.

Do not make Redis the authoritative long-term database for critical call/appointment history unless the existing architecture has a very strong reason.

Redis may be used for:
- temporary session state
- locks
- cache
- short-lived concurrency coordination

Suggested entities:

Business
User/Admin
Caller/Contact
Call
TranscriptTurn
Appointment
Message
Escalation
Service
Staff/Provider
BusinessHours
BusinessSetting

Potential Call fields:

id
business_id
external_call_id
caller_phone
started_at
ended_at
duration_seconds
status
outcome
summary
transcript
appointment_created
created_at

Potential Appointment fields:

id
business_id
call_id
caller_name
caller_phone
caller_email
service
start_at
end_at
timezone
status
calendar_event_id
created_at
updated_at

Choose clean schemas after understanding the project.

Use migrations.

==================================================
CALL LOGGING
==================================================

Every call should create a durable call record.

Track where available:

- incoming/outgoing direction
- caller number
- call start
- call end
- duration
- transcript
- conversation turns
- final outcome
- appointment booked?
- message left?
- escalation?
- failure reason
- AI summary

Do not let logging failure crash an active call whenever reasonably avoidable.

==================================================
CALL SUMMARY
==================================================

After a call ends, generate a concise structured summary.

Example:

Outcome:
Appointment booked

Caller:
John Smith

Reason:
Lower-back physiotherapy consultation

Appointment:
Tuesday, October 6 at 3:00 PM

Other notes:
Asked about parking.

Follow-up:
None

Store both:
- human-readable summary
- structured outcome fields where useful

Do not rely on free-text summaries for analytics.

==================================================
DASHBOARD
==================================================

Build a clean, premium, responsive admin dashboard.

Preferred frontend if it fits the existing codebase:

- Next.js
- React
- TypeScript
- Tailwind

Do not redesign the entire technology stack if the existing frontend is already suitable.

Visual style:
- modern
- calm
- professional
- premium
- minimal
- not flashy
- appropriate for business owners/clinic staff

Dashboard navigation should initially include:

Overview
Calls
Appointments
Messages
Settings

==================================================
DASHBOARD: OVERVIEW
==================================================

Show useful operational metrics such as:

- total calls
- calls today
- appointments booked
- booking conversion rate
- average call duration
- unresolved messages
- escalations

Add a recent activity section.

Do not invent metrics from unavailable data.

==================================================
DASHBOARD: CALLS
==================================================

Calls page should show a table with:

- caller
- date/time
- duration
- outcome
- booking status
- status

Allow selecting a call.

Call detail page/drawer should show:

- full transcript
- clearly separated User / Ava turns
- call summary
- outcome
- associated appointment
- associated message/escalation
- timestamps where available
- relevant errors/events where useful

==================================================
DASHBOARD: APPOINTMENTS
==================================================

Show:

- upcoming appointments
- past appointments
- canceled appointments
- caller name
- service
- date/time
- source/call
- Google Calendar sync status

Allow viewing appointment details.

For MVP, dashboard editing may be limited if calendar consistency would become complicated.

If implementing edit/reschedule:
- use the same scheduling service as the agent
- never bypass calendar validation

==================================================
DASHBOARD: MESSAGES
==================================================

Show:

- new messages
- caller
- timestamp
- message content
- associated call
- status

Allow staff to mark:
- reviewed
- resolved

==================================================
DASHBOARD: SETTINGS
==================================================

Allow business configuration such as:

Business:
- name
- timezone
- phone
- location

Voice agent:
- assistant name
- greeting
- escalation number
- selected voice where supported

Scheduling:
- appointment duration
- buffer time
- minimum notice
- maximum advance booking window
- business hours
- calendar connection/status

Services:
- service name
- duration
- active/inactive

Knowledge:
- FAQs
- policies
- business information

Keep settings simple for MVP.

==================================================
AUTHENTICATION
==================================================

Dashboard must not be publicly accessible.

Implement straightforward secure authentication.

Do not create a huge enterprise identity platform.

Use existing auth if the repository already has it.

Otherwise choose a simple mature solution that works naturally with the selected stack.

Protect all business data endpoints.

==================================================
MULTI-TENANCY
==================================================

Architect data models with business_id / tenant isolation in mind.

However, do not build an excessively complicated SaaS tenancy platform in week one.

For MVP:
- one deployment may initially serve one business
OR
- simple tenant-aware models may support multiple businesses

Whichever approach best fits existing code, ensure one business can never access another business's:

- calls
- appointments
- settings
- calendar credentials
- transcripts
- messages

Document the chosen isolation model.

==================================================
ERROR HANDLING
==================================================

Handle failures explicitly.

Examples:

Deepgram unavailable
Gemini/LLM unavailable
ElevenLabs unavailable
Google Calendar unavailable
database unavailable
invalid calendar credentials
TTS stream interruption
network timeout
duplicate webhook
invalid appointment data

Ava should fail gracefully.

Example:

Do NOT say:
"Your appointment has been booked."

if calendar creation failed.

Instead:
"I'm sorry, I wasn't able to complete the booking right now. I can take your details so the team can follow up."

Log technical details server-side.

Give callers human-friendly messages.

==================================================
RETRIES
==================================================

Use retries only where safe.

Do not blindly retry operations that can create duplicates.

For calendar/event creation:
- use idempotency/deduplication strategy
- check whether an operation already succeeded before retrying where appropriate

==================================================
OBSERVABILITY
==================================================

Implement useful structured logging.

Log important lifecycle events such as:

CALL_STARTED
STT_CONNECTED
USER_TURN_FINALIZED
LLM_STARTED
LLM_COMPLETED
TTS_STARTED
TTS_INTERRUPTED
TTS_COMPLETED
TOOL_CALLED
CALENDAR_CHECK
BOOKING_CREATED
BOOKING_FAILED
MESSAGE_CREATED
CALL_ENDED

Avoid dumping API secrets or sensitive credentials.

Where feasible record latency measurements:

- end of user speech → final transcript
- final transcript → LLM response
- LLM response → first TTS audio
- total end-of-turn → Ava speech latency

Keep instrumentation lightweight.

==================================================
SECURITY
==================================================

Never commit secrets.

Use environment variables.

Create:

.env.example

but never populate it with real secrets.

Expected variables may include:

DEEPGRAM_API_KEY
GEMINI_API_KEY
ELEVENLABS_API_KEY
DATABASE_URL
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI
etc.

Verify exact Google auth requirements against current official documentation.

Do not print tokens in logs.

Validate all public API input.

==================================================
GOOGLE AUTH
==================================================

Implement the required Google Calendar OAuth flow or appropriate service-account model depending on the actual business deployment architecture.

Do not guess.

Research the current Google Calendar API authentication requirements from official Google documentation.

Document exactly what I must manually do in Google Cloud Console:

- project creation if needed
- enabling Calendar API
- OAuth consent configuration
- redirect URI
- credentials
- environment variables
- authorization process

If some step requires me to click/authorize manually, do not fake completion.

Implement everything around it and provide exact instructions.

==================================================
WEBSITE TALK-TO-AVA MODE
==================================================

If feasible within the existing project architecture, preserve or implement a browser-based voice demo.

It should use the same core business agent as phone calls.

Do not create separate business logic for the browser demo.

Browser:
audio transport
    ↓
same Ava core
    ↓
same tools
    ↓
same calendar
    ↓
same database

==================================================
STATE MACHINE / TOOL SAFETY
==================================================

Do not let the LLM freely execute dangerous or irreversible actions merely because it generated text.

Implement controlled tools.

Examples:

check_availability(...)
create_appointment(...)
reschedule_appointment(...)
cancel_appointment(...)
lookup_business_info(...)
take_message(...)
request_human_escalation(...)

Validate tool arguments in Python before execution.

Critical mutations such as appointment creation should require appropriate conversational confirmation.

The LLM chooses/intends the action.

Application code validates and executes it.

==================================================
PROMPT DESIGN
==================================================

Ava should sound:

- natural
- calm
- concise
- professional
- helpful

Avoid long chatbot-style paragraphs on phone calls.

Ava should ask one question at a time where practical.

Ava must:

- never invent availability
- never invent pricing/policies
- never fabricate caller information
- never falsely say an appointment was booked
- never falsely say a human transfer succeeded
- clearly ask for missing required information
- confirm important transactional details

Keep system prompts in their own clearly editable file/configuration.

==================================================
APPOINTMENT DATE HANDLING
==================================================

Date/time logic must not rely solely on the LLM.

Support natural phrases such as:

"tomorrow"
"next Friday"
"Friday afternoon"
"around 4"
"after 5"
"October 12"

Resolve them relative to the business timezone.

Validate the resolved date/time using deterministic application code.

The LLM may interpret user language, but Python/calendar logic owns final validity.

==================================================
TESTING
==================================================

Write automated tests for business-critical logic.

At minimum test scenarios such as:

normal booking
unavailable requested slot
alternative slot
caller changes requested date
caller changes requested time
missing caller name
missing phone number
invalid date
past date
double booking attempt
duplicate tool invocation
calendar creation failure
rescheduling
cancellation
user interrupts Ava
empty STT turn
multiple interim STT updates
only EndOfTurn triggers LLM
message-taking
human escalation
LLM tries to invent availability
appointment not created before confirmation

Mock external providers where appropriate.

Do not make unit tests spend real API credits.

==================================================
MANUAL END-TO-END TESTS
==================================================

Also produce a manual QA checklist.

Examples:

1.
Caller:
"I want an appointment Friday at 5."

2.
Caller changes mind halfway:
"Actually, make that Monday."

3.
Caller interrupts Ava during speech.

4.
Requested time is occupied.

5.
Caller asks:
"What's available tomorrow afternoon?"

6.
Caller asks unrelated FAQ then returns to booking.

7.
Caller asks for human.

8.
Calendar API is unavailable.

9.
Caller provides incomplete information.

10.
Caller attempts to confirm twice.

Document expected result for each.

==================================================
DOCUMENTATION
==================================================

This is extremely important because I intend to study the code after it works.

Create:

README.md
ARCHITECTURE.md
DATA_FLOW.md
SETUP.md
TESTING.md

ARCHITECTURE.md should explain:

- major modules
- responsibilities
- why architecture choices were made
- what threads/tasks exist
- provider boundaries
- state ownership
- database ownership
- calendar integration
- how interruption works

DATA_FLOW.md should trace:

AUDIO FLOW:

caller
→ audio transport
→ Deepgram
→ finalized transcript
→ conversation controller
→ agent

AGENT FLOW:

agent
→ respond directly
OR
→ tool call
→ application validates
→ external system
→ result
→ LLM
→ response

OUTPUT FLOW:

LLM response
→ ElevenLabs
→ streaming PCM
→ caller

BOOKING FLOW:

caller request
→ structured state
→ availability check
→ selection
→ confirmation
→ revalidation
→ calendar event
→ local DB record
→ confirmation response

DASHBOARD FLOW:

database
→ API
→ authenticated dashboard

Explain these in beginner-friendly language.

==================================================
CODE COMMENTS
==================================================

Do not comment obvious syntax.

Bad:

# increment i
i += 1

Good:

# Do not run Gemini directly inside the Deepgram event callback.
# Keeping agent work on a separate worker prevents LLM/TTS latency
# from blocking incoming STT events and enables barge-in.
agent_queue.put(transcript)

Use comments to explain architectural reasons.

==================================================
LEARNING MODE
==================================================

Whenever you introduce a technically advanced mechanism, add a short explanation to ARCHITECTURE.md.

Examples:

asyncio
thread synchronization
WebSocket audio transport
database transactions
locks
OAuth
idempotency
tool calling
stream cancellation

I need to understand this codebase later.

If two approaches are similarly good, prefer the one that is easier to understand.

==================================================
IMPLEMENTATION STRATEGY
==================================================

Do not attempt the entire project as one giant unverified edit.

Work in milestones.

Suggested order:

MILESTONE 0
Repository audit

- inspect project
- run existing code
- document current architecture
- identify reusable components
- identify broken/dead code
- produce implementation plan

MILESTONE 1
Clean voice core

- modularize existing STT/LLM/TTS pipeline
- preserve working voice behavior
- preserve interruption
- verify local conversation
- remove obsolete prototype code only after replacement is verified

MILESTONE 2
Conversation + structured state

- explicit session object
- appointment state
- tool interface
- provider interfaces

MILESTONE 3
Database

- PostgreSQL
- migrations
- calls
- turns
- appointments
- messages
- settings

MILESTONE 4
Google Calendar

- OAuth/setup
- availability
- create
- reschedule
- cancel
- validation
- idempotency

MILESTONE 5
Complete receptionist flows

- booking
- FAQs
- messages
- escalation
- error recovery

MILESTONE 6
Dashboard API

- calls
- appointments
- messages
- analytics
- settings

MILESTONE 7
Dashboard frontend

- overview
- calls
- call details
- appointments
- messages
- settings

MILESTONE 8
Telephony/browser integration

- connect core agent to real transport
- keep business logic independent

MILESTONE 9
Reliability/testing

- concurrency
- retries
- duplicates
- failure states
- tests
- latency logging

MILESTONE 10
Documentation and cleanup

- architecture docs
- data flow
- setup
- test instructions
- remove dead code
- verify clean fresh setup

At the end of each milestone:

1. run relevant tests
2. run lint/type checks where configured
3. fix errors
4. briefly summarize what changed
5. note any manual action required from me
6. commit or clearly identify a stable checkpoint if git workflow permits

==================================================
DO NOT DO THESE THINGS
==================================================

Do not:

- delete working functionality without replacement
- expose secrets
- invent API behavior
- silently change providers
- hard-code business facts
- allow the LLM to invent calendar availability
- build appointment logic entirely inside prompts
- call Gemini for every interim STT update
- block the Deepgram event listener with TTS playback
- depend on ffplay for production playback
- store only free-text call summaries instead of structured outcomes
- create calendar events before explicit confirmation
- silently swallow booking failures
- make the frontend directly responsible for calendar truth
- introduce unnecessary infrastructure
- use fake placeholder caller data
- claim a feature works unless it has actually been tested

==================================================
ACCEPTANCE CRITERIA
==================================================

The MVP is considered complete when I can demonstrate:

TEST A — NORMAL CONVERSATION

Caller speaks naturally.
Ava responds with low enough latency for a usable conversation.

TEST B — INTERRUPTION

Ava begins speaking.
Caller interrupts.
Ava stops output and processes the caller's new turn.

TEST C — BUSINESS FAQ

Caller asks business question.
Ava answers from configured business information rather than guessing.

TEST D — AVAILABILITY

Caller asks:
"Do you have anything Friday afternoon?"

Ava checks the actual calendar and returns valid slots.

TEST E — BOOKING

Caller selects a slot.
Ava gathers required information.
Ava confirms details.
Caller confirms.
A real Google Calendar event is created.
A matching database record exists.

TEST F — DOUBLE BOOKING

Two booking attempts target the same slot.
System does not silently create conflicting appointments.

TEST G — RESCHEDULE

Existing appointment can be moved only after checking new availability.

TEST H — CANCEL

Appointment can be canceled and local/calendar state remain consistent.

TEST I — FAILURE

Calendar API fails.

Ava does NOT claim success.
Failure is logged.
Caller receives an appropriate fallback response.

TEST J — DASHBOARD

Staff can sign in and see:

- overview metrics
- calls
- call transcript
- call summary
- appointments
- messages

TEST K — PERSISTENCE

Restarting the server does not erase critical call/appointment records.

TEST L — DOCUMENTATION

A developer with my level of experience can follow README.md + ARCHITECTURE.md and understand the main execution flow.

==================================================
FINAL PRODUCT PHILOSOPHY
==================================================

The value of Ava is not merely:

STT + LLM + TTS.

It is:

reliable voice interaction
+
business-specific knowledge
+
real scheduling
+
safe transactional behavior
+
good interruption handling
+
persistent operational records
+
staff visibility
+
graceful failure handling

Optimize for reliability and understandable engineering rather than impressive-looking complexity.

==================================================
YOUR FIRST ACTION
==================================================

Do NOT start implementing immediately.

Begin by:

1. Inspecting every important directory/file in the current repository.
2. Running the current application if feasible.
3. Identifying what currently works.
4. Identifying architectural problems.
5. Identifying missing dependencies/features.
6. Giving me a concise proposed target architecture.
7. Giving me the milestone plan adapted to THIS repository.
8. Telling me which manual credentials/accounts/configuration will eventually be required.

Then begin Milestone 1.

When you encounter uncertainty:
- inspect the existing implementation
- check current official API documentation when necessary
- make a reasonable simple engineering decision
- document that decision

Do not repeatedly stop for minor preferences.

Only ask me when a decision materially affects:
- business behavior
- paid provider choice
- security
- irreversible data behavior
- credentials/account authorization
- product scope

Otherwise proceed autonomously.