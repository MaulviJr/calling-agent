# Ava: Python walkthrough from microphone transport to the reply

This guide follows procedures 9–22 of our conversation. Read one procedure at a
time with its source file open beside it. It describes the code inspected for
this guide, including the opening greeting and delayed waiting acknowledgement.
Examples marked “equivalent” expand compact code for teaching; they are not extra
functions in the application. Source links are relative to this document.

## Reading map

| Procedure | Open this file | Main code to find |
|---|---|---|
| 9. Send microphone bytes | [browser.py](../backend/app/voice/browser.py) | `receive`, `context.__enter__` |
| 10. Receive Deepgram events | [providers.py](../backend/app/voice/providers.py) | `flux_connection`, `flux_turn_settings` |
| 11. Queue finalized transcripts | [session.py](../backend/app/voice/session.py) | `Turn`, `VoiceSession.event` |
| 12. Process turns and acknowledge waiting | [session.py](../backend/app/voice/session.py) | `_run`, `_respond_with_acknowledgement` |
| 13. Load context and coordinate | [agent.py](../backend/app/agent.py) | `Receptionist.respond`, `call_lock` |
| 14. Interpret the request | [agent.py](../backend/app/agent.py), [prompts.py](../backend/app/prompts.py) | `GeminiConversationPlanner.decide`, `AgentDecision` |
| 15. Validate and act | [agent.py](../backend/app/agent.py), [scheduling.py](../backend/app/scheduling.py), [dates.py](../backend/app/dates.py), [calendar.py](../backend/app/calendar.py) | `_act`, `slots`, `mutate`, `_execute` |
| 16. Build trusted response data | [conversation.py](../backend/app/conversation.py) | `TrustedContext`, `ToolResult` |
| 17. Generate and check wording | [conversation.py](../backend/app/conversation.py) | `generate`, `check_surface`, `render_response` |
| 18. Save the conversation | [agent.py](../backend/app/agent.py), [database.py](../backend/app/database.py) | end of `respond`, database models |
| 19. Generate outgoing audio | [providers.py](../backend/app/voice/providers.py), [browser.py](../backend/app/voice/browser.py) | `ElevenSpeech`, `speak`, `enqueue`, `send` |
| 20. Play audio | [voice-session.ts](../frontend/lib/voice-session.ts) | `receive` |
| 21. Interrupt and mark delivery | [session.py](../backend/app/voice/session.py), [browser.py](../backend/app/voice/browser.py), [agent.py](../backend/app/agent.py) | `StartOfTurn`, `clear_audio`, `delivered` |
| 22. Finish the call | [browser.py](../backend/app/voice/browser.py), [agent.py](../backend/app/agent.py) | cleanup, `end` |

## Python foundations used throughout

```python
packet = b'example'
```

`packet` is a variable name. `=` binds the name to a value; it does not compare
values. `==` compares values. The `b` prefix creates bytes rather than normal
Unicode text. Real microphone packets contain binary sample values, not the
letters in this demonstration.

```python
def process(packet):
    return len(packet)
```

`def` defines a function. `process` is its name; `packet` is a parameter, a local
name for an argument supplied when calling it. The colon starts a block.
Indentation identifies which statements belong to that block. `return` sends a
value back and ends this function call. It does not end the whole application.

`process` refers to the function object. `process(packet)` calls it now. This
distinction explains callbacks, threads, timers and `asyncio.to_thread`.

```python
class Example:
    def __init__(self, value):
        self.value = value
```

`class` defines an object type. `Example(3)` creates an instance and initializes
it with `__init__`. `self` refers to that instance; Python passes it automatically
when you call an instance method. `self.value` is data stored on the object and
survives between method calls. A plain local variable exists within its function
call. `self` is a convention, not a special reserved keyword.

`None` means no value. `True` and `False` are booleans. Empty strings, empty
collections, zero and `None` are false-like in an `if`. `not` reverses a truth
test. `and` and `or` short-circuit: the right side may not be evaluated.
They also return operand values, which is why `voice or default_voice` works.

```python
settings = {'greeting': 'Hello'}
greeting = settings['greeting']
voice = settings.get('voice_id')
```

A dictionary maps keys to values. Square-bracket lookup raises `KeyError` if the
key is missing. `.get()` returns `None` by default instead. A Python dictionary
is not JSON: JSON is a textual serialization that can represent similar data.

`[]` also constructs lists; `items[0]` retrieves the first item. Python indexes
start at zero. `items[:4]` takes up to four items; `items[-12:]` takes up to the
last twelve. Slicing does not require that many items to exist.

`for item in items` visits each element. `break` leaves the current loop.
`continue` skips to its next iteration. Neither necessarily exits the function.

```python
try:
    result = operation()
except ValueError as exc:
    handle(exc)
finally:
    cleanup()
```

`try` runs work that may raise an exception. A matching `except` handles it;
`exc` names the exception object. `raise` creates or propagates a failure.
`finally` runs during normal return or exception unwinding too. It cannot
guarantee cleanup after a process crash or forced termination.

`with resource as item` uses a context manager: enter a resource scope, execute
the block, then leave the scope. Depending on the resource this can close a
connection, release a lock, or commit/roll back a database transaction.

`async def` defines a coroutine function. Calling it creates a coroutine object;
it must be awaited or scheduled. `await` waits cooperatively: other event-loop
tasks may run while this task waits. It does not automatically move arbitrary
Python code to a background thread. Blocking SDK work needs a thread or an
asynchronous SDK method.

`str`, `int`, `float`, `bool`, `bytes`, `list` and `dict` name common Python types.
Annotations like `text: str` document expected types; ordinary Python does not
enforce them automatically. Pydantic models add runtime validation separately.

## 9. Microphone audio reaches Deepgram

At this point the browser has already converted microphone samples into mono,
16 kHz, signed 16-bit PCM and sent 80 ms packets over a WebSocket. Read the
following nested function inside `browser_session` in `browser.py`:

```python
async def receive():
    while not stopped.is_set():
        packet=await asyncio.wait_for(ws.receive_bytes(),timeout=60)
        if not packet or len(packet)>16000 or len(packet)%2: raise ValueError('Invalid PCM packet.')
        await asyncio.to_thread(connection.send_media,packet)
```

1. `async def receive():` defines an asynchronous function with no explicit
   parameters. It is nested inside `browser_session`, so it can use that outer
   function's `ws`, `stopped` and `connection`. This access to enclosing variables
   is called a closure. Defining it does not start it.
2. `while` repeats the body. `stopped` is an `asyncio.Event`, an initially unset
   signal. `.is_set()` checks it without waiting. `not` means keep receiving
   while shutdown has not been requested.
3. `ws` is the FastAPI WebSocket object for this browser connection.
   `ws.receive_bytes()` is an asynchronous operation to receive one binary
   WebSocket message. It does not receive words or call Gemini.
4. `asyncio.wait_for(..., timeout=60)` places a 60-second limit on that receive
   operation. This is a packet-inactivity timeout, not a limit on the length of
   an utterance. A silent microphone generally still sends audio packets.
5. `await` pauses this coroutine until a packet arrives or receiving fails. Other
   event-loop tasks, such as sending outgoing audio, can continue.
6. `packet =` stores the resulting `bytes` object locally for this loop iteration.
7. `not packet` rejects an empty byte sequence. `len(packet)>16000` rejects an
   oversized message; the number here is bytes, not sample rate.
8. `%` is remainder. `len(packet)%2` is nonzero for an odd byte count. Each 16-bit
   sample needs two bytes, so an odd-sized packet is rejected.
9. The tests are joined by `or`: any one invalid condition triggers `raise`.
   `ValueError(...)` constructs the error. The one-line `if` is equivalent to an
   indented `if` whose body is that `raise` statement.
