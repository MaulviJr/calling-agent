"use client";

import type { BusinessSettings, CalendarStatus } from "@/lib/types";
const fields = [
  ["buffer_minutes", "Buffer between visits (minutes)"],
  ["minimum_notice_minutes", "Minimum notice (minutes)"],
  ["maximum_advance_days", "Advance booking window (days)"],
] as const;

export default function SchedulingSettings({
  data,
  calendar,
  onChange,
}: {
  data: BusinessSettings;
  calendar: CalendarStatus | null;
  onChange: (changes: Partial<BusinessSettings>) => void;
}) {
  return (
    <section className="panel form-panel">
      <h2>Scheduling</h2>
      <p className="calendar-state">
        {calendar?.connected
          ? "● Calendar connected"
          : "○ Calendar not connected"}
        <small>Credentials are configured on the server.</small>
      </p>
      {fields.map(([key, label]) => (
        <label key={key}>
          {label}
          <input
            type="number"
            min="0"
            value={data[key]}
            onChange={(event) =>
              onChange({ [key]: Number(event.target.value) })
            }
          />
        </label>
      ))}
      <label className="checkbox">
        <input
          type="checkbox"
          checked={data.require_email}
          onChange={(event) =>
            onChange({ require_email: event.target.checked })
          }
        />
        Require caller email
      </label>
      <label>
        Cancellation policy
        <textarea
          value={data.cancellation_policy}
          onChange={(event) =>
            onChange({ cancellation_policy: event.target.value })
          }
        />
      </label>
    </section>
  );
}
