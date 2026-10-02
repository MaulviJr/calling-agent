"use client";

import { useState } from "react";
import Link from "next/link";
import { api, errorMessage } from "@/lib/api";
import type { Message, MessageStatus } from "@/lib/types";
import { useRecords } from "@/lib/useRecords";
import { formatDate } from "@/lib/formatting";
import EmptyState from "../dashboard/EmptyState";
import Notice from "../dashboard/Notice";
import Pagination from "../dashboard/Pagination";
import StatusBadge from "../dashboard/StatusBadge";

export default function MessageList() {
  const { rows, loading, error, refresh, offset, setOffset } =
    useRecords<Message>("/messages");
  const [mutationError, setMutationError] = useState("");
  const [pending, setPending] = useState<string | null>(null);

  async function changeStatus(id: string, status: MessageStatus) {
    setPending(id);
    setMutationError("");
    try {
      await api(`/messages/${encodeURIComponent(id)}`, "PATCH", { status });
      refresh();
    } catch (error) {
      setMutationError(errorMessage(error));
    } finally {
      setPending(null);
    }
  }

  return (
    <>
      {(error || mutationError) && <Notice text={error || mutationError} />}
      <section className="panel">
        <div className="panel-title">
          <h2>Team inbox</h2>
          <button onClick={refresh}>Refresh ↻</button>
        </div>
        {loading ? (
          <p className="padding">Loading…</p>
        ) : !rows.length ? (
          <EmptyState
            title="No messages yet"
            text="New activity will appear here automatically when you refresh."
          />
        ) : (
          <div className="messages">
            {rows.map((message) => (
              <article key={message.id}>
                <div>
                  <strong>{message.caller_name}</strong>
                  <StatusBadge status={message.status} />
                  {message.escalated === 1 && (
                    <StatusBadge status="escalated" />
                  )}
                </div>
                <small>
                  {message.phone} · {formatDate(message.created_at)}
                </small>
                <p>{message.content}</p>
                <div className="actions">
                  <select
                    aria-label={`Message status for ${message.caller_name}`}
                    disabled={pending !== null}
                    value={message.status}
                    onChange={(event) =>
                      changeStatus(
                        message.id,
                        event.target.value as MessageStatus,
                      )
                    }
                  >
                    {(["new", "reviewed", "resolved"] as const).map(
                      (status) => (
                        <option key={status}>{status}</option>
                      ),
                    )}
                  </select>
                  {message.call_id && (
                    <Link
                      href={`/dashboard/calls/${encodeURIComponent(message.call_id)}`}
                    >
                      View call
                    </Link>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
        <Pagination offset={offset} count={rows.length} onChange={setOffset} />
      </section>
    </>
  );
}
