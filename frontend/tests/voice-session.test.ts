import test from "node:test";
import assert from "node:assert/strict";
import { createVoiceSession } from "../lib/voice-session";

// These doubles exercise the extracted transport without recording a microphone
// or contacting STT/TTS providers. Hardware acceptance remains a manual check.
function environment() {
  const originals = new Map<string, PropertyDescriptor | undefined>();
  function install(name: string, value: unknown) {
    originals.set(name, Object.getOwnPropertyDescriptor(globalThis, name));
    Object.defineProperty(globalThis, name, { configurable: true, value });
  }
  let tracksStopped = 0;
  let constraints: unknown;
  const stream = { getTracks: () => [{ stop: () => tracksStopped++ }] };
  class Source {
    buffer: { duration: number } | null = null;
    stopped = false;
    started = -1;
    onended?: () => void;
    connect() {}
    start(time: number) { this.started = time; }
    stop() { this.stopped = true; }
  }
  class Context {
    static instance: Context;
    currentTime = 1;
    destination = {};
    closed = 0;
    module = "";
    samples: Float32Array[] = [];
    sources: Source[] = [];
    audioWorklet = { addModule: async (path: string) => { this.module = path; } };
    constructor() { Context.instance = this; }
    createMediaStreamSource() { return { connect() {} }; }
    createBuffer(channels: number, length: number, rate: number) {
      assert.equal(channels, 1);
      assert.equal(rate, 16000);
      const samples = new Float32Array(length);
      this.samples.push(samples);
      return { duration: length / rate, getChannelData: () => samples };
    }
    createBufferSource() { const source = new Source(); this.sources.push(source); return source; }
    async close() { this.closed++; }
  }
  class Socket {
    static OPEN = 1;
    static instance: Socket;
    readyState = 1;
    bufferedAmount = 0;
    binaryType = "";
    closed = 0;
    sent: unknown[] = [];
    onmessage?: (event: { data: string | ArrayBuffer }) => void;
    onclose?: () => void;
    onerror?: () => void;
    constructor(public url: string) { Socket.instance = this; }
    send(value: unknown) { this.sent.push(value); }
    close() { this.closed++; this.readyState = 3; }
    receive(data: string | ArrayBuffer) { this.onmessage?.({ data }); }
  }
  class Worklet {
    static instance: Worklet;
    port: { onmessage?: (event: { data: ArrayBuffer }) => void } = {};
    constructor(_context: unknown, public name: string) { Worklet.instance = this; }
    connect() {}
  }
  const mediaDevices = { getUserMedia: async (value: unknown) => { constraints = value; return stream; } };
  install("navigator", { mediaDevices });
  install("location", { protocol: "https:", host: "ava.test" });
  install("AudioContext", Context);
  install("WebSocket", Socket);
  install("AudioWorkletNode", Worklet);
  const messages: { role: string; text: string }[] = [];
  const errors: string[] = [];
  const active: boolean[] = [];
  const session = createVoiceSession({ onMessage: (role, text) => messages.push({ role, text }), onError: message => errors.push(message), onActive: value => active.push(value) });
  return {
    session, mediaDevices, stream, messages, errors, active,
    context: () => Context.instance, socket: () => Socket.instance, worklet: () => Worklet.instance,
    constraints: () => constraints, tracksStopped: () => tracksStopped,
    restore() {
      session.stop();
      for (const [name, descriptor] of originals) {
        if (descriptor) Object.defineProperty(globalThis, name, descriptor);
        else Reflect.deleteProperty(globalThis, name);
      }
    },
  };
}

