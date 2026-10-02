"use client";

import Link from "next/link";
import type { Call } from "@/lib/types";
import { useRecords } from "@/lib/useRecords";
import { formatDate } from "@/lib/formatting";
import EmptyState from "../dashboard/EmptyState";
import Notice from "../dashboard/Notice";
import Pagination from "../dashboard/Pagination";
import StatusBadge from "../dashboard/StatusBadge";

export default function CallsTable() {
  const { rows, loading, error, refresh, offset, setOffset } =
    useRecords<Call>("/calls");
  return (
    <>
      {error && <Notice text={error} />}
      <section className="panel">
        <div className="panel-title">
          <h2>Conversation history</h2>
          <button onClick={refresh}>Refresh ↻</button>
        </div>
        {loading ? (
          <p className="padding">Loading…</p>
        ) : !rows.length ? (
          <EmptyState
            title="No calls yet"
            text="New activity will appear here automatically when you refresh."
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Caller</th>
                  <th>Started</th>
                  <th>Duration</th>
                  <th>Outcome</th>
                  <th>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((call) => (
                  <tr key={call.id}>
                    <td>
                      {call.caller_phone || "Number not provided"}
                      <small>{call.transport}</small>
                    </td>
                    <td>{formatDate(call.started_at)}</td>
                    <td>{call.duration_seconds}s</td>
                    <td>
                      <StatusBadge status={call.outcome} />
                    </td>
                    <td>
                      <Link
                        href={`/dashboard/calls/${encodeURIComponent(call.id)}`}
                      >
                        Details →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Pagination offset={offset} count={rows.length} onChange={setOffset} />
      </section>
    </>
  );
}
