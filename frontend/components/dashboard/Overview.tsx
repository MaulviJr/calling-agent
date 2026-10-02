"use client";

import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import type { Call, CalendarOperation, DashboardOverview } from "@/lib/types";
import { formatDate } from "@/lib/formatting";
import MetricCard from "./MetricCard";
import EmptyState from "./EmptyState";
import Notice from "./Notice";
import StatusBadge from "./StatusBadge";

export default function Overview() {
  const [data, setData] = useState<DashboardOverview | null>(null);
  const [calls, setCalls] = useState<Call[]>([]);
  const [operations, setOperations] = useState<CalendarOperation[]>([]);
  const [error, setError] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      const [overview, recent, unresolved] = await Promise.all([
        api<DashboardOverview>("/overview"),
        api<Call[]>("/calls?limit=6"),
        api<CalendarOperation[]>("/operations"),
      ]);
      setData(overview);
      setCalls(recent);
      setOperations(unresolved);
    } catch (error) {
      setError(errorMessage(error));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  async function reconcile(id: string) {
    setPending(id);
    setError("");
    try {
      await api(`/operations/${encodeURIComponent(id)}/reconcile`, "POST");
      await load();
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setPending(null);
    }
  }

  if (!data) return error ? <Notice text={error} /> : <p>Loading activity…</p>;
  return (
    <>
      {error && <Notice text={error} />}
      <div className="hero-strip">
        <div>
          <span className="dot" />
          <strong>Room for the human side of care.</strong>
          <p>Review conversations and give your team a clear next step.</p>
        </div>
        <span className="hero-art">◌</span>
      </div>
      <div className="metrics">
        <MetricCard
          title="Total calls"
          value={data.total_calls}
          description="All conversations"
        />
        <MetricCard
          title="Appointments booked"
          value={data.appointments_booked}
          description="Recorded bookings"
        />
        <MetricCard
          title="Booking conversion"
          value={`${data.conversion_rate}%`}
          description="Calls with a booking"
        />
        <MetricCard
          title="Open messages"
          value={data.unresolved_messages}
          description="Awaiting follow-up"
        />
      </div>
      <div className="overview-grid">
        <section className="panel">
          <div className="panel-title">
            <h2>Recent conversations</h2>
            <span>Latest activity</span>
          </div>
          {calls.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Caller</th>
                    <th>Started</th>
                    <th>Outcome</th>
                  </tr>
                </thead>
                <tbody>
                  {calls.map((call) => (
                    <tr key={call.id}>
                      <td>{call.caller_phone || "Number not provided"}</td>
                      <td>{formatDate(call.started_at)}</td>
                      <td>
                        <StatusBadge status={call.outcome} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="Your next conversation starts here"
              text="Calls will appear as people speak with Ava."
            />
          )}
        </section>
        <section className="panel snapshot">
          <h2>At a glance</h2>
          <div>
            <span>Calls today</span>
            <strong>{data.calls_today}</strong>
          </div>
          <div>
            <span>Average call</span>
            <strong>{data.average_duration}s</strong>
          </div>
          <div>
            <span>Escalations</span>
            <strong>{data.escalations}</strong>
          </div>
          <p>Metrics come from stored call and appointment records.</p>
        </section>
      </div>
      {operations.length > 0 && (
        <section className="panel">
          <h2>Calendar changes need review</h2>
          <p>
            A request could not be verified. Reconcile it to check Google and
            finish the saved operation.
          </p>
          {operations.map((operation) => (
            <div className="operation" key={operation.id}>
              <span>
                {operation.kind} · {operation.status} ·{" "}
                {formatDate(operation.created_at)}
              </span>
              <button
                disabled={pending !== null}
                onClick={() => reconcile(operation.id)}
              >
                {pending === operation.id ? "Checking…" : "Reconcile"}
              </button>
            </div>
          ))}
        </section>
      )}
    </>
  );
}
