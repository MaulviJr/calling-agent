"use client";

import { useState, type FormEvent } from "react";
import { api, errorMessage } from "@/lib/api";
import type { Appointment } from "@/lib/types";
import Dialog from "../dashboard/Dialog";
import Notice from "../dashboard/Notice";

export default function RescheduleDialog({
  appointment,
  action,
  onClose,
  onSaved,
}: {
  appointment: Appointment;
  action: "reschedule" | "cancel";
  onClose: () => void;
  onSaved: () => void;
}) {
  const [start, setStart] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // Keep the request key on retries; a changed requested time is a new operation.
  const [requestKey, setRequestKey] = useState(() => crypto.randomUUID());
  const rescheduling = action === "reschedule";

  function changeStart(value: string) {
    setStart(value);
    setRequestKey(crypto.randomUUID());
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(
        `/appointments/${encodeURIComponent(appointment.id)}/${action}`,
        "POST",
        {
          confirmed: true,
          key: requestKey,
          ...(rescheduling ? { start_at: start } : {}),
        },
      );
      onSaved();
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      title={rescheduling ? "Reschedule appointment" : "Cancel appointment"}
      busy={busy}
      onClose={onClose}
    >
      <form onSubmit={submit} className="flex flex-col gap-4">
        <p>
          {appointment.caller_name} · {appointment.service_id}
        </p>
        {rescheduling ? (
          <label>
            New date and time with timezone offset
            <input
              required
              autoFocus
              value={start}
              disabled={busy}
              onChange={(event) => changeStart(event.target.value)}
              placeholder="2026-10-12T15:00:00+05:00"
              aria-describedby="appointment-time-help"
            />
            <small id="appointment-time-help">
              Clinic timezone: {appointment.timezone}. Include the offset, as in
              the example. Availability is checked before the change is saved.
            </small>
          </label>
        ) : (
          <p>
            Confirm cancellation of this appointment and its calendar event.
          </p>
        )}
        {error && <Notice text={error} />}
        <div className="flex justify-end gap-3">
          <button type="button" disabled={busy} onClick={onClose}>
            Keep appointment
          </button>
          <button className="primary" disabled={busy}>
            {busy
              ? "Saving…"
              : rescheduling
                ? "Confirm reschedule"
                : "Confirm cancellation"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