10. `connection.send_media` is a bound SDK method, passed without parentheses.
    `asyncio.to_thread(function, argument)` runs `function(argument)` in a worker
    thread. Here that means `connection.send_media(packet)`.
11. Awaiting the thread result waits for this send operation to finish without
    blocking the event-loop thread. It does not wait for the full transcript.
12. Control returns to `while` for the next packet. The long-lived Deepgram
    connection carries all of these packets; Ava does not create one per packet.

Where did `connection` come from? Earlier in the same outer function:

```python
context=flux_connection(event,lambda: loop.call_soon_threadsafe(stopped.set))
connection=await asyncio.to_thread(context.__enter__)
```

`flux_connection` is imported from `providers.py`. Its arguments are callbacks:
one handles provider events, the other signals failure/closure. A `lambda` is
a small anonymous function; `lambda: expression` has no parameters and evaluates
that expression when called. It does not execute immediately when constructed.

Because `flux_connection` is decorated with `@contextmanager`, calling it returns
a context-manager object. `context.__enter__` is the method normally invoked by
`with`. The code explicitly enters it in a thread because connecting may block.
That method runs the generator until `yield conn`, and its result becomes
`connection`. The corresponding `__exit__` is invoked later during cleanup.

**Check your understanding:** if a packet is 2,560 bytes, how much audio does it
contain? 2,560 / 2 / 16,000 = 0.08 seconds. Why is this not a transcript? It still
contains waveform samples, not recognized characters.

## 10. Connect to Deepgram and receive recognized words

Read these imports in `providers.py`:

| Statement | Meaning |
|---|---|
| `import os` | Access process environment variables, including configured API keys. |
| `import logging` | Obtain loggers and emit diagnostic messages. |
| `from contextlib import contextmanager` | Import the decorator that turns a generator into a context manager. |
| `from deepgram import DeepgramClient` | Import the third-party provider client class. |
| `from deepgram.core.events import EventType` | Import the provider's event identifiers. |
| `from elevenlabs.client import ElevenLabs` | Import the speech-generation client; used later. |
| `from google import genai` and `from google.genai import types` | Gemini SDK support. `GeminiChat` in this file is a retained adapter; the current receptionist uses the planner in `agent.py`. |

The connection function:

```python
@contextmanager
def flux_connection(on_event, on_error):
    import threading
    client = DeepgramClient(api_key=os.environ['DEEPGRAM_API_KEY'])
    thresholds = flux_turn_settings()
    with client.listen.v2.connect(model='flux-general-en', encoding='linear16',
            sample_rate=16000, **thresholds) as conn:
        conn.on(EventType.OPEN, lambda _: logging.getLogger('ava').info('STT_CONNECTED'))
        conn.on(EventType.MESSAGE, lambda m: on_event(
            getattr(m, 'event', ''), getattr(m, 'transcript', ''), getattr(m, 'turn_index', None)))
        conn.on(EventType.ERROR, lambda _: on_error())
        conn.on(EventType.CLOSE, lambda _: on_error())
        listener = threading.Thread(target=conn.start_listening, daemon=True, name='ava-stt')
        listener.start()
        try:
            yield conn
        finally:
            conn.send_close_stream()
```

1. `@contextmanager` is a decorator: it wraps the function below it with resource
   enter/exit behavior. The function must yield once during successful use.
2. `on_event` and `on_error` are ordinary parameters containing callable objects.
   Python allows functions to be stored and passed around like other values.
3. `import threading` imports thread support inside the function. A thread is an
   independently scheduled execution path within the same process, sharing memory.
4. `DeepgramClient(...)` constructs a client. `api_key=` is a keyword argument.
   `os.environ[...]` looks up a required environment variable; missing it raises
   `KeyError`. This is a lookup of an already-loaded value, not reading `.env` here.
5. `flux_turn_settings()` returns a dictionary of validated detection settings.
6. `client.listen.v2.connect(...)` creates the provider's connection context.
   Dots access attributes: the client exposes a listen API with a v2 connection
   method. `model` selects recognition/turn detection behavior. `linear16`
   describes PCM encoding; `sample_rate=16000` describes input samples per second.
7. `**thresholds` expands dictionary entries into keyword arguments. With the
   defaults, it is equivalent to adding `eot_threshold='0.7'` and
   `eot_timeout_ms='2000'` to this call.
8. `with ... as conn` enters the connection scope and binds its usable connection
   object to `conn`. Leaving the scope invokes the SDK's connection cleanup.
9. `conn.on(EventType.OPEN, callback)` registers a callback. It does not call it
   immediately. `lambda _:` accepts one event argument but ignores it. `_` is an
   ordinary variable name conventionally used for an unused value.
10. `logging.getLogger('ava').info(...)` obtains the named logger and emits an
    informational entry when the callback executes.
11. The MESSAGE lambda accepts `m`, a provider message object. It calls `on_event`
    with three extracted attributes. `getattr(m, 'event', '')` means “read
    attribute event, or return the supplied default if absent.” This is an
    attribute lookup, not dictionary lookup. The transcript defaults to an empty
    string and turn index to `None`.
12. ERROR and CLOSE callbacks both invoke the supplied `on_error` with no
    arguments. In the browser integration that schedules `stopped.set` on the
    event loop. The callback itself does not perform reconnection.
13. `threading.Thread(...)` constructs a thread but does not start it.
    `target=conn.start_listening` passes a function to execute later. Adding `()`
    here would incorrectly call it immediately.
14. `daemon=True` means this thread alone will not keep Python alive on process
    exit. It does not guarantee that the thread will gracefully clean itself up.
    `name` supplies a useful diagnostic label.
15. `listener.start()` starts execution of the listener on that thread. Incoming
    events can now invoke the registered callbacks while other work continues.
16. `yield conn` temporarily hands the connection to the caller. Unlike `return`,
    the generator remains suspended and can later resume for cleanup.
17. `finally` executes on context exit and calls `send_close_stream()` to request
    the provider stream close. The outer SDK `with` also handles its own resource.

The helper, statement by statement:

```python
threshold = float(os.getenv('DEEPGRAM_EOT_THRESHOLD', '0.7'))
timeout = int(os.getenv('DEEPGRAM_EOT_TIMEOUT_MS', '2000'))
```

Environment variables are strings. `getenv(name, default)` uses a default if the
name is absent. `float` converts a decimal string; `int` converts an integer
string. Invalid text raises `ValueError`. An empty configured string is not an
absent value, so the default does not automatically replace it.

```python
if not 0.5 <= threshold <= 1.0:
    raise ValueError(...)
if not 500 <= timeout <= 60000:
    raise ValueError(...)
return {'eot_threshold': str(threshold), 'eot_timeout_ms': str(timeout)}
```

Python supports chained comparisons. The first condition rejects values outside
the permitted range. `str(...)` converts validated numbers back to the string
form used by the connection parameters. The confidence threshold and forced
silence timeout influence when a final turn is emitted; they do not themselves
make a Gemini call.

The receiving callback in `browser.py`:

```python
def event(kind,text,index):
    session.event(kind,text,index)
    if kind=='StartOfTurn': loop.call_soon_threadsafe(clear_audio)
    elif kind=='EndOfTurn' and text.strip():
        loop.call_soon_threadsafe(lambda: output.put_nowait({'type':'transcript','text':text}))
```

`session.event` handles conversation scheduling first. `==` compares the event
name. `elif` is another condition evaluated only if the preceding `if` failed.
`strip()` removes leading/trailing whitespace; its truth value tests nonempty text.
The SDK callback can run on a separate thread. `call_soon_threadsafe` schedules
an ordinary callback on the asyncio loop, rather than manipulating its queue
directly from that thread. The JSON dictionary is a UI event. It is not the LLM
request and has not yet gone through the controller's redaction/persistence.

