"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api, errorMessage } from "@/lib/api";
import type { User } from "@/lib/types";
import Notice from "./dashboard/Notice";

export default function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api<User>("/login", "POST", { email, password });
      setPassword("");
      router.replace("/dashboard");
      router.refresh();
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={signIn}>
      <span className="eyebrow">AVA WORKSPACE</span>
      <h2>Welcome back</h2>
      <p>Sign in to your clinic workspace.</p>
      <label>
        Email address
        <input
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </label>
      <label>
        Password
        <input
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </label>
      {error && <Notice text={error} />}
      <button disabled={busy} className="primary">
        {busy ? "Signing in…" : "Sign in →"}
      </button>
      <small>Access is limited to authorized clinic staff.</small>
    </form>
  );
}
