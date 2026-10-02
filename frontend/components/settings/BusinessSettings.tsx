"use client";

import type { BusinessSettings as Settings } from "@/lib/types";

interface Props {
  data: Settings;
  onChange: (changes: Partial<Settings>) => void;
}
const businessFields = [
  ["name", "Business name"],
  ["timezone", "IANA timezone"],
  ["phone", "Business phone"],
  ["location", "Location"],
] as const;
const receptionistFields = [
  ["assistant_name", "Assistant name"],
  ["greeting", "Greeting"],
  ["escalation_number", "Staff follow-up number"],
  ["voice_id", "ElevenLabs voice ID"],
  ["after_hours_message", "Follow-up message"],
] as const;

export default function BusinessSettings({ data, onChange }: Props) {
  return (
    <>
      <section className="panel form-panel">
        <h2>Business details</h2>
        <p>The information your receptionist uses.</p>
        {businessFields.map(([key, label]) => (
          <label key={key}>
            {label}
            <input
              required={key === "name" || key === "timezone"}
              value={data[key]}
              onChange={(event) => onChange({ [key]: event.target.value })}
            />
          </label>
        ))}
      </section>
      <section className="panel form-panel">
        <h2>Your receptionist</h2>
        {receptionistFields.map(([key, label]) => (
          <label key={key}>
            {label}
            <input
              value={data[key]}
              onChange={(event) => onChange({ [key]: event.target.value })}
            />
          </label>
        ))}
        <small>Live transfer requires a connected phone adapter.</small>
      </section>
    </>
  );
}