## 11. Turn objects, queues, and interruption state

Open `session.py`. `logging`, `queue`, `threading` and `time` provide logging,
thread-safe queues, thread synchronization, and elapsed-time clocks.
`dataclass` and `field` come from Python's standard library.

```python
@dataclass
class Turn:
    text: str
    generation: int = 0
    cancel: threading.Event = field(default_factory=threading.Event)
    received: float = field(default_factory=time.monotonic)
    is_greeting: bool = False
```

`@dataclass` generates routine methods, including an initializer, from the
declared fields. `text` is required because it has no default. The other fields
have defaults. `generation` identifies the speech generation this turn belongs
to; it is separate from Deepgram's deduplication index.

`default_factory=threading.Event` calls `threading.Event()` separately for each
Turn. This is essential: each reply needs its own cancellation flag. Constructing
one shared Event as a default would allow cancelling one turn to affect others.
Similarly `time.monotonic` is called at creation time to record elapsed-time
reference. Passing the function without `()` defers evaluation until creation.
`is_greeting` distinguishes outbound startup speech from a caller request.

Inside `VoiceSession.__init__`, read each assignment:

| Statement | Meaning |
|---|---|
| `self.respond, self.speak, self.on_reply = respond, speak, on_reply` | Tuple assignment stores three callbacks on this session. No callback executes yet. |
| `self.speak_greeting = speak_greeting or speak` | Use a separate greeting speaker if supplied; otherwise reuse normal speech. |
| `self.wait_seconds = wait_seconds` | Delay before optional acknowledgement; default one second. |
| `self.wait_count = 0` | Counter used to alternate acknowledgement phrases. |
| `self.pending = queue.Queue(maxsize=16)` | Thread-safe FIFO queue with a bounded capacity. |
| `self.closed = threading.Event()` | Whole-session shutdown signal, separate from a turn's cancellation. |
| `self.lock = threading.Lock()` | Mutual-exclusion lock around shared session state. |
| `self.current = None` | No turn is being processed yet. |
| `self.last_final_index = -1` | No finalized provider index has been accepted yet. |
| `self.generation = 0` | Initial interruption generation. |
| `self.failed = False` | No worker failure observed yet. |
| `self.worker = threading.Thread(target=self._run, ...)` | Prepare a daemon worker, without starting it. |

The default `on_reply=lambda text, interrupted: None` is a no-op function that
accepts the two expected arguments and returns `None`. It permits use without a
delivery callback, such as in focused tests.

`start(greeting='')` checks `greeting.strip()`, queues a greeting Turn if nonempty,
then calls `worker.start()`. Greeting processing bypasses the normal responder.

Now `event()` in execution order:

1. `with self.lock:` prevents another session-state update from entering this
   locked block simultaneously. Exiting it releases the lock, including on return.
2. `if self.closed.is_set(): return` ignores events after shutdown.
3. On `StartOfTurn`, `self.generation += 1` increments the interruption version.
4. `if self.current:` checks that a current Turn exists, then sets its cancel flag.
5. `with self.pending.mutex:` locks the queue's underlying storage while iterating
   over queued turns. This code uses queue internals; ordinary producer/consumer
   code usually needs only `put` and `get`.
6. Each queued Turn's cancellation event is set. The turn remains queued so the
   controller can still account for finalized user input; outdated audio is suppressed.
7. `return` ends handling of this StartOfTurn event.
8. Other events must equal `EndOfTurn` and contain non-whitespace text. Otherwise
   return without invoking the model.
9. An absent index or an index no greater than `last_final_index` is ignored. This
   avoids processing duplicate finalized provider messages.
10. Store the new index, construct `Turn(transcript.strip(), self.generation)`,
    and call `put_nowait` to enqueue it without blocking the listener thread.
11. Log `USER_TURN_FINALIZED` after successful insertion.
12. If `queue.Full` is raised, mark the session failed and closed, then log overflow.
    The queue bounds resource growth; it does not silently make processing faster.

**Check:** `Update` does not call Gemini. `EndOfTurn` puts work in a queue. The
actual Gemini call happens farther downstream, on the worker path.

## 12. The worker and waiting acknowledgement

Read `_run()` as a continuous consumer loop:

1. `while not self.closed.is_set()` runs until shutdown is observed.
2. `self.pending.get(timeout=.1)` waits up to 0.1 seconds for a turn. A timeout
   raises `queue.Empty`; `continue` returns to the top so shutdown is checked again.
3. Under `self.lock`, the retrieved Turn becomes `self.current`.
4. Compare `turn.generation` with `self.generation`. Speech may have started after
   queue removal but before this lock was acquired. A mismatch cancels stale audio.
5. For a greeting, speak only if not cancelled, then `continue`. Python still
   executes the enclosing `finally` when continuing out of a try block.
6. For caller input, log `VOICE_TURN_STARTED` and call `_respond_with_acknowledgement`.
7. Compute `(time.monotonic() - turn.received) * 1000`. The result is milliseconds
   since enqueueing and can include queueing and acknowledgement time.
8. `if reply and not turn.cancel.is_set()` speaks only a nonempty, current reply.
9. `self.on_reply(reply, turn.cancel.is_set())` reports final delivery handling.
   It may report an interrupted reply even when its audio was never started.
10. The exception handler marks `failed` and logs only the exception class.
11. The `finally` block clears `current` under the lock and calls `task_done()`.
    `task_done` accounts for dequeued work; it does not remove another queue item.

The callback wiring in `browser.py` is equivalent to:

```python
def respond_to_caller(text):
    return agent.respond(business_id, call_id, text, uid())

def report_delivery(text, interrupted):
    agent.delivered(business_id, call_id, interrupted)
```

The actual code uses lambdas. `uid()` generates a request key when the responder
is invoked. The callback captures this connection's business and call IDs, so
`VoiceSession` does not need to understand authentication or database schemas.

`_respond_with_acknowledgement()` installs a turn-local lookup observer using a
ContextVar. `calendar_read` in `lookup.py` signals only around actual calendar
`get`/`busy` calls; appointment ownership reads also signal their lookup scope.
Each lookup starts the configured delay. When that lookup ends, its timer is
cancelled and joined. Slow planning or language generation never starts a timer.
The callback checks that the lookup is still active, the turn is current and the
session is open. It speaks at most once per turn, sharing the interruption flag.
Final speech waits for acknowledgement speech to finish. Only the final reply
receives a delivery callback, so filler cannot authorize a booking.

## 13. Receptionist.respond: load memory and coordinate

In `agent.py`, `Receptionist.__init__` stores the database session factory,
scheduler and planner. It uses a supplied response generator or constructs a
default GeminiResponseGenerator. These are dependencies passed into the controller.

`respond(business_id, call_id, transcript, request_key)` receives four ordinary
values: the authenticated business, active call, finalized text, and request key.

The first scope is `with call_lock(self.sessions, call_id)`. This serializes
controller operations for the call. `call_lock` hashes the ID into a signed
integer, uses one of 64 process `RLock`s, and additionally takes a PostgreSQL
advisory lock when using PostgreSQL. `RLock` is reentrant: the same thread may
acquire it again. The `finally` in the PostgreSQL branch releases the advisory
lock. SQLite's protection here is process-local, not a distributed lock.

The read portion:

```python
with self.sessions() as db:
    call=db.scalar(select(Call).where(Call.id==call_id,Call.business_id==business_id))
    if not call or call.status!='active': raise ValueError('Active call not found.')
    settings=BusinessSettings.model_validate(db.get(Business,business_id).settings)
    state=AppointmentState.model_validate(call.state)
    if request_key in state.receipts: return state.receipts[request_key]
```

