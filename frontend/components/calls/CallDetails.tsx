"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, errorMessage } from "@/lib/api";
import type { CallDetail } from "@/lib/types";
import { formatDate } from "@/lib/formatting";
import Notice from "../dashboard/Notice";
import StatusBadge from "../dashboard/StatusBadge";
import Transcript from "./Transcript";

export default function CallDetails({ id }: { id: string }) {
  const [detail, setDetail] = useState<CallDetail | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<CallDetail>(`/calls/${encodeURIComponent(id)}`)
      .then((data) => {
        if (active) setDetail(data);
      })
      .catch((error) => {
        if (active) setError(errorMessage(error));
      });
    return () => {
      active = false;
    };
  }, [id]);
  return (
    <section className="panel form-panel">
      <Link href="/dashboard/calls">← Conversation history</Link>
      {error ? (
        <Notice text={error} />
      ) : !detail ? (
        <p>Loading conversation…</p>
      ) : (
        <>
          <h2>{formatDate(detail.started_at)}</h2>
          <StatusBadge status={detail.outcome} />
          <div className="summary">
            <h3>Call summary</h3>
            <p>
              {detail.summary || "Summary is available after the call ends."}
            </p>
            <small>
              {detail.summary_status === "ai"
                ? "AI-assisted summary"
                : "Structured record summary"}
            </small>
          </div>
          <Transcript turns={detail.turns} />
        </>
      )}
    </section>
  );
}
