"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api, errorMessage } from "@/lib/api";
import type { BusinessSettings as Settings, CalendarStatus } from "@/lib/types";
import Notice from "../dashboard/Notice";
import BusinessSettings from "./BusinessSettings";
import SchedulingSettings from "./SchedulingSettings";
import BusinessHours from "./BusinessHours";
import ServicesSettings from "./ServicesSettings";
import KnowledgeSettings from "./KnowledgeSettings";

export default function SettingsForm() {
  const [data, setData] = useState<Settings | null>(null);
  const [calendar, setCalendar] = useState<CalendarStatus | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [working, setWorking] = useState(false);
  useEffect(() => {
    let active = true;
    api<Settings>("/settings")
      .then((data) => {
        if (active) setData(data);
      })
      .catch((error) => {
        if (active) setError(errorMessage(error));
      });
    api<CalendarStatus>("/calendar/status")
      .then((data) => {
        if (active) setCalendar(data);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  function update(changes: Partial<Settings>) {
    setData((current) => (current ? { ...current, ...changes } : current));
    setSaved(false);
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!data) return;
    setWorking(true);
    setError("");
    try {
      setData(await api<Settings>("/settings", "PUT", data));
      setSaved(true);
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setWorking(false);
    }
  }
  if (!data) return error ? <Notice text={error} /> : <p>Loading settings…</p>;
  return (
    <form onSubmit={save}>
      {error && <Notice text={error} />}
      <fieldset disabled={working} className="settings-fields">
        <div className="settings-grid">
          <BusinessSettings data={data} onChange={update} />
          <SchedulingSettings
            data={data}
            calendar={calendar}
            onChange={update}
          />
          <BusinessHours
            hours={data.hours}
            onChange={(hours) => update({ hours })}
          />
        </div>
        <ServicesSettings
          services={data.services}
          onChange={(services) => update({ services })}
        />
        <KnowledgeSettings
          staff={data.staff ?? []}
          onStaffChange={(staff) => update({ staff })}
          entries={data.knowledge}
          onChange={(knowledge) => update({ knowledge })}
        />
      </fieldset>
      <div className="save-bar">
        <span aria-live="polite">
          {saved
            ? "✓ Settings saved"
            : "Changes apply to the next conversation turn."}
        </span>
        <button className="primary" disabled={working}>
          {working ? "Saving…" : "Save settings"}
        </button>
      </div>
    </form>
  );
}