1. `self.sessions()` constructs a SQLAlchemy database session. `as db` binds it.
2. `select(Call)` constructs a SQL query for Call rows. `.where(...)` adds both
   call ID and business ID conditions. SQLAlchemy overloads the model-column `==`
   operation to build SQL expressions; it is not comparing two loaded rows here.
3. `db.scalar(...)` executes and returns the first scalar result, which here is
   a mapped Call object, or `None` if no row was found.
4. Reject a missing or inactive call. The short-circuit `or` avoids reading
   `call.status` when `call` is `None`.
5. `db.get(Business, business_id)` retrieves a primary-key row. `.settings` is its
   stored JSON dictionary. `model_validate` constructs a validated settings model.
6. Validate `call.state` into an AppointmentState object too.
7. `request_key in state.receipts` checks dictionary membership. Returning the
   saved reply makes an identical keyed request idempotent instead of repeating work.

The next list comprehension loads history:

```python
history=[{'role':t.role,'text':t.text,'delivery':t.delivery} for t in db.scalars(
    select(TranscriptTurn).where(TranscriptTurn.call_id==call_id).order_by(TranscriptTurn.created_at))]
```

`db.scalars` iterates matching mapped objects. `order_by` requests time ordering.
The expression before `for` constructs one dictionary for each row. Equivalent
ordinary syntax is `history=[]`, then a `for` loop appending each dictionary.

After the read scope, `transcript.strip()` removes edge whitespace and `redact`
replaces obvious 13–19 digit card-like sequences with `[number omitted]` using a
regular expression. This is a heuristic, not comprehensive sensitive-data detection.
Empty input and more than the allowed number of request receipts are rejected.

`context=None` initializes the variable before the try block, allowing later
code to inspect it even when an earlier branch failed.

The decision chain lowercases input and checks emergency phrases, a card-redaction
marker, a recognized affirmative utterance with pending consent, and escalation
keywords. `any(...)` returns true if at least one generated condition is true.
These branches construct Decision objects directly. Otherwise the controller
calls `self.llm.decide(transcript, state, settings, history)` and measures its time.

Then:

```python
context=self._act(business_id,call_id,state,settings,decision,transcript,request_key,history)
outcome=context.outcome
reply=render_response(self.response_generator,transcript,history,
    state.model_dump(mode='json',exclude={'receipts','pending'}),context)
state.failures=0
```

`_act` mutates the operational state and returns response context. The underscore
marks an internal-method convention, not a Python access restriction. `model_dump`
converts the state model to a dictionary, excluding receipt and pending payload
details from the language generator. `mode='json'` produces JSON-compatible values.
Successful handling resets the consecutive failure count.

`except ValueError` distinguishes Pydantic ValidationError from other validation
errors. The former gets fixed safe wording; other validation errors become context
for an explanation. `except Exception` handles other ordinary failures, increments
the count and produces a fixed fallback; repeated failures switch to message mode.
Exceptions in the later persistence block are outside these handlers and can still
propagate to the voice worker.

## 14. The exact Gemini planning request

`AgentDecision` is a Pydantic model containing an allowed action, optional caller
fields, FAQ/topic selection and conversational metadata. `Literal[...]` restricts
values, `str | None` allows either text or no value, and `Field(max_length=...)`
adds runtime constraints. Optional fields let the model report only newly provided
information rather than invent missing names, numbers or dates.

`AppointmentState` stores the collected fields, offered/selected slots, pending
action, mode, failure count and receipts. `Field(default_factory=list/dict)` makes
a fresh collection for each model instance. `Decision = AgentDecision` and
`GeminiExtractor = GeminiConversationPlanner` are compatibility aliases, not
additional model calls.

`LLMProvider(Protocol)` describes the expected `decide` method for type checking.
It is not the network provider itself. Test doubles can implement the same method.

In `GeminiConversationPlanner.__init__`:

```python
self.client=genai.Client(api_key=os.environ['GEMINI_API_KEY'],
    http_options=types.HttpOptions(timeout=30000))
self.model=os.getenv('GEMINI_MODEL','gemini-3.5-flash-lite')
```

Construct the SDK client with a required key and a 30,000 ms HTTP timeout, then
select the configured model or default. Never print the key to debug this call.

In `decide`, this statement is the actual remote model invocation:

```python
result=self.client.models.generate_content(model=self.model,
    contents=json.dumps({'caller':transcript,'state':state.model_dump(exclude={'receipts'}),
        'business':settings.model_dump(mode='json'),'history':history[-30:]}),
    config=types.GenerateContentConfig(system_instruction=EXTRACTION_PROMPT,
        response_mime_type='application/json',response_json_schema=Decision.model_json_schema(),
        temperature=0,automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)))
return Decision.model_validate_json(result.text)
```

1. `json.dumps` serializes the supplied Python dictionary to JSON text.
2. `caller` supplies the current transcript. `state` excludes receipts, while the
   planner can still inspect pending state. `business` supplies approved settings.
3. `history[-30:]` supplies at most the last 30 transcript entries, not 30 calls.
4. `EXTRACTION_PROMPT` is a string imported from `prompts.py`; it describes how to
   interpret requests, select FAQ topics and handle corrections/clarification.
5. `response_mime_type` requests JSON output. `model_json_schema()` creates a
   machine-readable description of permitted Decision fields and values.
6. `temperature=0` asks for low sampling variation; it does not guarantee correctness.
7. `AutomaticFunctionCallingConfig(disable=True)` disables SDK automatic tool calls.
   The planner returns a proposal. The application executes its own functions later.
8. `result.text` contains the provider's response text. `model_validate_json`
   parses and validates it. Invalid output raises instead of becoming arbitrary
   executable instructions.

At this stage the system has a proposed action such as `faq` or `book`, not the
final spoken answer. For example, `action='faq', business_topic='services'` tells
Python which approved facts to retrieve.

## 15. Python validates the decision and executes procedures

### The controller's `_act` function

The parameters `bid` and `cid` abbreviate business ID and call ID. `d` is the
validated decision, `text` is the caller transcript, and `state` is the mutable
AppointmentState for this call. `history=history or []` supplies an empty list
when no history was passed. The nested helpers build response context:

| Helper | Work |
|---|---|
| `context(kind, goal, baseline, *, facts=None, result=None, outcome=None, fallback=None)` | Construct TrustedContext from application-owned values. `*` makes following parameters keyword-only. |
| `fixed(baseline, outcome=None, *, confirmation=False)` | Construct protected text and flag whether it is a consent readback. |
| `ask(goal, baseline, facts=None)` | Construct context whose purpose is asking or explaining a missing detail. |

`facts or {}` supplies an empty dictionary when there are no facts. The
conditional expression `['speak','ask_question'] if '?' in baseline else ['speak']`
selects allowed speaking actions according to the baseline question. The model
receives that list as a constraint; it does not grant database permissions.

The first branches check emergency, payment-card and medical-advice handling.
They return protected wording, bypassing free-form response generation. The
emergency branch also clears pending consent. A `return` exits `_act` immediately;
branches below it do not execute for that turn.

Next comes field merging, before normal conversational branches:

```python
changed=False
for field in ('caller_name','phone','email','service_id','date_phrase','time_phrase','appointment_id','message_text'):
    value=getattr(d,field)
    if value is not None and value!=getattr(state,field):
        setattr(state,field,value)
        changed=True
        if field in ('service_id','date_phrase','time_phrase'):
            state.selected_slot=''
            state.offered_slots=[]
if changed:
    state.pending=None
```

