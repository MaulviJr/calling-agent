"use client";

import { useState } from "react";
import type { Appointment } from "@/lib/types";
import { useRecords } from "@/lib/useRecords";
import { formatDate } from "@/lib/formatting";
import EmptyState from "../dashboard/EmptyState";
import Notice from "../dashboard/Notice";
import Pagination from "../dashboard/Pagination";
import StatusBadge from "../dashboard/StatusBadge";
import RescheduleDialog from "./RescheduleDialog";

export default function AppointmentsTable() {
  const { rows, loading, error, refresh, offset, setOffset } =
    useRecords<Appointment>("/appointments");
  const [selection, setSelection] = useState<{
    appointment: Appointment;
    action: "reschedule" | "cancel";
  } | null>(null);

  function finishChange() {
    setSelection(null);
    refresh();
  }

  return (
    <>
      {error && <Notice text={error} />}
      <section className="panel">
        <div className="panel-title">
          <h2>Appointment register</h2>
          <button onClick={refresh}>Refresh ↻</button>
        </div>
        {loading ? (
          <p className="padding">Loading…</p>
        ) : !rows.length ? (
          <EmptyState
            title="No appointments yet"
            text="New activity will appear here automatically when you refresh."
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Caller / service</th>
                  <th>Appointment time</th>
                  <th>Status</th>
                  <th>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((appointment) => (
                  <tr key={appointment.id}>
                    <td>
                      {appointment.caller_name}
                      <small>
                        {appointment.service_id} · {appointment.caller_phone}
                      </small>
                    </td>
                    <td>
                      {formatDate(appointment.start_at, appointment.timezone)}
                      <small>Clinic timezone: {appointment.timezone}</small>
                    </td>
                    <td>
                      <StatusBadge status={appointment.status} />
                    </td>
                    <td>
                      {appointment.status === "booked" && (
                        <div className="actions">
                          <button
                            onClick={() =>
                              setSelection({
                                appointment,
                                action: "reschedule",
                              })
                            }
                          >
                            Move
                          </button>
                          <button
                            onClick={() =>
                              setSelection({ appointment, action: "cancel" })
                            }
                          >
                            Cancel
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pagination offset={offset} count={rows.length} onChange={setOffset} />
      </section>
      {selection && (
        <RescheduleDialog
          appointment={selection.appointment}
          action={selection.action}
          onClose={() => setSelection(null)}
          onSaved={finishChange}
        />
      )}
    </>
  );
}