test("capture constraints, worklet and PCM upload remain unchanged", async () => {
  const env = environment();
  try {
    await env.session.start();
    assert.deepEqual(env.constraints(), { audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    assert.equal(env.context().module, "/audio-worklet.js");
    assert.equal(env.worklet().name, "ava-capture");
    assert.equal(env.socket().url, "wss://ava.test/api/voice");
    assert.equal(env.socket().binaryType, "arraybuffer");
    const frame = new Int16Array([1, -2]).buffer;
    env.worklet().port.onmessage?.({ data: frame });
    assert.equal(env.socket().sent[0], frame);
    assert.deepEqual(env.active, [true]);
  } finally { env.restore(); }
});

test("binary PCM playback is scheduled sequentially and clear interrupts all queued audio", async () => {
  const env = environment();
  try {
    await env.session.start();
    env.socket().receive(new Int16Array([-32768, 0, 16384]).buffer);
    env.socket().receive(new Int16Array(1600).buffer);
    assert.deepEqual([...env.context().samples[0]], [-1, 0, .5]);
    assert.equal(env.context().sources[0].started, 1.08);
    assert.equal(env.context().sources[1].started, 1.08 + 3 / 16000);
    env.socket().receive(JSON.stringify({ type: "clear" }));
    assert.ok(env.context().sources.every(source => source.stopped));
    env.context().currentTime = 2;
    env.socket().receive(new Int16Array([10]).buffer);
    assert.equal(env.context().sources[2].started, 2.08);
  } finally { env.restore(); }
});

test("packets arriving near playback remain contiguous instead of inserting silence", async () => {
  const env = environment();
  try {
    await env.session.start();
    env.socket().receive(new Int16Array(320).buffer);
    env.context().currentTime = 1.09;
    env.socket().receive(new Int16Array(320).buffer);
    assert.equal(env.context().sources[1].started, 1.1);
    env.context().currentTime = 2;
    env.socket().receive(new Int16Array(320).buffer);
    assert.equal(env.context().sources[2].started, 2.08);
  } finally { env.restore(); }
});

test("ready, transcript, reply and error events retain their meaning", async () => {
  const env = environment();
  try {
    await env.session.start();
    for (const event of [{ type: "ready", greeting: "Hello" }, { type: "transcript", text: "Hi" }, { type: "reply", text: "Welcome" }, { type: "error", text: "Unavailable" }]) env.socket().receive(JSON.stringify(event));
    assert.deepEqual(env.messages, [{ role: "assistant", text: "Hello" }, { role: "user", text: "Hi" }, { role: "assistant", text: "Welcome" }]);
    assert.deepEqual(env.errors, ["Unavailable"]);
  } finally { env.restore(); }
});

test("backpressure and disconnect release microphone, audio and socket", async () => {
  const env = environment();
  try {
    await env.session.start();
    env.socket().bufferedAmount = 32001;
    env.worklet().port.onmessage?.({ data: new ArrayBuffer(2) });
    assert.deepEqual(env.errors, ["Connection is too slow for voice."]);
    assert.equal(env.tracksStopped(), 1);
    assert.equal(env.context().closed, 1);
    env.socket().onclose?.();
    env.session.stop();
    assert.equal(env.context().closed, 1);
    assert.equal(env.socket().closed, 1);
    assert.deepEqual(env.active, [true, false]);
  } finally { env.restore(); }
});

test("route cleanup during permission request releases the late microphone stream", async () => {
  const env = environment();
  try {
    let allow!: (stream: typeof env.stream) => void;
    env.mediaDevices.getUserMedia = () => new Promise(resolve => { allow = resolve; });
    const starting = env.session.start();
    env.session.stop();
    allow(env.stream);
    await starting;
    assert.equal(env.tracksStopped(), 1);
    assert.equal(env.socket(), undefined);
  } finally { env.restore(); }
});

test("permission denial reports a useful error without starting transport", async () => {
  const env = environment();
  try {
    env.mediaDevices.getUserMedia = async () => { throw new Error("Microphone permission denied"); };
    await env.session.start();
    assert.deepEqual(env.errors, ["Microphone permission denied"]);
    assert.equal(env.socket(), undefined);
  } finally { env.restore(); }
});