This teaching excerpt expands semicolon-separated statements into separate lines.
`getattr` reads an attribute whose name is held in a variable. `setattr` writes
one that way. `is not None` distinguishes “not supplied this turn” from a supplied
value. Any changed caller/action detail invalidates old consent. Changing the
service or date/time also clears the earlier selected/offered times.

If `d.selected_slot` is supplied, it must be a member of `state.offered_slots`.
`not in` rejects invented selections. Changing the selection clears pending
consent before storing the new selected slot.

The remaining branches run in the following order:

1. **Clarify:** return a question asking for the missing subject. No knowledge
   lookup or calendar operation is performed.
2. **Out of scope:** explain receptionist scope and ask what clinic help is needed.
3. **Greeting:** if consent is pending, repeat a protected readback. Otherwise
   provide conversational context including assistant name and AI identity.
4. **Conversation/meta:** obtain the previous user turn using a generator over
   `reversed(history)` and `next(..., None)`. Select an appropriate baseline for
   hearing, identity, previous turn, interruption, wellbeing or general scope.
   `next` with a default avoids an exception when there is no prior user turn.
5. **Capabilities:** build a list according to which settings are present, then
   pass those supported capabilities as response context.
6. **Confirm:** only enter the mutation path if the proposed action is confirm,
   a pending action exists, the entire utterance matches `_yes`, and no details
   changed. A model-proposed confirm action alone is insufficient.
7. **FAQ:** select an approved settings topic or valid knowledge index. No matching
   information means a missing-information context, not an invented answer.
8. **Mode selection:** update `state.mode` for message, cancellation, reschedule
   or booking. This mode persists across turns. A caller saying only a phone
   number can therefore continue the existing operation.
9. **Message mode:** collect name, validate callback phone, collect message, then
   save a pending message and ask for confirmation. The actual insert occurs only
   in the confirmation branch. Human requests flag escalation but do not perform
   a live telephone transfer.
10. **Cancel/reschedule mode:** request appointment reference and original phone.
    Query a booked appointment scoped to this business. Normalize both phones
    with `re.sub(r'\D', '', ...)` before comparing. `\D` means a non-digit.
    Failure returns an unverified result rather than exposing appointment details.
    Cancellation creates a pending cancellation with its settings fingerprint.
11. **Unknown request:** if there are no useful appointment details yet, ask what
    help is needed instead of assuming a booking.
12. **Services/date:** reject an unconfigured service list, select the sole active
    service or ask the caller to choose, and request a date if missing.
13. **Slot search:** if no slot is selected, resolve date/time and call the scheduler.
    If the requested time has no results, try the rest of the day. No results
    means a trusted unavailable result. Multiple results are offered for selection;
    a single result is selected but is still not a booking.
14. **Caller details:** for a new booking, request missing name, phone and required
    email one at a time. Construct a validated Booking object when ready.
15. **Pending action:** save kind, generated operation key, payload and settings
    fingerprint, then return an exact confirmation readback.

These are application procedures, not a Gemini tool-calling loop. A normal
turn often exits after just one question or information answer.

### Understanding confirmation code

`_normalized` lowercases text, normalizes a curly apostrophe, replaces most
punctuation with spaces and strips edge whitespace. `_yes` compares the entire
normalized utterance with an explicit set of accepted affirmations. It does not
search for a `yes` substring inside “yes, but change it to tomorrow.”

`@staticmethod` defines a method that receives no automatic `self` or `cls`.
`@classmethod` supplies the class as `cls`; `_yes` uses `cls._normalized(...)`.

Inside the confirmation branch:

```python
pending=state.pending
if pending.get('ready') is False:
    return fixed(..., confirmation=True)
fingerprint=hashlib.sha256(settings.model_dump_json().encode()).hexdigest()
```

`pending` refers to the pending-action dictionary. `.get('ready') is False`
checks the explicit false boolean set for unread/interrupted voice readbacks.
`model_dump_json()` produces settings JSON text; `.encode()` converts it to bytes;
SHA-256 hashes those bytes; `.hexdigest()` produces a comparable string. This is
a change detector for settings, not encryption or a caller identity check.

If settings changed since the readback, Python clears the pending action and
selection and asks for a fresh selection. Otherwise a confirmed message is
inserted with a duplicate-key check, or the scheduler is called:

```python
result=self.scheduler.mutate(bid,pending['key'],pending['kind'],pending['payload'],True)
```

Each square-bracket lookup retrieves a required saved field. The final `True`
passes confirmed status. The proposed operation comes from the saved payload,
not fresh free-form words generated during the confirmation response.

Only after successful return are pending state cleared and a completed result
constructed. Date formatting such as `{local:%A, %B %d at %I:%M %p}` inside an
f-string turns a datetime into human-readable weekday/month/day/time text.

### FAQ retrieval syntax

For services, a comprehension selects `s for s in settings.services if s.active`.
An f-string formats each name/duration/price. `'; '.join(...)` joins the resulting
strings with semicolons. This creates source information for the response generator.
A separate fallback builds readable sentences from those structured service fields.

For hours, `sorted(..., key=lambda h: h.weekday)` orders entries by weekday.
`weekdays[h.weekday]` maps the numeric weekday to its name. A time format such as
`{h.opens:%H:%M}` prints 24-hour hours/minutes. The business timezone is included.

`getattr(settings, d.business_topic)` is safe from arbitrary topic names because
the decision schema limits the allowed topic values. An approved knowledge entry
is retrieved only after checking the index is not None and is below list length;
Pydantic already disallows negative FAQ indexes.

### Dates: `dates.py`

`aware(value)` attaches UTC metadata to a naive datetime; otherwise it returns
the original aware datetime. A *naive* datetime lacks timezone metadata. An
*aware* datetime includes it. This helper is used where persisted naive values
are understood to represent UTC; attaching a timezone is not the same as
converting a clock reading from another timezone.

`wall_time(day, clock, zone)` combines a calendar date and local time. It compares
the offsets with `fold=0` and `fold=1` to reject ambiguous/nonexistent daylight-
saving transitions. It also round-trips through UTC and rejects a local time
that fails to round-trip. Accepted times carry the requested timezone.

`resolve_date(phrase, zone, now)`:

1. Convert `now` to the business timezone and take `.date()`.
2. Normalize the phrase with `.strip().lower()`.
3. Return today directly or add `timedelta(days=1)` for tomorrow.
4. Define ordered weekday names and remove the optional `next ` prefix.
5. For weekdays, calculate `(requested_index - current_weekday) % 7`.
   `delta or 7` ensures a same-weekday request resolves to the next occurrence.
6. Try parsing `%Y-%m-%d` with `datetime.strptime`.
7. If that raises ValueError, try a month/day phrase with the current year.
8. Roll a past month/day into the following year, or raise a clarifying error
   when parsing is unsupported.

`time_window(phrase)` normalizes text, handles any/morning/afternoon/evening, then
uses `re.fullmatch` for a supported time expression. `r'...'` is a raw string,
useful for regex backslashes. Capturing groups are unpacked into modifier, hour,
minute and AM/PM. Missing minutes default to zero. AM/PM converts to a 24-hour
hour; a bare ambiguous hour asks for clarification. `after` returns a start/end
window; an exact time returns `(clock, clock)`. The two-item return is a tuple.

### Scheduling validation: `scheduling.py`

The `Booking` Pydantic model checks name length, phone syntax/digit count, a basic
email shape and timezone presence. `@field_validator` runs custom validation for
a named field. A classmethod validator takes `cls` and the value, returns a valid
value, or raises ValueError. This verifies format, not actual phone ownership.

`Scheduling` stores `sessions`, the calendar adapter, and a `clock` function.
Injecting a clock allows deterministic tests without changing the machine time.

