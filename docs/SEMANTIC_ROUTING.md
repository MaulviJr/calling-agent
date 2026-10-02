# Single-call conversational interpretation

The production `GeminiResponseGenerator.interpret` call selects intent, entities,
approved evidence and a response together. There is no preceding classifier and
no following LLM grounding review. Python remains the only action executor.

## Structured schemas

`SemanticDraft` (all schemas forbid unknown fields):

| Field | Contract |
|---|---|
| `turn_kind` | `knowledge`, `conversation`, `clarification`, `action` |
| `selected_source_ids` | Up to 100 unique IDs from this turn's approved packet |
| `resolved_entity_ids` | Up to 100 unique raw staff IDs in that packet |
| `answer_mode` | Bounded service/staff/source/missing/social/clarification/action relation |
| `response_text` | Proposed spoken text, 1–4000 characters |
| `discourse_update` | Topic, focused staff ID, selected recent source IDs only |
| `role_filter`, `qualification` | Optional parameters for typed staff relations |
| `action_proposal` | Optional existing `AgentDecision`; proposals grant no permissions |

`DiscourseState`:

| Field | Contract |
|---|---|
| `topic` | Bounded clinic topic; includes services, staff, accessibility, parking, walk-in, other |
| `focused_entity_id` | Validated staff ID or null |
| `recent_source_ids` | Validated IDs, never cached authoritative facts |
| `last_answer_mode` | Last accepted knowledge/clarification mode |
| `age` | Turns since the last accepted knowledge/clarification answer |
| `interrupted` | Application-owned delivery metadata |

The model proposes only the first three memory fields. Python owns age, answer
mode, delivery metadata and the persisted assistant turn ID. Memory expires after
six intervening turns. Deleted/inactive source references are removed before the
next call. Current settings are loaded afresh for every turn. User role assertions
never update business records.

## Dispatch and call budgets

Existing emergency/privacy checks, configured escalation shortcuts, medical
boundaries and pending explicit confirmation guards run first. Remaining turns
use one semantic call, including ambiguous appointment-related policy questions
and corrections. Action proposals enter the existing `_act` controller, with at
most one additional bounded response-generation call. Consent readbacks and
completed-operation receipts remain deterministic; knowledge turns do not enter
`_act` and cannot modify appointment state. The existing confirmation readiness,
settings fingerprint, ownership, slot checks and idempotency remain in force.

Generate-only integration adapters retain the legacy local route for backward
compatibility. The default production generator implements `interpret`; legacy
text-only test coverage is explicitly separated from semantic-path tests.

## Approved packet and validation

The packet is bounded to 32,000 serialized characters. It contains active typed
staff/service records, configured business facts, approved FAQ candidates, source
IDs, coverage counts, assistant capability facts, compact discourse, and generic
name-similarity candidates. Recent sources and typed facts have priority. Lexical
FAQ ranking selects evidence candidates only; it does not classify intent. Recent
history is capped to 12 entries of 1500 characters each. Workflow snapshots omit
pending executable payloads and receipts and expose only pending kind/readiness.

Python validates source/entity membership, uniqueness, staff-source agreement,
role/qualification predicates, complete list selection, required topic relations,
and discourse provenance. Near-tied name candidates require clarification; an
exact unique configured name takes precedence. Individual roles require a named
candidate or valid recent focus. List answers cannot manufacture a focused person.
Partial packets cannot authorize a complete staff/service list.

Approved FAQ prose is not a source of typed staff credentials. Staff/credential
FAQ prose is rejected, even if the model labels it another topic. Configured
business fields take priority over FAQ selections for the same topic. Action
service IDs and offered-slot IDs are checked before entering the controller;
appointment ownership remains in its existing database verification path.

The factual text contract uses Python renderings over validated relations. This
permits entity-specific answers, corrections, service overviews without unrequested
prices, and topic-specific unknowns. It does not pretend that arbitrary natural
language entailment can be established by ID validation. The smallest version
keeps wording bounded; richer phrasing requires additional locally verifiable
rendering variants, not a second model review.

If selection/schema/generation fails, Python uses a generic verification/clarify
fallback and preserves prior validated memory with aging. If only response text
fails, Python renders the already-validated selected relation without another
call. Oversized rendered answers also use the generic fallback. No invalid state
proposal is persisted and no fallback claims that an operation completed.

## Diagnostics and regression evidence

`SEMANTIC_TURN` logs effective turn kind, selected source IDs, resolved entity IDs,
answer mode, actual generative call count and fixed fallback reason. It does not
log caller text, generated prose, credentials or provider exception bodies.

`tests/test_semantic_conversation.py` covers all ten reported caller turns,
paraphrase dispatch, provider/schema failure, ID and memory poisoning, unsupported
roles/qualifications/prices/success claims, complete lists, current fact reload,
logistics retrieval, memory continuity and expiry, interrupted pending consent,
semantic corrections and action call budgets. SDK wire tests cover the new schema
and absent executable tools. These tests use controlled provider outputs; they
verify application behavior, not live interpretation accuracy.

`python -m scripts.replay_semantic_conversation` produces the controlled offline
before/after report and per-turn diagnostics in `docs/CONVERSATION_REPLAY.md` and
JSON. The `--live` option sends the synthetic conversation to the configured
Gemini provider and requires authorization for that payload. The current live
replay was blocked by network restrictions and automatic approval review; the
saved report is explicitly offline. No real database/calendar or microphone is
used by the replay.

Known limits: large catalogs may omit FAQ evidence (coverage is explicit); missing
data cannot be replaced with invented policy; the model can still select an
irrelevant but valid source. The schema and validators protect factual relations,
not all possible semantic interpretation errors. Startup/reconnect greeting
duplication is a separate transport concern; this change prevents semantic replies
from reintroducing the assistant but does not change the voice session lifecycle.
