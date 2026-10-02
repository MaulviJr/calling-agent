"use client";

import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "./api";

// Shared only by the three paginated lists. Business rules stay in the backend.
export function useRecords<T>(path: string) {
  const [rows, setRows] = useState<T[]>([]);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);

  const refresh = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api<T[]>(`${path}?limit=50&offset=${offset}`)
      .then((data) => {
        if (active) setRows(data);
      })
      .catch((error) => {
        if (active) setError(errorMessage(error));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [path, offset, revision]);

  return { rows, offset, setOffset, loading, error, refresh };
}