`locked(business_id)` uses a process lock for SQLite and a database Business row
lock for PostgreSQL. The `with self.sessions.begin()` scope is a transaction:
commit on clean exit, roll back on an exception escaping that scope. A yielded
tuple contains the session and validated business settings for the caller.

`validate(settings, service_id, start)` performs these statements in order:

1. `next((s for s in settings.services if ...), None)` finds an active service.
2. Reject a missing service or timezone-naive start.
3. Convert to the business timezone with `astimezone` and validate its wall time.
4. Read the clock and enforce minimum notice and maximum advance days.
5. Add the service duration to compute the appointment end.
6. Find the configured opening interval for the local weekday.
7. Reject absent hours, crossing the local date, starting before opening, or
   ending after closing. The `or` conditions combine those invalid cases.
8. Reject seconds/microseconds and minutes not divisible by five.
9. Return the computed end datetime. This method alone does not query Google.

`free(...)` builds a buffer timedelta, obtains Google busy intervals and checks
overlap using `busy_start < appointment_end` and `busy_end > appointment_start`.
It also checks booked database appointments, excluding the event being moved.
Return False on a conflict; otherwise return True.

`slots(...)`:

1. Read settings and the day's opening interval; return `[]` if closed.
2. Use `max` and `min` to restrict the search to requested/opening time bounds.
3. Fetch busy periods once for the search window, then extend the list with local
   booked appointments. `+=` here extends a list, rather than adding numbers.
4. Create `result=[]` and iterate candidate times until the window ends or 12
   slots have been found.
5. Call `validate` for each candidate and append its ISO-formatted start when
   there is no overlap. `any(...)` is true if at least one interval conflicts.
6. A candidate's ValueError is intentionally skipped. Calendar/network errors
   are not swallowed by that candidate-level handler.
7. Add 15 minutes to the candidate and repeat, then return the result list.

### Mutations and recovery, statement by statement

`mutate(business_id, key, kind, payload, confirmed=False)` first rejects missing
confirmation, unsupported operation kinds, or an invalid idempotency key.

In its first locked transaction it looks up an existing Operation with the same
business/key. If found, it rejects reuse for different arguments, returns a
completed result, or rejects a previously rejected operation. Otherwise it checks
for unresolved pending/uncertain operations, creates a pending Operation and
calls `db.flush()` to send the insert and obtain its ID. Leaving the transaction
commits this intent before any external calendar mutation.

`flush()` is not `commit()`: it synchronizes pending ORM changes with the database
inside the current transaction. A later rollback can still undo those changes.

In a second locked transaction, `mutate` loads the operation, checks completion
again, calls `_execute`, records result ID/completed status, flushes, and converts
the result row into a dictionary using `record`. ValueError marks rejection;
other execution failures mark uncertainty and create a CalendarUnavailable error.
The error is stored and raised *after* the transaction ends, so the durable
rejected/uncertain status can commit rather than be rolled back by that raise.

`_execute(db, settings, op)`:

1. Read `payload` and initialize `existing=None`.
2. For create, validate Booking, verify its call belongs to the business, enforce
   any required email, and use the operation ID as stable Google event ID.
3. For cancel/reschedule, load the business-scoped appointment, use its event ID,
   and build booking values from its stored caller/service data and requested time.
4. Retrieve the remote event. Read its private `ava_operation` marker using
   chained `.get` calls with empty dictionary defaults.
5. For cancellation, delete an existing remote event using its ETag, mark the
   local appointment cancelled and return it.
6. For create/reschedule, reject an inactive existing appointment, calculate end,
   and check whether the remote marker already equals this operation ID.
7. When the marker differs, check ownership/missing-event conditions, revalidate
   booking rules and availability, and build the Google event body.
8. Update the existing event or create a new event using a conditional expression.
   The body includes start/end timezone data and private operation/business markers.
9. Parse the committed remote start/end values. On recovery, these are authoritative
   even if configuration changed after the remote action originally happened.
10. Insert a new Appointment or update the existing one's times, flush and return it.

These locks serialize cooperating Ava writers. They cannot make Google's separate
availability check and insertion atomic against someone editing Google directly.

### Google adapter: `calendar.py`

`CalendarProvider(Protocol)` describes the expected `busy/get/create/update/delete`
interface. `GoogleCalendar` implements it; the scheduler does not need to know
how OAuth headers or HTTP requests are made.

`__init__` reads the calendar ID and credential file path, rejects missing config,
loads service-account credentials with calendar event/free-busy scopes, and creates
an `AuthorizedSession`. It stores the API base URL and an event path containing
`quote(calendar_id, safe='')`, which URL-encodes the calendar ID.

`_request(method, path, **kwargs)` is the shared HTTP method. Here `**kwargs`
collects extra keyword arguments into a dictionary (the inverse of expanding it
at a call site). It calls the authorized HTTP session with a 15-second timeout.
Transport failures become CalendarUnavailable. `raise ... from None` hides the
original exception chain in the raised error's presentation.

HTTP 404/410 return None; 409 becomes a conflict error; other unsuccessful statuses
raise an error. Successful nonempty responses are decoded with `.json()`;
an empty response becomes `{}`.

`get(event_id)` requests one event and treats a remotely cancelled event as absent.
`busy(start, end, exclude=None)` normally POSTs the interval to `/freeBusy`, verifies
the expected busy data exists without provider errors, and turns each ISO timestamp
pair into datetime objects. Missing data is not interpreted as “everything is free.”

When excluding the original event for rescheduling, `busy` lists expanded events
instead, follows `nextPageToken`, skips exactly that event and transparent/cancelled
events, and treats all-day events conservatively as busy in the calendar timezone.
`while True` continues until the code explicitly returns when no next page exists.

`create` POSTs a body with a stable ID. `{**body, 'id': event_id}` copies dictionary
entries then sets/overrides the id. `update` PATCHes with `If-Match: etag` and
`delete` sends DELETE with the same version precondition. An ETag lets the provider
reject changes based on an outdated event version.

`UnconfiguredCalendar.__getattr__` returns a function that raises an unavailable
error for requested adapter methods. This keeps missing configuration explicit
instead of falling back to fabricated availability.

## 16. TrustedContext and ToolResult are data, not tools

In `conversation.py` these classes inherit `StrictModel`, which inherits Pydantic's
BaseModel and forbids unexpected fields. Unlike ordinary type annotations,
Pydantic validates values when constructing/parsing these objects.

| Field | Meaning |
|---|---|
| `ToolResult.action` | Which application operation produced this result. |
| `ToolResult.status` | Available, unavailable, completed or unverified. |
| `ToolResult.facts` | The application-owned result values. |
| `TrustedContext.kind` | Fixed, conversation, question, knowledge or result. |
| `goal` | Authorized purpose of the next reply. |
| `baseline` | Controller-authored wording expressing its intended meaning. |
| `approved_facts` | Retrieved business/capability facts. |
| `tool_result` | Optional actual tool outcome. |
| `allowed_actions` | Speak and optionally ask a question; no database authority. |
| `outcome` | Structured outcome to record on the call. |
| `requires_confirmation` | Whether this reply is the consent readback. |
| `fallback_text` | Optional safe application-rendered fallback. |

`ResponseDraft` contains bounded nonempty text. `ResponseRejected` carries a
fixed local diagnostic code. There is no grounding-review model call.

## 17. Routing, response generation, checks and fallbacks

`Receptionist._route` selects conversation and approved knowledge locally using
normalized intent patterns and deterministic question matching. Action requests
and workflow details use the planner. Python owns facts, state, tools, consent,
calendar truth and side effects throughout.

| Route | LLM budget |
| --- | --- |
| `fixed` | 0, including safety, deterministic confirmation and cached receipts |
| `conversation` | 1 response-generation call |
| `knowledge` | Deterministic retrieval plus 1 response-generation call |
| `booking` | At most 2: planner and response generator |

