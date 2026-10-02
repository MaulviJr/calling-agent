export function formatLabel(value: string): string {
  return value.replaceAll("_", " ");
}

export function formatDate(value: string | null, timezone?: string): string {
  if (!value) return "—";
  return new Date(value).toLocaleString(
    undefined,
    timezone ? { timeZone: timezone } : undefined,
  );
}
