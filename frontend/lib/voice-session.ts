"use client";

import { errorMessage } from "./api";
import type { ChatMessage, VoiceEvent } from "./types";

interface VoiceCallbacks {
  onMessage: (role: ChatMessage["role"], text: string) => void;
  onError: (message: string) => void;
  onActive: (active: boolean) => void;
  onDiagnostics?: (stats: VoiceDiagnostics) => void;
}

export interface VoiceDiagnostics {
  receivedFrames: number;
  playbackUnderruns: number;
  maxPacketGapMs: number;
  clearEvents: number;
}

// Transport/audio code extracted from the original browser demo. The worklet,
// capture constraints, PCM format and clear protocol are unchanged.
export function createVoiceSession(callbacks: VoiceCallbacks) {
  let context: AudioContext | undefined;
  let stream: MediaStream | undefined;
  let socket: WebSocket | undefined;
  let stopped = false;
  let next = 0;
  const sources = new Set<AudioBufferSourceNode>();
  const diagnostics: VoiceDiagnostics = {
    receivedFrames: 0,
    playbackUnderruns: 0,
    maxPacketGapMs: 0,
    clearEvents: 0,
  };
  let lastPacketTime: number | null = null;
  let replyHasAudio = false;

  function clearPlayback() {
    sources.forEach((source) => {
      try {
        source.stop();
      } catch {
        /* Already finished. */
      }
    });
    sources.clear();
    next = 0;
  }

  function stop() {
    if (stopped) return;
    stopped = true;
    // Timing/counts only: never log PCM, transcripts or authentication data.
    console.info("AVA_AUDIO_STATS", { ...diagnostics });
    callbacks.onDiagnostics?.({ ...diagnostics });
    clearPlayback();
    socket?.close();
    stream?.getTracks().forEach((track) => track.stop());
    void context?.close();
    callbacks.onActive(false);
  }

  function receive(event: MessageEvent<string | ArrayBuffer>) {
    if (stopped || !context) return;
    if (typeof event.data === "string") {
      const data: VoiceEvent = JSON.parse(event.data);
      switch (data.type) {
        case "clear":
          diagnostics.clearEvents++;
          lastPacketTime = null;
          replyHasAudio = false;
          clearPlayback();
          break;
        case "ready":
          callbacks.onMessage("assistant", data.greeting);
          break;
        case "reply":
          lastPacketTime = null;
          replyHasAudio = false;
          callbacks.onMessage("assistant", data.text);
          break;
        case "transcript":
          callbacks.onMessage("user", data.text);
          break;
        case "error":
          callbacks.onError(data.text);
          break;
      }
      return;
    }
    const pcm = new Int16Array(event.data);
    diagnostics.receivedFrames++;
    if (lastPacketTime !== null) {
      diagnostics.maxPacketGapMs = Math.max(
        diagnostics.maxPacketGapMs,
        Math.round((context.currentTime - lastPacketTime) * 1000),
      );
    }
    lastPacketTime = context.currentTime;
    if (replyHasAudio && next <= context.currentTime) {
      diagnostics.playbackUnderruns++;
    }
    replyHasAudio = true;
    const buffer = context.createBuffer(1, pcm.length, 16000);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) channel[i] = pcm[i] / 32768;
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);
    // Reserve 80 ms on startup/underrun for network jitter. While audio remains
    // queued, preserve contiguous sample timing rather than adding a new gap.
    if (next <= context.currentTime) next = context.currentTime + 0.08;
    source.start(next);
    next += buffer.duration;
    sources.add(source);
    source.onended = () => sources.delete(source);
  }

  async function start() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      // Route navigation can happen while the browser permission prompt is open.
      if (stopped) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      context = new AudioContext();
      await context.audioWorklet.addModule("/audio-worklet.js");
      if (stopped) return;
      socket = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/voice`,
      );
      socket.binaryType = "arraybuffer";
      const worklet = new AudioWorkletNode(context, "ava-capture");
      context.createMediaStreamSource(stream).connect(worklet);
      worklet.connect(context.destination);
      worklet.port.onmessage = (event) => {
        if (socket?.readyState === WebSocket.OPEN) {
          if (socket.bufferedAmount > 32000) {
            callbacks.onError("Connection is too slow for voice.");
            stop();
          } else {
            socket.send(event.data);
          }
        }
      };
      socket.onmessage = receive;
      socket.onclose = stop;
      socket.onerror = () =>
        callbacks.onError(
          "Voice connection failed. Check provider configuration.",
        );
      callbacks.onActive(true);
    } catch (error) {
      stop();
      callbacks.onError(errorMessage(error));
    }
  }

  return { start, stop };
}