A planner-driven workflow that produces a protected confirmation or receipt
uses only its planner call. It does not spend a generation call on fixed wording.
`TURN_COMPLETED` logs `call_id`, `route` and `llm_calls`, including failures and
cached replies. SDK automatic retries are disabled to keep the budget bounded.

The generator requests one structured ResponseDraft with no executable tools.
Local checks reject unsupported numbers, protected transaction language and
changes to business or tool content. Knowledge rewriting conservatively retains
content words; a simple staff-list inversion and application-authored service
wording are allowed. These checks are deliberately restrictive and are not a
general semantic proof for arbitrary language.

Fixed safety/consent and completed-action contexts bypass generation. A failed
or rejected draft uses the application fallback; it never invokes another model,
repeats a side effect or changes consent. Unknown knowledge remains unknown.

## 18. Save the final turn and state

At the end of `Receptionist.respond`:

```python
state.receipts[request_key]=reply
with self.sessions.begin() as db:
    call=db.get(Call,call_id)
    if state.phone: call.caller_phone=state.phone
    assistant_turn=TranscriptTurn(id=uid(),business_id=business_id,call_id=call_id,
        role='assistant',text=reply,delivery='generated' if call.transport!='text' else 'text')
```

The first line saves the keyed reply in the in-memory state; the subsequent
transaction persists that state. `sessions.begin()` opens a session/transaction
scope. `db.get` retrieves the call. A nonempty collected phone updates its caller
phone. Constructing `TranscriptTurn(...)` creates a Python ORM object; it is not
inserted until added/flushed. An explicit `uid()` makes its ID available now.
The conditional expression assigns generated status to voice output and text
status to the text demo.

If there is a pending action, this is a voice call, and this context is a consent
readback, Python stores `ready=False` and the assistant transcript ID as
`confirmation_turn_id`. An ordinary meta response must not replace that ID.

`call.state=state.model_dump(mode='json')` assigns a fresh serializable dictionary.
If a new outcome exists, store it. `db.add_all([...])` registers the caller and
assistant TranscriptTurn objects for insertion. Leaving the transaction commits
these changes. `return reply` then passes the text back to the voice worker.

In `database.py`, each class inheriting `Base` is an ORM model:

| Model | Persistent purpose |
|---|---|
| Business | Validated settings stored as JSON. |
| Call | Call identity, status, timestamps, outcome, summary and operational state. |
| TranscriptTurn | One user/assistant message and delivery status. |
| Appointment | Booked/cancelled appointment and linked calendar event ID. |
| Operation | Durable mutation intent, idempotency key, status and result ID. |
| Message | Confirmed staff message and review/escalation fields. |
| Admin, LoginSession | Staff authentication, outside the per-audio-packet flow. |

`Mapped[str]` describes a mapped Python attribute. `mapped_column(...)` configures
the database column. `primary_key=True` identifies rows; `ForeignKey(...)` links
tables; `UniqueConstraint(...)` enforces uniqueness in the database. A `default=uid`
passes a callable for fresh IDs; `default=uid()` would evaluate too early.

`database()` chooses DATABASE_URL, creates an SQLAlchemy engine and returns a
session factory. The engine manages connectivity/pooling, while a session tracks
a particular unit of ORM work. `record(row)` constructs a dictionary from mapped
columns and restores explicit UTC metadata for naive persisted timestamps.

## 19. Text becomes audio and is sent to the browser

First read `ElevenSpeech` in `providers.py`:

```python
class ElevenSpeech:
    def __init__(self, voice=None):
        self.client = ElevenLabs(api_key=os.environ['ELEVENLABS_API_KEY'], timeout=30)
        self.voice = voice or os.getenv('ELEVENLABS_VOICE_ID', 'JBFqnCBsd6RMkjVDRZzb')

    def stream(self, text):
        return self.client.text_to_speech.stream(text=text, voice_id=self.voice,
            model_id='eleven_flash_v2_5', output_format='pcm_16000')
```

The initializer creates the provider client. The voice argument is optional;
a nonempty business voice takes priority over environment/default configuration.
`stream` returns an iterable speech stream rather than combining the whole
response into one big audio file. Iterating it yields chunks of PCM bytes.
The ElevenLabs timeout here is seconds; Gemini HttpOptions above uses milliseconds.

Now the nested `speak(text, cancel, announce=True)` in `browser.py`, line by line:

1. If `announce` is true, enqueue a `reply` dictionary so the UI displays text.
   The greeting passes false because its text already arrived in `ready`.
2. `stream=tts.stream(text)` obtains the iterable; record a monotonic start and
   `first=True` to track the first outgoing audio frame.
3. Initialize provider-read timing and total received PCM byte count.
4. `pending=b''` starts an empty bytes buffer; construct `PcmPacer`.
5. `for chunk in stream` obtains provider chunks. Iteration may block awaiting
   network data; it runs on the speech worker/timer thread, not the asyncio loop.
6. Update maximum observed provider wait and total byte count.
7. If the turn was cancelled or the browser stopped, break out of the stream loop.
8. `pending += chunk` concatenates bytes. A provider chunk need not be exactly
   one desired playback frame, so it is accumulated first.
9. While at least 640 bytes remain and output is not cancelled, process one frame.
10. On the first frame, log time-to-first-audio and set `first=False`.
11. `pacer.begin_frame(640)` updates the intended frame deadline.
12. `pending[:640]` slices the first frame for enqueueing. `pending[640:]` retains
    the remainder for later frames. At 16 kHz and two bytes/sample, 640 bytes = 20 ms.
13. The current `cancel.wait(pacer.remaining())` line is commented out. Updating
    the deadline alone does not make the server sleep. Actual server pacing is
    therefore not enforced by that line in the inspected code.
14. Reset provider-read timing before obtaining the next chunk.
15. At stream end, send any remaining whole samples if not cancelled.
    `len(pending)//2*2` rounds down to an even byte count; `//` is integer floor division.
16. In `finally`, close the stream and log audio duration, elapsed time, maximum
    provider wait and cancellation status. `pcm_bytes/32` converts byte count to
    milliseconds: 16,000 samples/s × 2 bytes = 32 bytes/ms.

`PcmPacer` in `pacing.py` maintains a monotonic deadline, advances it by each
frame's duration, and can report remaining wait. It is not a speech synthesizer.
Its intended wait is currently disabled in this browser loop, as noted above.

The thread-to-asyncio bridge is `enqueue(item)`:

```python
if stopped.is_set(): return
future=asyncio.run_coroutine_threadsafe(output.put(item),loop)
try: future.result(timeout=2)
except Exception:
    future.cancel()
    loop.call_soon_threadsafe(stopped.set)
```

`output` is an `asyncio.Queue(maxsize=100)`. `output.put(item)` is a coroutine and
may wait for room. `run_coroutine_threadsafe` schedules it on the correct event
loop from the speech thread, returning a concurrent Future. `.result(timeout=2)`
blocks this speech thread waiting for enqueue completion, not the event-loop
thread. Queue failure/timeout cancels that scheduled future and requests shutdown.
This is backpressure; the queue cannot grow forever without the consumer keeping up.

The consumer `send()` is short:

```python
async def send():
    while not stopped.is_set():
        item=await output.get()
        if isinstance(item,bytes): await ws.send_bytes(item)
        else: await ws.send_json(item)
```

Wait cooperatively for the next item. Bytes take the binary WebSocket path.
Dictionaries take the JSON path. One queue preserves the order in which these
events and audio frames are queued. There is no separate HTTP request per frame.

## 20. The reply is played: this part is TypeScript, not Python

