"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, errorMessage } from "@/lib/api";
import { createVoiceSession } from "@/lib/voice-session";
import type { ChatMessage } from "@/lib/types";
import EmptyState from "../dashboard/EmptyState";
import Notice from "../dashboard/Notice";

export default function VoiceDemo() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [text, setText] = useState("");
  const [call, setCall] = useState("");
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const [voice, setVoice] = useState(false);
  const session = useRef<ReturnType<typeof createVoiceSession> | null>(null);

  useEffect(
    () => () => {
      session.current?.stop();
    },
    [],
  );

  function append(role: ChatMessage["role"], text: string) {
    setMessages((current) => [...current, { role, text }]);
  }
  async function toggleVoice() {
    if (voice) {
      session.current?.stop();
      return;
    }
    setError("");
    setWorking(true);
    session.current = createVoiceSession({
      onMessage: append,
      onError: setError,
      onActive: setVoice,
    });
    try {
      await session.current.start();
    } finally {
      setWorking(false);
    }
  }
  async function endTextCall() {
    setWorking(true);
    setError("");
    try {
      await api(`/demo/calls/${encodeURIComponent(call)}/end`, "POST");
      setCall("");
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setWorking(false);
    }
  }
  async function sendText(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!text.trim()) return;
    setWorking(true);
    setError("");
    const input = text;
    setText("");
    append("user", input);
    try {
      let id = call;
      if (!id) {
        id = (await api<{ id: string }>("/demo/calls", "POST")).id;
        setCall(id);
      }
      const result = await api<{ reply: string }>(
        `/demo/calls/${encodeURIComponent(id)}/turn`,
        "POST",
        { text: input, key: crypto.randomUUID() },
      );
      append("assistant", result.reply);
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setWorking(false);
    }
  }

  return (
    <>
      <div className="demo-note">
        This staff demo uses the real clinic settings and calendar. Confirmed
        bookings create real appointments.
      </div>
      {error && <Notice text={error} />}
      <section className="panel demo">
        <div className="panel-title">
          <h2>
            <span className={voice ? "live-dot" : ""} /> Ava receptionist
          </h2>
          <div className="actions">
            <button disabled={working || Boolean(call)} onClick={toggleVoice}>
              {voice ? "Stop voice" : "Start voice"}
            </button>
            {call && (
              <button disabled={working} onClick={endTextCall}>
                End text call
              </button>
            )}
          </div>
        </div>
        <div className="chat" aria-live="polite">
          {!messages.length && (
            <EmptyState
              title="Hello. How can I help?"
              text="Speak with Ava or try a typed conversation below."
            />
          )}
          {messages.map((message, index) => (
            <div className={`turn ${message.role}`} key={index}>
              <strong>{message.role === "user" ? "You" : "Ava"}</strong>
              <p>{message.text}</p>
            </div>
          ))}
        </div>
        <form className="compose" onSubmit={sendText}>
          <input
            aria-label="Message Ava"
            placeholder={
              voice
                ? "Voice conversation in progress…"
                : "Ask Ava about an appointment…"
            }
            disabled={voice || working}
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <button
            disabled={voice || working || !text.trim()}
            className="primary"
          >
            {working ? "Working…" : "Send ↑"}
          </button>
        </form>
      </section>
      <small>
        Use headphones for the clearest interruption test. The transcript marks
        interrupted replies in Calls.
      </small>
    </>
  );
}