Open `frontend/lib/voice-session.ts`, function `receive(event)`.
The function exits when stopped or when no AudioContext exists. `typeof
event.data === 'string'` distinguishes textual WebSocket messages from binary
ArrayBuffers. `JSON.parse` decodes a textual protocol event.

The switch handles clear, ready, reply, transcript and error. `break` exits the
switch; the following `return` exits receive for that JSON message. A `reply`
updates text immediately, before all its audio has arrived. A `clear` stops
scheduled sources and resets timing. `ready` displays the opening greeting.

For binary data, these lines perform playback:

```typescript
const pcm = new Int16Array(event.data);
const buffer = context.createBuffer(1, pcm.length, 16000);
const channel = buffer.getChannelData(0);
for (let i = 0; i < pcm.length; i++) channel[i] = pcm[i] / 32768;
const source = context.createBufferSource();
source.buffer = buffer;
source.connect(context.destination);
if (next <= context.currentTime) next = context.currentTime + 0.08;
source.start(next);
next += buffer.duration;
sources.add(source);
source.onended = () => sources.delete(source);
```

1. `const` declares a binding that will not be reassigned. The typed array views
   the received bytes as signed 16-bit sample values.
2. `createBuffer(1, length, 16000)` allocates one-channel audio with that many
   frames and a 16 kHz sample rate.
3. `getChannelData(0)` accesses its first/only channel as floating-point samples.
4. The for loop starts `i` at zero, tests it against sample count, increments it
   with `i++`, and converts each sample to approximately -1 to 1 by dividing by 32768.
5. Create an AudioBufferSourceNode, attach the buffer, and connect to the audio
   context's speaker destination.
6. If previously scheduled audio has run out, start 0.08 seconds ahead to allow
   a small jitter reserve. Otherwise keep the established contiguous schedule.
7. `source.start(next)` schedules playback, rather than necessarily playing now.
8. Add this buffer's duration to the next start time.
9. Track the source in a Set so interruption can stop it later.
10. The arrow-function callback removes it from that Set when playback ends.

The intervening diagnostics count frames, packet gaps and underruns. These are
timing observations, not audio recordings. `onended` currently does not send a
hardware-playback acknowledgement back to Python.

## 21. Interruption and delivery bookkeeping

A new Deepgram StartOfTurn activates two paths:

```text
session.event → set current/queued turn cancellation flags
browser.event → schedule clear_audio on the asyncio loop
```

`clear_audio()` removes queued outgoing items with `get_nowait()` until empty.
It catches `asyncio.QueueEmpty` if there is nothing left, then puts a `clear`
JSON event. In the browser, `clearPlayback()` calls `.stop()` on scheduled source
nodes, clears the Set and resets `next=0`.

This can stop audio already scheduled locally as well as stop further server
output. It cannot undo samples already heard, retract a sent packet, or roll
back a completed calendar mutation. Blocking provider reads may not notice a
cancel flag until they return.

`Receptionist.delivered(bid, cid, interrupted)`:

1. Open a transaction.
2. Select the latest assistant TranscriptTurn for this business/call in descending
   timestamp order. `desc()` requests newest first.
3. If it exists, set delivery to interrupted or played using a conditional expression.
4. Load the scoped call and validate its state.
5. Only when pending exists and `pending.confirmation_turn_id == turn.id`, update
   readiness to `not interrupted` and persist the state dictionary.

The greeting and acknowledgement skip this callback. A later ordinary reply
cannot mark a different interrupted consent readback ready. The current method
still bases playback status on server completion/cancellation; it does not know
whether the user's actual speaker finished playing the last packet.

## 22. End the connection and finalize the call

In `browser.py`, the three tasks are created with:

```python
tasks=[asyncio.create_task(receive()),asyncio.create_task(send()),
       asyncio.create_task(stopped.wait())]
done,_=await asyncio.wait(tasks,timeout=1800,return_when=asyncio.FIRST_COMPLETED)
```

`create_task` schedules a coroutine to run on the event loop. One task receives
microphone input, one sends output, and one waits for shutdown. `asyncio.wait`
returns when one finishes or the 1,800-second limit is reached. `done` is the set
of completed tasks; `_` ignores the remaining-task set. `task.exception()` returns
a task's exception, which the code raises when present.

The task-scope `finally` sets stopped, calls `cancel()` on every task and awaits
`gather(..., return_exceptions=True)` so their cancellation/completion is collected.
`*tasks` expands the list into positional arguments. Task cancellation is
cooperative and does not forcibly terminate a blocking SDK call running in a thread.
The code then calls the Deepgram context's `__exit__(None,None,None)` in a thread.
Those three arguments are the exception type/value/traceback slots used by the
context-manager protocol; here it explicitly supplies no exception information.

An outer `except WebSocketDisconnect: pass` treats normal browser disconnection
as a normal end. Other exceptions set a failure class name, log the exception and
attempt to send an error event. The final cleanup always requests stopped,
closes the VoiceSession, attempts `agent.end`, and closes the WebSocket.

`VoiceSession.close()` sets its closed flag under the lock and cancels the current
turn if present. If the worker has actually started, it joins it with a 35-second
limit. A join timeout does not kill a Python thread; it only stops waiting for it.

`Receptionist.end(bid, cid, failure='')`:

1. Acquire the per-call lock and start a database transaction.
2. Load the scoped call; reject missing calls and return for an already-ended call.
3. Store end time and compute nonnegative integer duration from start/end datetimes.
4. Set failed/completed status and a bounded failure reason.
5. Validate stored state and produce a deterministic outcome/caller/follow-up summary.
6. Mark its summary status deterministic and commit this baseline first.
7. Log `CALL_ENDED`.
8. `hasattr(self.llm, 'summarize')` tests for an optional summary method.
9. If available, load turns and call it outside that initial write transaction.
10. If nonempty summary text returns, append bounded, labelled AI notes in another
    transaction and set summary status AI. Failures log a warning and preserve
    the already-committed baseline summary.

`GeminiConversationPlanner.summarize()` sends at most the last 60 transcript
entries with a summary-specific instruction and a bounded output token setting.
It disables automatic tool calling and redacts its returned text. The summary
does not determine calendar truth or retroactively create appointments.

Browser-side `stop()` is guarded with `if (stopped) return`, so repeated cleanup
does not redo everything. It marks stopped, logs diagnostics, clears playback,
closes the socket, stops every microphone track, closes AudioContext and updates
the UI. Optional chaining (`socket?.close()`) calls a method only when the object
exists. `void context?.close()` intentionally does not await that promise there.

## Practice without changing production behavior

Read one procedure and answer these in your own words before moving on:

1. Why does `to_thread(connection.send_media, packet)` omit parentheses after
   `send_media`, and which thread is free to continue while the send runs?
2. What does `yield conn` return to the caller, and when does the function resume?
3. Which object receives the first transcript text? Which function makes the first
   Gemini request? These are different points in the flow.
4. Why must each Turn get its own cancellation Event?
5. What is the difference between a transcript, AppointmentState and an Appointment row?
6. Why does a changed date invalidate pending consent even if the decision says confirm?
7. Why record Operation before calling Google? What should happen after a timeout
   when Google may already have created the event?
8. Why can a successful booking use a protected response without a generator call?
9. Why does completing a filler phrase not mark a confirmation ready?
10. What does `source.start(next)` schedule, and why is server delivery not proof
    that the user heard the audio?

For a safe starting trace, use the unit tests rather than a real booking:

```powershell
.\venv\Scripts\python.exe -m pytest -q tests/test_voice.py tests/test_voice_wait.py tests/test_browser_greeting.py
```

These use controlled callbacks/fakes. They let you follow function calls and
interruption behavior without sending microphone audio or creating calendar events.
